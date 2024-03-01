from tilia.ui.dialogs.basic import ask_yes_or_no


def confirm_delete_timeline(timeline_str: str) -> bool | None:
    return ask_yes_or_no(
        "Delete timeline",
        f"Are you sure you want to delete timeline {timeline_str}?",
    )


def confirm_clear_timeline(timeline_str: str) -> bool | None:
    return ask_yes_or_no(
        "Delete timeline",
        f"Are you sure you want to clear timeline {timeline_str}?",
    )


def confirm_clear_all_timelines() -> bool | None:
    return ask_yes_or_no(
        "Delete timeline",
        "Are you sure you want to clear ALL timelines?",
    )
