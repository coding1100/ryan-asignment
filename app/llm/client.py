from __future__ import annotations

import json
import os
import textwrap
from typing import Optional, Protocol

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from openai import AsyncOpenAI
from vercel_ai.providers.openai import stream_completion

from app.agent.models import PlanResponse, ToolAction, ToolSpec


class LLMClient(Protocol):
    """Interface for planner backends."""

    async def plan(self, goal: str, context: Optional[str], tools: list[ToolSpec]) -> PlanResponse:
        ...


def _build_prompt(goal: str, context: Optional[str], tools: list[ToolSpec]) -> dict[str, str]:
    tool_descriptions = "\n".join(
        f"- {tool.name}: {tool.description}. Input schema: {json.dumps(tool.input_schema)}"
        for tool in tools
    )

    system_prompt = textwrap.dedent(
        f"""
        You are the planning brain for an AI operator. Choose tools and arguments to achieve the goal.
        Only use tools that are listed below. Respond with JSON that matches:
        {{
          "actions": [{{"tool": "<tool_name>", "arguments": {{}}, "reasoning": "why"}}],
          "direct_response": "optional plain answer if tools unnecessary",
          "reasoning": "high level thoughts"
        }}
        Tools available:
        {tool_descriptions}
        """
    ).strip()

    user_prompt = f"Goal: {goal}\\n\\nContext: {context or 'None provided.'}"
    return {"system": system_prompt, "user": user_prompt}


def _parse_plan(raw_text: str, tools: list[ToolSpec]) -> PlanResponse:
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        # Attempt to salvage trailing text
        clipped = raw_text.strip()
        brace_start = clipped.find("{")
        brace_end = clipped.rfind("}")
        if brace_start != -1 and brace_end != -1:
            data = json.loads(clipped[brace_start : brace_end + 1])
        else:
            raise

    actions = []
    tool_names = {t.name for t in tools}
    for item in data.get("actions", []):
        tool_name = item.get("tool") or item.get("name")
        if tool_name and tool_name in tool_names:
            actions.append(
                ToolAction(
                    tool=tool_name,
                    arguments=item.get("arguments", {}) or item.get("args", {}),
                    reasoning=item.get("reasoning") or item.get("commentary"),
                )
            )

    return PlanResponse(
        actions=actions,
        direct_response=data.get("direct_response") or data.get("final_response"),
        reasoning=data.get("reasoning") or data.get("notes"),
    )


class VercelAILLMClient:
    """
    LLM client backed by the Vercel AI SDK streaming adapter.

    The client talks to any OpenAI-compatible endpoint via AsyncOpenAI, but uses
    vercel_ai.providers.openai.stream_completion to stay aligned with the AI SDK
    semantics (step parts, tool call streaming, token usage).
    """

    def __init__(self, model: Optional[str] = None):
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url) if api_key else None

    async def plan(self, goal: str, context: Optional[str], tools: list[ToolSpec]) -> PlanResponse:
        if not self.client:
            raise RuntimeError("OPENAI_API_KEY is not set; LLM planning is unavailable.")

        prompt = _build_prompt(goal, context, tools)
        completion = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": prompt["system"]},
                {"role": "user", "content": prompt["user"]},
            ],
            temperature=0.1,
            stream=True,
            response_format={"type": "json_object"},
        )

        text_buffer = ""
        async for part in stream_completion(completion):
            # We only need the text delta parts to reconstruct the JSON plan
            if hasattr(part, "text_delta"):
                text_buffer += part.text_delta

        if not text_buffer.strip():
            raise RuntimeError("LLM returned an empty plan.")

        return _parse_plan(text_buffer, tools)


class LangChainGenAILLMClient:
    """Planner backed by LangChain + Google GenAI."""

    def __init__(self, model: Optional[str] = None):
        self.model = model or os.getenv("GOOGLE_GENAI_MODEL", "gemini-2.5-flash")
        api_key = os.getenv("GOOGLE_GENAI_API_KEY")
        self.api_key = api_key
        self.llm = (
            ChatGoogleGenerativeAI(
                model=self.model,
                temperature=0.1,
                api_key=api_key,
                convert_system_message_to_human=True,
            )
            if api_key
            else None
        )

    async def plan(self, goal: str, context: Optional[str], tools: list[ToolSpec]) -> PlanResponse:
        if not self.llm or not self.api_key:
            raise RuntimeError("GOOGLE_GENAI_API_KEY is not set; Google planning unavailable.")
        prompt = _build_prompt(goal, context, tools)
        # Build chat messages for LangChain
        messages = [SystemMessage(content=prompt["system"]), HumanMessage(content=prompt["user"])]
        response = await self.llm.ainvoke(messages)
        text = self._extract_text(response.content)
        if not text:
            raise RuntimeError("Google GenAI returned an empty plan.")
        return _parse_plan(text, tools)

    def _extract_text(self, content) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list) and content and isinstance(content[0], dict):
            # google genai may return list of parts
            return " ".join(part.get("text", "") for part in content)
        return str(content)
