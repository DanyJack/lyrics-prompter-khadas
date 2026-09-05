"""Run manually on the Prompter display; uses temporary data, no USB I/O."""
from pathlib import Path
import tempfile
import player
from usb_import import ImportScreen

player.load_gtk()
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    store = player.SetlistStore(root / 'runtime', root / 'saved')
    screen = ImportScreen(player, store, confirm=True)
    player.GLib.source_remove(screen.poll_timer)
    screen.poll_timer = None
    screen.choices = [('Serata acustica con un nome molto lungo ' * 4, root)] * 15
    screen.selection = 6
    screen.state = 'choose'
    screen.show_choices()
    failures = []
    def check():
        window = screen.window.get_allocation()
        monitor = screen.window.get_display().get_monitor_at_window(screen.window.get_window()).get_geometry()
        if window.width > monitor.width or window.height > monitor.height:
            failures.append(('window exceeds monitor', window.width, window.height))
        for child in screen.box.get_children():
            rect = child.get_allocation()
            print(repr(child.get_text()[:35]), rect.x, rect.y, rect.width, rect.height)
            if rect.x < 0 or rect.y < 0 or rect.x + rect.width > window.width or rect.y + rect.height > window.height:
                failures.append((child.get_text(), rect.x, rect.y, rect.width, rect.height))
        print('Picker size:', window.width, window.height, 'overflow:', failures)
        screen.closed = True
        screen.window.destroy()
        player.Gtk.main_quit()
        return False
    player.GLib.timeout_add(600, check)
    player.Gtk.main()
    store.close()
    assert not failures, failures
