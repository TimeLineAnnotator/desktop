from unittest.mock import patch

from tilia.ui.dialogs.crash import CrashDialog, CrashSupportDialog


class TestCrashDialog:
    def test_contact_support_opens_dialog(self):
        crash_dialog = CrashDialog("exception message")
        with patch("tilia.ui.dialogs.crash.CrashSupportDialog") as support_dialog:
            crash_dialog.help_button.click()
        support_dialog.assert_called_once()

    def test_crash_support_valid_email_sets_user(self):
        crash_support_dialog = CrashSupportDialog(None)
        crash_support_dialog.email_field.setText("a@valid.email")
        crash_support_dialog.name_field.setText("John Doe")

        with patch("sentry_sdk.set_user") as set_user:
            crash_support_dialog.button_box.accepted.emit()

        set_user.assert_called_with({"name": "John Doe", "email": "a@valid.email"})

    def test_crash_support_invalid_email_sets_user(self):
        crash_support_dialog = CrashSupportDialog(None)
        crash_support_dialog.email_field.setText("an invalid email")
        crash_support_dialog.name_field.setText("John Doe")

        with patch("sentry_sdk.set_user") as set_user:
            crash_support_dialog.button_box.accepted.emit()

        set_user.assert_called_with({"name": "John Doe", "email": ""})

    def test_crash_support_empty_fields(self):
        crash_support_dialog = CrashSupportDialog(None)
        crash_support_dialog.email_field.setText("")
        crash_support_dialog.name_field.setText("")

        with patch("sentry_sdk.set_user") as set_user:
            crash_support_dialog.button_box.accepted.emit()

        set_user.assert_not_called()

    def test_crash_support_remember(self):
        crash_support_dialog = CrashSupportDialog(None)
        crash_support_dialog.email_field.setText("an invalid email")
        crash_support_dialog.name_field.setText("John Doe")
        crash_support_dialog.remember.setChecked(True)

        with patch("tilia.settings.settings.set_user") as set_user:
            crash_support_dialog.button_box.accepted.emit()

        set_user.assert_called_once_with("", "John Doe")

    def test_crash_support_not_remember(self):
        crash_support_dialog = CrashSupportDialog(None)
        crash_support_dialog.email_field.setText("an invalid email")
        crash_support_dialog.name_field.setText("John Doe")
        crash_support_dialog.remember.setChecked(False)

        with patch("tilia.settings.settings.set_user") as set_user:
            crash_support_dialog.button_box.accepted.emit()

        set_user.assert_not_called()
