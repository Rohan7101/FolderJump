#!/usr/bin/env python3
"""
Unit and integration tests for FolderJump.
Covers matching, case-insensitivity, spaces/special characters,
error handling, interactive selection, cancellation, dry-run,
and zsh shell navigation.
"""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

# Import modular components directly from folderjump.py
import folderjump


class TestFolderJumpUnit(unittest.TestCase):
    def setUp(self):
        # Create an isolated temporary directory tree outside the repo
        self.test_dir = tempfile.mkdtemp(prefix="fj_test_")
        self.test_path = Path(self.test_dir)

        # Setup standard subfolders
        self.doc_folder = self.test_path / "Documents" / "college-mca"
        self.doc_folder.mkdir(parents=True)

        self.desk_folder = self.test_path / "Desktop" / "Linux Project"
        self.desk_folder.mkdir(parents=True)

        self.down_folder = self.test_path / "Downloads" / "My Notes (v1) [2026] & test"
        self.down_folder.mkdir(parents=True)

        self.hidden_folder = self.test_path / "Documents" / ".hidden_project"
        self.hidden_folder.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_case_insensitive_matching(self):
        """Case-insensitive search should match regardless of query case."""
        matches = folderjump.find_matching_folders([self.test_path], "mCa")
        matched_names = [p.name for p in matches]
        self.assertIn("college-mca", matched_names)

    def test_spaces_and_special_characters(self):
        """Folders with spaces, brackets, parentheses, and ampersands must match correctly."""
        matches = folderjump.find_matching_folders([self.test_path], "Notes (v1)")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].name, "My Notes (v1) [2026] & test")

    def test_environment_variable_roots(self):
        """Custom search roots specified via FOLDERJUMP_ROOTS must be recognized."""
        custom_dir = self.test_path / "CustomRoot"
        custom_dir.mkdir()
        try:
            os.environ["FOLDERJUMP_ROOTS"] = str(custom_dir)
            roots = folderjump.get_search_roots()
            self.assertIn(custom_dir.resolve(), roots)
        finally:
            os.environ.pop("FOLDERJUMP_ROOTS", None)

    def test_hidden_directories_ignored(self):
        """Hidden folders starting with . should be ignored."""
        matches = folderjump.find_matching_folders([self.test_path], "hidden_project")
        self.assertEqual(len(matches), 0)

    def test_inaccessible_directory(self):
        """Folders with permission denied should be skipped gracefully without error."""
        locked = self.test_path / "Documents" / "locked_dir"
        locked.mkdir()
        try:
            os.chmod(locked, 0o000)
            # Searching should not raise PermissionError
            matches = folderjump.find_matching_folders([self.test_path], "college")
            self.assertEqual(len(matches), 1)
        finally:
            os.chmod(locked, 0o755)

    def test_no_matches(self):
        """Searching for a non-existent folder returns empty list."""
        matches = folderjump.find_matching_folders([self.test_path], "nonexistent_dir_name")
        self.assertEqual(len(matches), 0)

    def test_multiple_matches_ranking(self):
        """Exact matches and prefix matches rank before arbitrary substring matches."""
        (self.test_path / "linux").mkdir()
        (self.test_path / "linux-kernel").mkdir()
        (self.test_path / "my-linux-notes").mkdir()

        matches = folderjump.find_matching_folders([self.test_path], "linux")
        matched_names = [p.name for p in matches]
        # 'linux' exact match must be first
        self.assertEqual(matched_names[0], "linux")
        self.assertIn("linux-kernel", matched_names)
        self.assertIn("my-linux-notes", matched_names)


class TestFolderJumpCLI(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="fj_cli_")
        self.test_path = Path(self.test_dir)
        self.script_path = str(Path(__file__).parent / "folderjump.py")

        # Create sample folder hierarchy
        self.target_one = self.test_path / "SingleMatchFolder"
        self.target_one.mkdir()

        self.multi_a = self.test_path / "Multi Alpha"
        self.multi_a.mkdir()
        self.multi_b = self.test_path / "Multi Beta"
        self.multi_b.mkdir()

        self.special = self.test_path / "Course Notes [MCA] & Labs"
        self.special.mkdir()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def run_fj(self, args, input_text=""):
        cmd = [sys.executable, self.script_path] + args
        proc = subprocess.run(
            cmd,
            input=input_text,
            text=True,
            capture_output=True,
        )
        return proc

    def test_cli_single_match_auto_accept(self):
        """Single match accepts default choice on Enter."""
        proc = self.run_fj(["-r", str(self.test_path), "SingleMatch"], input_text="\n")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), str(self.target_one.resolve()))
        self.assertIn("Found 1 matching folder", proc.stderr)

    def test_cli_multiple_matches_select(self):
        """Multiple matches display numbered menu and return selected path."""
        proc = self.run_fj(["-r", str(self.test_path), "Multi"], input_text="2\n")
        self.assertEqual(proc.returncode, 0)
        selected_path = proc.stdout.strip()
        self.assertTrue(selected_path.endswith("Multi Beta") or selected_path.endswith("Multi Alpha"))
        self.assertIn("Found 2 matching folders", proc.stderr)

    def test_cli_cancellation(self):
        """Entering 'q' cancels selection and exits with code 130."""
        proc = self.run_fj(["-r", str(self.test_path), "Multi"], input_text="q\n")
        self.assertEqual(proc.returncode, 130)
        self.assertEqual(proc.stdout.strip(), "")
        self.assertIn("cancelled", proc.stderr.lower())

    def test_cli_invalid_selection(self):
        """Entering an out-of-range number triggers error message and exits with 1."""
        proc = self.run_fj(["-r", str(self.test_path), "Multi"], input_text="99\n")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("out of range", proc.stderr)

    def test_cli_no_match(self):
        """No matches exits with code 1."""
        proc = self.run_fj(["-r", str(self.test_path), "DoesntExist"])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("No matching folders found", proc.stderr)

    def test_cli_missing_root(self):
        """Non-existent root argument exits with code 2."""
        proc = self.run_fj(["-r", "/non/existent/directory/12345", "query"])
        self.assertEqual(proc.returncode, 2)
        self.assertIn("does not exist", proc.stderr)

    def test_cli_dry_run(self):
        """Dry run previews destination on stderr and outputs nothing to stdout."""
        proc = self.run_fj(["--dry-run", "-r", str(self.test_path), "SingleMatch"], input_text="\n")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "")
        self.assertIn("[DRY-RUN]", proc.stderr)
        self.assertIn("Directory was not changed", proc.stderr)

    def test_cli_help(self):
        """--help displays synopsis and exits with 0."""
        proc = self.run_fj(["--help"])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Search for folders by partial name", proc.stdout)


class TestZshIntegration(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="fj_zsh_")
        self.test_path = Path(self.test_dir)
        self.target_dir = self.test_path / "SubFolder With Spaces"
        self.target_dir.mkdir()

        self.zsh_script = Path(__file__).parent / "folderjump.zsh"
        self.py_script = Path(__file__).parent / "folderjump.py"

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_zsh_cd_navigation(self):
        """Verify that sourcing folderjump.zsh and calling fj changes parent shell directory."""
        shell_script = f"""
source "{self.zsh_script.resolve()}"
export FOLDERJUMP_PATH="{self.py_script.resolve()}"
cd "{self.test_dir}"
echo "BEFORE:$PWD"
fj -r "{self.test_dir}" "SubFolder" <<< "1" >/dev/null 2>&1
echo "AFTER:$PWD"
"""
        proc = subprocess.run(
            ["/bin/zsh", "-c", shell_script],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        lines = [line.strip() for line in proc.stdout.splitlines() if ":" in line]
        output_dict = dict(line.split(":", 1) for line in lines)

        before = Path(output_dict["BEFORE"]).resolve()
        after = Path(output_dict["AFTER"]).resolve()

        self.assertEqual(before, self.test_path.resolve())
        self.assertEqual(after, self.target_dir.resolve())
        self.assertNotEqual(before, after)

    def test_zsh_help_flag(self):
        """Verify that fj --help prints help text directly and does not attempt cd."""
        shell_script = f"""
source "{self.zsh_script.resolve()}"
export FOLDERJUMP_PATH="{self.py_script.resolve()}"
fj --help
"""
        proc = subprocess.run(
            ["/bin/zsh", "-c", shell_script],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("usage: folderjump", proc.stdout)
        self.assertNotIn("resolved path is not a directory", proc.stderr)


if __name__ == "__main__":
    unittest.main()
