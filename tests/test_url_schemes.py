from datetime import date

import pytest

import _2do_tools.url_schemes as url_schemes


def test_show_task_url_encodes_uid() -> None:
    assert (
        url_schemes.show_task_url("task 123/abc?")
        == "twodo://x-callback-url/showtask?uid=task%20123%2Fabc%3F"
    )


def test_show_list_url_encodes_name() -> None:
    assert (
        url_schemes.show_list_url("Work & Home")
        == "twodo://x-callback-url/showlist?name=Work%20%26%20Home"
    )


def test_search_url_encodes_text() -> None:
    assert (
        url_schemes.search_url("invoice, admin\nnext")
        == "twodo://x-callback-url/search?text=invoice%2C%20admin%0Anext"
    )


def test_add_task_url_encodes_quick_entry_fields() -> None:
    assert url_schemes.add_task_url(
        title="Review & send",
        notes="Line one\nLine two",
        list_name="Work",
        due_date=date(2026, 6, 20),
        tags=["Client", "Follow up"],
        repeat=2,
        use_quick_entry=True,
    ) == (
        "twodo://x-callback-url/add?"
        "task=Review%20%26%20send"
        "&note=Line%20one%0ALine%20two"
        "&forlist=Work"
        "&due=2026-06-20"
        "&tags=Client%2CFollow%20up"
        "&repeat=2"
        "&ignoredefaults=1"
        "&usequickentry=1"
    )


def test_add_task_url_encodes_callbacks_and_omits_absent_fields() -> None:
    assert url_schemes.add_task_url(
        title="Buy milk",
        notes=None,
        list_name="Inbox",
        due_date=None,
        tags=None,
        repeat=None,
        success_url="http://127.0.0.1:8000/success/token",
        error_url="http://127.0.0.1:8000/error/token",
        cancel_url="http://127.0.0.1:8000/cancel/token",
    ) == (
        "twodo://x-callback-url/add?"
        "task=Buy%20milk"
        "&forlist=Inbox"
        "&ignoredefaults=1"
        "&x-success=http%3A%2F%2F127.0.0.1%3A8000%2Fsuccess%2Ftoken"
        "&x-error=http%3A%2F%2F127.0.0.1%3A8000%2Ferror%2Ftoken"
        "&x-cancel=http%3A%2F%2F127.0.0.1%3A8000%2Fcancel%2Ftoken"
        "&x-source=2Do%20Tools"
    )


def test_complete_task_url_encodes_one_uid_and_callbacks() -> None:
    assert url_schemes.complete_task_url(
        uid="task 123/abc?",
        success_url="http://127.0.0.1:8000/success/token",
        error_url="http://127.0.0.1:8000/error/token",
        cancel_url="http://127.0.0.1:8000/cancel/token",
    ) == (
        "twodo://x-callback-url/completetasks?"
        "uids=task%20123%2Fabc%3F"
        "&x-success=http%3A%2F%2F127.0.0.1%3A8000%2Fsuccess%2Ftoken"
        "&x-error=http%3A%2F%2F127.0.0.1%3A8000%2Ferror%2Ftoken"
        "&x-cancel=http%3A%2F%2F127.0.0.1%3A8000%2Fcancel%2Ftoken"
        "&x-source=2Do%20Tools"
    )


def test_complete_task_url_rejects_multiple_uids() -> None:
    with pytest.raises(ValueError, match="exactly one task UID"):
        url_schemes.complete_task_url(
            uid="task-123,task-456",
            success_url="http://127.0.0.1:8000/success/token",
            error_url="http://127.0.0.1:8000/error/token",
            cancel_url="http://127.0.0.1:8000/cancel/token",
        )


def test_open_url_launches_macos_url_scheme(monkeypatch) -> None:
    calls: list[tuple[list[str], bool]] = []

    def run(args: list[str], *, check: bool) -> None:
        calls.append((args, check))

    monkeypatch.setattr(url_schemes.subprocess, "run", run)

    url_schemes.open_url("twodo://x-callback-url/showtoday")

    assert calls == [(["open", "twodo://x-callback-url/showtoday"], True)]
