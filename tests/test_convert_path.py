import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.jetbrains_proxy_mcp_server.paths import convert_path


class TestConvertPath(unittest.TestCase):
    def test_wsl_to_windows(self):
        cases = [
            ("/mnt/d/Projects", "d:/Projects"),
            ("/mnt/dd/Projects", "dd:/Projects"),
            ("/c/Users/Test", "/c/Users/Test"),  # Original path unchanged
            ("/C/Users/Example", "/C/Users/Example"),  # Original path unchanged
            ("  /c/Users/Example", "  /c/Users/Example"),  # Original path unchanged
            ("/c/", "/c/"),  # Original path unchanged
            ("/d/", "/d/"),  # Original path unchanged
            ("some/relative/path", "some/relative/path"),
            ("relative/path", "relative/path"),
            ("C:/relative/path", "C:/relative/path"),
            ("C:/relative/path   ", "C:/relative/path   "),  # Original path unchanged
            ("C:\\relative\\path", "C:\\relative\\path"),
        ]
        for src, expected in cases:
            with self.subTest(src=src):
                result = convert_path(src, "wsl", "windows")
                print(f"wsl -> windows: {src} -> {result}, expected: {expected}")
                self.assertEqual(expected, result)

    def test_wsl_to_windows_git_bash(self):
        cases = [
            ("/mnt/d/Projects", "/d/Projects"),
            ("/mnt/dd/Projects", "/dd/Projects"),
            ("/c/Users/Example", "/c/Users/Example"),
            ("/c/Users/Test", "/c/Users/Test"),
            ("/c/", "/c/"),
            ("relative/path", "relative/path"),
            ("some/relative/path", "some/relative/path"),
            ("C:/relative/path", "/c/relative/path"),  # Use detected from type
            ("C:/relative/path   ", "/c/relative/path"),
            ("C:\\relative\\path", "/c/relative/path"),
        ]
        for src, expected in cases:
            with self.subTest(src=src):
                result = convert_path(src, "wsl", "windows_git_bash")
                print(f"wsl -> windows_git_bash: {src} -> {result}, expected: {expected}")
                self.assertEqual(expected, result)

    def test_windows_git_bash_to_wsl(self):
        cases = [
            ("/d/Projects", "/mnt/d/Projects"),
            ("/c/Users/Test", "/mnt/c/Users/Test"),
            ("/C/Users/Test", "/C/Users/Test"),
            ("/d/", "/mnt/d/"),
            ("/mnt/e/Stuff", "/mnt/e/Stuff"),
            ("relative/path", "relative/path"),
            ("d:/Projects", "/mnt/d/Projects"),
            ("D:/Projects", "/mnt/d/Projects"),
            ("D:\\Projects", "/mnt/d/Projects"),
        ]
        for src, expected in cases:
            with self.subTest(src=src):
                result = convert_path(src, "windows_git_bash", "wsl")
                print(f"windows_git_bash -> wsl: {src} -> {result}, expected: {expected}")
                self.assertEqual(expected, result)

    def test_windows_git_bash_to_windows(self):
        cases = [
            ("/d/Projects", "d:/Projects"),
            ("/c/Users/Test", "c:/Users/Test"),
            ("/d/", "d:/"),
            ("/c/", "c:/"),
            ("/mnt/e/Stuff", "e:/Stuff"),
            ("/mnt/E/Stuff", "mnt:/E/Stuff"),
            ("relative/path", "relative/path"),
        ]
        for src, expected in cases:
            with self.subTest(src=src):
                result = convert_path(src, "windows_git_bash", "windows")
                print(f"windows_git_bash -> windows: {src} -> {result}, expected: {expected}")
                self.assertEqual(expected, result)

    def test_windows_to_wsl(self):
        cases = [
            ("C:\\Users\\Test", "/mnt/c/Users/Test"),
            ("c:\\Users\\Test", "/mnt/c/Users/Test"),
            ("c:/Users/Test", "/mnt/c/Users/Test"),
            ("D:\\", "/mnt/d/"),
            ("E:\\Folder\\Sub", "/mnt/e/Folder/Sub"),
            ("some\\relative\\path", "some/relative/path"),
            ("C:/Users/Test", "/mnt/c/Users/Test"),  # mixed slashes
        ]
        for src, expected in cases:
            with self.subTest(src=src):
                result = convert_path(src, "windows", "wsl")
                print(f"windows -> wsl: {src} -> {result}, expected: {expected}")
                self.assertEqual(expected, result)

    def test_windows_to_windows_git_bash(self):
        cases = [
            ("C:\\Users\\Test", "/c/Users/Test"),
            ("c:\\Users\\Test", "/c/Users/Test"),
            ("D:\\", "/d/"),
            ("E:\\Folder\\Sub", "/e/Folder/Sub"),
            ("some\\relative\\path", "some/relative/path"),
            ("C:/Users/Test", "/c/Users/Test"),  # mixed slashes
        ]
        for src, expected in cases:
            with self.subTest(src=src):
                result = convert_path(src, "windows", "windows_git_bash")
                print(f"windows -> windows_git_bash: {src} -> {result}, expected: {expected}")
                self.assertEqual(expected, result)

    def test_edge_and_identity_cases(self):
        # Empty path
        self.assertEqual("", convert_path("", "windows", "wsl"))
        self.assertEqual("", convert_path("", "wsl", "windows"))
        self.assertEqual("", convert_path("", "wsl", "windows_git_bash"))
        # Identity
        self.assertEqual("C:\\Users\\Test", convert_path("C:\\Users\\Test", "windows", "windows"))
        self.assertEqual("/c/Users/Test", convert_path("/c/Users/Test", "wsl", "wsl"))
        self.assertEqual("/c/Users/Test", convert_path("/c/Users/Test", "windows_git_bash", "windows_git_bash"))
        # Unknown destination => unchanged
        self.assertEqual("/c/path", convert_path("/c/path", "unknown", "windows"))
        self.assertEqual("C:/path", convert_path("C:/path", "windows", "unknown"))
        self.assertEqual("/c/path", convert_path("/c/path", "wsl", "unknown"))
        # Relative conversions already covered; recheck both directions
        self.assertEqual("relative/path", convert_path("relative/path", "wsl", "windows"))
        self.assertEqual("relative/path", convert_path(r"relative\path", "windows", "wsl"))


if __name__ == '__main__':
    unittest.main()
