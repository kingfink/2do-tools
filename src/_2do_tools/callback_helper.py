import plistlib
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .storage import app_support_dir

CALLBACK_SCHEME = "twodo-tools-callback"
CALLBACK_HELPER_VERSION = "2"
CALLBACK_HELPER_BUNDLE_ID = "com.kingfink.2do-tools.callback"
CALLBACK_HELPER_APP_NAME = "2Do Tools Callback.app"
LSREGISTER_PATH = (
    "/System/Library/Frameworks/CoreServices.framework/"
    "Frameworks/LaunchServices.framework/Support/lsregister"
)

CALLBACK_HELPER_SCRIPT = "\n".join(
    [
        "on run",
        "end run",
        "",
        "on open location callbackUrl",
        '    set schemePrefix to "twodo-tools-callback://"',
        '    set loopbackPrefix to schemePrefix & "127.0.0.1:"',
        "",
        "    if callbackUrl does not start with loopbackPrefix then",
        "        return",
        "    end if",
        "",
        "    set callbackSuffix to text ((length of schemePrefix) + 1) thru -1 of callbackUrl",
        '    set pathOffset to offset of "/" in callbackSuffix',
        "    if pathOffset is 0 then",
        "        return",
        "    end if",
        "",
        "    set callbackPath to text pathOffset thru -1 of callbackSuffix",
        '    if callbackPath does not start with "/callback/" then',
        "        return",
        "    end if",
        "",
        '    set loopbackUrl to "http://" & callbackSuffix',
        "    try",
        '        do shell script "/usr/bin/curl --silent --show-error --fail --max-time 5 " & '
        'quoted form of loopbackUrl & " >/dev/null 2>&1"',
        "    end try",
        "end open location",
    ]
)


def background_callback_url(loopback_url: str) -> str:
    parsed = urlsplit(loopback_url)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.port is None
        or not parsed.path.startswith("/callback/")
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("background callbacks require a tokenized loopback HTTP URL")

    return urlunsplit(
        (
            CALLBACK_SCHEME,
            parsed.netloc,
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )


def ensure_callback_helper(
    *,
    app_path: Path | None = None,
    run_fn: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    helper_path = app_path or app_support_dir() / CALLBACK_HELPER_APP_NAME
    if not _helper_is_current(helper_path):
        _build_callback_helper(helper_path, run_fn=run_fn)

    run_fn(
        [LSREGISTER_PATH, "-f", str(helper_path)],
        check=True,
        capture_output=True,
        text=True,
    )


def _helper_is_current(app_path: Path) -> bool:
    try:
        with (app_path / "Contents" / "Info.plist").open("rb") as file:
            info = plistlib.load(file)
    except (OSError, plistlib.InvalidFileException):
        return False

    return (
        info.get("CFBundleIdentifier") == CALLBACK_HELPER_BUNDLE_ID
        and info.get("LSUIElement") is True
        and info.get("TwoDoToolsCallbackHelperVersion") == CALLBACK_HELPER_VERSION
        and info.get("CFBundleURLTypes") == _callback_url_types()
    )


def _build_callback_helper(
    app_path: Path,
    *,
    run_fn: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    app_path.parent.mkdir(parents=True, exist_ok=True)
    if app_path.exists():
        if app_path.is_dir():
            shutil.rmtree(app_path)
        else:
            app_path.unlink()

    run_fn(
        [
            "osacompile",
            "-o",
            str(app_path),
            "-e",
            CALLBACK_HELPER_SCRIPT,
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    info_path = app_path / "Contents" / "Info.plist"
    with info_path.open("rb") as file:
        info = plistlib.load(file)

    for key in list(info):
        if key.startswith("NS") and key.endswith("UsageDescription"):
            del info[key]

    info.update(
        {
            "CFBundleIdentifier": CALLBACK_HELPER_BUNDLE_ID,
            "CFBundleName": "2Do Tools Callback",
            "CFBundleDisplayName": "2Do Tools Callback",
            "CFBundleURLTypes": _callback_url_types(),
            "LSUIElement": True,
            "TwoDoToolsCallbackHelperVersion": CALLBACK_HELPER_VERSION,
        }
    )
    with info_path.open("wb") as file:
        plistlib.dump(info, file)


def _callback_url_types() -> list[dict[str, object]]:
    return [
        {
            "CFBundleURLName": CALLBACK_HELPER_BUNDLE_ID,
            "CFBundleURLSchemes": [CALLBACK_SCHEME],
        }
    ]
