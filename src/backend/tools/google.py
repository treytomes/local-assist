"""
Google account tools — Calendar, Tasks, Drive (read-only).

OAuth flow: the backend starts a loopback listener on localhost:8080,
builds an auth URL, and returns it to the frontend which opens it in
the system browser. The callback handler receives the code, exchanges it
for tokens, and stores them in the google_tokens DB table.
"""
import asyncio
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .. import database as db

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

REDIRECT_URI = "http://localhost:8080/oauth2callback"
_oauth_server: HTTPServer | None = None
_pending_future: asyncio.Future | None = None
_event_loop: asyncio.AbstractEventLoop | None = None
_pending_flow: "Flow | None" = None


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

def _client_id() -> str:
    return os.getenv("GOOGLE_CLIENT_ID", "")


def _client_secret() -> str:
    return os.getenv("GOOGLE_CLIENT_SECRET", "")


def get_credentials(conn: sqlite3.Connection) -> Credentials | None:
    """Return valid Credentials, refreshing the access token if needed."""
    row = db.get_google_tokens(conn)
    if not row:
        return None

    creds = Credentials(
        token=row["access_token"],
        refresh_token=row["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=_client_id(),
        client_secret=_client_secret(),
        scopes=row["scopes"].split(",") if row["scopes"] else SCOPES,
        expiry=datetime.fromisoformat(row["token_expiry"]) if row["token_expiry"] else None,
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with db.transaction(conn):
            db.upsert_google_tokens(
                conn,
                access_token=creds.token or "",
                refresh_token=creds.refresh_token or "",
                token_expiry=creds.expiry.isoformat() if creds.expiry else "",
                email=row["email"],
                scopes=",".join(creds.scopes or []),
            )

    return creds


def auth_status(conn: sqlite3.Connection) -> dict:
    row = db.get_google_tokens(conn)
    if not row:
        return {"connected": False, "email": None}
    return {"connected": True, "email": row["email"]}


# ---------------------------------------------------------------------------
# OAuth flow
# ---------------------------------------------------------------------------

def _client_config() -> dict:
    return {
        "installed": {
            "client_id": _client_id(),
            "client_secret": _client_secret(),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }


def build_auth_url() -> tuple[str, "Flow"]:
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    url, _ = flow.authorization_url(access_type="offline", prompt="consent")
    return url, flow


async def start_oauth_flow(conn: sqlite3.Connection) -> dict:
    """
    Starts the loopback OAuth server, returns the auth URL.
    The frontend opens the URL; the callback completes in the background.
    """
    global _oauth_server, _pending_future, _event_loop

    # Shut down any leftover server from a previous attempt before binding again
    if _oauth_server is not None:
        threading.Thread(target=_oauth_server.shutdown, daemon=True).start()
        _oauth_server = None
    if _pending_future is not None and not _pending_future.done():
        _pending_future.cancel()

    _event_loop = asyncio.get_event_loop()
    _pending_future = _event_loop.create_future()
    global _pending_flow

    def _run_server():
        global _oauth_server

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass  # suppress access logs

            def do_GET(self):
                parsed = urlparse(self.path)
                params = parse_qs(parsed.query)
                code = params.get("code", [None])[0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                if code:
                    self.wfile.write(b"<h2>Connected! You can close this tab.</h2>")
                    _event_loop.call_soon_threadsafe(
                        _pending_future.set_result, code
                    )
                else:
                    self.wfile.write(b"<h2>Auth failed - no code received.</h2>")
                    _event_loop.call_soon_threadsafe(
                        _pending_future.set_exception,
                        RuntimeError("No code in callback"),
                    )
                # Shut down in a separate thread so do_GET can return first
                threading.Thread(target=_oauth_server.shutdown, daemon=True).start()

        HTTPServer.allow_reuse_address = True
        _oauth_server = HTTPServer(("localhost", 8080), _Handler)
        _oauth_server.serve_forever()

    threading.Thread(target=_run_server, daemon=True).start()

    url, flow = build_auth_url()
    _pending_flow = flow

    async def _exchange_in_background():
        import logging
        log = logging.getLogger(__name__)
        try:
            code = await asyncio.wait_for(_pending_future, timeout=300)
            loop = asyncio.get_event_loop()
            flow = _pending_flow

            def _do_exchange():
                flow.fetch_token(code=code)
                creds = flow.credentials
                email = ""
                try:
                    user_info = build("oauth2", "v2", credentials=creds).userinfo().get().execute()
                    email = user_info.get("email", "")
                except Exception:
                    pass
                return creds, email

            creds, email = await loop.run_in_executor(None, _do_exchange)
            with db.transaction(conn):
                db.upsert_google_tokens(
                    conn,
                    access_token=creds.token or "",
                    refresh_token=creds.refresh_token or "",
                    token_expiry=creds.expiry.isoformat() if creds.expiry else "",
                    email=email,
                    scopes=",".join(creds.scopes or []),
                )
            log.info("Google OAuth complete, stored tokens for %s", email)
        except Exception as e:
            log.error("Google OAuth exchange failed: %s", e, exc_info=True)

    asyncio.create_task(_exchange_in_background())
    return {"auth_url": url}


def revoke_tokens(conn: sqlite3.Connection) -> dict:
    import requests as _requests
    row = db.get_google_tokens(conn)
    if row:
        try:
            _requests.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": row["access_token"]},
                headers={"content-type": "application/x-www-form-urlencoded"},
                timeout=5,
            )
        except Exception:
            pass
        with db.transaction(conn):
            db.delete_google_tokens(conn)
    return {"revoked": True}


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------

def _cal(creds: Credentials):
    return build("calendar", "v3", credentials=creds)


def list_calendars(conn: sqlite3.Connection) -> dict:
    creds = get_credentials(conn)
    if not creds:
        return {"error": "Not authenticated with Google"}
    try:
        result = _cal(creds).calendarList().list().execute()
        calendars = [
            {"id": c["id"], "name": c.get("summary", ""), "primary": c.get("primary", False)}
            for c in result.get("items", [])
        ]
        return {"calendars": calendars}
    except HttpError as e:
        return {"error": str(e)}


def get_calendar_events(
    conn: sqlite3.Connection,
    calendar_id: str = "primary",
    time_min: str | None = None,
    time_max: str | None = None,
    max_results: int = 10,
) -> dict:
    creds = get_credentials(conn)
    if not creds:
        return {"error": "Not authenticated with Google"}
    try:
        if not time_min:
            time_min = datetime.now(timezone.utc).isoformat()
        kwargs = {
            "calendarId": calendar_id,
            "timeMin": time_min,
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
        }
        if time_max:
            kwargs["timeMax"] = time_max
        result = _cal(creds).events().list(**kwargs).execute()
        events = []
        for e in result.get("items", []):
            start = e.get("start", {})
            end = e.get("end", {})
            events.append({
                "id": e["id"],
                "summary": e.get("summary", "(no title)"),
                "start": start.get("dateTime") or start.get("date"),
                "end": end.get("dateTime") or end.get("date"),
                "description": e.get("description", ""),
                "location": e.get("location", ""),
                "attendees": [a.get("email") for a in e.get("attendees", [])],
            })
        return {"events": events}
    except HttpError as e:
        return {"error": str(e)}


def create_calendar_event(
    conn: sqlite3.Connection,
    summary: str,
    start: str,
    end: str,
    calendar_id: str = "primary",
    description: str = "",
    attendees: list[str] | None = None,
) -> dict:
    creds = get_credentials(conn)
    if not creds:
        return {"error": "Not authenticated with Google"}
    try:
        body: dict = {
            "summary": summary,
            "start": {"dateTime": start, "timeZone": "UTC"},
            "end": {"dateTime": end, "timeZone": "UTC"},
        }
        if description:
            body["description"] = description
        if attendees:
            body["attendees"] = [{"email": a} for a in attendees]
        event = _cal(creds).events().insert(calendarId=calendar_id, body=body).execute()
        return {"id": event["id"], "summary": event.get("summary"), "htmlLink": event.get("htmlLink")}
    except HttpError as e:
        return {"error": str(e)}


def update_calendar_event(
    conn: sqlite3.Connection,
    event_id: str,
    calendar_id: str = "primary",
    summary: str | None = None,
    start: str | None = None,
    end: str | None = None,
    description: str | None = None,
) -> dict:
    creds = get_credentials(conn)
    if not creds:
        return {"error": "Not authenticated with Google"}
    try:
        event = _cal(creds).events().get(calendarId=calendar_id, eventId=event_id).execute()
        if summary is not None:
            event["summary"] = summary
        if start is not None:
            event["start"] = {"dateTime": start, "timeZone": "UTC"}
        if end is not None:
            event["end"] = {"dateTime": end, "timeZone": "UTC"}
        if description is not None:
            event["description"] = description
        updated = _cal(creds).events().update(calendarId=calendar_id, eventId=event_id, body=event).execute()
        return {"id": updated["id"], "summary": updated.get("summary"), "updated": True}
    except HttpError as e:
        return {"error": str(e)}


def delete_calendar_event(
    conn: sqlite3.Connection,
    event_id: str,
    calendar_id: str = "primary",
) -> dict:
    creds = get_credentials(conn)
    if not creds:
        return {"error": "Not authenticated with Google"}
    try:
        _cal(creds).events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return {"deleted": True, "event_id": event_id}
    except HttpError as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

def _tasks_svc(creds: Credentials):
    return build("tasks", "v1", credentials=creds)


def list_task_lists(conn: sqlite3.Connection) -> dict:
    creds = get_credentials(conn)
    if not creds:
        return {"error": "Not authenticated with Google"}
    try:
        result = _tasks_svc(creds).tasklists().list(maxResults=20).execute()
        lists = [{"id": tl["id"], "title": tl.get("title", "")} for tl in result.get("items", [])]
        return {"task_lists": lists}
    except HttpError as e:
        return {"error": str(e)}


def get_tasks(
    conn: sqlite3.Connection,
    task_list_id: str = "@default",
    show_completed: bool = False,
) -> dict:
    creds = get_credentials(conn)
    if not creds:
        return {"error": "Not authenticated with Google"}
    try:
        result = _tasks_svc(creds).tasks().list(
            tasklist=task_list_id,
            showCompleted=show_completed,
            showHidden=show_completed,
            maxResults=50,
        ).execute()
        tasks = [
            {
                "id": t["id"],
                "title": t.get("title", ""),
                "status": t.get("status", ""),
                "due": t.get("due"),
                "notes": t.get("notes", ""),
            }
            for t in result.get("items", [])
        ]
        return {"tasks": tasks}
    except HttpError as e:
        return {"error": str(e)}


def create_task(
    conn: sqlite3.Connection,
    title: str,
    task_list_id: str = "@default",
    notes: str = "",
    due: str | None = None,
) -> dict:
    creds = get_credentials(conn)
    if not creds:
        return {"error": "Not authenticated with Google"}
    try:
        body: dict = {"title": title}
        if notes:
            body["notes"] = notes
        if due:
            body["due"] = due
        task = _tasks_svc(creds).tasks().insert(tasklist=task_list_id, body=body).execute()
        return {"id": task["id"], "title": task.get("title"), "created": True}
    except HttpError as e:
        return {"error": str(e)}


def complete_task(
    conn: sqlite3.Connection,
    task_id: str,
    task_list_id: str = "@default",
) -> dict:
    creds = get_credentials(conn)
    if not creds:
        return {"error": "Not authenticated with Google"}
    try:
        task = _tasks_svc(creds).tasks().get(tasklist=task_list_id, task=task_id).execute()
        task["status"] = "completed"
        updated = _tasks_svc(creds).tasks().update(tasklist=task_list_id, task=task_id, body=task).execute()
        return {"id": updated["id"], "title": updated.get("title"), "completed": True}
    except HttpError as e:
        return {"error": str(e)}


def update_task(
    conn: sqlite3.Connection,
    task_id: str,
    task_list_id: str = "@default",
    title: str | None = None,
    notes: str | None = None,
    due: str | None = None,
) -> dict:
    creds = get_credentials(conn)
    if not creds:
        return {"error": "Not authenticated with Google"}
    try:
        task = _tasks_svc(creds).tasks().get(tasklist=task_list_id, task=task_id).execute()
        if title is not None:
            task["title"] = title
        if notes is not None:
            task["notes"] = notes
        if due is not None:
            task["due"] = due
        updated = _tasks_svc(creds).tasks().update(tasklist=task_list_id, task=task_id, body=task).execute()
        return {"id": updated["id"], "title": updated.get("title"), "updated": True}
    except HttpError as e:
        return {"error": str(e)}


def delete_task(
    conn: sqlite3.Connection,
    task_id: str,
    task_list_id: str = "@default",
) -> dict:
    creds = get_credentials(conn)
    if not creds:
        return {"error": "Not authenticated with Google"}
    try:
        _tasks_svc(creds).tasks().delete(tasklist=task_list_id, task=task_id).execute()
        return {"deleted": True, "task_id": task_id}
    except HttpError as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Drive (read-only)
# ---------------------------------------------------------------------------

def _drive(creds: Credentials):
    return build("drive", "v3", credentials=creds)


# MIME types that can be exported as plain text
_EXPORT_MIME = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}


def search_drive(conn: sqlite3.Connection, query: str, max_results: int = 10) -> dict:
    creds = get_credentials(conn)
    if not creds:
        return {"error": "Not authenticated with Google"}
    try:
        result = _drive(creds).files().list(
            q=f"fullText contains '{query.replace(chr(39), chr(39)*2)}'",
            pageSize=max_results,
            fields="files(id,name,mimeType,webViewLink,modifiedTime)",
        ).execute()
        files = [
            {
                "id": f["id"],
                "name": f.get("name", ""),
                "mimeType": f.get("mimeType", ""),
                "webViewLink": f.get("webViewLink", ""),
                "modifiedTime": f.get("modifiedTime", ""),
            }
            for f in result.get("files", [])
        ]
        return {"files": files}
    except HttpError as e:
        return {"error": str(e)}


def get_drive_file(conn: sqlite3.Connection, file_id: str) -> dict:
    creds = get_credentials(conn)
    if not creds:
        return {"error": "Not authenticated with Google"}
    try:
        meta = _drive(creds).files().get(
            fileId=file_id,
            fields="id,name,mimeType,webViewLink,modifiedTime,size",
        ).execute()
        mime = meta.get("mimeType", "")
        preview = ""
        if mime in _EXPORT_MIME:
            content = (
                _drive(creds).files()
                .export(fileId=file_id, mimeType=_EXPORT_MIME[mime])
                .execute()
            )
            preview = content.decode("utf-8", errors="replace")[:2000]
        elif mime.startswith("text/"):
            content = _drive(creds).files().get_media(fileId=file_id).execute()
            preview = content.decode("utf-8", errors="replace")[:2000]
        return {
            "id": meta["id"],
            "name": meta.get("name", ""),
            "mimeType": mime,
            "webViewLink": meta.get("webViewLink", ""),
            "modifiedTime": meta.get("modifiedTime", ""),
            "size": meta.get("size"),
            "preview": preview,
        }
    except HttpError as e:
        return {"error": str(e)}
