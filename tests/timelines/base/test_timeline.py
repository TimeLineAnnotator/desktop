from unittest.mock import patch

from tilia.timelines.base.timeline import Timeline


def test_ensure_timeline_ui_subclasses_is_only_called_once():
    # Subclasses were already loaded in previous tests, so we reset the flag
    Timeline.SUBCLASSES_ARE_LOADED = False
    with patch.object(
        Timeline,
        "ensure_subclasses_are_available",
        wraps=Timeline.ensure_subclasses_are_available,
    ) as wrapped:
        for _ in range(50):
            Timeline.subclasses()
        assert wrapped.call_count == 1
