"""Server-side task management with MCP."""
import time
import logging
import os
import os as _os
import json
from dotenv import load_dotenv
from typing import Optional, Dict, Any
from uuid import uuid4
from pydantic import BaseModel, Field
from mcp.server.fastmcp import FastMCP, Context
from azure.identity import EnvironmentCredential, DefaultAzureCredential
try:
    from azure.storage.blob import BlobClient
    from azure.core.exceptions import ResourceNotFoundError, HttpResponseError
except ImportError:
    # Import failures are handled at runtime; developer should `pip install azure-storage-blob azure-identity`
    BlobClient = None
    ResourceNotFoundError = None
    HttpResponseError = None

LOG = logging.getLogger("task_pilot")

load_dotenv()

STORAGE_BLOB_NAME = "tasks.json"

# Configuration: environment-driven. AZURE_STORAGE_ACCOUNT and AZURE_STORAGE_CONTAINER
# are required. This server persists tasks exclusively to Azure Blob Storage.
STORAGE_ACCOUNT = os.environ.get("AZURE_STORAGE_ACCOUNT")
STORAGE_CONTAINER = os.environ.get("AZURE_STORAGE_CONTAINER")
if not STORAGE_ACCOUNT or not STORAGE_CONTAINER:
    raise RuntimeError(
        "AZURE_STORAGE_ACCOUNT and AZURE_STORAGE_CONTAINER must be set to use Azure Blob persistence"
    )

LOG.info("Configured to use Azure Blob Storage: account=%s container=%s",
          STORAGE_ACCOUNT, STORAGE_CONTAINER)

def _get_blob_client():
    """Return a BlobClient when Azure Storage configuration is present, else None."""
    if BlobClient is None:
        raise RuntimeError("azure.storage.blob is not installed. Please install azure-storage-blob and azure-identity")
    
    # Try DefaultAzureCredential first (preferred for production / managed identity)
    last_exc = None
    try:
        credential = EnvironmentCredential()
        # quick test token call to surface authentication errors early
        credential.get_token("https://storage.azure.com/.default")
        url = f"https://{STORAGE_ACCOUNT}.blob.core.windows.net/{STORAGE_CONTAINER}/{STORAGE_BLOB_NAME}"
        return BlobClient.from_blob_url(blob_url=url, credential=credential)
    except Exception as e_default:
        LOG.warning("DefaultAzureCredential unavailable: %s", e_default)
        last_exc = e_default

    # Fallback: try Azure CLI credential (requires 'az' available in PATH)
    try:
        from azure.identity import AzureCliCredential

        try:
            cli_cred = AzureCliCredential()
            cli_cred.get_token("https://storage.azure.com/.default")
            url = f"https://{STORAGE_ACCOUNT}.blob.core.windows.net/{STORAGE_CONTAINER}/{STORAGE_BLOB_NAME}"
            return BlobClient.from_blob_url(blob_url=url, credential=cli_cred)
        except Exception as e_cli:
            LOG.warning("AzureCliCredential failed: %s", e_cli)
            last_exc = e_cli
    except Exception as import_cli_err:
        LOG.debug("AzureCliCredential not available: %s", import_cli_err)

    # Fallback: use account key from environment (StorageSharedKeyCredential)
    key = _os.environ.get("AZURE_STORAGE_KEY") or _os.environ.get("AZURE_STORAGE_ACCOUNT_KEY")
    if key:
        try:
            shared_cred = StorageSharedKeyCredential(STORAGE_ACCOUNT, key)
            url = f"https://{STORAGE_ACCOUNT}.blob.core.windows.net/{STORAGE_CONTAINER}/{STORAGE_BLOB_NAME}"
            return BlobClient.from_blob_url(blob_url=url, credential=shared_cred)
        except Exception as e_key:
            LOG.warning("StorageSharedKeyCredential failed: %s", e_key)
            last_exc = e_key

    # No credential strategy succeeded — raise a helpful error with hints
    hint = (
        "Could not create an authenticated BlobClient. Ensure one of the following is available:\n"
        " - DefaultAzureCredential works (Managed Identity or environment variables set),\n"
        " - Azure CLI is installed and 'az login' was run in the same environment, or\n"
        " - AZURE_STORAGE_KEY is set with an account key (for local testing).\n"
        "See https://aka.ms/azsdk/python/identity/troubleshoot for details."
    )
    LOG.error(hint)
    # raise the last low-level exception as context
    raise RuntimeError(hint) from last_exc

def _read_blob_with_retry(blob_client: Any, retries: int = 3, backoff: float = 0.5):
    for attempt in range(1, retries + 1):
        try:
            stream = blob_client.download_blob()
            return json.loads(stream.readall())
        except ResourceNotFoundError:
            # Blob doesn't exist yet -> return empty store
            LOG.info("Blob not found; returning empty store")
            return {}
        except HttpResponseError as e:
            LOG.warning("Blob read error (attempt %d/%d): %s", attempt, retries, e)
            if attempt == retries:
                raise
            time.sleep(backoff * attempt)

def _write_blob_with_retry(blob_client: Any, store: Dict[str, dict], retries: int = 3, backoff: float = 0.5):
    data = json.dumps(store, indent=2).encode("utf-8")
    for attempt in range(1, retries + 1):
        try:
            blob_client.upload_blob(data, overwrite=True)
            return
        except HttpResponseError as e:
            LOG.warning("Blob write error (attempt %d/%d): %s", attempt, retries, e)
            if attempt == retries:
                raise
            time.sleep(backoff * attempt)

def load() -> Dict[str, dict]:
    """Load the task store from Blob Storage. Raises if storage not available."""
    blob = _get_blob_client()
    return _read_blob_with_retry(blob)

def save(store: Dict[str, dict]) -> None:
    """Save the task store to Blob Storage. Raises on failure."""
    blob = _get_blob_client()
    _write_blob_with_retry(blob, store)

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
