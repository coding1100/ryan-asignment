from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """Common interface for executable tools."""

    name: str
    description: str
    input_schema: dict[str, Any]

    @abstractmethod
    async def run(self, **kwargs) -> dict[str, Any]:
        """Execute the tool with validated kwargs."""
        raise NotImplementedError
