import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.jetbrains_proxy_mcp_server.paths import normalize_path, parse_from_wsl, parse_from_windows_git_bash, \
    parse_from_windows, detect_path_type, detect_drive_and_path, build_converted_path


class TestPaths(unittest.TestCase):
    def test_normalize_path(self):
        self.assertEqual("a/b/c", normalize_path("a/b/c"))
        self.assertEqual("a/b/c", normalize_path(r"a\b\c"))
        self.assertEqual("a/b/c", normalize_path(r"a/b\c"))
        self.assertEqual("a/b/c", normalize_path("a//b/c"))
        self.assertEqual("a/b/c", normalize_path("a//b//c"))
        self.assertEqual("a/b", normalize_path("a///b"))
        self.assertEqual("a/b", normalize_path("a////b"))
        self.assertEqual("a/b/c", normalize_path("  a/b/c  "))
        self.assertEqual("a/b/c", normalize_path("\t a/b/c \n"))
        self.assertEqual("a/b/c/d", normalize_path(r"  a\b//c\d "))
        self.assertEqual("", normalize_path(""))
        self.assertEqual("", normalize_path("   "))

    def test_parse_from_wsl(self):
        self.assertEqual(("x", "/b/c/d"), parse_from_wsl("/mnt/x/b/c/d"))
        self.assertEqual(("xx", "/b/c/d"), parse_from_wsl("/mnt/xx/b/c/d"))
        self.assertEqual((None, "/"), parse_from_wsl("/"))
        self.assertEqual((None, "/mnt/C/b/c/d"), parse_from_wsl("/mnt/C/b/c/d"))
        self.assertEqual((None, "/m/x/b/c/d"), parse_from_wsl("/m/x/b/c/d"))
        self.assertEqual((None, "/x/b/c/d"), parse_from_wsl("/x/b/c/d"))
        self.assertEqual((None, "C:/b/c/d"), parse_from_wsl("C:/b/c/d"))
        self.assertEqual((None, "c:/b/c/d"), parse_from_wsl("c:/b/c/d"))
        self.assertEqual((None, ""), parse_from_wsl(""))
        self.assertEqual((None, "a/b/c"), parse_from_wsl("a/b/c"))
        self.assertEqual((None, "  /mnt/c/b/c/d"), parse_from_wsl("  /mnt/c/b/c/d"))  # Non-normalized path
        self.assertEqual((None, "/mnt//c/b/c/d"), parse_from_wsl("/mnt//c/b/c/d"))  # Non-normalized path
        self.assertEqual((None, "  "), parse_from_wsl("  "))

    def test_parse_from_windows_git_bash(self):
        self.assertEqual(("x", "/b/c/d"), parse_from_windows_git_bash("/x/b/c/d"))
        self.assertEqual(("xx", "/b/c/d"), parse_from_windows_git_bash("/xx/b/c/d"))
        self.assertEqual((None, "/"), parse_from_windows_git_bash("/"))
        self.assertEqual((None, "/C/b/c/d"), parse_from_windows_git_bash("/C/b/c/d"))
        self.assertEqual((None, "C:/b/c/d"), parse_from_windows_git_bash("C:/b/c/d"))
        self.assertEqual((None, "c:/b/c/d"), parse_from_windows_git_bash("c:/b/c/d"))
        self.assertEqual((None, ""), parse_from_windows_git_bash(""))
        self.assertEqual((None, "a/b/c"), parse_from_windows_git_bash("a/b/c"))
        self.assertEqual((None, "  /c/b/c/d"), parse_from_windows_git_bash("  /c/b/c/d"))
        self.assertEqual((None, "//c/b/c/d"), parse_from_windows_git_bash("//c/b/c/d"))
        self.assertEqual((None, "  "), parse_from_windows_git_bash("  "))

    def test_parse_from_windows(self):
        self.assertEqual(("C", "/b/c/d"), parse_from_windows("C:/b/c/d"))
        self.assertEqual(("c", "/b/c/d"), parse_from_windows("c:/b/c/d"))
        self.assertEqual(("cd", "/b/c/d"), parse_from_windows("cd:/b/c/d"))
        self.assertEqual(("c", "/"), parse_from_windows("c:/"))
        self.assertEqual(("c", "/"), parse_from_windows("c:"))
        self.assertEqual((None, "a/b/c"), parse_from_windows("a/b/c"))
        self.assertEqual((None, ""), parse_from_windows(""))
        self.assertEqual((None, "  C:/b/c/d"), parse_from_windows("  C:/b/c/d"))
        self.assertEqual((None, "  c:/b/c/d"), parse_from_windows("  c:/b/c/d"))
        self.assertEqual((None, "  "), parse_from_windows("  "))

    def test_detect_path_type(self):
        # WSL detections
        self.assertEqual("wsl", detect_path_type("/mnt/x/a/b"))
        self.assertEqual("wsl", detect_path_type("/mnt/xx/a/b"))
        self.assertEqual("wsl", detect_path_type("   /mnt/x/a/b  "))
        self.assertEqual("wsl", detect_path_type("/mnt//x/a/b"))
        # WSL non-matches
        self.assertIsNone(detect_path_type("/mnt/C/a/b"))  # uppercase drive
        self.assertIsNone(detect_path_type("/mnt/x"))  # no trailing slash after drive segment
        # Windows detections
        self.assertEqual("windows", detect_path_type("C:/a/b"))
        self.assertEqual("windows", detect_path_type("c:/a/b"))
        self.assertEqual("windows", detect_path_type("c:"))
        self.assertEqual("windows", detect_path_type("ABC:/foo"))
        self.assertEqual("windows", detect_path_type("ABC:"))
        # Non-matching others
        self.assertIsNone(detect_path_type("/x/a/b"))  # git-bash style not classified
        self.assertIsNone(detect_path_type("a/b/c"))
        self.assertIsNone(detect_path_type("/"))
        self.assertIsNone(detect_path_type(""))
        self.assertIsNone(detect_path_type("   "))
        self.assertIsNone(detect_path_type(None))  # type: ignore

    def test_detect_drive_and_path(self):
        # WSL style
        self.assertEqual(("x", "/a/b"), detect_drive_and_path("/mnt/x/a/b", "wsl"))
        self.assertEqual(("xx", "/a"), detect_drive_and_path("/mnt/xx/a", "wsl"))
        # No drive match (missing trailing slash after drive segment)
        self.assertEqual((None, "/mnt/x"), detect_drive_and_path("/mnt/x", "wsl"))
        # Not a WSL path -> passthrough
        self.assertEqual((None, "/x/a/b"), detect_drive_and_path("/x/a/b", "wsl"))

        # Git Bash style (single + multi-letter)
        self.assertEqual(("x", "/a/b"), detect_drive_and_path("/x/a/b", "windows_git_bash"))
        self.assertEqual(("xx", "/a"), detect_drive_and_path("/xx/a", "windows_git_bash"))
        # Ambiguous /mnt treated as multi-letter drive ('mnt')
        self.assertEqual(("mnt", "/x/a"), detect_drive_and_path("/mnt/x/a", "windows_git_bash"))
        # No drive (no following slash)
        self.assertEqual((None, "/x"), detect_drive_and_path("/x", "windows_git_bash"))
        # Uppercase not matched (regex only lowercase)
        self.assertEqual((None, "/C/a"), detect_drive_and_path("/C/a", "windows_git_bash"))

        # Windows style
        self.assertEqual(("C", "/a/b"), detect_drive_and_path("C:/a/b", "windows"))
        self.assertEqual(("c", "/"), detect_drive_and_path("c:", "windows"))
        self.assertEqual(("c", "/"), detect_drive_and_path("c:/", "windows"))
        # Multi-letter drive (accepted due to split logic)
        self.assertEqual(("ABC", "/foo"), detect_drive_and_path("ABC:/foo", "windows"))
        # No drive
        self.assertEqual((None, "a/b"), detect_drive_and_path("a/b", "windows"))

        # Unknown from_type -> returns (None, p_norm)
        self.assertEqual((None, "/mnt/x/a"), detect_drive_and_path("/mnt/x/a", "unknown"))  # type: ignore

        # Ensure caller supplies normalized path: backslashes remain if not normalized
        self.assertEqual(("C", "/a/b"), detect_drive_and_path(normalize_path(r"C:\a\b"), "windows"))
        self.assertEqual((None, r"C:\a\b"), detect_drive_and_path(r"C:\a\b", "wsl"))

    def test_build_converted_path(self):
        # To wsl (drive lowercased)
        self.assertEqual("/mnt/c/foo", build_converted_path("C", "/foo", "wsl", "C:/foo"))
        self.assertEqual("/mnt/c/foo", build_converted_path("c", "/foo", "wsl", "c:/foo"))
        self.assertEqual("/bar/baz", build_converted_path(None, "/bar/baz", "wsl", "/bar/baz"))
        # To windows_git_bash (drive lowercased)
        self.assertEqual("/c/foo", build_converted_path("C", "/foo", "windows_git_bash", "C:/foo"))
        self.assertEqual("/c/foo", build_converted_path("c", "/foo", "windows_git_bash", "c:/foo"))
        self.assertEqual("/no/drive", build_converted_path(None, "/no/drive", "windows_git_bash", "/no/drive"))
        # To windows (drive preserved, double slash behavior maintained)
        self.assertEqual("C:/foo", build_converted_path("C", "/foo", "windows", "C:/foo"))
        self.assertEqual("c:/foo", build_converted_path("c", "/foo", "windows", "c:/foo"))
        # No drive, relative path returned unchanged
        self.assertEqual("rel/path", build_converted_path(None, "rel/path", "windows", "rel/path"))
        # No drive, absolute style path -> original returned
        self.assertEqual("/abs/path", build_converted_path(None, "/abs/path", "windows", "/abs/path"))
        # Unknown to_type returns original
        self.assertEqual("orig/path", build_converted_path("c", "/foo", "unknown", "orig/path"))  # type: ignore


if __name__ == '__main__':
    unittest.main()
