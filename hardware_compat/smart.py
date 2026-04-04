"""
smart.py — Disk health via S.M.A.R.T. (smartctl).

Requires: sudo apt install smartmontools

For each block device found in /sys/block, runs:
    sudo smartctl -Aj /dev/<device>

and parses the JSON output into a structured health dict.

Key attributes tracked:
    5   Reallocated_Sector_Ct  — non-zero = dying drive
    187 Reported_Uncorrectable — read errors hardware couldn't fix
    188 Command_Timeout        — command timeouts (usually I/O issues)
    197 Current_Pending_Sector — sectors waiting to be reallocated
    198 Offline_Uncorrectable  — sectors found bad during offline scan
    199 UDMA_CRC_Error_Count   — cable/controller issues
    231 SSD_Life_Left          — SSD wear (100% = new, 0% = dead)
    233 Media_Wearout_Indicator — Intel SSD equivalent

NVMe drives are detected separately and use the nvme_smart_health_information_log.
"""

import json
import os
import re
import subprocess
from typing import Optional


# Attributes that signal serious trouble if non-zero
CRITICAL_ATTRS = {5, 187, 197, 198}
WARNING_ATTRS  = {188, 199}


def _list_block_devices() -> list:
    """Return physical block device names from /sys/block (no partitions)."""
    devices = []
    base = "/sys/block"
    if not os.path.exists(base):
        return devices
    for name in sorted(os.listdir(base)):
        # Include sda/sdb, nvme0n1, mmcblk0 — skip loop, ram, zram, sr
        if re.match(r"^(sd|nvme|mmcblk|vd|hd)[a-z0-9]+$", name):
            devices.append(name)
    return devices


def _run_smartctl(device: str) -> Optional[dict]:
    """Run `sudo smartctl -Aj /dev/<device>` and return parsed JSON or None."""
    try:
        result = subprocess.run(
            ["sudo", "-n", "smartctl", "-Aj", f"/dev/{device}"],
            # -n = non-interactive: fail immediately instead of prompting
            capture_output=True, text=True, timeout=15
        )
        out = result.stdout.strip()
        if not out:
            # sudo -n fails with exit code 1 and stderr "sudo: a password is required"
            if "password is required" in result.stderr:
                return {"_permission_error": True}
            return None
        return json.loads(out)
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def _parse_ata(device: str, data: dict) -> dict:
    """Parse ATA/SATA SMART JSON into our standard dict."""
    info       = data.get("device", {})
    smart_info = data.get("smart_status", {})
    attrs      = {a["id"]: a for a in data.get("ata_smart_attributes", {}).get("table", [])}
    temp_data  = data.get("temperature", {})
    capacity   = data.get("user_capacity", {})

    def attr_raw(attr_id: int) -> Optional[int]:
        a = attrs.get(attr_id)
        if not a:
            return None
        return a.get("raw", {}).get("value")

    def attr_val(attr_id: int) -> Optional[int]:
        a = attrs.get(attr_id)
        return a.get("value") if a else None

    passed = smart_info.get("passed", None)
    overall = "PASSED" if passed is True else ("FAILED" if passed is False else "UNKNOWN")

    reallocated   = attr_raw(5)
    pending       = attr_raw(197)
    uncorrectable = attr_raw(198)
    cmd_timeout   = attr_raw(188)
    crc_errors    = attr_raw(199)
    ssd_life      = attr_val(231) or attr_val(233)

    issues = []
    if reallocated and reallocated > 0:
        issues.append(f"{reallocated} reallocated sector(s) — drive is remapping bad blocks")
    if pending and pending > 0:
        issues.append(f"{pending} sector(s) pending reallocation")
    if uncorrectable and uncorrectable > 0:
        issues.append(f"{uncorrectable} offline uncorrectable sector(s)")
    if cmd_timeout and cmd_timeout > 100:
        issues.append(f"{cmd_timeout} command timeouts")
    if crc_errors and crc_errors > 50:
        issues.append(f"{crc_errors} UDMA CRC errors — check cable/controller")
    if ssd_life is not None and ssd_life < 20:
        issues.append(f"SSD life remaining: {ssd_life}% — consider replacing soon")

    severity = (
        "HIGH"   if overall == "FAILED" or any(attr_raw(i) and attr_raw(i) > 0 for i in CRITICAL_ATTRS)
        else "MEDIUM" if issues
        else "OK"
    )

    return {
        "device":            device,
        "type":              info.get("type", "ata"),
        "model":             data.get("model_name", "—"),
        "serial":            data.get("serial_number", "—"),
        "firmware":          data.get("firmware_version", "—"),
        "capacity_bytes":    capacity.get("bytes"),
        "temp_c":            temp_data.get("current"),
        "power_on_hours":    data.get("power_on_time", {}).get("hours"),
        "power_cycle_count": attr_raw(12),
        "overall":           overall,
        "severity":          severity,
        "issues":            issues,
        "reallocated_sectors": reallocated,
        "pending_sectors":   pending,
        "uncorrectable":     uncorrectable,
        "ssd_life_pct":      ssd_life,
        "self_test_status":  data.get("ata_smart_self_test_log", {}).get("standard", {}).get("count"),
    }


def _parse_nvme(device: str, data: dict) -> dict:
    """Parse NVMe SMART JSON."""
    smart_info  = data.get("smart_status", {})
    nvme_health = data.get("nvme_smart_health_information_log", {})
    temp_data   = data.get("temperature", {})
    capacity    = data.get("user_capacity", {})

    passed  = smart_info.get("passed", None)
    overall = "PASSED" if passed is True else ("FAILED" if passed is False else "UNKNOWN")

    critical_warning  = nvme_health.get("critical_warning", 0)
    media_errors      = nvme_health.get("media_errors", 0)
    percentage_used   = nvme_health.get("percentage_used", None)
    available_spare   = nvme_health.get("available_spare", None)
    spare_threshold   = nvme_health.get("available_spare_threshold", None)
    power_on_hours    = nvme_health.get("power_on_hours", None)
    unsafe_shutdowns  = nvme_health.get("unsafe_shutdowns", 0)

    issues = []
    if critical_warning:
        issues.append(f"Critical warning flag: 0x{critical_warning:02x}")
    if media_errors:
        issues.append(f"{media_errors} media error(s)")
    if percentage_used is not None and percentage_used >= 90:
        issues.append(f"NVMe endurance used: {percentage_used}%")
    if available_spare is not None and spare_threshold is not None:
        if available_spare <= spare_threshold:
            issues.append(f"Available spare ({available_spare}%) at or below threshold ({spare_threshold}%)")

    severity = (
        "HIGH"   if overall == "FAILED" or critical_warning or media_errors > 0
        else "MEDIUM" if issues
        else "OK"
    )

    life_pct = (100 - percentage_used) if percentage_used is not None else None

    return {
        "device":            device,
        "type":              "nvme",
        "model":             data.get("model_name", "—"),
        "serial":            data.get("serial_number", "—"),
        "firmware":          data.get("firmware_version", "—"),
        "capacity_bytes":    capacity.get("bytes"),
        "temp_c":            temp_data.get("current"),
        "power_on_hours":    power_on_hours,
        "power_cycle_count": nvme_health.get("power_cycles"),
        "overall":           overall,
        "severity":          severity,
        "issues":            issues,
        "reallocated_sectors": None,
        "pending_sectors":   None,
        "uncorrectable":     media_errors if media_errors else None,
        "ssd_life_pct":      life_pct,
        "available_spare":   available_spare,
        "percentage_used":   percentage_used,
        "unsafe_shutdowns":  unsafe_shutdowns,
    }


def scan_disks() -> list:
    """
    Scan all block devices and return list of SMART health dicts.
    Gracefully handles missing smartctl or permission errors.
    """
    results = []
    devices = _list_block_devices()

    if not devices:
        return results

    for device in devices:
        data = _run_smartctl(device)
        if not data:
            # smartctl not installed or no SMART support — minimal entry
            results.append({
                "device":   device,
                "type":     "unknown",
                "model":    "—",
                "overall":  "UNKNOWN",
                "severity": "OK",
                "issues":   ["smartctl not available or SMART not supported"],
                "temp_c":   None,
                "ssd_life_pct": None,
                "power_on_hours": None,
            })
            continue
        if data.get("_permission_error"):
            results.append({
                "device":   device,
                "type":     "unknown",
                "model":    "—",
                "overall":  "UNKNOWN",
                "severity": "OK",
                "issues":  [
                    "Permission denied. Run: sudo tee /etc/sudoers.d/hardware-compat "
                    "and add: %sudo ALL=(ALL) NOPASSWD: /usr/sbin/smartctl -Aj /dev/*"
                ],
                "temp_c":   None,
                "ssd_life_pct": None,
                "power_on_hours": None,
            })
            continue

        dev_type = data.get("device", {}).get("type", "ata")
        if dev_type == "nvme":
            results.append(_parse_nvme(device, data))
        else:
            results.append(_parse_ata(device, data))

    return results
