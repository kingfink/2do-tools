from _2do_tools import render


def test_hyperlink_wraps_text_in_osc8_sequence() -> None:
    result = render.hyperlink("Buy milk", "twodo://task/1")

    assert result == "\x1b]8;;twodo://task/1\x1b\\Buy milk\x1b]8;;\x1b\\"


def test_truncate_leaves_short_text_unchanged() -> None:
    assert render.truncate("Buy milk", 20) == "Buy milk"


def test_truncate_adds_ellipsis_when_too_long() -> None:
    result = render.truncate("Buy a lot of milk", 10)

    assert result == "Buy a l..."
    assert len(result) == 10


def test_render_table_aligns_columns_on_visible_width() -> None:
    rows = [
        [
            render.Cell("[ ]"),
            render.Cell("Inbox"),
            render.Cell("Active task"),
            render.Cell(""),
        ]
    ]

    lines = render.render_table(["Status", "List", "Task", "Due"], rows, hyperlinks=False)

    assert lines == [
        "Status  List   Task         Due",
        "------  -----  -----------  ---",
        "[ ]     Inbox  Active task",
    ]


def test_render_table_links_cell_and_keeps_alignment() -> None:
    rows = [
        [
            render.Cell("[ ]"),
            render.Cell("Inbox"),
            render.Cell("Task", url="twodo://t/1"),
            render.Cell("2026-06-05"),
        ]
    ]

    lines = render.render_table(["Status", "List", "Task", "Due"], rows, hyperlinks=True)

    # The visible title is hyperlinked, and the trailing Due column still aligns
    # because padding is computed from visible width, not the escape sequence.
    assert render.hyperlink("Task", "twodo://t/1") in lines[2]
    assert lines[2].endswith("2026-06-05")
