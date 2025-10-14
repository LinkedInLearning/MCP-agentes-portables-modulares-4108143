""" MCP Client using OpenAI's Azure API and MCP protocol."""
import asyncio
import os
import json
import sys
from typing import Optional
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from openai import AsyncAzureOpenAI
from dotenv import load_dotenv

load_dotenv()  # load environment variables from .env

def mcp_tool_to_openai(t):
    return {
        "type": "function",
        "function": {
            "name": t.name,
            "description": t.description or "",
            "parameters": t.inputSchema or {"type": "object", "properties": {}},
        },
    }

def mcp_result_to_text(result) -> str:
    parts = []
    for c in getattr(result, "content", []) or []:
        t = getattr(c, "type", None)
        if t == "json" and hasattr(c, "json"):
            try:
                parts.append(json.dumps(c.json, ensure_ascii=False, indent=2))
            except Exception:
                parts.append(str(c.json))
        elif t == "text" and hasattr(c, "text"):
            parts.append(c.text)
    return "\n".join(parts) if parts else ""


class MCPClient:
    """MCP Client to interact with an MCP server using OpenAI's Azure API."""
    def __init__(self):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.openai = AsyncAzureOpenAI(
            api_version="2024-08-01-preview",
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
        )
        self.write = None
        self.stdio = None
    
    async def connect_to_server(self, server_script_path: str):
        """Connect to an MCP server

        Args:
            server_script_path: Path to the server script (.py or .js)
        """
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")

        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=None
        )

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()

        # List available tools
        response = await self.session.list_tools()
        tools = response.tools
        print("\nConnected to server with tools:", [tool.name for tool in tools])
    
    async def process_query(self, query: str) -> str:
        """Process a query using Azure OpenAI and available tools"""
        messages = [
            {
                "role": "user",
                "content": query
            }
        ]

        tools = await get_mcp_tools()

        # Initial OpenAI API call
        response = await self.openai.chat.completions.create(
            model="gpt-4.1",
            max_tokens=1000,
            messages=messages,
            tools=tools,
        )

        # Process response and handle tool calls
        final_text = []

        assistant_message_content = []
        for content in response.content:
            if content.type == 'text':
                final_text.append(content.text)
                assistant_message_content.append(content)
            elif content.type == 'tool_use':
                tool_name = content.name
                tool_args = content.input

                # Execute tool call
                result = await self.session.call_tool(tool_name, tool_args)
                final_text.append(f"[Calling tool {tool_name} with args {tool_args}]")
                content_text = mcp_result_to_text(result)

                assistant_message_content.append(content_text)
                messages.append({
                    "role": "assistant",
                    "content": assistant_message_content
                })
                messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": content.id,
                            "content": content_text
                        }
                    ]
                })

                # Get next response from OpenAI
                response = await self.openai.chat.completions.create(
                    model="gpt-4.1",
                    max_tokens=1000,
                    messages=messages,
                    tools=tools
                )

                final_text.append(response.content[0].text)

        return "\n".join(final_text)
    
    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")

        while True:
            try:
                query = input("\nQuery: ").strip()

                if query.lower() == 'quit':
                    break

                response = await self.process_query(query)
                print("\n" + response)

            except Exception as e:
                print(f"\nError: {str(e)}")

    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()
        
# Main entry point
async def main():
    """Main function to run the MCP client"""
    if len(sys.argv) < 2:
        print("Usage: python client.py task_pilot_server.py")
        sys.exit(1)

    client = MCPClient()
    try:
        await client.connect_to_server(sys.argv[1])
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
