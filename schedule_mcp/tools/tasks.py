"""MCP tools for Notion Tasks database."""

import json
from typing import Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, ConfigDict

from ..clients.notion import (
    get_tasks,
    create_task,
    update_task,
    get_overdue_tasks,
)


def register_task_tools(mcp: FastMCP) -> None:
    """Register all Notion Tasks tools with the MCP server."""

    # ------------------------------------------------------------------
    # Get tasks
    # ------------------------------------------------------------------

    class GetTasksInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

        status: Optional[str] = Field(
            default=None,
            description="Filter by status: Not started, In progress, Done, Archived, or Overdue.",
        )
        due_before: Optional[str] = Field(
            default=None,
            description="Only return tasks due on or before this ISO date.",
        )
        due_after: Optional[str] = Field(
            default=None,
            description="Only return tasks due on or after this ISO date.",
        )

    @mcp.tool(
        name="notion_get_tasks",
        annotations={"readOnlyHint": True, "destructiveHint": False},
    )
    async def notion_get_tasks(params: GetTasksInput) -> str:
        """
        Query the Notion Tasks database with optional filters.

        Returns tasks with their Notion IDs, names, statuses, due dates,
        and Notion URLs (for linking in calendar event descriptions).

        Args:
            params.status: Filter by Not started, In progress, Done, Archived, or Overdue.
            params.due_before: Only return tasks due on or before this date.
            params.due_after: Only return tasks due on or after this date.

        Returns:
            str: JSON array of task dicts.
        """
        try:
            tasks = get_tasks(
                status=params.status,
                due_before=params.due_before,
                due_after=params.due_after,
            )
            return json.dumps(tasks, indent=2)
        except Exception as e:
            return f"Error fetching tasks: {e}"

    # ------------------------------------------------------------------
    # Get overdue tasks
    # ------------------------------------------------------------------

    @mcp.tool(
        name="notion_get_overdue_tasks",
        annotations={"readOnlyHint": True, "destructiveHint": False},
    )
    async def notion_get_overdue_tasks() -> str:
        """
        Return all overdue tasks — either explicitly marked Overdue or
        with a due date in the past that isn't marked Done, Archived, or Overdue.

        Returns:
            str: JSON array of overdue task dicts.
        """
        try:
            tasks = get_overdue_tasks()
            if not tasks:
                return json.dumps({"message": "No overdue tasks found.", "tasks": []})
            return json.dumps({"count": len(tasks), "tasks": tasks}, indent=2)
        except Exception as e:
            return f"Error fetching overdue tasks: {e}"

    # ------------------------------------------------------------------
    # Create task
    # ------------------------------------------------------------------

    class CreateTaskInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

        name: str = Field(..., description="Task name.", min_length=1, max_length=500)
        due_date: Optional[str] = Field(
            default=None, description="Due date as ISO date string (e.g. '2026-02-24')."
        )
        status: str = Field(
            default="Not started",
            description="Initial status: Not started, In progress, Done, Archived, or Overdue.",
        )

    @mcp.tool(
        name="notion_create_task",
        annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False},
    )
    async def notion_create_task(params: CreateTaskInput) -> str:
        """
        Create a new task in the Notion Tasks database.

        Args:
            params.name: Task name.
            params.due_date: Optional due date (ISO date string).
            params.status: Initial status (default: Not started).

        Returns:
            str: JSON dict of the created task including its Notion ID and URL.
        """
        try:
            task = create_task(
                name=params.name,
                due_date=params.due_date,
                status=params.status,
            )
            return json.dumps(task, indent=2)
        except Exception as e:
            return f"Error creating task: {e}"

    # ------------------------------------------------------------------
    # Update task
    # ------------------------------------------------------------------

    class UpdateTaskInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

        notion_id: str = Field(..., description="Notion page ID of the task to update.")
        name: Optional[str] = Field(default=None, description="New task name.")
        status: Optional[str] = Field(
            default=None, description="New status: Not started, In progress, Done, Archived, or Overdue."
        )
        due_date: Optional[str] = Field(
            default=None, description="New due date (ISO date string)."
        )

    @mcp.tool(
        name="notion_update_task",
        annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
    )
    async def notion_update_task(params: UpdateTaskInput) -> str:
        """
        Update fields on an existing Notion task. Only provided fields change.

        Args:
            params.notion_id: Notion page ID (from notion_get_tasks).
            params.name/status/due_date: Fields to update.

        Returns:
            str: JSON dict of the updated task.
        """
        try:
            kwargs = {
                k: v for k, v in {
                    "name": params.name,
                    "status": params.status,
                    "due_date": params.due_date,
                }.items() if v is not None
            }
            task = update_task(params.notion_id, **kwargs)
            return json.dumps(task, indent=2)
        except Exception as e:
            return f"Error updating task: {e}"
