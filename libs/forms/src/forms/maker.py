"""
Google Workspace Factory — programmatically create Sheets (and optionally
Forms) when a new project or opportunity is opened.

Usage::

    maker = WorkspaceMaker(credentials_file="/path/to/service-account.json")
    result = maker.create_spreadsheet("Fall 2026 Applicants")
    # result == {"spreadsheet_id": "...", "url": "https://docs.google.com/..."}
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional


class WorkspaceMaker:
    """Create Google Workspace artefacts for UROG opportunities."""

    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    def __init__(self, credentials_file: Optional[str] = None):
        self.credentials_file = (
            credentials_file
            or os.getenv("GOOGLE_CREDENTIALS_FILE")
            or os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..",
                "..",
                "..",
                "..",
                "google_credentials.json",
            )
        )
        # Resolve to an absolute, canonical path
        self.credentials_file = os.path.realpath(self.credentials_file)

    # ------------------------------------------------------------------
    # Internal helpers (independently mockable)
    # ------------------------------------------------------------------

    def _build_sheets_service(self):
        """Authenticate and return a Sheets API v4 service."""
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        if not self.credentials_file or not os.path.isfile(self.credentials_file):
            raise EnvironmentError(
                f"Google credentials file not found: {self.credentials_file!r}. "
                "Set GOOGLE_CREDENTIALS_FILE or place google_credentials.json "
                "at the project root."
            )
        creds = Credentials.from_service_account_file(
            self.credentials_file, scopes=self.SCOPES
        )
        return build("sheets", "v4", credentials=creds)

    def _build_drive_service(self):
        """Authenticate and return a Drive API v3 service (for permissions)."""
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        if not self.credentials_file or not os.path.isfile(self.credentials_file):
            raise EnvironmentError(
                f"Google credentials file not found: {self.credentials_file!r}. "
                "Set GOOGLE_CREDENTIALS_FILE or place google_credentials.json "
                "at the project root."
            )
        creds = Credentials.from_service_account_file(
            self.credentials_file, scopes=self.SCOPES
        )
        return build("drive", "v3", credentials=creds)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_spreadsheet(
        self,
        title: str,
        sheet_headers: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        """
        Create a new Google Spreadsheet.

        Parameters
        ----------
        title : str
            Title for the new spreadsheet.
        sheet_headers : list[str], optional
            If provided, writes these as the first row in Sheet1.

        Returns
        -------
        dict
            ``{"spreadsheet_id": "<id>", "url": "<url>"}``
        """
        service = self._build_sheets_service()

        body = {"properties": {"title": title}}
        spreadsheet = service.spreadsheets().create(body=body).execute()

        spreadsheet_id = spreadsheet["spreadsheetId"]
        url = spreadsheet["spreadsheetUrl"]

        # Optionally seed the header row
        if sheet_headers:
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range="Sheet1!A1",
                valueInputOption="RAW",
                body={"values": [sheet_headers]},
            ).execute()

        print(f"[WorkspaceMaker] Created spreadsheet '{title}' → {url}")
        return {"spreadsheet_id": spreadsheet_id, "url": url}

    def create_opportunity_sheet(
        self,
        title: str,
        professor_email: str,
        sheet_headers: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        """
        Create a new Google Spreadsheet **and** share it with a professor.

        1. Creates the spreadsheet (owned by the service-account bot).
        2. Uses the Drive API to grant *writer* access to ``professor_email``.
        3. Returns ``{"spreadsheet_id": "…", "url": "…"}``.

        Parameters
        ----------
        title : str
            Title for the new spreadsheet.
        professor_email : str
            Email of the professor who will receive write access.
        sheet_headers : list[str], optional
            If provided, writes these as the first row in Sheet1.
        """
        # 1. Create the sheet
        result = self.create_spreadsheet(title, sheet_headers=sheet_headers)
        spreadsheet_id = result["spreadsheet_id"]

        # 2. Share with the professor via Drive API
        drive_svc = self._build_drive_service()
        permission = {
            "type": "user",
            "role": "writer",
            "emailAddress": professor_email,
        }
        drive_svc.permissions().create(
            fileId=spreadsheet_id,
            body=permission,
            sendNotificationEmail=True,
        ).execute()

        print(
            f"[WorkspaceMaker] Shared spreadsheet {spreadsheet_id} "
            f"with {professor_email}"
        )
        return result

    def create_form(self, title: str) -> Dict[str, str]:
        """
        Create a new Google Form.

        .. note:: The Forms API requires separate OAuth scopes and is
           currently in limited preview. This is a placeholder that returns
           a stub result until the Forms API is fully enabled.

        Returns
        -------
        dict
            ``{"form_id": "<id>", "url": "<url>"}``
        """
        # Google Forms API v1 is in limited access; stub for now
        print(
            f"[WorkspaceMaker] Google Forms API not yet enabled — "
            f"returning stub for '{title}'."
        )
        return {
            "form_id": "stub-form-id",
            "url": "https://docs.google.com/forms/d/stub-form-id/edit",
        }
