The test suite is written in pytest. Below are some things to keep in my mind when writing tests. For examples of good and thorough tests, see `tests\ui\timelines\test_marker_timeline_ui.py`.  Older modules should be refactored at some point to follow the guidelines below.
## How to simulate interaction with the UI?
- The `user_actions` fixture can be used to trigger actions on the UI. This is equivalent to pressing buttons on the UI. We should also check that the actions are available in the UI where we expect them.
- The `tilia_state` fixture can be used to make certain changes to state simulating user input (e.g. `tilia_state.current_time = 10`).
- The `press_key` and `type_string` functions can be used to simulate keyboard input.

### Modal dialogs
Unfortunately, we can't simulate input to modal dialogs, as they block execution. To work around that, we can:
- Mock methods of the modal dialogs (e.g. `QInputDialog.getInt`). There are utility functions that do that in some cases (e.g. `tests.utils.patch_file_dialog`)
- If the dialog is called in response to a `Get` request, the `Serve` context manager can be used to mock the return value of the request. E.g.:

```python
with Serve(Get.FROM_USER_INT, (True, 150)):
    user_actions.execute("timeline_height_set")
```

We should prefer the first option as it makes the test cover more code, but the second is more resilient to changes in implementation details.

Some known modal dialogs:
- `QInputDialog`
- `QMenu used as context menus`
- `QColorDialog`

An alternative to mocking modal dialogs would be appreciated. Experiments with mocking modal dialogs (to date) have not worked.

## How to simulate interaction with timelines?
We shouldn't use methods of the `Timeline` or the `TimelineUI` classes, but instead try to simulate user input. This makes for tests that are more resilient to changes in implementation. For instance, this:
```python
def test_me(tlui, marker_tlui):
    tlui.create_marker(0)
    assert len(marker_tlui) == 1
```

can be rewritten as:

```python
def test_me(marker_tlui, user_actions, tilia_state):
    tilia_state.current_time = 0
    user_action.execute("marker_add")
    assert not len(marker_tlui) == 1
```
You will find many examples of the former in the test suite, though. Refactors are welcome.

## How to test the right actions are available in the UI?
The `get_submenu`, `get_action` and `get_qaction` in the `tests.ui.utils` module should help.

## Test the backend or the frontend?
In my opinion, we should aim to test the backend behavior through the frontend, when possible. This way, we can be sure that both are functioning. Backend-specific tests can be useful for a particularly complex piece of logic or during development. Tests of the latter type should not be kept in the codebase, as they are usually coupled to implementation details and may be broken by refactors.
