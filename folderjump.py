#!/usr/bin/env python3
"""
FolderJump — A Folder Search and Navigation Tool for macOS.

This program searches designated root directories for folders matching a full
or partial name, presents an interactive numbered list, and prints the selected
folder path to stdout (for shell cd integration) while writing all prompts and
status messages to stderr.
"""

import argparse
import os
from pathlib import Path
import sys
from typing import List, Optional


# Standard directories searched by default on macOS
DEFAULT_SEARCH_NAMES = ["Documents", "Desktop", "Downloads"]

# Directory names to skip to prevent scanning slow or irrelevant trees
IGNORE_DIRS = {
    ".git",
    ".svn",
    ".hg",
    ".DS_Store",
    ".Trash",
    ".cache",
    ".npm",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "Library",
}


def parse_arguments(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments using argparse."""
    parser = argparse.ArgumentParser(
        prog="folderjump",
        description="Search for folders by partial name and select one to jump to.",
        epilog=(
            "Examples:\n"
            "  folderjump linux             # Search default folders for 'linux'\n"
            "  folderjump -r ~/Documents py # Search only ~/Documents for 'py'\n"
            "  folderjump --dry-run project # Preview destination without navigating\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "query",
        nargs="?",
        default="",
        help="Full or partial folder name to search for (case-insensitive).",
    )
    parser.add_argument(
        "-r",
        "--root",
        dest="roots",
        action="append",
        metavar="DIR",
        help="Custom root directory to search (can be specified multiple times).",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Show which folder would be selected without changing directory.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print verbose details about directories scanned and skipped.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=5,
        metavar="N",
        help="Maximum folder recursion depth (default: 5).",
    )

    return parser.parse_args(args)


def get_search_roots(custom_roots: Optional[List[str]] = None, verbose: bool = False) -> List[Path]:
    """
    Resolve and validate directories to search.

    If custom_roots are provided, verifies that each exists.
    Otherwise, checks FOLDERJUMP_ROOTS environment variable, or defaults to
    ~/Documents, ~/Desktop, ~/Downloads, and /Applications/MCA if present.
    """
    roots: List[Path] = []

    if custom_roots:
        for r in custom_roots:
            p = Path(r).expanduser().resolve()
            if not p.exists():
                sys.stderr.write(f"folderjump: error: search root does not exist: {r}\n")
                sys.exit(2)
            if not p.is_dir():
                sys.stderr.write(f"folderjump: error: search root is not a directory: {r}\n")
                sys.exit(2)
            roots.append(p)
    else:
        # Check if user configured custom default roots via environment variable
        env_roots = os.environ.get("FOLDERJUMP_ROOTS")
        if env_roots:
            sep = ":" if ":" in env_roots and "," not in env_roots else ","
            for r in env_roots.split(sep):
                r = r.strip()
                if r:
                    p = Path(r).expanduser().resolve()
                    if p.is_dir() and p not in roots:
                        roots.append(p)
                    elif verbose:
                        sys.stderr.write(f"folderjump: notice: environment root not found: {r}\n")
        else:
            home = Path.home()
            for name in DEFAULT_SEARCH_NAMES:
                candidate = (home / name).resolve()
                if candidate.is_dir() and candidate not in roots:
                    roots.append(candidate)
                elif verbose:
                    sys.stderr.write(f"folderjump: notice: default root not found: {candidate}\n")

            # Check for college / application course directory if present on this Mac
            mca_dir = Path("/Applications/MCA").resolve()
            if mca_dir.is_dir() and mca_dir not in roots:
                roots.append(mca_dir)

    return roots


def find_matching_folders(
    roots: List[Path],
    query: str,
    max_depth: int = 5,
    verbose: bool = False,
) -> List[Path]:
    """
    Scan root directories for folders matching query (case-insensitive).

    Uses os.walk with followlinks=False to avoid recursive symlink loops.
    Catches PermissionError to skip inaccessible folders gracefully.
    """
    matches: List[Path] = []
    seen = set()
    query_lower = query.strip().lower()

    for root_dir in roots:
        root_str = str(root_dir)
        if verbose:
            sys.stderr.write(f"folderjump: scanning root: {root_str}\n")

        def on_walk_error(err: OSError) -> None:
            if verbose:
                sys.stderr.write(f"folderjump: warning: skipping inaccessible {err.filename}: {err.strerror}\n")

        for dirpath, dirnames, _ in os.walk(root_str, followlinks=False, onerror=on_walk_error):
            # Calculate current recursion depth
            try:
                rel = os.path.relpath(dirpath, start=root_str)
                depth = 0 if rel == "." else len(rel.split(os.sep))
            except ValueError:
                depth = 0

            # Prune directory search if max depth exceeded
            if depth >= max_depth:
                dirnames.clear()
                continue

            # In-place filtering to prune ignored or hidden folders
            filtered_dirnames = []
            for d in dirnames:
                # Skip hidden folders, macOS app bundles (.app), and cache directories
                if d.startswith(".") or d.endswith(".app") or d in IGNORE_DIRS:
                    continue
                filtered_dirnames.append(d)
            dirnames[:] = filtered_dirnames

            # Check each subfolder in the current directory
            for d in dirnames:
                folder_path = Path(dirpath) / d
                folder_name_lower = d.lower()

                # Case-insensitive substring match
                # Also allow matching subpath if user typed e.g. "mca/linux"
                is_match = False
                if query_lower in folder_name_lower:
                    is_match = True
                elif "/" in query_lower:
                    try:
                        rel_path = folder_path.relative_to(root_dir)
                        if query_lower in str(rel_path).lower():
                            is_match = True
                    except ValueError:
                        pass

                if is_match:
                    resolved = folder_path.resolve()
                    if resolved not in seen and resolved.is_dir():
                        seen.add(resolved)
                        matches.append(folder_path)

    # Sort matches: exact match first, then prefix match, then shortest path
    def sort_key(p: Path):
        name_lower = p.name.lower()
        exact = 0 if name_lower == query_lower else 1
        prefix = 0 if name_lower.startswith(query_lower) else 1
        return (exact, prefix, len(str(p)), str(p))

    matches.sort(key=sort_key)
    return matches


def prompt_user_selection(matches: List[Path], is_dry_run: bool = False) -> Optional[Path]:
    """
    Present numbered matches to stderr and read the user's choice.

    Returns the selected Path, or None if the user cancelled.
    """
    count = len(matches)
    if count == 0:
        return None

    if count == 1:
        single = matches[0]
        sys.stderr.write(f"\nFound 1 matching folder:\n")
        sys.stderr.write(f"  [1] {single}\n\n")
        prompt_text = "Select folder [1] (Press Enter to accept, 'q' to cancel): "
        sys.stderr.write(prompt_text)
        sys.stderr.flush()
        try:
            choice = input().strip()
        except (KeyboardInterrupt, EOFError):
            sys.stderr.write("\nSearch cancelled.\n")
            return None

        if choice in ("", "1", "y", "yes"):
            return single
        elif choice.lower() in ("q", "quit", "c", "cancel", "0", "n", "no"):
            sys.stderr.write("Search cancelled.\n")
            return None
        else:
            sys.stderr.write(f"folderjump: Invalid choice '{choice}'. Expected '1' or 'q'.\n")
            sys.exit(1)

    # Multiple matches
    sys.stderr.write(f"\nFound {count} matching folders:\n")
    for idx, path in enumerate(matches, start=1):
        sys.stderr.write(f"  [{idx}] {path}\n")
    sys.stderr.write("\n")

    prompt_text = f"Select a folder [1-{count}] (or 'q' to cancel): "
    sys.stderr.write(prompt_text)
    sys.stderr.flush()
    try:
        choice = input().strip()
    except (KeyboardInterrupt, EOFError):
        sys.stderr.write("\nSearch cancelled.\n")
        return None

    if choice.lower() in ("q", "quit", "c", "cancel", "0"):
        sys.stderr.write("Search cancelled.\n")
        return None

    if not choice.isdigit():
        sys.stderr.write(f"folderjump: Invalid selection '{choice}'. Expected a number between 1 and {count}.\n")
        sys.exit(1)

    selected_idx = int(choice)
    if 1 <= selected_idx <= count:
        return matches[selected_idx - 1]
    else:
        sys.stderr.write(f"folderjump: Selection '{choice}' out of range [1-{count}].\n")
        sys.exit(1)


def main() -> int:
    """Main CLI entry point."""
    args = parse_arguments()

    query = args.query.strip()
    if not query:
        # Prompt user if no query provided interactively
        try:
            sys.stderr.write("Enter folder name to search: ")
            sys.stderr.flush()
            query = input().strip()
        except (KeyboardInterrupt, EOFError):
            sys.stderr.write("\nSearch cancelled.\n")
            return 130
        if not query:
            sys.stderr.write("folderjump: error: no search query provided.\n")
            return 1

    roots = get_search_roots(args.roots, verbose=args.verbose)
    if not roots:
        sys.stderr.write("folderjump: error: no valid search directories found.\n")
        return 1

    matches = find_matching_folders(
        roots=roots,
        query=query,
        max_depth=args.max_depth,
        verbose=args.verbose,
    )

    if not matches:
        root_names = ", ".join(str(r) for r in roots)
        sys.stderr.write(f"folderjump: No matching folders found for '{query}' in: {root_names}\n")
        return 1

    selected = prompt_user_selection(matches, is_dry_run=args.dry_run)
    if selected is None:
        return 130

    if args.dry_run:
        sys.stderr.write(f"\n[DRY-RUN] Selected destination: {selected}\n")
        sys.stderr.write("[DRY-RUN] Directory was not changed.\n")
        return 0

    # Print ONLY the selected path to stdout for the shell function to cd
    print(str(selected))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.stderr.write("\nSearch cancelled.\n")
        sys.exit(130)
