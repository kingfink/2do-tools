import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

import _2do_tools.callback_helper as callback_helper


def test_background_callback_url_wraps_loopback_url() -> None:
    assert (
        callback_helper.background_callback_url("http://127.0.0.1:54321/callback/token/success")
        == "twodo-tools-callback://127.0.0.1:54321/callback/token/success"
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:54321/callback/token/success",
        "http://localhost:54321/callback/token/success",
        "http://example.com/callback/token/success",
    ],
)
def test_background_callback_url_rejects_non_loopback_http_urls(url: str) -> None:
    with pytest.raises(ValueError, match="loopback HTTP"):
        callback_helper.background_callback_url(url)


def test_ensure_callback_helper_builds_hidden_url_handler(tmp_path: Path) -> None:
    app_path = tmp_path / "2Do Tools Callback.app"
    calls: list[list[str]] = []

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args[0] == "osacompile":
            output_path = Path(args[args.index("-o") + 1])
            contents_dir = output_path / "Contents"
            contents_dir.mkdir(parents=True)
            with (contents_dir / "Info.plist").open("wb") as file:
                plistlib.dump(
                    {"NSCameraUsageDescription": "Unused generic description."},
                    file,
                )
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    callback_helper.ensure_callback_helper(app_path=app_path, run_fn=run)

    with (app_path / "Contents" / "Info.plist").open("rb") as file:
        info = plistlib.load(file)

    assert info["CFBundleIdentifier"] == "com.kingfink.2do-tools.callback"
    assert info["LSUIElement"] is True
    assert info["TwoDoToolsCallbackHelperVersion"] == callback_helper.CALLBACK_HELPER_VERSION
    assert info["CFBundleURLTypes"] == [
        {
            "CFBundleURLName": "com.kingfink.2do-tools.callback",
            "CFBundleURLSchemes": ["twodo-tools-callback"],
        }
    ]
    assert "NSCameraUsageDescription" not in info
    assert calls[0][:3] == ["osacompile", "-o", str(app_path)]
    assert callback_helper.CALLBACK_HELPER_SCRIPT in calls[0]
    assert calls[1] == [callback_helper.LSREGISTER_PATH, "-f", str(app_path)]


def test_ensure_callback_helper_reuses_current_app(tmp_path: Path) -> None:
    app_path = tmp_path / "2Do Tools Callback.app"
    contents_dir = app_path / "Contents"
    contents_dir.mkdir(parents=True)
    with (contents_dir / "Info.plist").open("wb") as file:
        plistlib.dump(
            {
                "CFBundleIdentifier": "com.kingfink.2do-tools.callback",
                "LSUIElement": True,
                "TwoDoToolsCallbackHelperVersion": callback_helper.CALLBACK_HELPER_VERSION,
                "CFBundleURLTypes": [
                    {
                        "CFBundleURLName": "com.kingfink.2do-tools.callback",
                        "CFBundleURLSchemes": ["twodo-tools-callback"],
                    }
                ],
            },
            file,
        )
    calls: list[list[str]] = []

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    callback_helper.ensure_callback_helper(app_path=app_path, run_fn=run)

    assert calls == [[callback_helper.LSREGISTER_PATH, "-f", str(app_path)]]


@pytest.mark.skipif(sys.platform != "darwin", reason="AppleScript is macOS-only")
def test_callback_helper_script_compiles(tmp_path: Path) -> None:
    subprocess.run(
        [
            "osacompile",
            "-o",
            str(tmp_path / "Callback.app"),
            "-e",
            callback_helper.CALLBACK_HELPER_SCRIPT,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
