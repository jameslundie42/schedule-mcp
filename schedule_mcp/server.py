"""
Schedule MCP Server
===================

A personal schedule management MCP server that bridges Google Calendar,
Notion Appointments, and Notion Tasks — letting Claude help you plan,
organize, and stay on top of your schedule.

Setup:
    1. Copy .env.example to .env and fill in your credentials
    2. Run: uv run schedule-mcp (first run opens Google OAuth browser flow)
    3. Add to your Claude MCP config (see README.md)

Usage with Claude:
    - "What does my week look like?"
    - "Schedule 2 hours for SeattleCouncilmatic work tomorrow"
    - "Do I have any conflicts this week?"
    - "Add my dentist appointment from Google Calendar to Notion"
"""

import os
import sys
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from .tools import (
    register_calendar_tools,
    register_appointment_tools,
    register_task_tools,
    register_schedule_tools,
)

# Load .env from the project root
load_dotenv()

# Initialize the MCP server
mcp = FastMCP(
    "schedule_mcp",
    instructions=(
        "This server manages schedule data across Google Calendar and Notion. "
        "Use gcal_* tools for Google Calendar events, notion_get_appointments / "
        "notion_create_appointment for Notion Appointments, notion_get_tasks / "
        "notion_create_task for Notion Tasks, and schedule_* tools for cross-source "
        "views like week overviews, conflict detection, and task scheduling. "
        "When creating a work block for a task, always include the Notion task URL "
        "in the Google Calendar event description."
    ),
)

# Register all tool groups
register_calendar_tools(mcp)
register_appointment_tools(mcp)
register_task_tools(mcp)
register_schedule_tools(mcp)


def main() -> None:
    """Entry point for the schedule-mcp command."""
    print("schedule-mcp: starting up...", file=sys.stderr)
    try:
        mcp.run()
    except KeyboardInterrupt:
        pass
    finally:
        print("schedule-mcp: shutting down.", file=sys.stderr)


if __name__ == "__main__":
    main()
