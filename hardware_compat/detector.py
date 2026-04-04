"""
detector.py — Scans system hardware and returns a structured device list.

Uses:
    lspci       — PCI devices (GPU, WiFi, Audio, Ethernet, etc.)
    lsusb       — USB devices (Webcam, Bluetooth, etc.)
    rfkill      — RF device block status (WiFi/BT soft/hard blocks)
    fwupdmgr    — Firmware update availability
    /proc/sys   — Kernel module info
    dmidecode   — BIOS/UEFI version and battery info

Each device is returned as a dict with:
    {
        "id":           unique string (bus address or usb id)
        "name":         human-readable name
        "category":     GPU | WIFI | ETHERNET | AUDIO | BLUETOOTH |
                        WEBCAM | INPUT | STORAGE | OTHER
        "driver":       currently loaded kernel driver or None
        "modules":      list of available kernel modules
        "status":       OPTIMAL | SUBOPTIMAL | MISSING | BLOCKED | UNKNOWN
        "blocked":      True if rfkill-blocked (WiFi/BT only)
        "block_type":   "soft" | "hard" | None
        "firmware_update_available": True | False | None
        "raw":          original lspci/lsusb line
    }
"""

import subprocess
import re
import os
from typing import Optional


# ─── Category classifier ──────────────────────────────────────────────────────

CATEGORY_KEYWORDS = {
    "GPU":       ["vga compatible", "3d controller", "display controller",
                  "graphics", "gpu"],
    "WIFI":      ["network controller", "wireless", "802.11", "wifi", "wlan"],
    "ETHERNET":  ["ethernet controller", "ethernet"],
    "AUDIO":     ["audio device", "multimedia audio", "sound", "audio"],
    "BLUETOOTH": ["bluetooth"],
    "WEBCAM":    ["webcam", "camera", "video"],
    "INPUT":     ["input device", "i2c", "hid", "touchpad", "keyboard"],
    "STORAGE":   ["sata", "nvme", "storage", "raid", "scsi"],
}

# Chipset-internal devices that intentionally have no Linux kernel driver.
# Flagging these as MISSING is a false positive — suppress them entirely.
_DRIVERLESS_OK = {
    "ram memory",           # DRAM controller — managed by BIOS/firmware
    "isa bridge",           # LPC/eSPI bridge — no driver needed on modern kernels
    "lpc controller",       # synonym for ISA bridge
    "espi controller",      # newer Intel eSPI variant
    "pci host bridge",      # root complex, handled by the kernel core
    "host bridge",          # same
    "system peripheral",    # generic catch-all chipset peripherals
    "non-essential instrumentation",  # Intel telemetry blocks
}

def _is_driverless_ok(name: str) -> bool:
    """Return True for chipset devices that are expected to have no driver."""
    n = name.lower()
    return any(fragment in n for fragment in _DRIVERLESS_OK)

def _classify_category(description: str) -> str:
    desc = description.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(k in desc for k in keywords):
            return category
    return "OTHER"


# ─── Status classifier ────────────────────────────────────────────────────────

def _classify_status(driver: Optional[str], modules: list,
                     blocked: bool) -> str:
    if blocked:
        return "BLOCKED"
    if not driver and not modules:
        return "MISSING"
    if not driver and modules:
        return "SUBOPTIMAL"   # module exists but not loaded
    if driver:
        return "OPTIMAL"
    return "UNKNOWN"


# ─── lspci parser ─────────────────────────────────────────────────────────────

def _run(cmd: list) -> str:
    """Run a subprocess command, return stdout or empty string on failure."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15
        )
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def _parse_lspci() -> list:
    """
    Runs lspci -k and parses each device block into a structured dict.
    """
    output = _run(["lspci", "-k"])
    if not output:
        return []

    devices = []
    current = {}

    for line in output.splitlines():
        # New device block starts with bus address like "00:02.0"
        addr_match = re.match(r'^([0-9a-f]{2}:[0-9a-f]{2}\.[0-9a-f])\s+(.+)', line)
        if addr_match:
            if current:
                devices.append(_finalize_pci_device(current))
            current = {
                "id":      addr_match.group(1),
                "raw":     line.strip(),
                "name":    addr_match.group(2).strip(),
                "driver":  None,
                "modules": [],
            }
        elif "Kernel driver in use:" in line and current:
            current["driver"] = line.split(":", 1)[1].strip()
        elif "Kernel modules:" in line and current:
            mods = line.split(":", 1)[1].strip()
            current["modules"] = [m.strip() for m in mods.split(",")]

    if current:
        devices.append(_finalize_pci_device(current))

    return devices


def _finalize_pci_device(raw: dict) -> dict:
    category = _classify_category(raw["name"])
    status   = _classify_status(raw["driver"], raw["modules"], False)
    return {
        "id":                         raw["id"],
        "name":                       raw["name"],
        "category":                   category,
        "driver":                     raw["driver"],
        "modules":                    raw["modules"],
        "status":                     status,
        "blocked":                    False,
        "block_type":                 None,
        "firmware_update_available":  None,
        "source":                     "lspci",
        "raw":                        raw["raw"],
    }


# ─── lsusb parser ─────────────────────────────────────────────────────────────

def _parse_lsusb() -> list:
    """
    Runs lsusb and returns basic USB device dicts.
    Note: lsusb doesn't show drivers — we infer from category.
    """
    output = _run(["lsusb"])
    if not output:
        return []

    devices = []
    for line in output.splitlines():
        # Format: Bus 001 Device 002: ID 1bcf:2b98 Sunplus ... Webcam
        match = re.match(
            r'Bus (\d+) Device (\d+): ID ([0-9a-f:]+)\s+(.*)', line
        )
        if not match:
            continue

        usb_id   = match.group(3)
        name     = match.group(4).strip()
        category = _classify_category(name)

        # Skip root hubs — not useful to report
        if "root hub" in name.lower():
            continue

        # Known Bluetooth USB vendor:product IDs that don't say "bluetooth"
        # in their lsusb display name but are definitively BT adapters.
        _BT_USB_IDS = {
            "0cf3:e009",  # Qualcomm Atheros QCA9377 Bluetooth (Dell Vostro etc.)
            "0cf3:e300",  # Qualcomm Atheros AR3011
            "0cf3:3004",  # Qualcomm Atheros AR3012
            "0cf3:3008",  # Qualcomm Atheros AR3012
            "0cf3:311d",  # Qualcomm Atheros QCA6174
            "8087:0025",  # Intel AX200 Bluetooth
            "8087:0026",  # Intel AX201 Bluetooth
            "8087:0029",  # Intel AX211 Bluetooth
            "8087:07dc",  # Intel 7260 Bluetooth
            "8087:0a2a",  # Intel 7265 Bluetooth
            "8087:0a2b",  # Intel 8265 Bluetooth
            "0a12:0001",  # Cambridge Silicon Radio (generic BT dongle)
        }
        if usb_id in _BT_USB_IDS:
            category = "BLUETOOTH"

        devices.append({
            "id":                        f"usb:{usb_id}",
            "name":                      name,
            "category":                  category,
            "driver":                    _infer_usb_driver(category, name),
            "modules":                   [],
            "status":                    "OPTIMAL",  # refined by rfkill below
            "blocked":                   False,
            "block_type":                None,
            "firmware_update_available": None,
            "source":                    "lsusb",
            "raw":                       line.strip(),
        })

    return devices


def _infer_usb_driver(category: str, name: str) -> Optional[str]:
    """
    Infer likely driver from category for USB devices where
    lsusb doesn't report driver directly.
    """
    inferred = {
        "WEBCAM":    "uvcvideo",
        "BLUETOOTH": "btusb",
        "INPUT":     "usbhid",
    }
    return inferred.get(category)


# ─── rfkill parser ────────────────────────────────────────────────────────────

def _parse_rfkill() -> dict:
    """
    Returns a dict of rfkill blocks keyed by type (wifi, bluetooth).
    Format: { "wifi": {"soft": False, "hard": False}, ... }
    """
    output = _run(["rfkill", "list"])
    if not output:
        return {}

    blocks = {}
    current_type = None

    for line in output.splitlines():
        # "0: phy0: Wireless LAN" or "1: hci0: Bluetooth"
        type_match = re.search(r'Wireless LAN|Bluetooth', line, re.IGNORECASE)
        if type_match:
            current_type = "wifi" if "Wireless" in line else "bluetooth"
            blocks[current_type] = {"soft": False, "hard": False}
        elif current_type and "Soft blocked:" in line:
            blocks[current_type]["soft"] = "yes" in line.lower()
        elif current_type and "Hard blocked:" in line:
            blocks[current_type]["hard"] = "yes" in line.lower()

    return blocks


def _apply_rfkill_status(devices: list, rfkill: dict) -> list:
    """
    Updates device status based on rfkill state.
    """
    for dev in devices:
        cat = dev["category"].lower()
        if cat in rfkill:
            block = rfkill[cat]
            is_blocked = block["soft"] or block["hard"]
            dev["blocked"]    = is_blocked
            dev["block_type"] = "hard" if block["hard"] else \
                                ("soft" if block["soft"] else None)
            if is_blocked:
                dev["status"] = "BLOCKED"
    return devices


# ─── fwupd parser ─────────────────────────────────────────────────────────────

def _check_firmware_updates() -> dict:
    """
    Runs fwupdmgr get-updates and returns a dict of
    { device_name_fragment: True } for devices with updates available.
    """
    output = _run(["fwupdmgr", "get-updates", "--no-unreported-check"])
    if not output or "no upgrades" in output.lower():
        return {}

    updates = {}
    for line in output.splitlines():
        # fwupdmgr output has device names as headers
        if line and not line.startswith(" ") and ":" not in line:
            updates[line.strip().lower()] = True

    return updates


def _apply_firmware_updates(devices: list, fw_updates: dict) -> list:
    """Cross-reference fwupd results with device names."""
    for dev in devices:
        name_lower = dev["name"].lower()
        for fw_name in fw_updates:
            if fw_name in name_lower or name_lower in fw_name:
                dev["firmware_update_available"] = True
                break
        if dev["firmware_update_available"] is None:
            dev["firmware_update_available"] = False
    return devices


# ─── BIOS/UEFI info ───────────────────────────────────────────────────────────

def _get_bios_info() -> dict:
    """
    Uses dmidecode to get BIOS version and date.
    Returns empty dict if dmidecode not available or needs root.
    """
    output = _run(["sudo", "-n", "dmidecode", "-t", "bios"])
    if not output:
        return {}

    info = {}
    for line in output.splitlines():
        if "Version:" in line:
            info["version"] = line.split(":", 1)[1].strip()
        elif "Release Date:" in line:
            info["date"] = line.split(":", 1)[1].strip()

    return info


# ─── Battery info ─────────────────────────────────────────────────────────────

def _get_battery_info() -> dict:
    """
    Reads battery health from /sys/class/power_supply.
    Falls back to `upower` if the energy_full* sysfs files are absent
    (common on some ACPI implementations that only expose charge_*/voltage_*).
    No root required for either path.
    """
    battery_path = "/sys/class/power_supply"
    if not os.path.exists(battery_path):
        return _get_battery_upower()

    for name in os.listdir(battery_path):
        if not name.startswith("BAT"):
            continue
        bat = os.path.join(battery_path, name)
        try:
            def read(f):
                p = os.path.join(bat, f)
                return open(p).read().strip() if os.path.exists(p) else None

            status   = read("status")
            capacity = read("capacity")

            # Prefer energy_full / energy_full_design (µWh)
            energy_full     = read("energy_full")
            energy_full_des = read("energy_full_design")

            # Fallback: charge_full / charge_full_design (µAh) — multiply by
            # voltage_now to get energy, but ratio is the same either way.
            if not energy_full or not energy_full_des:
                energy_full     = read("charge_full")
                energy_full_des = read("charge_full_design")

            health_pct = None
            if energy_full and energy_full_des:
                ef  = int(energy_full)
                efd = int(energy_full_des)
                if efd > 0:
                    health_pct = round(ef / efd * 100, 1)

            result = {
                "name":         name,
                "status":       status,
                "capacity_pct": int(capacity) if capacity else None,
                "health_pct":   health_pct,
            }

            # If /sys gave us nothing useful, try upower as a last resort
            if health_pct is None:
                upower = _get_battery_upower()
                if upower:
                    upower.setdefault("name",         result["name"])
                    upower.setdefault("status",       result["status"])
                    upower.setdefault("capacity_pct", result["capacity_pct"])
                    return upower

            return result

        except (ValueError, OSError):
            continue

    return _get_battery_upower()


def _get_battery_upower() -> dict:
    """
    Uses `upower` to read battery health.
    Returns {} if upower is not available or finds no battery.
    """
    try:
        # List all power supply paths
        result = subprocess.run(
            ["upower", "-e"], capture_output=True, text=True, timeout=8
        )
        bat_path = next(
            (l.strip() for l in result.stdout.splitlines() if "BAT" in l or "battery" in l.lower()),
            None,
        )
        if not bat_path:
            return {}

        info_result = subprocess.run(
            ["upower", "-i", bat_path], capture_output=True, text=True, timeout=8
        )
        info = info_result.stdout

        def _extract(key):
            for line in info.splitlines():
                if key in line:
                    return line.split(":", 1)[1].strip()
            return None

        state    = _extract("state")
        capacity = _extract("capacity")       # e.g. "69.8%"
        percent  = _extract("percentage")     # e.g. "14%"

        health_pct = None
        if capacity:
            try:
                health_pct = round(float(capacity.replace("%", "")), 1)
            except ValueError:
                pass

        cap_pct = None
        if percent:
            try:
                cap_pct = int(float(percent.replace("%", "")))
            except ValueError:
                pass

        if health_pct is None and cap_pct is None:
            return {}

        return {
            "name":         "BAT0",
            "status":       state or "unknown",
            "capacity_pct": cap_pct,
            "health_pct":   health_pct,
        }

    except (FileNotFoundError, subprocess.TimeoutExpired, StopIteration):
        return {}


# ─── Main entry point ─────────────────────────────────────────────────────────

def scan_hardware() -> dict:
    """
    Full hardware scan. Returns:
    {
        "devices":  [...],      # list of device dicts
        "bios":     {...},      # BIOS/UEFI info
        "battery":  {...},      # battery health
        "warnings": [...],      # tools that weren't available
    }
    """
    warnings = []

    # Check which tools are available
    import shutil
    for tool in ["lspci", "lsusb", "rfkill", "fwupdmgr", "dmidecode"]:
        if not shutil.which(tool):
            warnings.append(
                f"'{tool}' not found — install it for better detection: "
                f"sudo apt install {_tool_pkg(tool)}"
            )

    pci_devices = _parse_lspci()
    usb_devices = _parse_lsusb()
    all_devices = pci_devices + usb_devices

    # Silence chipset-internal devices that never need a driver
    all_devices = [d for d in all_devices if not _is_driverless_ok(d["name"])]

    rfkill_status = _parse_rfkill()
    all_devices   = _apply_rfkill_status(all_devices, rfkill_status)

    fw_updates  = _check_firmware_updates()
    all_devices = _apply_firmware_updates(all_devices, fw_updates)

    bios    = _get_bios_info()
    battery = _get_battery_info()

    return {
        "devices":  all_devices,
        "bios":     bios,
        "battery":  battery,
        "warnings": warnings,
    }


def _tool_pkg(tool: str) -> str:
    pkg_map = {
        "lspci":    "pciutils",
        "lsusb":    "usbutils",
        "rfkill":   "rfkill",
        "fwupdmgr": "fwupd",
        "dmidecode":"dmidecode",
    }
    return pkg_map.get(tool, tool)
