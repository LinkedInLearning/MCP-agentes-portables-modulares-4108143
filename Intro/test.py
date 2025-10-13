from mcp.server.fastmcp import FastMCP
mcp = FastMCP("Primitives Demo")

@mcp.tool()
def add(a: int, b: int) -> int:
    """Suma dos números."""
    return a + b
