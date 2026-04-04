"""
distro.py — Detects the Linux distribution and returns support status.

Supported tiers:
    FULL    — Ubuntu / Debian (apt-based). All features available.
    PARTIAL — Fedora / Arch / openSUSE. Detection works, install cmds vary.
    UNSUPPORTED — Everything else. Graceful exit with a friendly message.

This is the first thing hardware_compat checks before doing anything else.
"""

import sys
import os


# ─── Support registry ─────────────────────────────────────────────────────────

DISTRO_SUPPORT = {
    # id from /etc/os-release : (tier, pkg_manager, install_cmd)
    "ubuntu":   ("FULL",    "apt", "sudo apt install -y {pkg}"),
    "debian":   ("FULL",    "apt", "sudo apt install -y {pkg}"),
    "linuxmint":("FULL",    "apt", "sudo apt install -y {pkg}"),
    "pop":      ("FULL",    "apt", "sudo apt install -y {pkg}"),
    "elementary":("FULL",   "apt", "sudo apt install -y {pkg}"),
    "kali":     ("FULL",    "apt", "sudo apt install -y {pkg}"),
    "raspbian": ("FULL",    "apt", "sudo apt install -y {pkg}"),

    "fedora":   ("PARTIAL", "dnf", "sudo dnf install -y {pkg}"),
    "rhel":     ("PARTIAL", "dnf", "sudo dnf install -y {pkg}"),
    "centos":   ("PARTIAL", "dnf", "sudo dnf install -y {pkg}"),
    "arch":     ("PARTIAL", "pacman", "sudo pacman -S --noconfirm {pkg}"),
    "manjaro":  ("PARTIAL", "pacman", "sudo pacman -S --noconfirm {pkg}"),
    "opensuse-leap":    ("PARTIAL", "zypper", "sudo zypper install -y {pkg}"),
    "opensuse-tumbleweed": ("PARTIAL", "zypper", "sudo zypper install -y {pkg}"),
}

UNSUPPORTED_MESSAGE = """
╔══════════════════════════════════════════════════════════════════╗
║           hardware-compat — Unsupported Distribution            ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  Your distribution: {distro_name:<36}║
║                                                                  ║
║  hardware-compat currently has full support for:                 ║
║    • Ubuntu / Debian / Linux Mint / Pop!_OS                      ║
║    • Elementary OS / Kali Linux / Raspberry Pi OS                ║
║                                                                  ║
║  Partial support (detection only, no auto-install) for:          ║
║    • Fedora / RHEL / CentOS                                       ║
║    • Arch Linux / Manjaro                                        ║
║    • openSUSE Leap / Tumbleweed                                   ║
║                                                                  ║
║  The developer is actively working on extending compatibility     ║
║  to more Linux distributions. If you'd like your distro          ║
║  supported, please open an issue or contribute:                  ║
║    https://github.com/yourusername/hardware-compat               ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""

PARTIAL_MESSAGE = """
⚠  hardware-compat has partial support for {distro_name}.
   Hardware detection will run fully, but automatic driver
   installation commands may not work on your package manager.
   Commands will be shown for your review — run them manually.
"""


# ─── Detection ────────────────────────────────────────────────────────────────

def detect_distro() -> dict:
    """
    Reads /etc/os-release and returns a distro profile dict.

    Returns:
        {
            "id":           "ubuntu",
            "name":         "Ubuntu",
            "version":      "24.04",
            "codename":     "noble",
            "tier":         "FULL" | "PARTIAL" | "UNSUPPORTED",
            "pkg_manager":  "apt" | "dnf" | "pacman" | "zypper" | None,
            "install_cmd":  "sudo apt install -y {pkg}" | ...,
        }
    """
    info = _read_os_release()
    distro_id   = info.get("ID", "").lower().strip('"')
    distro_name = info.get("PRETTY_NAME", distro_id).strip('"')
    version     = info.get("VERSION_ID", "").strip('"')
    codename    = info.get("VERSION_CODENAME", "").strip('"')

    # Also check ID_LIKE for derivatives (e.g. LinuxMint has ID_LIKE=ubuntu)
    id_like = info.get("ID_LIKE", "").lower().strip('"').split()

    support = DISTRO_SUPPORT.get(distro_id)

    # Fall back to ID_LIKE if direct ID not found
    if not support:
        for like in id_like:
            support = DISTRO_SUPPORT.get(like)
            if support:
                break

    if support:
        tier, pkg_manager, install_cmd = support
    else:
        tier, pkg_manager, install_cmd = "UNSUPPORTED", None, None

    return {
        "id":           distro_id,
        "name":         distro_name,
        "version":      version,
        "codename":     codename,
        "tier":         tier,
        "pkg_manager":  pkg_manager,
        "install_cmd":  install_cmd,
    }


def check_and_exit_if_unsupported(distro: dict) -> None:
    """
    Call this at startup. Prints a message and exits cleanly
    if the distro is unsupported or partially supported.
    """
    tier = distro["tier"]
    name = distro["name"]

    if tier == "UNSUPPORTED":
        print(UNSUPPORTED_MESSAGE.format(distro_name=name))
        sys.exit(0)  # Clean exit — not an error, just not supported yet

    if tier == "PARTIAL":
        print(PARTIAL_MESSAGE.format(distro_name=name))
        # Don't exit — continue with detection-only mode


def _read_os_release() -> dict:
    """Parses /etc/os-release into a dict."""
    result = {}
    paths = ["/etc/os-release", "/usr/lib/os-release"]
    for path in paths:
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        key, _, val = line.partition("=")
                        result[key.strip()] = val.strip().strip('"')
            break
    return result
