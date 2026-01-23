#!/usr/bin/env python3

import os
import gi
import json
import subprocess
import re
import time
import threading

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, GObject, Gio, Gdk
from simple_localization_manager import get_localization_manager
_ = get_localization_manager().get_text

class InstallationTemplateWidget(Gtk.Box):
    """
    A GTK widget for selecting installation templates during system installation.
    Splits selected partition into EFI (FAT32) and Root (ext4) automatically.
    """

    __gsignals__ = {
        'template-selected': (GObject.SignalFlags.RUN_FIRST, None, (str, object)),
        'continue-to-next-page': (GObject.SignalFlags.RUN_FIRST, None, ())
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        get_localization_manager().register_widget(self)

        self.set_orientation(Gtk.Orientation.VERTICAL)
        self.set_spacing(0)

        # State tracking
        self.selected_template = None
        self.partitions = []
        self.selected_partition = None
        self.selected_disk = None
        self.selected_disk_widget = None

        # Connect map signal to refresh data when widget becomes visible
        self.connect("map", self._on_map)
        
        # Setup CSS
        self.setup_css()

        # --- UI Construction ---
        self.view_stack = Gtk.Stack()
        self.view_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.append(self.view_stack)

        # 1. Main Content View
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=40)
        self.content_box.set_margin_top(30)
        self.content_box.set_margin_bottom(30)
        self.content_box.set_margin_start(40)
        self.content_box.set_margin_end(40)
        self.content_box.set_vexpand(True)
        self.content_box.set_valign(Gtk.Align.CENTER)
        
        self.view_stack.add_named(self.content_box, "main")

        # Title & Subtitle
        self.title = Gtk.Label()
        self.title.set_markup('<span size="32000" weight="300">{}</span>'.format(_("Select a partition to install")))
        self.title.set_halign(Gtk.Align.CENTER)
        self.content_box.append(self.title)

        self.subtitle = Gtk.Label()
        self.subtitle.set_markup('<span size="11500">{}</span>'.format(_("The selected partition will be replaced with Linexin.")))
        self.subtitle.set_halign(Gtk.Align.CENTER)
        self.subtitle.add_css_class('dim-label')
        self.content_box.append(self.subtitle)

        # Scrolled Area
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        scrolled.set_vexpand(True)
        self.content_box.append(scrolled)

        center_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        center_box.set_halign(Gtk.Align.CENTER)
        center_box.set_valign(Gtk.Align.CENTER)
        scrolled.set_child(center_box)

        self.partition_cards_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        self.partition_cards_box.set_halign(Gtk.Align.CENTER)
        center_box.append(self.partition_cards_box)

        # Info Label
        self.info_label = Gtk.Label()
        self.info_label.set_wrap(True)
        self.info_label.set_max_width_chars(70)
        self.info_label.set_halign(Gtk.Align.CENTER)
        self.info_label.add_css_class('dim-label')
        self.info_label.set_margin_top(30)
        self.content_box.append(self.info_label)

        # Buttons
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        button_box.set_halign(Gtk.Align.CENTER)
        button_box.set_margin_bottom(30)
        self.append(button_box) # Note: We keep buttons outside the stack so they persist, or move inside if you want them hidden

        # Actually, if we want to "wait" effectively, we might want to hide these buttons or disable them.
        # But simpler is to put everything in the stack or just overlay. 
        # Let's move the button_box INTO content_box so it disappears when showing the spinner.
        # Re-appending to content_box instead of self
        self.remove(button_box)
        self.content_box.append(button_box)

        self.btn_back = Gtk.Button(label=_("Back"))
        self.btn_back.add_css_class('back_button')
        self.btn_back.set_size_request(140, 50)
        
        # Add hover effects to back button
        back_hover = Gtk.EventControllerMotion()
        back_hover.connect("enter", lambda c, x, y: self.btn_back.add_css_class("pulse-animation"))
        back_hover.connect("leave", lambda c: self.btn_back.remove_css_class("pulse-animation"))
        self.btn_back.add_controller(back_hover)
        
        button_box.append(self.btn_back)

        self.btn_proceed = Gtk.Button(label=_("Continue"))
        self.btn_proceed.add_css_class('suggested-action')
        self.btn_proceed.add_css_class('continue_button')
        self.btn_proceed.set_size_request(140, 50)
        
        # Add hover effects to continue button
        continue_hover = Gtk.EventControllerMotion()
        continue_hover.connect("enter", lambda c, x, y: self.btn_proceed.add_css_class("pulse-animation"))
        continue_hover.connect("leave", lambda c: self.btn_proceed.remove_css_class("pulse-animation"))
        self.btn_proceed.add_controller(continue_hover)
        
        self.btn_proceed.connect("clicked", self.on_continue_clicked)
        self.btn_proceed.set_sensitive(False)
        button_box.append(self.btn_proceed)

        # 2. Waiting View
        self._create_waiting_ui()

        # Initial Detection
        self._detect_partitions()
        self._create_partition_cards()

        get_localization_manager().update_widget_tree(self)

    def _create_waiting_ui(self):
        """Creates the UI shown while GParted is running"""
        waiting_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        waiting_box.set_halign(Gtk.Align.CENTER)
        waiting_box.set_valign(Gtk.Align.CENTER)
        
        spinner = Gtk.Spinner()
        spinner.set_size_request(64, 64)
        spinner.start()
        
        label = Gtk.Label(label=_("Waiting for partitioning tool..."))
        label.add_css_class("title-2")
        
        desc = Gtk.Label(label=_("The partition list will refresh automatically when you close Disks."))
        desc.add_css_class("dim-label")
        
        waiting_box.append(spinner)
        waiting_box.append(label)
        waiting_box.append(desc)
        
        self.view_stack.add_named(waiting_box, "waiting")

    def on_open_gparted_clicked(self, button=None):
        """
        Public method to be called by external buttons (e.g. from Installer headerbar).
        Launches GParted and shows waiting screen.
        """
        self.view_stack.set_visible_child_name("waiting")
        
        try:
            # Launch gparted asynchronously
            process = Gio.Subprocess.new(['gnome-disks'], Gio.SubprocessFlags.NONE)
            process.wait_check_async(None, self._on_gparted_closed)
        except GLib.Error as e:
            # Fallback if launch fails
            self.view_stack.set_visible_child_name("main")
            self._show_error_dialog(_("Error"), _("Could not launch GParted: {}").format(e.message))

    def _on_gparted_closed(self, process, result):
        """Callback when GParted closes"""
        try:
            process.wait_check_finish(result)
        except GLib.Error as e:
            print(f"GParted exited with error: {e}")
        finally:
            # Restore UI and refresh on the main thread
            GLib.idle_add(self._restore_and_refresh)

    def _restore_and_refresh(self):
        """Switch back to main view and refresh partitions"""
        self.refresh()
        self.view_stack.set_visible_child_name("main")

    def _on_map(self, widget):
        """Called when the widget becomes visible (mapped)"""
        # Only refresh if we are showing the main view
        if self.view_stack.get_visible_child_name() == "main":
            self.refresh()

    def refresh(self):
        """Refreshes the partition list and resets state"""
        # Clear existing cards
        child = self.partition_cards_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.partition_cards_box.remove(child)
            child = next_child

        # Reset state
        self.selected_template = None
        self.partitions = []
        self.selected_partition = None
        self.selected_partition = None
        self.selected_disk = None
        self.selected_disk_widget = None
        
        self.info_label.set_markup("")
        self.btn_proceed.set_sensitive(False)

        self._detect_partitions()
        self._create_partition_cards()

    def setup_css(self):
        """Setup CSS styling for buttons"""
        css_provider = Gtk.CssProvider()
        css_data = """
        .back_button {
            border-radius: 20px;
            font-weight: bold;
            font-size: 1em;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            text-shadow: 0 1px 2px rgba(0,0,0,0.1);
        }
        
        .back_button:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 15px alpha(@theme_bg_color, 0.3);
        }
        
        .back_button:active {
            transform: translateY(0px);
        }

        .continue_button {
            border-radius: 20px;
            font-weight: bold;
            font-size: 1em;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            text-shadow: 0 1px 2px rgba(0,0,0,0.1);
        }
        
        .continue_button:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 15px alpha(@accent_color, 0.3);
        }
        
        .continue_button:active {
            transform: translateY(0px);
        }
        
        @keyframes pulse {
            0% { transform: scale(1); }
            50% { transform: scale(1.05); }
            100% { transform: scale(1); }
        }
        
        .pulse-animation {
            animation: pulse 2s ease-in-out infinite;
        }
        """
        css_provider.load_from_data(css_data.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _detect_partitions(self):
        """Detect partitions, Free Space, and Whole Disks > 25GB"""
        self.partitions = []
        
        # Debug logging setup
        try:
            log_file = open("/tmp/installer_debug.log", "w")
            def log(msg):
                print(msg) # Still print to stdout for redundancy
                log_file.write(msg + "\n")
                log_file.flush()
        except Exception:
            def log(msg): print(msg)

        log("--- Starting Partition Detection ---")
        
        try:
            # 1. Standard Partition Detection (lsblk)
            # Added -b to get size in bytes directly
            cmd = ['lsblk', '-J', '-b', '-o', 'NAME,SIZE,FSTYPE,LABEL,MOUNTPOINT,TYPE,PKNAME,START']
            log(f"Running: {' '.join(cmd)}")
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            parent_disks = set()

            def _process_node(node, root_parent_disk):
                """Recursive helper to process partitions"""
                # If we encounter a disk at top level, track it
                if node.get('type') == 'disk':
                    disk_path = f"/dev/{node['name']}"
                    parent_disks.add(disk_path)
                    log(f"Found disk: {disk_path}")
                    if root_parent_disk is None:
                        root_parent_disk = disk_path
                    
                    # CHECK FOR WHOLE DISK (No partitions)
                    # If this disk has no children that are partitions, treat as raw disk
                    has_partitions = False
                    if 'children' in node:
                         for child in node['children']:
                             if child.get('type') == 'part':
                                 has_partitions = True
                                 break
                    
                    if not has_partitions:
                        # Process as Whole Disk
                        try:
                            size_bytes = int(node.get('size', 0))
                        except (ValueError, TypeError):
                            size_bytes = 0
                        
                        size_gb = size_bytes // (1024**3)
                        size_sectors = size_bytes // 512
                        

                        log(f"Checking Whole Disk {disk_path}: Size={size_gb}GB")
                        
                        log(f"  -> ACCEPTED Whole Disk {disk_path}")
                        self.partitions.append({
                            'type': 'wholedisk',
                            'device': disk_path,
                            'name': node['name'],
                            'display_name': _("Whole Disk ({})").format(node['name']),
                            'size_gb': size_gb,
                            'size_sectors': size_sectors,
                            'start_sector': 2048, # Default start for raw disk
                            'parent_disk': disk_path
                        })


                # If it is a partition, process it
                if node.get('type') == 'part':
                    part_path = f"/dev/{node['name']}"
                    
                    # Determine parent disk
                    parent_disk_path = root_parent_disk
                    if not parent_disk_path and node.get('pkname'):
                         parent_disk_path = f"/dev/{node['pkname']}"

                    # Get size directly from lsblk JSON
                    try:
                        size_bytes = int(node.get('size', 0))
                    except (ValueError, TypeError):
                        size_bytes = 0
                        
                    size_gb = size_bytes // (1024**3)
                    size_sectors = size_bytes // 512

                    log(f"Checking partition {part_path}: Size={size_gb}GB ({size_bytes} bytes), Parent={parent_disk_path}")

                    log(f"  -> ACCEPTED {part_path}")
                    self.partitions.append({
                        'type': 'partition',
                        'device': part_path,
                        'name': node['name'],
                        'display_name': node.get('label') or node.get('name'),
                        'size_gb': size_gb,
                        'size_sectors': size_sectors,
                        'start_sector': node.get('start'),
                        'parent_disk': parent_disk_path
                    })


                # Recurse into children
                if 'children' in node:
                    for child in node['children']:
                        _process_node(child, root_parent_disk)

            if process.returncode == 0:
                try:
                    data = json.loads(process.stdout)
                    for device in data.get('blockdevices', []):
                        _process_node(device, None)
                except json.JSONDecodeError as e:
                     log(f"JSON Decode Error: {e}")
                     log(f"Output: {process.stdout}")
            else:
                 log(f"lsblk failed: {process.stderr}")

            # 2. Free Space Detection (parted)
            for parent_disk in parent_disks:
                try:
                    log(f"Scanning free space on {parent_disk}")
                    # Output machine readable, unit sectors
                    p_cmd = ['sudo', 'parted', '-m', parent_disk, 'unit', 's', 'print', 'free']
                    p_proc = subprocess.run(p_cmd, capture_output=True, text=True)
                    
                    if p_proc.returncode == 0:
                        lines = p_proc.stdout.strip().splitlines()
                        for line in lines:
                            if not line.strip() or line.startswith('BYT;'): continue
                                
                            # Format: number:start:end:size:filesystem:name:flags;
                            parts = line.split(':')
                            if len(parts) > 4 and 'free' in parts[4]:
                                size_str = parts[3].replace('s', '')
                                start_str = parts[1].replace('s', '')
                                
                                try:
                                    size_sectors = int(size_str)
                                except ValueError:
                                    continue
                                    
                                size_gb = (size_sectors * 512) // (1024**3)
                                size_mb = (size_sectors * 512) // (1024**2)
                                
                                log(f"Checking Free Space on {parent_disk}: Size={size_gb}GB ({size_mb} MB)")

                                # Filter out tiny gaps (alignment issues), show only meaningful free space (>256MB)
                                if size_mb >= 256:
                                    log(f"  -> ACCEPTED Free Space")
                                    self.partitions.append({
                                        'type': 'freespace',
                                        'device': 'Unallocated Space',
                                        'name': 'Free Space',
                                        'display_name': _("Free Space"),
                                        'size_gb': size_gb,
                                        'size_sectors': size_sectors,
                                        'start_sector': start_str,
                                        'parent_disk': parent_disk
                                    })
                                else:
                                    log(f"  -> REJECTED Free Space (Too small: {size_mb} MB)")

                except Exception as e:
                    log(f"Failed to scan free space on {parent_disk}: {e}")

        except Exception as e:
            log(f"Error in detection: {e}")
            import traceback
            log(traceback.format_exc())
            
        try:
            log_file.close()
        except: pass

    def _create_partition_cards(self):
        if not self.partitions:
            return

        for partition in self.partitions:
            card_button = Gtk.Button()
            card_button.add_css_class('card')
            card_button.set_size_request(220, 200)

            overlay = Gtk.Overlay()
            card_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            card_box.set_valign(Gtk.Align.CENTER)

            icon_name = "drive-harddisk-symbolic"
            if partition.get('type') == 'freespace':
                icon_name = "list-add-symbolic"
            elif partition.get('type') == 'wholedisk':
                icon_name = "drive-harddisk-symbolic" # Use disk icon

            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_pixel_size(72)
            icon.set_halign(Gtk.Align.CENTER)
            if partition.get('type') == 'freespace':
                icon.set_opacity(0.5) # Dim the icon for free space
            card_box.append(icon)

            name_lbl = Gtk.Label(label=partition['display_name'])
            name_lbl.add_css_class('title-4')
            card_box.append(name_lbl)

            size_lbl = Gtk.Label(label=f"{partition['size_gb']} GB")
            size_lbl.add_css_class('dim-label')
            card_box.append(size_lbl)

            # Show "Available" instead of path for free space
            sub_text = partition['device'] 
            if partition['type'] == 'freespace':
                sub_text = _("Available for Install")
            elif partition['type'] == 'wholedisk':
                sub_text = _("Uninitialized Disk")
                
            path_lbl = Gtk.Label(label=sub_text)
            path_lbl.add_css_class('caption')
            card_box.append(path_lbl)

            overlay.set_child(card_box)

            check = Gtk.Image.new_from_icon_name("object-select-symbolic")
            check.set_halign(Gtk.Align.END)
            check.set_valign(Gtk.Align.START)
            check.set_margin_top(10)
            check.set_margin_end(10)
            check.set_opacity(0)
            overlay.add_overlay(check)

            card_button.set_child(overlay)
            card_button.partition_data = partition
            card_button.check_icon = check
            card_button.connect("clicked", self._on_partition_card_clicked)

            self.partition_cards_box.append(card_button)

    def _on_partition_card_clicked(self, button):
        if self.selected_disk_widget:
            self.selected_disk_widget.remove_css_class('suggested-action')
            self.selected_disk_widget.check_icon.set_opacity(0)

        button.add_css_class('suggested-action')
        button.check_icon.set_opacity(1)
        self.selected_disk_widget = button

        self.selected_partition = button.partition_data
        self.selected_disk = self.selected_partition['parent_disk']
        self.selected_template = "wipe"

        # Size Validation
        if self.selected_partition['size_gb'] < 25:
             msg = _("<span color='red'><b>Error: Partition is too small!</b></span>\nMinimum required size is 25GB.\nSelected size: {}GB").format(self.selected_partition['size_gb'])
             self.info_label.set_markup(msg)
             self.btn_proceed.set_sensitive(False)
             return

        boot_mode = self._detect_boot_mode()
        if boot_mode == "uefi":
            msg = _("Will split <b>{}</b> into:\n1. <b>EFI Boot</b> (512 MB)\n2. <b>Root</b> (Remaining space)").format(self.selected_partition['device'])
        else:
            msg = _("Will replace <b>{}</b> with:\n1. <b>Root</b> (Full available space, Bootable)").format(self.selected_partition['device'])

        self.info_label.set_markup(msg)
        self.btn_proceed.set_sensitive(True)

    def on_continue_clicked(self, btn):
        self.emit('template-selected', self.selected_template, {
            'template': 'wipe',
            'target_disk': self.selected_partition['device'],
            'parent_disk': self.selected_partition['parent_disk']
        })

    def execute_template(self, disk_utility_widget):
        """Starts the threading process for partitioning"""
        # Show the progress dialog immediately on the main thread
        self.progress_dialog = self._show_progress_dialog(_("Partitioning"), _("Preparing disk..."))
        
        # Start the heavy lifting in a separate thread
        thread = threading.Thread(target=self._split_and_format_partition_thread, args=(disk_utility_widget,))
        thread.daemon = True
        thread.start()
        return True

    def _detect_boot_mode(self):
        """Detect if the system is running in UEFI or Legacy mode"""
        try:
            if os.path.exists('/sys/firmware/efi'):
                return "uefi"
            else:
                return "legacy"
        except Exception:
            return "legacy"

    def _split_and_format_partition_thread(self, disk_utility_widget):
        """Background thread logic: Delete -> Create (Limited Size) -> Format"""
        try:
            boot_mode = self._detect_boot_mode()
            
            parent_disk = self.selected_partition['parent_disk']
            target_device = self.selected_partition['device']
            start_sector = int(self.selected_partition['start_sector'])
            
            # Retrieve the strict limit of the selected space
            total_sectors_available = int(self.selected_partition['size_sectors'])
            
            item_type = self.selected_partition.get('type', 'partition')

            print(f"Processing {item_type} on {parent_disk}")
            print(f"Start: {start_sector}, Size: {total_sectors_available} sectors")

            # --- STEP A: INITIALIZE DISK IF NEEDED ---
            if item_type == 'wholedisk':
                GLib.idle_add(self.progress_dialog.set_body, _("Initializing disk partition table..."))
                label_type = "gpt" if boot_mode == "uefi" else "msdos"
                
                # Create fresh partition table
                subprocess.run(['sudo', 'parted', '-s', parent_disk, 'mklabel', label_type], check=True)
                subprocess.run(['sudo', 'partprobe', parent_disk])
                time.sleep(1)
                
                # Start sector 2048 is safe for new tables
                start_sector = 2048
                # Adjust available sectors slightly to account for table overhead if needed, 
                # but sfdisk usually handles "size" relative to start well.

            # --- STEP B: CLEANUP (If it's an existing partition) ---
            if item_type == 'partition':
                GLib.idle_add(self.progress_dialog.set_body, _("Unmounting partition..."))
                subprocess.run(['sudo', 'umount', target_device], capture_output=True)
                subprocess.run(['sudo', 'umount', f"{target_device}*"], capture_output=True)
                subprocess.run(['sudo', 'swapoff', '-a'], capture_output=True)

                # Delete Old Partition
                part_num = None
                match = re.search(r'(\d+)$', target_device)
                if match: part_num = match.group(1)

                if part_num:
                    GLib.idle_add(self.progress_dialog.set_body, _("Removing old partition..."))
                    subprocess.run(['sudo', 'sfdisk', '--delete', parent_disk, part_num], check=True)
                    subprocess.run(['sudo', 'partprobe', parent_disk])
                    time.sleep(1)

            # --- STEP C: CREATION ---
            GLib.idle_add(self.progress_dialog.set_body, _("Creating new partitions..."))
            
            sfdisk_script = ""
            EFI_SIZE_SECTORS = 1048576 # 512MB
            
            if boot_mode == "uefi":
                # Calculate remaining space for Root
                root_size_sectors = total_sectors_available - EFI_SIZE_SECTORS
                # Account for start offset if we are on a fresh disk (total size is whole disk)
                if item_type == 'wholedisk':
                     # If whole disk, total_sectors_available is the DISK size. 
                     # We start at 2048. So we lose 2048 sectors.
                     root_size_sectors = total_sectors_available - EFI_SIZE_SECTORS - 2048 - 34 # approx overhead
                     
                
                # Safety check
                if root_size_sectors < 1000000: # Approx 500MB
                    raise Exception("Selected space is too small for EFI + Root.")

                root_start_sector = start_sector + EFI_SIZE_SECTORS
                
                # We specify explicit SIZE for root to stop it from grabbing extra free space
                sfdisk_script = (
                    f"start={start_sector}, size={EFI_SIZE_SECTORS}, type=U\n"
                    f"start={root_start_sector}, size={root_size_sectors}, type=L\n"
                )
            else:
                # Legacy: Use explicit size to stay within bounds
                current_size = total_sectors_available
                if item_type == 'wholedisk':
                    current_size = total_sectors_available - 2048
                
                sfdisk_script = (
                    f"start={start_sector}, size={current_size}, type=L\n"
                )

            # Use --force to ensure we can write to the gap exactly
            sfdisk_proc = subprocess.run(
                ['sudo', 'sfdisk', '--append', '--force', parent_disk],
                input=sfdisk_script,
                text=True,
                capture_output=True
            )

            if sfdisk_proc.returncode != 0:
                raise Exception(f"Partition creation failed: {sfdisk_proc.stderr}")

            # Sync
            GLib.idle_add(self.progress_dialog.set_body, _("Synchronizing disks..."))
            subprocess.run(['sudo', 'partprobe', parent_disk])
            subprocess.run(['sudo', 'udevadm', 'settle'], check=False)
            time.sleep(2) 

            # --- STEP C: IDENTIFICATION ---
            GLib.idle_add(self.progress_dialog.set_body, _("Verifying partitions..."))
            
            chk_cmd = ['sudo', 'sfdisk', '-l', '-o', 'DEVICE,START,TYPE', '-J', parent_disk]
            chk_proc = subprocess.run(chk_cmd, capture_output=True, text=True)
            part_table = json.loads(chk_proc.stdout)
            partitions = part_table.get('partitiontable', {}).get('partitions', [])
            
            new_efi_device = None
            new_root_device = None
            SECTOR_TOLERANCE = 8192 

            if boot_mode == "uefi":
                for p in partitions:
                    try:
                        p_start = int(p.get('start', -1))
                        p_node = p.get('node') or p.get('device')
                        if not p_node: continue

                        if abs(p_start - start_sector) < SECTOR_TOLERANCE:
                            new_efi_device = p_node
                        
                        expected_root = start_sector + EFI_SIZE_SECTORS
                        if abs(p_start - expected_root) < SECTOR_TOLERANCE:
                            new_root_device = p_node
                    except ValueError: continue
            else:
                for p in partitions:
                    try:
                        p_start = int(p.get('start', -1))
                        p_node = p.get('node') or p.get('device')
                        if p_node and abs(p_start - start_sector) < SECTOR_TOLERANCE:
                            new_root_device = p_node
                    except ValueError: continue
                
                if new_root_device:
                    new_num = ''.join(filter(str.isdigit, os.path.basename(new_root_device)))
                    subprocess.run(['sudo', 'parted', '-s', parent_disk, 'set', new_num, 'boot', 'on'], check=True)

            # Verification
            if boot_mode == "uefi" and (not new_efi_device or not new_root_device):
                raise Exception(f"Detection failed. EFI: {new_efi_device}, Root: {new_root_device}")
            elif boot_mode == "legacy" and not new_root_device:
                raise Exception("Detection failed for Root partition.")

            # --- STEP D: FORMATTING ---
            if boot_mode == "uefi":
                GLib.idle_add(self.progress_dialog.set_body, _("Formatting EFI partition..."))
                subprocess.run(['sudo', 'mkfs.vfat', '-F32', new_efi_device], check=True)

            GLib.idle_add(self.progress_dialog.set_body, _("Formatting Root partition..."))
            subprocess.run(['sudo', 'mkfs.ext4', '-F', new_root_device], check=True)

            # Final Settle
            GLib.idle_add(self.progress_dialog.set_body, _("Finalizing configuration..."))
            subprocess.run(['sudo', 'udevadm', 'settle'], check=False)
            time.sleep(1)

            # --- STEP E: CONFIG UPDATE ---
            disk_utility_widget.partition_config = {}
            if boot_mode == "uefi":
                disk_utility_widget.partition_config[new_efi_device] = {
                    'mountpoint': '/boot', 'bootable': True, 'filesystem': 'vfat'
                }
                disk_utility_widget.partition_config[new_root_device] = {
                    'mountpoint': '/', 'bootable': False, 'filesystem': 'ext4'
                }
            else:
                disk_utility_widget.partition_config[new_root_device] = {
                    'mountpoint': '/', 'bootable': True, 'filesystem': 'ext4'
                }

            disk_utility_widget.selected_disk = parent_disk

            print("Saving partition config and generating fstab...")
            disk_utility_widget._save_partition_config()
            disk_utility_widget._generate_and_apply_fstab()

            GLib.idle_add(self._finish_success)

        except Exception as e:
            print(f"CRITICAL ERROR: {e}")
            import traceback
            traceback.print_exc()
            GLib.idle_add(self._finish_error, str(e))

    def _finish_success(self):
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.close()
        self.emit('continue-to-next-page')

    def _finish_error(self, error_msg):
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.close()
        self._show_error_dialog(_("Partitioning Failed"), error_msg)

    def _show_progress_dialog(self, heading, message):
        dialog = Adw.MessageDialog(heading=heading, body=message, transient_for=self.get_root())
        spinner = Gtk.Spinner()
        spinner.start()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_halign(Gtk.Align.CENTER)
        box.append(spinner)
        box.append(Gtk.Label(label=_("Working...")))
        dialog.set_extra_child(box)
        dialog.present()
        return dialog

    def _show_error_dialog(self, heading, message):
        dialog = Adw.MessageDialog(heading=heading, body=message, transient_for=self.get_root())
        dialog.add_response("ok", "OK")
        dialog.present()

    # Compat properties
    @property
    def free_space_radio(self): return None
    @property
    def wipe_radio(self): return None
    @property
    def manual_radio(self): return None