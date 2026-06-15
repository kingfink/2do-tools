import secrets
import subprocess
import time
from collections.abc import Callable
from datetime import date
from enum import StrEnum
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Self
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, field_validator, model_validator

from .url_schemes import add_task_url, open_url, show_task_url


class RepeatPreset(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"

    @property
    def url_value(self) -> int:
        return {
            RepeatPreset.DAILY: 1,
            RepeatPreset.WEEKLY: 2,
            RepeatPreset.BIWEEKLY: 3,
            RepeatPreset.MONTHLY: 4,
        }[self]


class TaskDraft(BaseModel):
    title: str
    notes: str | None = None
    list_name: str = "Inbox"
    due_date: date | None = None
    tags: list[str] | None = None
    repeat: RepeatPreset | None = None

    @field_validator("title")
    @classmethod
    def _normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("title must not be blank")
        return normalized

    @field_validator("notes")
    @classmethod
    def _normalize_notes(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return value

    @field_validator("list_name")
    @classmethod
    def _normalize_list_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("list name must not be blank")
        return normalized

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, value: list[str] | None) -> list[str] | None:
        if not value:
            return None

        normalized_tags: list[str] = []
        seen_tags: set[str] = set()

        for tag in value:
            normalized = tag.strip()
            if not normalized:
                raise ValueError("tag names must not be blank")
            if "," in normalized or "\n" in normalized or "\r" in normalized:
                raise ValueError("tag names must not contain commas or newlines")

            tag_key = normalized.casefold()
            if tag_key not in seen_tags:
                normalized_tags.append(normalized)
                seen_tags.add(tag_key)

        return normalized_tags

    @model_validator(mode="after")
    def _validate_repeat_due_date(self) -> Self:
        if self.repeat is not None and self.due_date is None:
            raise ValueError("a due date is required for repeating tasks")
        return self


class TaskCreationStatus(StrEnum):
    CREATED = "created"
    CANCELLED = "cancelled"
    FAILED = "failed"


class TaskCreationResult(BaseModel):
    status: TaskCreationStatus
    uid: str | None = None
    task_url: str | None = None
    message: str


class ConfirmationStatus(StrEnum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ConfirmationResult(BaseModel):
    status: ConfirmationStatus
    message: str


NATIVE_CONFIRM_SCRIPT = (
    "on run argv\n"
    "    set taskPreview to item 1 of argv\n"
    "    try\n"
    '        display dialog taskPreview with title "2Do Tools" '
    'buttons {"Cancel", "Create"} default button "Create" '
    'cancel button "Cancel"\n'
    '        return "confirmed"\n'
    "    on error number -128\n"
    '        return "cancelled"\n'
    "    end try\n"
    "end run"
)


def task_preview(draft: TaskDraft) -> str:
    lines = [f"Title: {draft.title}"]
    if draft.notes is not None:
        lines.append(f"Notes: {draft.notes}")
    lines.append(f"List: {draft.list_name}")
    if draft.due_date is not None:
        lines.append(f"Due: {draft.due_date.isoformat()}")
    if draft.tags:
        lines.append(f"Tags: {', '.join(draft.tags)}")
    if draft.repeat is not None:
        lines.append(f"Repeat: {draft.repeat.value}")
    return "\n".join(lines)


def confirm_task_native(
    draft: TaskDraft,
    *,
    run_fn: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> ConfirmationResult:
    try:
        completed = run_fn(
            ["osascript", "-e", NATIVE_CONFIRM_SCRIPT, task_preview(draft)],
            check=False,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return ConfirmationResult(
            status=ConfirmationStatus.FAILED,
            message=f"Could not display confirmation: {exc}",
        )

    if completed.returncode != 0:
        detail = completed.stderr.strip() or "unknown osascript error"
        return ConfirmationResult(
            status=ConfirmationStatus.FAILED,
            message=f"Could not display confirmation: {detail}",
        )

    response = completed.stdout.strip()
    if response == "confirmed":
        return ConfirmationResult(
            status=ConfirmationStatus.CONFIRMED,
            message="Task creation confirmed.",
        )
    if response == "cancelled":
        return ConfirmationResult(
            status=ConfirmationStatus.CANCELLED,
            message="Task creation cancelled.",
        )

    return ConfirmationResult(
        status=ConfirmationStatus.FAILED,
        message="Could not interpret the native confirmation response.",
    )


class TaskCallbackListener:
    def __init__(self) -> None:
        self._token = secrets.token_urlsafe(24)
        self._server: HTTPServer | None = None
        self._result: TaskCreationResult | None = None

    def __enter__(self) -> "TaskCallbackListener":
        self._server = HTTPServer(("127.0.0.1", 0), self._handler_type())
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: object,
    ) -> None:
        if self._server is not None:
            self._server.server_close()

    @property
    def success_url(self) -> str:
        return self._callback_url("success")

    @property
    def error_url(self) -> str:
        return self._callback_url("error")

    @property
    def cancel_url(self) -> str:
        return self._callback_url("cancel")

    def wait(self, timeout: float) -> TaskCreationResult:
        server = self._require_server()
        deadline = time.monotonic() + timeout

        while self._result is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            server.timeout = remaining
            server.handle_request()

        if self._result is None:
            return TaskCreationResult(
                status=TaskCreationStatus.FAILED,
                message=(
                    "Timed out waiting for 2Do. Task creation may have succeeded; "
                    "check 2Do before retrying."
                ),
            )

        return self._result

    def _require_server(self) -> HTTPServer:
        if self._server is None:
            raise RuntimeError("callback listener is not running")
        return self._server

    def _callback_url(self, kind: str) -> str:
        server = self._require_server()
        return f"http://127.0.0.1:{server.server_port}/callback/{self._token}/{kind}"

    def _handler_type(self) -> type[BaseHTTPRequestHandler]:
        listener = self

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed_url = urlparse(self.path)
                result = listener._parse_callback(parsed_url.path, parsed_url.query)
                if result is None:
                    self.send_error(404)
                    return

                listener._result = result
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"2Do Tools received the callback.\n")

            def do_POST(self) -> None:
                self.send_error(405)

            def log_message(self, _format: str, *args: object) -> None:
                return

        return CallbackHandler

    def _parse_callback(self, path: str, query: str) -> TaskCreationResult | None:
        expected_prefix = f"/callback/{self._token}/"
        if not path.startswith(expected_prefix):
            return None

        callback_kind = path.removeprefix(expected_prefix)
        query_params = parse_qs(query, keep_blank_values=True)

        if callback_kind == "success":
            uid = query_params.get("add", [""])[0].strip()
            if not uid:
                return TaskCreationResult(
                    status=TaskCreationStatus.FAILED,
                    message="2Do reported success without returning a task UID.",
                )
            return TaskCreationResult(
                status=TaskCreationStatus.CREATED,
                uid=uid,
                task_url=show_task_url(uid),
                message="Created task.",
            )

        if callback_kind == "error":
            error_message = next(
                (
                    query_params[name][0].strip()
                    for name in ("errorMessage", "error-message", "message")
                    if query_params.get(name) and query_params[name][0].strip()
                ),
                "Unknown error.",
            )
            return TaskCreationResult(
                status=TaskCreationStatus.FAILED,
                message=f"2Do could not create the task: {error_message}",
            )

        if callback_kind == "cancel":
            return TaskCreationResult(
                status=TaskCreationStatus.CANCELLED,
                message="Task creation cancelled.",
            )

        return None


def create_task_direct(
    draft: TaskDraft,
    *,
    open_url_fn: Callable[[str], None] = open_url,
    listener_factory: Callable[[], TaskCallbackListener] = TaskCallbackListener,
    timeout: float = 30.0,
) -> TaskCreationResult:
    try:
        listener_context = listener_factory()
        with listener_context as listener:
            url = add_task_url(
                title=draft.title,
                notes=draft.notes,
                list_name=draft.list_name,
                due_date=draft.due_date,
                tags=draft.tags,
                repeat=draft.repeat.url_value if draft.repeat is not None else None,
                success_url=listener.success_url,
                error_url=listener.error_url,
                cancel_url=listener.cancel_url,
            )

            try:
                open_url_fn(url)
            except (OSError, subprocess.SubprocessError) as exc:
                return TaskCreationResult(
                    status=TaskCreationStatus.FAILED,
                    message=f"Could not open 2Do: {exc}",
                )

            try:
                return listener.wait(timeout)
            except (OSError, RuntimeError) as exc:
                return TaskCreationResult(
                    status=TaskCreationStatus.FAILED,
                    message=f"Could not receive 2Do callback: {exc}",
                )
    except (OSError, RuntimeError) as exc:
        return TaskCreationResult(
            status=TaskCreationStatus.FAILED,
            message=f"Could not start task callback listener: {exc}",
        )
