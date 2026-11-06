"""TimelineView catches the arrows itself and passes them on to each timeline
kind; other tests post the requests it sends directly. These press the keys on
a hierarchy timeline, which takes every arrow. The keys go to the timeline's
view, which is where they arrive once the timeline has been clicked."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from tilia.ui import commands

NONE = Qt.KeyboardModifier.NoModifier
CTRL = Qt.KeyboardModifier.ControlModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier


def unit(tlui, start, level):
    return next(
        u for u in tlui if u.get_data("start") == start and u.get_data("level") == level
    )


@pytest.fixture
def family(hierarchy_tlui):
    """A parent at level 2, from 0 to 2, with children from 0 to 1 and 1 to 2."""
    commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)
    commands.execute("timeline.hierarchy.add", start=1, end=2, level=1)
    hierarchy_tlui.select_element(hierarchy_tlui[0])
    hierarchy_tlui.select_element(hierarchy_tlui[1])
    commands.execute("timeline.hierarchy.group")
    hierarchy_tlui.deselect_all_elements()
    return hierarchy_tlui


@pytest.mark.parametrize(
    "key,modifier,selected,to_select",
    [
        (Qt.Key.Key_Right, NONE, (0, 1), (1, 1)),
        (Qt.Key.Key_Left, NONE, (1, 1), (0, 1)),
        (Qt.Key.Key_Up, NONE, (0, 1), (0, 2)),
        (Qt.Key.Key_Down, NONE, (0, 2), (0, 1)),
        # Ctrl only changes the vertical arrows; other modifiers change none.
        (Qt.Key.Key_Left, CTRL, (1, 1), (0, 1)),
        (Qt.Key.Key_Right, SHIFT, (0, 1), (1, 1)),
        (Qt.Key.Key_Down, SHIFT, (0, 2), (0, 1)),
    ],
)
def test_arrow_moves_the_selection(family, key, modifier, selected, to_select):
    family.select_element(unit(family, *selected))

    QTest.keyClick(family.view, key, modifier)

    assert family.selected_elements == [unit(family, *to_select)]


@pytest.mark.parametrize(
    "key,modifier,level,new_level",
    [
        (Qt.Key.Key_Up, CTRL, 1, 2),
        (Qt.Key.Key_Down, CTRL, 2, 1),
        # Ctrl with other modifiers still counts as Ctrl.
        (Qt.Key.Key_Up, CTRL | SHIFT, 1, 2),
    ],
)
def test_ctrl_arrow_changes_the_level(hierarchy_tlui, key, modifier, level, new_level):
    commands.execute("timeline.hierarchy.add", start=0, end=1, level=level)
    hierarchy_tlui.select_element(hierarchy_tlui[0])

    QTest.keyClick(hierarchy_tlui.view, key, modifier)

    assert hierarchy_tlui[0].get_data("level") == new_level


def test_other_keys_do_nothing(family):
    first_child = unit(family, 0, 1)
    family.select_element(first_child)

    QTest.keyClick(family.view, Qt.Key.Key_A)
    QTest.keyClick(family.view, Qt.Key.Key_PageUp, CTRL)

    assert family.selected_elements == [first_child]
    assert sorted(u.get_data("level") for u in family) == [1, 1, 2]
