import subprocess
import sys
from datetime import date
from subprocess import CompletedProcess
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from pydantic import ValidationError

import _2do_tools.task_creation as task_creation
from _2do_tools.task_creation import (
    NATIVE_CONFIRM_SCRIPT,
    ConfirmationStatus,
    RepeatPreset,
    TaskCreationCallbackListener,
    TaskCreationResult,
    TaskCreationStatus,
    TaskDraft,
    confirm_task_native,
    create_task_direct,
    task_preview,
)


@pytest.mark.skipif(sys.platform != "darwin", reason="AppleScript is macOS-only")
def test_native_confirmation_script_compiles(tmp_path) -> None:
    subprocess.run(
        [
            "osacompile",
            "-e",
            NATIVE_CONFIRM_SCRIPT,
            "-o",
            str(tmp_path / "confirm.scpt"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def test_task_draft_normalizes_fields_and_deduplicates_tags() -> None:
    draft = TaskDraft(
        title="  Buy milk  ",
        notes="   ",
        list_name=" inbox ",
        due_date=date(2026, 6, 20),
        tags=[" Home ", "home", "Errands"],
        repeat=RepeatPreset.WEEKLY,
    )

    assert draft.title == "Buy milk"
    assert draft.notes is None
    assert draft.list_name == "inbox"
    assert draft.due_date == date(2026, 6, 20)
    assert draft.tags == ["Home", "Errands"]
    assert draft.repeat is RepeatPreset.WEEKLY
    assert draft.repeat.url_value == 2


@pytest.mark.parametrize(
    ("preset", "url_value"),
    [
        (RepeatPreset.DAILY, 1),
        (RepeatPreset.WEEKLY, 2),
        (RepeatPreset.BIWEEKLY, 3),
        (RepeatPreset.MONTHLY, 4),
    ],
)
def test_repeat_presets_map_to_2do_values(
    preset: RepeatPreset,
    url_value: int,
) -> None:
    assert preset.url_value == url_value


def test_task_preview_includes_populated_fields_in_stable_order() -> None:
    draft = TaskDraft(
        title="Buy milk",
        notes="Whole milk",
        list_name="Inbox",
        due_date=date(2026, 6, 20),
        tags=["Home", "Errands"],
        repeat=RepeatPreset.DAILY,
    )

    assert task_preview(draft) == (
        "Title: Buy milk\n"
        "Notes: Whole milk\n"
        "List: Inbox\n"
        "Due: 2026-06-20\n"
        "Tags: Home, Errands\n"
        "Repeat: daily"
    )


def test_task_preview_omits_absent_optional_fields() -> None:
    assert (
        task_preview(TaskDraft(title="Buy milk", list_name="Inbox"))
        == "Title: Buy milk\nList: Inbox"
    )


def test_task_draft_rejects_blank_title() -> None:
    with pytest.raises(ValidationError, match="title must not be blank"):
        TaskDraft(title="  ", list_name="Inbox")


def test_task_draft_rejects_blank_tag() -> None:
    with pytest.raises(ValidationError, match="tag names must not be blank"):
        TaskDraft(title="Buy milk", list_name="Inbox", tags=["Home", " "])


@pytest.mark.parametrize("tag", ["Client, urgent", "Client\nurgent"])
def test_task_draft_rejects_tag_delimiters(tag: str) -> None:
    with pytest.raises(ValidationError, match="commas or newlines"):
        TaskDraft(title="Buy milk", list_name="Inbox", tags=[tag])


def test_task_draft_requires_due_date_for_repeat() -> None:
    with pytest.raises(ValidationError, match="due date is required"):
        TaskDraft(
            title="Buy milk",
            list_name="Inbox",
            repeat=RepeatPreset.WEEKLY,
        )


def _send_request(url: str, *, method: str = "GET") -> None:
    with urlopen(Request(url, method=method), timeout=1) as response:
        assert response.status == 200


def test_callback_listener_accepts_success_with_task_uid() -> None:
    with TaskCreationCallbackListener() as listener:
        sender = Thread(target=_send_request, args=(f"{listener.success_url}?add=task-123",))
        sender.start()
        result = listener.wait(timeout=1)
        sender.join()

    assert result == TaskCreationResult(
        status=TaskCreationStatus.CREATED,
        uid="task-123",
        task_url="twodo://x-callback-url/showtask?uid=task-123",
        message="Created task.",
    )


def test_callback_listener_rejects_invalid_token_then_accepts_valid_callback() -> None:
    with TaskCreationCallbackListener() as listener:
        invalid_url = listener.success_url.replace(
            listener.success_url.rsplit("/", 2)[-2],
            "invalid-token",
        )

        def send_callbacks() -> None:
            with pytest.raises(HTTPError) as exc_info:
                _send_request(f"{invalid_url}?add=wrong-task")
            assert exc_info.value.code == 404
            _send_request(f"{listener.success_url}?add=task-123")

        sender = Thread(target=send_callbacks)
        sender.start()
        result = listener.wait(timeout=1)
        sender.join()

    assert result.status is TaskCreationStatus.CREATED
    assert result.uid == "task-123"


def test_callback_listener_rejects_non_get_then_accepts_valid_callback() -> None:
    with TaskCreationCallbackListener() as listener:

        def send_callbacks() -> None:
            with pytest.raises(HTTPError) as exc_info:
                _send_request(listener.cancel_url, method="POST")
            assert exc_info.value.code == 405
            _send_request(listener.cancel_url)

        sender = Thread(target=send_callbacks)
        sender.start()
        result = listener.wait(timeout=1)
        sender.join()

    assert result.status is TaskCreationStatus.CANCELLED


def test_callback_listener_fails_success_without_uid() -> None:
    with TaskCreationCallbackListener() as listener:
        sender = Thread(target=_send_request, args=(listener.success_url,))
        sender.start()
        result = listener.wait(timeout=1)
        sender.join()

    assert result.status is TaskCreationStatus.FAILED
    assert result.uid is None
    assert result.task_url is None
    assert "UID" in result.message


def test_callback_listener_returns_error_message() -> None:
    with TaskCreationCallbackListener() as listener:
        sender = Thread(
            target=_send_request,
            args=(f"{listener.error_url}?errorMessage=List%20not%20found",),
        )
        sender.start()
        result = listener.wait(timeout=1)
        sender.join()

    assert result.status is TaskCreationStatus.FAILED
    assert result.message == "2Do could not create the task: List not found"


def test_callback_listener_returns_cancelled() -> None:
    with TaskCreationCallbackListener() as listener:
        sender = Thread(target=_send_request, args=(listener.cancel_url,))
        sender.start()
        result = listener.wait(timeout=1)
        sender.join()

    assert result == TaskCreationResult(
        status=TaskCreationStatus.CANCELLED,
        message="Task creation cancelled.",
    )


def test_callback_listener_timeout_warns_about_unknown_outcome() -> None:
    with TaskCreationCallbackListener() as listener:
        result = listener.wait(timeout=0.01)

    assert result.status is TaskCreationStatus.FAILED
    assert "may have succeeded" in result.message
    assert "before retrying" in result.message


@pytest.mark.parametrize(
    ("query_params", "expected"),
    [
        ({"errorMessage": ["First"]}, "First"),
        ({"error-message": ["Second"]}, "Second"),
        ({"message": ["Third"]}, "Third"),
        ({}, "Unknown error."),
    ],
)
def test_callback_error_message_uses_supported_keys(
    query_params: dict[str, list[str]],
    expected: str,
) -> None:
    assert task_creation._callback_error_message(query_params) == expected


def test_completion_callback_listener_accepts_success_for_requested_uid() -> None:
    with task_creation.TaskCompletionCallbackListener("task-123") as listener:
        sender = Thread(target=_send_request, args=(listener.success_url,))
        sender.start()
        result = listener.wait(timeout=1)
        sender.join()

    assert result == task_creation.TaskCompletionResult(
        status=task_creation.TaskCompletionStatus.COMPLETED,
        uid="task-123",
        task_url="twodo://x-callback-url/showtask?uid=task-123",
        message="Completed task.",
    )


def test_completion_callback_listener_returns_error_message() -> None:
    with task_creation.TaskCompletionCallbackListener("task-123") as listener:
        sender = Thread(
            target=_send_request,
            args=(f"{listener.error_url}?errorMessage=Task%20not%20found",),
        )
        sender.start()
        result = listener.wait(timeout=1)
        sender.join()

    assert result == task_creation.TaskCompletionResult(
        status=task_creation.TaskCompletionStatus.FAILED,
        uid="task-123",
        task_url="twodo://x-callback-url/showtask?uid=task-123",
        message="2Do could not complete the task: Task not found",
    )


def test_completion_callback_listener_returns_cancelled() -> None:
    with task_creation.TaskCompletionCallbackListener("task-123") as listener:
        sender = Thread(target=_send_request, args=(listener.cancel_url,))
        sender.start()
        result = listener.wait(timeout=1)
        sender.join()

    assert result == task_creation.TaskCompletionResult(
        status=task_creation.TaskCompletionStatus.CANCELLED,
        uid="task-123",
        task_url="twodo://x-callback-url/showtask?uid=task-123",
        message="Task completion cancelled.",
    )


def test_completion_callback_listener_timeout_warns_about_unknown_outcome() -> None:
    with task_creation.TaskCompletionCallbackListener("task-123") as listener:
        result = listener.wait(timeout=0.01)

    assert isinstance(result, task_creation.TaskCompletionResult)
    assert result.status is task_creation.TaskCompletionStatus.FAILED
    assert result.uid == "task-123"
    assert result.task_url == "twodo://x-callback-url/showtask?uid=task-123"
    assert "may have succeeded" in result.message
    assert "before retrying" in result.message


class _FakeCallbackListener:
    success_url = "http://127.0.0.1:1234/callback/token/success"
    error_url = "http://127.0.0.1:1234/callback/token/error"
    cancel_url = "http://127.0.0.1:1234/callback/token/cancel"

    def __init__(self, result: TaskCreationResult) -> None:
        self.result = result
        self.entered = False
        self.wait_timeout: float | None = None

    def __enter__(self) -> "_FakeCallbackListener":
        self.entered = True
        return self

    def __exit__(self, *args: object) -> None:
        self.entered = False

    def wait(self, timeout: float) -> TaskCreationResult:
        self.wait_timeout = timeout
        return self.result


class _FakeCompletionCallbackListener:
    success_url = "http://127.0.0.1:1234/callback/token/success"
    error_url = "http://127.0.0.1:1234/callback/token/error"
    cancel_url = "http://127.0.0.1:1234/callback/token/cancel"

    def __init__(self, result: task_creation.TaskCompletionResult) -> None:
        self.result = result
        self.entered = False
        self.wait_timeout: float | None = None

    def __enter__(self) -> "_FakeCompletionCallbackListener":
        self.entered = True
        return self

    def __exit__(self, *args: object) -> None:
        self.entered = False

    def wait(self, timeout: float) -> task_creation.TaskCompletionResult:
        self.wait_timeout = timeout
        return self.result


def test_complete_task_direct_opens_url_after_listener_starts() -> None:
    expected = task_creation.TaskCompletionResult(
        status=task_creation.TaskCompletionStatus.COMPLETED,
        uid="task-123",
        task_url="twodo://x-callback-url/showtask?uid=task-123",
        message="Completed task.",
    )
    listener = _FakeCompletionCallbackListener(expected)
    opened_urls: list[str] = []
    listener_uids: list[str] = []

    def open_url(url: str) -> None:
        assert listener.entered is True
        opened_urls.append(url)

    def listener_factory(uid: str) -> _FakeCompletionCallbackListener:
        listener_uids.append(uid)
        return listener

    result = task_creation.complete_task_direct(
        "task-123",
        open_url_fn=open_url,
        listener_factory=listener_factory,
        timeout=7,
    )

    assert result == expected
    assert listener_uids == ["task-123"]
    assert listener.wait_timeout == 7
    assert opened_urls == [
        "twodo://x-callback-url/completetasks?"
        "uids=task-123"
        "&x-success=http%3A%2F%2F127.0.0.1%3A1234%2Fcallback%2Ftoken%2Fsuccess"
        "&x-error=http%3A%2F%2F127.0.0.1%3A1234%2Fcallback%2Ftoken%2Ferror"
        "&x-cancel=http%3A%2F%2F127.0.0.1%3A1234%2Fcallback%2Ftoken%2Fcancel"
        "&x-source=2Do%20Tools"
    ]


def test_complete_task_direct_returns_failed_when_2do_cannot_open() -> None:
    listener = _FakeCompletionCallbackListener(
        task_creation.TaskCompletionResult(
            status=task_creation.TaskCompletionStatus.COMPLETED,
            uid="unused",
            task_url="twodo://x-callback-url/showtask?uid=unused",
            message="unused",
        )
    )

    def fail_to_open(_url: str) -> None:
        raise OSError("2Do is unavailable")

    result = task_creation.complete_task_direct(
        "task-123",
        open_url_fn=fail_to_open,
        listener_factory=lambda _uid: listener,
    )

    assert result.status is task_creation.TaskCompletionStatus.FAILED
    assert result.uid == "task-123"
    assert result.message == "Could not open 2Do: 2Do is unavailable"
    assert listener.wait_timeout is None


def test_complete_task_direct_returns_failed_when_callback_listener_cannot_start() -> None:
    def broken_listener(_uid: str) -> object:
        raise OSError("address unavailable")

    result = task_creation.complete_task_direct(
        "task-123",
        listener_factory=broken_listener,
    )

    assert result.status is task_creation.TaskCompletionStatus.FAILED
    assert result.uid == "task-123"
    assert result.message == "Could not start task callback listener: address unavailable"


def test_complete_task_direct_returns_failed_when_callback_wait_errors() -> None:
    class BrokenWaitListener(_FakeCompletionCallbackListener):
        def wait(self, timeout: float) -> task_creation.TaskCompletionResult:
            raise OSError("callback connection failed")

    listener = BrokenWaitListener(
        task_creation.TaskCompletionResult(
            status=task_creation.TaskCompletionStatus.COMPLETED,
            uid="unused",
            task_url="twodo://x-callback-url/showtask?uid=unused",
            message="unused",
        )
    )

    result = task_creation.complete_task_direct(
        "task-123",
        open_url_fn=lambda _url: None,
        listener_factory=lambda _uid: listener,
    )

    assert result.status is task_creation.TaskCompletionStatus.FAILED
    assert result.uid == "task-123"
    assert result.message == "Could not receive 2Do callback: callback connection failed"


def test_create_task_direct_opens_url_after_listener_starts() -> None:
    expected = TaskCreationResult(
        status=TaskCreationStatus.CREATED,
        uid="task-123",
        task_url="twodo://x-callback-url/showtask?uid=task-123",
        message="Created task.",
    )
    listener = _FakeCallbackListener(expected)
    opened_urls: list[str] = []

    def open_url(url: str) -> None:
        assert listener.entered is True
        opened_urls.append(url)

    result = create_task_direct(
        TaskDraft(
            title="Buy milk",
            notes="Whole milk",
            list_name="Inbox",
            due_date=date(2026, 6, 20),
            tags=["Home"],
            repeat=RepeatPreset.DAILY,
        ),
        open_url_fn=open_url,
        listener_factory=lambda: listener,
        timeout=7,
    )

    assert result == expected
    assert listener.wait_timeout == 7
    assert len(opened_urls) == 1
    assert "task=Buy%20milk" in opened_urls[0]
    assert "x-success=http%3A%2F%2F127.0.0.1" in opened_urls[0]
    assert "token" not in result.task_url


def test_create_task_direct_returns_failed_when_2do_cannot_open() -> None:
    listener = _FakeCallbackListener(
        TaskCreationResult(
            status=TaskCreationStatus.CREATED,
            uid="unused",
            task_url="twodo://x-callback-url/showtask?uid=unused",
            message="unused",
        )
    )

    def fail_to_open(_url: str) -> None:
        raise OSError("2Do is unavailable")

    result = create_task_direct(
        TaskDraft(title="Buy milk", list_name="Inbox"),
        open_url_fn=fail_to_open,
        listener_factory=lambda: listener,
    )

    assert result.status is TaskCreationStatus.FAILED
    assert result.message == "Could not open 2Do: 2Do is unavailable"
    assert listener.wait_timeout is None


def test_create_task_direct_returns_failed_when_callback_listener_cannot_start() -> None:
    class BrokenListener:
        def __enter__(self) -> object:
            raise OSError("address unavailable")

        def __exit__(self, *args: object) -> None:
            return

    result = create_task_direct(
        TaskDraft(title="Buy milk", list_name="Inbox"),
        listener_factory=BrokenListener,
    )

    assert result.status is TaskCreationStatus.FAILED
    assert result.message == "Could not start task callback listener: address unavailable"


def test_create_task_direct_returns_failed_when_callback_wait_errors() -> None:
    class BrokenWaitListener(_FakeCallbackListener):
        def wait(self, timeout: float) -> TaskCreationResult:
            raise OSError("callback connection failed")

    listener = BrokenWaitListener(_created_result_for_test())

    result = create_task_direct(
        TaskDraft(title="Buy milk", list_name="Inbox"),
        open_url_fn=lambda _url: None,
        listener_factory=lambda: listener,
    )

    assert result.status is TaskCreationStatus.FAILED
    assert result.message == "Could not receive 2Do callback: callback connection failed"


def _created_result_for_test() -> TaskCreationResult:
    return TaskCreationResult(
        status=TaskCreationStatus.CREATED,
        uid="task-123",
        task_url="twodo://x-callback-url/showtask?uid=task-123",
        message="Created task.",
    )


def test_native_confirmation_passes_preview_as_process_argument() -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def run(args: list[str], **kwargs: object) -> CompletedProcess[str]:
        calls.append((args, kwargs))
        return CompletedProcess(args, 0, stdout="confirmed\n", stderr="")

    result = confirm_task_native(
        TaskDraft(
            title='Buy "special" milk',
            notes="Line one\nLine two",
            list_name="Inbox",
        ),
        run_fn=run,
    )

    assert result.status is ConfirmationStatus.CONFIRMED
    assert result.message == "Task creation confirmed."
    assert calls[0][0][:2] == ["osascript", "-e"]
    assert 'Buy "special" milk' not in calls[0][0][2]
    assert calls[0][0][3] == ('Title: Buy "special" milk\nNotes: Line one\nLine two\nList: Inbox')
    assert calls[0][0][4] == "Create"
    assert calls[0][1] == {
        "check": False,
        "capture_output": True,
        "text": True,
    }


def test_native_action_confirmation_passes_preview_and_button_label() -> None:
    calls: list[list[str]] = []

    def run(args: list[str], **_kwargs: object) -> CompletedProcess[str]:
        calls.append(args)
        return CompletedProcess(args, 0, stdout="confirmed\n", stderr="")

    result = task_creation.confirm_action_native(
        "Title: Buy milk\nList: Inbox\nUID: task-123",
        action="Complete",
        timeout_seconds=45,
        run_fn=run,
    )

    assert result.status is ConfirmationStatus.CONFIRMED
    assert calls[0][3] == "Title: Buy milk\nList: Inbox\nUID: task-123"
    assert calls[0][4] == "Complete"
    assert calls[0][5] == "45"
    assert "giving up after timeoutSeconds" in NATIVE_CONFIRM_SCRIPT
    assert "gave up of dialogResult" in NATIVE_CONFIRM_SCRIPT


def test_native_confirmation_returns_cancelled() -> None:
    def run(args: list[str], **_kwargs: object) -> CompletedProcess[str]:
        return CompletedProcess(args, 0, stdout="cancelled\n", stderr="")

    result = confirm_task_native(
        TaskDraft(title="Buy milk", list_name="Inbox"),
        run_fn=run,
    )

    assert result.status is ConfirmationStatus.CANCELLED
    assert result.message == "Task creation cancelled."


def test_native_confirmation_returns_cancelled_for_apple_event_timeout() -> None:
    def run(args: list[str], **_kwargs: object) -> CompletedProcess[str]:
        return CompletedProcess(
            args,
            1,
            stdout="",
            stderr="execution error: AppleEvent timed out. (-1712)\n",
        )

    result = task_creation.confirm_action_native(
        "Title: Buy milk",
        action="Create",
        operation="creation",
        run_fn=run,
    )

    assert result.status is ConfirmationStatus.CANCELLED
    assert result.message == "Task creation cancelled."


def test_native_confirmation_returns_failed_for_osascript_error() -> None:
    def run(args: list[str], **_kwargs: object) -> CompletedProcess[str]:
        return CompletedProcess(args, 1, stdout="", stderr="Not authorized\n")

    result = confirm_task_native(
        TaskDraft(title="Buy milk", list_name="Inbox"),
        run_fn=run,
    )

    assert result.status is ConfirmationStatus.FAILED
    assert result.message == "Could not display confirmation: Not authorized"


def test_native_confirmation_returns_failed_when_osascript_cannot_start() -> None:
    def run(
        _args: list[str],
        **_kwargs: object,
    ) -> CompletedProcess[str]:
        raise OSError("osascript unavailable")

    result = confirm_task_native(
        TaskDraft(title="Buy milk", list_name="Inbox"),
        run_fn=run,
    )

    assert result.status is ConfirmationStatus.FAILED
    assert result.message == "Could not display confirmation: osascript unavailable"
