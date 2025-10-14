"""Server-side task management with MCP."""

from pathlib import Path
from typing import Optional, Dict
from uuid import uuid4
import json

from pydantic import BaseModel, Field
from mcp.server.fastmcp import FastMCP, Context

DATA_FILE = Path("data/tasks.json")
DATA_FILE.parent.mkdir(exist_ok=True)

def load() -> Dict[str, dict]:
    """Load the task store from disk, or return empty."""
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {}

def save(store: Dict[str, dict]) -> None:
    """Save the task store to disk."""
    DATA_FILE.write_text(json.dumps(store, indent=2), encoding="utf-8")

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
def add_task(title: str, tags: Optional[list[str]] = None) -> Task:
    """Create and persist a new task."""
    title = (title or "").strip()
    if not title:
        raise ValueError("Title cannot be empty.")
    task = Task(title=title, tags=[t for t in (tags or []) if t.strip()])
    STORE[task.id] = task.model_dump()
    save(STORE)
    return task

@mcp.tool()
def list_tasks(include_done: bool = False) -> list[Task]:
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

@mcp.tool()
async def bulk_import(lines: list[str], ctx: Context) -> int:
    """
    Import tasks from a list of lines (one title per line).
    Emits progress notifications visible in Inspector.
    """
    total = len(lines) or 1
    created = 0
    await ctx.info(f"Starting import of {len(lines)} tasks")

    for idx, raw in enumerate(lines, start=1):
        title = (raw or "").strip()
        if not title:
            await ctx.warning(f"Skipping empty line {idx}")
            continue
        t = Task(title=title)
        STORE[t.id] = t.model_dump()
        created += 1

        await ctx.report_progress(progress=idx, total=total, message=f"Imported {idx}/{total}")
        await ctx.debug(f"Created task {t.id}: {t.title}")

    save(STORE)
    await ctx.info(f"Import complete: {created} created")
    return created

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
