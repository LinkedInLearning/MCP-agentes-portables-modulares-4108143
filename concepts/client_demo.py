"""A demo client that talks to the Task Pilot server via stdio."""

import asyncio
from pprint import pprint
import json

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters


def _get_contents(obj):
    """Return the list of content items from an RPC result or resource read.

    The protocol sometimes uses `.content` and sometimes `.contents` (or a
    plain dict). Normalize both to a Python list for easier processing.
    """
    if obj is None:
        return []
    # object with attribute
    if hasattr(obj, "content"):
        val = getattr(obj, "content")
        if val is None:
            return []
        return list(val)
    if hasattr(obj, "contents"):
        val = getattr(obj, "contents")
        if val is None:
            return []
        return list(val)
    # maybe a dict-like mapping
    if isinstance(obj, dict):
        for key in ("content", "contents"):
            if key in obj and obj[key] is not None:
                return list(obj[key])
    # fallback: single item
    return [obj]


def _extract_id_from_result(result):
    """Try several heuristics to extract an `id` from a tool result."""
    for item in _get_contents(result):
        # item may be an object with .type/.json/.text attributes
        t = getattr(item, "type", None)
        j = getattr(item, "json", None)
        txt = getattr(item, "text", None)

        # structured JSON payload already available
        if t == "json" and isinstance(j, dict) and "id" in j:
            return j.get("id")

        # sometimes item itself is a dict
        if isinstance(item, dict):
            if item.get("type") == "json" and isinstance(item.get("json"), dict):
                return item["json"].get("id")
            # direct id in json-like
            if "id" in item:
                return item.get("id")

        # other shapes: json property contains id
        if isinstance(j, dict) and "id" in j:
            return j.get("id")

        # sometimes the server returns JSON as text; try parsing it
        if isinstance(txt, str):
            try:
                parsed = json.loads(txt)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict) and "id" in parsed:
                return parsed.get("id")
            # parsed may be a list of items
            if isinstance(parsed, list):
                for p in parsed:
                    if isinstance(p, dict) and "id" in p:
                        return p.get("id")
    return None


def _pretty_print_result(result, prefix=None):
    """Print a tool result / listing in a readable way.

    Handles structured .json items and plain text items.
    """
    if prefix:
        print(prefix)
    items = _get_contents(result)
    if not items:
        print("(no content)")
        return
    for i, item in enumerate(items, start=1):
        # object with json
        j = getattr(item, "json", None)
        if isinstance(j, dict):
            print(f"[{i}] JSON:")
            pprint(j)
            continue
        # object with text
        txt = getattr(item, "text", None)
        if isinstance(txt, str):
            # try parsing JSON text to present structured output instead of raw string
            try:
                parsed = json.loads(txt)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                print(f"[{i}] JSON (from text):")
                pprint(parsed)
                continue
            if isinstance(parsed, list):
                print(f"[{i}] List (from text):")
                pprint(parsed)
                continue
            print(f"[{i}] Text:")
            print(txt)
            continue
        # dict-like
        if isinstance(item, dict):
            print(f"[{i}] Dict:")
            pprint(item)
            continue
        # fallback to repr
        print(f"[{i}] -> {repr(item)}")


async def main():
    """Start our server as a subprocess the client can talk to via stdio"""
    params = StdioServerParameters(
        command="python",
        args=["task_pilot_server.py"],
        env=None,
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            print("== Tools ==")
            tools = await session.list_tools()
            for t in tools.tools:
                print(f"- {t.name}: {t.description}")

            print("\n== Resources ==")
            resources = await session.list_resources()
            for r in resources.resources:
                print(f"- {r.uri}")

            # Create a task, list tasks, complete it, list again
            print("\nCalling add_task() ...")
            created = await session.call_tool(
                "add_task",
                arguments={"title": "Record Chapter 3", "tags": ["course"]}
            )
            # Print the created response and extract the new id robustly
            _pretty_print_result(created, prefix="Created result:")
            new_id = _extract_id_from_result(created)
            if new_id is None:
                print("Warning: couldn't find id in create result")

            print("\nListing tasks ...")
            listing = await session.call_tool("list_tasks", arguments={"include_done": True})
            _pretty_print_result(listing, prefix="List tasks result:")

            if new_id:
                print("\nCompleting the new task ...")
                done = await session.call_tool("complete_task", arguments={"task_id": new_id})
                _pretty_print_result(done, prefix="Complete task result:")

            # Read via resources
            print("\nReading tasks://all ...")
            result = await session.read_resource("tasks://all")
            # resources may return .contents or .content; print them all
            _pretty_print_result(result, prefix="tasks://all resource contents:")

if __name__ == "__main__":
    asyncio.run(main())
