The test suite is written in pytest. Below are some things to keep in my mind when writing tests. For examples of good and thorough tests, see `tests\ui\timelines\test_marker_timeline_ui.py`.  Older modules should be refactored at some point to follow the guidelines below.
## Pre-requisites
`pip install --group testing`
## How to simulate interaction with the UI?
- The `user_actions` fixture can be used to trigger actions on the UI. This is equivalent to pressing buttons on the UI. We should also check that the actions are available in the UI where we expect them.
- The `tilia_state` fixture can be used to make certain changes to state simulating user input (e.g. `tilia_state.duration = 10`.)
- The `press_key` and `type_string` functions can be used to simulate keyboard input.

### Modal dialogs
Unfortunately, we can't simulate input to modal dialogs, as they block execution. To work around that, we can:
- Mock methods of the modal dialogs (e.g. `QInputDialog.getInt`). There are utility functions that do that in some cases (e.g. `tests.utils.patch_file_dialog`)
- If the dialog is called in response to a `Get` request, the `Serve` context manager can be used to mock the return value of the request. E.g.:

```python
with Serve(Get.FROM_USER_INT, (True, 150)):
    commands.execute("timeline_height_set")
```

We should prefer the first option as it makes the test cover more code, but the second is more resilient to changes in implementation details.

Some known modal dialogs:
- `QInputDialog`
- `QMenu used as context menus`
- `QColorDialog`

An alternative to mocking modal dialogs would be appreciated. Experiments with mocking modal dialogs (to date) have not worked.

## How to simulate interaction with timelines?
We shouldn't use methods of the `Timeline` or the `TimelineUI` classes, but instead try to simulate user input or use commands. This makes for tests that are more resilient to changes in implementation. For instance, this:
```python
def test_me(tlui, marker_tlui):
    tlui.create_marker(0)
    assert len(marker_tlui) == 1
```

can be rewritten as:

```python
def test_me(marker_tlui):
    commands.execute("media.seek", 0)
    commands.execute("marker_add")
    assert not len(marker_tlui) == 1
```
You will find many examples of the former in the test suite, though. Refactors are welcome.

## Use helpers in `tests.utils`

Prefer existing helpers in `tests/utils.py` over inlining the same setup or assertion patterns. If you find yourself repeating a sequence across tests, add a helper rather than copy-pasting.

Commonly useful helpers:

- **`save_and_reopen(tmp_path)`** — save the current state, clear, and reopen. Use for save/load round-trip tests instead of inlining `file.save_as` + `file.new` + `file.open`. `save_tilia_to_tmp_path(tmp_path)` returns the saved path without reopening.
- **`undoable()`** (context manager) — wrap a `commands.execute(...)` call to assert undoing restores the prior state and redoing returns to the post-action state. Cover every state-changing command with at least one `undoable()` test.
- **`reloadable(save_path)`** (decorator) — same idea applied to a `checks()` function: runs checks, saves, reopens, runs checks again.
- **`load_local_media(path)`** / **`load_youtube_media(url)`** — patch the file dialog / URL prompt and run the corresponding `media.load.*` command.
- **`assert_timeline_ui_update(tlui, attr)`** (context manager) — spy on `update_<attr>` and assert it ran during the wrapped block.
- **Menu / command discovery:** `get_command_action(menu, command_name)`, `get_command_from_toolbar(tlui, command_name)`, `get_command_names(menu)`, `get_submenu(menu, name)`, `get_main_window_menu(qtui, name)`, `get_context_menu(tlui, x, y)`, `get_actions_in_menu(menu)`. `get_command_action` walks ribbon-style toolbars where commands are wrapped in `QWidgetAction` containers.
- **Modal-dialog patches** (in `tests.mock`): `patch_file_dialog`, `patch_ask_for_string_dialog` — context managers that drive modals, as covered in the modal-dialogs section above.

## Index timelines and UI elements directly

Index `*_tlui` and timeline collections directly: `range_tlui[0]`, not `list(range_tlui)[0]`. Likewise `len(range_tlui)` over `len(list(range_tlui))`. UI elements are kept sorted by their components' `ORDERING_ATTRS`, so positional indexing is well-defined.

Prefer UI-layer access over backend access in tests: `range_tlui[0].get_data("joined_right")` exercises the same path the user does. Drop into the backend (`.timeline`, `.rows`, `.components`) only when the data isn't reachable from the UI side.

## How to test the right actions are available in the UI?
The `get_submenu`, `get_action` and `get_qaction` in the `tests.ui.utils` module should help.

## Test the backend or the frontend?
In my opinion, we should aim to test the backend behavior through the frontend, when possible. This way, we can be sure that both are functioning. Backend-specific tests can be useful for a particularly complex piece of logic or during development. Tests of the latter type should not be kept in the codebase, as they are usually coupled to implementation details and may be broken by refactors.
