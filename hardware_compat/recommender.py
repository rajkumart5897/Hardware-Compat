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
Expanded knowledge base — covers WiFi, Bluetooth, GPU, Audio, Ethernet,
Touchpad, Webcam, Fingerprint, Power, USB, and more.
"""

from typing import Optional


# ─── Driver knowledge base ────────────────────────────────────────────────────
# Key: kernel module name (matches driver or modules[] from detector)
# Value: dict with fix info

DRIVER_KB = {

    # ══════════════════════════════════════════════════════════════════════════
    # WiFi
    # ══════════════════════════════════════════════════════════════════════════

    "ath10k_pci": {
        "description": "Qualcomm Atheros WiFi (QCA9377, QCA9370 and similar)",
        "firmware_pkg": "linux-firmware",
        "notes": "ath10k firmware is in linux-firmware. Usually works out of "
                 "the box on Ubuntu but firmware files may need updating. "
                 "If WiFi connects but drops, try disabling power management.",
        "fix_missing": [
            {"description": "Install ath10k firmware",
             "cmd": "sudo apt install -y linux-firmware"},
            {"description": "Reload the driver",
             "cmd": "sudo modprobe -r ath10k_pci && sudo modprobe ath10k_pci"},
            {"description": "Check firmware loaded correctly",
             "cmd": "sudo dmesg | grep ath10k"},
        ],
        "fix_suboptimal": [
            {"description": "Disable WiFi power management (fixes drops)",
             "cmd": "sudo iwconfig wlan0 power off"},
            {"description": "Make power management change permanent",
             "cmd": "echo 'options ath10k_pci nohwcrypt=1' | sudo tee /etc/modprobe.d/ath10k.conf"},
        ],
        "reboot_required": False,
        "docs_url": "https://wireless.wiki.kernel.org/en/users/Drivers/ath10k",
    },

    "ath11k_pci": {
        "description": "Qualcomm WiFi 6 (QCA6390, WCN6855, QCN9074 and similar)",
        "notes": "ath11k is the driver for Qualcomm WiFi 6 chips. Requires "
                 "up-to-date linux-firmware. Kernel 5.15+ recommended.",
        "fix_missing": [
            {"description": "Update linux-firmware to get latest ath11k firmware",
             "cmd": "sudo apt update && sudo apt install -y linux-firmware"},
            {"description": "Reload ath11k driver",
             "cmd": "sudo modprobe -r ath11k_pci && sudo modprobe ath11k_pci"},
            {"description": "Check for firmware errors",
             "cmd": "sudo dmesg | grep -i ath11k"},
        ],
        "fix_suboptimal": [
            {"description": "Disable power management if drops occur",
             "cmd": "sudo iwconfig wlan0 power off"},
        ],
        "reboot_required": False,
        "docs_url": "https://wireless.wiki.kernel.org/en/users/Drivers/ath11k",
    },

    "iwlwifi": {
        "description": "Intel WiFi (most Intel wireless adapters — AX200, AX201, AX210, etc.)",
        "firmware_pkg": "linux-firmware",
        "notes": "iwlwifi is the correct driver for Intel WiFi. If it loads "
                 "but fails, the firmware version in linux-firmware may be "
                 "too old for your specific card. AX210 requires kernel 5.10+.",
        "fix_missing": [
            {"description": "Install Intel WiFi firmware",
             "cmd": "sudo apt install -y linux-firmware"},
            {"description": "Reload Intel WiFi driver",
             "cmd": "sudo modprobe -r iwlwifi && sudo modprobe iwlwifi"},
            {"description": "Check which firmware file is being loaded",
             "cmd": "sudo dmesg | grep iwlwifi | head -20"},
        ],
        "fix_suboptimal": [
            {"description": "Disable 802.11n if connection is unstable (workaround)",
             "cmd": "echo 'options iwlwifi 11n_disable=1' | sudo tee /etc/modprobe.d/iwlwifi.conf"},
            {"description": "Or disable power saving which causes drops",
             "cmd": "echo 'options iwlwifi power_save=0' | sudo tee /etc/modprobe.d/iwlwifi.conf"},
            {"description": "Reload with new options",
             "cmd": "sudo modprobe -r iwlwifi && sudo modprobe iwlwifi"},
        ],
        "reboot_required": False,
        "docs_url": "https://wireless.wiki.kernel.org/en/users/Drivers/iwlwifi",
    },

    # ── Realtek in-kernel drivers (rtw88 family) ──────────────────────────────

    "rtw88_pci": {
        "description": "Realtek WiFi — rtw88 family (RTL8822BE, RTL8822CE, RTL8821CE, RTL8723DE)",
        "notes": "rtw88 is the in-kernel open-source driver for Realtek WiFi. "
                 "RTL8821CE also has a separate DKMS package (rtl8821ce-dkms) "
                 "which sometimes works better. Try the in-kernel driver first.",
        "fix_missing": [
            {"description": "Install Realtek firmware",
             "cmd": "sudo apt install -y linux-firmware"},
            {"description": "Reload rtw88 driver",
             "cmd": "sudo modprobe -r rtw88_pci && sudo modprobe rtw88_pci"},
            {"description": "Check kernel messages for the chip variant",
             "cmd": "sudo dmesg | grep rtw"},
        ],
        "fix_suboptimal": [
            {"description": "Disable power saving if drops occur",
             "cmd": "echo 'options rtw88_core disable_lps_deep=y' | sudo tee /etc/modprobe.d/rtw88.conf"},
        ],
        "reboot_required": False,
        "docs_url": "https://wireless.wiki.kernel.org/en/users/Drivers/rtw88",
    },

    "rtw89_pci": {
        "description": "Realtek WiFi 6 — rtw89 family (RTL8852AE, RTL8852BE, RTL8852CE, RTL8851BE)",
        "notes": "rtw89 is the in-kernel driver for newer Realtek WiFi 6 chips. "
                 "Requires kernel 5.18+ for RTL8852AE, 6.0+ for RTL8852BE. "
                 "RTL8852BE is very common in budget 2022-2024 laptops.",
        "fix_missing": [
            {"description": "Update linux-firmware for rtw89 firmware files",
             "cmd": "sudo apt update && sudo apt install -y linux-firmware"},
            {"description": "Reload rtw89 driver",
             "cmd": "sudo modprobe -r rtw89_pci && sudo modprobe rtw89_pci"},
            {"description": "If kernel is too old, install HWE kernel for newer driver support",
             "cmd": "sudo apt install -y linux-generic-hwe-22.04"},
            {"description": "Check dmesg for firmware load status",
             "cmd": "sudo dmesg | grep rtw89"},
        ],
        "fix_suboptimal": [
            {"description": "Disable power saving to fix random disconnects",
             "cmd": "echo 'options rtw89_core disable_ps_mode=y' | sudo tee /etc/modprobe.d/rtw89.conf"},
        ],
        "reboot_required": True,
        "docs_url": "https://wireless.wiki.kernel.org/en/users/Drivers/rtw89",
    },

    # ── Realtek out-of-tree DKMS drivers ──────────────────────────────────────

    "8821ce": {
        "description": "Realtek RTL8821CE WiFi (DKMS driver)",
        "notes": "RTL8821CE needs the rtl8821ce-dkms out-of-tree driver. "
                 "Secure Boot must be disabled for DKMS drivers to load. "
                 "This chip is very common in HP, Lenovo, and Acer budget laptops.",
        "fix_missing": [
            {"description": "Check if Secure Boot is enabled (must disable for DKMS)",
             "cmd": "[ -d /sys/firmware/efi ] && mokutil --sb-state || echo 'BIOS mode, Secure Boot N/A'"},
            {"description": "Install build tools and DKMS",
             "cmd": "sudo apt install -y dkms build-essential linux-headers-$(uname -r)"},
            {"description": "Install RTL8821CE DKMS package from Ubuntu repos",
             "cmd": "sudo apt install -y rtl8821ce-dkms"},
            {"description": "If repo version fails, try the community driver",
             "cmd": "git clone https://github.com/tomaspinho/rtl8821ce.git /tmp/rtl8821ce && cd /tmp/rtl8821ce && sudo ./dkms-install.sh"},
            {"description": "Load the module",
             "cmd": "sudo modprobe 8821ce"},
        ],
        "reboot_required": True,
        "docs_url": "https://github.com/tomaspinho/rtl8821ce",
    },

    # ── MediaTek WiFi drivers ─────────────────────────────────────────────────

    "mt7921e": {
        "description": "MediaTek MT7921 / MT7922 WiFi 6 (extremely common in AMD laptops)",
        "notes": "mt7921e covers both MT7921 and MT7922 chips (MT7922 confusingly "
                 "also uses the mt7921e driver). Very common in AMD Ryzen 5000/6000/7000 "
                 "laptops — Framework 13 AMD, ASUS TUF, Lenovo IdeaPad, etc. "
                 "Kernel 5.12+ required. If firmware fails, update linux-firmware.",
        "fix_missing": [
            {"description": "Update linux-firmware (includes MT7921/MT7922 firmware)",
             "cmd": "sudo apt update && sudo apt install -y linux-firmware"},
            {"description": "Reload mt7921e driver",
             "cmd": "sudo modprobe -r mt7921e && sudo modprobe mt7921e"},
            {"description": "Check which firmware files are being requested",
             "cmd": "sudo dmesg | grep -i mt792"},
            {"description": "If firmware still fails, check your kernel version (needs 5.12+)",
             "cmd": "uname -r"},
            {"description": "Install HWE kernel if yours is too old",
             "cmd": "sudo apt install -y linux-generic-hwe-22.04"},
        ],
        "fix_suboptimal": [
            {"description": "Remove conflicting backport-iwlwifi if installed (known conflict)",
             "cmd": "sudo apt remove -y backport-iwlwifi-dkms"},
            {"description": "Disable power management if drops occur",
             "cmd": "echo 'options mt7921e disable_clc=y' | sudo tee /etc/modprobe.d/mt7921.conf"},
            {"description": "Reload driver after config change",
             "cmd": "sudo modprobe -r mt7921e && sudo modprobe mt7921e"},
        ],
        "reboot_required": False,
        "docs_url": "https://wireless.wiki.kernel.org/en/users/Drivers/mt76",
    },

    "mt7921u": {
        "description": "MediaTek MT7921AU WiFi 6 (USB variant — AMD RZ608 dongles)",
        "notes": "mt7921u is the USB variant of the MT7921 driver. "
                 "Requires kernel 5.18+ for proper support.",
        "fix_missing": [
            {"description": "Update linux-firmware",
             "cmd": "sudo apt update && sudo apt install -y linux-firmware"},
            {"description": "Reload USB driver",
             "cmd": "sudo modprobe -r mt7921u && sudo modprobe mt7921u"},
            {"description": "Check kernel version (need 5.18+)",
             "cmd": "uname -r"},
        ],
        "reboot_required": False,
        "docs_url": "https://wireless.wiki.kernel.org/en/users/Drivers/mt76",
    },

    "mt7925e": {
        "description": "MediaTek MT7925 WiFi 6E/7 (newest MediaTek — Copilot+ laptops)",
        "notes": "MT7925 ships in many 2024 Qualcomm Snapdragon X and AMD AI PC laptops. "
                 "Requires kernel 6.6+ and very recent linux-firmware.",
        "fix_missing": [
            {"description": "Update linux-firmware to get MT7925 firmware",
             "cmd": "sudo apt update && sudo apt install -y linux-firmware"},
            {"description": "Check kernel version (need 6.6+)",
             "cmd": "uname -r"},
            {"description": "Install mainline or HWE kernel if needed",
             "cmd": "sudo apt install -y linux-generic-hwe-24.04"},
            {"description": "Reload driver",
             "cmd": "sudo modprobe -r mt7925e && sudo modprobe mt7925e"},
        ],
        "reboot_required": True,
        "docs_url": "https://wireless.wiki.kernel.org/en/users/Drivers/mt76",
    },

    # ── Broadcom WiFi ─────────────────────────────────────────────────────────

    "brcmfmac": {
        "description": "Broadcom WiFi — open source driver (BCM43xx chips)",
        "fix_missing": [
            {"description": "Install Broadcom firmware",
             "cmd": "sudo apt install -y firmware-brcm80211"},
            {"description": "Or install the proprietary driver for better stability",
             "cmd": "sudo apt install -y broadcom-sta-dkms"},
            {"description": "Rebuild kernel modules after install",
             "cmd": "sudo dkms autoinstall"},
        ],
        "reboot_required": True,
        "docs_url": "https://help.ubuntu.com/community/WifiDocs/Driver/bcm43xx",
    },

    "wl": {
        "description": "Broadcom WiFi — proprietary wl driver",
        "notes": "The proprietary wl driver conflicts with the open-source "
                 "brcmfmac/b43 drivers. Only one should be active at a time. "
                 "Secure Boot must be disabled for this DKMS driver.",
        "fix_missing": [
            {"description": "Install Broadcom proprietary driver",
             "cmd": "sudo apt install -y broadcom-sta-dkms"},
            {"description": "Blacklist conflicting open-source drivers",
             "cmd": "printf 'blacklist b43\nblacklist b43legacy\nblacklist ssb\nblacklist bcm43xx\nblacklist brcm80211\nblacklist brcmfmac\nblacklist brcmsmac\nblacklist bcma\n' | sudo tee /etc/modprobe.d/blacklist-broadcom.conf"},
            {"description": "Rebuild and load",
             "cmd": "sudo dkms autoinstall && sudo modprobe wl"},
        ],
        "reboot_required": True,
        "docs_url": "https://help.ubuntu.com/community/WifiDocs/Driver/bcm43xx",
    },

    "r8188eu": {
        "description": "Realtek RTL8188EU USB WiFi dongle",
        "fix_missing": [
            {"description": "Install firmware for RTL8188EU",
             "cmd": "sudo apt install -y firmware-realtek"},
            {"description": "Reload driver",
             "cmd": "sudo modprobe -r r8188eu && sudo modprobe r8188eu"},
        ],
        "reboot_required": True,
    },

    "r8192eu": {
        "description": "Realtek RTL8192EU USB WiFi dongle",
        "notes": "RTL8192EU requires an out-of-tree driver. No in-kernel support.",
        "fix_missing": [
            {"description": "Install build dependencies",
             "cmd": "sudo apt install -y git dkms build-essential linux-headers-$(uname -r)"},
            {"description": "Clone and install community driver",
             "cmd": "git clone https://github.com/clnhub/rtl8192eu-linux.git /tmp/rtl8192eu && cd /tmp/rtl8192eu && sudo ./install.sh"},
        ],
        "reboot_required": True,
        "docs_url": "https://github.com/clnhub/rtl8192eu-linux",
    },

    # ── USB WiFi catch-all ─────────────────────────────────────────────────────

    "ath9k_htc": {
        "description": "Qualcomm Atheros USB WiFi (older chipsets — AR9271, AR7010)",
        "fix_missing": [
            {"description": "Install firmware",
             "cmd": "sudo apt install -y firmware-atheros"},
            {"description": "Reload driver",
             "cmd": "sudo modprobe -r ath9k_htc && sudo modprobe ath9k_htc"},
        ],
        "reboot_required": False,
        "docs_url": "https://wireless.wiki.kernel.org/en/users/Drivers/ath9k_htc",
    },

    "rt2800usb": {
        "description": "Ralink / MediaTek USB WiFi (RT2870, RT3070 and similar)",
        "fix_missing": [
            {"description": "Install firmware",
             "cmd": "sudo apt install -y linux-firmware"},
            {"description": "Reload driver",
             "cmd": "sudo modprobe -r rt2800usb && sudo modprobe rt2800usb"},
        ],
        "reboot_required": False,
    },


    # ══════════════════════════════════════════════════════════════════════════
    # Bluetooth
    # ══════════════════════════════════════════════════════════════════════════

    "btusb": {
        "description": "USB Bluetooth adapter (covers most Intel, Qualcomm, Realtek BT chips)",
        "notes": "btusb is the universal Bluetooth driver for USB-connected chips. "
                 "Most laptop Bluetooth runs through this driver even if the chip "
                 "is PCI-connected internally.",
        "fix_soft_block": [
            {"description": "Unblock Bluetooth via rfkill",
             "cmd": "sudo rfkill unblock bluetooth"},
            {"description": "Enable and start Bluetooth service",
             "cmd": "sudo systemctl enable bluetooth && sudo systemctl start bluetooth"},
            {"description": "Verify Bluetooth is now unblocked",
             "cmd": "rfkill list bluetooth"},
        ],
        "fix_hard_block": [
            {"description": "Hard block = physical switch or BIOS disabled Bluetooth. "
                             "Check for a physical wireless switch on your laptop, "
                             "or enter BIOS/UEFI and look for a Wireless/Bluetooth toggle.",
             "cmd": None},
        ],
        "fix_missing": [
            {"description": "Install Bluetooth stack",
             "cmd": "sudo apt install -y bluez bluez-tools"},
            {"description": "Load Bluetooth driver",
             "cmd": "sudo modprobe btusb"},
            {"description": "Start Bluetooth service",
             "cmd": "sudo systemctl enable bluetooth && sudo systemctl start bluetooth"},
            {"description": "Check Bluetooth status",
             "cmd": "bluetoothctl show"},
        ],
        "reboot_required": False,
        "docs_url": "https://help.ubuntu.com/community/BluetoothSetup",
    },

    "btintel": {
        "description": "Intel Bluetooth (ThunderBolt / AX series)",
        "notes": "btintel is the Intel-specific Bluetooth driver. Works alongside btusb. "
                 "Requires up-to-date linux-firmware for AX200/AX210 Bluetooth.",
        "fix_missing": [
            {"description": "Update firmware for Intel Bluetooth",
             "cmd": "sudo apt install -y linux-firmware"},
            {"description": "Load Intel Bluetooth modules",
             "cmd": "sudo modprobe btusb && sudo modprobe btintel"},
            {"description": "Start Bluetooth service",
             "cmd": "sudo systemctl enable bluetooth && sudo systemctl start bluetooth"},
        ],
        "reboot_required": False,
    },

    "btnxpuart": {
        "description": "NXP Bluetooth (common in NXP IW61x chips on ARM-based devices)",
        "fix_missing": [
            {"description": "Install NXP Bluetooth firmware",
             "cmd": "sudo apt install -y linux-firmware"},
            {"description": "Load driver",
             "cmd": "sudo modprobe btnxpuart"},
        ],
        "reboot_required": False,
    },

    "hci_uart": {
        "description": "UART-based Bluetooth (Raspberry Pi, embedded systems)",
        "fix_missing": [
            {"description": "Load hci_uart module",
             "cmd": "sudo modprobe hci_uart"},
            {"description": "Enable Bluetooth service",
             "cmd": "sudo systemctl enable bluetooth && sudo systemctl start bluetooth"},
            {"description": "On Raspberry Pi, ensure Bluetooth overlay is enabled in /boot/config.txt",
             "cmd": "grep dtoverlay=pi3-miniuart-bt /boot/config.txt || echo 'dtoverlay=pi3-miniuart-bt' | sudo tee -a /boot/config.txt"},
        ],
        "reboot_required": True,
    },


    # ══════════════════════════════════════════════════════════════════════════
    # GPU
    # ══════════════════════════════════════════════════════════════════════════

    "i915": {
        "description": "Intel integrated GPU (i915 — Gen 4 through Meteor Lake)",
        "notes": "i915 is the correct open-source driver for Intel GPUs. "
                 "If you have display issues, check Mesa version with glxinfo. "
                 "For hardware video acceleration, install intel-media-va-driver.",
        "fix_missing": [
            {"description": "Install Intel GPU tools",
             "cmd": "sudo apt install -y intel-gpu-tools"},
            {"description": "Load i915 driver",
             "cmd": "sudo modprobe i915"},
            {"description": "Check GPU is recognised",
             "cmd": "sudo intel_gpu_top"},
        ],
        "fix_suboptimal": [
            {"description": "Update Mesa for latest Intel GPU support",
             "cmd": "sudo apt install -y mesa-utils mesa-vulkan-drivers intel-media-va-driver"},
            {"description": "For Iris Xe (Gen 12+), install newer mesa from PPA if needed",
             "cmd": "sudo add-apt-repository -y ppa:kisak/kisak-mesa && sudo apt update && sudo apt upgrade -y"},
            {"description": "Check current OpenGL version",
             "cmd": "glxinfo | grep 'OpenGL version'"},
            {"description": "Check hardware video decode support",
             "cmd": "vainfo 2>/dev/null | head -20"},
        ],
        "reboot_required": False,
        "docs_url": "https://help.ubuntu.com/community/IntelGraphicsDriver",
    },

    "xe": {
        "description": "Intel GPU — new Xe driver (Meteor Lake and newer, kernel 6.8+)",
        "notes": "The xe driver replaces i915 for very new Intel GPUs (Meteor Lake+). "
                 "Requires kernel 6.8 or newer.",
        "fix_suboptimal": [
            {"description": "Install Mesa Vulkan drivers for Xe",
             "cmd": "sudo apt install -y mesa-vulkan-drivers vulkan-tools"},
            {"description": "Check Vulkan support",
             "cmd": "vulkaninfo --summary 2>/dev/null | head -20"},
        ],
        "reboot_required": False,
    },

    "nouveau": {
        "description": "NVIDIA GPU — open-source nouveau driver (suboptimal performance)",
        "notes": "nouveau works but NVIDIA's proprietary driver gives much better "
                 "performance, power management, and CUDA support. "
                 "Use ubuntu-drivers to find the right version.",
        "fix_suboptimal": [
            {"description": "Check which NVIDIA driver is recommended",
             "cmd": "ubuntu-drivers devices"},
            {"description": "Install the recommended NVIDIA driver automatically",
             "cmd": "sudo ubuntu-drivers autoinstall"},
            {"description": "Or install a specific version (check ubuntu-drivers output first)",
             "cmd": "sudo apt install -y nvidia-driver-535"},
            {"description": "Verify NVIDIA driver after reboot",
             "cmd": "nvidia-smi"},
        ],
        "reboot_required": True,
        "docs_url": "https://help.ubuntu.com/community/NvidiaDriversInstallation",
    },

    "nvidia": {
        "description": "NVIDIA GPU — proprietary driver (active)",
        "notes": "NVIDIA proprietary driver is loaded. Check it is up to date.",
        "fix_suboptimal": [
            {"description": "Check current driver version",
             "cmd": "nvidia-smi"},
            {"description": "Check for newer available versions",
             "cmd": "ubuntu-drivers devices"},
            {"description": "Update NVIDIA driver",
             "cmd": "sudo apt update && sudo apt install -y --only-upgrade 'nvidia-driver-*'"},
        ],
        "reboot_required": True,
        "docs_url": "https://help.ubuntu.com/community/NvidiaDriversInstallation",
    },

    "amdgpu": {
        "description": "AMD GPU — amdgpu open-source driver (GCN and newer)",
        "notes": "amdgpu is the correct open-source driver for modern AMD GPUs. "
                 "For professional workloads, AMD also provides ROCm. "
                 "If you need the proprietary AMDGPU-PRO, use AMD's installer.",
        "fix_missing": [
            {"description": "Load amdgpu module",
             "cmd": "sudo modprobe amdgpu"},
            {"description": "Check GPU is detected",
             "cmd": "sudo dmesg | grep amdgpu | head -20"},
        ],
        "fix_suboptimal": [
            {"description": "Install Vulkan and VA-API support for AMD",
             "cmd": "sudo apt install -y mesa-vulkan-drivers mesa-va-drivers libvulkan1"},
            {"description": "Check Vulkan support",
             "cmd": "vulkaninfo --summary 2>/dev/null | head -20"},
            {"description": "Check video decode support",
             "cmd": "vainfo 2>/dev/null | head -20"},
            {"description": "For ROCm (GPU compute), visit AMD's ROCm install guide",
             "cmd": "echo 'See: https://rocm.docs.amd.com/projects/install-on-linux/en/latest/'"},
        ],
        "reboot_required": False,
        "docs_url": "https://wiki.ubuntu.com/AMDGPU",
    },

    "radeon": {
        "description": "AMD GPU — radeon driver (older pre-GCN and early GCN cards)",
        "notes": "radeon covers AMD GPUs older than Fiji/Polaris. "
                 "If you have an RX 400 series or newer, amdgpu should be used instead.",
        "fix_suboptimal": [
            {"description": "Install Mesa for radeon",
             "cmd": "sudo apt install -y mesa-utils libgl1-mesa-dri"},
            {"description": "Check if amdgpu should be used instead",
             "cmd": "lspci | grep -i vga"},
        ],
        "reboot_required": False,
    },

    "vmwgfx": {
        "description": "VMware SVGA GPU (virtual machine display)",
        "notes": "vmwgfx is the display driver for VMware virtual machines. "
                 "Install open-vm-tools for best performance.",
        "fix_missing": [
            {"description": "Install VMware guest tools",
             "cmd": "sudo apt install -y open-vm-tools open-vm-tools-desktop"},
            {"description": "Enable and start vmtoolsd",
             "cmd": "sudo systemctl enable open-vm-tools && sudo systemctl start open-vm-tools"},
        ],
        "fix_suboptimal": [
            {"description": "Update VMware tools for better display support",
             "cmd": "sudo apt install -y open-vm-tools open-vm-tools-desktop"},
        ],
        "reboot_required": True,
    },

    "vboxvideo": {
        "description": "VirtualBox GPU (virtual machine display)",
        "fix_missing": [
            {"description": "Install VirtualBox guest additions",
             "cmd": "sudo apt install -y virtualbox-guest-additions-iso"},
            {"description": "Or install via VirtualBox menu: Devices > Insert Guest Additions CD",
             "cmd": None},
        ],
        "reboot_required": True,
    },


    # ══════════════════════════════════════════════════════════════════════════
    # Audio
    # ══════════════════════════════════════════════════════════════════════════

    "snd_hda_intel": {
        "description": "Intel HD Audio (most common Intel audio driver)",
        "notes": "snd_hda_intel handles the hardware side. Audio issues on "
                 "modern Ubuntu are usually PipeWire/PulseAudio config rather "
                 "than the driver itself. Check PipeWire first.",
        "fix_missing": [
            {"description": "Reload Intel HDA driver",
             "cmd": "sudo modprobe -r snd_hda_intel && sudo modprobe snd_hda_intel"},
            {"description": "Check if PipeWire is running",
             "cmd": "systemctl --user status pipewire pipewire-pulse"},
            {"description": "Restart PipeWire if needed",
             "cmd": "systemctl --user restart pipewire pipewire-pulse wireplumber"},
            {"description": "List audio devices",
             "cmd": "aplay -l"},
        ],
        "fix_suboptimal": [
            {"description": "If no sound after suspend/resume, restart PipeWire",
             "cmd": "systemctl --user restart pipewire pipewire-pulse wireplumber"},
            {"description": "Check for muted channels",
             "cmd": "amixer sset Master unmute && amixer sset Speaker unmute"},
            {"description": "If audio is completely broken, try forcing legacy HDA mode",
             "cmd": "echo 'options snd-intel-dspcfg dsp_driver=1' | sudo tee /etc/modprobe.d/alsa-intel.conf"},
        ],
        "reboot_required": False,
        "docs_url": "https://help.ubuntu.com/community/SoundTroubleshootingProcedure",
    },

    # ── Intel Sound Open Firmware (SOF) — Tiger Lake, Alder Lake, Raptor Lake ─

    "sof_audio_pci_intel_tgl": {
        "description": "Intel SOF Audio — Tiger Lake (11th Gen Intel, 2020-2021 laptops)",
        "notes": "SOF (Sound Open Firmware) replaced snd_hda_intel on Tiger Lake "
                 "and newer Intel platforms. If audio shows 'Dummy Output', "
                 "install firmware-sof-signed and restart. This is one of the most "
                 "commonly reported audio issues on Ubuntu.",
        "fix_missing": [
            {"description": "Install SOF firmware",
             "cmd": "sudo apt install -y firmware-sof-signed"},
            {"description": "Restart audio services",
             "cmd": "systemctl --user restart pipewire pipewire-pulse wireplumber"},
            {"description": "If still no audio, try legacy HDA mode as fallback",
             "cmd": "echo 'options snd-intel-dspcfg dsp_driver=1' | sudo tee /etc/modprobe.d/alsa-intel.conf"},
            {"description": "Reboot for firmware changes to take effect",
             "cmd": "sudo reboot"},
        ],
        "fix_suboptimal": [
            {"description": "Update SOF firmware for stability fixes",
             "cmd": "sudo apt update && sudo apt install -y firmware-sof-signed"},
            {"description": "Install OEM kernel if audio still broken (sometimes better SOF support)",
             "cmd": "sudo apt install -y linux-oem-22.04"},
            {"description": "Restart audio stack after updates",
             "cmd": "systemctl --user restart pipewire pipewire-pulse wireplumber"},
        ],
        "reboot_required": True,
        "docs_url": "https://thesofproject.github.io/latest/getting_started/intel_debug/suggestions.html",
    },

    "sof_audio_pci_intel_adl": {
        "description": "Intel SOF Audio — Alder Lake / Raptor Lake (12th/13th Gen Intel, 2021-2023)",
        "notes": "Alder Lake and Raptor Lake use SOF for audio. Same fix as Tiger Lake. "
                 "Very common cause of 'Dummy Output' on 12th/13th Gen Intel laptops.",
        "fix_missing": [
            {"description": "Install SOF firmware",
             "cmd": "sudo apt install -y firmware-sof-signed"},
            {"description": "Install updated alsa UCM config for Alder Lake",
             "cmd": "sudo apt install -y alsa-ucm-conf"},
            {"description": "Restart audio services",
             "cmd": "systemctl --user restart pipewire pipewire-pulse wireplumber"},
            {"description": "If still broken, try legacy HDA mode",
             "cmd": "echo 'options snd-intel-dspcfg dsp_driver=1' | sudo tee /etc/modprobe.d/alsa-intel.conf && sudo reboot"},
        ],
        "fix_suboptimal": [
            {"description": "Update SOF firmware and ALSA UCM configs",
             "cmd": "sudo apt update && sudo apt install -y firmware-sof-signed alsa-ucm-conf"},
            {"description": "Install OEM kernel (often has better SOF patches)",
             "cmd": "sudo apt install -y linux-oem-22.04"},
            {"description": "Check SOF firmware is loaded",
             "cmd": "sudo dmesg | grep -i sof | head -20"},
        ],
        "reboot_required": True,
        "docs_url": "https://thesofproject.github.io/latest/getting_started/intel_debug/suggestions.html",
    },

    "sof_audio_pci_intel_mtl": {
        "description": "Intel SOF Audio — Meteor Lake (Core Ultra, 2023-2024 laptops)",
        "notes": "Meteor Lake uses SOF for audio. Requires kernel 6.7+ for full support. "
                 "If you have a Core Ultra laptop (e.g. Dell XPS 15 2024, ASUS Zenbook), "
                 "this is your audio driver.",
        "fix_missing": [
            {"description": "Install SOF firmware",
             "cmd": "sudo apt install -y firmware-sof-signed"},
            {"description": "Install HWE kernel (6.5+) for better Meteor Lake support",
             "cmd": "sudo apt install -y linux-generic-hwe-24.04"},
            {"description": "Install ALSA UCM configs",
             "cmd": "sudo apt install -y alsa-ucm-conf"},
            {"description": "Restart audio stack",
             "cmd": "systemctl --user restart pipewire pipewire-pulse wireplumber"},
        ],
        "reboot_required": True,
        "docs_url": "https://thesofproject.github.io/latest/getting_started/intel_debug/suggestions.html",
    },

    "snd_sof_pci_intel_icl": {
        "description": "Intel SOF Audio — Ice Lake (10th Gen Intel, 2019-2020)",
        "fix_missing": [
            {"description": "Install SOF firmware",
             "cmd": "sudo apt install -y firmware-sof-signed"},
            {"description": "Reload audio and restart PipeWire",
             "cmd": "systemctl --user restart pipewire pipewire-pulse wireplumber"},
        ],
        "reboot_required": True,
    },

    "snd_hda_codec_realtek": {
        "description": "Realtek HD Audio codec (headphone/speaker output)",
        "notes": "This driver handles the Realtek audio codec chip for headphone "
                 "and speaker output. If headphones are not detected on plug-in, "
                 "a pin config fix may be needed.",
        "fix_suboptimal": [
            {"description": "Check if headphones are detected",
             "cmd": "aplay -l && amixer contents | grep -i headphone"},
            {"description": "Try toggling audio output in PulseAudio/PipeWire",
             "cmd": "pactl list sinks short"},
            {"description": "If headphone jack not detected, try ALSA fix",
             "cmd": "echo 'options snd-hda-intel model=auto' | sudo tee /etc/modprobe.d/alsa-base.conf"},
        ],
        "reboot_required": False,
    },

    "snd_usb_audio": {
        "description": "USB Audio device (USB DAC, USB headset, USB sound card)",
        "fix_missing": [
            {"description": "Load USB audio driver",
             "cmd": "sudo modprobe snd_usb_audio"},
            {"description": "Check if USB audio device is detected",
             "cmd": "aplay -l | grep -i usb"},
            {"description": "List USB audio devices",
             "cmd": "lsusb | grep -i audio"},
        ],
        "reboot_required": False,
    },


    # ══════════════════════════════════════════════════════════════════════════
    # Ethernet
    # ══════════════════════════════════════════════════════════════════════════

    "r8169": {
        "description": "Realtek Gigabit Ethernet (RTL8111/8168/8411 — most common)",
        "notes": "r8169 is the kernel driver for most Realtek NICs. Generally works "
                 "well. If you see slow speeds or dropped connections, check if the "
                 "proprietary r8168 driver helps for your specific chip variant.",
        "fix_missing": [
            {"description": "Load r8169 driver",
             "cmd": "sudo modprobe r8169"},
            {"description": "Check Ethernet link status",
             "cmd": "ip link show && sudo ethtool $(ls /sys/class/net | grep -v lo | head -1)"},
        ],
        "fix_suboptimal": [
            {"description": "Try proprietary r8168 driver if r8169 is unstable",
             "cmd": "sudo apt install -y r8168-dkms"},
            {"description": "Disable Energy-Efficient Ethernet if drops occur",
             "cmd": "sudo ethtool -s $(ip route | grep default | awk '{print $5}') wol d"},
        ],
        "reboot_required": False,
        "docs_url": "https://help.ubuntu.com/community/HardwareSupportComponentsWiredNetworkCards",
    },

    "r8168": {
        "description": "Realtek Gigabit Ethernet — r8168 proprietary driver",
        "notes": "r8168-dkms is the proprietary driver, sometimes more stable than "
                 "the in-kernel r8169 for certain RTL8168 chip variants.",
        "fix_missing": [
            {"description": "Install r8168 proprietary driver",
             "cmd": "sudo apt install -y r8168-dkms"},
            {"description": "Blacklist r8169 to prevent conflict",
             "cmd": "echo 'blacklist r8169' | sudo tee /etc/modprobe.d/blacklist-r8169.conf"},
            {"description": "Load r8168 driver",
             "cmd": "sudo modprobe r8168"},
        ],
        "reboot_required": True,
    },

    "e1000e": {
        "description": "Intel Ethernet — e1000e (I217, I218, I219 — ThinkPad, Dell Latitude, HP EliteBook)",
        "notes": "e1000e is in the kernel but the version bundled in Ubuntu can be "
                 "outdated for newer chips. I219-V and I219-LM on 10th Gen+ Intel "
                 "may need an updated kernel or HWE kernel. If UNCLAIMED, try "
                 "modprobing e1000e and checking dmesg for NVM errors.",
        "fix_missing": [
            {"description": "Load e1000e driver",
             "cmd": "sudo modprobe e1000e"},
            {"description": "Check dmesg for NVM or driver errors",
             "cmd": "sudo dmesg | grep e1000e | tail -20"},
            {"description": "If driver loads but NIC is UNCLAIMED, try HWE kernel",
             "cmd": "sudo apt install -y linux-generic-hwe-22.04"},
            {"description": "Install ethtool for diagnostics",
             "cmd": "sudo apt install -y ethtool"},
            {"description": "Check link speed and status",
             "cmd": "sudo ethtool $(ip route | grep default | awk '{print $5}' | head -1)"},
        ],
        "fix_suboptimal": [
            {"description": "Disable EEE (Energy-Efficient Ethernet) if drops occur",
             "cmd": "sudo ethtool --set-eee $(ip route | grep default | awk '{print $5}' | head -1) eee off"},
        ],
        "reboot_required": False,
        "docs_url": "https://www.intel.com/content/www/us/en/support/articles/000005480/ethernet-products.html",
    },

    "igc": {
        "description": "Intel Ethernet 2.5GbE — igc (I225-V, I226-V — newer desktops/workstations)",
        "notes": "igc handles Intel 2.5GbE NICs found on newer Intel motherboards. "
                 "Generally works well on kernel 5.13+.",
        "fix_missing": [
            {"description": "Load igc driver",
             "cmd": "sudo modprobe igc"},
            {"description": "Check interface is up",
             "cmd": "ip link show && sudo ethtool $(ip route | grep default | awk '{print $5}' | head -1)"},
        ],
        "reboot_required": False,
    },

    "tg3": {
        "description": "Broadcom Gigabit Ethernet (tg3 driver — older ThinkPads, HP)",
        "fix_missing": [
            {"description": "Load tg3 driver",
             "cmd": "sudo modprobe tg3"},
            {"description": "Install Broadcom Ethernet firmware",
             "cmd": "sudo apt install -y firmware-bnx2"},
            {"description": "Check interface status",
             "cmd": "ip link show"},
        ],
        "reboot_required": False,
    },

    "bnx2": {
        "description": "Broadcom NetXtreme II Ethernet",
        "fix_missing": [
            {"description": "Install Broadcom firmware",
             "cmd": "sudo apt install -y firmware-bnx2"},
            {"description": "Load bnx2 driver",
             "cmd": "sudo modprobe bnx2"},
        ],
        "reboot_required": False,
    },

    "atlantic": {
        "description": "Marvell / AQtion 2.5GbE / 5GbE / 10GbE Ethernet",
        "notes": "atlantic driver covers Marvell AQC107/AQC111 chips. Common in "
                 "PCIe 2.5GbE NICs and some newer laptops.",
        "fix_missing": [
            {"description": "Load atlantic driver",
             "cmd": "sudo modprobe atlantic"},
            {"description": "Check for firmware errors",
             "cmd": "sudo dmesg | grep atlantic"},
        ],
        "reboot_required": False,
    },


    # ══════════════════════════════════════════════════════════════════════════
    # Touchpad / Input
    # ══════════════════════════════════════════════════════════════════════════

    "hid_multitouch": {
        "description": "Generic multitouch HID (touchpad / touchscreen)",
        "notes": "hid_multitouch is the base multitouch driver. Most modern laptop "
                 "touchpads run through i2c_hid which calls hid_multitouch. "
                 "If touchpad works but gestures are broken, try libinput.",
        "fix_missing": [
            {"description": "Install libinput for touchpad support",
             "cmd": "sudo apt install -y xserver-xorg-input-libinput"},
            {"description": "Load multitouch driver",
             "cmd": "sudo modprobe hid_multitouch"},
            {"description": "List detected input devices",
             "cmd": "libinput list-devices 2>/dev/null | head -40"},
        ],
        "reboot_required": False,
    },

    "i2c_hid": {
        "description": "I2C HID touchpad (most modern laptop touchpads — ELAN, Synaptics, ALPS)",
        "notes": "i2c_hid is the driver for I2C-connected touchpads. Most laptop "
                 "touchpads from 2014 onward use this. If touchpad is not detected, "
                 "try loading i2c_hid manually. On some ASUS laptops, ideapad-laptop "
                 "module can conflict.",
        "fix_missing": [
            {"description": "Load i2c_hid driver",
             "cmd": "sudo modprobe i2c_hid"},
            {"description": "Make it load on boot",
             "cmd": "echo 'i2c_hid' | sudo tee /etc/modules-load.d/touchpad.conf"},
            {"description": "Check dmesg for I2C HID errors",
             "cmd": "sudo dmesg | grep -i i2c_hid | tail -20"},
            {"description": "List I2C devices",
             "cmd": "ls /sys/bus/i2c/devices/"},
            {"description": "Install libinput for touchpad gestures",
             "cmd": "sudo apt install -y xserver-xorg-input-libinput libinput-tools"},
        ],
        "fix_suboptimal": [
            {"description": "If touchpad is erratic, try synaptics driver instead of libinput",
             "cmd": "sudo apt install -y xserver-xorg-input-synaptics"},
            {"description": "If Lenovo ideapad is conflicting, try disabling that module",
             "cmd": "echo 'blacklist ideapad_laptop' | sudo tee /etc/modprobe.d/blacklist-ideapad.conf"},
            {"description": "Reload i2c_hid after config change",
             "cmd": "sudo modprobe -r i2c_hid && sudo modprobe i2c_hid"},
        ],
        "reboot_required": False,
        "docs_url": "https://wiki.archlinux.org/title/Touchpad_Synaptics",
    },

    "elan_i2c": {
        "description": "ELAN touchpad — elan_i2c driver (ASUS, Acer, Lenovo laptops)",
        "notes": "elan_i2c is the driver for ELAN precision touchpads. Very common "
                 "on ASUS and some Acer laptops. If touchpad resets after suspend, "
                 "a kernel bug may be involved — check kernel version.",
        "fix_missing": [
            {"description": "Load elan_i2c driver",
             "cmd": "sudo modprobe elan_i2c"},
            {"description": "Make it load on boot",
             "cmd": "echo 'elan_i2c' | sudo tee /etc/modules-load.d/elan-touchpad.conf"},
            {"description": "Check dmesg for ELAN device errors",
             "cmd": "sudo dmesg | grep -i elan | tail -20"},
            {"description": "Verify touchpad is now visible",
             "cmd": "libinput list-devices 2>/dev/null | grep -i touchpad"},
        ],
        "fix_suboptimal": [
            {"description": "If touchpad resets after suspend, install HWE kernel",
             "cmd": "sudo apt install -y linux-generic-hwe-22.04"},
            {"description": "Reinstall libinput for fresh config",
             "cmd": "sudo apt install -y --reinstall xserver-xorg-input-libinput"},
        ],
        "reboot_required": False,
    },

    "psmouse": {
        "description": "PS/2 mouse / older Synaptics touchpad",
        "notes": "psmouse handles older PS/2 touchpads and mice. On modern laptops, "
                 "touchpads use i2c_hid instead. If psmouse is conflicting with "
                 "i2c_hid, blacklisting psmouse sometimes helps.",
        "fix_missing": [
            {"description": "Load psmouse driver",
             "cmd": "sudo modprobe psmouse"},
        ],
        "fix_suboptimal": [
            {"description": "If psmouse conflicts with i2c touchpad, blacklist it",
             "cmd": "echo 'blacklist psmouse' | sudo tee /etc/modprobe.d/blacklist-psmouse.conf"},
            {"description": "Reload drivers",
             "cmd": "sudo modprobe -r psmouse && sudo modprobe i2c_hid"},
        ],
        "reboot_required": False,
    },


    # ══════════════════════════════════════════════════════════════════════════
    # Webcam
    # ══════════════════════════════════════════════════════════════════════════

    "uvcvideo": {
        "description": "USB Video Class webcam (most USB and built-in laptop webcams)",
        "notes": "uvcvideo is the standard kernel driver for virtually all modern "
                 "webcams including built-in laptop cameras. If webcam not detected, "
                 "check v4l2 and that the module is loaded.",
        "fix_missing": [
            {"description": "Load UVC driver",
             "cmd": "sudo modprobe uvcvideo"},
            {"description": "Check if webcam is recognised",
             "cmd": "v4l2-ctl --list-devices 2>/dev/null"},
            {"description": "Install v4l2 utils if not present",
             "cmd": "sudo apt install -y v4l-utils"},
            {"description": "List video devices",
             "cmd": "ls -la /dev/video*"},
        ],
        "fix_suboptimal": [
            {"description": "Test webcam with cheese or ffplay",
             "cmd": "sudo apt install -y cheese && cheese"},
            {"description": "If webcam shows but is flipped/wrong, check app settings",
             "cmd": "v4l2-ctl --list-formats-ext --device=/dev/video0"},
        ],
        "reboot_required": False,
    },

    "ov5693": {
        "description": "OmniVision webcam sensor (common in Lenovo ThinkPad IR cameras)",
        "notes": "ov5693 is the sensor driver for some built-in ThinkPad cameras. "
                 "Requires ipu3-imgu for the full pipeline.",
        "fix_missing": [
            {"description": "Load camera sensor modules",
             "cmd": "sudo modprobe ov5693 && sudo modprobe ipu3_imgu"},
            {"description": "Check camera devices",
             "cmd": "ls /dev/video* && v4l2-ctl --list-devices"},
        ],
        "reboot_required": False,
    },

    "ov8865": {
        "description": "OmniVision webcam sensor (some ASUS, HP laptops)",
        "fix_missing": [
            {"description": "Load sensor driver",
             "cmd": "sudo modprobe ov8865"},
            {"description": "Check camera is detected",
             "cmd": "v4l2-ctl --list-devices"},
        ],
        "reboot_required": False,
    },


    # ══════════════════════════════════════════════════════════════════════════
    # Fingerprint reader
    # ══════════════════════════════════════════════════════════════════════════

    "fingerprint": {
        "description": "Fingerprint reader",
        "notes": "Linux fingerprint support depends on whether your specific reader "
                 "model is supported by libfprint. Check https://fprint.freedesktop.org/supported-devices.html "
                 "before spending time on this — unsupported readers cannot be made to work.",
        "fix_missing": [
            {"description": "Check if your fingerprint reader is listed in supported devices",
             "cmd": "lsusb | grep -i fingerprint"},
            {"description": "Install fingerprint daemon and PAM module",
             "cmd": "sudo apt install -y fprintd libpam-fprintd"},
            {"description": "Enroll your fingerprint",
             "cmd": "fprintd-enroll"},
            {"description": "Check enrolled fingerprints",
             "cmd": "fprintd-list $USER"},
            {"description": "Enable fingerprint auth in PAM",
             "cmd": "sudo pam-auth-update"},
        ],
        "reboot_required": False,
        "docs_url": "https://fprint.freedesktop.org/supported-devices.html",
    },

    "goodix_fp": {
        "description": "Goodix fingerprint reader (common in Lenovo ThinkPad, Huawei laptops)",
        "notes": "Goodix readers are partially supported in newer libfprint. "
                 "ThinkPad X1 Carbon Gen 9+ and some Huawei laptops use these.",
        "fix_missing": [
            {"description": "Install fprintd",
             "cmd": "sudo apt install -y fprintd libpam-fprintd"},
            {"description": "Check if Goodix reader is detected",
             "cmd": "lsusb | grep 27c6"},
            {"description": "Try enrolling",
             "cmd": "fprintd-enroll"},
        ],
        "reboot_required": False,
        "docs_url": "https://fprint.freedesktop.org/supported-devices.html",
    },


    # ══════════════════════════════════════════════════════════════════════════
    # Storage
    # ══════════════════════════════════════════════════════════════════════════

    "nvme": {
        "description": "NVMe SSD",
        "notes": "nvme is built into the kernel and should work without intervention. "
                 "If an NVMe drive is not detected, it may be a PCIe power management "
                 "issue. Try adding nvme_core.default_ps_max_latency_us=0 to kernel params.",
        "fix_suboptimal": [
            {"description": "Check NVMe health with nvme-cli",
             "cmd": "sudo apt install -y nvme-cli && sudo nvme smart-log /dev/nvme0"},
            {"description": "List NVMe devices",
             "cmd": "sudo nvme list"},
            {"description": "If NVMe disappears on suspend, disable power management",
             "cmd": "echo 'options nvme_core default_ps_max_latency_us=0' | sudo tee /etc/modprobe.d/nvme.conf"},
        ],
        "reboot_required": False,
        "docs_url": "https://help.ubuntu.com/community/SSD_Optimization_Procedures",
    },

    "ahci": {
        "description": "SATA AHCI controller (spinning HDDs and SATA SSDs)",
        "fix_suboptimal": [
            {"description": "Check SMART health for all SATA drives",
             "cmd": "sudo apt install -y smartmontools && sudo smartctl -a /dev/sda"},
            {"description": "Enable SMART monitoring daemon",
             "cmd": "sudo systemctl enable smartd && sudo systemctl start smartd"},
        ],
        "reboot_required": False,
    },


    # ══════════════════════════════════════════════════════════════════════════
    # Power management
    # ══════════════════════════════════════════════════════════════════════════

    "thinkpad_acpi": {
        "description": "ThinkPad power management and ACPI (fan control, hotkeys, battery)",
        "notes": "thinkpad_acpi provides ThinkPad-specific features: fan control, "
                 "hotkeys, battery charge thresholds, and more. Usually loaded "
                 "automatically on ThinkPads.",
        "fix_missing": [
            {"description": "Load thinkpad_acpi module",
             "cmd": "sudo modprobe thinkpad_acpi"},
            {"description": "Check ThinkPad ACPI is loaded",
             "cmd": "sudo dmesg | grep thinkpad_acpi"},
            {"description": "Install tp-smapi for older ThinkPad battery management",
             "cmd": "sudo apt install -y tp-smapi-dkms"},
        ],
        "fix_suboptimal": [
            {"description": "Install TLP for advanced ThinkPad power management",
             "cmd": "sudo apt install -y tlp tlp-rdw && sudo tlp start"},
            {"description": "Set battery charge thresholds (ThinkPad only)",
             "cmd": "echo 'START_CHARGE_THRESH_BAT0=75\nSTOP_CHARGE_THRESH_BAT0=80' | sudo tee -a /etc/tlp.conf && sudo tlp start"},
        ],
        "reboot_required": False,
        "docs_url": "https://www.thinkwiki.org/wiki/Thinkpad-acpi",
    },

    "asus_wmi": {
        "description": "ASUS laptop WMI (fan curves, performance modes, ROG features)",
        "notes": "asus_wmi provides ASUS-specific features including performance "
                 "mode switching, fan curves, and keyboard backlight on ROG/TUF laptops.",
        "fix_missing": [
            {"description": "Load asus_wmi module",
             "cmd": "sudo modprobe asus_wmi"},
            {"description": "Install asusctl for full ASUS laptop management",
             "cmd": "sudo apt install -y asusctl"},
        ],
        "fix_suboptimal": [
            {"description": "Install asusctl for performance mode and fan control",
             "cmd": "sudo apt install -y asusctl && sudo systemctl enable asusd && sudo systemctl start asusd"},
            {"description": "Check available performance profiles",
             "cmd": "asusctl profile --list-profiles"},
        ],
        "reboot_required": False,
        "docs_url": "https://wiki.archlinux.org/title/ASUS_Linux",
    },

    "ideapad_laptop": {
        "description": "Lenovo IdeaPad / ThinkBook WMI (Fn keys, camera privacy, conservation mode)",
        "fix_missing": [
            {"description": "Load ideapad_laptop module",
             "cmd": "sudo modprobe ideapad_laptop"},
        ],
        "fix_suboptimal": [
            {"description": "Enable battery conservation mode (keeps battery at 60% when plugged in)",
             "cmd": "echo 1 | sudo tee /sys/bus/platform/drivers/ideapad_acpi/VPC2004:00/conservation_mode"},
        ],
        "reboot_required": False,
    },

    "acpi_call": {
        "description": "ACPI call module (for battery thresholds, fan control on various laptops)",
        "fix_missing": [
            {"description": "Install acpi_call-dkms",
             "cmd": "sudo apt install -y acpi-call-dkms"},
            {"description": "Load module",
             "cmd": "sudo modprobe acpi_call"},
        ],
        "reboot_required": False,
    },


    # ══════════════════════════════════════════════════════════════════════════
    # USB / Thunderbolt
    # ══════════════════════════════════════════════════════════════════════════

    "xhci_hcd": {
        "description": "USB 3.x host controller",
        "notes": "xhci_hcd handles USB 3.0/3.1/3.2 ports. Usually loaded automatically.",
        "fix_missing": [
            {"description": "Load xhci_hcd",
             "cmd": "sudo modprobe xhci_hcd"},
            {"description": "Check USB devices",
             "cmd": "lsusb"},
        ],
        "reboot_required": False,
    },

    "thunderbolt": {
        "description": "Thunderbolt controller (USB4, Thunderbolt 3/4)",
        "notes": "Thunderbolt on Linux requires the bolt daemon for device authorisation. "
                 "Without bolt, Thunderbolt docks and devices may not be authorised.",
        "fix_missing": [
            {"description": "Install bolt for Thunderbolt device management",
             "cmd": "sudo apt install -y bolt"},
            {"description": "Enable and start bolt daemon",
             "cmd": "sudo systemctl enable bolt && sudo systemctl start bolt"},
            {"description": "List Thunderbolt devices",
             "cmd": "boltctl list"},
            {"description": "Authorise a Thunderbolt device",
             "cmd": "boltctl enroll --policy auto <device-uuid>"},
        ],
        "reboot_required": False,
        "docs_url": "https://wiki.archlinux.org/title/Thunderbolt",
    },


    # ══════════════════════════════════════════════════════════════════════════
    # SD card reader
    # ══════════════════════════════════════════════════════════════════════════

    "sdhci_pci": {
        "description": "PCI SD card reader (built-in laptop SD slot)",
        "fix_missing": [
            {"description": "Load SD host controller driver",
             "cmd": "sudo modprobe sdhci_pci"},
            {"description": "Check if SD card is detected",
             "cmd": "lsblk | grep -i sd"},
        ],
        "reboot_required": False,
    },

    "rtsx_pci": {
        "description": "Realtek PCIE card reader (common in Dell, Lenovo, HP laptops)",
        "fix_missing": [
            {"description": "Load Realtek card reader driver",
             "cmd": "sudo modprobe rtsx_pci && sudo modprobe rtsx_pci_sdmmc"},
            {"description": "Check if card reader is detected",
             "cmd": "lspci | grep -i realtek && lsblk"},
        ],
        "reboot_required": False,
    },


    # ══════════════════════════════════════════════════════════════════════════
    # Sensors / thermal
    # ══════════════════════════════════════════════════════════════════════════

    "coretemp": {
        "description": "Intel CPU temperature sensor",
        "fix_missing": [
            {"description": "Load coretemp module",
             "cmd": "sudo modprobe coretemp"},
            {"description": "Install lm-sensors for temperature monitoring",
             "cmd": "sudo apt install -y lm-sensors && sudo sensors-detect --auto"},
            {"description": "View temperatures",
             "cmd": "sensors"},
        ],
        "reboot_required": False,
    },

    "k10temp": {
        "description": "AMD CPU temperature sensor (Ryzen and EPYC)",
        "fix_missing": [
            {"description": "Load k10temp module",
             "cmd": "sudo modprobe k10temp"},
            {"description": "Install lm-sensors",
             "cmd": "sudo apt install -y lm-sensors && sudo sensors-detect --auto"},
            {"description": "View temperatures",
             "cmd": "sensors"},
        ],
        "reboot_required": False,
    },
}


# ─── Name fragment fallback KB ────────────────────────────────────────────────
# Used when kernel module name doesn't match — tries device name substrings.
# Ordered from most specific to least specific.

NAME_FRAGMENT_KB = {
    "mediatek mt7921": "mt7921e",
    "mediatek mt7922": "mt7921e",
    "mediatek mt7925": "mt7925e",
    "mediatek mt7920": "mt7921e",
    "mediatek mt792": "mt7921e",
    "mediatek":        "mt7921e",
    "rtl8852be":       "rtw89_pci",
    "rtl8852ae":       "rtw89_pci",
    "rtl8852ce":       "rtw89_pci",
    "rtl8851be":       "rtw89_pci",
    "rtl8822ce":       "rtw88_pci",
    "rtl8822be":       "rtw88_pci",
    "rtl8821ce":       "8821ce",
    "rtl8723de":       "rtw88_pci",
    "rtl8188eu":       "r8188eu",
    "rtl8192eu":       "r8192eu",
    "rtl8111":         "r8169",
    "rtl8168":         "r8169",
    "i219":            "e1000e",
    "i218":            "e1000e",
    "i217":            "e1000e",
    "i225":            "igc",
    "i226":            "igc",
    "qca9377":         "ath10k_pci",
    "qca9370":         "ath10k_pci",
    "qcn9074":         "ath11k_pci",
    "ax200":           "iwlwifi",
    "ax201":           "iwlwifi",
    "ax210":           "iwlwifi",
    "ax211":           "iwlwifi",
    "tiger lake":      "sof_audio_pci_intel_tgl",
    "alder lake":      "sof_audio_pci_intel_adl",
    "raptor lake":     "sof_audio_pci_intel_adl",
    "meteor lake":     "sof_audio_pci_intel_mtl",
    "smart sound":     "sof_audio_pci_intel_tgl",
    "elan":            "elan_i2c",
    "bcm43":           "brcmfmac",
    "goodix":          "goodix_fp",
    "thinkpad":        "thinkpad_acpi",
    "ideapad":         "ideapad_laptop",
}


# ─── Bluetooth soft/hard block handler ───────────────────────────────────────

def _bluetooth_block_recommendation(device: dict) -> Optional[dict]:
    block_type = device.get("block_type")
    if not block_type:
        return None

    kb = DRIVER_KB.get("btusb", {})

    if block_type == "hard":
        steps = kb.get("fix_hard_block", [])
        issue = ("Bluetooth is hard-blocked. A physical wireless switch or "
                 "a BIOS/UEFI setting has disabled it.")
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


# ─── KB lookup helper ─────────────────────────────────────────────────────────

def _find_kb_entry(device: dict) -> Optional[dict]:
    """
    Try to find a KB entry for a device.
    Priority:
      1. Exact match on driver name
      2. Exact match on any module in device["modules"]
      3. Name fragment matching (case-insensitive device name)
    """
    # 1. Exact driver match
    driver = device.get("driver", "")
    if driver and driver in DRIVER_KB:
        return DRIVER_KB[driver]

    # 2. Module list match
    for mod in device.get("modules", []):
        if mod and mod in DRIVER_KB:
            return DRIVER_KB[mod]

    # 3. Name fragment match
    name_lower = device.get("name", "").lower()
    for fragment, kb_key in NAME_FRAGMENT_KB.items():
        if fragment in name_lower:
            return DRIVER_KB.get(kb_key)

    # 4. Direct key match against device name words
    for kb_key in DRIVER_KB:
        if kb_key in name_lower:
            return DRIVER_KB[kb_key]

    return None


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

    # ── USB Bluetooth ID whitelist ─────────────────────────────────────────
    # USB BT adapters share driver with the paired PCI chip.
    # Mark known-working USB IDs as OPTIMAL to suppress false MISSING reports.
    _bt_usb_ids_working = {
        # Intel AX series
        "8087:0025", "8087:0026", "8087:0029", "8087:07dc",
        "8087:0a2a", "8087:0a2b", "8087:0032", "8087:0033",
        # Qualcomm Atheros
        "0cf3:e009", "0cf3:e300", "0cf3:3004", "0cf3:3008",
        "0cf3:311d", "0cf3:e500",
        # Realtek
        "0bda:b009", "0bda:c123", "0bda:8771",
        # Generic CSR
        "0a12:0001",
        # MediaTek
        "0e8d:0616",
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

    # ── Main loop ─────────────────────────────────────────────────────────
    for device in devices:
        status = device["status"]

        if status == "OPTIMAL":
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
                    "docs_url": "https://fwupd.org",
                })
            continue

        if status == "BLOCKED":
            rec = _bluetooth_block_recommendation(device)
            if rec:
                recs.append(rec)
            continue

        kb_entry = _find_kb_entry(device)

        if not kb_entry:
            # Unknown device — provide a generic fallback
            recs.append({
                "device":   device,
                "issue":    (f"No driver loaded for {device['name']} and no known "
                             f"fix in the database."),
                "severity": "MEDIUM",
                "fix_steps": [
                    {"description": "Search for drivers via ubuntu-drivers",
                     "cmd": f"ubuntu-drivers devices 2>/dev/null"},
                    {"description": "Search for the device online (use this ID)",
                     "cmd": f"echo 'Search: linux driver {device.get('name', 'unknown device')}'"},
                    {"description": "Check kernel messages for clues",
                     "cmd": f"sudo dmesg | grep -i '{device.get('name', '').split()[0]}'"},
                ],
                "reboot_required": False,
                "docs_url": "https://help.ubuntu.com/community/HardwareSupport",
            })
            continue

        # Build fix steps based on device status
        if status == "MISSING":
            steps = kb_entry.get("fix_missing", [])
            notes = kb_entry.get("notes", "")
            issue = f"{device['name']} has no driver loaded. {notes}".strip()
            severity = "HIGH"
        elif status == "SUBOPTIMAL":
            steps = kb_entry.get("fix_suboptimal",
                                 kb_entry.get("fix_missing", []))
            notes = kb_entry.get("notes", "")
            issue = (f"{device['name']} has a better driver or configuration available. "
                     f"{notes}").strip()
            severity = "MEDIUM"
        else:
            continue

        if distro["tier"] != "FULL":
            steps = _annotate_partial_distro(steps, distro)

        recs.append({
            "device":          device,
            "issue":           issue,
            "severity":        severity,
            "fix_steps":       steps,
            "reboot_required": kb_entry.get("reboot_required", False),
            "docs_url":        kb_entry.get("docs_url"),
        })

    # ── Battery health warnings ────────────────────────────────────────────
    if battery:
        health = battery.get("health_pct")
        if health is not None:
            if health < 50:
                recs.append({
                    "device": {"name": f"Battery ({battery.get('name', 'BAT0')})",
                               "category": "BATTERY", "status": "DEGRADED"},
                    "issue":  (f"Battery health is critically low at {health}%. "
                               f"Battery replacement recommended."),
                    "severity": "HIGH",
                    "fix_steps": [
                        {"description": "Check detailed battery info",
                         "cmd": "upower -i $(upower -e | grep BAT)"},
                        {"description": "On ThinkPads, check via TLP",
                         "cmd": "sudo tlp-stat -b 2>/dev/null"},
                    ],
                    "reboot_required": False,
                    "docs_url": None,
                })
            elif health < 70:
                recs.append({
                    "device": {"name": f"Battery ({battery.get('name', 'BAT0')})",
                               "category": "BATTERY", "status": "DEGRADED"},
                    "issue":  (f"Battery health is {health}% — noticeably degraded from new."),
                    "severity": "MEDIUM",
                    "fix_steps": [
                        {"description": "Check full battery details",
                         "cmd": "upower -i $(upower -e | grep BAT)"},
                        {"description": "Enable battery conservation mode if supported",
                         "cmd": "echo 1 | sudo tee /sys/bus/platform/drivers/ideapad_acpi/VPC2004:00/conservation_mode 2>/dev/null || echo 'Conservation mode not available on this laptop'"},
                    ],
                    "reboot_required": False,
                    "docs_url": None,
                })

    # ── BIOS update check ─────────────────────────────────────────────────
    if bios:
        recs.append({
            "device": {"name": "BIOS/UEFI Firmware",
                       "category": "FIRMWARE", "status": "UNKNOWN"},
            "issue":  (f"BIOS version {bios.get('version', 'unknown')} "
                       f"dated {bios.get('date', 'unknown')}. "
                       f"Check if a newer version is available."),
            "severity": "LOW",
            "fix_steps": [
                {"description": "Check for BIOS/firmware updates via fwupd",
                 "cmd": "sudo fwupdmgr refresh && sudo fwupdmgr get-updates"},
                {"description": "Apply any available firmware updates",
                 "cmd": "sudo fwupdmgr update"},
                {"description": "Also check your laptop manufacturer's support page",
                 "cmd": f"echo 'BIOS: {bios.get(\"vendor\", \"\")} {bios.get(\"version\", \"\")} ({bios.get(\"date\", \"\")})'"},
            ],
            "reboot_required": True,
            "docs_url": "https://fwupd.org",
        })

    # ── Sort by severity ──────────────────────────────────────────────────
    severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    recs.sort(key=lambda r: severity_order.get(r["severity"], 3))

    return recs


def _annotate_partial_distro(steps: list, distro: dict) -> list:
    """
    For PARTIAL distro support, annotate apt commands with a note
    that the user should adapt them to their package manager.
    """
    annotated = []
    pkg_mgr = distro.get("install_cmd", "").split()[0] if distro.get("install_cmd") else "dnf"
    for step in steps:
        cmd = step.get("cmd", "")
        if cmd and "apt install" in cmd:
            annotated.append({
                "description": step["description"] +
                               f" (adapt for {distro.get('pkg_manager', 'your package manager')})",
                "cmd": cmd + f"  # NOTE: replace 'apt install' with '{pkg_mgr} install'",
            })
        elif cmd and "apt " in cmd:
            annotated.append({
                "description": step["description"] +
                               f" (adapt 'apt' to '{pkg_mgr}')",
                "cmd": cmd,
            })
        else:
            annotated.append(step)
    return annotated