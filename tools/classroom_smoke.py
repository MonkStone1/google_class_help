"""Manual Google Classroom smoke test (run by hand, not by pytest).

Formerly ``backend/test_classroom.py``: the ``test_*`` name made pytest
collect it, and a bare run demanded ``credentials.json``, opened a browser
and wrote its token into ``backend/token.json`` instead of the user data
dir (review §1.8). It is not an automated test — it is a human-driven check
that the OAuth flow and the courses.list call work against a real account.

Usage (from the project root):

    .venv\\Scripts\\python.exe tools\\classroom_smoke.py

The token is read from / written to the app's real token location
(``GC_DASHBOARD_TOKEN`` or ``DATA_DIR/token.json``), so a sign-in performed
here is also picked up by the dashboard.
"""

import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR / "backend"))

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import CREDENTIALS_FILE, TOKEN_FILE

SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.student-submissions.me.readonly",
    "https://www.googleapis.com/auth/classroom.student-submissions.students.readonly",
    "https://www.googleapis.com/auth/classroom.rosters.readonly",
]


def main() -> None:
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    service = build("classroom", "v1", credentials=creds)
    results = service.courses().list(pageSize=100).execute()
    courses = results.get("courses", [])
    if not courses:
        print("No courses found.")
        return
    print("\nYour Google Classroom courses:\n")
    for course in courses:
        print(f"{course['id']} — {course['name']}")


if __name__ == "__main__":
    main()
