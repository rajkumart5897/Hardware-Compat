"""
monitor.py — Live system metrics (no root required for most readings).

Data sources (all from /proc and /sys — zero external dependencies):

    CPU usage      /proc/stat          per-core utilisation delta
    CPU freq       /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq
    RAM            /proc/meminfo
    Thermals       /sys/class/thermal/thermal_zone*   (ACPI zones)
                   /sys/class/hwmon/hwmon*            (lm-sensors chips)
    Fan speed      /sys/class/hwmon/hwmon*/fan*_input
    Network        /proc/net/dev                      RX/TX byte deltas
    Disk I/O       /proc/diskstats                    read/write byte deltas
    Uptime         /proc/uptime
    Load avg       /proc/loadavg
    Processes      /proc/loadavg (field 4)
    Boot time      /proc/stat (btime field)
    Kernel         /proc/version or uname
    lm-sensors     `sensors -j` if available (richer chip data)
"""

import os
import re
import json
import time
import subprocess
from typing import Optional

# ── CPU usage ─────────────────────────────────────────────────────────────────

_prev_cpu: dict = {}   # {core_id: (idle, total)}

def _read_cpu_stat() -> dict:
    """Read /proc/stat and return raw values per core."""
    result = {}
    try:
        with open("/proc/stat") as f:
            for line in f:
                if not line.startswith("cpu"):
                    continue
                parts = line.split()
                name = parts[0]           # "cpu", "cpu0", "cpu1", …
                vals = [int(x) for x in parts[1:]]
                # fields: user nice system idle iowait irq softirq steal …
                idle  = vals[3] + (vals[4] if len(vals) > 4 else 0)
                total = sum(vals)
                result[name] = (idle, total)
    except OSError:
        pass
    return result


def cpu_usage() -> dict:
    """
    Returns:
        {
            "total_pct":  float,          # overall CPU usage %
            "per_core":   [float, ...],   # per logical core %
        }
    Delta between two calls; first call returns zeros.
    """
    global _prev_cpu
    current = _read_cpu_stat()
    result_total = 0.0
    per_core = []

    for key in sorted(current):
        idle_now,  total_now  = current[key]
        idle_prev, total_prev = _prev_cpu.get(key, (idle_now, total_now))
        d_total = total_now - total_prev
        d_idle  = idle_now  - idle_prev
        pct = 0.0 if d_total == 0 else round((1 - d_idle / d_total) * 100, 1)
        if key == "cpu":
            result_total = pct
        else:
            per_core.append(pct)

    _prev_cpu = current
    return {"total_pct": result_total, "per_core": per_core}


# ── CPU frequency ─────────────────────────────────────────────────────────────

def cpu_frequencies() -> list:
    """Returns list of current MHz per logical core."""
    freqs = []
    cpu_base = "/sys/devices/system/cpu"
    if not os.path.exists(cpu_base):
        return freqs
    for entry in sorted(os.listdir(cpu_base)):
        if not re.match(r"^cpu\d+$", entry):
            continue
        freq_file = os.path.join(cpu_base, entry, "cpufreq", "scaling_cur_freq")
        try:
            val = int(open(freq_file).read().strip())
            freqs.append(round(val / 1000, 0))  # kHz → MHz
        except (OSError, ValueError):
            freqs.append(None)
    return freqs


# ── RAM ───────────────────────────────────────────────────────────────────────

def ram_info() -> dict:
    """
    Returns:
        {
            "total_mb":   int,
            "used_mb":    int,
            "free_mb":    int,
            "available_mb": int,
            "used_pct":   float,
            "buffers_mb": int,
            "cached_mb":  int,
            "swap_total_mb": int,
            "swap_used_mb":  int,
        }
    """
    data = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    key = parts[0].rstrip(":")
                    val = int(parts[1])      # always kB
                    data[key] = val
    except OSError:
        return {}

    total     = data.get("MemTotal", 0)
    free      = data.get("MemFree", 0)
    available = data.get("MemAvailable", 0)
    buffers   = data.get("Buffers", 0)
    cached    = data.get("Cached", 0) + data.get("SReclaimable", 0)
    used      = total - free - buffers - cached
    swap_tot  = data.get("SwapTotal", 0)
    swap_free = data.get("SwapFree", 0)

    kb = 1024
    return {
        "total_mb":      round(total     / kb),
        "used_mb":       round(used      / kb),
        "free_mb":       round(free      / kb),
        "available_mb":  round(available / kb),
        "used_pct":      round(used / total * 100, 1) if total else 0,
        "buffers_mb":    round(buffers   / kb),
        "cached_mb":     round(cached    / kb),
        "swap_total_mb": round(swap_tot  / kb),
        "swap_used_mb":  round((swap_tot - swap_free) / kb),
    }


# ── Thermals ──────────────────────────────────────────────────────────────────

def thermal_zones() -> list:
    """
    Reads /sys/class/thermal/thermal_zone* (ACPI thermal zones).
    Returns list of {type, temp_c} dicts.
    """
    zones = []
    base = "/sys/class/thermal"
    if not os.path.exists(base):
        return zones
    for entry in sorted(os.listdir(base)):
        if not entry.startswith("thermal_zone"):
            continue
        path = os.path.join(base, entry)
        try:
            zone_type = open(os.path.join(path, "type")).read().strip()
            temp_raw  = int(open(os.path.join(path, "temp")).read().strip())
            temp_c    = round(temp_raw / 1000, 1)
            zones.append({"type": zone_type, "temp_c": temp_c})
        except (OSError, ValueError):
            continue
    return zones


def hwmon_sensors() -> list:
    """
    Reads /sys/class/hwmon/hwmon*/temp*_input for chip temperatures
    and /sys/class/hwmon/hwmon*/fan*_input for fan speeds.

    Falls back to `sensors -j` if available (much richer labels).

    Returns list of:
        {
            "chip":      str,
            "label":     str,
            "temp_c":    float | None,
            "fan_rpm":   int   | None,
        }
    """
    # Try sensors -j first (best labels)
    sensors_json = _run_sensors_json()
    if sensors_json:
        return _parse_sensors_json(sensors_json)

    # Fallback: raw /sys/class/hwmon
    return _parse_hwmon_raw()


def _run_sensors_json() -> Optional[dict]:
    try:
        result = subprocess.run(
            ["sensors", "-j"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired,
            json.JSONDecodeError, OSError):
        pass
    return None


def _parse_sensors_json(data: dict) -> list:
    """Parse `sensors -j` output into a flat list of readings."""
    readings = []
    for chip_name, chip_data in data.items():
        if not isinstance(chip_data, dict):
            continue
        for sensor_name, sensor_data in chip_data.items():
            if not isinstance(sensor_data, dict):
                continue
            # Temperature keys end with _input
            temp_c   = None
            fan_rpm  = None
            for key, val in sensor_data.items():
                if key.endswith("_input") and "temp" in key.lower():
                    try: temp_c = round(float(val), 1)
                    except (TypeError, ValueError): pass
                if key.endswith("_input") and "fan" in key.lower():
                    try: fan_rpm = int(val)
                    except (TypeError, ValueError): pass
            if temp_c is not None or fan_rpm is not None:
                readings.append({
                    "chip":    chip_name,
                    "label":   sensor_name,
                    "temp_c":  temp_c,
                    "fan_rpm": fan_rpm,
                })
    return readings


def _parse_hwmon_raw() -> list:
    """Direct /sys/class/hwmon parsing as fallback."""
    readings = []
    base = "/sys/class/hwmon"
    if not os.path.exists(base):
        return readings

    for hwmon in sorted(os.listdir(base)):
        path = os.path.join(base, hwmon)
        try:
            chip = open(os.path.join(path, "name")).read().strip()
        except OSError:
            chip = hwmon

        # Temperatures
        for f in sorted(os.listdir(path)):
            if re.match(r"temp\d+_input", f):
                idx = f.split("_")[0]  # "temp1"
                try:
                    temp_raw = int(open(os.path.join(path, f)).read())
                    temp_c   = round(temp_raw / 1000, 1)
                    # Try to read label
                    label_f = os.path.join(path, f"{idx}_label")
                    label = open(label_f).read().strip() if os.path.exists(label_f) else idx
                    readings.append({"chip": chip, "label": label, "temp_c": temp_c, "fan_rpm": None})
                except (OSError, ValueError):
                    pass

        # Fans
        for f in sorted(os.listdir(path)):
            if re.match(r"fan\d+_input", f):
                idx = f.split("_")[0]
                try:
                    rpm = int(open(os.path.join(path, f)).read())
                    label_f = os.path.join(path, f"{idx}_label")
                    label = open(label_f).read().strip() if os.path.exists(label_f) else idx
                    # Find existing entry for this chip or create new
                    existing = next(
                        (r for r in readings if r["chip"] == chip and r["label"] == label), None
                    )
                    if existing:
                        existing["fan_rpm"] = rpm
                    else:
                        readings.append({"chip": chip, "label": label, "temp_c": None, "fan_rpm": rpm})
                except (OSError, ValueError):
                    pass

    return readings


# ── Network ───────────────────────────────────────────────────────────────────

_prev_net: dict = {}   # {iface: (rx_bytes, tx_bytes, timestamp)}

def network_stats() -> list:
    """
    Reads /proc/net/dev and returns per-interface stats with RX/TX speed.
    Skips loopback.
    Returns list of:
        {
            "iface":      str,
            "rx_bytes":   int,   # total
            "tx_bytes":   int,
            "rx_kbps":    float, # since last call
            "tx_kbps":    float,
            "state":      str,   # "up" | "down" | "unknown"
            "ip":         str | None,
        }
    """
    global _prev_net
    now = time.monotonic()
    current = {}

    try:
        with open("/proc/net/dev") as f:
            for line in f:
                line = line.strip()
                if ":" not in line:
                    continue
                iface, rest = line.split(":", 1)
                iface = iface.strip()
                if iface == "lo":
                    continue
                parts = rest.split()
                if len(parts) < 9:
                    continue
                rx_bytes = int(parts[0])
                tx_bytes = int(parts[8])
                current[iface] = (rx_bytes, tx_bytes, now)
    except OSError:
        return []

    results = []
    for iface, (rx, tx, ts) in current.items():
        prev_rx, prev_tx, prev_ts = _prev_net.get(iface, (rx, tx, ts))
        dt = ts - prev_ts
        rx_kbps = round((rx - prev_rx) / 1024 / dt, 1) if dt > 0 else 0.0
        tx_kbps = round((tx - prev_tx) / 1024 / dt, 1) if dt > 0 else 0.0

        state   = _iface_state(iface)
        ip      = _iface_ip(iface)

        results.append({
            "iface":    iface,
            "rx_bytes": rx,
            "tx_bytes": tx,
            "rx_kbps":  max(rx_kbps, 0),
            "tx_kbps":  max(tx_kbps, 0),
            "state":    state,
            "ip":       ip,
        })

    _prev_net = {k: v for k, v in current.items()}
    return results


def _iface_state(iface: str) -> str:
    try:
        state = open(f"/sys/class/net/{iface}/operstate").read().strip()
        return state  # "up", "down", "unknown", "dormant"
    except OSError:
        return "unknown"


def _iface_ip(iface: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["ip", "-4", "addr", "show", iface],
            capture_output=True, text=True, timeout=3
        )
        match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", result.stdout)
        return match.group(1) if match else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


# ── Disk I/O ──────────────────────────────────────────────────────────────────

_prev_disk: dict = {}  # {dev: (reads, writes, timestamp)}

def disk_io() -> list:
    """
    Reads /proc/diskstats and returns per-device read/write throughput.
    Returns list of:
        {
            "dev":       str,
            "read_kbps": float,
            "write_kbps": float,
        }
    """
    global _prev_disk
    now = time.monotonic()
    current = {}

    try:
        with open("/proc/diskstats") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 14:
                    continue
                dev = parts[2]
                # Skip partitions (sda1, sda2, etc.) — keep only whole disks
                if re.search(r"\d+$", dev) and not dev.startswith("nvme"):
                    continue
                if dev.startswith("loop") or dev.startswith("ram"):
                    continue
                # fields 5 and 9 are sectors read/written
                sectors_read  = int(parts[5])
                sectors_write = int(parts[9])
                current[dev] = (sectors_read * 512, sectors_write * 512, now)
    except OSError:
        return []

    results = []
    for dev, (rb, wb, ts) in current.items():
        prev_rb, prev_wb, prev_ts = _prev_disk.get(dev, (rb, wb, ts))
        dt = ts - prev_ts
        read_kbps  = round((rb - prev_rb) / 1024 / dt, 1) if dt > 0 else 0.0
        write_kbps = round((wb - prev_wb) / 1024 / dt, 1) if dt > 0 else 0.0
        results.append({
            "dev":        dev,
            "read_kbps":  max(read_kbps,  0),
            "write_kbps": max(write_kbps, 0),
        })

    _prev_disk = {k: v for k, v in current.items()}
    return results


# ── System info ───────────────────────────────────────────────────────────────

def system_info() -> dict:
    """
    Returns static + semi-static system information.
    {
        "uptime_s":      int,
        "uptime_str":    str,
        "boot_time":     str,   ISO-like
        "load_avg":      [1m, 5m, 15m],
        "process_count": int,
        "kernel":        str,
        "hostname":      str,
    }
    """
    info = {}

    # Uptime
    try:
        uptime_s = float(open("/proc/uptime").read().split()[0])
        info["uptime_s"]   = int(uptime_s)
        info["uptime_str"] = _fmt_uptime(int(uptime_s))
    except (OSError, ValueError):
        info["uptime_s"]   = 0
        info["uptime_str"] = "—"

    # Boot time
    try:
        with open("/proc/stat") as f:
            for line in f:
                if line.startswith("btime"):
                    btime = int(line.split()[1])
                    import datetime
                    info["boot_time"] = datetime.datetime.fromtimestamp(btime).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    break
    except (OSError, ValueError):
        info["boot_time"] = "—"

    # Load average
    try:
        parts = open("/proc/loadavg").read().split()
        info["load_avg"]      = [float(parts[0]), float(parts[1]), float(parts[2])]
        info["process_count"] = int(parts[3].split("/")[1])
    except (OSError, ValueError, IndexError):
        info["load_avg"]      = [0.0, 0.0, 0.0]
        info["process_count"] = 0

    # Kernel
    try:
        info["kernel"] = open("/proc/version").read().split()[2]
    except (OSError, IndexError):
        info["kernel"] = "—"

    # Hostname
    try:
        info["hostname"] = open("/proc/sys/kernel/hostname").read().strip()
    except OSError:
        info["hostname"] = "—"

    return info


def _fmt_uptime(seconds: int) -> str:
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, s   = divmod(rem, 60)
    if d:
        return f"{d}d {h}h {m}m"
    if h:
        return f"{h}h {m}m"
    return f"{m}m {s}s"


# ── dmesg errors ──────────────────────────────────────────────────────────────

def dmesg_errors(limit: int = 10) -> list:
    """
    Returns up to `limit` recent kernel error/warning lines.
    Requires read access to /dev/kmsg or fallback to `dmesg`.
    """
    lines = []
    try:
        result = subprocess.run(
            ["dmesg", "--level=err,warn", "--time-format=reltime", "-T"],
            capture_output=True, text=True, timeout=5
        )
        raw = result.stdout.strip().splitlines()
        lines = raw[-limit:] if len(raw) > limit else raw
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return lines


# ── Main poll function ────────────────────────────────────────────────────────

def poll() -> dict:
    """
    Single call that returns all live metrics.
    Designed to be called every N seconds by the GUI server.
    """
    return {
        "cpu":          cpu_usage(),
        "cpu_freq_mhz": cpu_frequencies(),
        "ram":          ram_info(),
        "thermals":     thermal_zones(),
        "sensors":      hwmon_sensors(),
        "network":      network_stats(),
        "disk_io":      disk_io(),
        "system":       system_info(),
        "dmesg_errors": dmesg_errors(limit=5),
    }
