import subprocess
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


def open_url(url: str) -> None:
    subprocess.run(["open", url], check=True)
