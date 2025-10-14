"""A demo client that talks to the Task Pilot server via stdio."""

import asyncio
from pprint import pprint

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

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
                arguments={"title": "Record Chapter 2", "tags": ["course"]}
            )
            pprint(created.content)

            # Extract id from structured result
            new_id = None
            for c in created.content:
                if c.type == "json":
                    new_id = c.json.get("id")

            print("\nListing tasks ...")
            listing = await session.call_tool("list_tasks", arguments={"include_done": True})
            pprint(listing.content)

            if new_id:
                print("\nCompleting the new task ...")
                done = await session.call_tool("complete_task", arguments={"task_id": new_id})
                pprint(done.content)

            # Read via resources
            print("\nReading tasks://all ...")
            all_tasks = await session.read_resource("tasks://all")
            print(all_tasks[0].text)

if __name__ == "__main__":
    asyncio.run(main())
