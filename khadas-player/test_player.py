import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parent))
from player import ImportErrorMessage, MENU_PAGE_SIZE, Navigation, PACKAGE_DIR, Page, Setlist, SetlistStore, Song, validate_package


def png(width=1680, height=1050):
    return b"\x89PNG\r\n\x1a\n" + (13).to_bytes(4, "big") + b"IHDR" + width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x08\x02\x00\x00\x00"


def package(root: Path, corrupt=False):
    package_root = root / PACKAGE_DIR
    page_path = package_root / "songs/song-1-test/page-001.png"
    page_path.parent.mkdir(parents=True)
    contents = png()
    page_path.write_bytes(contents)
    digest = hashlib.sha256(contents).hexdigest()
    if corrupt:
        digest = "0" * 64
    manifest = {"schema": "lyrics-prompter/khadas-list", "version": 1, "display": {"width": 1680, "height": 1050}, "opening": None, "songs": [{"id": "song-1-test", "title": "Test", "artist": "", "pages": [{"path": "songs/song-1-test/page-001.png", "sha256": digest}]}]}
    (package_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


class PlayerTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(self._testMethodName)

    def test_import_and_integrity(self):
        with self.subTest("valid package"):
            import tempfile
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory); package(root)
                store = SetlistStore(root / "cache", root / "saved")
                active = store.import_from_usb(root)
                self.assertEqual(active.songs[0].title, "Test")
                self.assertTrue((active.root / active.songs[0].pages[0].path).is_file())
                store.close()
                restarted = SetlistStore(root / "cache-next", root / "saved")
                self.assertTrue(restarted.has_saved_list())
                self.assertEqual(restarted.use_saved_list().songs[0].title, "Test")
                restarted.close()

    def test_bad_import_preserves_active_list(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); good = root / "good"; bad = root / "bad"; good.mkdir(); bad.mkdir()
            package(good); package(bad, corrupt=True)
            store = SetlistStore(root / "cache", root / "saved")
            first = store.import_from_usb(good)
            with self.assertRaises(ImportErrorMessage):
                store.import_from_usb(bad)
            self.assertIs(store.active, first)
            self.assertTrue(first.root.exists())
            store.close()

    def test_portrait_package_is_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); package(root)
            package_root = root / PACKAGE_DIR
            manifest_path = package_root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["display"] = {"width": 1050, "height": 1680}
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ImportErrorMessage, "1680×1050"):
                validate_package(package_root)

            manifest["display"] = {"width": 1680, "height": 1050}
            page_path = package_root / manifest["songs"][0]["pages"][0]["path"]
            contents = png(1050, 1680)
            page_path.write_bytes(contents)
            manifest["songs"][0]["pages"][0]["sha256"] = hashlib.sha256(contents).hexdigest()
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ImportErrorMessage, "1680×1050"):
                validate_package(package_root)

    def test_navigation(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); package(root)
            store = SetlistStore(root / "cache", root / "saved")
            nav = Navigation(store.import_from_usb(root))
            nav.select()
            self.assertFalse(nav.in_menu)
            nav.previous()
            self.assertFalse(nav.in_menu)
            self.assertIsNotNone(nav.image_path)
            nav.next(); self.assertEqual(nav.page, 0)
            nav.select(); self.assertTrue(nav.in_menu)
            store.close()

    def test_setlist_pages_follow_selection(self):
        songs = tuple(Song(f"song-{number}", f"Song {number}", "", (Page("page.png", "0" * 64),)) for number in range(MENU_PAGE_SIZE * 2 + 2))
        nav = Navigation(Setlist(Path("/tmp"), None, songs))
        nav.jump_menu_page(1)
        self.assertEqual(nav.menu_page, 1)
        self.assertEqual(nav.selection, MENU_PAGE_SIZE)
        self.assertEqual(nav.visible_entries[0][0], MENU_PAGE_SIZE)
        self.assertEqual(nav.menu_page_count, 3)
        nav.jump_menu_page(-1)
        self.assertEqual(nav.selection, 0)

    def test_page_navigation_moves_between_songs(self):
        songs = (
            Song("first", "First", "", (Page("first.png", "0" * 64),)),
            Song("second", "Second", "", (Page("second-1.png", "0" * 64), Page("second-2.png", "0" * 64))),
        )
        nav = Navigation(Setlist(Path("/tmp"), None, songs))
        nav.select()
        nav.next()
        self.assertEqual(nav.selection, 1)
        self.assertEqual(nav.page, 0)
        nav.previous()
        self.assertEqual(nav.selection, 0)
        nav.next(); nav.next()
        self.assertEqual(nav.page, 1)


if __name__ == "__main__":
    unittest.main()
