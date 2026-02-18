"""Google Calendar API client."""

import os
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from googleapiclient.errors import HttpError

from ..auth import get_calendar_service

DEFAULT_CALENDAR_ID = os.environ.get("GOOGLE_DEFAULT_CALENDAR_ID", "primary")


def _tz() -> ZoneInfo:
    return ZoneInfo(os.environ.get("LOCAL_TIMEZONE", "America/Los_Angeles"))


def _now_iso() -> str:
    return datetime.now(_tz()).isoformat()


def _handle_http_error(e: HttpError) -> str:
    """Convert Google API HttpError to a human-readable message."""
    code = e.resp.status
    if code == 404:
        return "Error: Calendar event not found. Check the event ID."
    if code == 403:
        return "Error: Permission denied. Ensure the Calendar API is enabled and OAuth scopes include calendar write."
    if code == 409:
        return "Error: Conflict — this event may already exist."
    if code == 429:
        return "Error: Google Calendar API rate limit hit. Wait a moment and retry."
    return f"Error: Google Calendar API error {code}: {e}"


# ---------------------------------------------------------------------------
# Calendar listing
# ---------------------------------------------------------------------------

def list_calendars() -> list[dict]:
    """Return all calendars the authenticated user has access to."""
    service = get_calendar_service()
    result = service.calendarList().list().execute()
    return result.get("items", [])


# ---------------------------------------------------------------------------
# Event CRUD
# ---------------------------------------------------------------------------

def get_events(
    start_date: str,
    end_date: str,
    calendar_id: str = DEFAULT_CALENDAR_ID,
    max_results: int = 50,
) -> list[dict]:
    """
    Fetch events between start_date and end_date (ISO date strings, e.g. '2026-02-17').

    Returns a list of Google Calendar event dicts.
    """
    service = get_calendar_service()

    # Parse as dates and convert to RFC3339 datetimes
    tz = _tz()
    time_min = datetime.fromisoformat(start_date).replace(tzinfo=tz).isoformat()
    time_max = (
        datetime.fromisoformat(end_date).replace(tzinfo=tz) + timedelta(days=1)
    ).isoformat()

    result = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    return result.get("items", [])


def get_event(event_id: str, calendar_id: str = DEFAULT_CALENDAR_ID) -> dict:
    """Fetch a single event by ID."""
    service = get_calendar_service()
    return service.events().get(calendarId=calendar_id, eventId=event_id).execute()


def create_event(
    title: str,
    start: str,
    end: str,
    description: Optional[str] = None,
    location: Optional[str] = None,
    calendar_id: str = DEFAULT_CALENDAR_ID,
) -> dict:
    """
    Create a Google Calendar event.

    Args:
        title: Event summary/title.
        start: ISO datetime string (e.g. '2026-02-17T14:00:00').
        end: ISO datetime string.
        description: Optional event description (supports plain text or HTML).
        location: Optional location string.
        calendar_id: Calendar to create the event in.

    Returns:
        Created event dict including 'id' for future reference.
    """
    service = get_calendar_service()
    tz = os.environ.get("LOCAL_TIMEZONE", "America/Los_Angeles")

    event_body: dict = {
        "summary": title,
        "start": {"dateTime": start, "timeZone": tz},
        "end": {"dateTime": end, "timeZone": tz},
    }
    if description:
        event_body["description"] = description
    if location:
        event_body["location"] = location

    return service.events().insert(calendarId=calendar_id, body=event_body).execute()


def update_event(
    event_id: str,
    calendar_id: str = DEFAULT_CALENDAR_ID,
    **kwargs,
) -> dict:
    """
    Update fields on an existing event. Only provided kwargs are changed.

    Supported kwargs: title, start, end, description, location.
    """
    service = get_calendar_service()
    tz = os.environ.get("LOCAL_TIMEZONE", "America/Los_Angeles")

    # Fetch existing event first (patch requires the full object for some fields)
    existing = service.events().get(calendarId=calendar_id, eventId=event_id).execute()

    if "title" in kwargs:
        existing["summary"] = kwargs["title"]
    if "start" in kwargs:
        existing["start"] = {"dateTime": kwargs["start"], "timeZone": tz}
    if "end" in kwargs:
        existing["end"] = {"dateTime": kwargs["end"], "timeZone": tz}
    if "description" in kwargs:
        existing["description"] = kwargs["description"]
    if "location" in kwargs:
        existing["location"] = kwargs["location"]

    return (
        service.events()
        .update(calendarId=calendar_id, eventId=event_id, body=existing)
        .execute()
    )


def delete_event(event_id: str, calendar_id: str = DEFAULT_CALENDAR_ID) -> None:
    """Delete a Google Calendar event by ID."""
    service = get_calendar_service()
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()


# ---------------------------------------------------------------------------
# Free slot finder
# ---------------------------------------------------------------------------

def find_free_slots(
    date: str,
    duration_minutes: int,
    earliest_hour: int = 8,
    latest_hour: int = 20,
    calendar_id: str = DEFAULT_CALENDAR_ID,
) -> list[dict]:
    """
    Find free time slots of at least `duration_minutes` on the given date.

    Args:
        date: ISO date string (e.g. '2026-02-17').
        duration_minutes: Desired slot length in minutes.
        earliest_hour: Don't suggest slots before this hour (24h, default 8).
        latest_hour: Don't suggest slots after this hour (24h, default 20).
        calendar_id: Calendar to check for conflicts.

    Returns:
        List of dicts with 'start' and 'end' ISO datetime strings.
    """
    tz = _tz()
    day_start = datetime.fromisoformat(date).replace(
        hour=earliest_hour, minute=0, second=0, tzinfo=tz
    )
    day_end = datetime.fromisoformat(date).replace(
        hour=latest_hour, minute=0, second=0, tzinfo=tz
    )

    events = get_events(date, date, calendar_id)

    # Build list of busy windows
    busy: list[tuple[datetime, datetime]] = []
    for ev in events:
        start_str = ev["start"].get("dateTime") or ev["start"].get("date")
        end_str = ev["end"].get("dateTime") or ev["end"].get("date")
        try:
            s = datetime.fromisoformat(start_str).astimezone(tz)
            e = datetime.fromisoformat(end_str).astimezone(tz)
            busy.append((s, e))
        except ValueError:
            continue

    busy.sort()

    # Walk the day and find gaps
    free_slots = []
    cursor = day_start
    slot_delta = timedelta(minutes=duration_minutes)

    for (busy_start, busy_end) in busy:
        if cursor + slot_delta <= busy_start:
            free_slots.append(
                {"start": cursor.isoformat(), "end": (cursor + slot_delta).isoformat()}
            )
        if busy_end > cursor:
            cursor = busy_end

    # Check remaining time after last event
    if cursor + slot_delta <= day_end:
        free_slots.append(
            {"start": cursor.isoformat(), "end": (cursor + slot_delta).isoformat()}
        )

    return free_slots
