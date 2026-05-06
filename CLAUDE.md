# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

TiLiA (TimeLine Annotator) is a PySide6 desktop GUI for creating and visualizing timeline-based annotations over audio/video/PDF. Python 3.10–3.12 (3.13 is flaky due to PySide dependencies).

## Environment

A virtual environment exists at `.venv`. Activate it before running any Python command (per `.windsurf/rules/virtualenv.md`).

## Common commands

```bash
# Install (editable) with dev extras and pre-commit hooks
pip install -e .
pip install --group dev
pre-commit install

# Run the app
tilia                       # Qt GUI
tilia --user-interface cli  # CLI (source-only, not in compiled builds)

# Tests (pytest-env auto-sets ENVIRONMENT=test and QT_QPA_PLATFORM=offscreen)
pytest                                                  # full suite
pytest tests/ui/timelines/marker/test_marker_timeline_ui.py    # one file
pytest tests/ui/timelines/marker/test_marker_timeline_ui.py::TestCreateDelete::test_create_at_selected_time  # one test
pytest -k marker                                        # by keyword
coverage run -m pytest && coverage report -m            # coverage

# Lint / format (black + ruff; run automatically via pre-commit)
ruff check
black .

# Build a standalone executable with Nuitka
pip install -e . --group build
python scripts/deploy.py <ref_name> <os_type>  # output in build/<os_type>/exe
```

Default pytest timeout is 10s (pytest-timeout). `ffmpeg` must be on PATH for audio export/convert features.

## Architecture

### Entry point and wiring

`tilia/__main__.py` → `tilia/boot.py::boot()` constructs the QApplication, then `setup_logic()` (builds `App` with `FileManager`, `Clipboard`, `UndoManager`, `QtAudioPlayer`), then `setup_ui()` (QtUI or CLI). The `App` class (`tilia/app.py`) owns the `Timelines` collection and coordinates file ops, media, undo, clipboard.

### Backend ↔ frontend split

Each timeline kind has **two parallel packages**: backend model under `tilia/timelines/<kind>/` and UI view under `tilia/ui/timelines/<kind>/`. Kinds are registered in `tilia/timelines/timeline_kinds.py` (`TimelineKind` enum: audiowave, beat, harmony, hierarchy, marker, pdf, score, slider; `range` is currently being added — see `.todo.md`). The UI side mirrors the backend structure closely; when adding or modifying a timeline, expect to touch both trees plus corresponding tests under `tests/timelines/<kind>/` and `tests/ui/timelines/<kind>/`.

Frontend constants and visual settings — paddings, margins, alignment options, fonts, color defaults — live under `tilia/ui/` (in the relevant UI module or as keys in `settings.py`), never under `tilia/timelines/<kind>/`. The backend is presentation-agnostic.

### Two communication systems (do not confuse them)

1. **Requests** (`tilia/requests/`): decoupled pub/sub between internal components. `Get` enum + `get()`/`serve()` for synchronous queries (including "ask the user" prompts via `Get.FROM_USER_*`); `Post` enum + `post()`/`listen()` for fire-and-forget events. Use this for component-to-component wiring.
2. **Commands** (`tilia/ui/commands.py`): the **only** mechanism for user-initiated actions (menu items, shortcuts, toolbar buttons). Register with dotted names (`file.open`, `timeline.component.copy`) via `commands.register(name, callback, text=..., shortcut=..., icon=...)` and invoke with `commands.execute(name, ...)`. The docstring at the top of `commands.py` is authoritative on conventions.

Rule of thumb: anything a user could trigger is a command; anything only the code triggers is a request.

### Other key modules

- `tilia/file/` — `.tla` file format (`TiliaFile` dataclass), save/load, autosave.
- `tilia/media/` — Qt-based audio/video players; YouTube player embeds HTML/CSS in `media/player/`.
- `tilia/parsers/` — CSV (`parsers/csv/<kind>.py`) and MusicXML (`parsers/score/musicxml.py`) import. `parsers/__init__.py::get_import_function` dispatches by `(TimelineKind, by={"time"|"measure"})`.
- `tilia/ui/qtui.py` — `QtUI` and `TiliaMainWindow`; builds menubar, toolbars, dock widgets.
- `tilia/ui/cli/` — click-style CLI exposing a subset of features.
- `tilia/undo_manager.py` — app-state snapshots; `PauseUndoManager` context manager suppresses recording.

## Code style

- **Type hints required** in production code (`tilia/`). Annotate all function/method parameters, return types, and instance attributes whose types aren't obvious from initialization. Tests (`tests/`) do not need type hints.
- **Use `ORDERING_ATTRS` / natural `__lt__`** when sorting timeline components. Each `TimelineComponent` subclass declares `ORDERING_ATTRS` (e.g. `Range = ("start", "row_id")`); `sorted(components)` already orders correctly. Adding `key=lambda c: c.start` is at best redundant and at worst hides the secondary tiebreaker.
- **Don't `raise` for stale-UI references or internal-invariant violations** on paths reachable in production. Use `tilia.log.logger.error(...)` + early return. The default console threshold is `ERROR`; `WARNING` only surfaces under `dev.log_requests=True`, so `error` is the level that actually reaches users.

## Commit hygiene

Split unrelated changes into their own commits, even if they were touched while building a feature: codebase-wide refactors (`type(Foo)` → `type[Foo]`), deprecation removals, mechanical fixes (block-signal patterns), `Post.*` additions consumed elsewhere, and doc/test-pattern updates that emerged from the work belong on their own commits with explanatory messages. Reviewers want to evaluate each rationale separately.

When you discover a pre-existing bug in code unrelated to the feature you're working on, prompt for opening a separate PR off `main`/`dev` rather than burying the fix in the feature branch.

## Testing conventions

Read `TESTING.md` first. Key points:

- **Simulate users, don't call internals.** Use `commands.execute(...)` everywhere possible — including test *setup*, not just the action under test. Calling `tlui.create_marker(0)` directly is the old style; `commands.execute("timeline.marker.add")` is preferred even when it's not the thing being tested. Older tests violate this; refactors are welcome.
- **Fixtures** in `tests/conftest.py` + per-kind `fixtures.py` files (registered via `pytest_plugins` in the root conftest). Common: `tilia_state`, `user_actions`, `marker_tlui`, `beat_tlui`, etc.
- **Modal dialogs block execution** and cannot be driven directly. Two workarounds:
  - Mock the Qt method (e.g. `QInputDialog.getInt`); helpers like `tests.utils.patch_file_dialog` exist.
  - If the dialog is triggered by a `Get.FROM_USER_*` request, use `Serve(Get.FROM_USER_INT, (True, 150))` as a context manager to short-circuit it. Prefer mocking the dialog when feasible (covers more code).
- **Menu/action presence checks**: use `get_submenu`, `get_command_action`, `get_qaction`, `get_command_names` from `tests/utils.py`. `CommandQAction` carries a `command_name` attribute that makes lookups by command possible.
- **Context menus: test both presence AND behavior.** Instantiate the context menu class directly to check which actions are present. Then write a separate test that actually triggers each action through the menu and asserts the outcome. Don't stop at presence checks.
- **Undo/redo: use `undoable()` for all user-initiated state changes.** Wrap the command call in `with undoable():` — this verifies the undo restores state exactly and redo returns to the post-action state. Every command that modifies state should have at least one `undoable()` test.
- **Drag: test at integration level only.** Use `drag_mouse_in_timeline_view(x, y)` after clicking the drag target. Don't test drag callbacks directly. Cover: normal drag, drag beyond limits (clamped), drag resulting in a state change (e.g. row change for vertical drag).
- **Keyboard navigation: simulate key presses.** Use `press_key(Qt.Key.Key_Up)` etc., not direct method calls. This exercises the full wiring from keypress event through to the outcome.
- **Settings: write explicit tests** when behavior depends on a settings value (e.g. height, color, alpha). Change the setting, trigger the relevant action/update, assert the visual property changed. Settings reads and writes are routed to a test QSettings store via the `use_test_settings` fixture (auto-applied through `qtui`), so don't write per-test save/restore fixtures — set the values you depend on explicitly inside each test.
- **Interact helpers**: Put per-kind click helpers in `tests/ui/timelines/<kind>/interact.py` (e.g. `click_range_ui(element, button, modifier)`). These should compute coordinates from element data (time → X, row → Y) so test bodies stay readable. Import them at the top of the test file.
- **File layout for a new timeline kind:**
  - `tests/ui/timelines/<kind>/test_<kind>_timeline_ui.py` — primary test file; no separate element-level file needed unless the element has genuinely complex standalone behavior.
  - `tests/ui/timelines/<kind>/interact.py` — click/drag helpers.
  - `tests/parsers/csv/test_<kind>_from_csv.py` — CSV parser tests (separate from UI tests).
- Prefer end-to-end (backend-through-frontend) tests; backend-only tests are appropriate for complex pure logic but shouldn't be kept if they're coupled to implementation details.
- **Gold reference**: `tests/ui/timelines/marker/test_marker_timeline_ui.py`. When uncertain about structure or depth, match that file.

## Debugging GUI-only bugs

When a bug is reported in the running app but the test suite is green, agents can't drive the desktop GUI themselves. The fallback is to instrument the suspect code path and ask the user to reproduce live:

- Add `print("[FEATURE-DEBUG] ...", flush=True)` lines at the points where the data flow is unclear (e.g. inside the command handler, around `set_component_data` calls, in `Post.*` listeners that might overwrite state). Use a unique tag per investigation so the prints are easy to grep and remove.
- Ask the user to run the exact action in TiLiA from a terminal and paste the tagged lines back. State which inspector / view / save-load step you want them to perform.
- Once the cause is identified, remove the prints in the same commit as the fix — don't ship debug output.
- Prefer this over speculation when tests cover the symptom but it still reproduces in the app: there's almost always a step in the live path (signal handler, focus change, dialog) that the test harness doesn't exercise.

## CI

`.github/workflows/run-tests.yml` runs ruff + pytest on Linux/macOS/Windows across Python 3.10–3.13 (excluding Windows+3.13). Linting is `continue-on-error: true` — ruff failures won't fail CI, but they should still be fixed. After tests, CI boots the GUI and CLI for 10s each as a smoke check.
