#!/bin/bash

# Post-Installation Script for Arch Linux
# Converted from Calamares shellprocess-final.conf
# This script handles system configuration and cleanup only

# Set variables
ROOT="/"  # Adjust this to your actual mount point if different
USER="${USER:-}"  # Will be set to the username if available
DE_SELECTION_FILE="/de_selection"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_msg() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Function to check internet connectivity
check_internet() {
    local test_urls=("8.8.8.8" "1.1.1.1" "archlinux.org")
    
    print_msg "Checking internet connectivity..."
    
    # Try ping first (fastest)
    for url in "${test_urls[@]:0:2}"; do
        if ping -c 1 -W 3 "$url" &>/dev/null; then
            print_msg "Internet connection detected via ping to $url"
            return 0
        fi
    done
    
    # Try wget as backup
    if command -v wget &>/dev/null; then
        if wget --spider --timeout=5 -q "https://${test_urls[2]}" 2>/dev/null; then
            print_msg "Internet connection detected via wget to ${test_urls[2]}"
            return 0
        fi
    fi
    
    # Try curl as another backup
    if command -v curl &>/dev/null; then
        if curl --connect-timeout 5 -s "https://${test_urls[2]}" &>/dev/null; then
            print_msg "Internet connection detected via curl to ${test_urls[2]}"
            return 0
        fi
    fi
    
    print_warning "No internet connection detected"
    return 1
}

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   print_error "This script must be run as root"
   exit 1
fi

# Check if target system is mounted
if ! mountpoint -q "$ROOT"; then
    print_error "Target system is not mounted at $ROOT"
    exit 1
fi

print_msg "Starting post-installation configuration..."

print_msg "Removing live user account..."

# Check if liveuser exists and remove it
if id "liveuser" &>/dev/null; then
    print_msg "Found liveuser account, removing..."
    
    # Kill any processes owned by liveuser
    pkill -u liveuser 2>/dev/null || true
    
    # Remove user and home directory
    userdel -r liveuser 2>/dev/null || true
    
    # Force remove home directory if it still exists
    rm -rf /home/liveuser 2>/dev/null || true
    
    # Remove from any additional groups (belt and suspenders approach)
    groupdel liveuser 2>/dev/null || true
    
    print_msg "liveuser account removed successfully"
else
    print_msg "liveuser account not found, skipping removal"
fi

# Execute commands in chroot environment
# Note: Commands starting with "-" will ignore errors

print_msg "Cleaning up installation files..."

# Remove temporary sudo configuration
rm -f /etc/sudoers.d/g_wheel 2>/dev/null || true

# Remove mkinitcpio configuration directory
rm -rf /etc/mkinitcpio.conf.d 2>/dev/null || true

# Remove getty service customization
rm -rf /etc/systemd/system/getty@tty1.service.d 2>/dev/null || true

# Remove pacman initialization service
rm -f /etc/systemd/system/multi-user.target.wants/pacman-init.service 2>/dev/null || true
rm -f /etc/systemd/system/pacman-init.service 2>/dev/null || true
rm -f /etc/systemd/system/etc-pacman.d-gnupg.mount 2>/dev/null || true

# Remove root login script
rm -f /root/.zlogin 2>/dev/null || true

# Remove polkit rules
rm -f /etc/polkit-1/rules.d/49-nopasswd_global.rules 2>/dev/null || true
rm -f /etc/polkit-1/rules.d/49-nopasswd-calamares.rules 2>/dev/null || true

# Remove GDM custom configuration
rm -f /etc/gdm/custom.conf 2>/dev/null || true

# Remove message of the day
rm -f /etc/motd 2>/dev/null || true

# Remove dconf configurations
rm -rf /etc/dconf/db/local.d/00-logout 2>/dev/null || true
rm -rf /etc/dconf/db/local.d/06-disableoverviewinstallation 2>/dev/null || true

# Hide specific desktop applications
echo "Hidden=true" >> /usr/share/applications/bssh.desktop 2>/dev/null || true
echo "Hidden=true" >> /usr/share/applications/avahi-discover.desktop 2>/dev/null || true
echo "Hidden=true" >> /usr/share/applications/qv4l2.desktop 2>/dev/null || true
echo "Hidden=true" >> /usr/share/applications/qvidcap.desktop 2>/dev/null || true
echo "Hidden=true" >> /usr/share/applications/stoken-gui.desktop 2>/dev/null || true
echo "Hidden=true" >> /usr/share/applications/stoken-gui-small.desktop 2>/dev/null || true
echo "Hidden=true" >> /usr/share/applications/vim.desktop 2>/dev/null || true
echo "Hidden=true" >> /usr/share/applications/lftp.desktop 2>/dev/null || true
echo "Hidden=true" >> /usr/share/applications/bvnc.desktop 2>/dev/null || true
echo "Hidden=true" >> /usr/share/applications/org.gnome.Extensions.desktop 2>/dev/null || true

# Enable system services
systemctl enable gdm 2>/dev/null || true
systemctl enable bluetooth 2>/dev/null || true

# Move and configure system files
mv /etc/skel/.zshrc_postinstall /etc/skel/.zshrc 2>/dev/null || true
cp /usr/share/refind/icons/os_linexin.png /boot/vmlinuz-linux.png 2>/dev/null || true
mv /etc/os-release /usr/lib/os-release 2>/dev/null || true
ln -sf /usr/lib/os-release /etc/os-release 2>/dev/null || true
mv /etc/mkinitcpio.d/linux-postinstall.preset /etc/mkinitcpio.d/linux.preset 2>/dev/null || true
mv /usr/share/pixmaps/archlinux-logo-text-dark-postinstall.svg /usr/share/pixmaps/archlinux-logo-text-dark.svg
mv /usr/share/pixmaps/archlinux-logo-text-postinstall.svg /usr/share/pixmaps/archlinux-logo-text.svg

# Remove specific GNOME extension
rm -rf /usr/share/gnome-shell/extensions/BringOutSubmenuOfPowerOffLogoutButton@pratap.fastmail.fm 2>/dev/null || true

# Update Plymouth theme
mv /usr/share/plymouth/themes/spinner/watermark-postinstall.png /usr/share/plymouth/themes/spinner/watermark.png 2>/dev/null || true



# Set executable permissions for custom scripts
chmod +x /usr/bin/bsod 2>/dev/null || true
chmod +x /usr/local/bin/rum 2>/dev/null || true
chmod +x /usr/bin/photo 2>/dev/null || true
chmod +x /usr/bin/designer 2>/dev/null || true
chmod +x /usr/bin/publisher 2>/dev/null || true
chmod +x /usr/bin/linexin-sound-fix-usb-dac 2>/dev/null || true

# Set permissions for GNOME Shell extensions
chmod 755 /usr/share/gnome-shell/extensions -R 2>/dev/null || true

# Update dconf database
dconf update 2>/dev/null || true

# Set audio volume to maximum
#amixer set 'Master' 100% 2>/dev/null || true
#alsactl store 2>/dev/null || true

# Initialize pacman keys (always needed)
rm -rf /etc/pacman.d/gnupg 2>/dev/null || true
pacman-key --init 2>/dev/null || true
pacman-key --populate archlinux 2>/dev/null || true

# Remove specific packages (works offline since they're already installed)
pacman -R totem --noconfirm 2>/dev/null || true
pacman -R archinstall --noconfirm 2>/dev/null || true
pacman -R linexin-installer --noconfirm 2>/dev/null || true
pacman -R gparted --noconfirm 2>/dev/null || true

#Kinexin Update
check_de_selection() {
    if [[ ! -f "$DE_SELECTION_FILE" ]]; then
        print_error "DE selection file not found at $DE_SELECTION_FILE"
        return 2
    fi
    
    local de_value
    de_value=$(cat "$DE_SELECTION_FILE" 2>/dev/null | tr -d '[:space:]')
    
    if [[ "$de_value" == "0" ]]; then
        print_msg "DE selection: Linexin"
        return 0
    elif [[ "$de_value" == "1" ]]; then
        print_msg "DE selection: Kinexin"
        pacman -Sy kinexin-desktop --noconfirm
        pacman -Rsc gnome --noconfirm 
        return 0
    else
        print_error "Invalid DE selection value: '$de_value'. Expected 0 or 1"
        return 2
    fi
}

# Update system packages (only if internet is available)
if check_internet; then
    print_msg "Internet connection available, proceeding with package updates..."
    pacman -Sy archlinux-keyring linux --noconfirm 2>/dev/null || true
    pacman -Syu --noconfirm 2>/dev/null || true
    check_de_selection
else
    print_warning "No internet connection available, skipping package updates"
    print_warning "You can run 'pacman -Syu' manually later when internet is available"
fi



# Regenerate initramfs
mkinitcpio -P 2>/dev/null || true



print_msg "Post-installation configuration completed successfully!"
