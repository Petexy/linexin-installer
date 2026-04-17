#!/usr/bin/env bash

# Function to check if a package is installed
is_installed() {
    pacman -Q "$1" &>/dev/null
}

# Function to remove package if installed
remove_if_installed() {
    local pkg="$1"
    if is_installed "$pkg"; then
        echo "Removing $pkg..."
        pacman -Rns --noconfirm "$pkg"
    fi
}

# Function to check if NVIDIA GPU is Turing or newer
is_turing_or_newer() {
    local device_id="$1"
    
    # Convert device ID to uppercase for comparison
    device_id=$(echo "$device_id" | tr '[:lower:]' '[:upper:]')
    
    # Turing and newer architectures based on device IDs
    # Turing: 1E00-1FFF, 2100-21FF
    # Ampere: 2200-24FF
    # Ada Lovelace: 2600-28FF
    # Hopper and newer: 2300+
    
    # Extract the hex value
    local hex_val="0x${device_id}"
    local dec_val=$((hex_val))
    
    # Check if it's Turing (TU1XX) or newer
    # Turing starts at 0x1E00 (7680 decimal)
    if [ $dec_val -ge 7680 ]; then
        return 0  # True - Turing or newer
    fi
    
    # Also check for newer RTX 20 series (0x2180-0x21FF range)
    if [ $dec_val -ge 8576 ] && [ $dec_val -le 8703 ]; then
        return 0  # True - Turing or newer
    fi
    
    return 1  # False - Pre-Turing
}

# Detect all GPUs (both VGA and 3D controllers)
echo "Detecting GPU configuration..."

# Get all NVIDIA GPUs
nvidia_gpus=$(lspci -nn | grep -E "(VGA|3D controller).*NVIDIA" | grep -oP '\[10de:([0-9a-f]{4})\]' | cut -d: -f2 | tr -d ']')
# Get all AMD GPUs
amd_gpus=$(lspci -nn | grep -E "(VGA|3D controller).*(AMD|ATI)" | grep -oP '\[1002:([0-9a-f]{4})\]' | cut -d: -f2 | tr -d ']')

# Check what GPUs are present
has_nvidia=false
has_amd=false
nvidia_is_turing_or_newer=false

if [ -n "$nvidia_gpus" ]; then
    has_nvidia=true
    echo "NVIDIA GPU(s) detected:"
    
    # Check each NVIDIA GPU to see if any is Turing or newer
    for gpu_id in $nvidia_gpus; do
        echo "  - Device ID: $gpu_id"
        if is_turing_or_newer "$gpu_id"; then
            nvidia_is_turing_or_newer=true
            echo "    -> Turing or newer architecture detected"
        else
            echo "    -> Pre-Turing architecture detected"
        fi
    done
fi

if [ -n "$amd_gpus" ]; then
    has_amd=true
    echo "AMD GPU(s) detected:"
    for gpu_id in $amd_gpus; do
        echo "  - Device ID: $gpu_id"
    done
fi

# Apply the logic based on detected GPUs
echo ""
echo "Applying driver configuration..."

if [ "$has_nvidia" = true ] && [ "$has_amd" = false ]; then
    # Only NVIDIA, no AMD
    if [ "$nvidia_is_turing_or_newer" = true ]; then
        echo "Configuration: NVIDIA Turing or newer without AMD"
        echo "Action: Remove vulkan-radeon, keep nvidia-open"
        remove_if_installed "vulkan-radeon"
    else
        echo "Configuration: Pre-Turing NVIDIA without AMD"
        echo "Action: Remove nvidia-open and vulkan-radeon, use open-source nouveau driver"
        remove_if_installed "nvidia-open"
        remove_if_installed "nvidia-utils"
        remove_if_installed "vulkan-radeon"
    fi
    
elif [ "$has_nvidia" = true ] && [ "$has_amd" = true ]; then
    # Both NVIDIA and AMD present
    if [ "$nvidia_is_turing_or_newer" = false ]; then
        echo "Configuration: Pre-Turing NVIDIA with AMD"
        echo "Action: Remove nvidia-open, use open-source nouveau driver"
        remove_if_installed "nvidia-open"
        remove_if_installed "nvidia-utils"
    else
        echo "Configuration: NVIDIA Turing or newer with AMD"
        echo "Action: Keep both drivers as configured"
    fi
    
elif [ "$has_nvidia" = false ] && [ "$has_amd" = true ]; then
    # Only AMD, no NVIDIA
    echo "Configuration: AMD without NVIDIA"
    echo "Action: Remove nvidia-open"
    remove_if_installed "nvidia-open"
    remove_if_installed "nvidia-utils"
    
else
    # No dedicated GPU detected
    echo "Warning: No dedicated GPU detected"
    echo "This might be an integrated GPU only system"
fi

echo ""
echo "Driver configuration complete."

exit 0
