"""A tiny MCP server exposing 'support ticket' tools over stdio.

MCP (Model Context Protocol) is a standard way to expose tools/resources to any
MCP-aware client. Here we build one with FastMCP. The agents discover these
tools at runtime via langchain-mcp-adapters (see insightdesk/tools.py).

Run standalone for a sanity check:
    python mcp_server/server.py        # waits on stdio for an MCP client
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("support")

# Pretend datastore — in reality this would hit a ticketing system.
_TICKETS: dict[str, dict] = {
    "T-1001": {"status": "open", "subject": "Cannot export reports", "priority": "high"},
    "T-1002": {"status": "resolved", "subject": "Billing question", "priority": "low"},
}
_next_id = 1003


@mcp.tool()
def get_ticket(ticket_id: str) -> str:
    """Look up a support ticket by its ID (e.g. 'T-1001')."""
    ticket = _TICKETS.get(ticket_id.upper())
    if not ticket:
        return f"No ticket found with id {ticket_id}."
    return (
        f"{ticket_id.upper()} — {ticket['subject']} "
        f"(status: {ticket['status']}, priority: {ticket['priority']})"
    )


@mcp.tool()
def create_ticket(subject: str, priority: str = "medium") -> str:
    """Create a new support ticket and return its ID."""
    global _next_id
    ticket_id = f"T-{_next_id}"
    _next_id += 1
    _TICKETS[ticket_id] = {"status": "open", "subject": subject, "priority": priority}
    return f"Created {ticket_id} (subject: {subject!r}, priority: {priority})."


@mcp.tool()
def list_open_tickets() -> str:
    """List all currently open support tickets."""
    open_ones = [f"{tid}: {t['subject']}" for tid, t in _TICKETS.items() if t["status"] == "open"]
    return "\n".join(open_ones) if open_ones else "No open tickets."


if __name__ == "__main__":
    mcp.run(transport="stdio")
