"""LLM Client to communicate with MCP server"""

import asyncio
import json
import os
import sys
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import AsyncOpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()  # loads OPENAI_API_KEY if you have .env

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# --------- Utilities ---------
def _tool_def_for_openai(
    name: str,
    description: Optional[str],
    input_schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Takes a tool definition from MCP and converts it to OpenAI function format.
    OpenAI expects a JSON Schema for the parameters.
    """
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description or "",
            "parameters": input_schema or {"type": "object", "properties": {}},
        },
    }

def _extract_text_or_json_as_text(mcp_result) -> str:
    """
    MCP can return content in various formats (text, json, etc).
    This function extracts the content and returns it as a string.
    """
    for c in getattr(mcp_result, "content", []):
        t = getattr(c, "type", "")
        if t == "json" and hasattr(c, "json"):
            try:
                return json.dumps(c.json, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                # defensive fallback
                return str(c.json)
        if t == "text" and hasattr(c, "text"):
            return c.text
    return ""  # empty if there was no content (unlikely)

SYSTEM_INSTRUCTIONS = (
    """
    You are a helpful agent that can manage tasks in a task management system.
    You can help the user by using the available tools.
    """
)

# --------- LLM + MCP Client ---------
class TaskPilotAgent:
    """Agent for managing tasks using LLM and MCP."""
    def __init__(self, server_script: str = "task_pilot_server.py") -> None:
        self.server_script = server_script
        self.session: Optional[ClientSession] = None
        self.openai = AsyncOpenAI()
        self._stdio_ctx = None

    async def __aenter__(self):
        params = StdioServerParameters(
            command=sys.executable,  # use the same Python interpreter as the script
            args=[self.server_script],
        )
        self._stdio_ctx = stdio_client(params)
        # Get the first yielded value from the async generator
        async for read_write in self._stdio_ctx:
            read, write = read_write
            break
        self.session = await ClientSession(read, write).__aenter__()
        await self.session.initialize()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        """Cleanup the session and stdio context."""
        if self.session:
            await self.session.__aexit__(exc_type, exc, tb)
        if self._stdio_ctx:
            await self._stdio_ctx.aclose()

    async def list_tools_for_openai(self) -> List[Dict[str, Any]]:
        """Lists available tools in a format compatible with OpenAI function calling."""
        assert self.session is not None
        tools = await self.session.list_tools()
        return [_tool_def_for_openai(t.name, t.description, t.inputSchema) for t in tools.tools]

    async def call_mcp_tool(self, name: str, args: Dict[str, Any]) -> str:
        """Executes a tool on the server and ALWAYS returns a string (text or serialized JSON)."""
        assert self.session is not None
        result = await self.session.call_tool(name, arguments=args)
        return _extract_text_or_json_as_text(result)

    async def chat(self, user_prompt: str, *, max_tool_loops: int = 3) -> str:
        """
        One-turn conversation with tool calls.
        The function will call tools as needed, up to max_tool_loops times.
        """
        tools = await self.list_tools_for_openai()

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": user_prompt},
        ]

        # 1) first call, to get initial response or tool calls
        response = await self.openai.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        msg = response.choices[0].message
        messages.append({"role": "assistant", "content": msg.content, "tool_calls": msg.tool_calls})

        loops = 0
        # 2) while there are tool calls, execute them and retry
        while msg.tool_calls and loops < max_tool_loops:
            loops += 1
            tool_results_msgs: List[Dict[str, Any]] = []

            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}

                # Execute tool on the MCP server
                tool_output = await self.call_mcp_tool(name, args)

                # Attach the tool response to the history, as OpenAI expects
                tool_results_msgs.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_output,
                })

            messages.extend(tool_results_msgs)

            # 3) request the final answer (or more tool calls)
            response = await self.openai.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=tools,
                tool_choice="auto",   # still allow tool calls, in case the model chains them
            )
            msg = response.choices[0].message
            messages.append({"role": "assistant", "content": msg.content, "tool_calls": msg.tool_calls})

        # 4) if there are no pending tool calls, return the last assistant response
        return msg.content or "(no content)"

# --------- Executable ---------
async def main():
    """Example usage of TaskPilotAgent."""
    user_prompt = "Create a task 'Record chapter 2' with the label course, then list all tasks."
    if len(sys.argv) > 1:
        user_prompt = " ".join(sys.argv[1:])

    print(f"Prompt: {user_prompt}\n")

    async with TaskPilotAgent("task_pilot_server.py") as agent:
        # (optional) show detected tools
        tools = await agent.list_tools_for_openai()
        print("Available tools:")
        for t in tools:
            print(f"- {t['function']['name']}: {t['function'].get('description','')}")
        print()

        answer = await agent.chat(user_prompt)
        print("Agent response:\n")
        print(answer)

if __name__ == "__main__":
    asyncio.run(main())
