from __future__ import annotations

import logging
from typing import Iterable, Optional

from app.agent.models import AgentResult, PlanResponse, ToolExecution, ToolSpec
from app.llm.client import LLMClient
from app.tools.base import Tool

logger = logging.getLogger(__name__)


class Agent:
    """Minimal agent core that can plan and execute tool calls."""

    def __init__(self, llm_client: LLMClient, tools: Iterable[Tool]):
        self.llm_client = llm_client
        self.tools = {tool.name: tool for tool in tools}

    async def run_task(
        self,
        goal: str,
        context: Optional[str] = None,
        tools: Optional[list[str]] = None,
    ) -> AgentResult:
        tools_to_use = (
            {name: tool for name, tool in self.tools.items() if name in tools}
            if tools
            else self.tools
        )

        tool_specs = [
            ToolSpec(
                name=tool.name,
                description=tool.description,
                input_schema=tool.input_schema,
            )
            for tool in tools_to_use.values()
        ]

        plan = await self._plan(goal, context, tool_specs)

        trace: list[ToolExecution] = []
        any_error = False

        for idx, action in enumerate(plan.actions, start=1):
            if action.tool not in tools_to_use:
                trace.append(
                    ToolExecution(
                        step=idx,
                        tool=action.tool,
                        arguments=action.arguments,
                        status="error",
                        error="Tool not allowed or unknown",
                        reasoning=action.reasoning,
                    )
                )
                any_error = True
                continue

            tool = tools_to_use[action.tool]
            try:
                result = await tool.run(**action.arguments)
                trace.append(
                    ToolExecution(
                        step=idx,
                        tool=action.tool,
                        arguments=action.arguments,
                        status="success",
                        output=result,
                        reasoning=action.reasoning,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - we want to capture any failure
                logger.exception("Tool execution failed")
                trace.append(
                    ToolExecution(
                        step=idx,
                        tool=action.tool,
                        arguments=action.arguments,
                        status="error",
                        error=str(exc),
                        reasoning=action.reasoning,
                    )
                )
                any_error = True

        # Determine final output based on execution results
        final_output = plan.direct_response
        if not final_output:
            if trace:
                # Collect all successful tool outputs
                successful_outputs = [t for t in trace if t.status == "success"]
                
                # If multiple successful tools, aggregate their outputs
                if len(successful_outputs) > 1:
                    # Generate natural language summary
                    nl_summary = self._generate_natural_language_summary(successful_outputs)
                    
                    final_output = {
                        "results": [t.output for t in successful_outputs],
                        "count": len(successful_outputs),
                        "summary": f"Executed {len(successful_outputs)} tools successfully",
                        "natural_language_summary": nl_summary
                    }
                # Single successful tool or last tool result
                elif successful_outputs:
                    final_output = successful_outputs[0].output
                # All tools failed, return last error
                else:
                    final_output = trace[-1].error
            else:
                final_output = "No actions executed."
        
        # Post-process: Ask LLM to synthesize results into natural language answer
        # This is especially useful for search results
        if not plan.direct_response and successful_outputs and len(successful_outputs) > 0:
            try:
                synthesized_answer = await self._synthesize_results(
                    goal=goal,
                    context=context,
                    tool_executions=successful_outputs
                )
                if synthesized_answer:
                    # Add agent response to output
                    if isinstance(final_output, dict):
                        final_output["agent_response"] = synthesized_answer
                    else:
                        # For single tool outputs, wrap them
                        final_output = {
                            "raw_output": final_output,
                            "agent_response": synthesized_answer
                        }
            except Exception as e:
                logger.warning(f"Failed to synthesize results: {e}")
                # Continue without synthesis


        if any_error and trace:
            status = "partial"
        elif any_error:
            status = "error"
        else:
            status = "success"

        return AgentResult(
            status=status,
            output=final_output,
            trace=trace,
            notes=plan.reasoning,
        )

    async def _synthesize_results(
        self,
        goal: str,
        context: Optional[str],
        tool_executions: list[ToolExecution]
    ) -> Optional[str]:
        """Ask LLM to synthesize tool results into a natural language answer."""
        # Build a summary of tool results
        results_summary = []
        local_summary_parts = []  # For fallback
        
        for execution in tool_executions:
            tool_name = execution.tool
            output = execution.output
            
            # Extract data from unified schema
            data = output.get("data", {}) if isinstance(output, dict) else {}
            message = output.get("message", "") if isinstance(output, dict) else ""
            
            if tool_name == "web_search":
                # For search, include titles and snippets
                results = data.get("results", [])
                search_text = f"Search results for '{data.get('query', 'unknown')}':\n"
                
                # Local summary (fallback)
                if results:
                    top_result = results[0]
                    local_summary_parts.append(
                        f"Based on the search results, {top_result.get('snippet', 'information was found')}. "
                        f"See more at: {top_result.get('url', 'search results')}"
                    )
                else:
                    local_summary_parts.append("No search results were found.")
                
                for i, result in enumerate(results[:3], 1):  # Top 3 results
                    search_text += f"{i}. {result.get('title', 'Unknown')}\n"
                    search_text += f"   {result.get('snippet', 'No description')}\n"
                results_summary.append(search_text)
            
            elif tool_name == "math":
                result = data.get("result", "unknown")
                expr = data.get("expression", execution.arguments.get("expression", "calculation"))
                results_summary.append(f"Calculation: {expr} = {result}")
                local_summary_parts.append(f"The calculation {expr} equals {result}.")
            
            elif tool_name == "governance_note":
                proposal_id = data.get("proposal_id", execution.arguments.get("proposal_id", "unknown"))
                results_summary.append(f"Recorded note for proposal {proposal_id}")
                local_summary_parts.append(f"Successfully recorded governance note for proposal {proposal_id}.")
            
            else:
                results_summary.append(f"Tool {tool_name}: {message or str(data)[:200]}")
                local_summary_parts.append(message or f"Tool {tool_name} executed successfully.")
        
        combined_results = "\n\n".join(results_summary)
        
        # Try LLM synthesis first
        synthesis_prompt = f"""Based on the following tool results, provide a clear, concise answer to the user's question.

User's Question: {goal}
{f"Context: {context}" if context else ""}

Tool Results:
{combined_results}

Provide a natural, helpful answer that directly addresses the user's question. Be concise but informative."""

        try:
            # Try to get synthesis from LLM
            response = await self.llm_client.plan(
                goal=synthesis_prompt,
                context=None,
                tools=[]  # No tools for synthesis
            )
            
            # Extract direct response
            if response.direct_response:
                return response.direct_response
                
        except Exception as e:
            logger.warning(f"LLM synthesis failed: {e}")
        
        # Fallback: Use local summary
        if local_summary_parts:
            return " ".join(local_summary_parts)
        
        return None


    async def _plan(
        self, goal: str, context: Optional[str], tool_specs: list[ToolSpec]
    ) -> PlanResponse:
        """Ask the LLM to produce a tool plan, with a heuristic fallback."""
        try:
            return await self.llm_client.plan(goal, context, tool_specs)
        except Exception as exc:  # noqa: BLE001 - planning is best-effort
            logger.warning("LLM planning failed, using heuristics: %s", exc)
            return self._heuristic_plan(goal, tool_specs)

    def _heuristic_plan(self, goal: str, tool_specs: list[ToolSpec]) -> PlanResponse:
        """Fallback planner that uses simple rules when LLM is unavailable."""
        available = {spec.name for spec in tool_specs}
        actions = []
        reasoning = "Heuristic fallback plan based on keyword matching."

        goal_lower = goal.lower()
        if "governance" in goal_lower or "proposal" in goal_lower:
            if "governance_note" in available:
                proposal_id = self._extract_proposal_id(goal)
                actions.append(
                    {
                        "tool": "governance_note",
                        "arguments": {"proposal_id": proposal_id, "note": goal},
                    }
                )
        if any(char.isdigit() for char in goal) and "math" in available:
            actions.append({"tool": "math", "arguments": {"expression": goal}})
        if not actions and "web_search" in available:
            actions.append({"tool": "web_search", "arguments": {"query": goal}})

        from app.agent.models import ToolAction  # local import to avoid cycle

        return PlanResponse(
            actions=[ToolAction(**action, reasoning="") for action in actions],
            direct_response="Heuristic answer only; see trace for tool output." if not actions else None,
            reasoning=reasoning,
        )

    def _generate_natural_language_summary(self, successful_outputs: list[ToolExecution]) -> str:
        """Generate a natural language summary of multiple tool executions."""
        summaries = []
        
        for execution in successful_outputs:
            tool_name = execution.tool
            output = execution.output
            args = execution.arguments
            
            # Extract data from unified schema
            data = output.get("data", {}) if isinstance(output, dict) else {}
            
            # Generate tool-specific descriptions
            if tool_name == "math":
                expr = data.get("expression", args.get("expression", "calculation"))
                result = data.get("result", "unknown")
                summaries.append(f"Calculated {expr} which equals {result}")
            
            elif tool_name == "web_search":
                query = data.get("query", args.get("query", "search"))
                result_count = data.get("count", len(data.get("results", [])))
                summaries.append(f"Found {result_count} search results for '{query}'")
            
            elif tool_name == "governance_note":
                proposal_id = data.get("proposal_id", args.get("proposal_id", "unknown"))
                summaries.append(f"Recorded governance note for proposal {proposal_id}")
            
            else:
                # Generic fallback for unknown tools
                message = output.get("message", f"Executed {tool_name} successfully")
                summaries.append(message)
        
        # Join summaries naturally
        if len(summaries) == 1:
            return summaries[0] + "."
        elif len(summaries) == 2:
            return f"{summaries[0]}, and {summaries[1]}."
        else:
            # For 3+ items: "A, B, and C."
            return ", ".join(summaries[:-1]) + f", and {summaries[-1]}."

    @staticmethod
    def _extract_proposal_id(goal: str) -> str:
        """Lightweight extractor for proposal identifiers in text."""
        import re

        match = re.search(r"proposal[\s:-]*([A-Za-z0-9_-]+)", goal, flags=re.IGNORECASE)
        if match:
            return match.group(1)
        return "general"


async def run_task_job(payload: dict, agent: Agent) -> AgentResult:
    """
    Entry point usable by Trigger.dev or other schedulers.

    The payload should include the same fields as POST /run-task.
    """
    return await agent.run_task(
        goal=payload.get("goal", ""),
        context=payload.get("context"),
        tools=payload.get("tools"),
    )
