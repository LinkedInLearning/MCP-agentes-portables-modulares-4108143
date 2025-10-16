"""MCP Client using OpenAI models and tools."""
import asyncio
import json
import logging
import sys as sys, pathlib as _pathlib
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncAzureOpenAI

# FastAPI for HTTP endpoint so Azure Bot Service can call the client
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

LOG = logging.getLogger("client_openai")

# Load environment variables
load_dotenv()

# (Bot Framework integration removed) The app provides a simple SPA and /message endpoint.


class MCPClient:
    """Client for interacting with OpenAI models using MCP tools."""

    def __init__(self, model: str = "gpt-4.1"):
        """Initialize the OpenAI MCP client.

        Args:
            model: The LLM to use.
        """
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        # NOTE: construction of AsyncAzureOpenAI depends on environment
        # (API keys and endpoints). We rely on the library to pick up
        # env vars, but we still create a client instance to use.
        self.openai_client = AsyncAzureOpenAI(api_version="2024-12-01-preview")
        self.model = model
        self.stdio: Optional[Any] = None
        self.write: Optional[Any] = None

    async def connect_to_server(self, server_script_path: str = "task_pilot_server.py"):
        """Connect to an MCP server.

        Improvements:
        - Use the running Python interpreter (sys.executable) to launch the
          server script which avoids mismatched python executables.
        - Add logging and basic validation of returned tools.
        """
        # Server configuration
        # Use the current Python executable to avoid mismatched environments
        python_exe = sys.executable or "python"
        # Resolve the server script to an absolute path relative to this file
        server_path = _pathlib.Path(server_script_path)
        if not server_path.is_absolute():
            server_path = (_pathlib.Path(__file__).parent / server_path).resolve()

        server_params = StdioServerParameters(
            command=python_exe,
            args=[str(server_path)],
        )

        # Connect to the server
        stdio_transport = await self.exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(self.stdio, self.write)
        )

        # Initialize the connection. Wrap to capture server-side import/runtime
        # errors (for example task_pilot_server.py raising on missing env vars).
        try:
            await self.session.initialize()
        except Exception as e:
            # Provide a clearer diagnostic message and include the original
            # exception. The underlying error often originates from the server
            # process failing to start (import errors or RuntimeError in
            # task_pilot_server.py).
            LOG.exception("Failed to initialize MCP session: %s", e)
            # Ensure we close any partially-opened resources
            try:
                await self.exit_stack.aclose()
            except Exception:
                pass
            # Re-raise a more descriptive exception for the caller
            raise RuntimeError(
                "Could not start or connect to MCP server. Check server logs and ensure required env vars (e.g. AZURE_STORAGE_ACCOUNT, AZURE_STORAGE_CONTAINER) are set."
            ) from e

        # List available tools
        tools_result = await self.session.list_tools()
        print("\nConnected to server with tools:")
        for tool in tools_result.tools:
            print(f"  - {tool.name}: {tool.description}")

    async def get_mcp_tools(self) -> List[Dict[str, Any]]:
        """Obtain MCP server tools in the OpenAI format.

        Returns:
            A list of tools in OpenAI format.
        """
        tools_result = await self.session.list_tools()
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                },
            }
            for tool in tools_result.tools
        ]

    async def process_query(self, query: str) -> str:
        """Process a query using OpenAI and available MCP tools.

        Args:
            query: The user query.

        Returns:
            The response from OpenAI.
        """
        # Get available tools
        tools = await self.get_mcp_tools()

        # Initial OpenAI API call
        response = await self.openai_client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": query}],
            tools=tools,
            tool_choice="auto",
        )

        # Get assistant's response
        assistant_message = response.choices[0].message

        # Initialize conversation with user query and assistant response
        messages = [
            {"role": "user", "content": query},
            assistant_message,
        ]

        # Handle tool calls if present
        if assistant_message.tool_calls:
            # Process each tool call
            for tool_call in assistant_message.tool_calls:
                # Execute tool call
                result = await self.session.call_tool(
                    tool_call.function.name,
                    arguments=json.loads(tool_call.function.arguments),
                )

                # Add tool response to conversation
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result.content[0].text,
                    }
                )

            # Get final response from OpenAI with tool results
            final_response = await self.openai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="none",  # Don't allow more tool calls
            )
            return final_response.choices[0].message.content

        # No tool calls, just return the direct response
        return assistant_message.content

    async def cleanup(self):
        """Clean up resources."""
        await self.exit_stack.aclose()

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

app = FastAPI()
# Mount static files (chat SPA)
app.mount("/static", StaticFiles(directory="./static"), name="static")


@app.get("/")
async def root_html():
    """Serve the main HTML page."""
    return FileResponse("./static/chat.html")


# Bot debug endpoints removed — this app now exposes a simple SPA and /message endpoint only.


@app.post("/message")
async def receive_message(req: Request):
    """Endpoint to receive messages from an Azure Bot or other HTTP client.
    Expects JSON {"text": "..."} and returns the assistant response.
    """
    payload = await req.json()
    text = payload.get("text") if isinstance(payload, dict) else None
    if not text:
        return {"error": "missing text"}

    # For simplicity, create a temporary MCPClient and connect to local server
    client = MCPClient()
    try:
        await client.connect_to_server("task_pilot_server.py")
        resp = await client.process_query(text)
        return {"reply": resp}
    finally:
        await client.cleanup()

async def main():
    """Main function to run the MCP client"""
    if len(sys.argv) < 2:
        print("Usage: python client_openai.py task_pilot_server.py")
        sys.exit(1)

    client = MCPClient()
    try:
        await client.connect_to_server(sys.argv[1])
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
