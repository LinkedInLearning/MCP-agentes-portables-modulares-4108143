"""Server-side task management with MCP."""
import time
import logging
import os
import json
from uuid import uuid4
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from mcp.server.fastmcp import FastMCP, Context
from azure.storage.blob import BlobClient

LOG = logging.getLogger("task_pilot")

load_dotenv()

AZURE_STORAGE_CONNECTION_STRING = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
AZURE_STORAGE_CONTAINER = os.environ.get("AZURE_STORAGE_CONTAINER", "tasks")
AZURE_STORAGE_BLOB_NAME = os.environ.get("AZURE_STORAGE_BLOB_NAME", "tasks.json")

def get_blob_client():
    """Return a BlobClient when Azure Storage."""
    blob_client = None
    if AZURE_STORAGE_CONNECTION_STRING:
        blob_client = BlobClient.from_connection_string(
            AZURE_STORAGE_CONNECTION_STRING, container_name=AZURE_STORAGE_CONTAINER,
            blob_name=AZURE_STORAGE_BLOB_NAME)
    return blob_client

def read_blob_with_retry(blob_client: Any, retries: int = 3, backoff: float = 0.5):
    """Read the task store from Blob Storage with retries."""
    for attempt in range(1, retries + 1):
        try:
            stream = blob_client.download_blob()
            return json.loads(stream.readall())
        except Exception as e:
            LOG.warning("Blob read error (attempt %d/%d): %s", attempt, retries, e)
            if attempt == retries:
                raise
            time.sleep(backoff * attempt)

def write_blob_with_retry(blob_client: Any, store: Dict[str, dict], retries: int = 3, backoff: float = 0.5):
    """Write the task store to Blob Storage with retries."""
    data = json.dumps(store, indent=2).encode("utf-8")
    for attempt in range(1, retries + 1):
        try:
            blob_client.upload_blob(data, overwrite=True)
            return
        except Exception as e:
            LOG.warning("Blob write error (attempt %d/%d): %s", attempt, retries, e)
            if attempt == retries:
                raise
            time.sleep(backoff * attempt)

def load() -> Dict[str, dict]:
    """Load the task store from Blob Storage. Raises if storage not available."""
    blob = get_blob_client()
    return read_blob_with_retry(blob)

def save(store: Dict[str, dict]) -> None:
    """Save the task store to Blob Storage. Raises on failure."""
    blob = get_blob_client()
    write_blob_with_retry(blob, store)

# ---------- Data model ----------
class Task(BaseModel):
    """A simple task item."""
    id: str = Field(default_factory=lambda: uuid4().hex)
    title: str
    done: bool = False
    tags: list[str] = []

# Resolve any forward refs (safe even if none exist)
Task.model_rebuild()

STORE: Dict[str, dict] = load()

# ---------- MCP Setup ----------
mcp = FastMCP("TaskPilot")

# ---------- Tools ----------
@mcp.tool()
async def add_task(title: str, ctx: Context, tags: Optional[list[str]] = None) -> Task:
    """Create and persist a new task."""
    title = (title or "").strip()
    if not title:
        ctx.error("Title cannot be empty.")
        raise ValueError("Title cannot be empty.")
    task = Task(title=title, tags=[t for t in (tags or []) if t.strip()])
    STORE[task.id] = task.model_dump()
    await ctx.info(f"Created task {task.id}: {task.title}")
    save(STORE)
    return task

@mcp.tool()
def list_tasks(include_done: bool = True) -> list[Task]:
    """Return all tasks (filtering by completion)."""
    tasks = [Task(**t) for t in STORE.values()]
    if not include_done:
        tasks = [t for t in tasks if not t.done]
    return tasks

@mcp.tool()
def complete_task(task_id: str) -> Task:
    """Mark a task completed and save it."""
    if task_id not in STORE:
        raise ValueError(f"Task not found: {task_id}")
    t = Task(**STORE[task_id])
    t.done = True
    STORE[t.id] = t.model_dump()
    save(STORE)
    return t

@mcp.tool()
def clear_completed() -> int:
    """Remove all completed tasks. Returns number removed."""
    removed = 0
    for tid in list(STORE.keys()):
        if STORE[tid].get("done"):
            del STORE[tid]
            removed += 1
    if removed:
        save(STORE)
    return removed

# ---------- Resources (read-only) ----------
@mcp.resource("tasks://all")
def get_all_tasks() -> str:
    """Return the entire task store as JSON."""
    return json.dumps(STORE, indent=2)

@mcp.resource("task://{task_id}")
def get_task(task_id: str) -> str:
    """Return a single task as JSON by id."""
    if task_id not in STORE:
        return json.dumps({"error": "not found", "id": task_id})
    return json.dumps(STORE[task_id], indent=2)

@mcp.prompt(title="Write a status note")
def status_note(title: str):
    """Suggest a short status line for a task title."""
    return [
        {
            "role": "system",
            "content": {
                "type": "text", "text": "You are a concise assistant who writes status notes."
            },
        },
        {
            "role": "user",
            "content": {
                "type": "text", "text": f'Create a one-line status note for the task: "{title}"'
            },
        },
    ]

if __name__ == "__main__":
    mcp.run()
