"""LLM Client to communicate with MCP server"""

import asyncio
import json
import logging
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncAzureOpenAI

load_dotenv()

logging.basicConfig(level=logging.INFO)

SYSTEM_INSTRUCTIONS = """
You are a helpful agent that can manage tasks in a task management system.
You can help the user by using the available tools.
"""

def tool_def_for_openai(name: str,
                        description: Optional[str],
                        input_schema: Dict[str, Any]) -> Dict[str, Any]:
    """Convert MCP tool definition to OpenAI function format."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description or "",
            "parameters": input_schema or {"type": "object", "properties": {}},
        },
    }

def extract_text_or_json_as_text(mcp_result) -> str:
    """Extract text or JSON content from an MCP result."""
    json_items = []
    texts = []
    for c in getattr(mcp_result, "content", []):
        t = getattr(c, "type", "")
        if t == "json" and hasattr(c, "json"):
            json_items.append(c.json)
        elif t == "text" and hasattr(c, "text"):
            texts.append(c.text)

    # If only JSON: return a single object or an array of objects
    if json_items and not texts:
        if len(json_items) == 1:
            return json.dumps(json_items[0], ensure_ascii=False, indent=2)
        return json.dumps(json_items, ensure_ascii=False, indent=2)

    # If only text: join lines
    if texts and not json_items:
        return "\n".join(texts)

    # Mixed: return a structured envelope
    return json.dumps({"json": json_items, "text": texts}, ensure_ascii=False, indent=2)

class TaskPilotAgent:
    """Agent for managing tasks using LLM and MCP."""
    def __init__(self, server_script: str = "task_pilot_server.py") -> None:
        self.server_script = server_script
        self.session: Optional[ClientSession] = None
        self.openai = AsyncAzureOpenAI(
            api_version="2024-08-01-preview",
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
        )
        self.model = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
        self._stack: Optional[AsyncExitStack] = None

    async def __aenter__(self):
        self._stack = AsyncExitStack()
        # Absolute path to the server script
        server_path = str(Path(__file__).with_name(self.server_script))
        params = StdioServerParameters(
            command=sys.executable,
            args=["-u", server_path],
            env=None,
        )
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._stack:
            await self._stack.aclose()

    async def list_tools_for_openai(self) -> List[Dict[str, Any]]:
        """List available tools in OpenAI format."""
        assert self.session is not None
        tools = await self.session.list_tools()
        return [tool_def_for_openai(t.name, t.description, t.inputSchema) for t in tools.tools]

    async def call_mcp_tool(self, name: str, args: Dict[str, Any]) -> str:
        """Call an MCP tool by name with given arguments."""
        assert self.session is not None
        result = await self.session.call_tool(name, arguments=args)
        return extract_text_or_json_as_text(result)

    async def chat(self, user_prompt: str) -> str:
        """Chat with the LLM, allowing it to call MCP tools as needed."""
        
        tools = await self.list_tools_for_openai()
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": user_prompt},
        ]

        # First call to the model
        try:
            response = await self.openai.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
            )
        except Exception as e:
            logging.error("OpenAI API error: %s", e)
            return "Sorry, there was an error communicating with the model."
        
        # Process the model's response
        response_message = response.choices[0].message
        messages.append(response_message)

        # Handle tool calls loop
        if response_message.tool_calls:
            for tool_call in response_message.tool_calls:
                print(f"Tool call requested: {tool_call.function.name} with args {tool_call.function.arguments}")
                # Execute tool call
                result = await self.call_mcp_tool(
                    tool_call.function.name,
                    args=json.loads(tool_call.function.arguments),
                )
                
                messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": tool_call.function.name,
                    "content": result,
                })
        else:
            print("No tool calls were made by the model.")

        # Call the model again with tool outputs
        try:
            final_response = await self.openai.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="none",
            )
        except Exception as e:
            logging.error("OpenAI API error: %s", e)
            return "Sorry, there was an error communicating with the model."

        return final_response.choices[0].message.content

# --------- Executable ---------
async def main():
    """Main function to run the TaskPilotAgent."""
   
    user_prompt = "list all my tasks"
   
    if len(sys.argv) > 1:
        user_prompt = " ".join(sys.argv[1:])

    print(f"Prompt: {user_prompt}\n")
   
    async with TaskPilotAgent("task_pilot_server.py") as agent:

        # Chat with the model
        answer = await agent.chat(user_prompt)
        print("Model response:\n")
        print(answer)

if __name__ == "__main__":
    asyncio.run(main())
