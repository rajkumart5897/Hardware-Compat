# hardware-compat

> Hardware compatibility checker and driver advisor for Linux.

Scans every PCI and USB device on your system, checks driver status, rfkill blocks, firmware update availability, SMART disk health, and battery condition — then gives you **exact fix commands** and an interactive prompt to apply them. Note: **It is still a work in progress**

**No pip packages required.** Pure Python stdlib + standard Linux system tools.

---

## What It Does

```
  Scanning hardware... found 18 devices.

  ══════════════════════════════════════════════════════════════════════
  ════════════════ HARDWARE COMPATIBILITY REPORT ═══════════════════════
  ══════════════════════════════════════════════════════════════════════

  Distribution: Ubuntu 24.04 LTS
  Support Tier: FULL
  BIOS:         1.14.0 (04/20/2023)
  Battery:      72% health, 85% charge, status: Discharging

  ── Detected Devices ──────────────────────────────────────────────────

  WIFI
    [OPTIMAL]  Intel Wi-Fi 6 AX201 — driver: iwlwifi

  BLUETOOTH
    [BLOCKED]  Qualcomm Atheros QCA9377 — driver: btusb  [SOFT BLOCKED]

  ── Recommendations  (1 issue found) ──────────────────────────────────

  1. Qualcomm Atheros QCA9377 Bluetooth  [LOW]
     Bluetooth is soft-blocked. It can be unblocked without rebooting.
     Fix steps:
       → Unblock Bluetooth via rfkill
         $ sudo rfkill unblock bluetooth
       → Enable and start Bluetooth service
         $ sudo systemctl enable bluetooth && sudo systemctl start bluetooth
```

---

## Features

- **Full hardware scan** via `lspci` + `lsusb` — GPU, WiFi, Ethernet, Bluetooth, Audio, Webcam, Input, Storage
- **Driver status** — MISSING, SUBOPTIMAL (module exists but not loaded), BLOCKED, OPTIMAL
- **rfkill detection** — hard and soft blocks on WiFi/Bluetooth, with exact unblock commands
- **Firmware update check** via `fwupdmgr` — flags devices with pending updates
- **SMART disk health** via `smartctl` — reallocated sectors, pending sectors, SSD wear, NVMe endurance
- **Battery health** from `/sys/class/power_supply` with `upower` fallback
- **BIOS version** via `dmidecode`
- **Driver knowledge base** — exact fix commands for Intel, Qualcomm, Realtek, Broadcom, NVIDIA, AMD
- **Interactive fix prompt** — apply commands one by one with y/n/q
- **Web GUI** — live dashboard with real-time CPU, RAM, temperature, fan, disk I/O, and network monitoring
- **JSON output** — `--json` flag for scripting or integration
- **Distro-aware** — full auto-install on Ubuntu/Debian; detection-only on Fedora, Arch, openSUSE

---

## Quick Start

```bash
git clone https://github.com/yourusername/hardware-compat.git
cd hardware-compat
chmod +x install.sh
./install.sh
```

After install, from anywhere:

```bash
hardware-compat                    # opens web GUI (default)
hardware-compat --cli              # CLI full scan + interactive fix prompt
hardware-compat --cli --report    # report only, no prompts
hardware-compat --cli --json      # raw JSON output
hardware-compat --check-only      # distro support check only
```

Or without installing:

```bash
chmod +x run.sh
./run.sh            # CLI
./run.sh --gui      # Web GUI at http://localhost:7474
```

---

## Web GUI

`hardware-compat --gui` starts a local server at `http://localhost:7474` — no pip installs, pure Python stdlib.

The dashboard shows the full hardware scan, all recommendations with fix commands, a live system monitor (CPU, RAM, temps, fans, disk I/O, network), SMART disk health, and a settings panel.

```bash
hardware-compat --gui                    # default port 7474
hardware-compat --gui --port 8080        # custom port
hardware-compat --gui --no-browser       # skip auto-open
```

---

## System Dependencies

No Python packages. Uses standard Linux tools only:

| Tool | Package | Used for |
|------|---------|---------|
| `lspci` | `pciutils` | PCI device detection |
| `lsusb` | `usbutils` | USB device detection |
| `rfkill` | `rfkill` | WiFi / Bluetooth block state |
| `fwupdmgr` | `fwupd` | Firmware update checks |
| `dmidecode` | `dmidecode` | BIOS version (needs sudo) |
| `smartctl` | `smartmontools` | SMART disk health |
| `sensors` | `lm-sensors` | CPU / disk temperatures |

Install everything at once:

```bash
sudo apt install pciutils usbutils rfkill fwupd dmidecode smartmontools lm-sensors
```

`install.sh` detects missing tools and offers to install them for you.

---

## Supported Distributions

| Distro | Tier | Auto-install |
|--------|------|-------------|
| Ubuntu, Debian, Mint, Pop!\_OS | Full | ✅ Yes |
| Elementary, Kali, Raspberry Pi OS | Full | ✅ Yes |
| Fedora, RHEL, CentOS | Partial | ⚠️ Manual |
| Arch Linux, Manjaro | Partial | ⚠️ Manual |
| openSUSE Leap / Tumbleweed | Partial | ⚠️ Manual |
| Everything else | None | Graceful exit |

On **Partial** distros, hardware detection runs in full but install commands are shown for review rather than auto-applied. Each command is annotated with the equivalent for your package manager.

---

## CLI Flags

```
usage: hardware-compat [--cli | --gui] [options]

  --cli              Force CLI mode
  --gui              Force web GUI mode (default)
  --report           Show report only, skip the interactive fix prompt (CLI)
  --json             Output results as JSON (CLI)
  --check-only       Check distro support tier and exit
  --port PORT        Custom GUI port (default: 7474)
  --no-browser       Don't auto-open browser when starting GUI
```

---

## Project Structure

```
hardware-compat/
├── main.py                     # CLI entry point
├── gui_server.py               # Web GUI server (no Flask, stdlib only)
├── run.sh                      # Quick launcher — no install needed
├── install.sh                  # Full installer: tools + PATH + .desktop entry
├── hardware_compat/
│   ├── __init__.py
│   ├── detector.py             # lspci / lsusb / rfkill / fwupd / battery / BIOS scan
│   ├── distro.py               # Distro detection + support tier
│   ├── recommender.py          # Maps device issues → exact fix commands
│   ├── monitor.py              # Live metrics: CPU, RAM, temp, fans, net, disk I/O
│   ├── smart.py                # SMART disk health via smartctl (ATA + NVMe)
│   ├── cli.py                  # Colour terminal output + interactive apply
│   └── config.py               # Persistent settings (~/.config/hardware-compat/)
└── gui/
    ├── index.html              # Web dashboard (fetches from /api/* endpoints)
    └── static/
        └── icon.svg
```

---

## Driver Knowledge Base

`recommender.py` contains a curated KB mapping kernel module names to exact fix commands:

| Category | Covered |
|----------|---------|
| WiFi | `iwlwifi` (Intel), `ath10k_pci` (Qualcomm), `rtw88_pci` (Realtek), `brcmfmac` / `wl` (Broadcom), `r8188eu` |
| Bluetooth | `btusb` — soft block, hard block, missing stack |
| GPU | `i915` (Intel), `nouveau` → NVIDIA proprietary, `nvidia`, `amdgpu` |
| Audio | `snd_hda_intel`, SOF (`snd_sof_pci_intel_icl`) |
| Ethernet | `r8169` (Realtek) |
| Webcam | `uvcvideo` |
| Input | `hid_multitouch` |
| Fingerprint | `fprintd` setup |

Unknown devices fall back to `ubuntu-drivers` with a targeted search command.

---

## API Endpoints

When running in GUI mode, these endpoints are available locally:

| Endpoint | Description |
|----------|-------------|
| `GET /api/scan` | Full hardware scan (JSON) |
| `GET /api/monitor` | Live system metrics |
| `GET /api/smart` | SMART disk health |
| `GET /api/config` | Read settings |
| `POST /api/config` | Save settings |

---

## Configuration

Settings live at `~/.config/hardware-compat/settings.json`. The tool works with zero config — all keys have safe defaults.

Key options:

```json
{
  "default_mode": "gui",
  "gui_port": 7474,
  "auto_open_browser": true,
  "refresh_interval_s": 10,
  "theme": "auto",
  "alert_cpu_temp_c": 85,
  "alert_ram_pct": 90,
  "temp_unit": "C"
}
```

---

## Requirements

- Python 3.8+
- Linux (developed and tested on Ubuntu 24.04)
- No pip packages


