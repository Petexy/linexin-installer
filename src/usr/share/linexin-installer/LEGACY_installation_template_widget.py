#!/usr/bin/env python3

import os
import gi
import json
import subprocess
import re

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, GObject
from simple_localization_manager import get_localization_manager
_ = get_localization_manager().get_text

class InstallationTemplateWidget(Gtk.Box):
    """
    A GTK widget for selecting installation templates during system installation.
    Provides options for installing on free space, clean install, or manual partitioning.
    """
    
    __gsignals__ = {
        'template-selected': (GObject.SignalFlags.RUN_FIRST, None, (str, object)),
        'continue-to-next-page': (GObject.SignalFlags.RUN_FIRST, None, ())
    }
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        get_localization_manager().register_widget(self)
        
        self.set_orientation(Gtk.Orientation.VERTICAL)
        self.set_spacing(20)
        self.set_margin_top(30)
        self.set_margin_bottom(30)
        
        # State tracking
        self.selected_template = None
        self.free_spaces = []  # List of free spaces found
        self.available_disks = []
        self.selected_disk = None
        self.selected_free_space = None
        
        # --- Title Label ---
        self.title = Gtk.Label()
        self.title.set_markup('<span size="xx-large" weight="bold">Choose Installation Type</span>')
        self.title.set_halign(Gtk.Align.CENTER)
        self.append(self.title)
        
        # --- Adw.Clamp constrains the width of the content ---
        clamp = Adw.Clamp(margin_start=12, margin_end=12, maximum_size=600)
        clamp.set_vexpand(True)
        self.append(clamp)
        
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        clamp.set_child(content_box)
        
        # --- Subtitle Label ---
        self.subtitle = Gtk.Label(
            label="Select how you want to install the operating system.",
            halign=Gtk.Align.CENTER
        )
        self.subtitle.add_css_class('dim-label')
        content_box.append(self.subtitle)
        
        # --- Scrolled Window for the options ---
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_vexpand(True)
        content_box.append(scrolled_window)
        
        # Options container
        options_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        options_box.set_margin_top(20)
        options_box.set_margin_start(20)
        options_box.set_margin_end(20)
        scrolled_window.set_child(options_box)
        
        # --- Installation Options ---
        
        # Detect free spaces on all disks
        self._detect_free_spaces()
        
        # Option 1: Install on free space (only if sufficient free space is detected)
        if self.free_spaces:
            free_space_group = Adw.PreferencesGroup()
            options_box.append(free_space_group)
            
            self.free_space_row = Adw.ActionRow()
            self.free_space_row.set_title("Install on free space")
            self.free_space_row.set_subtitle("Use available free space on disk without removing existing data")
            
            free_space_radio = Gtk.CheckButton()
            free_space_radio.set_active(False)
            self.free_space_row.add_prefix(free_space_radio)
            self.free_space_row.set_activatable_widget(free_space_radio)
            
            free_space_icon = Gtk.Image.new_from_icon_name("list-add-symbolic")
            free_space_icon.set_pixel_size(32)
            self.free_space_row.add_suffix(free_space_icon)
            
            free_space_group.add(self.free_space_row)
            
            # Free space details (initially hidden)
            self.free_space_details_revealer = Gtk.Revealer()
            self.free_space_details_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
            options_box.append(self.free_space_details_revealer)
            
            free_space_details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            free_space_details_box.set_margin_start(40)
            free_space_details_box.set_margin_end(20)
            self.free_space_details_revealer.set_child(free_space_details_box)
            
            # Free space selector (if multiple free spaces)
            if len(self.free_spaces) > 1:
                space_label = Gtk.Label(label="Select free space to use:", xalign=0)
                space_label.add_css_class('dim-label')
                free_space_details_box.append(space_label)
                
                self.free_space_combo = Gtk.ComboBoxText()
                for fs in self.free_spaces:
                    size_gb = fs['size'] // (1024**3)
                    self.free_space_combo.append_text(f"{fs['disk']} - {size_gb} GB free")
                self.free_space_combo.set_active(0)
                self.free_space_combo.connect("changed", self._on_free_space_selection_changed)
                free_space_details_box.append(self.free_space_combo)
            else:
                # Single free space info
                fs = self.free_spaces[0]
                size_gb = fs['size'] // (1024**3)
                info_label = Gtk.Label(
                    label=f"Available free space: {size_gb} GB on {fs['disk']}",
                    xalign=0
                )
                info_label.add_css_class('dim-label')
                free_space_details_box.append(info_label)
            
            # Show what will be created
            self.space_config_label = Gtk.Label(xalign=0)
            self.space_config_label.add_css_class('dim-label')
            self._update_space_config_info()
            free_space_details_box.append(self.space_config_label)
            
            # Info about automatic configuration
            info_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            info_box.set_margin_top(10)
            free_space_details_box.append(info_box)
            
            info_icon = Gtk.Image.new_from_icon_name("dialog-information-symbolic")
            info_icon.set_pixel_size(16)
            info_box.append(info_icon)
            
            info_label = Gtk.Label(xalign=0)
            info_label.set_markup('<span size="small">Linux will be automatically configured with:\n'
                                 '• Boot partition (if UEFI mode)\n'
                                 '• Root partition with remaining space</span>')
            info_label.set_wrap(True)
            info_box.append(info_label)
            
            free_space_radio.connect("toggled", self._on_free_space_toggled)
        else:
            free_space_radio = None
        
        # Option 2: Wipe disk and install
        wipe_group = Adw.PreferencesGroup()
        options_box.append(wipe_group)
        
        self.wipe_row = Adw.ActionRow()
        self.wipe_row.set_title("Erase disk and install")
        self.wipe_row.set_subtitle("Delete all data on the selected disk and install the system")
        
        wipe_radio = Gtk.CheckButton()
        if free_space_radio:
            wipe_radio.set_group(free_space_radio)
        wipe_radio.set_active(False)
        self.wipe_row.add_prefix(wipe_radio)
        self.wipe_row.set_activatable_widget(wipe_radio)
        
        wipe_icon = Gtk.Image.new_from_icon_name("drive-harddisk-symbolic")
        wipe_icon.set_pixel_size(32)
        self.wipe_row.add_suffix(wipe_icon)
        
        wipe_group.add(self.wipe_row)
        
        # Disk selector (initially hidden)
        self.disk_details_revealer = Gtk.Revealer()
        self.disk_details_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        options_box.append(self.disk_details_revealer)
        
        disk_details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        disk_details_box.set_margin_start(40)
        disk_details_box.set_margin_end(20)
        self.disk_details_revealer.set_child(disk_details_box)
        
        disk_label = Gtk.Label(label="Select disk to format:", xalign=0)
        disk_label.add_css_class('dim-label')
        disk_details_box.append(disk_label)
        
        # Detect available disks
        self._detect_available_disks()
        
        self.disk_combo = Gtk.ComboBoxText()
        for disk in self.available_disks:
            size_gb = disk['size'] // (1024**3)
            self.disk_combo.append_text(f"{disk['device']} - {disk['model']} ({size_gb} GB)")
        if self.available_disks:
            self.disk_combo.set_active(0)
        disk_details_box.append(self.disk_combo)
        
        # Warning label
        warning_label = Gtk.Label(xalign=0)
        warning_text = "Warning: All data will be lost!"
        warning_label.set_markup(f'<span color="red" weight="bold">{warning_text}</span>')
        warning_label.set_wrap(True)
        disk_details_box.append(warning_label)
        
        wipe_radio.connect("toggled", self._on_wipe_toggled)
        
        # Option 3: Manual partitioning
        manual_group = Adw.PreferencesGroup()
        options_box.append(manual_group)
        
        self.manual_row = Adw.ActionRow()
        self.manual_row.set_title("Manual partitioning")
        self.manual_row.set_subtitle("Create, resize, and configure partitions manually")
        
        manual_radio = Gtk.CheckButton()
        if free_space_radio:
            manual_radio.set_group(free_space_radio)
        elif wipe_radio:
            manual_radio.set_group(wipe_radio)
        manual_radio.set_active(True)  # Default selection
        self.manual_row.add_prefix(manual_radio)
        self.manual_row.set_activatable_widget(manual_radio)
        
        manual_icon = Gtk.Image.new_from_icon_name("applications-utilities-symbolic")
        manual_icon.set_pixel_size(32)
        self.manual_row.add_suffix(manual_icon)
        
        manual_group.add(self.manual_row)
        
        manual_radio.connect("toggled", self._on_manual_toggled)
        
        # Store radio buttons for reference
        self.free_space_radio = free_space_radio
        self.wipe_radio = wipe_radio
        self.manual_radio = manual_radio
        
        # Set default selection
        self.selected_template = "manual"
        
        # --- Navigation Buttons ---
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        button_box.set_halign(Gtk.Align.CENTER)
        self.append(button_box)
        
        self.btn_back = Gtk.Button(label="Back")
        self.btn_back.add_css_class('buttons_all')
        button_box.append(self.btn_back)
        
        self.btn_proceed = Gtk.Button(label="Continue")
        self.btn_proceed.add_css_class('suggested-action')
        self.btn_proceed.add_css_class('buttons_all')
        self.btn_proceed.connect("clicked", self.on_continue_clicked)
        button_box.append(self.btn_proceed)
        
        get_localization_manager().update_widget_tree(self)
    
    def _detect_free_spaces(self):
        """Detect free spaces larger than 10GB on all disks"""
        try:
            # First get list of all disks
            cmd = ['lsblk', '-d', '-J', '-o', 'NAME,SIZE,MODEL,TYPE']
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if process.returncode == 0:
                data = json.loads(process.stdout)
                
                for device in data.get('blockdevices', []):
                    if device.get('type') == 'disk':
                        disk_name = f"/dev/{device['name']}"
                        
                        # Get free space info using parted
                        cmd = ['sudo', 'parted', disk_name, 'unit', 'B', 'print', 'free']
                        parted_process = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                        
                        if parted_process.returncode == 0:
                            lines = parted_process.stdout.split('\n')
                            
                            for line in lines:
                                if 'Free Space' in line:
                                    parts = line.strip().split()
                                    if len(parts) >= 3:
                                        try:
                                            start = int(parts[0].replace('B', ''))
                                            end = int(parts[1].replace('B', ''))
                                            size = int(parts[2].replace('B', ''))
                                            
                                            # Only consider free spaces larger than 10GB
                                            if size > 10 * 1024**3:
                                                self.free_spaces.append({
                                                    'disk': disk_name,
                                                    'start': start,
                                                    'end': end,
                                                    'size': size,
                                                    'model': device.get('model', 'Unknown')
                                                })
                                        except (ValueError, IndexError):
                                            continue
        
        except Exception as e:
            print(f"Error detecting free spaces: {e}")
    
    def _detect_available_disks(self):
        """Detect all available disks on the system"""
        try:
            cmd = ['lsblk', '-d', '-J', '-o', 'NAME,SIZE,MODEL,TYPE']
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if process.returncode == 0:
                data = json.loads(process.stdout)
                
                for device in data.get('blockdevices', []):
                    if device.get('type') == 'disk':
                        # Get size in bytes
                        size_cmd = ['sudo', 'blockdev', '--getsize64', f"/dev/{device['name']}"]
                        size_process = subprocess.run(size_cmd, capture_output=True, text=True, timeout=5)
                        
                        if size_process.returncode == 0:
                            size_bytes = int(size_process.stdout.strip())
                            
                            self.available_disks.append({
                                'device': f"/dev/{device['name']}",
                                'size': size_bytes,
                                'model': device.get('model', 'Unknown')
                            })
        
        except Exception as e:
            print(f"Error detecting available disks: {e}")
    
    def _on_free_space_toggled(self, radio):
        """Handle free space option toggle"""
        if radio.get_active():
            self.selected_template = "free_space"
            self.free_space_details_revealer.set_reveal_child(True)
            self.disk_details_revealer.set_reveal_child(False)
            self._update_space_config_info()
    
    def _on_wipe_toggled(self, radio):
        """Handle wipe disk option toggle"""
        if radio.get_active():
            self.selected_template = "wipe"
            self.disk_details_revealer.set_reveal_child(True)
            if self.free_spaces:
                self.free_space_details_revealer.set_reveal_child(False)
    
    def _on_manual_toggled(self, radio):
        """Handle manual partitioning option toggle"""
        if radio.get_active():
            self.selected_template = "manual"
            self.disk_details_revealer.set_reveal_child(False)
            if self.free_spaces:
                self.free_space_details_revealer.set_reveal_child(False)
    
    def _on_free_space_selection_changed(self, combo):
        """Handle free space selection change"""
        self._update_space_config_info()
    
    def _update_space_config_info(self):
        """Update the space configuration info label"""
        if self.free_spaces:
            if hasattr(self, 'free_space_combo') and len(self.free_spaces) > 1:
                selected_fs = self.free_spaces[self.free_space_combo.get_active()]
            else:
                selected_fs = self.free_spaces[0]
            
            size_gb = selected_fs['size'] // (1024**3)
            
            # Detect if system is UEFI or Legacy
            if os.path.exists('/sys/firmware/efi'):
                config_text = (f"Will create in {size_gb} GB free space:\n"
                              f"• 1 GB FAT32 boot partition (EFI)\n"
                              f"• {size_gb - 1} GB ext4 root partition")
            else:
                config_text = (f"Will create in {size_gb} GB free space:\n"
                              f"• {size_gb} GB ext4 root partition (bootable)")
            
            self.space_config_label.set_text(config_text)
    
    def _show_progress_dialog(self, heading, message):
        """Show progress dialog with spinner"""
        dialog = Adw.MessageDialog(
            heading=heading,
            body=message,
            transient_for=self.get_root()
        )
        
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
    
    def on_continue_clicked(self, button):
        """Handle continue button click"""
        self._proceed_with_template()
    
    def _proceed_with_template(self):
        """Proceed with the selected template"""
        template_data = {
            'template': self.selected_template
        }
        
        if self.selected_template == "free_space":
            # Prepare data for free space installation
            if hasattr(self, 'free_space_combo') and len(self.free_spaces) > 1:
                selected_free_space = self.free_spaces[self.free_space_combo.get_active()]
            else:
                selected_free_space = self.free_spaces[0]
            
            template_data['disk'] = selected_free_space['disk']
            template_data['free_space'] = selected_free_space
            
        elif self.selected_template == "wipe":
            # Prepare data for wipe installation
            if self.available_disks:
                selected_disk = self.available_disks[self.disk_combo.get_active()]
                template_data['target_disk'] = selected_disk['device']
        
        # Emit signal with template data
        self.emit('template-selected', self.selected_template, template_data)
    
    def execute_template(self, disk_utility_widget):
        """Execute the selected template using disk_utility_widget methods"""
        if self.selected_template == "free_space":
            return self._execute_free_space_installation(disk_utility_widget)
        elif self.selected_template == "wipe":
            return self._execute_wipe_installation(disk_utility_widget)
        else:  # manual
            # For manual, just proceed to disk utility
            return True
    
    def _execute_free_space_installation(self, disk_utility_widget):
        """Execute installation on free space using disk_utility_widget"""
        try:
            if hasattr(self, 'free_space_combo') and len(self.free_spaces) > 1:
                selected_free_space = self.free_spaces[self.free_space_combo.get_active()]
            else:
                selected_free_space = self.free_spaces[0]
            
            disk = selected_free_space['disk']
            
            print(f"Installing on free space: {disk}")
            print(f"Free space details: start={selected_free_space['start']}, end={selected_free_space['end']}, size={selected_free_space['size']}")
            
            # Set up disk_utility_widget to use the free space
            disk_utility_widget.selected_disk = disk
            disk_utility_widget.selected_free_space = selected_free_space
            disk_utility_widget.type = 2  # Type 2 indicates free space
            
            # Call auto configure which will use the free space
            disk_utility_widget._auto_configure_disk()
            
            return True
            
        except Exception as e:
            self._show_error_dialog("Error", f"Failed to configure free space installation: {str(e)}")
            return False
    
    def _execute_wipe_installation(self, disk_utility_widget):
        """Execute wipe disk installation using disk_utility_widget"""
        try:
            if self.available_disks:
                selected_disk = self.available_disks[self.disk_combo.get_active()]
                disk = selected_disk['device']
                
                print(f"Wiping and installing on disk: {disk}")
                
                # Set up disk_utility_widget for whole disk
                disk_utility_widget.selected_disk = disk
                disk_utility_widget.type = 0  # Type 0 indicates whole disk
                
                # Detect boot mode
                boot_mode = "uefi" if os.path.exists('/sys/firmware/efi') else "legacy"
                
                # Show progress dialog
                progress_dialog = self._show_progress_dialog(
                    "Formatting Disk",
                    f"Wiping {disk} and creating partitions..."
                )
                
                # Execute the wipe using disk_utility_widget's method
                success = disk_utility_widget._wipe_disk_sync(progress_dialog, boot_mode)

                if success:
                    # Emit the continue signal to proceed to next page
                    GLib.idle_add(lambda: self.emit('continue-to-next-page'))
                
                return success
            
            return False
            
        except Exception as e:
            self._show_error_dialog("Error", f"Failed to execute wipe installation: {str(e)}")
            return False