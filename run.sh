#!/usr/bin/env bash
# ==============================================================================
# Local LAMMPS Assistant Launcher for Linux / POSIX
# ==============================================================================
set -e

# Resolve script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Ensure ~/.local/bin is in PATH for lmp and local tools
if [[ -d "$HOME/.local/bin" && ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    export PATH="$HOME/.local/bin:$PATH"
fi

# Detect Python environment
PYTHON_BIN=""
if [[ -x "$HOME/.venv/bin/python" ]]; then
    PYTHON_BIN="$HOME/.venv/bin/python"
elif [[ -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
    PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON_BIN="$(command -v python3)"
elif command -v python &>/dev/null; then
    PYTHON_BIN="$(command -v python)"
else
    echo "[ERROR] Python 3 not found on system." >&2
    exit 1
fi

# CLI subcommands
case "$1" in
    check|--check|status)
        shift
        exec "$PYTHON_BIN" scripts/check_lammps.py "$@"
        ;;
    test|--test)
        shift
        exec "$PYTHON_BIN" -m unittest discover -s tests -p "test_*.py" "$@"
        ;;
    help|--help|-h)
        echo "Usage: ./run.sh [command|options]"
        echo ""
        echo "Commands:"
        echo "  (default)    Start the web application server on localhost"
        echo "  check        Run diagnostic check for LAMMPS binary & packages"
        echo "  test         Run the complete test suite"
        echo "  help         Show this message"
        echo ""
        echo "Examples:"
        echo "  ./run.sh"
        echo "  ./run.sh check"
        echo "  ./run.sh test"
        exit 0
        ;;
    *)
        exec "$PYTHON_BIN" run.py "$@"
        ;;
esac
