#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import subprocess
import gi
import json
import os

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from disk_utils import DiskUtils
from gi.repository import Gtk, Adw, Gio, Gdk, GLib, GObject
from simple_localization_manager import get_localization_manager
_ = get_localization_manager().get_text

class DiskUtilityWidget(Gtk.Box):

    __gsignals__ = {
        'continue-to-next-page': (GObject.SignalFlags.RUN_FIRST, None, ())
    }

    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self.init_partition_config()
        get_localization_manager().register_widget(self)

        # --- FIX: Apply the CSS globally to the display, not just this widget. ---
        # This ensures the hover effects on child widgets like Adw.ActionRow work correctly.
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
            .disk-row:hover {
                background-color: alpha(@accent_color, 0.1);
            }
            
            .partition-row:hover {
                background-color: alpha(@accent_color, 0.08);
            }
            .free-space-row:hover {
                background-color: alpha(@accent_color, 0.05);
            }
        """)
        # Apply the CSS provider to the entire display
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), 
            css_provider, 
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.selected_disk = None
        
        scrolled_window = Gtk.ScrolledWindow(vexpand=True)
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.append(scrolled_window)

        self.clamp = Adw.Clamp(margin_top=12, margin_bottom=12, margin_start=12, margin_end=12, maximum_size=600)
        scrolled_window.set_child(self.clamp)

        self.group = Adw.PreferencesGroup()
        self.clamp.set_child(self.group)
        
        # --- Bottom Navigation Buttons ---
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        button_box.set_halign(Gtk.Align.CENTER)
        self.append(button_box)

        self.btn_back = Gtk.Button(label="Back", margin_bottom=20, margin_top=20)
        self.btn_back.add_css_class('buttons_all')
        button_box.append(self.btn_back)

        
        self.action_bar = Gtk.ActionBar()
        self.action_bar_revealer = Gtk.Revealer(child=self.action_bar)
        self.action_bar_revealer.set_transition_type(Gtk.RevealerTransitionType.CROSSFADE)
        self.action_bar_revealer.set_transition_duration(250)
        self.append(self.action_bar_revealer)

        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.status_icon = Gtk.Image(pixel_size=24, margin_start=20)
        status_box.append(self.status_icon)
        
        self.status_label = Gtk.Label(margin_top=20, margin_bottom=20, margin_end=20)
        self.status_label.add_css_class("large-text")
        status_box.append(self.status_label)
        self.action_bar.pack_start(status_box)

        self.btn_add = Gtk.Button(label="Add", margin_end=10, margin_bottom=10, margin_top=10)
        self.btn_add.set_visible(False)
        self.btn_add.connect("clicked", self.on_add_clicked)
        self.action_bar.pack_start(self.btn_add)

        self.btn_remove = Gtk.Button(label="Remove", margin_end=10, margin_bottom=10, margin_top=10)
        self.btn_remove.set_visible(False)
        self.btn_remove.connect("clicked", self.on_remove_clicked)
        self.action_bar.pack_start(self.btn_remove)

        self.btn_format = Gtk.Button(label="Format", margin_end=10, margin_bottom=10, margin_top=10)
        self.btn_format.set_visible(False)
        self.btn_format.connect("clicked", self.on_format_clicked)
        self.action_bar.pack_start(self.btn_format)

        self.btn_auto = Gtk.Button(label="Auto", margin_end=10, margin_bottom=10, margin_top=10)
        self.btn_auto.set_visible(False)
        self.btn_auto.connect("clicked", self.on_auto_clicked)
        self.action_bar.pack_start(self.btn_auto)

        self.btn_filesystem = Gtk.Button(label="Filesystem", margin_end=10, margin_bottom=10, margin_top=10)
        self.btn_filesystem.set_visible(False)
        self.btn_filesystem.connect("clicked", self.on_filesystem_clicked)
        self.action_bar.pack_start(self.btn_filesystem)

        self.btn_mountpoint = Gtk.Button(label="Mountpoint", margin_end=10, margin_bottom=10, margin_top=10)
        self.btn_mountpoint.set_visible(False)
        self.btn_mountpoint.connect("clicked", self.on_mountpoint_clicked)
        self.action_bar.pack_start(self.btn_mountpoint)

        self.btn_bootable = Gtk.Button(label="Boot flag", margin_end=10, margin_bottom=10, margin_top=10)
        self.btn_bootable.set_visible(False)
        self.btn_bootable.connect("clicked", self.on_bootflag_clicked)
        self.action_bar.pack_start(self.btn_bootable)
        
        self.btn_proceed = Gtk.Button(label="Continue", margin_end=10, margin_bottom=10, margin_top=10)
        self.btn_proceed.add_css_class("suggested-action")
        self.btn_proceed.add_css_class("buttons_all")
        self.btn_proceed.connect("clicked", self.on_next_clicked)
        self.action_bar.pack_end(self.btn_proceed)



        self.on_refresh_clicked(None)



    def _update_status_bar(self, device_path, icon_name):
        self.selected_disk = device_path
        print(f"Selected device: {self.selected_disk}")
        self.status_icon.set_from_icon_name(icon_name)
        self.status_label.set_text(f"Selected: {self.selected_disk}")
        self.action_bar_revealer.set_reveal_child(True)

    def on_next_clicked(self, button):
        """Handle the Continue button click with validation"""
        print(f"'Continue' button clicked for device: {self.selected_disk}")
        
        # Load configuration to check for boot partition and root mountpoint
        self._load_partition_config()
        
        has_boot_partition = False
        has_root_mountpoint = False
        
        if hasattr(self, 'partition_config'):
            for device, config in self.partition_config.items():
                if config.get('bootable', False):
                    has_boot_partition = True
                if config.get('mountpoint') == '/':
                    has_root_mountpoint = True
        
        if not has_boot_partition or not has_root_mountpoint:
            if self.selected_disk:
                missing_items = []
                if not has_boot_partition:
                    missing_items.append("• No bootable partition found")
                if not has_root_mountpoint:
                    missing_items.append("• No root (/) mountpoint configured")
                
                dialog = Adw.MessageDialog(
                    heading="Missing Required Configuration",
                    body=f"The following requirements are missing:\n\n"
                        f"{chr(10).join(missing_items)}\n\n"
                        f"Would you like to automatically configure the selected device?\n\n"
                        f"Auto-configure will:\n"
                        f"• Remove the selected partition/disk\n"
                        f"• Create a 1GB FAT32 boot partition at /boot\n"
                        f"• Create an ext4 root partition at / with remaining space\n\n"
                        f"WARNING: All data on the selected device will be lost!",
                    transient_for=self.get_root()
                )
                dialog.add_response("back", "Go Back")
                dialog.add_response("continue", "Continue Anyway")
                dialog.add_response("auto", "Auto-Configure")
                dialog.set_response_appearance("auto", Adw.ResponseAppearance.SUGGESTED)
                dialog.set_response_appearance("continue", Adw.ResponseAppearance.DESTRUCTIVE)
                dialog.connect("response", self._on_auto_configure_response)
                dialog.present()
            else:
                self._show_error_dialog("Configuration Required", 
                                    "Please select a disk and configure:\n"
                                    "• At least one bootable partition\n"
                                    "• A root (/) mountpoint")
        else:
            print("Configuration valid, proceeding...")
            self._continue_with_installation()

    def _on_auto_configure_response(self, dialog, response_id):
        """Handle auto-configuration dialog response"""
        if response_id == "auto":
            self._auto_configure_disk()
        elif response_id == "continue":
            print("User chose to continue anyway without proper configuration")
            self._continue_with_installation()
        # If "back" or dialog closed, do nothing

    def _continue_with_installation(self):
        """Continue with the installation process"""
        self.emit("continue-to-next-page")
        print("Continuing with installation...")
        pass


    def _auto_configure_disk(self):
        """Automatically configure disk with boot and root partitions based on boot mode"""
        try:
            if not self.selected_disk:
                self._show_error_dialog("Error", "No device selected")
                return
            
            # Detect boot mode (UEFI or Legacy)
            boot_mode = self._detect_boot_mode()
            print(f"Detected boot mode: {boot_mode}")
            
            if boot_mode == "uefi":
                progress_dialog = self._show_progress_dialog("Auto-Configuring", 
                                                            "Setting up UEFI boot and root partitions...")
            else:
                progress_dialog = self._show_progress_dialog("Auto-Configuring", 
                                                            "Setting up Legacy boot and root partitions...")
            
            # FIX: Clean up the disk path if it contains "Free space on"
            if "Free space on" in self.selected_disk:
                self.selected_disk = self.selected_disk.split("Free space on ")[-1].strip()
            
            disk_info = DiskUtils.parse_disk_path(self.selected_disk)
            base_disk = disk_info['base_disk'] if disk_info else self.selected_disk
            
            # If a whole disk is selected (type 0), use the format whole disk approach
            if hasattr(self, 'type') and (self.type == 0 or (self.type == 2 and "Free space on" in self.selected_disk)):
                # If whole disk or if we're selecting free space but want to format whole disk
                progress_dialog.destroy()
                if boot_mode == "uefi":
                    progress_dialog = self._show_progress_dialog("Formatting Disk", "Wiping disk and creating UEFI partitions...")
                else:
                    progress_dialog = self._show_progress_dialog("Formatting Disk", "Wiping disk and creating Legacy partitions...")
                self._wipe_disk_sync(progress_dialog, boot_mode)
                return
            
            # For partitions (type 1), get partition info and remove it first
            if self.selected_disk != base_disk and hasattr(self, 'type') and self.type == 1:
                # Get the position of the partition we're removing
                cmd = ['sudo', 'parted', base_disk, 'unit', 'B', 'print']
                process = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                
                partition_num = ''.join(filter(str.isdigit, self.selected_disk.split('/')[-1]))
                freed_start = None
                freed_end = None
                
                if process.returncode == 0:
                    for line in process.stdout.split('\n'):
                        if line.strip().startswith(partition_num + ' '):
                            parts = line.strip().split()
                            if len(parts) >= 3:
                                try:
                                    freed_start = int(parts[1].replace('B', ''))
                                    freed_end = int(parts[2].replace('B', ''))
                                except:
                                    pass
                                break
                
                # Remove the partition
                if partition_num:
                    cmd = ['sudo', 'parted', '-s', base_disk, 'rm', partition_num]
                    subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                    
                    cmd = ['sudo', 'partprobe', base_disk]
                    subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                    
                    import time
                    time.sleep(2)
                    
                    # Set up to use the freed space
                    if freed_start and freed_end:
                        self.selected_free_space = {
                            'start': freed_start,
                            'end': freed_end,
                            'size': freed_end - freed_start
                        }
                        self.type = 2  # Treat as free space now
            
            # Check if we need to create a partition table
            cmd = ['sudo', 'parted', base_disk, 'print']
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if "unrecognised disk label" in process.stderr.lower() or "unrecognized disk label" in process.stderr.lower():
                if boot_mode == "uefi":
                    cmd = ['sudo', 'parted', '-s', base_disk, 'mklabel', 'gpt']
                else:
                    cmd = ['sudo', 'parted', '-s', base_disk, 'mklabel', 'msdos']
                process = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if process.returncode != 0:
                    partition_table_type = "GPT" if boot_mode == "uefi" else "MBR"
                    raise Exception(f"Failed to create {partition_table_type} table: {process.stderr}")
                import time
                time.sleep(1)
            
            # Calculate partition positions based on boot mode
            if hasattr(self, 'type') and self.type == 2 and hasattr(self, 'selected_free_space'):
                # Use the freed space boundaries
                free_start_bytes = self.selected_free_space['start']
                free_end_bytes = self.selected_free_space['end']
                
                # Convert to MiB and align to MiB boundaries (1048576 bytes = 1 MiB)
                free_start_mib = ((free_start_bytes + 1048575) // 1048576)  # Round up to next MiB
                free_end_mib = (free_end_bytes // 1048576)  # Round down to MiB boundary
                
                if boot_mode == "uefi":
                    # UEFI: 1024 MiB boot partition (1 GiB)
                    boot_size_mib = 1024
                    boot_end_mib = free_start_mib + boot_size_mib
                    
                    # Ensure we have enough space (need at least 100 MiB for root)
                    if (free_end_mib - free_start_mib) < boot_size_mib + 15360:
                        available_mib = free_end_mib - free_start_mib
                        raise Exception(f"Not enough free space. Available: {available_mib}MiB, Need: {boot_size_mib + 15360}MiB")
                    
                    # Use MiB positions for perfect alignment
                    boot_start = f"{free_start_mib}MiB"
                    boot_end_pos = f"{boot_end_mib}MiB"
                    root_start = f"{boot_end_mib}MiB"
                    root_end = f"{free_end_mib}MiB"
                    
                    partition_type_boot = "fat32"
                    partition_type_root = "ext4"
                else:
                    # Legacy: No separate boot partition needed, just root
                    # Ensure we have enough space (need at least 1000 MiB for root)
                    if (free_end_mib - free_start_mib) < 15360:
                        available_mib = free_end_mib - free_start_mib
                        raise Exception(f"Not enough free space. Available: {available_mib}MiB, Need: 15360MiB")
                    
                    # Single root partition taking all space
                    root_start = f"{free_start_mib}MiB"
                    root_end = f"{free_end_mib}MiB"
                    partition_type_root = "ext4"
                    
                    boot_start = None  # No separate boot partition
                    boot_end_pos = None
                    partition_type_boot = None
                    
            else:
                # Find the largest free space using byte units and convert to MiB with integer math
                cmd = ['sudo', 'parted', base_disk, 'unit', 'B', 'print', 'free']
                process = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                
                if process.returncode != 0:
                    raise Exception(f"Failed to get disk info: {process.stderr}")
                
                lines = process.stdout.split('\n')
                free_start_bytes = None
                free_end_bytes = None
                max_size = 0
                
                for line in lines:
                    if 'Free Space' in line:
                        parts = line.strip().split()
                        if len(parts) >= 3:
                            try:
                                start = int(parts[0].replace('B', ''))
                                end = int(parts[1].replace('B', ''))
                                size = end - start
                                if size > max_size:
                                    free_start_bytes = start
                                    free_end_bytes = end
                                    max_size = size
                            except (ValueError, IndexError):
                                continue
                
                if free_start_bytes is None:
                    raise Exception("No free space found")
                
                # Convert to MiB using integer division (1 MiB = 1048576 bytes)
                mib_size = 1048576
                free_start_mib = (free_start_bytes + mib_size - 1) // mib_size  # Round up
                free_end_mib = free_end_bytes // mib_size  # Round down
                
                if boot_mode == "uefi":
                    # UEFI: 1024 MiB boot partition
                    boot_size_mib = 1024
                    boot_end_mib = free_start_mib + boot_size_mib
                    
                    if (free_end_mib - free_start_mib) < boot_size_mib + 15360:
                        available_mib = free_end_mib - free_start_mib
                        raise Exception(f"Not enough free space. Available: {available_mib}MiB, Need: {boot_size_mib + 15360}MiB")
                    
                    boot_start = f"{free_start_mib}MiB"
                    boot_end_pos = f"{boot_end_mib}MiB"
                    root_start = f"{boot_end_mib}MiB"
                    root_end = f"{free_end_mib}MiB"
                    
                    partition_type_boot = "fat32"
                    partition_type_root = "ext4"
                else:
                    # Legacy: Just root partition
                    if (free_end_mib - free_start_mib) < 15360:
                        available_mib = free_end_mib - free_start_mib
                        raise Exception(f"Not enough free space. Available: {available_mib}MiB, Need: 15360MiB")
                    
                    root_start = f"{free_start_mib}MiB"
                    root_end = f"{free_end_mib}MiB"
                    partition_type_root = "ext4"
                    
                    boot_start = None
                    boot_end_pos = None
                    partition_type_boot = None
            
            # Create partitions based on boot mode
            if boot_mode == "uefi":
                print(f"Creating UEFI partitions: boot {boot_start}-{boot_end_pos}, root {root_start}-{root_end}")
                
                # Create boot partition using byte positioning
                cmd = ['sudo', 'parted', '-s', base_disk, 'mkpart', 'primary', partition_type_boot, 
                    boot_start, boot_end_pos]
                process = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if process.returncode != 0:
                    # Try without filesystem type
                    cmd = ['sudo', 'parted', '-s', base_disk, 'mkpart', 'primary', 
                        boot_start, boot_end_pos]
                    process = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                    if process.returncode != 0:
                        raise Exception(f"Failed to create boot partition: {process.stderr}")
                
                # Create root partition
                cmd = ['sudo', 'parted', '-s', base_disk, 'mkpart', 'primary', partition_type_root,
                    root_start, root_end]
                process = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if process.returncode != 0:
                    # Try without filesystem type
                    cmd = ['sudo', 'parted', '-s', base_disk, 'mkpart', 'primary',
                        root_start, root_end]
                    process = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                    if process.returncode != 0:
                        raise Exception(f"Failed to create root partition: {process.stderr}")
            else:
                print(f"Creating Legacy partition: root {root_start}-{root_end}")
                
                # Create single root partition for Legacy boot
                cmd = ['sudo', 'parted', '-s', base_disk, 'mkpart', 'primary', partition_type_root,
                    root_start, root_end]
                process = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if process.returncode != 0:
                    # Try without filesystem type
                    cmd = ['sudo', 'parted', '-s', base_disk, 'mkpart', 'primary',
                        root_start, root_end]
                    process = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                    if process.returncode != 0:
                        raise Exception(f"Failed to create root partition: {process.stderr}")
            
            # Force kernel to re-read partition table
            cmd = ['sudo', 'partprobe', base_disk]
            subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            import time
            time.sleep(2)
            
            # Find the newly created partitions
            cmd = ['sudo', 'parted', base_disk, 'print']
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            partition_nums = []
            for line in process.stdout.split('\n'):
                line = line.strip()
                if line and line[0].isdigit():
                    parts = line.split()
                    if len(parts) >= 1:
                        try:
                            partition_nums.append(int(parts[0]))
                        except ValueError:
                            continue
            
            partition_nums.sort()
            
            if boot_mode == "uefi":
                # Find the two newest partitions for UEFI
                if len(partition_nums) >= 2:
                    if len(partition_nums) >= 2:
                        boot_partition = DiskUtils.get_partition_path(base_disk, partition_nums[-2])
                        root_partition = DiskUtils.get_partition_path(base_disk, partition_nums[-1])
                    else:
                        boot_partition = DiskUtils.get_partition_path(base_disk, 1)
                        root_partition = DiskUtils.get_partition_path(base_disk, 2)
                
                # Set boot flag for UEFI ESP
                boot_num = ''.join(filter(str.isdigit, boot_partition.split('/')[-1]))
                cmd = ['sudo', 'parted', '-s', base_disk, 'set', boot_num, 'esp', 'on']
                subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                
                time.sleep(2)
                
                # Format partitions
                cmd = ['sudo', 'mkfs.fat', '-F', '32', boot_partition]
                process = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if process.returncode != 0:
                    raise Exception(f"Failed to format boot partition: {process.stderr}")
                
                cmd = ['sudo', 'mkfs.ext4', '-F', root_partition]
                process = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if process.returncode != 0:
                    raise Exception(f"Failed to format root partition: {process.stderr}")
                
                # Update configuration
                if not hasattr(self, 'partition_config'):
                    self.partition_config = {}
                
                self.partition_config[boot_partition] = {
                    'mountpoint': '/boot',
                    'bootable': True
                }
                
                self.partition_config[root_partition] = {
                    'mountpoint': '/',
                    'bootable': False
                }
                
                success_message = (f"UEFI disk configured successfully!\n\n"
                                f"Created partitions:\n"
                                f"• {boot_partition}: 1 GiB FAT32 at /boot (ESP)\n"
                                f"• {root_partition}: ext4 at /\n\n"
                                f"fstab has been updated.")
            else:
                # Find the newest partition for Legacy
                if len(partition_nums) >= 1:
                    root_partition = DiskUtils.get_partition_path(base_disk, partition_nums[-1])
                else:
                    root_partition = DiskUtils.get_partition_path(base_disk, 1)
                
                # Set boot flag for Legacy boot
                root_num = ''.join(filter(str.isdigit, root_partition.split('/')[-1]))
                cmd = ['sudo', 'parted', '-s', base_disk, 'set', root_num, 'boot', 'on']
                subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                
                time.sleep(2)
                
                # Format root partition
                cmd = ['sudo', 'mkfs.ext4', '-F', root_partition]
                process = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if process.returncode != 0:
                    raise Exception(f"Failed to format root partition: {process.stderr}")
                
                # Update configuration
                if not hasattr(self, 'partition_config'):
                    self.partition_config = {}
                
                self.partition_config[root_partition] = {
                    'mountpoint': '/',
                    'bootable': True
                }
                
                success_message = (f"Legacy disk configured successfully!\n\n"
                                f"Created partitions:\n"
                                f"• {root_partition}: ext4 at / (bootable)\n\n"
                                f"fstab has been updated.\n\n"
                                f"Note: GRUB will be installed to the MBR of {base_disk}")
            
            self._save_partition_config()
            self._generate_and_apply_fstab()
            
            progress_dialog.destroy()
            self._show_info_dialog("Success", success_message)
            self.on_refresh_clicked(None)
            
            GLib.idle_add(self._continue_with_installation)

        except Exception as e:
            progress_dialog.destroy()
            self._show_error_dialog("Error", f"Failed to auto-configure: {str(e)}")

    def _detect_boot_mode(self):
        """Detect if the system is running in UEFI or Legacy mode"""
        try:
            # Check if /sys/firmware/efi exists
            if os.path.exists('/sys/firmware/efi'):
                return "uefi"
            else:
                return "legacy"
        except Exception:
            # Fallback: assume legacy if detection fails
            return "legacy"

    def on_refresh_clicked(self, button):
        print("Refreshing disk list...")
        self.selected_disk = None
        self.action_bar_revealer.set_reveal_child(False)
        self.populate_disk_list()

    # --- MODIFIED: Re-added the logic to wait for gnome-disks to close ---
    def on_open_disks_clicked(self, button):
        """Launches Gparted, hides the UI, and waits for it to close."""
        print("Attempting to launch Gparted and waiting for it to close...")
        
        # 1. Hide the current UI and show a waiting message
        self.action_bar_revealer.set_reveal_child(False)
        waiting_group = Adw.PreferencesGroup(
            title="Waiting for Gparted",
            description="The disk list will be refreshed after you close the Gparted application."
        )
        self.clamp.set_child(waiting_group)
        self.group = waiting_group

        try:
            # 2. Launch gnome-disks asynchronously
            process = Gio.Subprocess.new(['gparted'], Gio.SubprocessFlags.NONE)
            # 3. Set a callback for when the process finishes
            process.wait_check_async(None, self.on_gnome_disks_closed)

        except GLib.Error as e:
            print(f"Error launching 'gparted': {e.message}")
            dialog = Adw.MessageDialog(
                heading="Error: Gparted Not Found",
                body=f"Could not launch Gparted: {e.message}.",
                transient_for=self.get_root(),
            )
            dialog.add_response("ok", "OK")
            # If launching fails, refresh the view back to the original list
            dialog.connect("response", lambda d, r: self.on_refresh_clicked(None))
            dialog.present()

    # --- NEW: Callback function that runs after gnome-disks closes ---
    def on_gnome_disks_closed(self, process, result):
        """Callback executed after the 'gnome-disks' process terminates."""
        try:
            process.wait_check_finish(result)
            print("Gparted closed. Refreshing list.")
        except GLib.Error as e:
            print(f"Gparted process finished with an error: {e.message}")
        finally:
            # Safely schedule the UI update on the main thread
            GLib.idle_add(self.on_refresh_clicked, None)

    def on_disk_selected(self, row, disk_name):
        self.type=0
        print(self.type)
        self._update_status_bar(f"/dev/{disk_name}", "drive-harddisk-symbolic")
        # Show buttons relevant for a whole disk
        self.btn_add.set_visible(True)
        self.btn_auto.set_visible(True)  
        self.btn_format.set_visible(False)  
        # Hide buttons relevant for a partition
        self.btn_remove.set_visible(False)
        self.btn_bootable.set_visible(False)
        self.btn_filesystem.set_visible(False)
        self.btn_mountpoint.set_visible(False)

    def on_partition_selected(self, row, device_name):
        self.type=1
        print(type)
        self._update_status_bar(f"/dev/{device_name}", "drive-removable-media-symbolic")
        # Hide button relevant for a whole disk
        self.btn_add.set_visible(False)
        # Show buttons relevant for a partition
        self.btn_remove.set_visible(True)
        self.btn_format.set_visible(True)
        self.btn_auto.set_visible(False)
        self.btn_bootable.set_visible(True)
        self.btn_filesystem.set_visible(True)
        self.btn_mountpoint.set_visible(True)

    def populate_disk_list(self):
        loading_group = Adw.PreferencesGroup(
            title="Loading...",
            description="Scanning for storage devices."
        )
        self.clamp.set_child(loading_group)
        self.group = loading_group
        try:
            command = ['lsblk', '--json', '-b', '-o', 'NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE']
            process = Gio.Subprocess.new(command, Gio.SubprocessFlags.STDOUT_PIPE)
            process.communicate_utf8_async(None, None, self._on_lsblk_finish)
        except GLib.Error as e:
            self._render_disk_list_error(f"Failed to execute 'lsblk'. Is it installed?")

    def _on_lsblk_finish(self, process, result):
        try:
            ok, stdout, stderr = process.communicate_utf8_finish(result)
            if not ok: raise GLib.Error(f"lsblk process failed: {stderr}")
            data = json.loads(stdout)
            disks = {}
            
            for device in data.get('blockdevices', []):
                if device.get('type') == 'disk':
                    disk_name = device['name']
                    disks[disk_name] = {
                        'name': disk_name,
                        'size': int(device['size']),
                        'type': device['type'],
                        'partitions': []
                    }
                    
                    for p in device.get('children', []):
                        disks[disk_name]['partitions'].append({
                            'name': p['name'],
                            'size': int(p['size']),
                            'type': p['type'],
                            'mountpoint': p.get('mountpoint'),
                            'fstype': p.get('fstype')
                        })
            
            # Get free space information for each disk
            for disk_name in disks.keys():
                self._get_disk_free_space(f"/dev/{disk_name}", disks[disk_name])
            
            GLib.idle_add(self._render_disk_list, disks)
        except Exception as e:
            GLib.idle_add(self._render_disk_list_error, f"Error parsing disk data: {e}")
    
    def _get_disk_free_space(self, disk_path, disk_info):
        """Get free space information for a disk using parted"""
        try:
            # Get both partition and free space info in one command
            cmd = ['sudo', 'parted', disk_path, 'unit', 'B', 'print', 'free']
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            
            if process.returncode != 0:
                disk_info['free_spaces'] = []
                disk_info['partition_positions'] = {}
                return
            
            lines = process.stdout.split('\n')
            free_spaces = []
            partition_positions = {}
            
            for line in lines:
                line = line.strip()
                # Parse free space lines
                if 'Free Space' in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        try:
                            # Free space lines format: "start end size Free Space"
                            start = int(parts[0].replace('B', ''))
                            end = int(parts[1].replace('B', ''))
                            size = int(parts[2].replace('B', ''))
                            free_spaces.append({
                                'start': start,
                                'end': end,
                                'size': size
                            })
                        except (ValueError, IndexError):
                            continue
                # Parse partition lines (they start with a number)
                elif line and line[0].isdigit():
                    parts = line.split()
                    if len(parts) >= 3:
                        try:
                            part_num = parts[0]
                            start = int(parts[1].replace('B', ''))
                            end = int(parts[2].replace('B', ''))
                            # Store partition position by number
                            partition_positions[part_num] = {
                                'start': start,
                                'end': end
                            }
                        except (ValueError, IndexError):
                            continue
            
            disk_info['free_spaces'] = free_spaces
            disk_info['partition_positions'] = partition_positions
            
        except Exception as e:
            print(f"Error getting free space for {disk_path}: {e}")
            disk_info['free_spaces'] = []
            disk_info['partition_positions'] = {}

    def on_free_space_clicked(self, gesture, n_press, x, y, disk_name, free_space_data):
        """Handle clicks on free space rows"""
        if n_press == 1:
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            # FIX: Use the actual disk device, not "Free space on..."
            self.selected_disk = f"/dev/{disk_name}"  # This is the disk device
            self.selected_free_space = free_space_data
            self.type = 2  # Type 2 indicates free space
            
            self._update_status_bar(f"Free space on /dev/{disk_name}", "list-add-symbolic")
            
            # Show Add and Auto buttons for free space
            self.btn_add.set_visible(True)
            self.btn_auto.set_visible(True) 
            self.btn_format.set_visible(False)
            self.btn_remove.set_visible(False)
            self.btn_bootable.set_visible(False)
            self.btn_filesystem.set_visible(False)
            self.btn_mountpoint.set_visible(False)

    def _render_disk_list(self, disks):
        new_group = Adw.PreferencesGroup(
            title="Select Installation Destination",
            description="Click on a disk or partition to select it or modify it."
        )
        
        # Load the current partition configuration for mountpoint display
        self._load_partition_config()
        
        if not disks:
            new_group.add(Adw.ActionRow(title="No Disks Found"))
        else:
            for name, disk in disks.items():
                exp_row = Adw.ExpanderRow(
                    title=f"/dev/{name}",
                    subtitle=f"Size: {self._format_size_human(disk['size'])} | Type: {disk['type']}"
                )
                exp_row.add_css_class("disk-row")
                exp_row.add_prefix(Gtk.Image.new_from_icon_name("drive-harddisk-symbolic"))
                
                click_controller = Gtk.GestureClick()
                click_controller.connect("pressed", self.on_disk_row_clicked, name)
                exp_row.add_controller(click_controller)
                
                new_group.add(exp_row)
                
                # Create a list of all items with their actual disk positions
                items = []
                
                # Get partition positions from the disk info (already parsed)
                partition_positions = disk.get('partition_positions', {})
                
                # Add partitions with their actual start positions
                for part in disk['partitions']:
                    device_path = f"/dev/{part['name']}"
                    
                    # Extract partition number from name (e.g., "vda1" -> "1")
                    part_num = part['name'].replace(name, '')
                    
                    # Get the actual start position from partition_positions
                    start_pos = 0
                    if part_num in partition_positions:
                        start_pos = partition_positions[part_num]['start']
                    
                    # Get configured mountpoint from our config
                    configured_mountpoint = "Not configured"
                    if hasattr(self, 'partition_config') and device_path in self.partition_config:
                        configured_mountpoint = self.partition_config[device_path].get('mountpoint', 'Not configured')
                    
                    # Check if partition is marked as bootable
                    is_bootable = False
                    if hasattr(self, 'partition_config') and device_path in self.partition_config:
                        is_bootable = self.partition_config[device_path].get('bootable', False)
                    
                    # Build subtitle
                    subtitle_parts = [f"Size: {self._format_size_human(part['size'])}"]
                    subtitle_parts.append(f"Mount: {configured_mountpoint}")
                    if is_bootable:
                        subtitle_parts.append("Bootable")
                    
                    items.append({
                        'type': 'partition',
                        'start': start_pos,
                        'data': part,
                        'subtitle': ' | '.join(subtitle_parts),
                        'is_bootable': is_bootable
                    })
                
                # Add free spaces with their positions
                if 'free_spaces' in disk:
                    for free_space in disk['free_spaces']:
                        if free_space['size'] > 1024 * 1024:  # Only show free space > 1MB
                            items.append({
                                'type': 'free_space',
                                'start': free_space['start'],
                                'data': free_space,
                                'subtitle': f"Size: {self._format_size_human(free_space['size'])} | Unallocated"
                            })
                
                # Sort items by their start position
                items.sort(key=lambda x: x.get('start', 0))
                
                # Debug print to see the sorting
                print(f"Disk {name} items sorted by position:")
                for item in items:
                    if item['type'] == 'partition':
                        print(f"  Partition {item['data']['name']} at position {item['start']}")
                    else:
                        print(f"  Free Space at position {item['start']}, size {item['data']['size']}")
                
                # Add sorted items to the expander row
                for item in items:
                    if item['type'] == 'partition':
                        part = item['data']
                        row = Adw.ActionRow(
                            title=f"/dev/{part['name']}",
                            subtitle=item['subtitle']
                        )
                        row.add_css_class("partition-row")
                        
                        if item['is_bootable']:
                            row.add_prefix(Gtk.Image.new_from_icon_name("emblem-system-symbolic"))
                        else:
                            row.add_prefix(Gtk.Image.new_from_icon_name("drive-removable-media-symbolic"))
                        
                        row.set_activatable(False)
                        partition_click = Gtk.GestureClick()
                        partition_click.connect("pressed", self.on_partition_row_clicked, part['name'])
                        row.add_controller(partition_click)
                        
                        exp_row.add_row(row)
                        
                    elif item['type'] == 'free_space':
                        free = item['data']
                        row = Adw.ActionRow(
                            title="Free Space",
                            subtitle=item['subtitle']
                        )
                        row.add_css_class("free-space-row")
                        row.add_prefix(Gtk.Image.new_from_icon_name("list-add-symbolic"))
                        
                        row.set_activatable(False)
                        free_click = Gtk.GestureClick()
                        free_click.connect("pressed", self.on_free_space_clicked, name, free)
                        row.add_controller(free_click)
                        
                        exp_row.add_row(row)
        
        self.clamp.set_child(new_group)
        self.group = new_group

    def on_disk_row_clicked(self, gesture, n_press, x, y, disk_name):
        """Handle clicks on disk expander rows"""
        # Only handle single clicks
        if n_press == 1:
            self.on_disk_selected(None, disk_name)

    def on_partition_row_clicked(self, gesture, n_press, x, y, partition_name):
        """Handle clicks on partition rows"""
        # Only handle single clicks and stop event propagation
        if n_press == 1:
            # Stop the event from bubbling up to the parent disk row
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            self.on_partition_selected(None, partition_name)

    def _format_size_human(self, size_bytes):
        if size_bytes < 1000: return f"{size_bytes} B"
        for unit in ['KB', 'MB', 'GB', 'TB']:
            size_bytes /= 1000
            if size_bytes < 1000: return f"{size_bytes:.2f} {unit}"
        return f"{size_bytes:.2f} TB"

















    def on_add_clicked(self, button):
        """Add partition to selected disk"""
        if not self.selected_disk:
            self._show_error_dialog("No Selection", "Please select a disk first.")
            return
        
        # Check if a disk is selected - add button is only visible for disks
        if not self.btn_add.get_visible():
            self._show_error_dialog("Invalid Selection", "Cannot add partition to a partition. Please select a disk.")
            return
        
        print(f"Adding partition to disk: {self.selected_disk}")
        
        # Show partition creation dialog directly
        self._show_partition_size_dialog()

    # Initialize partition configuration when widget is created
    def init_partition_config(self):
        """Initialize partition configuration - call this in widget __init__"""
        self._load_partition_config()
        # Btrfs subvolume layout. Kept intentionally minimal so that every
        # subvolume listed here is actually created and then mounted: the fstab
        # generator emits exactly one entry per item, so any subvolume that is
        # listed but not created would make the installed system drop to
        # emergency mode when systemd fails to mount it at boot.
        self.btrfs_subvolumes = {
            '@': '/',
            '@home': '/home',
        }

    def on_remove_clicked(self, button):
        """Remove selected partition"""
        if not self.selected_disk:
            self._show_error_dialog("No Selection", "Please select a partition first.")
            return
        
        # Check if a partition is selected - remove button is only visible for partitions
        if not self.btn_remove.get_visible():
            self._show_error_dialog("Invalid Selection", "Can only remove partitions. Please select a partition.")
            return
        
        print(f"Removing partition: {self.selected_disk}")
        
        # Show confirmation dialog
        dialog = Adw.MessageDialog(
            heading="Remove Partition",
            body=f"Are you sure you want to remove partition {self.selected_disk}?\n\nThis action cannot be undone and all data will be lost!",
            transient_for=self.get_root()
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("remove", "Remove")
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self._on_remove_partition_response)
        dialog.present()

    def _on_remove_partition_response(self, dialog, response_id):
        """Handle remove partition dialog response"""
        if response_id == "remove":
            self._execute_remove_partition()

    def on_format_clicked(self, button):
        """Format selected partition"""
        if not self.selected_disk:
            self._show_error_dialog("No Selection", "Please select a partition first.")
            return
        
        # Only handle partitions now, not whole disks
        if hasattr(self, 'type') and self.type == 1:
            # For partitions, show filesystem selection
            selection_type = "partition"
            
            print(f"Formatting {selection_type}: {self.selected_disk}")
            
            # Show filesystem selection dialog
            dialog = Adw.MessageDialog(
                heading=f"Format {selection_type.title()}",
                body=f"Select filesystem type for {self.selected_disk}:\n\nWarning: All data will be lost!",
                transient_for=self.get_root()
            )
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("ext4", "ext4")
            dialog.add_response("btrfs", "Btrfs")
            dialog.add_response("ntfs", "NTFS")
            dialog.add_response("fat32", "FAT32")
            dialog.add_response("exfat", "exFAT")
            dialog.add_response("swap", "swap")
            dialog.set_response_appearance("ext4", Adw.ResponseAppearance.SUGGESTED)
            dialog.connect("response", self._on_format_response)
            dialog.present()
        else:
            self._show_error_dialog("Invalid Selection", "Format is only available for partitions. Use Auto for whole disks or free space.")

    def _on_format_response(self, dialog, response_id):
        """Handle format dialog response"""
        if response_id in ["ext4", "btrfs", "ntfs", "fat32", "exfat", "swap"]:
            filesystem = response_id
            # Formatting partition
            self._execute_format(filesystem)

    def on_auto_clicked(self, button):
        """Handle Auto button click - automatically configure disk or free space"""
        if not self.selected_disk:
            self._show_error_dialog("No Selection", "Please select a disk or free space first.")
            return
        
        # Check if it's a whole disk (type 0) or free space (type 2)
        if hasattr(self, 'type'):
            if self.type == 0:
                # Whole disk selected - format entire disk
                self._execute_format_whole_disk()
            elif self.type == 2:
                # Free space selected - auto configure in that space
                self._auto_configure_disk()
            else:
                self._show_error_dialog("Invalid Selection", "Auto configuration is only available for whole disks or free space.")
        else:
            self._show_error_dialog("Invalid Selection", "Please select a disk or free space first.")

    def on_filesystem_clicked(self, button):
        """Change filesystem of selected partition"""
        if not self.selected_disk:
            self._show_error_dialog("No Selection", "Please select a partition first.")
            return
        
        # Check if a partition is selected - partitions are visible when these buttons are shown
        # If the filesystem button is visible, it means a partition is selected
        if not self.btn_filesystem.get_visible():
            self._show_error_dialog("Invalid Selection", "Can only change filesystem of partitions. Please select a partition.")
            return
        
        print(f"Changing filesystem for partition: {self.selected_disk}")
        
        # Show filesystem change dialog
        dialog = Adw.MessageDialog(
            heading="Change Filesystem",
            body=f"Change filesystem type for {self.selected_disk}:\n\nWarning: This will reformat the partition and all data will be lost!",
            transient_for=self.get_root()
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("ext4", "ext4")
        dialog.add_response("btrfs", "Btrfs")
        dialog.add_response("ntfs", "NTFS")
        dialog.add_response("fat32", "FAT32")
        dialog.add_response("exfat", "exFAT")
        dialog.add_response("swap", "swap")
        dialog.set_response_appearance("ext4", Adw.ResponseAppearance.SUGGESTED)
        dialog.connect("response", self._on_filesystem_response)
        dialog.present()

    def _on_filesystem_response(self, dialog, response_id):
        """Handle filesystem change dialog response"""
        if response_id in ["ext4", "btrfs", "ntfs", "fat32", "exfat", "swap"]:
            filesystem = response_id
            self._execute_format(filesystem)

    def on_mountpoint_clicked(self, button):
        """Change mountpoint of selected partition"""
        if not self.selected_disk:
            self._show_error_dialog("No Selection", "Please select a partition first.")
            return
        
        # Check if a partition is selected - mountpoint button is only visible for partitions
        if not self.btn_mountpoint.get_visible():
            self._show_error_dialog("Invalid Selection", "Can only set mountpoint for partitions. Please select a partition.")
            return
        
        print(f"Setting mountpoint for partition: {self.selected_disk}")
        
        # Create mountpoint input dialog
        self._show_mountpoint_input_dialog()

    def _show_mountpoint_input_dialog(self):
        """Show dialog to input custom mountpoint"""
        dialog = Gtk.Dialog(
            title="Set Mountpoint",
            transient_for=self.get_root(),
            modal=True
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Set", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        
        content_area = dialog.get_content_area()
        content_area.set_spacing(12)
        content_area.set_margin_top(12)
        content_area.set_margin_bottom(12)
        content_area.set_margin_start(12)
        content_area.set_margin_end(12)
        
        label = Gtk.Label(label=f"Set mountpoint for {self.selected_disk}:")
        content_area.append(label)
        
        # Add common mountpoint buttons
        button_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        
        common_mountpoints = ["/", "/home", "/boot", "/var", "/tmp", "/usr"]
        for mp in common_mountpoints:
            btn = Gtk.Button(label=mp)
            btn.connect("clicked", lambda b, mountpoint=mp: self._set_mountpoint(dialog, mountpoint))
            button_box.append(btn)
        
        content_area.append(button_box)
        
        # Add custom input
        custom_label = Gtk.Label(label="Or enter custom mountpoint:")
        content_area.append(custom_label)
        
        self.mountpoint_entry = Gtk.Entry()
        self.mountpoint_entry.set_placeholder_text("/custom/path")
        content_area.append(self.mountpoint_entry)
        
        dialog.connect("response", self._on_mountpoint_dialog_response)
        from simple_localization_manager import get_localization_manager
        get_localization_manager().translate_gtk_dialog(dialog)
        dialog.present()

    def _set_mountpoint(self, dialog, mountpoint):
        """Set mountpoint from button click"""
        self.mountpoint_entry.set_text(mountpoint)
        dialog.response(Gtk.ResponseType.OK)

    def _on_mountpoint_dialog_response(self, dialog, response_id):
        """Handle mountpoint dialog response"""
        if response_id == Gtk.ResponseType.OK:
            mountpoint = self.mountpoint_entry.get_text().strip()
            if mountpoint:
                if not mountpoint.startswith('/'):
                    self._show_error_dialog("Invalid Mountpoint", "Mountpoint must start with '/'")
                    dialog.destroy()
                    return
                self._execute_set_mountpoint(mountpoint)
        dialog.destroy()

    def on_bootflag_clicked(self, button):
        """Toggle boot flag for selected partition"""
        if not self.selected_disk:
            self._show_error_dialog("No Selection", "Please select a partition first.")
            return
        
        # Check if a partition is selected - boot flag button is only visible for partitions
        if not self.btn_bootable.get_visible():
            self._show_error_dialog("Invalid Selection", "Can only set boot flag on partitions. Please select a partition.")
            return
        
        print(f"Toggling boot flag for partition: {self.selected_disk}")
        
        # Show boot flag dialog
        dialog = Adw.MessageDialog(
            heading="Boot Flag",
            body=f"Toggle boot flag for {self.selected_disk}?\n\nThis will modify the partition to be visible in the boot menu.",
            transient_for=self.get_root()
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("enable", "Enable Boot Flag")
        dialog.add_response("disable", "Disable Boot Flag")
        dialog.set_response_appearance("enable", Adw.ResponseAppearance.SUGGESTED)
        dialog.connect("response", self._on_bootflag_response)
        dialog.present()

    def _on_bootflag_response(self, dialog, response_id):
        """Handle boot flag dialog response"""
        if response_id in ["enable", "disable"]:
            enable_boot = (response_id == "enable")
            self._execute_set_bootflag(enable_boot)

    # Helper functions for dialogs
    def _show_error_dialog(self, heading, message):
        """Show error dialog"""
        dialog = Adw.MessageDialog(
            heading=heading,
            body=message,
            transient_for=self.get_root()
        )
        dialog.add_response("ok", "OK")
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.present()

    def _show_info_dialog(self, heading, message):
        """Show info dialog"""
        dialog = Adw.MessageDialog(
            heading=heading,
            body=message,
            transient_for=self.get_root()
        )
        dialog.add_response("ok", "OK")
        dialog.present()

    def _show_progress_dialog(self, heading, message):
        """Show progress dialog with spinner"""
        dialog = Adw.MessageDialog(
            heading=heading,
            body=message,
            transient_for=self.get_root()
        )
        
        # Add spinner
        spinner = Gtk.Spinner()
        spinner.start()
        spinner.set_size_request(32, 32)
        
        content_area = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        content_area.set_halign(Gtk.Align.CENTER)
        content_area.append(spinner)
        content_area.append(Gtk.Label(label="Please wait..."))
        
        dialog.set_extra_child(content_area)
        dialog.present()
        
        return dialog

    # Implementation functions using parted and other disk utilities

    def _show_partition_size_dialog(self):
        """Show dialog to set partition size and type with dropdown for units"""
        dialog = Gtk.Dialog(
            title="Create Partition",
            transient_for=self.get_root(),
            modal=True
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Create", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        
        content_area = dialog.get_content_area()
        content_area.set_spacing(12)
        content_area.set_margin_top(12)
        content_area.set_margin_bottom(12)
        content_area.set_margin_start(12)
        content_area.set_margin_end(12)
        
        label = Gtk.Label(label=f"Create partition on {self.selected_disk}")
        content_area.append(label)
        
        # Size input with unit selector
        size_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        
        size_label = Gtk.Label(label="Size:")
        content_area.append(size_label)
        
        self.partition_size_entry = Gtk.Entry()
        self.partition_size_entry.set_placeholder_text("10 or leave empty for max")
        self.partition_size_entry.set_hexpand(True)
        size_box.append(self.partition_size_entry)
        
        # Unit selector
        self.partition_unit_combo = Gtk.ComboBoxText()
        self.partition_unit_combo.append("MB", "MB")
        self.partition_unit_combo.append("GB", "GB") 
        self.partition_unit_combo.append("TB", "TB")
        self.partition_unit_combo.set_active(1)  # Default to GB
        size_box.append(self.partition_unit_combo)
        
        content_area.append(size_box)
        
        # Filesystem type
        fs_label = Gtk.Label(label="Filesystem:")
        content_area.append(fs_label)
        
        self.partition_fs_combo = Gtk.ComboBoxText()
        self.partition_fs_combo.append("ext4", "ext4")
        self.partition_fs_combo.append("btrfs", "Btrfs")
        self.partition_fs_combo.append("ntfs", "NTFS")
        self.partition_fs_combo.append("fat32", "FAT32")
        self.partition_fs_combo.append("exfat", "exFAT")
        self.partition_fs_combo.append("swap", "swap")
        self.partition_fs_combo.append("unformatted", "Unformatted")
        self.partition_fs_combo.set_active(0)
        content_area.append(self.partition_fs_combo)
        
        dialog.connect("response", self._on_partition_create_response)
        from simple_localization_manager import get_localization_manager
        get_localization_manager().translate_gtk_dialog(dialog)
        dialog.present()

    def _on_partition_create_response(self, dialog, response_id):
        """Handle partition creation dialog response"""
        if response_id == Gtk.ResponseType.OK:
            size_text = self.partition_size_entry.get_text().strip()
            unit = self.partition_unit_combo.get_active_id()
            filesystem = self.partition_fs_combo.get_active_id()
            
            # If size is empty, use remaining space
            if not size_text:
                size = "100%"
            else:
                try:
                    size_value = float(size_text)
                    if size_value <= 0:
                        self._show_error_dialog("Invalid Size", "Size must be greater than 0")
                        dialog.destroy()
                        return
                    size = f"{size_value}{unit}"
                except ValueError:
                    self._show_error_dialog("Invalid Size", "Please enter a valid number")
                    dialog.destroy()
                    return
                
            self._execute_create_partition(size, filesystem)
        dialog.destroy()

    def _execute_create_partition(self, size, filesystem):
        """Execute partition creation using parted with proper unit handling"""
        try:
            progress_dialog = self._show_progress_dialog("Creating Partition", "Creating partition, please wait...")
            
            # FIX: Clean up the disk path if it contains "Free space on"
            if "Free space on" in self.selected_disk:
                # Extract actual disk path from "Free space on /dev/vda"
                self.selected_disk = self.selected_disk.split("Free space on ")[-1].strip()
            
            # Ensure we're working with the base disk for free space
            if hasattr(self, 'type') and self.type == 2:
                # For free space, ensure we have the base disk
                base_disk = ''.join([c for c in self.selected_disk if not c.isdigit()])
                self.selected_disk = base_disk
            
            # First, check if the disk has a partition table
            cmd = ['sudo', 'parted', self.selected_disk, 'print']
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            # If no partition table exists, create GPT
            if "unrecognised disk label" in process.stderr.lower() or "unrecognized disk label" in process.stderr.lower():
                print(f"No partition table found on {self.selected_disk}, creating GPT...")
                cmd = ['sudo', 'parted', '-s', self.selected_disk, 'mklabel', 'gpt']
                process = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if process.returncode != 0:
                    raise Exception(f"Failed to create GPT partition table: {process.stderr}")
                
                import time
                time.sleep(1)
            
            # If we're working with selected free space, use those bounds
            if hasattr(self, 'type') and self.type == 2 and hasattr(self, 'selected_free_space'):
                # Use byte boundaries and align to sector boundaries
                start_bytes = self.selected_free_space['start']
                end_bytes = self.selected_free_space['end']
                
                # Align start to next sector boundary (typically 512 bytes)
                sector_size = 512
                if start_bytes % sector_size != 0:
                    start_bytes = ((start_bytes // sector_size) + 1) * sector_size
                
                if size == "100%":
                    # Align end to sector boundary
                    if end_bytes % sector_size != 0:
                        end_bytes = (end_bytes // sector_size) * sector_size
                    end_pos = f"{end_bytes}B"
                else:
                    size_mb = self._convert_size_to_mb(size)
                    if size_mb is None:
                        raise Exception(f"Invalid size format: {size}")
                    
                    size_bytes = int(size_mb * 1024 * 1024)
                    available_bytes = end_bytes - start_bytes
                    
                    if size_bytes > available_bytes:
                        available_mb = available_bytes / (1024 * 1024)
                        raise Exception(f"Requested size ({size_mb:.1f}MB) exceeds available space ({available_mb:.1f}MB)")
                    
                    end_bytes = start_bytes + size_bytes
                    # Align end to sector boundary
                    if end_bytes % sector_size != 0:
                        end_bytes = (end_bytes // sector_size) * sector_size
                    end_pos = f"{end_bytes}B"
                
                start_pos = f"{start_bytes}B"
                
            else:
                # Original logic for whole disk - get free space
                cmd = ['sudo', 'parted', self.selected_disk, 'unit', 'B', 'print', 'free']
                process = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                
                if process.returncode != 0 and "unrecognised disk label" not in process.stderr.lower():
                    raise Exception(f"Failed to get disk info: {process.stderr}")
                
                # Parse output to find free space in bytes
                lines = process.stdout.split('\n')
                free_spaces = []
                
                for line in lines:
                    if 'Free Space' in line:
                        parts = line.strip().split()
                        if len(parts) >= 3:
                            try:
                                start = int(parts[0].replace('B', ''))
                                end = int(parts[1].replace('B', ''))
                                free_spaces.append((start, end))
                            except ValueError:
                                continue
                
                if not free_spaces:
                    progress_dialog.destroy()
                    self._show_error_dialog("Error", "No free space found on disk")
                    return
                
                # Use the largest free space
                start_bytes, end_bytes = max(free_spaces, key=lambda x: x[1] - x[0])
                
                # Align to sector boundaries
                sector_size = 512
                if start_bytes % sector_size != 0:
                    start_bytes = ((start_bytes // sector_size) + 1) * sector_size
                
                if size == "100%":
                    if end_bytes % sector_size != 0:
                        end_bytes = (end_bytes // sector_size) * sector_size
                    end_pos = f"{end_bytes}B"
                else:
                    size_mb = self._convert_size_to_mb(size)
                    if size_mb is None:
                        raise Exception(f"Invalid size format: {size}")
                    
                    size_bytes = int(size_mb * 1024 * 1024)
                    available_bytes = end_bytes - start_bytes
                    
                    if size_bytes > available_bytes:
                        available_mb = available_bytes / (1024 * 1024)
                        raise Exception(f"Requested size ({size_mb:.1f}MB) exceeds available space ({available_mb:.1f}MB)")
                    
                    end_bytes = start_bytes + size_bytes
                    if end_bytes % sector_size != 0:
                        end_bytes = (end_bytes // sector_size) * sector_size
                    end_pos = f"{end_bytes}B"
                
                start_pos = f"{start_bytes}B"
            
            print(f"Creating partition from {start_pos} to {end_pos}")
            
            # Create partition using byte boundaries
            cmd = ['sudo', 'parted', '-s', self.selected_disk, 'mkpart', 'primary', start_pos, end_pos]
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if process.returncode != 0:
                raise Exception(f"Failed to create partition: {process.stderr}")
            
            # Force kernel to re-read partition table
            cmd = ['sudo', 'partprobe', self.selected_disk]
            subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            import time
            time.sleep(2)
            
            # Get the new partition device path
            cmd = ['sudo', 'parted', self.selected_disk, 'print']
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if process.returncode != 0:
                raise Exception(f"Failed to get partition info: {process.stderr}")
            
            lines = process.stdout.split('\n')
            partition_num = 0
            for line in lines:
                line = line.strip()
                if line and line[0].isdigit():
                    parts = line.split()
                    if len(parts) >= 1:
                        try:
                            num = int(parts[0])
                            partition_num = max(partition_num, num)
                        except ValueError:
                            continue

            if partition_num == 0:
                raise Exception("Could not determine new partition number")

            # Use DiskUtils to construct proper partition path
            new_partition = DiskUtils.get_partition_path(self.selected_disk, partition_num)
            if not new_partition:
                # Fallback to old method if DiskUtils fails
                new_partition = DiskUtils.get_partition_path(self.selected_disk, partition_num)
            
            # Format if requested
            if filesystem != 'unformatted':
                self._format_partition_sync(new_partition, filesystem)
            
            progress_dialog.destroy()
            self._show_info_dialog("Success", f"Partition created successfully: {new_partition}")
            self.on_refresh_clicked(None)
            
        except subprocess.TimeoutExpired:
            progress_dialog.destroy()
            self._show_error_dialog("Error", "Operation timed out")
        except Exception as e:
            progress_dialog.destroy()
            self._show_error_dialog("Error", f"Failed to create partition: {str(e)}")

    def _convert_size_to_mb(self, size_str):
        """Convert size string (e.g., '10GB', '500MB') to MB"""
        try:
            if size_str.upper().endswith('GB'):
                return float(size_str[:-2]) * 1000
            elif size_str.upper().endswith('TB'):
                return float(size_str[:-2]) * 1000000
            elif size_str.upper().endswith('MB'):
                return float(size_str[:-2])
            else:
                # If no unit, assume MB
                return float(size_str)
        except (ValueError, IndexError):
            return None

    def _generate_fstab(self):
        """Generate fstab file in /tmp/installer_config/etc/"""
        try:
            # Create fstab header
            fstab_content = [
                "# /etc/fstab: static file system information.",
                "# Use 'blkid' to print the universally unique identifier for a device; this may",
                "# be used with UUID= as a more robust way to name devices that works even if",
                "# disks are added and removed. See fstab(5).",
                "#",
                "# <file system>             <mount point>  <type>  <options>         <dump>  <pass>",
                ""
            ]
            
            if not hasattr(self, 'partition_config') or not self.partition_config:
                fstab_content.append("# No partition configuration found")
            else:
                # Track which device is used for Btrfs root
                btrfs_root_device = None
                btrfs_root_uuid = None
                
                # First pass: identify Btrfs root device
                for device, config in self.partition_config.items():
                    if config.get('mountpoint') == '/':
                        filesystem = self._get_filesystem_type(device)
                        if filesystem == 'btrfs':
                            btrfs_root_device = device
                            btrfs_root_uuid = self._get_device_uuid(device)
                            break
                
                # Generate fstab entries
                for device, config in self.partition_config.items():
                    if 'mountpoint' not in config:
                        continue
                    
                    mountpoint = config['mountpoint']
                    bootable = config.get('bootable', False)
                    
                    # Get filesystem type
                    filesystem = self._get_filesystem_type(device)
                    if not filesystem:
                        filesystem = "auto"
                    
                    # Get UUID for more robust mounting
                    uuid = self._get_device_uuid(device)
                    
                    # For Btrfs root partition, create subvolume entries
                    if device == btrfs_root_device and filesystem == 'btrfs':
                        # Create entries for each subvolume
                        for subvol, mount in self.btrfs_subvolumes.items():
                            if uuid:
                                device_identifier = f"UUID={uuid}"
                            else:
                                device_identifier = device
                            
                            options = f"subvol={subvol},defaults,compress=zstd,noatime"

                            # Btrfs has no fsck; the pass field must be 0 for
                            # every subvolume entry (a non-zero pass makes systemd
                            # run a pointless fsck that can delay or derail boot).
                            dump = "0"
                            pass_num = "0"

                            fstab_line = f"{device_identifier:<25} {mount:<15} {filesystem:<7} {options:<40} {dump:<6} {pass_num}"
                            fstab_content.append(fstab_line)
                        
                        # Add comment about Btrfs subvolumes
                        fstab_content.append(f"# {device} uses Btrfs subvolumes")
                        
                    # For non-Btrfs or non-root partitions
                    elif filesystem != 'btrfs' or mountpoint != '/':
                        # Standard handling for non-Btrfs filesystems
                        if filesystem == "swap":
                            options = "defaults"
                            dump = "0"
                            pass_num = "0"
                        elif mountpoint == "/":
                            options = "defaults"
                            dump = "1"
                            pass_num = "1"
                        elif bootable and mountpoint == "/boot":
                            options = "defaults"
                            dump = "1" 
                            pass_num = "2"
                        else:
                            options = "defaults"
                            dump = "0"
                            pass_num = "2"
                        
                        if uuid:
                            device_identifier = f"UUID={uuid}"
                        else:
                            device_identifier = device
                        
                        fstab_line = f"{device_identifier:<25} {mountpoint:<15} {filesystem:<7} {options:<15} {dump:<6} {pass_num}"
                        fstab_content.append(fstab_line)
                        
                        if bootable:
                            fstab_content.append(f"# {device} is marked as bootable")
            
            # Create directory structure in /tmp/installer_config/etc/
            etc_dir = "/tmp/installer_config/etc"
            os.makedirs(etc_dir, exist_ok=True)
            
            # Save fstab to /tmp/installer_config/etc/fstab
            fstab_path = os.path.join(etc_dir, "fstab")
            
            with open(fstab_path, 'w') as f:
                f.write('\n'.join(fstab_content))
            print(f"Generated fstab saved to: {fstab_path}")
            
        except Exception as e:
            print(f"Error generating fstab: {e}")
            self._show_error_dialog("Error", f"Failed to generate fstab: {str(e)}")
            
            # Create directory structure in /tmp/installer_config/etc/
            etc_dir = "/tmp/installer_config/etc"
            os.makedirs(etc_dir, exist_ok=True)
            
            # Save fstab to /tmp/installer_config/etc/fstab
            fstab_path = os.path.join(etc_dir, "fstab")
            
            with open(fstab_path, 'w') as f:
                f.write('\n'.join(fstab_content))
            print(f"Generated fstab saved to: {fstab_path}")
            
        except Exception as e:
            print(f"Error generating fstab: {e}")
            self._show_error_dialog("Error", f"Failed to generate fstab: {str(e)}")

    def _generate_and_apply_fstab(self):
        """Generate fstab and copy it to /etc/fstab with backup"""
        try:
            # First generate the fstab
            self._generate_fstab()
            
            from datetime import datetime
            
            fstab_path = self.get_generated_fstab_path()
            if not os.path.exists(fstab_path):
                print("Generated fstab not found, skipping /etc/fstab update")
                return
            
            # Create backup of current /etc/fstab
            if os.path.exists("/etc/fstab"):
                backup_path = f"/etc/fstab.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                cmd = ['sudo', 'cp', '/etc/fstab', backup_path]
                subprocess.run(cmd, check=True, timeout=10)
                print(f"Backed up /etc/fstab to {backup_path}")
            
            # Copy generated fstab to /etc/fstab
            cmd = ['sudo', 'cp', fstab_path, '/etc/fstab']
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if process.returncode != 0:
                print(f"Failed to copy fstab to /etc/fstab: {process.stderr}")
            else:
                print("Successfully updated /etc/fstab")
                
        except Exception as e:
            print(f"Error updating /etc/fstab: {e}")

    def _get_filesystem_type(self, device):
        """Get filesystem type of a device using blkid"""
        try:
            cmd = ['sudo', 'blkid', '-o', 'value', '-s', 'TYPE', device]
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if process.returncode == 0:
                return process.stdout.strip()
        except Exception:
            pass
        return None

    def _get_device_uuid(self, device):
        """Get UUID of a device using blkid"""
        try:
            cmd = ['sudo', 'blkid', '-o', 'value', '-s', 'UUID', device]
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if process.returncode == 0:
                uuid = process.stdout.strip()
                return uuid if uuid else None
        except Exception:
            pass
        return None

    def _load_partition_config(self):
        """Load partition configuration from file"""
        try:
            import json
            # Use /tmp/installer_config for configuration file
            config_path = "/tmp/installer_config/.disk_utility_config.json"
            
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    self.partition_config = json.load(f)
            else:
                # If no config file found, start with empty config
                self.partition_config = {}
        except Exception:
            self.partition_config = {}

    def _save_partition_config(self):
        """Save partition configuration to file"""
        try:
            import json
            # Ensure directory exists
            config_dir = "/tmp/installer_config"
            os.makedirs(config_dir, exist_ok=True)
            
            # Save configuration to /tmp/installer_config
            config_path = os.path.join(config_dir, ".disk_utility_config.json")
            
            with open(config_path, 'w') as f:
                json.dump(self.partition_config, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")

    def get_generated_fstab_path(self):
        """Get the path to the generated fstab file"""
        return "/tmp/installer_config/etc/fstab"

    def export_fstab_to_system(self):
        """Export the generated fstab to /etc/fstab (with backup)"""
        try:
            from datetime import datetime
            
            fstab_path = self.get_generated_fstab_path()
            if not os.path.exists(fstab_path):
                self._show_error_dialog("Error", "No generated fstab found. Please configure partitions first.")
                return
            
            # Create backup of current /etc/fstab
            backup_path = f"/etc/fstab.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            if os.path.exists("/etc/fstab"):
                cmd = ['sudo', 'cp', '/etc/fstab', backup_path]
                subprocess.run(cmd, check=True, timeout=10)
            
            # Copy generated fstab to /etc/fstab
            cmd = ['sudo', 'cp', fstab_path, '/etc/fstab']
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if process.returncode != 0:
                raise Exception(f"Failed to copy fstab: {process.stderr}")
            
            self._show_info_dialog("Success", 
                                f"fstab exported to /etc/fstab\n"
                                f"Backup created: {backup_path}\n\n"
                                f"You can now run 'sudo mount -a' to mount all configured partitions.")
            
        except subprocess.TimeoutExpired:
            self._show_error_dialog("Error", "Operation timed out")
        except Exception as e:
            self._show_error_dialog("Error", f"Failed to export fstab: {str(e)}")

    def _execute_remove_partition(self):
        """Execute partition removal using parted"""
        try:
            progress_dialog = self._show_progress_dialog("Removing Partition", f"Removing partition {self.selected_disk}...")
            
            # Extract partition number from device path
            disk_info = DiskUtils.parse_disk_path(self.selected_disk)
            if not disk_info or disk_info['partition_num'] is None:
                raise Exception("Could not determine partition number")

            partition_num = str(disk_info['partition_num'])
            base_disk = disk_info['base_disk']
            
            # Remove the partition
            cmd = ['sudo', 'parted', '-s', base_disk, 'rm', partition_num]
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if process.returncode != 0:
                raise Exception(f"Failed to remove partition: {process.stderr}")
            
            # Force kernel to re-read partition table immediately
            cmd = ['sudo', 'partprobe', base_disk]
            subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            # Remove from configuration if it exists
            if hasattr(self, 'partition_config') and self.selected_disk in self.partition_config:
                del self.partition_config[self.selected_disk]
                self._save_partition_config()
                self._generate_and_apply_fstab()  # Use the new method
            
            progress_dialog.destroy()
            self._show_info_dialog("Success", f"Partition {self.selected_disk} removed successfully")
            
            # Force immediate refresh to show updated partition numbering
            import time
            time.sleep(1)  # Give kernel time to update
            self.on_refresh_clicked(None)
            
        except subprocess.TimeoutExpired:
            progress_dialog.destroy()
            self._show_error_dialog("Error", "Operation timed out")
        except Exception as e:
            progress_dialog.destroy()
            self._show_error_dialog("Error", f"Failed to remove partition: {str(e)}")

    def _execute_format(self, filesystem):
        """Execute formatting using appropriate mkfs command"""
        try:
            progress_dialog = self._show_progress_dialog("Formatting Partition", f"Formatting {self.selected_disk} with {filesystem}...")
            self._format_partition_sync(self.selected_disk, filesystem)
            
            progress_dialog.destroy()
            self._show_info_dialog("Success", f"Partition {self.selected_disk} formatted successfully with {filesystem}")
            self.on_refresh_clicked(None)
            
        except Exception as e:
            progress_dialog.destroy()
            self._show_error_dialog("Error", f"Failed to format partition: {str(e)}")

    def _create_btrfs_subvolumes(self, device):
        """Create the Btrfs subvolumes defined in self.btrfs_subvolumes.

        Mounts the freshly-formatted Btrfs top-level (subvolid=5), creates one
        subvolume per entry (e.g. @, @home) and unmounts. Those subvolumes are
        mounted later through explicit subvol= options in the generated fstab,
        and the kernel is told which one holds the root via rootflags=subvol=@
        (see bootloader.sh) -- so we intentionally do NOT change the
        filesystem's default subvolume here (keeping the default at subvolid=5
        is what snapshot/rollback tooling expects).

        Raises on failure so the caller can surface a partitioning error instead
        of silently producing an unbootable system.
        """
        import tempfile
        import time

        subvols = list(self.btrfs_subvolumes.keys()) or ['@']

        with tempfile.TemporaryDirectory() as tmpdir:
            # Mount the top-level volume explicitly so subvolumes are created at
            # the filesystem root regardless of any default-subvolume setting.
            mount_proc = subprocess.run(
                ['sudo', 'mount', '-t', 'btrfs', '-o', 'subvolid=5', device, tmpdir],
                capture_output=True, text=True, timeout=30
            )
            if mount_proc.returncode != 0:
                raise Exception(f"Failed to mount Btrfs {device}: {mount_proc.stderr}")

            try:
                for subvol in subvols:
                    proc = subprocess.run(
                        ['sudo', 'btrfs', 'subvolume', 'create', f"{tmpdir}/{subvol}"],
                        capture_output=True, text=True, timeout=30
                    )
                    if proc.returncode != 0:
                        raise Exception(f"Failed to create subvolume {subvol}: {proc.stderr}")
                    print(f"Created Btrfs subvolume {subvol}")
            finally:
                time.sleep(1)
                subprocess.run(['sudo', 'sync'], capture_output=True)
                subprocess.run(['sudo', 'umount', tmpdir], capture_output=True, text=True, timeout=30)

    def _format_partition_sync(self, device, filesystem):
        """Format a partition synchronously"""
        if filesystem == 'ext4':
            cmd = ['sudo', 'mkfs.ext4', '-F', device]
        elif filesystem == 'btrfs':
            # Format as Btrfs
            cmd = ['sudo', 'mkfs.btrfs', '-f', device]
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if process.returncode != 0:
                raise Exception(f"Formatting failed: {process.stderr}")
            
            # Create Btrfs subvolumes if this is being set as root
            if hasattr(self, 'partition_config') and device in self.partition_config:
                if self.partition_config[device].get('mountpoint') == '/':
                    self._create_btrfs_subvolumes(device)
            return
        elif filesystem == 'ntfs':
            cmd = ['sudo', 'mkfs.ntfs', '-f', device]
        elif filesystem == 'fat32':
            cmd = ['sudo', 'mkfs.fat', '-F', '32', device]
        elif filesystem == 'exfat':
            cmd = ['sudo', 'mkfs.exfat', device]
        elif filesystem == 'swap':
            cmd = ['sudo', 'mkswap', device]
        else:
            raise Exception(f"Unsupported filesystem: {filesystem}")
        
        process = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        if process.returncode != 0:
            raise Exception(f"Formatting failed: {process.stderr}")

    def _execute_set_mountpoint(self, mountpoint):
        """Set mountpoint for partition and update fstab configuration"""
        try:
            if not hasattr(self, 'partition_config'):
                self.partition_config = {}
            
            self.partition_config[self.selected_disk] = self.partition_config.get(self.selected_disk, {})
            self.partition_config[self.selected_disk]['mountpoint'] = mountpoint
            
            # Retroactively create Btrfs subvolumes if setting to root and filesystem is Btrfs
            if mountpoint == '/' and self._get_filesystem_type(self.selected_disk) == 'btrfs':
                try:
                    self._create_btrfs_subvolumes(self.selected_disk)
                    print(f"Retroactively created Btrfs subvolumes for {self.selected_disk} as root mountpoint.")
                except Exception as subvol_error:
                    print(f"Warning: Failed to create Btrfs subvolumes retroactively: {str(subvol_error)}")
                    # Optionally show a dialog warning here
                    self._show_info_dialog("Warning", 
                                        f"Mountpoint set, but failed to create Btrfs subvolumes: {str(subvol_error)}\n\n"
                                        f"You may need to create them manually using GParted.")
            
            # Save configuration and update /etc/fstab
            self._save_partition_config()
            self._generate_and_apply_fstab()
            
            self._show_info_dialog("Mountpoint Set", 
                                f"Mountpoint for {self.selected_disk} set to: {mountpoint}\n\n"
                                f"Configuration saved and /etc/fstab updated.")
            
            # Refresh to show the new mountpoint
            self.on_refresh_clicked(None)
            
        except Exception as e:
            self._show_error_dialog("Error", f"Failed to set mountpoint: {str(e)}")

    def _execute_set_bootflag(self, enable_boot):
        """Execute boot flag setting using parted"""
        try:
            progress_dialog = self._show_progress_dialog("Setting Boot Flag", f"Setting boot flag for {self.selected_disk}...")
            
            disk_info = DiskUtils.parse_disk_path(self.selected_disk)
            if not disk_info or disk_info['partition_num'] is None:
                raise Exception("Could not determine partition number")

            partition_num = str(disk_info['partition_num'])
            base_disk = disk_info['base_disk']
            
            flag_state = 'on' if enable_boot else 'off'
            cmd = ['sudo', 'parted', '-s', base_disk, 'set', partition_num, 'boot', flag_state]
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if process.returncode != 0:
                raise Exception(f"Failed to set boot flag: {process.stderr}")
            
            if not hasattr(self, 'partition_config'):
                self.partition_config = {}
            
            self.partition_config[self.selected_disk] = self.partition_config.get(self.selected_disk, {})
            self.partition_config[self.selected_disk]['bootable'] = enable_boot
            
            # Save configuration and update /etc/fstab
            self._save_partition_config()
            self._generate_and_apply_fstab()
            
            action = "enabled" if enable_boot else "disabled"
            progress_dialog.destroy()
            self._show_info_dialog("Success", 
                        f"Boot flag {action} for {self.selected_disk}\n\n"
                        f"Configuration saved and /etc/fstab updated.")
            self.on_refresh_clicked(None)
            
        except Exception as e:
            progress_dialog.destroy()
            self._show_error_dialog("Error", f"Failed to set boot flag: {str(e)}")

    def _execute_format_whole_disk(self):
        """Format whole disk with appropriate partition table and partitions based on boot mode"""
        try:
            # Detect boot mode first
            boot_mode = self._detect_boot_mode()
            
            if boot_mode == "uefi":
                dialog_body = (f"This will COMPLETELY WIPE {self.selected_disk} and create:\n\n"
                            f"• 1 GiB FAT32 EFI System Partition at /boot\n"
                            f"• Remaining space as ext4 partition at /\n\n"
                            f"ALL DATA WILL BE LOST! Are you sure?")
            else:
                dialog_body = (f"This will COMPLETELY WIPE {self.selected_disk} and create:\n\n"
                            f"• Single ext4 partition at / (bootable for Legacy boot)\n\n"
                            f"ALL DATA WILL BE LOST! Are you sure?\n\n"
                            f"Note: GRUB will be installed to the MBR")
            
            # Show confirmation dialog
            dialog = Adw.MessageDialog(
                heading="Format Entire Disk",
                body=dialog_body,
                transient_for=self.get_root()
            )
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("wipe", "Wipe Disk")
            dialog.set_response_appearance("wipe", Adw.ResponseAppearance.DESTRUCTIVE)
            
            # Store boot_mode for the response handler
            self._temp_boot_mode = boot_mode
            dialog.connect("response", self._on_wipe_disk_response)
            dialog.present()
            
        except Exception as e:
            self._show_error_dialog("Error", f"Failed to format disk: {str(e)}")

    def _on_wipe_disk_response(self, dialog, response_id):
        """Handle disk wipe confirmation"""
        if response_id == "wipe":
            try:
                boot_mode = getattr(self, '_temp_boot_mode', 'uefi')
                if boot_mode == "uefi":
                    progress_dialog = self._show_progress_dialog("Formatting Disk", "Wiping disk and creating UEFI partitions...")
                else:
                    progress_dialog = self._show_progress_dialog("Formatting Disk", "Wiping disk and creating Legacy partitions...")
                self._wipe_disk_sync(progress_dialog, boot_mode)
            except Exception as e:
                self._show_error_dialog("Error", f"Failed to wipe disk: {str(e)}")
            finally:
                # Clean up temporary variable
                if hasattr(self, '_temp_boot_mode'):
                    delattr(self, '_temp_boot_mode')

    def _wipe_disk_sync(self, progress_dialog, boot_mode="uefi"):
        """Synchronous disk wiping with support for both UEFI and Legacy boot modes"""
        try:
            if boot_mode == "uefi":
                # UEFI mode: Create GPT with ESP and root partitions
                # Step 1: Create GPT partition table
                cmd = ['sudo', 'parted', '-s', self.selected_disk, 'mklabel', 'gpt']
                process = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if process.returncode != 0:
                    raise Exception(f"Failed to create GPT table: {process.stderr}")

                # Step 2: Create EFI System Partition (1GiB FAT32)
                cmd = ['sudo', 'parted', '-s', self.selected_disk, 'mkpart', 'primary', 'fat32', '1MiB', '1025MiB']
                process = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if process.returncode != 0:
                    raise Exception(f"Failed to create EFI partition: {process.stderr}")

                # Step 3: Create root partition (remaining space ext4)
                cmd = ['sudo', 'parted', '-s', self.selected_disk, 'mkpart', 'primary', 'ext4', '1025MiB', '100%']
                process = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if process.returncode != 0:
                    raise Exception(f"Failed to create root partition: {process.stderr}")

                # Step 4: Set ESP flag on first partition
                cmd = ['sudo', 'parted', '-s', self.selected_disk, 'set', '1', 'esp', 'on']
                process = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if process.returncode != 0:
                    raise Exception(f"Failed to set ESP flag: {process.stderr}")

                # Give the system a moment to recognize new partitions
                import time
                time.sleep(2)

                # Step 5: Format EFI partition as FAT32
                boot_partition = DiskUtils.get_partition_path(self.selected_disk, 1)
                cmd = ['sudo', 'mkfs.fat', '-F', '32', boot_partition]
                process = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if process.returncode != 0:
                    raise Exception(f"Failed to format EFI partition: {process.stderr}")

                # Step 6: Format root partition as ext4
                root_partition = DiskUtils.get_partition_path(self.selected_disk, 2)
                cmd = ['sudo', 'mkfs.ext4', '-F', root_partition]
                process = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if process.returncode != 0:
                    raise Exception(f"Failed to format root partition: {process.stderr}")

                # Step 7: Update configuration with mountpoints
                if not hasattr(self, 'partition_config'):
                    self.partition_config = {}

                # Configure EFI System Partition
                self.partition_config[boot_partition] = {
                    'mountpoint': '/boot',
                    'bootable': True
                }

                # Configure root partition
                self.partition_config[root_partition] = {
                    'mountpoint': '/',
                    'bootable': False
                }

                success_message = (f"UEFI disk {self.selected_disk} successfully formatted!\n\n"
                                f"Created partitions:\n"
                                f"• {boot_partition}: 1 GiB FAT32 at /boot (ESP)\n"
                                f"• {root_partition}: Remaining space ext4 at /\n\n"
                                f"fstab has been generated automatically.")

            else:
                # Legacy mode: Create MBR with single bootable root partition
                # Step 1: Create MBR partition table
                cmd = ['sudo', 'parted', '-s', self.selected_disk, 'mklabel', 'msdos']
                process = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if process.returncode != 0:
                    raise Exception(f"Failed to create MBR table: {process.stderr}")

                # Step 2: Create single root partition (entire disk)
                cmd = ['sudo', 'parted', '-s', self.selected_disk, 'mkpart', 'primary', 'ext4', '1MiB', '100%']
                process = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if process.returncode != 0:
                    raise Exception(f"Failed to create root partition: {process.stderr}")

                # Step 3: Set boot flag on the partition
                cmd = ['sudo', 'parted', '-s', self.selected_disk, 'set', '1', 'boot', 'on']
                process = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if process.returncode != 0:
                    raise Exception(f"Failed to set boot flag: {process.stderr}")

                # Give the system a moment to recognize new partitions
                import time
                time.sleep(2)

                # Step 4: Format root partition as ext4
                root_partition = f"{self.selected_disk}1"
                cmd = ['sudo', 'mkfs.ext4', '-F', root_partition]
                process = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if process.returncode != 0:
                    raise Exception(f"Failed to format root partition: {process.stderr}")

                # Step 5: Update configuration with mountpoints
                if not hasattr(self, 'partition_config'):
                    self.partition_config = {}

                # Configure root partition as bootable
                self.partition_config[root_partition] = {
                    'mountpoint': '/',
                    'bootable': True
                }

                success_message = (f"Legacy disk {self.selected_disk} successfully formatted!\n\n"
                                f"Created partitions:\n"
                                f"• {root_partition}: Full disk ext4 at / (bootable)\n\n"
                                f"fstab has been generated automatically.\n\n"
                                f"Note: GRUB will be installed to the MBR of {self.selected_disk}")

            # Save configuration and generate fstab for both modes
            self._save_partition_config()
            self._generate_and_apply_fstab()

            progress_dialog.destroy()
            
            # DON'T show the info dialog here anymore for automated flows
            # Just refresh the partition list
            self.on_refresh_clicked(None)
            
            # Return True to indicate success
            return True

        except subprocess.TimeoutExpired:
            progress_dialog.destroy()
            self._show_error_dialog("Error", "Operation timed out")
            return False
        except Exception as e:
            progress_dialog.destroy()
            self._show_error_dialog("Error", f"Failed to complete disk formatting: {str(e)}")
            return False

    # Also, create a method that can be called without showing the final info dialog:
    def _wipe_disk_sync_silent(self, progress_dialog, boot_mode="uefi"):
        """Silent version that doesn't show success dialog - for automated flows"""
        return self._wipe_disk_sync(progress_dialog, boot_mode)

if __name__ == "__main__":
    app = Gtk.Application()
    def on_activate(app):
        win = Adw.ApplicationWindow(application=app, title="Disk Utility Test")
        win.set_default_size(450, 600)
        disk_widget = DiskUtilityWidget()
        win.set_content(disk_widget)
        win.present()
    app.connect('activate', on_activate)
    app.run(None)
