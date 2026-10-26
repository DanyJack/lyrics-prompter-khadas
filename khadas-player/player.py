#!/usr/bin/env python3
"""Offline, temporary-list player for Lyrics Prompter Khadas exports.

The GTK layer deliberately contains no editor or text layout code: it only
draws PNGs that have already been rendered by the editor.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import uuid
from typing import Any


PACKAGE_DIR = "LYRICS_PROMPTER"
MANIFEST_NAME = "manifest.json"
SCHEMA = "lyrics-prompter/khadas-list"
VERSION = 1
PAGE_SIZE = (1680, 1050)
MENU_PAGE_SIZE = 20
MENU_ROWS_PER_COLUMN = MENU_PAGE_SIZE // 2


class ImportErrorMessage(ValueError):
    """A user-facing reason why a package cannot be activated."""


@dataclass(frozen=True)
class Page:
    path: str
    sha256: str


@dataclass(frozen=True)
class Song:
    id: str
    title: str
    artist: str
    pages: tuple[Page, ...]


@dataclass(frozen=True)
class Setlist:
    root: Path
    opening: Page | None
    songs: tuple[Song, ...]

    @property
    def entries(self) -> tuple[tuple[str, Song | None], ...]:
        opening = (("Locandina", None),) if self.opening else ()
        return opening + tuple((song.title, song) for song in self.songs)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ImportErrorMessage("Il manifest contiene un percorso file non valido.")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ImportErrorMessage("Il manifest contiene un percorso non sicuro.")
    return value


def read_png_size(path: Path) -> tuple[int, int]:
    try:
        with path.open("rb") as file:
            header = file.read(24)
    except OSError as error:
        raise ImportErrorMessage(f"Impossibile leggere {path.name}.") from error
    if header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ImportErrorMessage(f"{path.name} non è un PNG valido.")
    return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")


def page_from_manifest(root: Path, raw: Any, expected_path: str | None = None) -> Page:
    if not isinstance(raw, dict):
        raise ImportErrorMessage("Il manifest contiene una pagina non valida.")
    relative_path = validate_relative_path(raw.get("path"))
    if expected_path and relative_path != expected_path:
        raise ImportErrorMessage(f"Nome pagina non valido: atteso {expected_path}.")
    checksum = raw.get("sha256")
    if not isinstance(checksum, str) or len(checksum) != 64 or any(c not in "0123456789abcdef" for c in checksum):
        raise ImportErrorMessage(f"Checksum SHA-256 non valido per {relative_path}.")
    file_path = root / relative_path
    if not file_path.is_file():
        raise ImportErrorMessage(f"File mancante: {relative_path}.")
    if sha256_file(file_path) != checksum:
        raise ImportErrorMessage(f"Controllo d'integrità fallito: {relative_path}.")
    if read_png_size(file_path) != PAGE_SIZE:
        raise ImportErrorMessage(
            f"Dimensioni non valide per {relative_path}: richieste {PAGE_SIZE[0]}×{PAGE_SIZE[1]} px."
        )
    return Page(relative_path, checksum)


def validate_package(root: Path) -> Setlist:
    """Validate an already-copied package and return only trusted playback data."""
    manifest_path = root / MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ImportErrorMessage("manifest.json non trovato nella chiavetta.") from error
    except (OSError, ValueError) as error:
        raise ImportErrorMessage("manifest.json non è leggibile o non contiene JSON valido.") from error
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA or manifest.get("version") != VERSION:
        raise ImportErrorMessage("Il manifest non appartiene a un export Khadas compatibile.")
    display = manifest.get("display")
    if not isinstance(display, dict) or (display.get("width"), display.get("height")) != PAGE_SIZE:
        raise ImportErrorMessage("Il formato display deve essere 1680×1050 px.")

    opening_raw = manifest.get("opening")
    opening = None if opening_raw is None else page_from_manifest(root, opening_raw, "opening.png")
    raw_songs = manifest.get("songs")
    if not isinstance(raw_songs, list) or not raw_songs:
        raise ImportErrorMessage("La lista non contiene brani.")
    songs: list[Song] = []
    seen_ids: set[str] = set()
    for index, raw_song in enumerate(raw_songs, start=1):
        if not isinstance(raw_song, dict):
            raise ImportErrorMessage("Il manifest contiene un brano non valido.")
        song_id = raw_song.get("id")
        title = raw_song.get("title")
        artist = raw_song.get("artist", "")
        if not isinstance(song_id, str) or not song_id or "/" in song_id or song_id in seen_ids:
            raise ImportErrorMessage("Ogni brano deve avere un ID univoco valido.")
        if not isinstance(title, str) or not title.strip() or not isinstance(artist, str):
            raise ImportErrorMessage(f"Metadati non validi per il brano {index}.")
        raw_pages = raw_song.get("pages")
        if not isinstance(raw_pages, list) or not raw_pages:
            raise ImportErrorMessage(f"Il brano '{title}' non contiene pagine.")
        pages = tuple(
            page_from_manifest(root, raw_page, f"songs/{song_id}/page-{page_index:03d}.png")
            for page_index, raw_page in enumerate(raw_pages, start=1)
        )
        seen_ids.add(song_id)
        songs.append(Song(song_id, title, artist, pages))
    return Setlist(root=root, opening=opening, songs=tuple(songs))


class SetlistStore:
    """Stores only the last fully verified Khadas package, never an editable library."""

    def __init__(self, runtime_dir: Path | None = None, saved_dir: Path | None = None) -> None:
        self.runtime_dir = runtime_dir or Path(tempfile.gettempdir()) / "lyrics-prompter-khadas"
        self.saved_dir = saved_dir or Path.home() / ".local/share/lyrics-prompter/saved-list"
        shutil.rmtree(self.runtime_dir, ignore_errors=True)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.active: Setlist | None = None

    def has_saved_list(self) -> bool:
        try:
            validate_package(self.saved_dir)
            return True
        except ImportErrorMessage:
            return False

    def use_saved_list(self) -> Setlist:
        self.active = validate_package(self.saved_dir)
        return self.active

    def import_from_usb(self, usb_root: Path) -> Setlist:
        return self.import_package(usb_root / PACKAGE_DIR)

    def import_package(self, source: Path) -> Setlist:
        if not source.is_dir():
            raise ImportErrorMessage(f"Cartella {PACKAGE_DIR} non trovata nella chiavetta.")
        staging = self.runtime_dir / f"staging-{uuid.uuid4().hex}"
        replacement = self.saved_dir.parent / f"saved-list-import-{uuid.uuid4().hex}"
        try:
            contents = [source / name for name in (MANIFEST_NAME, 'opening.png', 'songs')]
            if source.is_symlink() or any(path.is_symlink() for path in contents) or any(
                path.is_symlink() for path in (source / 'songs').rglob('*')
            ):
                raise ImportErrorMessage("Il pacchetto contiene collegamenti non consentiti.")
            def selected_files(directory: str, names: list[str]) -> list[str]:
                if Path(directory) == source:
                    return [name for name in names if name not in {MANIFEST_NAME, 'opening.png', 'songs'}]
                return []
            shutil.copytree(source, staging, ignore=selected_files)
            validate_package(staging)
            self.saved_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(staging, replacement)
            verified = validate_package(replacement)
            self.replace_saved_list(replacement)
            candidate = Setlist(self.saved_dir, verified.opening, verified.songs)
        except (OSError, ImportErrorMessage) as error:
            shutil.rmtree(staging, ignore_errors=True)
            shutil.rmtree(replacement, ignore_errors=True)
            if isinstance(error, ImportErrorMessage):
                raise
            raise ImportErrorMessage("Impossibile copiare il pacchetto dalla chiavetta.") from error
        shutil.rmtree(staging, ignore_errors=True)
        self.active = candidate
        return candidate

    def replace_saved_list(self, replacement: Path) -> None:
        backup = self.saved_dir.parent / f"saved-list-backup-{uuid.uuid4().hex}"
        moved_previous = False
        try:
            if self.saved_dir.exists():
                os.replace(self.saved_dir, backup)
                moved_previous = True
            os.replace(replacement, self.saved_dir)
        except OSError:
            if moved_previous and not self.saved_dir.exists() and backup.exists():
                os.replace(backup, self.saved_dir)
            raise
        finally:
            if self.saved_dir.exists():
                shutil.rmtree(backup, ignore_errors=True)

    def close(self) -> None:
        self.active = None
        shutil.rmtree(self.runtime_dir, ignore_errors=True)


class Navigation:
    """Pure navigation state, shared by GTK and local tests."""

    def __init__(self, setlist: Setlist) -> None:
        self.setlist = setlist
        self.in_menu = True
        self.selection = 0
        self.page = 0

    @property
    def selected_song(self) -> Song | None:
        return self.setlist.entries[self.selection][1]

    @property
    def menu_page(self) -> int:
        return self.selection // MENU_PAGE_SIZE

    @property
    def menu_page_count(self) -> int:
        return (len(self.setlist.entries) + MENU_PAGE_SIZE - 1) // MENU_PAGE_SIZE

    @property
    def visible_entries(self) -> tuple[tuple[int, tuple[str, Song | None]], ...]:
        start = self.menu_page * MENU_PAGE_SIZE
        return tuple(enumerate(self.setlist.entries[start : start + MENU_PAGE_SIZE], start=start))

    @property
    def image_path(self) -> Path | None:
        if self.in_menu:
            return None
        song = self.selected_song
        return self.setlist.root / (self.setlist.opening.path if song is None else song.pages[self.page].path)

    def previous(self) -> None:
        if self.in_menu:
            self.selection = max(0, self.selection - 1)
        elif self.page > 0:
            self.page -= 1
        elif self.selection > 0:
            self.selection -= 1
            previous_song = self.selected_song
            self.page = len(previous_song.pages) - 1 if previous_song is not None else 0

    def next(self) -> None:
        if self.in_menu:
            self.selection = min(len(self.setlist.entries) - 1, self.selection + 1)
        else:
            song = self.selected_song
            if song is not None and self.page < len(song.pages) - 1:
                self.page += 1
            elif self.selection < len(self.setlist.entries) - 1:
                self.selection += 1
                self.page = 0

    def jump_menu_page(self, direction: int) -> None:
        """Move the menu selection by one whole visible page."""
        self.select_menu_page(self.menu_page + direction)

    def select_menu_page(self, page: int) -> None:
        """Select the first item of a visible menu page."""
        if self.in_menu:
            target = min(self.menu_page_count - 1, max(0, page))
            self.selection = target * MENU_PAGE_SIZE

    def select(self) -> None:
        if self.in_menu:
            self.in_menu = False
            self.page = 0
        else:
            self.in_menu = True


def load_gtk() -> None:
    global Gdk, GdkPixbuf, GLib, Gtk, Pango
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("GdkPixbuf", "2.0")
    gi.require_version("Pango", "1.0")
    from gi.repository import Gdk as loaded_gdk, GdkPixbuf as loaded_pixbuf, GLib as loaded_glib, Gtk as loaded_gtk, Pango as loaded_pango
    Gdk, GdkPixbuf, GLib, Gtk, Pango = loaded_gdk, loaded_pixbuf, loaded_glib, loaded_gtk, loaded_pango
    css = Gtk.CssProvider()
    css.load_from_data(b"""
        window, box { background: #000000; color: #ffffff; }
        label { color: #ffffff; font-size: 34px; }
        .setlist-title { color: #ffffff; font-size: 52px; font-weight: 800; }
        .setlist-row { color: #d5d5d5; font-size: 32px; }
        .setlist-selected { color: #ffffff; background: #324862; font-size: 34px; font-weight: 800; }
        .setlist-meta { color: #aaa; font-size: 25px; }
        .import-error { color: #ff8c8c; font-size: 48px; font-weight: 800; }
    """)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )


def show_import_error(message: str) -> None:
    """Show a legible on-device error when there is no list to activate."""
    load_gtk()
    window = Gtk.Window(title="Lyrics Prompter")
    window.set_decorated(False)
    window.fullscreen()
    window.connect("destroy", Gtk.main_quit)
    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22)
    content.set_border_width(64)
    title = Gtk.Label(label="IMPORTAZIONE NON RIUSCITA")
    title.get_style_context().add_class("import-error")
    title.set_halign(Gtk.Align.START)
    details = Gtk.Label(label=message + "\n\nLa lista precedente, se aperta, non viene modificata.")
    details.set_halign(Gtk.Align.START)
    details.set_line_wrap(True)
    content.pack_start(title, False, False, 0)
    content.pack_start(details, False, False, 0)
    window.add(content)
    window.show_all()
    Gtk.main()


class KhadasPlayer:
    def __init__(self, store: SetlistStore, setlist: Setlist) -> None:
        self.store, self.navigation = store, Navigation(setlist)
        self.window = Gtk.Window(title="Lyrics Prompter")
        self.window.set_decorated(False)
        self.window.fullscreen()
        self.window.connect("destroy", self.on_destroy)
        self.window.connect("key-press-event", self.on_key)
        self.window.connect("key-release-event", self.on_key_release)
        self.window.connect("focus-out-event", self.on_focus_out)
        self.held_navigation_key: int | None = None
        self.held_menu_page: int | None = None
        self.hold_timer: int | None = None
        self.select_key: int | None = None
        self.select_timer: int | None = None
        self.select_long = False
        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.window.add(self.content)
        self.window.show_all()
        blank_cursor = Gdk.Cursor.new_for_display(
            self.window.get_display(), Gdk.CursorType.BLANK_CURSOR
        )
        self.window.get_window().set_cursor(blank_cursor)
        self.redraw()

    def on_destroy(self, *_args: Any) -> None:
        self.cancel_navigation_hold()
        self.cancel_select_hold()
        self.store.close()
        Gtk.main_quit()

    def on_key(self, _widget: Any, event: Any) -> bool:
        key = event.keyval
        if key in (Gdk.KEY_Escape,):
            self.window.destroy()
        elif key == Gdk.KEY_F12:
            self.cancel_navigation_hold()
            self.cancel_select_hold()
            PowerScreen(self.window)
        elif key in (Gdk.KEY_Page_Up, Gdk.KEY_Left, Gdk.KEY_Up):
            self.start_navigation_hold(key, -1)
        elif key in (Gdk.KEY_Page_Down, Gdk.KEY_Right, Gdk.KEY_Down):
            self.start_navigation_hold(key, 1)
        elif key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            self.cancel_navigation_hold()
            if self.select_key is None:
                self.select_key = key
                self.select_long = False
                if self.navigation.in_menu:
                    self.select_timer = GLib.timeout_add(900, self.open_import)
        return True

    def on_key_release(self, _widget: Any, event: Any) -> bool:
        if event.keyval == self.held_navigation_key:
            self.cancel_navigation_hold()
        if event.keyval == getattr(self, 'select_key', None):
            short = not self.select_long
            self.cancel_select_hold()
            if short:
                self.navigation.select(); self.redraw()
        return True

    def cancel_select_hold(self) -> None:
        if getattr(self, 'select_timer', None) is not None:
            GLib.source_remove(self.select_timer)
        self.select_timer = None
        self.select_key = None

    def open_import(self) -> bool:
        self.select_timer = None
        self.select_long = True
        self.cancel_navigation_hold()
        from usb_import import ImportScreen
        ImportScreen(sys.modules[__name__], self.store, parent=self, confirm=True)
        self.window.hide()
        return False

    def cancel_navigation_hold(self) -> None:
        if self.hold_timer is not None:
            GLib.source_remove(self.hold_timer)
            self.hold_timer = None
        self.held_navigation_key = None
        self.held_menu_page = None

    def on_focus_out(self, *_args: Any) -> bool:
        self.cancel_navigation_hold()
        self.cancel_select_hold()
        return False

    def start_navigation_hold(self, key: int, direction: int) -> None:
        """A short press moves one row; a hold advances full menu pages."""
        self.cancel_select_hold()
        if self.held_navigation_key == key:
            return  # Ignore keyboard autorepeat until the physical key is released.
        self.cancel_navigation_hold()
        self.held_navigation_key = key
        self.held_menu_page = self.navigation.menu_page if self.navigation.in_menu else None
        if direction < 0:
            self.navigation.previous()
        else:
            self.navigation.next()
        self.redraw()
        if self.navigation.in_menu:
            self.hold_timer = GLib.timeout_add(650, self.advance_held_menu_page, key, direction)

    def advance_held_menu_page(self, key: int, direction: int) -> bool:
        self.hold_timer = None
        if self.held_navigation_key != key or self.held_menu_page is None or not self.navigation.in_menu:
            return False
        self.navigation.select_menu_page(self.held_menu_page + direction)
        self.redraw()
        return False

    def redraw(self) -> None:
        for child in self.content.get_children():
            self.content.remove(child)
        if self.navigation.in_menu:
            menu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
            menu.set_border_width(48)
            header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            title = Gtk.Label(label="SCALETTA")
            title.get_style_context().add_class("setlist-title")
            title.set_halign(Gtk.Align.START)
            page_label = Gtk.Label(label=f"Pagina {self.navigation.menu_page + 1}/{self.navigation.menu_page_count}")
            page_label.get_style_context().add_class("setlist-meta")
            page_label.set_halign(Gtk.Align.END)
            header.pack_start(title, True, True, 0)
            header.pack_start(page_label, True, True, 0)
            menu.pack_start(header, False, False, 0)
            grid = Gtk.Grid()
            grid.set_column_homogeneous(True)
            grid.set_column_spacing(36)
            grid.set_row_spacing(12)
            for entry_index, (label, song) in self.navigation.visible_entries:
                position = entry_index % MENU_PAGE_SIZE
                column, line = divmod(position, MENU_ROWS_PER_COLUMN)
                prefix = "›" if entry_index == self.navigation.selection else " "
                row = Gtk.Label(label=f"{prefix} {entry_index + 1:02d}  {label}")
                row.get_style_context().add_class(
                    "setlist-selected" if entry_index == self.navigation.selection else "setlist-row"
                )
                row.set_xalign(0)
                row.set_hexpand(True)
                row.set_ellipsize(Pango.EllipsizeMode.END)
                row.set_size_request(0, 57)
                grid.attach(row, column, line, 1, 1)
            menu.pack_start(grid, True, True, 0)
            footer = Gtk.Label(label="Prev/Next: brano    •    pressione lunga: pagina    •    Select: apri")
            footer.get_style_context().add_class("setlist-meta")
            footer.set_halign(Gtk.Align.START)
            menu.pack_start(footer, False, False, 0)
            self.content.pack_start(menu, True, True, 0)
        else:
            image = Gtk.DrawingArea()
            image.set_size_request(1, 1)
            image.connect("draw", self.draw_page, GdkPixbuf.Pixbuf.new_from_file(str(self.navigation.image_path)))
            self.content.pack_start(image, True, True, 0)
        self.content.show_all()

    def draw_page(self, widget: Any, context: Any, pixbuf: Any) -> bool:
        """Fit the exported page inside the current display without cropping."""
        allocation = widget.get_allocation()
        scale = min(allocation.width / pixbuf.get_width(), allocation.height / pixbuf.get_height())
        context.translate((allocation.width - pixbuf.get_width() * scale) / 2,
                          (allocation.height - pixbuf.get_height() * scale) / 2)
        context.scale(scale, scale)
        Gdk.cairo_set_source_pixbuf(context, pixbuf, 0, 0)
        context.paint()
        return False


class PowerScreen:
    """Explicit shutdown choice, opened by the pedal's held chord."""

    ACTIONS = ("ANNULLA", "SPEGNI")

    def __init__(self, parent_window: Any) -> None:
        self.parent_window = parent_window
        self.selection = 0  # Start on the safe choice.
        self.pressed: set[int] = set()
        self.busy = False
        self.error = ""
        self.window = Gtk.Window(title="Alimentazione")
        self.window.set_decorated(False)
        self.window.fullscreen()
        self.window.connect("key-press-event", self.on_key)
        self.window.connect("key-release-event", self.on_release)
        self.window.connect("delete-event", lambda *_args: True)
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=28)
        self.box.set_halign(Gtk.Align.CENTER)
        self.box.set_valign(Gtk.Align.CENTER)
        self.window.add(self.box)
        self.redraw()
        self.window.show_all()
        self.window.get_window().set_cursor(Gdk.Cursor.new_for_display(
            self.window.get_display(), Gdk.CursorType.BLANK_CURSOR
        ))
        self.parent_window.hide()

    def redraw(self) -> None:
        for child in self.box.get_children():
            self.box.remove(child)
        title = Gtk.Label(label="SPEGNIMENTO")
        title.get_style_context().add_class("setlist-title")
        self.box.pack_start(title, False, False, 0)
        for index, action in enumerate(self.ACTIONS):
            label = Gtk.Label(label=("›  " if index == self.selection else "    ") + action)
            label.get_style_context().add_class(
                "setlist-selected" if index == self.selection else "setlist-row"
            )
            label.set_size_request(440, 66)
            label.set_xalign(0.5)
            self.box.pack_start(label, False, False, 0)
        hint = Gtk.Label(label=self.error or "Prev/Next: scegli    •    Select: conferma")
        hint.get_style_context().add_class("setlist-meta")
        self.box.pack_start(hint, False, False, 0)
        self.box.show_all()

    def on_key(self, _widget: Any, event: Any) -> bool:
        key = event.keyval
        if key in self.pressed or self.busy:
            return True
        self.pressed.add(key)
        if key == Gdk.KEY_Escape:
            self.cancel()
        elif key in (Gdk.KEY_Page_Up, Gdk.KEY_Left, Gdk.KEY_Up):
            self.selection = max(0, self.selection - 1)
            self.error = ""
            self.redraw()
        elif key in (Gdk.KEY_Page_Down, Gdk.KEY_Right, Gdk.KEY_Down):
            self.selection = min(len(self.ACTIONS) - 1, self.selection + 1)
            self.error = ""
            self.redraw()
        elif key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            self.confirm()
        return True

    def on_release(self, _widget: Any, event: Any) -> bool:
        self.pressed.discard(event.keyval)
        return True

    def cancel(self) -> None:
        self.window.destroy()
        self.parent_window.show_all()
        self.parent_window.present()

    def confirm(self) -> None:
        if self.selection == 0:
            self.cancel()
            return
        try:
            subprocess.run(["systemctl", "--no-ask-password", "poweroff"], check=True, capture_output=True,
                           text=True, timeout=8)
        except (OSError, subprocess.SubprocessError) as error:
            reason = getattr(error, "stderr", None) or str(error)
            print(f"Comando di spegnimento fallito: {reason}", file=sys.stderr)
            self.error = "Operazione non riuscita. Select: riprova; Prev/Next: scegli."
            self.redraw()
            return
        self.busy = True
        for child in self.box.get_children():
            self.box.remove(child)
        self.box.pack_start(Gtk.Label(label="Arresto in corso…"), False, False, 0)
        self.box.show_all()


class SavedListScreen:
    """Ask explicitly whether the verified saved setlist should be reused."""

    def __init__(self, store: SetlistStore, preferred_root: Path | None = None) -> None:
        self.store = store
        self.preferred_root = preferred_root
        self.activated = False
        self.window = Gtk.Window(title="Lyrics Prompter")
        self.window.set_decorated(False)
        self.window.fullscreen()
        self.window.connect("destroy", self.on_destroy)
        self.window.connect("key-press-event", self.on_key)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        content.set_halign(Gtk.Align.CENTER)
        content.set_valign(Gtk.Align.CENTER)
        title = Gtk.Label(label="USA LA SCALETTA SALVATA?")
        title.get_style_context().add_class("setlist-title")
        details = Gtk.Label(label="Prev: importa da chiavetta\nNext: usa la scaletta salvata")
        details.set_justify(Gtk.Justification.CENTER)
        content.pack_start(title, False, False, 0)
        content.pack_start(details, False, False, 0)
        self.window.add(content)
        self.window.show_all()
        self.window.get_window().set_cursor(
            Gdk.Cursor.new_for_display(self.window.get_display(), Gdk.CursorType.BLANK_CURSOR)
        )

    def on_destroy(self, *_args: Any) -> None:
        if not self.activated:
            self.store.close()
            Gtk.main_quit()

    def on_key(self, _widget: Any, event: Any) -> bool:
        key = event.keyval
        if key == Gdk.KEY_Escape:
            self.window.destroy()
        elif key == Gdk.KEY_F12:
            PowerScreen(self.window)
        elif key in (Gdk.KEY_Page_Up, Gdk.KEY_Left, Gdk.KEY_Up):
            self.activated = True
            self.window.destroy()
            NoMediaScreen(self.store, self.preferred_root)
        elif key in (Gdk.KEY_Page_Down, Gdk.KEY_Right, Gdk.KEY_Down, Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            self.activated = True
            self.window.destroy()
            KhadasPlayer(self.store, self.store.use_saved_list())
        return True


def NoMediaScreen(store: SetlistStore, preferred_root: Path | None = None) -> Any:
    from usb_import import ImportScreen
    return ImportScreen(sys.modules[__name__], store, preferred_root)


def find_usb_root() -> Path | None:
    user = os.environ.get("USER", "")
    candidates = [Path("/media") / user, Path("/run/media") / user, Path("/mnt")]
    for parent in candidates:
        if parent.is_dir():
            for child in parent.iterdir():
                if (child / PACKAGE_DIR / MANIFEST_NAME).is_file():
                    return child
    return None


def unmounted_usb_partitions() -> tuple[str, ...]:
    """Return FAT-family partitions on removable USB drives, without mounting them."""
    try:
        result = subprocess.run(
            ["lsblk", "--json", "--tree", "--output", "PATH,TYPE,TRAN,FSTYPE,MOUNTPOINTS"],
            check=True, capture_output=True, text=True, timeout=3,
        )
        devices = json.loads(result.stdout).get("blockdevices", [])
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return ()
    partitions: list[str] = []

    def walk(items: Any, usb_parent: bool = False) -> None:
        for item in items if isinstance(items, list) else []:
            is_usb = usb_parent or item.get("tran") == "usb"
            filesystem = item.get("fstype")
            mounted = item.get("mountpoints") or []
            if is_usb and item.get("type") == "part" and filesystem in {"vfat", "fat", "fat32", "exfat"} and not any(mounted):
                path = item.get("path")
                if isinstance(path, str):
                    partitions.append(path)
            walk(item.get("children"), is_usb)

    walk(devices)
    return tuple(partitions)


def mount_usb_partitions(partitions: tuple[str, ...]) -> None:
    """Ask UDisks to mount removable media; PolicyKit makes this non-interactive."""
    for partition in partitions:
        try:
            subprocess.run(
                ["udisksctl", "mount", "-b", partition],
                check=False, capture_output=True, text=True, timeout=8,
            )
        except (OSError, subprocess.SubprocessError):
            continue


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the offline Lyrics Prompter Khadas player.")
    parser.add_argument("--usb-root", type=Path, help="Mount point of the FAT32 USB drive.")
    parser.add_argument("--check", action="store_true", help="Import and validate without opening GTK.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    store = SetlistStore()
    started = False
    try:
        if args.check:
            usb_root = args.usb_root or find_usb_root()
            if usb_root is None:
                raise SystemExit("Nessuna chiavetta Lyrics Prompter trovata. Usa --usb-root per indicarla.")
            setlist = validate_package(usb_root / PACKAGE_DIR)
            print(f"Importazione riuscita: {len(setlist.songs)} brani.")
            return
        load_gtk()
        if store.has_saved_list():
            SavedListScreen(store, args.usb_root)
        else:
            NoMediaScreen(store, args.usb_root)
        started = True
        Gtk.main()
    except ImportErrorMessage as error:
        print(f"Importazione non riuscita: {error}")
        if args.check:
            raise SystemExit(1) from error
        show_import_error(str(error))
    finally:
        if args.check or not started:
            store.close()


if __name__ == "__main__":
    main()
