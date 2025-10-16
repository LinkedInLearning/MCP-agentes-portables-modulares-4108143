"""Main entry point to start the MCP server."""
from fastapi import FastAPI
from task_pilot_server import mcp
import uvicorn

app = FastAPI()

app = mcp.streamable_http_app()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)