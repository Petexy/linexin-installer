#!/bin/bash

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_msg() {
    echo -e "${GREEN}[INFO]${NC} $1" >&2
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" >&2
}

print_debug() {
    echo -e "${BLUE}[DEBUG]${NC} $1" >&2
}

[[ $EUID -ne 0 ]] && { print_error "This script must be run as root"; exit 1; }

detect_esp() {
    for esp_path in "/boot/efi" "/boot" "/efi"; do
        if mountpoint -q "$esp_path" 2>/dev/null; then
            if [ -d "$esp_path/EFI" ] || [ -w "$esp_path" ]; then
                echo "$esp_path"
                return 0
            fi
        fi
    done
    
    local esp_part=$(lsblk -f | grep -E "(fat32|vfat)" | head -1 | awk '{print $1}')
    if [ -n "$esp_part" ]; then
        echo "/boot"
        return 0
    fi
    
    return 1
}

detect_boot_mode() {
    if [ -d /sys/firmware/efi/efivars ]; then
        echo "uefi"
    else
        echo "legacy"
    fi
}

detect_other_os() {
    print_msg "═══════════════════════════════════════════"
    print_msg "Starting OS Detection"
    print_msg "═══════════════════════════════════════════"
    
    local current_root_device=$(df / | tail -1 | awk '{print $1}')
    local current_root_uuid=$(blkid -s UUID -o value "$current_root_device" 2>/dev/null)
    
    print_debug "Current root: $current_root_device (UUID: $current_root_uuid)"
    
    print_msg "Method 1: Checking all disk partitions..."
    
    local all_partitions=$(lsblk -rno NAME,TYPE | awk '$2=="part"{print "/dev/"$1}')
    
    for device in $all_partitions; do
        [ "$device" = "$current_root_device" ] && continue
        
        local fstype=$(blkid -s TYPE -o value "$device" 2>/dev/null)
        local uuid=$(blkid -s UUID -o value "$device" 2>/dev/null)
        
        [ -z "$fstype" ] && continue
        
        print_debug "Checking $device ($fstype, UUID: $uuid)..."
        
        case "$fstype" in
            ext4|ext3|ext2|btrfs|xfs|f2fs|jfs|reiserfs)
                local temp_mount="/tmp/check_os_$$_$(basename $device)"
                rm -rf "$temp_mount" 2>/dev/null
                mkdir -p "$temp_mount"
                
                if mount -o ro "$device" "$temp_mount" 2>/dev/null; then
                    local os_name=""
                    local is_other_os=false
                    
                    if [ -f "$temp_mount/etc/manjaro-release" ]; then
                        os_name="Manjaro Linux"
                        is_other_os=true
                    elif [ -f "$temp_mount/etc/os-release" ]; then
                        local detected_name=$(grep '^NAME=' "$temp_mount/etc/os-release" 2>/dev/null | cut -d'"' -f2)
                        local detected_id=$(grep '^ID=' "$temp_mount/etc/os-release" 2>/dev/null | cut -d'=' -f2 | tr -d '"')
                        
                        if [ -n "$detected_name" ]; then
                            os_name="$detected_name"
                            if [ "$uuid" != "$current_root_uuid" ] && ! echo "$detected_name" | grep -qi "linexin"; then
                                is_other_os=true
                            fi
                        fi
                    elif [ -f "$temp_mount/etc/lsb-release" ]; then
                        local detected_name=$(grep '^DISTRIB_ID=' "$temp_mount/etc/lsb-release" 2>/dev/null | cut -d'=' -f2)
                        if [ -n "$detected_name" ] && [ "$detected_name" != "Linexin" ]; then
                            os_name="$detected_name"
                            is_other_os=true
                        fi
                    elif [ -f "$temp_mount/etc/debian_version" ]; then
                        os_name="Debian/Ubuntu"
                        is_other_os=true
                    elif [ -f "$temp_mount/etc/redhat-release" ]; then
                        os_name="Red Hat/CentOS/Fedora"
                        is_other_os=true
                    elif [ -f "$temp_mount/etc/fedora-release" ]; then
                        os_name="Fedora"
                        is_other_os=true
                    elif [ -f "$temp_mount/etc/gentoo-release" ]; then
                        os_name="Gentoo"
                        is_other_os=true
                    elif [ -d "$temp_mount/boot" ] && [ -d "$temp_mount/usr" ] && [ -d "$temp_mount/etc" ]; then
                        if ls "$temp_mount/boot/"vmlinuz* >/dev/null 2>&1 || \
                           ls "$temp_mount/boot/"initrd* >/dev/null 2>&1 || \
                           ls "$temp_mount/boot/"initramfs* >/dev/null 2>&1; then
                            os_name="Generic Linux installation"
                            is_other_os=true
                        fi
                    fi
                    
                    if [ "$is_other_os" = true ]; then
                        print_msg "✓ FOUND LINUX: $os_name on $device"
                        umount "$temp_mount" 2>/dev/null
                        rm -rf "$temp_mount"
                        echo "true"
                        return 0
                    fi
                    
                    umount "$temp_mount" 2>/dev/null
                fi
                rm -rf "$temp_mount"
                ;;
                
            ntfs)
                local temp_mount="/tmp/check_win_$$_$(basename $device)"
                rm -rf "$temp_mount" 2>/dev/null
                mkdir -p "$temp_mount"
                
                if mount -t ntfs-3g -o ro "$device" "$temp_mount" 2>/dev/null || \
                   mount -t ntfs -o ro "$device" "$temp_mount" 2>/dev/null; then
                    if [ -d "$temp_mount/Windows" ] || [ -d "$temp_mount/windows" ] || \
                       [ -f "$temp_mount/bootmgr" ] || [ -f "$temp_mount/ntldr" ]; then
                        print_msg "✓ FOUND WINDOWS on $device"
                        umount "$temp_mount" 2>/dev/null
                        rm -rf "$temp_mount"
                        echo "true"
                        return 0
                    fi
                    umount "$temp_mount" 2>/dev/null
                fi
                rm -rf "$temp_mount"
                ;;
        esac
    done
    
    if [ "$BOOT_MODE" = "uefi" ] && [ -n "$ESP_PATH" ] && [ -d "$ESP_PATH/EFI" ]; then
        print_msg "Method 2: Checking ESP for bootloaders..."
        
        for dir in "$ESP_PATH/EFI"/*; do
            [ ! -d "$dir" ] && continue
            local dirname=$(basename "$dir")
            
            case "$dirname" in
                systemd|BOOT|Boot|refind|tools|Linexin)
                    print_debug "Skipping system directory: $dirname"
                    ;;
                Microsoft|microsoft|Windows|windows)
                    print_msg "✓ FOUND: Windows bootloader in ESP"
                    echo "true"
                    return 0
                    ;;
                ubuntu|Ubuntu|debian|Debian|manjaro|Manjaro|fedora|Fedora|opensuse|openSUSE|mint|Mint)
                    print_msg "✓ FOUND: $dirname bootloader in ESP"
                    echo "true"
                    return 0
                    ;;
                *)
                    if [ -f "$dir/grubx64.efi" ] || [ -f "$dir/shimx64.efi" ] || \
                       [ -f "$dir/grub.efi" ] || [ -f "$dir/bootmgfw.efi" ]; then
                        print_msg "✓ FOUND: $dirname bootloader in ESP"
                        echo "true"
                        return 0
                    fi
                    ;;
            esac
        done
    fi
    
    if [ "$BOOT_MODE" = "uefi" ] && command -v efibootmgr &>/dev/null; then
        print_msg "Method 3: Checking EFI entries..."
        local efi_output=$(efibootmgr 2>/dev/null)
        
        if echo "$efi_output" | grep -qiE "Windows|Microsoft|Ubuntu|Manjaro|Debian|Fedora|openSUSE|Mint"; then
            local non_linexin_entries=$(echo "$efi_output" | grep -iE "Windows|Microsoft|Ubuntu|Manjaro|Debian|Fedora|openSUSE|Mint" | grep -v -i "Linexin")
            if [ -n "$non_linexin_entries" ]; then
                local found_entry=$(echo "$non_linexin_entries" | head -1)
                print_msg "✓ EFI entry FOUND: $found_entry"
                echo "true"
                return 0
            fi
        fi
    fi
    
    if command -v os-prober &>/dev/null || pacman -S --noconfirm os-prober ntfs-3g &>/dev/null; then
        if command -v os-prober &>/dev/null; then
            print_msg "Method 4: Running os-prober..."
            
            echo 'GRUB_DISABLE_OS_PROBER=false' >> /etc/default/grub 2>/dev/null || true
            
            local prober_output=$(timeout 30 os-prober 2>/dev/null)
            
            if [ -n "$prober_output" ]; then
                local temp_prober="/tmp/prober_$$"
                echo "$prober_output" > "$temp_prober"
                
                while IFS=: read -r device name rest; do
                    if [ "$device" != "$current_root_device" ] && [ -n "$name" ]; then
                        print_msg "✓ os-prober FOUND: $name on $device"
                        rm -f "$temp_prober"
                        echo "true"
                        return 0
                    fi
                done < "$temp_prober"
                
                rm -f "$temp_prober"
            fi
        fi
    fi
    
    print_msg "═══════════════════════════════════════════"
    print_msg "RESULT: No other OS detected"
    print_msg "═══════════════════════════════════════════"
    echo "false"
}

install_systemd_boot() {
    local esp_path=$1
    print_msg "Installing systemd-boot to $esp_path..."
    
    if ! bootctl --esp-path="$esp_path" install; then
        print_error "bootctl install failed"
        return 1
    fi
    
    mkdir -p "$esp_path/loader"
    cat > "$esp_path/loader/loader.conf" <<EOF
default  linexin.conf
timeout  0
console-mode max
editor   no
EOF
    
    mkdir -p "$esp_path/loader/entries"
    local root_uuid=$(findmnt -no UUID /)
    
    cat > "$esp_path/loader/entries/linexin.conf" <<EOF
title   Linexin
linux   /vmlinuz-linux
initrd  /initramfs-linux.img
options root=UUID=$root_uuid rw quiet splash
EOF
    
    cat > "$esp_path/loader/entries/linexin-fallback.conf" <<EOF
title   Linexin (fallback)
linux   /vmlinuz-linux
initrd  /initramfs-linux-fallback.img
options root=UUID=$root_uuid rw
EOF
    
    local esp_device=$(findmnt -no SOURCE "$esp_path")
    if [ -n "$esp_device" ]; then
        local esp_part_num=$(echo "$esp_device" | grep -o '[0-9]*$')
        local esp_disk=$(echo "$esp_device" | sed 's/[0-9]*$//')
        
        if [ -n "$esp_part_num" ] && [ -n "$esp_disk" ]; then
            efibootmgr -c -d "$esp_disk" -p "$esp_part_num" -L "Linexin" -l "\\EFI\\systemd\\systemd-bootx64.efi" 2>/dev/null || true
            
            local linux_boot=$(efibootmgr | grep "Linexin" | grep -o '^Boot[0-9A-F]\{4\}' | sed 's/Boot//' | head -1)
            if [ -n "$linux_boot" ]; then
                local other_boots=$(efibootmgr | grep "BootOrder:" | cut -d: -f2 | tr -d ' ' | sed "s/$linux_boot,\?//g" | sed 's/,$//')
                efibootmgr -o "$linux_boot${other_boots:+,$other_boots}" 2>/dev/null || true
            fi
        fi
    fi
    
    print_msg "systemd-boot installed successfully"
    return 0
}

install_grub() {
    local boot_mode=$1
    local esp_path=$2
    print_msg "Installing GRUB for $boot_mode mode..."
    
    if [ "$boot_mode" = "uefi" ]; then
        if ! command -v grub-install &>/dev/null || ! command -v efibootmgr &>/dev/null; then
            print_msg "Installing missing bootloader packages..."
            pacman -S --noconfirm --needed grub efibootmgr os-prober ntfs-3g || return 1
        else
            print_msg "Bootloader packages already installed."
        fi
        
        if ! grub-install --target=x86_64-efi --efi-directory="$esp_path" --bootloader-id=Linexin; then
            print_error "GRUB UEFI installation failed"
            return 1
        fi
    else
        if ! command -v grub-install &>/dev/null; then
            print_msg "Installing missing bootloader packages..."
            pacman -S --noconfirm --needed grub os-prober ntfs-3g || return 1
        else
            print_msg "Bootloader packages already installed."
        fi
        
        local root_device=$(findmnt -no SOURCE /)
        # Resolved symlinks (e.g. /dev/disk/by-uuid/...) to real device (e.g. /dev/sda1)
        if [ -L "$root_device" ] || [[ "$root_device" == /dev/disk/* ]]; then
             root_device=$(readlink -f "$root_device")
        fi
        
        print_debug "Root device: $root_device"
        
        local root_disk=""
        if [[ "$root_device" =~ ^/dev/[a-z]+[0-9]+$ ]]; then
            root_disk=$(echo "$root_device" | sed 's/[0-9]*$//')
        elif [[ "$root_device" =~ ^/dev/nvme[0-9]+n[0-9]+p[0-9]+$ ]]; then
            root_disk=$(echo "$root_device" | sed 's/p[0-9]*$//')
        elif [[ "$root_device" =~ ^/dev/vd[a-z]+[0-9]+$ ]]; then
            root_disk=$(echo "$root_device" | sed 's/[0-9]*$//')
        else
            local parent_name=$(lsblk -no PKNAME "$root_device" 2>/dev/null | head -1)
            if [ -n "$parent_name" ]; then
                root_disk="/dev/$parent_name"
            else
                print_error "Could not determine root disk from $root_device"
                return 1
            fi
        fi
        
        print_debug "Detected root disk: $root_disk"
        
        if [ ! -b "$root_disk" ]; then
            print_error "Root disk $root_disk is not a valid block device"
            return 1
        fi
        
        print_msg "Installing GRUB to $root_disk"
        if ! grub-install --target=i386-pc "$root_disk"; then
            print_warning "Standard GRUB installation failed, attempting forced installation..."
            if ! grub-install --target=i386-pc --force "$root_disk"; then
                print_error "GRUB Legacy installation failed (even with --force)"
                return 1
            fi
            print_msg "GRUB installed successfully using --force"
        fi
    fi
    
    [ -f /etc/default/grub ] && cp /etc/default/grub /etc/default/grub.bak
    
    cat > /etc/default/grub <<'EOF'
GRUB_DEFAULT=0
GRUB_TIMEOUT=5
GRUB_DISTRIBUTOR="Linexin"
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"
GRUB_CMDLINE_LINUX=""
GRUB_TERMINAL_INPUT=console
GRUB_GFXMODE=auto
GRUB_GFXPAYLOAD_LINUX=keep
GRUB_DISABLE_RECOVERY=false
GRUB_DISABLE_OS_PROBER=false
GRUB_COLOR_NORMAL="light-blue/black"
GRUB_COLOR_HIGHLIGHT="light-cyan/blue"
EOF
    
    cat > /etc/lsb-release <<'EOF'
DISTRIB_ID=Linexin
DISTRIB_RELEASE=rolling
DISTRIB_DESCRIPTION="Linexin"
EOF
    
    print_msg "Cleaning up boot directory..."
    find /boot -name "*.png" -delete 2>/dev/null || true
    find "$esp_path" -name "*.png" -delete 2>/dev/null || true
    
    print_msg "Ensuring kernel files are accessible..."
    
    if [ ! -f "/boot/vmlinuz-linux" ]; then
        print_error "Kernel file /boot/vmlinuz-linux not found!"
        return 1
    fi
    
    if [ ! -f "/boot/initramfs-linux.img" ]; then
        print_error "Initramfs file /boot/initramfs-linux.img not found!"
        return 1
    fi
    
    if [ "$boot_mode" = "uefi" ] && [ "$esp_path" != "/boot" ]; then
        print_msg "Copying kernel files to ESP..."
        cp /boot/vmlinuz-linux "$esp_path/" || { print_error "Failed to copy kernel to ESP"; return 1; }
        cp /boot/initramfs-linux.img "$esp_path/" || { print_error "Failed to copy initramfs to ESP"; return 1; }
        cp /boot/initramfs-linux-fallback.img "$esp_path/" 2>/dev/null || print_warning "Could not copy fallback initramfs to ESP"
    fi
    
    print_msg "Clearing GRUB cache..."
    rm -rf /boot/grub/grubenv /boot/grub/*.mod /boot/grub/fonts 2>/dev/null || true
    
    print_msg "Generating fresh GRUB configuration..."
    export GRUB_DISABLE_OS_PROBER=false
    grub-mkconfig -o /boot/grub/grub.cfg.new || { print_error "GRUB configuration generation failed"; return 1; }
    
    print_msg "Verifying and cleaning GRUB configuration..."
    if grep -q "linux\.png\|initrd\.png" /boot/grub/grub.cfg.new; then
        print_warning "Found .png references in GRUB config, fixing..."
        sed -e 's/linux\.png/vmlinuz-linux/g' \
            -e 's/initrd\.png/initramfs-linux.img/g' \
            /boot/grub/grub.cfg.new > /boot/grub/grub.cfg.fixed
        mv /boot/grub/grub.cfg.fixed /boot/grub/grub.cfg.new
    fi
    
    sed -e 's/Arch Linux/Linexin/g' \
        -e "s/menuentry 'Arch/menuentry 'Linexin/g" \
        -e 's/menuentry "Arch/menuentry "Linexin/g' \
        /boot/grub/grub.cfg.new > /boot/grub/grub.cfg
    
    rm -f /boot/grub/grub.cfg.new
    
    if ! grep -q "vmlinuz-linux" /boot/grub/grub.cfg; then
        print_error "GRUB config does not contain proper kernel references"
        print_error "Manual configuration may be required"
        return 1
    fi
    
    print_msg "GRUB installed successfully"
    return 0
}

install_refind() {
    local esp_path=$1
    print_msg "Installing rEFInd to $esp_path..."
    
    if ! pacman -S --noconfirm refind; then
        print_error "Failed to install rEFInd package"
        return 1
    fi
    
    print_msg "Creating rEFInd directories..."
    mkdir -p "$esp_path/EFI/refind" || { print_error "Failed to create refind directory"; return 1; }
    mkdir -p "$esp_path/EFI/BOOT"
    
    if [ -d /usr/share/refind ]; then
        print_msg "Copying rEFInd files..."
        cp -r /usr/share/refind/* "$esp_path/EFI/refind/" || { print_error "Failed to copy rEFInd files"; return 1; }
    else
        print_error "rEFInd files not found in /usr/share/refind"
        return 1
    fi
    
    if [ -f "$esp_path/EFI/refind/refind_x64.efi" ]; then
        cp "$esp_path/EFI/refind/refind_x64.efi" "$esp_path/EFI/BOOT/bootx64.efi" 2>/dev/null || true
    fi
    
    local root_uuid=$(findmnt -no UUID /)
    cat > "$esp_path/refind_linux.conf" <<EOF
"Boot Linexin"                 "root=UUID=$root_uuid rw quiet splash"
"Boot Linexin (terminal)"      "root=UUID=$root_uuid rw systemd.unit=multi-user.target"
"Boot to single-user mode"     "root=UUID=$root_uuid rw single"
EOF
    
    cat > "$esp_path/EFI/refind/refind.conf" <<'EOF'
include themes/refind-theme-regular/theme.conf

timeout 5
hideui singleuser,hints,arrows,badges,hidden_tags
big_icon_size 128
small_icon_size 48
default_selection "vmlinuz-linux"
scan_all_linux_kernels true
fold_linux_kernels true
windows_recovery_files LRS_ESP:/EFI/Microsoft/Boot/bootmgfw.efi
scanfor manual,internal,external,optical
dont_scan_dirs ESP:/EFI/boot,ESP:/EFI/Boot
extra_kernel_version_strings linux-lts,linux
also_scan_dirs boot,EFI/manjaro,EFI/ubuntu,EFI/debian,EFI/fedora
EOF
    
    print_msg "Registering rEFInd with EFI..."
    local esp_device=$(findmnt -no SOURCE "$esp_path" 2>/dev/null)
    
        if [ -z "$esp_device" ]; then
            print_warning "Could not detect ESP device, rEFInd will work as fallback bootloader only"
            print_warning "To manually create EFI entry, run:"
            print_warning "  sudo efibootmgr --create --disk /dev/sdX --part N --label 'rEFInd' --loader '\\EFI\\refind\\refind_x64.efi'"
            return 0
        fi
        
        print_debug "ESP device: $esp_device"
        
        local esp_disk=""
        local esp_part_num=""
        
        if command -v lsblk &>/dev/null; then
            local pkname=$(lsblk -no PKNAME "$esp_device")
            esp_part_num=$(lsblk -no PARTN "$esp_device")
            
            # Handle NVMe/MMC parent notation if needed, but usually PKNAME gives just the name (e.g., nvme0n1)
            # We need full path
            if [ -n "$pkname" ]; then
                esp_disk="/dev/$pkname"
                print_debug "Device detection (lsblk): disk=$esp_disk part=$esp_part_num"
            fi
        fi

        # Fallback to regex if lsblk failed or returned empty
        if [ -z "$esp_disk" ] || [ -z "$esp_part_num" ]; then
            if [[ "$esp_device" =~ ^/dev/nvme[0-9]+n[0-9]+p[0-9]+$ ]]; then
                esp_disk=$(echo "$esp_device" | sed 's/p[0-9]*$//')
                esp_part_num=$(echo "$esp_device" | grep -o '[0-9]*$')
                print_debug "NVMe device detected: disk=$esp_disk part=$esp_part_num"
            elif [[ "$esp_device" =~ ^/dev/mmcblk[0-9]+p[0-9]+$ ]]; then
                esp_disk=$(echo "$esp_device" | sed 's/p[0-9]*$//')
                esp_part_num=$(echo "$esp_device" | grep -o '[0-9]*$')
                print_debug "MMC device detected: disk=$esp_disk part=$esp_part_num"
            elif [[ "$esp_device" =~ ^/dev/[sh]d[a-z]+[0-9]+$ ]]; then
                esp_disk=$(echo "$esp_device" | sed 's/[0-9]*$//')
                esp_part_num=$(echo "$esp_device" | grep -o '[0-9]*$')
                print_debug "SATA/SCSI device detected: disk=$esp_disk part=$esp_part_num"
            elif [[ "$esp_device" =~ ^/dev/vd[a-z]+[0-9]+$ ]]; then
                esp_disk=$(echo "$esp_device" | sed 's/[0-9]*$//')
                esp_part_num=$(echo "$esp_device" | grep -o '[0-9]*$')
                print_debug "VirtIO device detected: disk=$esp_disk part=$esp_part_num"
            elif [[ "$esp_device" =~ ^/dev/xvd[a-z]+[0-9]+$ ]]; then
                esp_disk=$(echo "$esp_device" | sed 's/[0-9]*$//')
                esp_part_num=$(echo "$esp_device" | grep -o '[0-9]*$')
                print_debug "Xen device detected: disk=$esp_disk part=$esp_part_num"
            else
                print_warning "Unsupported device type: $esp_device"
                print_warning "Manual EFI entry creation required:"
                print_warning "  sudo efibootmgr --create --disk <disk> --part <num> --label 'rEFInd' --loader '\\EFI\\refind\\refind_x64.efi'"
                return 0
            fi
        fi
        
        if [ -z "$esp_disk" ] || [ -z "$esp_part_num" ]; then
            print_error "Could not parse disk ($esp_disk) and partition ($esp_part_num) from $esp_device"
            print_warning "Manual EFI entry creation required"
            return 0
        fi
        
        if ! efibootmgr -v >/dev/null 2>&1; then
            print_warning "EFI variables not accessible, attempting to mount efivarfs..."
            mount -t efivarfs efivarfs /sys/firmware/efi/efivars 2>/dev/null
            
            if ! efibootmgr -v >/dev/null 2>&1; then
                print_warning "EFI variables still not accessible"
                print_warning "rEFInd will work as fallback bootloader, or create entry manually:"
                print_warning "  sudo efibootmgr --create --disk $esp_disk --part $esp_part_num --label 'rEFInd' --loader '\\EFI\\refind\\refind_x64.efi'"
                return 0
            fi
        fi
        
        print_msg "Removing old rEFInd entries..."
        efibootmgr 2>/dev/null | grep -i refind | grep -o '^Boot[0-9A-F]\{4\}' | sed 's/Boot//' | while read bootnum; do
            print_debug "Removing boot entry $bootnum"
            efibootmgr -b "$bootnum" -B 2>/dev/null || true
        done
        
        print_msg "Creating rEFInd EFI boot entry..."
        print_debug "Command: efibootmgr --create --disk $esp_disk --part $esp_part_num --label 'rEFInd' --loader '\\EFI\\refind\\refind_x64.efi'"
        
        if efibootmgr --create --disk "$esp_disk" --part "$esp_part_num" --label "rEFInd" --loader "\\EFI\\refind\\refind_x64.efi" 2>&1 | tee /tmp/efibootmgr.log; then
            print_msg "✓ rEFInd EFI entry created successfully"
            
            print_msg "Setting rEFInd as first boot option..."
            local refind_boot=$(efibootmgr 2>/dev/null | grep -i "rEFInd" | grep -o '^Boot[0-9A-F]\{4\}' | sed 's/Boot//' | head -1)
            if [ -n "$refind_boot" ]; then
                print_debug "rEFInd boot number: $refind_boot"
                local current_order=$(efibootmgr 2>/dev/null | grep "BootOrder:" | cut -d: -f2 | tr -d ' ')
                local other_boots=$(echo "$current_order" | sed "s/$refind_boot,\?//g" | sed 's/,$//' | sed 's/^,//')
                
                if efibootmgr -o "$refind_boot${other_boots:+,$other_boots}" 2>/dev/null; then
                    print_msg "✓ Boot order updated: rEFInd is now first"
                else
                    print_warning "Could not update boot order, but entry was created"
                fi
            fi
            
            print_msg ""
            print_msg "Current EFI boot entries:"
            efibootmgr 2>/dev/null | grep -E "(Boot|BootOrder)" || true
        else
            print_error "Failed to create rEFInd EFI entry"
            print_error "See /tmp/efibootmgr.log for details"
            print_warning ""
            print_warning "Manual fix required - run this command:"
            print_warning "  sudo efibootmgr --create --disk $esp_disk --part $esp_part_num --label 'rEFInd' --loader '\\EFI\\refind\\refind_x64.efi'"
            return 1
        fi
    
    print_msg "rEFInd installed successfully"
    return 0
}

main() {
    print_msg "Bootloader Configuration Script"
    print_msg "═══════════════════════════════════════════"
    
    if [ ! -f /etc/arch-release ]; then
        print_warning "This doesn't appear to be an Arch Linux system"
    fi
    
    if [ ! -f "/boot/initramfs-linux.img" ]; then
        print_warning "initramfs not found, generating..."
        mkinitcpio -P
    fi
    
    BOOT_MODE=$(detect_boot_mode)
    print_msg "Boot mode: $BOOT_MODE"
    
    ESP_PATH=""
    if [ "$BOOT_MODE" = "uefi" ]; then
        ESP_PATH=$(detect_esp)
        if [ -z "$ESP_PATH" ]; then
            print_error "Could not detect ESP mount point"
            print_error "Please ensure ESP is mounted at /boot, /boot/efi, or /efi"
            exit 1
        fi
        print_msg "ESP: $ESP_PATH"
        
        if [ -d "$ESP_PATH/EFI" ]; then
            print_msg "Current ESP contents:"
            ls -la "$ESP_PATH/EFI/" 2>/dev/null | grep "^d" | awk '{print "  - "$9}' || true
        fi
    fi
    
    if [ "$1" = "--debug" ] || [ "$DEBUG" = "1" ]; then
        set -x
        print_msg "DEBUG MODE ENABLED"
    fi
    
    OTHER_OS=$(detect_other_os)
    
    print_debug "Detection result: OTHER_OS='$OTHER_OS'"
    
    if [ "$FORCE_REFIND" = "1" ] || [ "$FORCE_REFIND" = "true" ]; then
        print_warning "FORCE_REFIND enabled - installing rEFInd"
        OTHER_OS="true"
    fi
    
    print_msg ""
    print_msg "FINAL DECISION:"
    print_msg "═══════════════════════════════════════════"
    
    if [ "$OTHER_OS" = "true" ]; then
        print_msg ">>> INSTALLING rEFInd (multi-boot detected) <<<"
        if [ "$BOOT_MODE" = "uefi" ]; then
            if ! install_refind "$ESP_PATH"; then
                print_error "rEFInd installation failed!"
                exit 1
            fi
        else
            print_msg ">>> INSTALLING GRUB (Legacy multi-boot) <<<"
            if ! install_grub "$BOOT_MODE" "$ESP_PATH"; then
                print_error "GRUB installation failed!"
                exit 1
            fi
        fi
    else
        print_msg ">>> INSTALLING systemd-boot (single OS) <<<"
        print_warning "To force rEFInd: FORCE_REFIND=1 $0"
        print_warning "To enable debug: DEBUG=1 $0 or $0 --debug"
        if [ "$BOOT_MODE" = "uefi" ]; then
            if ! install_systemd_boot "$ESP_PATH"; then
                print_error "systemd-boot installation failed!"
                exit 1
            fi
        else
            print_msg ">>> INSTALLING GRUB (Legacy single OS) <<<"
            if ! install_grub "$BOOT_MODE" "$ESP_PATH"; then
                print_error "GRUB installation failed!"
                exit 1
            fi
        fi
    fi
    
    print_msg "═══════════════════════════════════════════"
    print_msg "BOOTLOADER INSTALLED SUCCESSFULLY!"
    print_msg "Please reboot to test the new bootloader"
}

main "$@"