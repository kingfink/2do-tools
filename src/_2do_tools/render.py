"""Terminal rendering helpers for the ``2do`` CLI.

Pure presentation: OSC 8 hyperlinks, ellipsis truncation, and width-aware
table alignment. Kept separate from ``cli`` so it can be unit tested without
argument parsing or I/O.
"""

import shutil
from dataclasses import dataclass

_OSC8_START = "\x1b]8;;"
_STRING_TERMINATOR = "\x1b\\"
_ELLIPSIS = "..."


def terminal_width(default: int = 80) -> int:
    """Return the terminal width, falling back to ``default`` when unknown."""
    return shutil.get_terminal_size((default, 24)).columns


def truncate(text: str, width: int) -> str:
    """Shorten ``text`` to ``width`` columns, ending with an ellipsis."""
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width <= len(_ELLIPSIS):
        return _ELLIPSIS[:width]
    return text[: width - len(_ELLIPSIS)] + _ELLIPSIS


def hyperlink(text: str, url: str) -> str:
    """Wrap ``text`` in an OSC 8 hyperlink pointing at ``url``."""
    return f"{_OSC8_START}{url}{_STRING_TERMINATOR}{text}{_OSC8_START}{_STRING_TERMINATOR}"


@dataclass(frozen=True)
class Cell:
    """A single table cell: visible ``text`` plus an optional link ``url``."""

    text: str
    url: str | None = None


def render_table(headers: list[str], rows: list[list[Cell]], *, hyperlinks: bool) -> list[str]:
    """Render an aligned table, padding columns by visible width.

    Hyperlink escape sequences are emitted only when ``hyperlinks`` is true and
    a cell carries a ``url``; padding is always computed from the visible text
    so trailing columns stay aligned regardless of escape codes.
    """
    widths = [
        max(len(headers[index]), *(len(row[index].text) for row in rows)) if rows else len(header)
        for index, header in enumerate(headers)
    ]

    return [
        _render_row([Cell(header) for header in headers], widths, hyperlinks=False),
        _render_row([Cell("-" * width) for width in widths], widths, hyperlinks=False),
        *(_render_row(row, widths, hyperlinks=hyperlinks) for row in rows),
    ]


def _render_row(cells: list[Cell], widths: list[int], *, hyperlinks: bool) -> str:
    rendered = []
    for cell, width in zip(cells, widths, strict=True):
        padding = " " * max(0, width - len(cell.text))
        if hyperlinks and cell.url:
            rendered.append(hyperlink(cell.text, cell.url) + padding)
        else:
            rendered.append(cell.text + padding)
    return "  ".join(rendered).rstrip()
