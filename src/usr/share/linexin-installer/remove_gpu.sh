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
        pacman -Rdd --noconfirm "$pkg"
    fi
}

# Function to remove all NVIDIA packages (vulkan-driver is already satisfied by
# vulkan-intel / vulkan-radeon / vulkan-nouveau shipped on the ISO)
remove_nvidia_stack() {
    echo "Removing NVIDIA driver stack..."
    # Remove lib32-nvidia-utils first (depends on exact nvidia-utils version)
    remove_if_installed "lib32-nvidia-utils"
    remove_if_installed "nvidia-open"
    remove_if_installed "nvidia-utils"
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
        echo "Action: Remove vulkan-radeon/vulkan-intel/vulkan-nouveau, keep nvidia-open"
        remove_if_installed "vulkan-radeon"
        remove_if_installed "vulkan-intel"
        remove_if_installed "vulkan-nouveau"
    else
        echo "Configuration: Pre-Turing NVIDIA without AMD"
        echo "Action: Remove NVIDIA stack and vulkan-radeon, use nouveau"
        remove_if_installed "vulkan-radeon"
        remove_if_installed "vulkan-intel"
        remove_nvidia_stack
    fi
    
elif [ "$has_nvidia" = true ] && [ "$has_amd" = true ]; then
    # Both NVIDIA and AMD present
    if [ "$nvidia_is_turing_or_newer" = false ]; then
        echo "Configuration: Pre-Turing NVIDIA with AMD"
        echo "Action: Remove NVIDIA stack, keep vulkan-radeon"
        remove_if_installed "vulkan-intel"
        remove_nvidia_stack
    else
        echo "Configuration: NVIDIA Turing or newer with AMD"
        echo "Action: Keep nvidia and vulkan-radeon, remove unused vulkan drivers"
        remove_if_installed "vulkan-intel"
        remove_if_installed "vulkan-nouveau"
    fi
    
elif [ "$has_nvidia" = false ] && [ "$has_amd" = true ]; then
    # Only AMD, no NVIDIA
    echo "Configuration: AMD without NVIDIA"
    echo "Action: Remove NVIDIA stack, keep vulkan-radeon"
    remove_if_installed "vulkan-intel"
    remove_if_installed "vulkan-nouveau"
    remove_nvidia_stack
    
else
    # No dedicated GPU detected (integrated GPU only — likely Intel iGPU)
    echo "Configuration: Integrated GPU only (no dedicated GPU detected)"
    echo "Action: Remove NVIDIA stack and unused vulkan drivers"
    remove_if_installed "vulkan-radeon"
    remove_if_installed "vulkan-nouveau"
    remove_nvidia_stack
fi

echo ""
echo "Driver configuration complete."

exit 0
