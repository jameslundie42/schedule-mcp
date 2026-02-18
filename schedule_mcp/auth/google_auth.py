"""Google OAuth2 authentication for Calendar API access."""

import os
import json
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Scopes required for Google Calendar read/write
SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _resolve_path(path_str: str) -> Path:
    """Expand ~ and resolve the path."""
    return Path(path_str).expanduser().resolve()


def get_google_credentials() -> Credentials:
    """
    Load or refresh Google OAuth2 credentials.

    On first run, opens a browser window for the OAuth consent flow and
    saves the resulting token to GOOGLE_TOKEN_FILE. Subsequent runs load
    and auto-refresh the saved token.

    Returns:
        Valid Google OAuth2 Credentials object.

    Raises:
        FileNotFoundError: If GOOGLE_CREDENTIALS_FILE does not exist.
        EnvironmentError: If required environment variables are missing.
    """
    token_path = _resolve_path(
        os.environ.get("GOOGLE_TOKEN_FILE", "~/.schedule_mcp/google_token.json")
    )
    credentials_path = _resolve_path(
        os.environ.get("GOOGLE_CREDENTIALS_FILE", "~/.schedule_mcp/google_credentials.json")
    )

    if not credentials_path.exists():
        raise FileNotFoundError(
            f"Google credentials file not found at {credentials_path}. "
            "Download it from Google Cloud Console → APIs & Services → Credentials."
        )

    creds: Optional[Credentials] = None

    # Load existing token if present
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    # Refresh or run the OAuth flow if needed
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save token for future runs
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())

    return creds


def get_calendar_service():
    """
    Build and return an authenticated Google Calendar API service object.

    Returns:
        Google Calendar API Resource object ready for API calls.
    """
    creds = get_google_credentials()
    return build("calendar", "v3", credentials=creds)
