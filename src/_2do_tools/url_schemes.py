import subprocess
from datetime import date
from urllib.parse import quote, urlencode

BASE_URL = "twodo://x-callback-url"


def _url(action: str, params: dict[str, str] | None = None) -> str:
    url = f"{BASE_URL}/{action}"
    if not params:
        return url

    query = urlencode(params, quote_via=quote)
    return f"{url}?{query}"


def show_task_url(uid: str) -> str:
    return _url("showtask", {"uid": uid})


def show_list_url(name: str) -> str:
    return _url("showlist", {"name": name})


def search_url(text: str) -> str:
    return _url("search", {"text": text})


def add_task_url(
    *,
    title: str,
    notes: str | None,
    list_name: str,
    due_date: date | None,
    tags: list[str] | None,
    repeat: int | None,
    use_quick_entry: bool = False,
    success_url: str | None = None,
    error_url: str | None = None,
    cancel_url: str | None = None,
) -> str:
    params = {"task": title}

    if notes is not None:
        params["note"] = notes
    params["forlist"] = list_name
    if due_date is not None:
        params["due"] = due_date.isoformat()
    if tags:
        params["tags"] = ",".join(tags)
    if repeat is not None:
        params["repeat"] = str(repeat)
    params["ignoredefaults"] = "1"
    if use_quick_entry:
        params["usequickentry"] = "1"

    callback_urls = {
        "x-success": success_url,
        "x-error": error_url,
        "x-cancel": cancel_url,
    }
    for name, callback_url in callback_urls.items():
        if callback_url is not None:
            params[name] = callback_url
    if any(callback_url is not None for callback_url in callback_urls.values()):
        params["x-source"] = "2Do Tools"

    return _url("add", params)


def complete_task_url(
    *,
    uid: str,
    success_url: str,
    error_url: str,
    cancel_url: str,
) -> str:
    if not uid.strip() or "," in uid:
        raise ValueError("completion requires exactly one task UID")

    return _url(
        "completetasks",
        {
            "uids": uid,
            "x-success": success_url,
            "x-error": error_url,
            "x-cancel": cancel_url,
            "x-source": "2Do Tools",
        },
    )


def open_url(url: str) -> None:
    subprocess.run(["open", url], check=True)
