"""MCP tools for Google Calendar."""

import json
from typing import Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, ConfigDict

from ..clients.gcal import (
    list_calendars,
    get_events,
    get_event,
    create_event,
    update_event,
    delete_event,
    find_free_slots,
)


def register_calendar_tools(mcp: FastMCP) -> None:
    """Register all Google Calendar tools with the MCP server."""

    # ------------------------------------------------------------------
    # List calendars
    # ------------------------------------------------------------------

    @mcp.tool(
        name="gcal_list_calendars",
        annotations={"readOnlyHint": True, "destructiveHint": False},
    )
    async def gcal_list_calendars() -> str:
        """
        List all Google Calendars the user has access to.

        Returns:
            str: JSON array of calendars with id, summary, and primary flag.
        """
        try:
            calendars = list_calendars()
            simplified = [
                {
                    "id": cal["id"],
                    "name": cal.get("summary", ""),
                    "primary": cal.get("primary", False),
                    "access_role": cal.get("accessRole", ""),
                }
                for cal in calendars
            ]
            return json.dumps(simplified, indent=2)
        except Exception as e:
            return f"Error listing calendars: {e}"

    # ------------------------------------------------------------------
    # Get events
    # ------------------------------------------------------------------

    class GetEventsInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

        start_date: str = Field(
            ..., description="Start date in ISO format (e.g. '2026-02-17')"
        )
        end_date: str = Field(
            ..., description="End date in ISO format (e.g. '2026-02-23')"
        )
        calendar_id: str = Field(
            default="primary",
            description="Google Calendar ID. Use 'primary' for the main calendar.",
        )
        max_results: int = Field(
            default=50, description="Maximum events to return", ge=1, le=200
        )

    @mcp.tool(
        name="gcal_get_events",
        annotations={"readOnlyHint": True, "destructiveHint": False},
    )
    async def gcal_get_events(params: GetEventsInput) -> str:
        """
        Fetch Google Calendar events within a date range.

        Returns a list of events with their IDs, titles, start/end times,
        descriptions, and locations. Use the event ID with other tools
        to update or delete specific events.

        Args:
            params.start_date: Start of the date range (ISO date string).
            params.end_date: End of the date range (ISO date string).
            params.calendar_id: Calendar to query (default: primary).
            params.max_results: Max events to return (default: 50).

        Returns:
            str: JSON array of event dicts.
        """
        try:
            events = get_events(
                params.start_date,
                params.end_date,
                params.calendar_id,
                params.max_results,
            )
            simplified = [_simplify_event(e) for e in events]
            return json.dumps(simplified, indent=2)
        except Exception as e:
            return f"Error fetching events: {e}"

    # ------------------------------------------------------------------
    # Create event
    # ------------------------------------------------------------------

    class CreateEventInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

        title: str = Field(..., description="Event title/summary", min_length=1, max_length=500)
        start: str = Field(
            ...,
            description="Start datetime as ISO string (e.g. '2026-02-17T14:00:00'). Include timezone offset if known.",
        )
        end: str = Field(
            ...,
            description="End datetime as ISO string (e.g. '2026-02-17T15:00:00').",
        )
        description: Optional[str] = Field(
            default=None,
            description="Event description. Use this to include a link to a Notion task when scheduling work time.",
        )
        location: Optional[str] = Field(
            default=None, description="Location string (address, place name, or 'Remote')."
        )
        calendar_id: str = Field(
            default="primary", description="Calendar to create the event in."
        )

    @mcp.tool(
        name="gcal_create_event",
        annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False},
    )
    async def gcal_create_event(params: CreateEventInput) -> str:
        """
        Create a new Google Calendar event.

        When creating work blocks for Notion tasks, include the task's Notion URL
        in the description so there's a direct link from the calendar event to the task.

        Args:
            params.title: Event title.
            params.start: ISO datetime string for start time.
            params.end: ISO datetime string for end time.
            params.description: Optional description (include Notion task URL here for task blocks).
            params.location: Optional location.
            params.calendar_id: Target calendar (default: primary).

        Returns:
            str: JSON dict of the created event including its 'id'.
        """
        try:
            event = create_event(
                title=params.title,
                start=params.start,
                end=params.end,
                description=params.description,
                location=params.location,
                calendar_id=params.calendar_id,
            )
            return json.dumps(_simplify_event(event), indent=2)
        except Exception as e:
            return f"Error creating event: {e}"

    # ------------------------------------------------------------------
    # Update event
    # ------------------------------------------------------------------

    class UpdateEventInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

        event_id: str = Field(..., description="Google Calendar event ID to update.")
        calendar_id: str = Field(default="primary", description="Calendar containing the event.")
        title: Optional[str] = Field(default=None, description="New title (leave blank to keep existing).")
        start: Optional[str] = Field(default=None, description="New start datetime (ISO string).")
        end: Optional[str] = Field(default=None, description="New end datetime (ISO string).")
        description: Optional[str] = Field(default=None, description="New description.")
        location: Optional[str] = Field(default=None, description="New location.")

    @mcp.tool(
        name="gcal_update_event",
        annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
    )
    async def gcal_update_event(params: UpdateEventInput) -> str:
        """
        Update one or more fields on an existing Google Calendar event.
        Only provided fields are changed; omitted fields remain as-is.

        Args:
            params.event_id: ID of the event to update.
            params.calendar_id: Calendar containing the event.
            params.title/start/end/description/location: Fields to update.

        Returns:
            str: JSON dict of the updated event.
        """
        try:
            kwargs = {
                k: v for k, v in {
                    "title": params.title,
                    "start": params.start,
                    "end": params.end,
                    "description": params.description,
                    "location": params.location,
                }.items() if v is not None
            }
            event = update_event(params.event_id, params.calendar_id, **kwargs)
            return json.dumps(_simplify_event(event), indent=2)
        except Exception as e:
            return f"Error updating event: {e}"

    # ------------------------------------------------------------------
    # Delete event
    # ------------------------------------------------------------------

    class DeleteEventInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        event_id: str = Field(..., description="Google Calendar event ID to delete.")
        calendar_id: str = Field(default="primary", description="Calendar containing the event.")

    @mcp.tool(
        name="gcal_delete_event",
        annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True},
    )
    async def gcal_delete_event(params: DeleteEventInput) -> str:
        """
        Permanently delete a Google Calendar event.

        This action cannot be undone. Confirm the event ID with gcal_get_events
        before deleting.

        Args:
            params.event_id: ID of the event to delete.
            params.calendar_id: Calendar containing the event.

        Returns:
            str: Confirmation message.
        """
        try:
            delete_event(params.event_id, params.calendar_id)
            return f"Event {params.event_id} deleted successfully."
        except Exception as e:
            return f"Error deleting event: {e}"

    # ------------------------------------------------------------------
    # Find free slots
    # ------------------------------------------------------------------

    class FindFreeSlotsInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        date: str = Field(..., description="Date to find free slots on (ISO date string, e.g. '2026-02-17').")
        duration_minutes: int = Field(
            ..., description="Desired slot duration in minutes.", ge=15, le=480
        )
        earliest_hour: int = Field(
            default=8, description="Earliest hour to suggest (24h format, default 8).", ge=0, le=23
        )
        latest_hour: int = Field(
            default=20, description="Latest end hour to suggest (24h format, default 20).", ge=1, le=24
        )
        calendar_id: str = Field(default="primary", description="Calendar to check for conflicts.")

    @mcp.tool(
        name="gcal_find_free_slots",
        annotations={"readOnlyHint": True, "destructiveHint": False},
    )
    async def gcal_find_free_slots(params: FindFreeSlotsInput) -> str:
        """
        Find available time slots of a given duration on a specific date.

        Useful for scheduling work blocks, appointments, or any time-bound task.
        Returns all slots with at least the requested duration available.

        Args:
            params.date: The date to check (ISO date string).
            params.duration_minutes: How long the slot needs to be (in minutes).
            params.earliest_hour: Don't suggest slots starting before this hour.
            params.latest_hour: Don't suggest slots ending after this hour.
            params.calendar_id: Calendar to check for conflicts.

        Returns:
            str: JSON array of available slots with 'start' and 'end' ISO datetimes.
        """
        try:
            slots = find_free_slots(
                date=params.date,
                duration_minutes=params.duration_minutes,
                earliest_hour=params.earliest_hour,
                latest_hour=params.latest_hour,
                calendar_id=params.calendar_id,
            )
            if not slots:
                return json.dumps({"message": "No free slots found on this date.", "slots": []})
            return json.dumps({"slots": slots, "count": len(slots)}, indent=2)
        except Exception as e:
            return f"Error finding free slots: {e}"


def _simplify_event(event: dict) -> dict:
    """Extract the most useful fields from a raw Google Calendar event dict."""
    start = event.get("start", {})
    end = event.get("end", {})
    return {
        "id": event.get("id"),
        "title": event.get("summary", "(no title)"),
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "description": event.get("description"),
        "location": event.get("location"),
        "html_link": event.get("htmlLink"),
        "status": event.get("status"),
        "calendar_id": event.get("organizer", {}).get("email"),
        "recurring_event_id": event.get("recurringEventId"),
    }
