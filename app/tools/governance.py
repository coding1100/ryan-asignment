from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import aiosqlite

from app.tools.base import Tool


class GovernanceStore:
    """Persistent SQLite-backed storage for governance notes."""

    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            # Use absolute path relative to this file's location
            project_root = Path(__file__).parent.parent.parent
            db_path = str(project_root / "data" / "governance.db")
        
        self.db_path = db_path
        self._lock = asyncio.Lock()
        self._initialized = False

    async def _init_db(self) -> None:
        """Initialize database and create table if not exists."""
        if self._initialized:
            return
        
        # Ensure data directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS governance_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proposal_id TEXT NOT NULL,
                    note TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            
            # Create index for faster lookups
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_proposal_id 
                ON governance_notes(proposal_id)
            """)
            
            await db.commit()
        
        self._initialized = True

    async def add_note(self, proposal_id: str, note: str) -> dict:
        """Add a governance note to the database."""
        await self._init_db()
        
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        entry = {"note": note, "timestamp": timestamp}
        
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT INTO governance_notes (proposal_id, note, timestamp) VALUES (?, ?, ?)",
                    (proposal_id, note, timestamp)
                )
                await db.commit()
        
        return entry

    async def get_notes(self, proposal_id: str) -> list[dict]:
        """Retrieve all notes for a given proposal ID."""
        await self._init_db()
        
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT note, timestamp FROM governance_notes WHERE proposal_id = ? ORDER BY id ASC",
                    (proposal_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [{"note": row["note"], "timestamp": row["timestamp"]} for row in rows]


# Global singleton instance
governance_store = GovernanceStore()


class GovernanceNoteTool(Tool):
    """Adds a governance note for a proposal ID with persistent storage."""

    name = "governance_note"
    description = "Appends a governance note to a persistent database ledger keyed by proposal_id."
    input_schema = {
        "type": "object",
        "properties": {
            "proposal_id": {"type": "string", "description": "Proposal identifier"},
            "note": {"type": "string", "description": "The note to append"},
        },
        "required": ["proposal_id", "note"],
    }

    async def run(self, proposal_id: str, note: str) -> dict:
        if not proposal_id:
            raise ValueError("proposal_id is required")
        if not note:
            raise ValueError("note is required")
        entry = await governance_store.add_note(proposal_id, note)
        return {
            "success": True,
            "data": {
                "proposal_id": proposal_id,
                "note": entry["note"],
                "timestamp": entry["timestamp"]
            },
            "message": f"Note recorded for proposal {proposal_id}"
        }


