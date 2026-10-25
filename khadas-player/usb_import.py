"""USB import UI, active only when explicitly requested or at initial setup."""
from pathlib import Path
import json
import subprocess
import threading


def discover_packages(root):
    """List direct and named exports without parsing unrelated manifests."""
    base = root / 'LYRICS_PROMPTER'
    if base.is_symlink() or not base.is_dir():
        return []
    found = []
    if (base / 'manifest.json').is_file():
        found.append(('Scaletta principale', base))
    for child in sorted(base.iterdir(), key=lambda p: p.name.casefold()):
        if not child.is_symlink() and child.is_dir() and (child / 'manifest.json').is_file():
            found.append((child.name, child))
    return found


def usb_devices():
    result = subprocess.run(['lsblk', '--json', '--tree', '--output',
                             'PATH,TYPE,TRAN,FSTYPE,MOUNTPOINTS'],
                            capture_output=True, text=True, check=True, timeout=5)
    found = []
    def walk(items, usb=False):
        for item in items:
            is_usb = usb or item.get('tran') == 'usb'
            if is_usb and item.get('type') == 'part' and item.get('fstype') in {'vfat', 'exfat', 'fat', 'fat32'}:
                found.append((item['path'], [Path(p) for p in item.get('mountpoints', []) if p]))
            walk(item.get('children', []), is_usb)
    walk(json.loads(result.stdout).get('blockdevices', []))
    return found


def udisks(action, device):
    command = ['udisksctl', action, '--no-user-interaction', '-b', device]
    if action == 'mount':
        command += ['--options', 'ro,nosuid,nodev,noexec']
    result = subprocess.run(command, capture_output=True, text=True, timeout=12)
    if result.returncode:
        raise OSError('Impossibile ' + ('montare' if action == 'mount' else 'smontare')
                      + ' la chiavetta. Controlla il supporto e riprova.')


class USBSession:
    def __init__(self, preferred_root=None):
        self.preferred_root = preferred_root
        self.owned = set()

    def scan(self):
        if self.preferred_root is not None:
            return discover_packages(self.preferred_root) if self.preferred_root.exists() else None
        devices = usb_devices()
        if not devices:
            return None
        for device, mounts in devices:
            if not mounts:
                udisks('mount', device)
                self.owned.add(device)
        found = []
        for device, mounts in usb_devices():
            for root in mounts:
                options = subprocess.run(['findmnt', '-n', '-o', 'OPTIONS', '--target', str(root)],
                                         capture_output=True, text=True, check=True, timeout=3).stdout.strip().split(',')
                if 'ro' not in options:
                    raise OSError('La chiavetta è già montata in scrittura. Smontala e reinseriscila per importarla in sola lettura.')
                self.owned.add(device)
                found.extend(discover_packages(root))
        return found

    def close(self):
        errors = []
        for device in tuple(self.owned):
            try:
                udisks('unmount', device)
                self.owned.remove(device)
            except (OSError, subprocess.SubprocessError) as error:
                errors.append(str(error))
        return '\n'.join(errors)


class ImportScreen:
    def __init__(self, api, store, preferred_root=None, parent=None, confirm=False):
        self.api, self.store, self.parent = api, store, parent
        self.usb = USBSession(preferred_root)
        self.state = 'confirm' if confirm else 'waiting'
        self.busy = False
        self.closed = False
        self.choices = []
        self.selection = 0
        self.pressed = set()
        self.result = None
        self.cancel_requested = False
        self.poll_timer = None
        Gtk, Gdk = api.Gtk, api.Gdk
        self.window = Gtk.Window(title='Lyrics Prompter')
        geometry = self.window.get_display().get_primary_monitor().get_geometry()
        self.window.set_default_size(geometry.width, geometry.height)
        self.window.set_decorated(False)
        self.window.fullscreen()
        self.window.connect('key-press-event', self.on_key)
        self.window.connect('key-release-event', self.on_release)
        self.window.connect('delete-event', lambda *_: True)
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=26)
        self.box.set_border_width(58)
        self.window.add(self.box)
        self.show('CARICARE UNA NUOVA SCALETTA?' if confirm else 'NO MEDIA',
                  'Prev: annulla\nNext: importa da chiavetta' if confirm else
                  'Inserisci la chiavetta USB\nSelect: annulla')
        self.window.show_all()
        self.window.get_window().set_cursor(Gdk.Cursor.new_for_display(
            self.window.get_display(), Gdk.CursorType.BLANK_CURSOR))
        self.poll_timer = api.GLib.timeout_add(800, self.poll)

    def show(self, title, details='', rows=()):
        for child in self.box.get_children():
            self.box.remove(child)
        for text, style in [(title, 'setlist-title'), (details, '')] + list(rows):
            if not text:
                continue
            label = self.api.Gtk.Label(label=text)
            label.set_line_wrap(True)
            label.set_line_wrap_mode(self.api.Pango.WrapMode.WORD_CHAR)
            label.set_max_width_chars(30)
            label.set_size_request(880, -1)
            label.set_xalign(0)
            if style:
                label.get_style_context().add_class(style)
            if style in ('setlist-selected', 'setlist-row'):
                label.set_line_wrap(False)
                label.set_single_line_mode(True)
                label.set_ellipsize(self.api.Pango.EllipsizeMode.END)
            self.box.pack_start(label, False, False, 0)
        self.box.show_all()

    def worker(self, job, done):
        self.busy = True
        def run():
            try:
                value, error = job(), None
            except Exception as exc:
                value, error = None, exc
            self.api.GLib.idle_add(deliver, value, error)
        def deliver(value, error):
            self.busy = False
            if not self.closed:
                if self.cancel_requested:
                    self.cancel_requested = False
                    self.cancel()
                else:
                    done(value, error)
            return False
        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        if self.closed:
            return False
        if self.state == 'waiting' and not self.busy:
            self.worker(self.usb.scan, self.scanned)
        return True

    def scanned(self, choices, error):
        if error:
            self.fail(str(error))
        elif choices is None:
            return
        elif not choices:
            self.fail('Nessuna scaletta trovata nella cartella LYRICS_PROMPTER.')
        else:
            self.choices, self.selection = choices, 0
            if len(choices) == 1:
                self.import_selected()
            else:
                self.state = 'choose'
                self.show_choices()

    def show_choices(self):
        names = [name for name, _ in self.choices] + ['Annulla']
        start = self.selection // 7 * 7
        rows = [('▲', '')] if start else []
        rows += [('› ' + name if i == self.selection else name,
                  'setlist-selected' if i == self.selection else 'setlist-row')
                 for i, name in enumerate(names[start:start + 7], start)]
        if start + 7 < len(names):
            rows.append(('▼', ''))
        self.show('SCEGLI LA SCALETTA', 'Prev / Next: scegli\nSelect: conferma', rows)

    def import_selected(self):
        self.state = 'importing'
        self.show('IMPORTAZIONE IN CORSO', 'Copia e verifica della scaletta…\nNon rimuovere la chiavetta.')
        source = self.choices[self.selection][1]
        self.worker(lambda: self.store.import_package(source), self.imported)

    def imported(self, result, error):
        if error:
            self.fail(str(error))
            return
        self.result = result
        self.worker(self.usb.close, self.import_unmounted)

    def import_unmounted(self, warning, error):
        self.state = 'success'
        details = ('Scaletta caricata.\nSmontaggio non riuscito: lascia inserita la chiavetta.'
                   if warning or error else 'Puoi rimuovere la chiavetta.')
        self.show('SCALETTA PRONTA', details + '\n\nSelect: apri la scaletta')

    def fail(self, message):
        self.state = 'error'
        self.show('IMPORTAZIONE NON RIUSCITA', message +
                  '\n\nLa scaletta attuale resta disponibile.\nPrev: annulla\nNext: riprova / scegli un’altra lista')

    def on_release(self, _widget, event):
        self.pressed.discard(event.keyval)
        return True

    def on_key(self, _widget, event):
        key, Gdk = event.keyval, self.api.Gdk
        if key == Gdk.KEY_F12:
            if not self.busy:
                self.api.PowerScreen(self.window)
            return True
        if key in self.pressed:
            return True
        self.pressed.add(key)
        prev = key in (Gdk.KEY_Left, Gdk.KEY_Up, Gdk.KEY_Page_Up)
        next_ = key in (Gdk.KEY_Right, Gdk.KEY_Down, Gdk.KEY_Page_Down)
        select = key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space)
        if self.busy:
            if self.state == 'waiting' and select:
                self.cancel_requested = True
            return True
        if self.state == 'confirm':
            if prev:
                self.cancel()
            elif next_:
                self.state = 'waiting'
                self.show('NO MEDIA', 'Inserisci la chiavetta USB\nSelect: annulla')
        elif self.state == 'waiting' and select:
            self.cancel()
        elif self.state == 'choose':
            if prev or next_:
                self.selection = max(0, min(len(self.choices), self.selection + (1 if next_ else -1)))
                self.show_choices()
            elif select:
                if self.selection == len(self.choices):
                    self.cancel()
                else:
                    self.import_selected()
        elif self.state == 'error':
            if prev:
                self.cancel()
            elif next_:
                if len(self.choices) > 1:
                    self.state = 'choose'
                    self.show_choices()
                else:
                    self.state = 'waiting'
                    self.show('NO MEDIA', 'Controllo della chiavetta…\nSelect: annulla')
        elif self.state == 'success' and select:
            self.finish()
        return True

    def cancel(self):
        self.worker(self.usb.close, self.cancelled)

    def cancelled(self, warning, error):
        if warning or error:
            self.state = 'error'
            self.show('CHIAVETTA NON SMONTATA', 'Lasciala inserita.\nPrev: riprova ad annullare\nNext: riprova a leggere')
        else:
            self.finish()

    def finish(self):
        self.closed = True
        if self.poll_timer is not None:
            self.api.GLib.source_remove(self.poll_timer)
        self.window.destroy()
        if self.parent:
            if self.result:
                self.parent.navigation = self.api.Navigation(self.result)
            self.parent.redraw()
            self.parent.window.show_all()
            self.parent.window.present()
        elif self.result:
            self.api.KhadasPlayer(self.store, self.result)
        elif self.store.has_saved_list():
            self.api.SavedListScreen(self.store, self.usb.preferred_root)
        else:
            ImportScreen(self.api, self.store, self.usb.preferred_root)
