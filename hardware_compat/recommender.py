"""
recommender.py — Maps detected device issues to exact fix commands.

For each device with status MISSING, SUBOPTIMAL, or BLOCKED,
this module returns a Recommendation dict:

    {
        "device":       device dict from detector
        "issue":        human-readable description of the problem
        "severity":     "HIGH" | "MEDIUM" | "LOW"
        "fix_steps":    [ { "description": str, "cmd": str }, ... ]
        "reboot_required": bool
        "docs_url":     optional URL for more info
    }

Driver knowledge base is keyed by kernel module name or device name fragment.
"""

from typing import Optional


# ─── Driver knowledge base ────────────────────────────────────────────────────
# Key: kernel module name (matches driver or modules[] from detector)
# Value: dict with fix info

DRIVER_KB = {

    # ── WiFi ──────────────────────────────────────────────────────────────────
    "ath10k_pci": {
        "description": "Qualcomm Atheros WiFi (QCA9377 and similar)",
        "firmware_pkg": "linux-firmware",
        "notes": "ath10k firmware is in linux-firmware. Usually works OOB "
                 "on Ubuntu but firmware files may need updating.",
        "fix_missing": [
            {"description": "Install ath10k firmware",
             "cmd": "sudo apt install -y linux-firmware"},
            {"description": "Reload the driver",
             "cmd": "sudo modprobe -r ath10k_pci && sudo modprobe ath10k_pci"},
        ],
        "reboot_required": False,
        "docs_url": "https://wireless.wiki.kernel.org/en/users/Drivers/ath10k",
    },
    "iwlwifi": {
        "description": "Intel WiFi (most Intel wireless adapters)",
        "firmware_pkg": "linux-firmware",
        "fix_missing": [
            {"description": "Install Intel WiFi firmware",
             "cmd": "sudo apt install -y linux-firmware"},
            {"description": "Reload Intel WiFi driver",
             "cmd": "sudo modprobe -r iwlwifi && sudo modprobe iwlwifi"},
        ],
        "reboot_required": False,
        "docs_url": "https://wireless.wiki.kernel.org/en/users/Drivers/iwlwifi",
    },
    "rtw88_pci": {
        "description": "Realtek WiFi (RTL8822/RTL8821 series)",
        "fix_missing": [
            {"description": "Install Realtek WiFi firmware",
             "cmd": "sudo apt install -y linux-firmware"},
            {"description": "Reload driver",
             "cmd": "sudo modprobe -r rtw88_pci && sudo modprobe rtw88_pci"},
        ],
        "reboot_required": False,
    },
    "r8188eu": {
        "description": "Realtek RTL8188 USB WiFi dongle",
        "fix_missing": [
            {"description": "Install firmware",
             "cmd": "sudo apt install -y firmware-realtek"},
        ],
        "reboot_required": True,
    },
    "brcmfmac": {
        "description": "Broadcom WiFi (common in older laptops)",
        "fix_missing": [
            {"description": "Install Broadcom firmware",
             "cmd": "sudo apt install -y firmware-brcm80211"},
            {"description": "Or install the proprietary driver (better stability)",
             "cmd": "sudo apt install -y broadcom-sta-dkms"},
            {"description": "Rebuild kernel modules",
             "cmd": "sudo dkms autoinstall"},
        ],
        "reboot_required": True,
        "docs_url": "https://help.ubuntu.com/community/WifiDocs/Driver/bcm43xx",
    },
    "wl": {
        "description": "Broadcom WiFi (proprietary driver)",
        "fix_missing": [
            {"description": "Install Broadcom proprietary driver",
             "cmd": "sudo apt install -y broadcom-sta-dkms"},
            {"description": "Blacklist conflicting open-source drivers",
             "cmd": "echo -e 'blacklist b43\nblacklist b43legacy\nblacklist ssb\nblacklist bcm43xx\nblacklist brcm80211\nblacklist brcmfmac\nblacklist brcmsmac\nblacklist bcma' | sudo tee /etc/modprobe.d/blacklist-broadcom.conf"},
            {"description": "Rebuild and load",
             "cmd": "sudo dkms autoinstall && sudo modprobe wl"},
        ],
        "reboot_required": True,
    },

    # ── Bluetooth ─────────────────────────────────────────────────────────────
    "btusb": {
        "description": "USB Bluetooth adapter",
        "fix_soft_block": [
            {"description": "Unblock Bluetooth via rfkill",
             "cmd": "sudo rfkill unblock bluetooth"},
            {"description": "Enable and start Bluetooth service",
             "cmd": "sudo systemctl enable bluetooth && sudo systemctl start bluetooth"},
        ],
        "fix_hard_block": [
            {"description": "Hard block means the physical switch or BIOS "
                             "has disabled Bluetooth. Check BIOS settings or "
                             "the physical wireless switch on your laptop.",
             "cmd": None},
        ],
        "fix_missing": [
            {"description": "Install Bluetooth stack",
             "cmd": "sudo apt install -y bluez bluez-tools"},
            {"description": "Start Bluetooth service",
             "cmd": "sudo systemctl enable bluetooth && sudo systemctl start bluetooth"},
        ],
        "reboot_required": False,
    },

    # ── GPU ───────────────────────────────────────────────────────────────────
    "i915": {
        "description": "Intel integrated GPU (i915 driver)",
        "notes": "i915 is the correct open-source driver for Intel GPUs. "
                 "If you're seeing display issues, check Mesa version.",
        "fix_suboptimal": [
            {"description": "Update Mesa for latest Intel GPU support",
             "cmd": "sudo apt install -y mesa-utils mesa-vulkan-drivers intel-media-va-driver"},
            {"description": "Check current Mesa version",
             "cmd": "glxinfo | grep 'OpenGL version'"},
        ],
        "reboot_required": False,
    },
    "nouveau": {
        "description": "NVIDIA GPU using open-source nouveau driver",
        "notes": "nouveau works but NVIDIA proprietary drivers give much "
                 "better performance and power management.",
        "fix_suboptimal": [
            {"description": "Check which NVIDIA driver is recommended",
             "cmd": "ubuntu-drivers devices"},
            {"description": "Install recommended NVIDIA driver automatically",
             "cmd": "sudo ubuntu-drivers autoinstall"},
            {"description": "Or install a specific version (e.g. 535)",
             "cmd": "sudo apt install -y nvidia-driver-535"},
        ],
        "reboot_required": True,
        "docs_url": "https://help.ubuntu.com/community/NvidiaDriversInstallation",
    },
    "nvidia": {
        "description": "NVIDIA GPU (proprietary driver loaded)",
        "notes": "NVIDIA proprietary driver is active. Check for updates.",
        "fix_suboptimal": [
            {"description": "Check available NVIDIA driver versions",
             "cmd": "ubuntu-drivers devices"},
            {"description": "Update NVIDIA driver",
             "cmd": "sudo apt update && sudo apt install -y --only-upgrade nvidia-driver-*"},
        ],
        "reboot_required": True,
    },
    "amdgpu": {
        "description": "AMD GPU (amdgpu open-source driver)",
        "fix_suboptimal": [
            {"description": "Install AMDGPU extras for Vulkan and VA-API",
             "cmd": "sudo apt install -y mesa-vulkan-drivers mesa-va-drivers"},
        ],
        "reboot_required": False,
    },

    # ── Audio ─────────────────────────────────────────────────────────────────
    "snd_hda_intel": {
        "description": "Intel HD Audio",
        "notes": "snd_hda_intel is the standard Intel audio driver. "
                 "If audio is broken, PipeWire or PulseAudio config "
                 "is more likely the issue than the driver.",
        "fix_missing": [
            {"description": "Reload Intel HDA driver",
             "cmd": "sudo modprobe snd_hda_intel"},
            {"description": "Check if PipeWire is running",
             "cmd": "systemctl --user status pipewire"},
            {"description": "Restart PipeWire if needed",
             "cmd": "systemctl --user restart pipewire pipewire-pulse"},
        ],
        "reboot_required": False,
    },
    "snd_sof_pci_intel_icl": {
        "description": "Intel Sound Open Firmware (SOF) for Ice Lake audio",
        "notes": "SOF is an alternative to snd_hda_intel for newer Intel "
                 "platforms. Ubuntu may load either — both work.",
        "fix_missing": [
            {"description": "Install SOF firmware",
             "cmd": "sudo apt install -y firmware-sof-signed"},
        ],
        "reboot_required": True,
    },

    # ── Ethernet ──────────────────────────────────────────────────────────────
    "r8169": {
        "description": "Realtek Gigabit Ethernet",
        "notes": "r8169 is the kernel driver for most Realtek NICs. "
                 "Works well on Ubuntu. If you see slow speeds, "
                 "check if the proprietary r8168 driver is better for "
                 "your specific chip.",
        "fix_missing": [
            {"description": "Load r8169 driver",
             "cmd": "sudo modprobe r8169"},
        ],
        "reboot_required": False,
    },

    # ── Input / Touchpad ──────────────────────────────────────────────────────
    "hid_multitouch": {
        "description": "Touchpad / multitouch input",
        "fix_missing": [
            {"description": "Install touchpad support",
             "cmd": "sudo apt install -y xserver-xorg-input-libinput"},
        ],
        "reboot_required": False,
    },

    # ── Webcam ────────────────────────────────────────────────────────────────
    "uvcvideo": {
        "description": "USB Video Class webcam",
        "notes": "uvcvideo is the standard kernel driver for most webcams. "
                 "If webcam isn't detected, check if the module is loaded.",
        "fix_missing": [
            {"description": "Load UVC driver",
             "cmd": "sudo modprobe uvcvideo"},
            {"description": "Check if webcam is recognized",
             "cmd": "v4l2-ctl --list-devices"},
        ],
        "reboot_required": False,
    },

    # ── Fingerprint reader ────────────────────────────────────────────────────
    "fingerprint": {
        "description": "Fingerprint reader",
        "fix_missing": [
            {"description": "Install fingerprint daemon",
             "cmd": "sudo apt install -y fprintd libpam-fprintd"},
            {"description": "Enroll your fingerprint",
             "cmd": "fprintd-enroll"},
            {"description": "Check if your reader model is supported",
             "cmd": "sudo fprintd-list $USER"},
        ],
        "reboot_required": False,
        "docs_url": "https://wiki.ubuntu.com/fingerprint",
    },
}


# ─── Bluetooth soft-block recommendation ─────────────────────────────────────

def _bluetooth_block_recommendation(device: dict) -> Optional[dict]:
    block_type = device.get("block_type")
    if not block_type:
        return None

    kb = DRIVER_KB.get("btusb", {})

    if block_type == "hard":
        steps = kb.get("fix_hard_block", [])
        issue = ("Bluetooth is hard-blocked. This means either a physical "
                 "wireless switch or a BIOS setting has disabled it.")
        severity = "MEDIUM"
    else:
        steps = kb.get("fix_soft_block", [])
        issue = ("Bluetooth is soft-blocked (disabled in software). "
                 "It can be unblocked without rebooting.")
        severity = "LOW"

    return {
        "device":          device,
        "issue":           issue,
        "severity":        severity,
        "fix_steps":       steps,
        "reboot_required": False,
        "docs_url":        None,
    }


# ─── Main recommender ─────────────────────────────────────────────────────────

def build_recommendations(devices: list,
                           bios: dict,
                           battery: dict,
                           distro: dict) -> list:
    """
    Takes the device list from detector.scan_hardware() and returns
    a list of Recommendation dicts for anything that needs attention.
    """
    recs = []

    # USB Bluetooth adapters share their driver with the paired PCI device —
    # lsusb shows no driver but the chip is working. Mark them OPTIMAL so
    # they don't produce spurious MISSING recommendations.
    _bt_usb_ids_working = {
        "0cf3:e009", "0cf3:e300", "0cf3:3004", "0cf3:3008", "0cf3:311d",
        "8087:0025", "8087:0026", "8087:0029", "8087:07dc", "8087:0a2a",
        "8087:0a2b", "0a12:0001",
    }

    for device in devices:
        dev_id = device.get("id", "")
        if (device["category"] == "BLUETOOTH"
                and device["source"] == "lsusb"
                and dev_id.startswith("usb:")
                and dev_id[4:] in _bt_usb_ids_working
                and device["status"] == "MISSING"):
            device["status"] = "OPTIMAL"
            device["driver"] = "btusb"

    for device in devices:
        status = device["status"]

        if status == "OPTIMAL":
            # Check if a firmware update is available even for working devices
            if device.get("firmware_update_available"):
                recs.append({
                    "device":   device,
                    "issue":    f"Firmware update available for {device['name']}",
                    "severity": "LOW",
                    "fix_steps": [
                        {"description": "Refresh firmware metadata",
                         "cmd": "sudo fwupdmgr refresh"},
                        {"description": "Apply firmware updates",
                         "cmd": "sudo fwupdmgr update"},
                    ],
                    "reboot_required": True,
                    "docs_url": None,
                })
            continue

        if status == "BLOCKED":
            rec = _bluetooth_block_recommendation(device)
            if rec:
                recs.append(rec)
            continue

        # Find the best KB entry by checking driver then modules
        kb_entry = None
        for key in [device.get("driver")] + device.get("modules", []):
            if key and key in DRIVER_KB:
                kb_entry = DRIVER_KB[key]
                break

        # Also try matching by device name fragment
        if not kb_entry:
            name_lower = device["name"].lower()
            for kb_key, kb_val in DRIVER_KB.items():
                if kb_key in name_lower:
                    kb_entry = kb_val
                    break

        if not kb_entry:
            # Unknown device — flag it but no fix steps
            recs.append({
                "device":   device,
                "issue":    (f"No driver loaded for {device['name']}. "
                             f"No known fix in the database."),
                "severity": "MEDIUM",
                "fix_steps": [
                    {"description": "Search for drivers online",
                     "cmd": f"sudo ubuntu-drivers devices 2>/dev/null | grep -i '{device['name'].split()[0]}'"},
                ],
                "reboot_required": False,
                "docs_url": "https://help.ubuntu.com/community/HardwareSupport",
            })
            continue

        # Determine fix steps based on status
        if status == "MISSING":
            steps = kb_entry.get("fix_missing", [])
            issue = (f"{device['name']} has no driver loaded. "
                     f"{kb_entry.get('notes', '')}")
            severity = "HIGH"
        elif status == "SUBOPTIMAL":
            steps = kb_entry.get("fix_suboptimal",
                                 kb_entry.get("fix_missing", []))
            issue = (f"{device['name']} has a better driver available. "
                     f"{kb_entry.get('notes', '')}")
            severity = "MEDIUM"
        else:
            continue

        # Adapt install commands to this distro's package manager
        if distro["tier"] != "FULL":
            steps = _annotate_partial_distro(steps, distro)

        recs.append({
            "device":          device,
            "issue":           issue.strip(),
            "severity":        severity,
            "fix_steps":       steps,
            "reboot_required": kb_entry.get("reboot_required", False),
            "docs_url":        kb_entry.get("docs_url"),
        })

    # ── Battery health warning ─────────────────────────────────────────────
    if battery:
        health = battery.get("health_pct")
        if health is not None:
            if health < 50:
                recs.append({
                    "device":   {"name": f"Battery ({battery['name']})",
                                 "category": "BATTERY", "status": "DEGRADED"},
                    "issue":    (f"Battery health is critically low at {health}%. "
                                 f"Consider replacing the battery."),
                    "severity": "HIGH",
                    "fix_steps": [
                        {"description": "Check battery details",
                         "cmd": "upower -i $(upower -e | grep BAT)"},
                    ],
                    "reboot_required": False,
                    "docs_url": None,
                })
            elif health < 70:
                recs.append({
                    "device":   {"name": f"Battery ({battery['name']})",
                                 "category": "BATTERY", "status": "DEGRADED"},
                    "issue":    (f"Battery health is at {health}%. "
                                 f"Capacity has noticeably degraded from new."),
                    "severity": "MEDIUM",
                    "fix_steps": [
                        {"description": "Check full battery details",
                         "cmd": "upower -i $(upower -e | grep BAT)"},
                    ],
                    "reboot_required": False,
                    "docs_url": None,
                })

    # ── BIOS update check ─────────────────────────────────────────────────
    if bios:
        recs.append({
            "device":   {"name": "BIOS/UEFI Firmware",
                         "category": "FIRMWARE", "status": "UNKNOWN"},
            "issue":    (f"BIOS version {bios.get('version', 'unknown')} "
                         f"dated {bios.get('date', 'unknown')}. "
                         f"Check if a newer version is available."),
            "severity": "LOW",
            "fix_steps": [
                {"description": "Check for BIOS/firmware updates via fwupd",
                 "cmd": "sudo fwupdmgr refresh && sudo fwupdmgr get-updates"},
                {"description": "Apply any available firmware updates",
                 "cmd": "sudo fwupdmgr update"},
            ],
            "reboot_required": True,
            "docs_url": "https://fwupd.org",
        })

    # Sort by severity: HIGH first
    severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    recs.sort(key=lambda r: severity_order.get(r["severity"], 3))

    return recs


def _annotate_partial_distro(steps: list, distro: dict) -> list:
    """
    For PARTIAL distro support, annotate apt commands with a note
    that the user should adapt them to their package manager.
    """
    annotated = []
    for step in steps:
        cmd = step.get("cmd", "")
        if cmd and "apt" in cmd:
            annotated.append({
                "description": step["description"] +
                               f" (adapt for {distro['pkg_manager']})",
                "cmd": cmd + f"  # NOTE: replace 'apt install' with "
                             f"'{distro['install_cmd'].split()[0]} install'",
            })
        else:
            annotated.append(step)
    return annotated
