"""Deterministic button timing regressions, without a graphical display."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import player


class Clock:
    def __init__(self):
        self.now = 0
        self.counter = 0
        self.pending = {}

    def timeout_add(self, delay, callback, *args):
        self.counter += 1
        self.pending[self.counter] = (self.now + delay, callback, args)
        return self.counter

    def source_remove(self, source):
        del self.pending[source]

    def advance(self, milliseconds):
        end = self.now + milliseconds
        while self.pending:
            source = min(self.pending, key=lambda key: self.pending[key][0])
            due, callback, args = self.pending[source]
            if due > end:
                break
            self.now = due
            del self.pending[source]
            assert callback(*args) is False
        self.now = end


class HoldTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        mock_glib = patch.object(player, 'GLib', self.clock, create=True)
        mock_glib.start()
        self.addCleanup(mock_glib.stop)
        self.ui = player.KhadasPlayer.__new__(player.KhadasPlayer)
        songs = tuple(player.Song(str(i), str(i), '', ()) for i in range(80))
        self.ui.navigation = player.Navigation(player.Setlist(Path('.'), None, songs))
        self.ui.held_navigation_key = None
        self.ui.held_menu_page = None
        self.ui.hold_timer = None
        self.ui.redraw = lambda: None

    def release(self, key=1):
        self.ui.on_key_release(None, SimpleNamespace(keyval=key))

    def test_repeated_separate_clicks_never_jump(self):
        for _ in range(8):
            self.ui.start_navigation_hold(1, 1)
            self.clock.advance(100)
            self.release()
            self.clock.advance(100)
        self.assertEqual(self.ui.navigation.selection, 8)
        self.assertEqual(self.ui.navigation.menu_page, 0)
        self.assertFalse(self.clock.pending)

    def test_new_press_gets_full_hold_delay(self):
        self.ui.start_navigation_hold(1, 1)
        self.clock.advance(300)
        self.release()
        self.ui.start_navigation_hold(1, 1)
        self.clock.advance(350)  # Old timer would fire here.
        self.assertEqual(self.ui.navigation.selection, 2)
        self.clock.advance(300)
        self.assertEqual(self.ui.navigation.selection, player.MENU_PAGE_SIZE)
        self.release()

    def test_autorepeat_does_not_reset_hold(self):
        self.ui.start_navigation_hold(1, 1)
        for _ in range(6):
            self.clock.advance(100)
            self.ui.start_navigation_hold(1, 1)
        self.assertEqual(self.ui.navigation.selection, 1)
        self.clock.advance(50)
        self.assertEqual(self.ui.navigation.selection, player.MENU_PAGE_SIZE)
        self.release()

    def test_prev_hold_and_focus_loss(self):
        self.ui.navigation.selection = 45
        self.ui.start_navigation_hold(2, -1)
        self.clock.advance(650)
        self.assertEqual(self.ui.navigation.selection, player.MENU_PAGE_SIZE)
        self.release(2)
        self.ui.start_navigation_hold(1, 1)
        self.ui.on_focus_out()
        self.clock.advance(1000)
        self.assertEqual(self.ui.navigation.selection, player.MENU_PAGE_SIZE + 1)
        self.assertFalse(self.clock.pending)

    def test_holding_navigation_in_song_moves_only_once(self):
        pages = tuple(player.Page(f'page-{i}.png', '0' * 64) for i in range(4))
        song = player.Song('song', 'Song', '', pages)
        self.ui.navigation = player.Navigation(player.Setlist(Path('.'), None, (song,)))
        self.ui.navigation.select()

        self.ui.start_navigation_hold(1, 1)
        for _ in range(8):
            self.clock.advance(100)
            self.ui.start_navigation_hold(1, 1)
        self.assertEqual(self.ui.navigation.page, 1)
        self.assertFalse(self.clock.pending)

        self.release()
        self.ui.start_navigation_hold(1, 1)
        self.assertEqual(self.ui.navigation.page, 2)
        self.release()

        self.ui.start_navigation_hold(2, -1)
        for _ in range(8):
            self.clock.advance(100)
            self.ui.start_navigation_hold(2, -1)
        self.assertEqual(self.ui.navigation.page, 1)
        self.assertFalse(self.clock.pending)


if __name__ == '__main__':
    unittest.main()
