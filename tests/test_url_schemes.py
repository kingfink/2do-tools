import _2do_mcp.url_schemes as url_schemes


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


def test_open_url_launches_macos_url_scheme(monkeypatch) -> None:
    calls: list[tuple[list[str], bool]] = []

    def run(args: list[str], *, check: bool) -> None:
        calls.append((args, check))

    monkeypatch.setattr(url_schemes.subprocess, "run", run)

    url_schemes.open_url("twodo://x-callback-url/showtoday")

    assert calls == [(["open", "twodo://x-callback-url/showtoday"], True)]
