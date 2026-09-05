from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock
import tempfile
import unittest

import player
from test_player import package
from test_key_hold import Clock
from usb_import import discover_packages, USBSession, ImportScreen, udisks


class PackageSelectionTests(unittest.TestCase):
    def test_legacy_and_multiple_exports(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package(root)
            collection = root / 'LYRICS_PROMPTER'
            for name in ('Set acustico', 'Serata completa'):
                staging = root / name
                package(staging)
                (staging / 'LYRICS_PROMPTER').rename(collection / name)
            choices = discover_packages(root)
            self.assertEqual([name for name, _ in choices], ['Scaletta principale', 'Serata completa', 'Set acustico'])
            store = player.SetlistStore(root / 'cache', root / 'saved')
            active = store.import_package(choices[0][1])
            self.assertFalse((active.root / 'Set acustico').exists())
            self.assertFalse((active.root / 'Serata completa').exists())
            store.close()

    def test_only_selected_package_is_validated_and_error_keeps_old_list(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            good, bad = root / 'good', root / 'bad'
            package(good)
            package(bad, corrupt=True)
            store = player.SetlistStore(root / 'cache', root / 'saved')
            old = store.import_package(good / 'LYRICS_PROMPTER')
            with self.assertRaises(player.ImportErrorMessage):
                store.import_package(bad / 'LYRICS_PROMPTER')
            self.assertIs(store.active, old)
            self.assertEqual(player.validate_package(old.root).songs, old.songs)
            self.assertTrue(store.has_saved_list())
            store.close()

    def test_invalid_json_and_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package(root)
            source = root / 'LYRICS_PROMPTER'
            store = player.SetlistStore(root / 'cache', root / 'saved')
            (source / 'manifest.json').write_bytes(b'\xff')
            self.assertEqual(len(discover_packages(root)), 1)
            with self.assertRaises(player.ImportErrorMessage):
                store.import_package(source)
            (source / 'songs/outside').symlink_to(root)
            with self.assertRaises(player.ImportErrorMessage):
                store.import_package(source)
            store.close()

    def test_mount_is_readonly_noninteractive(self):
        with patch('usb_import.subprocess.run', return_value=SimpleNamespace(returncode=0)) as run:
            udisks('mount', '/dev/sda1')
            args = run.call_args.args[0]
            self.assertIn('ro,nosuid,nodev,noexec', args)
            self.assertIn('--no-user-interaction', args)

    def test_unmount_failure_is_not_reported_as_safe(self):
        session = USBSession()
        session.owned.add('/dev/sda1')
        with patch('usb_import.udisks', side_effect=OSError('busy')):
            self.assertEqual(session.close(), 'busy')
        self.assertIn('/dev/sda1', session.owned)
        with patch('usb_import.udisks'):
            self.assertEqual(session.close(), '')
        self.assertFalse(session.owned)

    def test_cancel_restores_same_navigation(self):
        screen = ImportScreen.__new__(ImportScreen)
        nav = object()
        screen.parent = SimpleNamespace(navigation=nav, redraw=Mock(), window=Mock())
        screen.result = None
        screen.poll_timer = None
        screen.window = Mock()
        screen.finish()
        self.assertIs(screen.parent.navigation, nav)
        screen.parent.window.present.assert_called_once()

    def test_error_allows_selecting_another_package(self):
        screen = ImportScreen.__new__(ImportScreen)
        screen.show = Mock()
        screen.choices = [('good', Path('good')), ('bad', Path('bad'))]
        screen.imported(None, player.ImportErrorMessage('damaged'))
        self.assertEqual(screen.state, 'error')
        self.assertEqual(len(screen.choices), 2)


class SelectHoldTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.keys = SimpleNamespace(KEY_Escape=9, KEY_Page_Up=10, KEY_Left=11, KEY_Up=12,
                                    KEY_Page_Down=13, KEY_Right=14, KEY_Down=15,
                                    KEY_Return=16, KEY_KP_Enter=17, KEY_space=18,
                                    keyval_name=str)
        for name, value in [('GLib', self.clock), ('Gdk', self.keys)]:
            patcher = patch.object(player, name, value, create=True)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.ui = player.KhadasPlayer.__new__(player.KhadasPlayer)
        self.ui.navigation = player.Navigation(player.Setlist(Path('.'), None, (player.Song('1', 'one', '', ()),)))
        self.ui.held_navigation_key = self.ui.held_menu_page = self.ui.hold_timer = None
        self.ui.select_key = self.ui.select_timer = None
        self.ui.redraw = Mock()
        self.ui.window = Mock()
        self.ui.store = Mock()

    def press(self):
        self.ui.on_key(None, SimpleNamespace(keyval=16))

    def release(self):
        self.ui.on_key_release(None, SimpleNamespace(keyval=16))

    def test_short_select_opens_and_returns_to_menu(self):
        self.press()
        self.clock.advance(100)
        self.release()
        self.assertFalse(self.ui.navigation.in_menu)
        self.press()
        self.clock.advance(1000)
        self.release()
        self.assertTrue(self.ui.navigation.in_menu)
        self.assertFalse(self.clock.pending)

    def test_hold_opens_import_once_without_opening_song(self):
        with patch('usb_import.ImportScreen') as screen:
            self.press()
            self.clock.advance(400)
            self.press()
            self.clock.advance(500)
            self.release()
            screen.assert_called_once()
            self.assertTrue(self.ui.navigation.in_menu)

    def test_separate_select_clicks_do_not_reuse_old_timer(self):
        self.press()
        self.clock.advance(100)
        self.release()
        self.press()
        self.release()
        with patch('usb_import.ImportScreen') as screen:
            self.press()
            self.clock.advance(800)
            screen.assert_not_called()
            self.release()
        self.assertFalse(self.clock.pending)
