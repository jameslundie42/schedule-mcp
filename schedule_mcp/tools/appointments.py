"""MCP tools for Notion Appointments database."""

import json
from typing import Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, ConfigDict

from ..clients.notion import (
    get_appointments,
    create_appointment,
    update_appointment,
    get_appointment_by_gcal_id,
)


def register_appointment_tools(mcp: FastMCP) -> None:
    """Register all Notion Appointments tools with the MCP server."""

    # ------------------------------------------------------------------
    # Get appointments
    # ------------------------------------------------------------------

    class GetAppointmentsInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

        start_date: Optional[str] = Field(
            default=None, description="Filter to appointments on or after this ISO date."
        )
        end_date: Optional[str] = Field(
            default=None, description="Filter to appointments on or before this ISO date."
        )
        appointment_type: Optional[str] = Field(
            default=None,
            description="Filter by type: Medical, Personal, Work, or Other.",
        )
        status: Optional[str] = Field(
            default=None,
            description="Filter by status: Scheduled, In progress, or Completed.",
        )

    @mcp.tool(
        name="notion_get_appointments",
        annotations={"readOnlyHint": True, "destructiveHint": False},
    )
    async def notion_get_appointments(params: GetAppointmentsInput) -> str:
        """
        Query the Notion Appointments database with optional filters.

        Returns appointments with Notion ID, title, start/end times, type,
        status, notes, and linked Google Calendar event ID (if synced).

        Args:
            params.start_date: Only return appointments from this date onwards.
            params.end_date: Only return appointments up to this date.
            params.appointment_type: Filter by Medical, Personal, Work, or Other.
            params.status: Filter by Scheduled, In progress, or Completed.

        Returns:
            str: JSON array of appointment dicts.
        """
        try:
            appointments = get_appointments(
                start_date=params.start_date,
                end_date=params.end_date,
                appointment_type=params.appointment_type,
                status=params.status,
            )
            return json.dumps(appointments, indent=2)
        except Exception as e:
            return f"Error fetching appointments: {e}"

    # ------------------------------------------------------------------
    # Create appointment
    # ------------------------------------------------------------------

    class CreateAppointmentInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

        title: str = Field(..., description="Appointment title.", min_length=1, max_length=500)
        start: str = Field(..., description="Start datetime (ISO string, e.g. '2026-02-17T14:00:00').")
        end: str = Field(..., description="End datetime (ISO string).")
        appointment_type: str = Field(
            default="Personal",
            description="Appointment type: Medical, Personal, Work, or Other.",
        )
        notes: Optional[str] = Field(default=None, description="Additional notes.")
        gcal_event_id: Optional[str] = Field(
            default=None,
            description="Google Calendar event ID to link. Prevents duplicate sync in future.",
        )
        gcal_series_id: Optional[str] = Field(
            default=None,
            description="Google Calendar series ID for recurring appointments.",
        )
        recurring: Optional[str] = Field(
            default=None,
            description="Recurrence type: One-Time, Limited Recurring, or Recurring.",
        )

    @mcp.tool(
        name="notion_create_appointment",
        annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False},
    )
    async def notion_create_appointment(params: CreateAppointmentInput) -> str:
        """
        Create a new appointment in the Notion Appointments database.

        When syncing from Google Calendar, always pass the gcal_event_id to prevent
        duplicates. When creating a new appointment from scratch, omit gcal_event_id
        and use gcal_create_event separately to sync it to Google Calendar.

        Args:
            params.title: Appointment name.
            params.start/end: ISO datetime strings.
            params.appointment_type: Medical, Personal, Work, or Other.
            params.notes: Optional notes.
            params.gcal_event_id: Google Calendar event ID (if syncing from GCal).
            params.gcal_series_id: Google Calendar series ID (for recurring appointments).
            params.recurring: One-Time, Limited Recurring, or Recurring.

        Returns:
            str: JSON dict of the created appointment including Notion ID.
        """
        try:
            appointment = create_appointment(
                title=params.title,
                start=params.start,
                end=params.end,
                appointment_type=params.appointment_type,
                notes=params.notes,
                gcal_event_id=params.gcal_event_id,
                gcal_series_id=params.gcal_series_id,
                recurring=params.recurring,
            )
            return json.dumps(appointment, indent=2)
        except Exception as e:
            return f"Error creating appointment: {e}"

    # ------------------------------------------------------------------
    # Update appointment
    # ------------------------------------------------------------------

    class UpdateAppointmentInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

        notion_id: str = Field(..., description="Notion page ID of the appointment to update.")
        title: Optional[str] = Field(default=None, description="New title.")
        start: Optional[str] = Field(default=None, description="New start datetime (ISO string).")
        end: Optional[str] = Field(default=None, description="New end datetime (ISO string).")
        appointment_type: Optional[str] = Field(
            default=None, description="New type: Medical, Personal, Work, or Other."
        )
        status: Optional[str] = Field(
            default=None, description="New status: Scheduled, In progress, or Completed."
        )
        canceled: Optional[str] = Field(
            default=None, description="Cancellation state: 'Canceled' or 'Not canceled'."
        )
        notes: Optional[str] = Field(default=None, description="New notes.")
        gcal_event_id: Optional[str] = Field(
            default=None, description="Link or update the Google Calendar event ID."
        )
        gcal_series_id: Optional[str] = Field(
            default=None, description="Link or update the Google Calendar series ID."
        )
        recurring: Optional[str] = Field(
            default=None, description="New recurrence type: One-Time, Limited Recurring, or Recurring."
        )

    @mcp.tool(
        name="notion_update_appointment",
        annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
    )
    async def notion_update_appointment(params: UpdateAppointmentInput) -> str:
        """
        Update fields on an existing Notion appointment. Only provided fields change.

        Args:
            params.notion_id: The Notion page ID (from notion_get_appointments).
            params.*: Any fields to update.

        Returns:
            str: JSON dict of the updated appointment.
        """
        try:
            kwargs = {
                k: v for k, v in {
                    "title": params.title,
                    "start": params.start,
                    "end": params.end,
                    "appointment_type": params.appointment_type,
                    "status": params.status,
                    "canceled": params.canceled,
                    "notes": params.notes,
                    "gcal_event_id": params.gcal_event_id,
                    "gcal_series_id": params.gcal_series_id,
                    "recurring": params.recurring,
                }.items() if v is not None
            }
            appointment = update_appointment(params.notion_id, **kwargs)
            return json.dumps(appointment, indent=2)
        except Exception as e:
            return f"Error updating appointment: {e}"

    # ------------------------------------------------------------------
    # Look up appointment by Google Calendar event ID
    # ------------------------------------------------------------------

    class GetAppointmentByGCalIDInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        gcal_event_id: str = Field(
            ..., description="Google Calendar event ID to look up in Notion."
        )

    @mcp.tool(
        name="notion_get_appointment_by_gcal_id",
        annotations={"readOnlyHint": True, "destructiveHint": False},
    )
    async def notion_get_appointment_by_gcal_id(params: GetAppointmentByGCalIDInput) -> str:
        """
        Find a Notion appointment by its linked Google Calendar event ID.

        Use this before syncing to check whether a calendar event already has
        a corresponding Notion record, preventing duplicate entries.

        Args:
            params.gcal_event_id: Google Calendar event ID to search for.

        Returns:
            str: JSON dict of the appointment if found, or a not-found message.
        """
        try:
            appointment = get_appointment_by_gcal_id(params.gcal_event_id)
            if appointment:
                return json.dumps(appointment, indent=2)
            return json.dumps({"found": False, "gcal_event_id": params.gcal_event_id})
        except Exception as e:
            return f"Error looking up appointment: {e}"
