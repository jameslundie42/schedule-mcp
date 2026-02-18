# schedule-mcp

Personal schedule management MCP server. Connects Google Calendar, Notion Appointments, and Notion Tasks so Claude can help you plan your week, detect conflicts, schedule task work blocks, and keep your calendar and Notion in sync.

## Architecture

```
Google Calendar  ←→  Claude (sync layer)  ←→  Notion Appointments
                                ↓
                         Notion Tasks
                    (linked via GCal event description)
```

**Key design decisions:**
- Google Calendar is the source of truth for *time*
- Notion Appointments is the source of truth for *context* (type, notes, rich metadata)
- Notion Tasks are linked to calendar events via Notion URLs in the event description (no bidirectional sync needed)
- A `GCal Event ID` field on each Notion Appointment prevents duplicate sync
- A `GCal Series ID`  field for linking Notion Appointments with recurring GCal events

## Tools

| Tool | Source | What it does |
|------|--------|--------------|
| `gcal_list_calendars` | GCal | List all your calendars |
| `gcal_get_events` | GCal | Fetch events in a date range |
| `gcal_create_event` | GCal | Create a calendar event |
| `gcal_update_event` | GCal | Update an existing event |
| `gcal_delete_event` | GCal | Delete an event |
| `gcal_find_free_slots` | GCal | Find available time blocks |
| `notion_get_appointments` | Notion | Query appointments with filters |
| `notion_create_appointment` | Notion | Add an appointment to Notion |
| `notion_update_appointment` | Notion | Update an appointment |
| `notion_get_appointment_by_gcal_id` | Notion | Check if a GCal event is already in Notion |
| `notion_get_tasks` | Notion | Query tasks with filters |
| `notion_get_overdue_tasks` | Notion | Get all overdue tasks |
| `notion_create_task` | Notion | Add a new task |
| `notion_update_task` | Notion | Update a task |
| `schedule_week_overview` | All | Unified week view: events, appointments, tasks due, overdue tasks |
| `schedule_task_block` | GCal + Notion | Schedule a work block for a task |
| `schedule_find_conflicts` | GCal | Detect overlaps and tight transitions |

### Notion Database Schema

**Appointments database** — expected fields:

| Field | Type | Notes |
|-------|------|-------|
| Appointment | Title | Appointment name |
| Start | Date | Start datetime |
| End | Date | End datetime |
| Type | Select | Medical, Personal, Work, Other |
| Status | Status | Scheduled, In progress, Completed |
| Canceled | Select | Canceled, Not canceled |
| Recurring | Select | One-Time, Limited Recurring, Recurring |
| Notes | Rich text | Free-form notes |
| GCal Event ID | Rich text | Linked GCal event ID (prevents duplicate sync) |
| GCal Series ID | Rich text | Linked GCal series ID (for recurring events) |

**Tasks database** — expected fields:

| Field | Type | Notes |
|-------|------|-------|
| Task name | Title | Task name |
| Task Status | Select | Not started, In progress, Done, Archived, Overdue |
| Due | Date | Due date |

## Setup

### 1. Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- A Google Cloud project with the Calendar API enabled
- A Notion integration with access to your Appointments and Tasks databases

### 2. Google Calendar API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or use an existing one)
3. Enable the **Google Calendar API**
4. Go to **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**
5. Application type: **Desktop app**
6. Download the JSON file → save as `~/.schedule_mcp/google_credentials.json` (Windows: `%USERPROFILE%\.schedule_mcp\google_credentials.json`)

### 3. Notion Integration

1. Go to [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Create a new integration (Internal, Read + Write content)
3. Copy the **Internal Integration Token**
4. In Notion, open your **Appointments** database → `...` menu → **Connections** → add your integration
5. Do the same for your **Tasks** database

### 4. Configure Environment

```bash
# Linux/macOS
cp .env.example .env

# Windows (PowerShell)
Copy-Item .env.example .env
```
Then edit `.env` with your credentials.

### 5. Install and Run

```bash
# Using uv (recommended)
uv sync
uv run schedule-mcp

# Or with pip
pip install -e .
schedule-mcp
```

The first run will open a browser window for Google OAuth consent. After that, the token is saved and auto-refreshed.

### 6. Add to Claude MCP Config

Add this to `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS), merged into the top-level JSON object alongside any existing keys:

```json
{
  "mcpServers": {
    "schedule": {
      "command": "uv",
      "args": ["run", "--project", "C:/Users/YOU/source/repos/schedule_mcp", "schedule-mcp"],
      "env": {
        "GOOGLE_TOKEN_FILE": "C:/Users/YOU/.schedule_mcp/google_token.json",
        "GOOGLE_CREDENTIALS_FILE": "C:/Users/YOU/.schedule_mcp/google_credentials.json",
        "NOTION_TOKEN": "your_token_here",
        "NOTION_APPOINTMENTS_DB_ID": "your_notion_appointments_db_id_here",
        "NOTION_TASKS_DB_ID": "your_notion_tasks_db_id_here",
        "LOCAL_TIMEZONE": "America/Los_Angeles"
      }
    }
  }
}
```

Replace `YOU` with your Windows username. On macOS, use `~` paths instead.

## Example Claude Prompts

```
What does my week look like?

Do I have any conflicts or back-to-backs this week?

Find me 90 minutes of free time tomorrow morning for SeattleCouncilmatic work.

Schedule 2 hours for "Add transit data support to SeattleCouncilmatic" 
on Thursday afternoon.

I have a dentist appointment Tuesday at 2pm — add it to both my calendar and Notion.

Show me all my medical appointments this month.

What tasks do I have due this week?
```

## Development

```bash
# Verify syntax
python -m py_compile schedule_mcp/server.py

# Run with MCP Inspector for interactive testing
npx @modelcontextprotocol/inspector uv run schedule-mcp
```

## Project Structure

```
schedule_mcp/
├── pyproject.toml
├── uv.lock
├── .env.example
├── README.md
└── schedule_mcp/
    ├── __init__.py
    ├── server.py              # MCP server entry point
    ├── auth/
    │   ├── __init__.py
    │   └── google_auth.py     # Google OAuth2 flow
    ├── clients/
    │   ├── __init__.py
    │   ├── gcal.py            # Google Calendar API client
    │   └── notion.py          # Notion API client
    └── tools/
        ├── __init__.py        # Exports register_* functions
        ├── calendar.py        # gcal_* MCP tools
        ├── appointments.py    # notion_*appointment* MCP tools
        ├── tasks.py           # notion_*task* MCP tools
        └── schedule.py        # schedule_* cross-source tools
```
