from unittest.mock import MagicMock, call

import pytest

from tilia import events
from tilia.events import Event, unsubscribe_from_all
from tilia.timelines.state_actions import StateAction
from tilia.undo_manager import UndoManager


@pytest.fixture
def um():
    _um = UndoManager()
    yield _um
    unsubscribe_from_all(_um)


class TestUndoManager:

    def test_constructor(self):
        um = UndoManager()
        unsubscribe_from_all(um)

    def test_record_state(self, um):
        can_restore_state_mock = MagicMock()
        events.post(Event.RECORD_STATE, can_restore_state_mock, StateAction.DUMMY_ACTION1)

        assert um.stack[-1][0] == can_restore_state_mock
        assert um.stack[-1][1] == can_restore_state_mock.get_state()
        assert um.stack[-1][2] == StateAction.FILE_LOAD

    def test_record_two_states(self, um):
        can_restore_state_mock = MagicMock()
        events.post(Event.RECORD_STATE, can_restore_state_mock, StateAction.DUMMY_ACTION1)
        events.post(Event.RECORD_STATE, can_restore_state_mock, StateAction.DUMMY_ACTION2)

        assert um.stack[-1][0] == can_restore_state_mock
        assert um.stack[-1][1] == can_restore_state_mock.get_state()
        assert um.stack[-1][2] == StateAction.DUMMY_ACTION1

    def test_record_successive_no_repeat_states_with_same_id(self, um):
        can_restore_state_mock = MagicMock()
        events.post(Event.RECORD_STATE, can_restore_state_mock, StateAction.DUMMY_ACTION1, no_repeat=True, repeat_identifier=':||')
        events.post(Event.RECORD_STATE, can_restore_state_mock, StateAction.DUMMY_ACTION1, no_repeat=True, repeat_identifier=':||')
        um.save_current_if_necessary()

        assert len(um.stack) == 2
        assert um.stack[-1]['state'] == 'state2'

    def test_record_successive_no_repeat_states_with_different_ids(self, um):
        can_restore_state_mock = MagicMock()
        events.post(Event.RECORD_STATE, can_restore_state_mock, StateAction.DUMMY_ACTION1, no_repeat=True,
                    repeat_identifier=':||')
        events.post(Event.RECORD_STATE, can_restore_state_mock, StateAction.DUMMY_ACTION1, no_repeat=True,
                    repeat_identifier='%')
        um.save_current_if_necessary()

        assert len(um.stack) == 3

    def test_undo(self, post_mock: MagicMock, um):
        um.record('state1', 'action1')


    def test_undo(self, um):
        timeline = MagicMock()

        events.post(Event.RECORD_STATE, timeline, StateAction.DUMMY_ACTION1)
        events.post(Event.RECORD_STATE, timeline, StateAction.DUMMY_ACTION2)

        um.undo()

        assert um.stack == [
            (timeline, timeline.get_state(), StateAction.FILE_LOAD),
            (timeline, timeline.get_state(), StateAction.DUMMY_ACTION1),
            (timeline, timeline.get_state(), StateAction.DUMMY_ACTION2)
        ]

        timeline.restore_state.assert_called_with(timeline.get_state(), StateAction.DUMMY_ACTION2)

