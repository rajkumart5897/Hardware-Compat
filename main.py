"""
main.py — hardware-compat entry point.

Usage:
    python3 main.py              # Full scan + interactive fix prompt
    python3 main.py --report     # Report only, no fix prompt
    python3 main.py --json       # Output raw JSON (for GUI consumption)
    python3 main.py --check-only # Just check distro support and exit
"""

import argparse
import json
import sys
import logging
import os

from hardware_compat.distro      import detect_distro, check_and_exit_if_unsupported
from hardware_compat.detector    import scan_hardware
from hardware_compat.recommender import build_recommendations
from hardware_compat.cli         import (
    print_hardware_summary,
    print_recommendations,
    prompt_and_apply_fixes,
    print_footer,
)


# ─── Logging ──────────────────────────────────────────────────────────────────

def _setup_logging():
    log_path = "/var/log/hardware-compat.log"
    try:
        logging.basicConfig(
            filename=log_path,
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    except PermissionError:
        # Fallback to home dir if /var/log isn't writable
        log_path = os.path.expanduser("~/.hardware-compat.log")
        logging.basicConfig(
            filename=log_path,
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
        )
    return log_path


# ─── JSON output (for GUI) ────────────────────────────────────────────────────

def _to_json_safe(obj):
    """Recursively make objects JSON-serialisable."""
    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_json_safe(i) for i in obj]
    return obj


def output_json(distro, scan, recommendations):
    payload = {
        "distro":          _to_json_safe(distro),
        "bios":            _to_json_safe(scan.get("bios", {})),
        "battery":         _to_json_safe(scan.get("battery", {})),
        "devices":         _to_json_safe(scan["devices"]),
        "warnings":        scan.get("warnings", []),
        "recommendations": _to_json_safe(recommendations),
    }
    print(json.dumps(payload, indent=2))


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="hardware-compat",
        description="Hardware compatibility checker and driver advisor for Linux.",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Show report only, skip the interactive fix prompt.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON (for GUI or scripting).",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check if this distro is supported, then exit.",
    )
    args = parser.parse_args()

    log_path = _setup_logging()
    logging.info("hardware-compat started")

    # ── Step 1: Distro check ──────────────────────────────────────────────────
    distro = detect_distro()
    logging.info(f"Distro: {distro['name']} {distro['version']} (tier={distro['tier']})")

    if args.check_only:
        print(f"Distribution: {distro['name']} {distro['version']}")
        print(f"Support tier: {distro['tier']}")
        sys.exit(0)

    # Gracefully exits here if UNSUPPORTED, prints partial warning if PARTIAL
    check_and_exit_if_unsupported(distro)

    # ── Step 2: Hardware scan ─────────────────────────────────────────────────
    if not args.json:
        print("\n  Scanning hardware...", end="", flush=True)

    scan = scan_hardware()

    if not args.json:
        print(f" found {len(scan['devices'])} devices.\n")

    logging.info(f"Scan complete: {len(scan['devices'])} devices found")
    for dev in scan["devices"]:
        logging.info(
            f"  {dev['category']:12} {dev['status']:10} "
            f"driver={dev.get('driver') or 'none':20} {dev['name'][:50]}"
        )

    # ── Step 3: Build recommendations ────────────────────────────────────────
    recommendations = build_recommendations(
        scan["devices"], scan.get("bios", {}),
        scan.get("battery", {}), distro
    )

    logging.info(f"Recommendations: {len(recommendations)} issues found")
    for rec in recommendations:
        logging.info(
            f"  [{rec['severity']}] {rec['device']['name']}: {rec['issue'][:80]}"
        )

    # ── Step 4: Output ────────────────────────────────────────────────────────
    if args.json:
        output_json(distro, scan, recommendations)
        sys.exit(0)

    print_hardware_summary(scan, distro)
    print_recommendations(recommendations)
    print_footer(recommendations)

    if not args.report:
        prompt_and_apply_fixes(recommendations, distro)

    logging.info("hardware-compat finished")


if __name__ == "__main__":
    main()
