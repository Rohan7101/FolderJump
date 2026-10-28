# FolderJump — Zsh Shell Integration for macOS
#
# Enables instant terminal directory navigation based on folderjump.py output.
# A Python subprocess cannot change its parent shell's working directory, so this
# zsh function captures the selected path and performs the actual 'cd'.
#
# Quick Setup:
#   source /Applications/MCA/Linux/FolderJump/folderjump.zsh
#
# Usage:
#   fj <partial_folder_name>
#   fj -r ~/Documents <partial_name>
#   fj --dry-run <name>
#   fj --help

# Determine the directory where this script resides when sourced in zsh
_FOLDERJUMP_DIR="${${(%):-%x}:A:h}"

fj() {
    # Path to Python implementation
    local py_script="${FOLDERJUMP_PATH:-${_FOLDERJUMP_DIR}/folderjump.py}"

    if [ ! -f "$py_script" ]; then
        echo "folderjump: cannot find folderjump.py at $py_script" >&2
        echo "Please set FOLDERJUMP_PATH to the full path of folderjump.py" >&2
        return 1
    fi

    # Ensure Python 3 is available
    if ! command -v python3 >/dev/null 2>&1; then
        echo "folderjump: python3 is required but not found in PATH" >&2
        return 1
    fi

    # If asking for help, run directly so stdout prints directly to terminal
    for arg in "$@"; do
        if [ "$arg" = "-h" ] || [ "$arg" = "--help" ]; then
            python3 "$py_script" "$@"
            return $?
        fi
    done

    # Execute search program. Prompts and menu are printed to stderr;
    # machine-readable destination path is printed to stdout.
    local target_dir
    target_dir=$(python3 "$py_script" "$@")
    local exit_code=$?

    # If successful and target path returned, perform directory jump
    if [ $exit_code -eq 0 ] && [ -n "$target_dir" ]; then
        if [ -d "$target_dir" ]; then
            cd "$target_dir" || return 1
        else
            echo "folderjump: resolved path is not a directory: $target_dir" >&2
            return 1
        fi
    fi

    return $exit_code
}
