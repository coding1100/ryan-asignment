from __future__ import annotations

import logging
import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

load_dotenv()

from app.agent.agent import Agent, run_task_job
from app.agent.models import AgentResult
from app.llm.client import LangChainGenAILLMClient, VercelAILLMClient
from app.tools.governance import GovernanceNoteTool, governance_store
from app.tools.math import MathTool
from app.tools.web_search import WebSearchTool

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Agent Execution Core", version="0.1.0")

tools = [WebSearchTool(), MathTool(), GovernanceNoteTool()]

def _select_llm_client():
    backend = os.getenv("LLM_PROVIDER", "vercel").lower()
    if backend == "google":
        try:
            return LangChainGenAILLMClient()
        except RuntimeError as exc:
            logging.warning("Falling back to Vercel LLM client: %s", exc)
    return VercelAILLMClient()


llm_client = _select_llm_client()
agent = Agent(llm_client=llm_client, tools=tools)


class RunTaskRequest(BaseModel):
    goal: str = Field(..., description="Natural language goal for the agent.")
    context: Optional[str] = Field(
        default=None, description="Optional context or background details."
    )
    tools: Optional[list[str]] = Field(
        default=None, description="Optional list of tool names to enable for this run."
    )


def get_agent() -> Agent:
    return agent


@app.post("/run-task")
async def run_task(request: RunTaskRequest, agent: Agent = Depends(get_agent)) -> AgentResult:
    """
    Submit a task for the agent to execute.
    
    If no tools are specified, the agent will automatically have access to ALL tools
    and will intelligently decide which ones to use based on the query.
    """
    if not request.goal:
        raise HTTPException(status_code=400, detail="goal is required")

    tool_names = request.tools
    if tool_names is None:
        # Make agent fully autonomous - provide all available tools
        # Agent will decide which to use based on query
        tool_names = list(agent.tools.keys())
    
    result = await agent.run_task(
        goal=request.goal,
        context=request.context,
        tools=tool_names,
    )
    return result


@app.get("/governance-notes/{proposal_id}")
async def get_governance_notes(proposal_id: str):
    notes = await governance_store.get_notes(proposal_id)
    return {"proposal_id": proposal_id, "notes": notes}


@app.get("/healthz")
async def healthcheck():
    return {"status": "ok"}


# Expose a scheduler-friendly entry point
async def trigger_job(payload: dict) -> AgentResult:
    return await run_task_job(payload, agent)
