"""Notion API client for Appointments and Tasks databases."""

import os
from typing import Optional, Any
from datetime import datetime

from notion_client import Client
from notion_client.errors import APIResponseError

# Database IDs from environment
APPOINTMENTS_DB_ID = os.environ.get(
    "NOTION_APPOINTMENTS_DB_ID", "9e949811-1b91-4f02-932b-72569bd97c97"
)
TASKS_DB_ID = os.environ.get(
    "NOTION_TASKS_DB_ID", "2331dfd4-8083-810f-8d28-000b9a413f64"
)


def _client() -> Client:
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        raise EnvironmentError(
            "NOTION_TOKEN environment variable is not set. "
            "Create an integration at https://www.notion.so/my-integrations"
        )
    return Client(auth=token)


def _handle_notion_error(e: APIResponseError) -> str:
    """Convert Notion API errors to actionable messages."""
    code = e.code
    if code == "object_not_found":
        return "Error: Notion page or database not found. Check that the integration has access."
    if code == "unauthorized":
        return "Error: Notion token is invalid or expired."
    if code == "validation_error":
        return f"Error: Invalid data sent to Notion — {e.message}"
    if code == "rate_limited":
        return "Error: Notion rate limit hit. Wait a moment and retry."
    return f"Error: Notion API error ({code}): {e.message}"


def _date_prop(iso_str: str, is_datetime: bool = True) -> dict:
    """Build a Notion date property value."""
    return {"date": {"start": iso_str, "time_zone": None}}


def _rich_text_prop(value: str) -> dict:
    """Build a Notion rich_text property value."""
    return {"rich_text": [{"text": {"content": value}}]}


def _title_prop(value: str) -> dict:
    """Build a Notion title property value."""
    return {"title": [{"text": {"content": value}}]}


def _select_prop(value: str) -> dict:
    """Build a Notion select property value."""
    return {"select": {"name": value}}


def _status_prop(value: str) -> dict:
    """Build a Notion status property value."""
    return {"status": {"name": value}}


def _extract_text(prop: Optional[dict]) -> str:
    """Extract plain text from a Notion rich_text or title property."""
    if not prop:
        return ""
    items = prop.get("rich_text") or prop.get("title") or []
    return "".join(item.get("plain_text", "") for item in items)


def _extract_date(prop: Optional[dict]) -> Optional[str]:
    """Extract the start date string from a Notion date property."""
    if not prop or not prop.get("date"):
        return None
    return prop["date"].get("start")


def _extract_select(prop: Optional[dict]) -> Optional[str]:
    """Extract the name from a Notion select property."""
    if not prop or not prop.get("select"):
        return None
    return prop["select"].get("name")


def _extract_status(prop: Optional[dict]) -> Optional[str]:
    """Extract the name from a Notion status property."""
    if not prop or not prop.get("status"):
        return None
    return prop["status"].get("name")


# ---------------------------------------------------------------------------
# Appointments
# ---------------------------------------------------------------------------

def get_appointments(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    appointment_type: Optional[str] = None,
    status: Optional[str] = None,
) -> list[dict]:
    """
    Query the Appointments database with optional filters.

    Args:
        start_date: ISO date string — only return appointments on or after this date.
        end_date: ISO date string — only return appointments on or before this date.
        appointment_type: One of Medical, Personal, Work, Other.
        status: One of Scheduled, In progress, Completed.

    Returns:
        List of simplified appointment dicts.
    """
    notion = _client()
    filters: list[dict] = []

    if start_date:
        filters.append(
            {"property": "Start", "date": {"on_or_after": start_date}}
        )
    if end_date:
        filters.append(
            {"property": "Start", "date": {"on_or_before": end_date}}
        )
    if appointment_type:
        filters.append(
            {"property": "Type", "select": {"equals": appointment_type}}
        )
    if status:
        filters.append(
            {"property": "Status", "status": {"equals": status}}
        )

    query_args: dict[str, Any] = {
        "sorts": [{"property": "Start", "direction": "ascending"}],
    }
    if len(filters) == 1:
        query_args["filter"] = filters[0]
    elif len(filters) > 1:
        query_args["filter"] = {"and": filters}

    response = notion.data_sources.query(APPOINTMENTS_DB_ID, **query_args)
    return [_simplify_appointment(page) for page in response["results"]]


def _simplify_appointment(page: dict) -> dict:
    """Convert a raw Notion appointment page to a clean dict."""
    props = page["properties"]
    return {
        "notion_id": page["id"],
        "url": page["url"],
        "title": _extract_text(props.get("Appointment")),
        "start": _extract_date(props.get("Start")),
        "end": _extract_date(props.get("End")),
        "type": _extract_select(props.get("Type")),
        "status": _extract_status(props.get("Status")),
        "canceled": _extract_select(props.get("Canceled")),
        "recurring": _extract_select(props.get("Recurring")),
        "notes": _extract_text(props.get("Notes")),
        "gcal_event_id": _extract_text(props.get("GCal Event ID")),
        "gcal_series_id": _extract_text(props.get("GCal Series ID")),
    }


def create_appointment(
    title: str,
    start: str,
    end: str,
    appointment_type: str = "Personal",
    notes: Optional[str] = None,
    gcal_event_id: Optional[str] = None,
    gcal_series_id: Optional[str] = None,
    recurring: Optional[str] = None,
) -> dict:
    """
    Create a new appointment in Notion.

    Args:
        title: Appointment name.
        start: ISO datetime string.
        end: ISO datetime string.
        appointment_type: One of Medical, Personal, Work, Other.
        notes: Optional notes.
        gcal_event_id: Google Calendar event ID to link this appointment.
        gcal_series_id: Google Calendar series ID for recurring appointments.
        recurring: One of One-Time, Limited Recurring, Recurring.

    Returns:
        Simplified appointment dict for the created page.
    """
    notion = _client()
    properties: dict[str, Any] = {
        "Appointment": _title_prop(title),
        "Start": _date_prop(start),
        "End": _date_prop(end),
        "Type": _select_prop(appointment_type),
        "Status": _status_prop("Scheduled"),
        "Canceled": _select_prop("Not canceled"),
    }
    if notes:
        properties["Notes"] = _rich_text_prop(notes)
    if gcal_event_id:
        properties["GCal Event ID"] = _rich_text_prop(gcal_event_id)
    if gcal_series_id:
        properties["GCal Series ID"] = _rich_text_prop(gcal_series_id)
    if recurring:
        properties["Recurring"] = _select_prop(recurring)

    page = notion.pages.create(
        parent={"database_id": APPOINTMENTS_DB_ID},
        properties=properties,
    )
    return _simplify_appointment(page)


def update_appointment(notion_id: str, **kwargs) -> dict:
    """
    Update fields on an existing Notion appointment.

    Supported kwargs: title, start, end, appointment_type, notes,
                      status, canceled, gcal_event_id, gcal_series_id, recurring.

    Returns:
        Updated simplified appointment dict.
    """
    notion = _client()
    properties: dict[str, Any] = {}

    if "title" in kwargs:
        properties["Appointment"] = _title_prop(kwargs["title"])
    if "start" in kwargs:
        properties["Start"] = _date_prop(kwargs["start"])
    if "end" in kwargs:
        properties["End"] = _date_prop(kwargs["end"])
    if "appointment_type" in kwargs:
        properties["Type"] = _select_prop(kwargs["appointment_type"])
    if "status" in kwargs:
        properties["Status"] = _status_prop(kwargs["status"])
    if "canceled" in kwargs:
        properties["Canceled"] = _select_prop(kwargs["canceled"])
    if "notes" in kwargs:
        properties["Notes"] = _rich_text_prop(kwargs["notes"])
    if "gcal_event_id" in kwargs:
        properties["GCal Event ID"] = _rich_text_prop(kwargs["gcal_event_id"])
    if "gcal_series_id" in kwargs:
        properties["GCal Series ID"] = _rich_text_prop(kwargs["gcal_series_id"])
    if "recurring" in kwargs:
        properties["Recurring"] = _select_prop(kwargs["recurring"])

    page = notion.pages.update(page_id=notion_id, properties=properties)
    return _simplify_appointment(page)


def get_appointment_by_gcal_id(gcal_event_id: str) -> Optional[dict]:
    """
    Find a Notion appointment by its linked Google Calendar event ID.

    Returns the simplified appointment dict if found, None otherwise.
    """
    notion = _client()
    response = notion.data_sources.query(
        APPOINTMENTS_DB_ID,
        filter={
            "property": "GCal Event ID",
            "rich_text": {"equals": gcal_event_id},
        },
    )
    if response["results"]:
        return _simplify_appointment(response["results"][0])
    return None


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

def get_tasks(
    status: Optional[str] = None,
    due_before: Optional[str] = None,
    due_after: Optional[str] = None,
) -> list[dict]:
    """
    Query the Tasks database with optional filters.

    Args:
        status: One of Not started, In progress, Done, Archived, Overdue.
        due_before: ISO date string — only tasks due on or before this date.
        due_after: ISO date string — only tasks due on or after this date.

    Returns:
        List of simplified task dicts.
    """
    notion = _client()
    filters: list[dict] = []

    if status:
        filters.append({"property": "Task Status", "select": {"equals": status}})
    if due_before:
        filters.append(
            {"property": "Due Date", "date": {"on_or_before": due_before}}
        )
    if due_after:
        filters.append(
            {"property": "Due Date", "date": {"on_or_after": due_after}}
        )

    query_args: dict[str, Any] = {
        "sorts": [{"property": "Due Date", "direction": "ascending"}],
    }
    if len(filters) == 1:
        query_args["filter"] = filters[0]
    elif len(filters) > 1:
        query_args["filter"] = {"and": filters}

    response = notion.data_sources.query(TASKS_DB_ID, **query_args)
    return [_simplify_task(page) for page in response["results"]]


def _simplify_task(page: dict) -> dict:
    """Convert a raw Notion task page to a clean dict."""
    props = page["properties"]
    return {
        "notion_id": page["id"],
        "url": page["url"],
        "name": _extract_text(props.get("Task name")),
        "status": _extract_select(props.get("Task Status")),
        "due_date": _extract_date(props.get("Due Date")),
    }


def create_task(
    name: str,
    due_date: Optional[str] = None,
    status: str = "Not started",
) -> dict:
    """
    Create a new task in Notion.

    Args:
        name: Task name.
        due_date: Optional ISO date string.
        status: One of Not started, In progress, Done, Archived, Overdue (default: Not started).

    Returns:
        Simplified task dict.
    """
    notion = _client()
    properties: dict[str, Any] = {
        "Task name": _title_prop(name),
        "Task Status": _select_prop(status),
    }
    if due_date:
        properties["Due Date"] = _date_prop(due_date, is_datetime=False)

    page = notion.pages.create(
        parent={"database_id": TASKS_DB_ID},
        properties=properties,
    )
    return _simplify_task(page)


def update_task(notion_id: str, **kwargs) -> dict:
    """
    Update fields on an existing Notion task.

    Supported kwargs: name, due_date, status.

    Returns:
        Updated simplified task dict.
    """
    notion = _client()
    properties: dict[str, Any] = {}

    if "name" in kwargs:
        properties["Task name"] = _title_prop(kwargs["name"])
    if "status" in kwargs:
        properties["Task Status"] = _select_prop(kwargs["status"])
    if "due_date" in kwargs:
        properties["Due Date"] = _date_prop(kwargs["due_date"], is_datetime=False)

    page = notion.pages.update(page_id=notion_id, properties=properties)
    return _simplify_task(page)


def get_overdue_tasks() -> list[dict]:
    """Return all tasks with status 'Overdue' or a due date in the past."""
    today = datetime.now().date().isoformat()

    # Get explicitly-marked overdue tasks
    overdue_by_status = get_tasks(status="Overdue")

    # Get tasks with a past due date that aren't marked Done, Archived, or Overdue
    overdue_by_date = get_tasks(due_before=today)
    overdue_by_date = [
        t for t in overdue_by_date
        if t["status"] not in ("Done", "Archived", "Overdue") and t["due_date"] and t["due_date"] < today
    ]

    # Deduplicate by notion_id
    seen: set[str] = set()
    combined = []
    for task in overdue_by_status + overdue_by_date:
        if task["notion_id"] not in seen:
            seen.add(task["notion_id"])
            combined.append(task)

    return combined
