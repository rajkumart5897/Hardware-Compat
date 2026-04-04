"""
cli.py — Terminal output for hardware-compat.

Prints a structured, colour-coded report of:
    1. Hardware summary (all detected devices + their status)
    2. Recommendations (issues sorted by severity with exact fix commands)
    3. Interactive yes/no prompt to apply fixes (Ubuntu/Debian only)

Colour codes:
    GREEN   — OPTIMAL / no issues
    YELLOW  — SUBOPTIMAL / LOW severity
    RED     — MISSING / BLOCKED / HIGH severity
    CYAN    — section headers
    BOLD    — device names
"""

import subprocess
import sys
import shutil

# ─── ANSI colours ─────────────────────────────────────────────────────────────
# Gracefully degrade if terminal doesn't support colour

def _supports_color():
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

if _supports_color():
    R  = "\033[0;31m"   # red
    G  = "\033[0;32m"   # green
    Y  = "\033[0;33m"   # yellow
    C  = "\033[0;36m"   # cyan
    B  = "\033[1m"      # bold
    DIM= "\033[2m"      # dim
    NC = "\033[0m"      # reset
else:
    R = G = Y = C = B = DIM = NC = ""

SEV_COLOR = {"HIGH": R, "MEDIUM": Y, "LOW": Y}
STATUS_COLOR = {
    "OPTIMAL":    G,
    "SUBOPTIMAL": Y,
    "MISSING":    R,
    "BLOCKED":    R,
    "DEGRADED":   R,
    "UNKNOWN":    DIM,
}

WIDTH = 70


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _line(char="─"):
    return char * WIDTH

def _header(text):
    print(f"\n{C}{B}{_line('═')}{NC}")
    pad = (WIDTH - len(text) - 2) // 2
    print(f"{C}{B}{'═' * pad} {text} {'═' * (WIDTH - pad - len(text) - 2)}{NC}")
    print(f"{C}{B}{_line('═')}{NC}")

def _section(text):
    print(f"\n{C}{_line('─')}{NC}")
    print(f"{C}  {text}{NC}")
    print(f"{C}{_line('─')}{NC}")

def _status_badge(status):
    color = STATUS_COLOR.get(status, DIM)
    return f"{color}[{status}]{NC}"

def _sev_badge(severity):
    color = SEV_COLOR.get(severity, DIM)
    return f"{color}[{severity}]{NC}"


# ─── Hardware summary ─────────────────────────────────────────────────────────

def print_hardware_summary(scan: dict, distro: dict):
    _header("HARDWARE COMPATIBILITY REPORT")

    # Distro info
    tier_color = G if distro["tier"] == "FULL" else Y
    print(f"\n  {B}Distribution:{NC} {distro['name']} {distro['version']}")
    print(f"  {B}Support Tier:{NC} {tier_color}{distro['tier']}{NC}")

    if distro["tier"] == "PARTIAL":
        print(f"  {Y}  ⚠  Detection only — install commands need manual adaptation{NC}")

    # BIOS
    bios = scan.get("bios", {})
    if bios:
        print(f"  {B}BIOS:{NC}         {bios.get('version', 'unknown')} "
              f"({bios.get('date', 'unknown')})")

    # Battery
    battery = scan.get("battery", {})
    if battery:
        health = battery.get("health_pct")
        health_color = G if health and health >= 80 else \
                       Y if health and health >= 60 else R
        print(f"  {B}Battery:{NC}      "
              f"{health_color}{health}% health{NC}, "
              f"{battery.get('capacity_pct', '?')}% charge, "
              f"status: {battery.get('status', 'unknown')}")

    # Missing tools
    if scan.get("warnings"):
        print(f"\n  {Y}Missing tools (install for better detection):{NC}")
        for w in scan["warnings"]:
            print(f"    {DIM}• {w}{NC}")

    # Device table
    _section("Detected Devices")

    # Group by category
    from collections import defaultdict
    by_category = defaultdict(list)
    for dev in scan["devices"]:
        by_category[dev["category"]].append(dev)

    category_order = ["GPU", "WIFI", "ETHERNET", "BLUETOOTH", "AUDIO",
                      "WEBCAM", "INPUT", "STORAGE", "OTHER"]

    for cat in category_order:
        devs = by_category.get(cat, [])
        if not devs:
            continue
        print(f"\n  {B}{cat}{NC}")
        for dev in devs:
            badge  = _status_badge(dev["status"])
            driver = dev.get("driver") or f"{DIM}no driver{NC}"
            fw_tag = f" {Y}[FW UPDATE]{NC}" \
                     if dev.get("firmware_update_available") else ""
            blocked_tag = ""
            if dev.get("blocked"):
                blocked_tag = f" {R}[{dev.get('block_type','?').upper()} BLOCKED]{NC}"

            print(f"    {badge} {B}{dev['name'][:45]:<45}{NC}")
            print(f"         driver: {driver}{fw_tag}{blocked_tag}")


# ─── Recommendations ──────────────────────────────────────────────────────────

def print_recommendations(recommendations: list):
    if not recommendations:
        _section("Recommendations")
        print(f"\n  {G}✓  No issues found. All hardware appears to be working correctly.{NC}\n")
        return

    _section(f"Recommendations  ({len(recommendations)} issue(s) found)")

    for i, rec in enumerate(recommendations, 1):
        dev  = rec["device"]
        sev  = rec["severity"]
        print(f"\n  {B}{i}. {dev['name']}{NC}  {_sev_badge(sev)}")
        print(f"     {rec['issue']}")

        if rec.get("docs_url"):
            print(f"     {DIM}docs: {rec['docs_url']}{NC}")

        if rec["fix_steps"]:
            print(f"     {C}Fix steps:{NC}")
            for step in rec["fix_steps"]:
                print(f"       {DIM}→ {step['description']}{NC}")
                if step.get("cmd"):
                    print(f"         {B}$ {step['cmd']}{NC}")

        if rec.get("reboot_required"):
            print(f"     {Y}⚠  Reboot required after applying this fix{NC}")


# ─── Interactive fix prompt ───────────────────────────────────────────────────

def prompt_and_apply_fixes(recommendations: list, distro: dict):
    """
    For FULL (Ubuntu/Debian) systems only.
    Walks through each recommendation and asks the user
    if they want to apply the fix commands.
    """
    if distro["tier"] != "FULL":
        print(f"\n{Y}Auto-apply is only available on Ubuntu/Debian systems.{NC}")
        print("Please run the commands above manually.\n")
        return

    actionable = [
        r for r in recommendations
        if r["fix_steps"] and any(s.get("cmd") for s in r["fix_steps"])
        and r["device"].get("category") not in ("BATTERY", "FIRMWARE")
    ]

    if not actionable:
        print(f"\n{DIM}No automatically applicable fixes available.{NC}\n")
        return

    _section("Apply Fixes Interactively")
    print(f"  {Y}You will be asked before each fix is applied.{NC}")
    print(f"  {DIM}Type 'y' to apply, 'n' to skip, 'q' to quit.{NC}\n")

    reboot_needed = False

    for rec in actionable:
        dev = rec["device"]
        print(f"\n  {B}Fix: {dev['name']}{NC}  {_sev_badge(rec['severity'])}")
        print(f"  {rec['issue']}\n")

        for step in rec["fix_steps"]:
            if not step.get("cmd"):
                print(f"  {DIM}  (manual step) {step['description']}{NC}")
                continue

            print(f"  {DIM}  → {step['description']}{NC}")
            print(f"  {B}  $ {step['cmd']}{NC}")
            answer = _ask("  Apply this command? [y/n/q]: ")

            if answer == "q":
                print(f"\n{Y}Stopped. Remaining fixes were skipped.{NC}\n")
                return
            elif answer == "y":
                _run_cmd(step["cmd"])
                if rec.get("reboot_required"):
                    reboot_needed = True
            else:
                print(f"  {DIM}Skipped.{NC}")

    if reboot_needed:
        print(f"\n{Y}⚠  One or more fixes require a reboot to take effect.{NC}")
        answer = _ask("  Reboot now? [y/n]: ")
        if answer == "y":
            subprocess.run(["sudo", "reboot"])


def _ask(prompt: str) -> str:
    try:
        return input(prompt).strip().lower()
    except (KeyboardInterrupt, EOFError):
        print()
        return "n"


def _run_cmd(cmd: str):
    print(f"  {DIM}Running...{NC}")
    try:
        result = subprocess.run(
            cmd, shell=True, text=True,
            capture_output=False  # let output stream to terminal
        )
        if result.returncode != 0:
            print(f"  {R}Command exited with code {result.returncode}{NC}")
        else:
            print(f"  {G}✓ Done{NC}")
    except Exception as e:
        print(f"  {R}Error: {e}{NC}")


# ─── Footer ───────────────────────────────────────────────────────────────────

def print_footer(recommendations: list):
    high   = sum(1 for r in recommendations if r["severity"] == "HIGH")
    medium = sum(1 for r in recommendations if r["severity"] == "MEDIUM")
    low    = sum(1 for r in recommendations if r["severity"] == "LOW")

    print(f"\n{_line()}")
    print(f"  Summary: {R}{high} HIGH{NC}  {Y}{medium} MEDIUM{NC}  {Y}{low} LOW{NC}")
    print(f"  Log saved to: /var/log/hardware-compat.log")
    print(f"{_line()}\n")
