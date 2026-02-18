"""Cross-source synthesis tools that combine Google Calendar, Appointments, and Tasks."""

import json
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo
import os

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, ConfigDict

from ..clients.gcal import get_events, find_free_slots
from ..clients.notion import get_appointments, get_tasks, get_overdue_tasks

def _local_tz() -> str:
    return os.environ.get("LOCAL_TIMEZONE", "America/Los_Angeles")


def register_schedule_tools(mcp: FastMCP) -> None:
    """Register cross-source schedule synthesis tools."""

    # ------------------------------------------------------------------
    # Week overview
    # ------------------------------------------------------------------

    class WeekOverviewInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        date: Optional[str] = Field(
            default=None,
            description=(
                "Any date within the desired week (ISO date string). "
                "Defaults to the current week if not provided."
            ),
        )

    @mcp.tool(
        name="schedule_week_overview",
        annotations={"readOnlyHint": True, "destructiveHint": False},
    )
    async def schedule_week_overview(params: WeekOverviewInput) -> str:
        """
        Get a unified overview of a week: calendar events, Notion appointments,
        and tasks due that week.

        This is the primary 'how does my week look?' tool. It pulls from all
        three sources and returns a combined view so you can see everything
        in context — scheduled appointments, work blocks, and upcoming deadlines.

        Args:
            params.date: Any date in the target week (defaults to current week).

        Returns:
            str: JSON with 'week_range', 'calendar_events', 'appointments',
                 'tasks_due', and 'overdue_tasks' keys.
        """
        try:
            tz = ZoneInfo(_local_tz())

            # Calculate week boundaries (Monday–Sunday)
            if params.date:
                anchor = datetime.fromisoformat(params.date).replace(tzinfo=tz)
            else:
                anchor = datetime.now(tz)

            monday = anchor - timedelta(days=anchor.weekday())
            sunday = monday + timedelta(days=6)
            start_str = monday.date().isoformat()
            end_str = sunday.date().isoformat()

            # Fetch from all three sources in parallel would be ideal in a
            # production server, but sequential is fine for a personal tool
            calendar_events = get_events(start_str, end_str)
            appointments = get_appointments(start_date=start_str, end_date=end_str)
            tasks_due = get_tasks(due_before=end_str, due_after=start_str)
            overdue = get_overdue_tasks()

            return json.dumps(
                {
                    "week_range": {"start": start_str, "end": end_str},
                    "calendar_events": [_slim_event(e) for e in calendar_events],
                    "appointments": appointments,
                    "tasks_due_this_week": tasks_due,
                    "overdue_tasks": overdue,
                    "summary": {
                        "event_count": len(calendar_events),
                        "appointment_count": len(appointments),
                        "tasks_due_count": len(tasks_due),
                        "overdue_count": len(overdue),
                    },
                },
                indent=2,
            )
        except Exception as e:
            return f"Error building week overview: {e}"

    # ------------------------------------------------------------------
    # Sync Google Calendar event to Notion
    # ------------------------------------------------------------------

    class SyncGCalToNotionInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

        event_id: str = Field(
            ..., description="Google Calendar event ID to sync to Notion Appointments."
        )
        calendar_id: str = Field(
            default="primary", description="Calendar containing the event."
        )
        appointment_type: str = Field(
            default="Personal",
            description="Appointment type to assign in Notion: Medical, Personal, Work, or Other.",
        )
        notes: Optional[str] = Field(
            default=None,
            description="Additional notes to add to the Notion appointment.",
        )

    # NOTE: This tool is intentionally not registered here — it requires
    # both gcal and notion clients to create/update records, which means
    # the implementation lives in the server.py where both clients are
    # available. The tool stub is kept here as documentation.
    #
    # The sync workflow is:
    #   1. gcal_get_events → find the event
    #   2. notion_get_appointment_by_gcal_id → check if already synced
    #   3. If not found: notion_create_appointment with gcal_event_id
    #   4. Confirm back to user
    #
    # Claude can execute this workflow with the existing primitive tools.
    # A dedicated tool can be added here once the pattern is validated.

    # ------------------------------------------------------------------
    # Schedule task time block
    # ------------------------------------------------------------------

    class ScheduleTaskBlockInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

        task_notion_id: str = Field(
            ..., description="Notion ID of the task to schedule time for."
        )
        task_name: str = Field(
            ..., description="Task name (for the calendar event title)."
        )
        task_url: str = Field(
            ..., description="Notion URL of the task (to embed in calendar event description)."
        )
        start: str = Field(
            ..., description="Start datetime for the work block (ISO string)."
        )
        end: str = Field(
            ..., description="End datetime for the work block (ISO string)."
        )
        calendar_id: str = Field(
            default="primary", description="Calendar to create the work block in."
        )

    @mcp.tool(
        name="schedule_task_block",
        annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False},
    )
    async def schedule_task_block(params: ScheduleTaskBlockInput) -> str:
        """
        Schedule a focused work block for a Notion task on Google Calendar.

        Creates a Google Calendar event with the task name as the title and
        a link to the Notion task in the description. The task itself is NOT
        modified — this just blocks time and creates a visible pointer.

        Typical workflow:
            1. notion_get_tasks → find the task and get its ID and URL
            2. gcal_find_free_slots → find available time
            3. schedule_task_block → create the calendar event with Notion link

        Args:
            params.task_notion_id: Notion page ID of the task.
            params.task_name: Task name (used as event title).
            params.task_url: Notion URL (embedded in event description).
            params.start/end: ISO datetime strings for the work block.
            params.calendar_id: Target calendar.

        Returns:
            str: JSON with the created calendar event and a confirmation.
        """
        from ..clients.gcal import create_event

        try:
            description = f"Work block for Notion task:\n{params.task_url}"
            event = create_event(
                title=f"🔨 {params.task_name}",
                start=params.start,
                end=params.end,
                description=description,
                calendar_id=params.calendar_id,
            )
            return json.dumps(
                {
                    "message": "Work block created on Google Calendar.",
                    "event": _slim_event(event),
                    "notion_task_url": params.task_url,
                },
                indent=2,
            )
        except Exception as e:
            return f"Error scheduling task block: {e}"

    # ------------------------------------------------------------------
    # Find scheduling conflicts
    # ------------------------------------------------------------------

    class FindConflictsInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        start_date: str = Field(..., description="Start of date range to check (ISO date string).")
        end_date: str = Field(..., description="End of date range to check (ISO date string).")
        calendar_id: str = Field(default="primary", description="Calendar to check.")

    @mcp.tool(
        name="schedule_find_conflicts",
        annotations={"readOnlyHint": True, "destructiveHint": False},
    )
    async def schedule_find_conflicts(params: FindConflictsInput) -> str:
        """
        Detect overlapping events or tight transitions in a date range.

        Checks Google Calendar events for: exact overlaps, events with fewer than
        10 minutes between them (tight transitions), and events longer than 4 hours
        (marathon sessions worth flagging).

        Args:
            params.start_date: Start of the range to scan.
            params.end_date: End of the range to scan.
            params.calendar_id: Calendar to check.

        Returns:
            str: JSON with lists of overlaps, tight transitions, and long events.
        """
        try:
            tz = ZoneInfo(_local_tz())
            events = get_events(params.start_date, params.end_date, params.calendar_id)

            # Parse events into (start_dt, end_dt, summary) tuples
            parsed = []
            for ev in events:
                start_str = ev["start"].get("dateTime") or ev["start"].get("date")
                end_str = ev["end"].get("dateTime") or ev["end"].get("date")
                try:
                    s = datetime.fromisoformat(start_str).astimezone(tz)
                    e = datetime.fromisoformat(end_str).astimezone(tz)
                    parsed.append((s, e, ev.get("summary", "(no title)"), ev.get("id")))
                except ValueError:
                    continue

            parsed.sort()

            overlaps = []
            tight_transitions = []
            long_events = []

            for i, (s1, e1, title1, id1) in enumerate(parsed):
                # Check for long events (> 4 hours)
                if (e1 - s1).total_seconds() > 4 * 3600:
                    long_events.append({
                        "event": title1,
                        "start": s1.isoformat(),
                        "end": e1.isoformat(),
                        "duration_hours": round((e1 - s1).total_seconds() / 3600, 1),
                    })

                if i + 1 >= len(parsed):
                    continue

                s2, e2, title2, id2 = parsed[i + 1]

                # Check for overlap
                if s2 < e1:
                    overlaps.append({
                        "event_1": title1,
                        "event_2": title2,
                        "overlap_start": s2.isoformat(),
                        "overlap_end": min(e1, e2).isoformat(),
                    })
                # Check for tight transition (< 10 min gap)
                elif (s2 - e1).total_seconds() < 600:
                    tight_transitions.append({
                        "event_1": title1,
                        "event_1_end": e1.isoformat(),
                        "event_2": title2,
                        "event_2_start": s2.isoformat(),
                        "gap_minutes": round((s2 - e1).total_seconds() / 60, 1),
                    })

            return json.dumps(
                {
                    "date_range": {"start": params.start_date, "end": params.end_date},
                    "overlaps": overlaps,
                    "tight_transitions": tight_transitions,
                    "long_events": long_events,
                    "all_clear": not overlaps and not tight_transitions,
                },
                indent=2,
            )
        except Exception as e:
            return f"Error checking for conflicts: {e}"


def _slim_event(event: dict) -> dict:
    """Minimal event representation for overview responses."""
    start = event.get("start", {})
    end = event.get("end", {})
    return {
        "id": event.get("id"),
        "title": event.get("summary", "(no title)"),
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "location": event.get("location"),
    }
