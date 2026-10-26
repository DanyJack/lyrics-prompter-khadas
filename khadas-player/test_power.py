"""Power menu safety checks without requesting an actual shutdown."""
import io
from types import SimpleNamespace
from unittest.mock import Mock, patch
import subprocess
import unittest

import player
from usb_import import ImportScreen


KEYS = SimpleNamespace(KEY_Escape=1, KEY_Page_Up=2, KEY_Left=3, KEY_Up=4,
                       KEY_Page_Down=5, KEY_Right=6, KEY_Down=7,
                       KEY_Return=8, KEY_KP_Enter=9, KEY_space=10, KEY_F12=11)


class PowerScreenTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(player, "Gdk", KEYS, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.screen = player.PowerScreen.__new__(player.PowerScreen)
        self.screen.selection = 0
        self.screen.pressed = set()
        self.screen.busy = False
        self.screen.error = ""
        self.screen.redraw = Mock()
        self.screen.cancel = Mock()

    def press(self, key):
        self.screen.on_key(None, SimpleNamespace(keyval=key))

    def release(self, key):
        self.screen.on_release(None, SimpleNamespace(keyval=key))

    def test_choice_requires_select_and_ignores_key_repeat(self):
        with patch.object(self.screen, "confirm") as confirm:
            self.press(KEYS.KEY_Right)
            self.assertEqual(self.screen.selection, 1)
            self.press(KEYS.KEY_Right)
            self.assertEqual(self.screen.selection, 1)
            confirm.assert_not_called()
            self.release(KEYS.KEY_Right)
            self.press(KEYS.KEY_Return)
            confirm.assert_called_once()

    def test_cancel_never_requests_power_action(self):
        with patch.object(player.subprocess, "run") as run:
            self.screen.confirm()
        self.screen.cancel.assert_called_once()
        run.assert_not_called()

    def test_shutdown_uses_poweroff_only(self):
        self.screen.selection = 1
        self.screen.box = SimpleNamespace(get_children=lambda: [],
                                          pack_start=Mock(), show_all=Mock())
        with patch.object(player, "Gtk", SimpleNamespace(Label=lambda **kwargs: kwargs), create=True), \
             patch.object(player.subprocess, "run") as run:
            self.screen.confirm()
        self.assertEqual(run.call_args.args[0], ["systemctl", "--no-ask-password", "poweroff"])
        self.assertTrue(self.screen.busy)

    def test_failed_power_action_preserves_selection(self):
        self.screen.selection = 1
        with patch.object(player.subprocess, "run", side_effect=subprocess.CalledProcessError(
            1, "systemctl", stderr="Access denied")), patch("sys.stderr", new_callable=io.StringIO) as stderr:
            self.screen.confirm()
        self.assertEqual(self.screen.selection, 1)
        self.assertIn("non riuscita", self.screen.error)
        self.assertIn("Access denied", stderr.getvalue())
        self.screen.redraw.assert_called_once()


class PowerShortcutTests(unittest.TestCase):
    def test_import_screen_accepts_shortcut_when_idle(self):
        screen = ImportScreen.__new__(ImportScreen)
        screen.api = SimpleNamespace(Gdk=KEYS, PowerScreen=Mock())
        screen.busy = False
        screen.window = object()
        screen.on_key(None, SimpleNamespace(keyval=KEYS.KEY_F12))
        screen.api.PowerScreen.assert_called_once_with(screen.window)

    def test_import_screen_ignores_shortcut_during_copy(self):
        screen = ImportScreen.__new__(ImportScreen)
        screen.api = SimpleNamespace(Gdk=KEYS, PowerScreen=Mock())
        screen.busy = True
        screen.on_key(None, SimpleNamespace(keyval=KEYS.KEY_F12))
        screen.api.PowerScreen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
