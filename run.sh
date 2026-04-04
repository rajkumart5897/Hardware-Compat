#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# run.sh — hardware-compat launcher
#
# Usage:
#   ./run.sh           → CLI full scan + interactive fix prompt
#   ./run.sh --report  → CLI report only
#   ./run.sh --json    → raw JSON output
#   ./run.sh --gui     → start the web GUI at http://localhost:7474
# ─────────────────────────────────────────────────────────────────

# Always run from the project root, regardless of where you call this from
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Dependency check ──────────────────────────────────────────────
check_deps() {
    local missing=()
    for tool in python3 lspci lsusb rfkill; do
        command -v "$tool" &>/dev/null || missing+=("$tool")
    done
    if [ ${#missing[@]} -gt 0 ]; then
        echo ""
        echo "  Missing system tools: ${missing[*]}"
        echo "  Install with: sudo apt install pciutils usbutils rfkill"
        echo ""
    fi
}

# ── GUI mode ──────────────────────────────────────────────────────
if [[ "$1" == "--gui" ]]; then
    echo ""
    echo "  Starting hardware-compat GUI…"
    check_deps
    exec python3 gui_server.py "${@:2}"
fi

# ── CLI mode ─────────────────────────────────────────────────────
check_deps
exec python3 main.py "$@"
