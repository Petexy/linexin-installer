#!/usr/bin/env python
# -*- coding: utf-8 -*-

import gi
import os
import gettext
import locale
import socket
import urllib.request

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, Gdk, GLib


class DEPicker(Gtk.Box):

    def __init__(self, on_continue_callback=None, **kwargs):
        """
        Initialize the widget.
        
        Args:
            on_continue_callback: Optional callback function to call when Continue button is clicked
            **kwargs: Additional arguments passed to Gtk.Box
        """
        super().__init__(**kwargs)
        
        print("DEBUG: Starting two box selection widget")
        
        # Store callback
        self.on_continue_callback = on_continue_callback
        self.selected_option = 0  # Default to first box
        self.animation_played = False  
        
        # Check internet connectivity
        self.has_internet = self.check_internet_connection()
        print(f"DEBUG: Internet connection status: {self.has_internet}")
        
        # Basic widget setup - reduced margins and spacing
        self.set_orientation(Gtk.Orientation.VERTICAL)
        self.set_spacing(20)
        self.set_margin_top(25)
        self.set_margin_bottom(25)
        self.set_margin_start(40)
        self.set_margin_end(40)
        
        # Setup CSS first
        self.setup_css()
        
        # Title - smaller font
        title = Gtk.Label()
        title.set_markup('<span size="x-large" weight="bold">Choose Your Option</span>')
        title.set_halign(Gtk.Align.CENTER)
        title.set_margin_bottom(10)
        self.append(title)
        
        # Get script directory for icons
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Define the two options
        self.options = [
            {
                "name": "Linexin (Current one)",
                "description": "GNOME-based desktop interface",
                "icon": "screen1.png",
                "requires_internet": False
            },
            {
                "name": "Kinexin",
                "description": "Plasma-based desktop interface",
                "icon": "screen2.png",
                "requires_internet": True
            }
        ]
        
        # Create options container - reduced spacing
        options_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        options_container.set_halign(Gtk.Align.CENTER)
        options_container.set_homogeneous(True)
        
        self.option_boxes = []
        
        # Create the two option boxes
        for i, option in enumerate(self.options):
            option_box = self.create_option_box(option, i, script_dir)
            options_container.append(option_box)
            self.option_boxes.append(option_box)
        
        self.append(options_container)
        
        # Set first box as selected by default
        self.update_selection(0)
        
        navigation_btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        navigation_btns.set_halign(Gtk.Align.CENTER)
        navigation_btns.set_margin_top(15)

        # Continue button - smaller
        self.continue_btn = Gtk.Button()
        self.continue_btn.set_label("Continue")
        self.continue_btn.add_css_class("suggested-action")
        self.continue_btn.add_css_class("continue_button")
        self.continue_btn.set_size_request(160, 40)
        self.continue_btn.set_halign(Gtk.Align.CENTER)
        self.continue_btn.set_margin_end(10)
        self.continue_btn.set_margin_top(10)
        self.continue_btn.connect("clicked", self.on_continue_clicked)
        

        self.back_btn = Gtk.Button()
        self.back_btn.set_label("Back")
        self.back_btn.add_css_class("back_button")
        self.back_btn.set_size_request(160, 40)
        self.back_btn.set_halign(Gtk.Align.CENTER)
        self.back_btn.set_margin_top(10)
        self.back_btn.set_margin_end(10)
        self.back_btn.connect("clicked", self.on_continue_clicked)
        
        # Add hover effects to continue button
        continue_hover = Gtk.EventControllerMotion()
        continue_hover.connect("enter", lambda c, x, y: self.continue_btn.add_css_class("pulse-animation"))
        continue_hover.connect("leave", lambda c: self.continue_btn.remove_css_class("pulse-animation"))
        self.continue_btn.add_controller(continue_hover)
        
        # Add hover effects to back button
        back_hover = Gtk.EventControllerMotion()
        back_hover.connect("enter", lambda c, x, y: self.back_btn.add_css_class("pulse-animation"))
        back_hover.connect("leave", lambda c: self.back_btn.remove_css_class("pulse-animation"))
        self.back_btn.add_controller(back_hover)

        navigation_btns.append(self.back_btn)
        navigation_btns.append(self.continue_btn)
        self.append(navigation_btns)
        
        # Animation setup
        self.set_opacity(0)
        self.connect("map", self.on_widget_mapped)
        
        print("DEBUG: Two box selection widget initialization complete")
    
    def check_internet_connection(self):
        """Check if internet connection is available"""
        # Try multiple methods to check connectivity
        
        # Method 1: Check if we can resolve a DNS name
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            print("DEBUG: Internet check via DNS succeeded")
            return True
        except (socket.error, socket.timeout):
            print("DEBUG: Internet check via DNS failed")
        
        # Method 2: Try to open a connection to a reliable host
        try:
            urllib.request.urlopen('http://clients3.google.com/generate_204', timeout=3)
            print("DEBUG: Internet check via HTTP succeeded")
            return True
        except:
            print("DEBUG: Internet check via HTTP failed")
        
        print("DEBUG: No internet connection detected")
        return False
    
    def create_option_box(self, option, index, script_dir):
        """Create a single selectable option box with smaller image"""
        
        # Check if this option requires internet and we don't have it
        is_disabled = option.get("requires_internet", False) and not self.has_internet
        
        # Main container - smaller dimensions
        main_box = Gtk.Button()
        main_box.add_css_class("option_box")
        main_box.set_size_request(240, 320)
        
        if is_disabled:
            main_box.add_css_class("disabled")
            main_box.set_sensitive(False)
        else:
            main_box.connect("clicked", lambda btn, idx=index: self.on_option_selected(idx))
        
        # Content container - reduced spacing
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content_box.set_margin_top(20)
        content_box.set_margin_bottom(20)
        content_box.set_margin_start(15)
        content_box.set_margin_end(15)
        
        # Icon container with smaller size
        icon_container = Gtk.Box()
        icon_container.set_size_request(210, 210)
        icon_container.set_halign(Gtk.Align.CENTER)
        icon_container.set_valign(Gtk.Align.CENTER)
        
        # Try to load icon
        icon_loaded = False
        icon_paths = [
            os.path.join(script_dir, option["icon"]),
            os.path.join(script_dir, "images", option["icon"])
        ]
        
        for path in icon_paths:
            print(f"DEBUG: Checking for icon at {path}")
            if os.path.isfile(path) and os.access(path, os.R_OK):
                try:
                    # Load with Gdk.Texture for validation
                    texture = Gdk.Texture.new_from_filename(path)
                    icon = Gtk.Picture.new_for_paintable(texture)
                    icon.set_content_fit(Gtk.ContentFit.CONTAIN)
                    icon.set_size_request(210, 210)
                    icon.add_css_class("option_icon_image")
                    if is_disabled:
                        icon.add_css_class("disabled_icon")
                    icon_container.append(icon)
                    icon_loaded = True
                    print(f"DEBUG: Loaded icon for {option['name']}: {path}")
                    break
                except Exception as e:
                    print(f"DEBUG: Failed to load {path}: {str(e)}")
            else:
                print(f"DEBUG: Path {path} does not exist or is not readable")
        
        if not icon_loaded:
            # Fallback icon - smaller
            fallback = Gtk.Box()
            fallback.set_size_request(210, 210)
            fallback.add_css_class("large_fallback_icon")
            if is_disabled:
                fallback.add_css_class("disabled_icon")
            
            # Add some text to the fallback
            fallback_label = Gtk.Label()
            fallback_label.set_text("📦" if index == 0 else "💼")
            fallback_label.add_css_class("fallback_emoji")
            fallback.set_halign(Gtk.Align.CENTER)
            fallback.set_valign(Gtk.Align.CENTER)
            
            overlay = Gtk.Overlay()
            overlay.set_child(fallback)
            overlay.add_overlay(fallback_label)
            
            icon_container.append(overlay)
            print(f"DEBUG: Using fallback icon for {option['name']}")
        
        content_box.append(icon_container)
        
        # Option name - smaller font
        name_label = Gtk.Label()
        name_label.set_markup(f'<span weight="bold" size="large">{option["name"]}</span>')
        name_label.set_halign(Gtk.Align.CENTER)
        name_label.set_wrap(True)
        name_label.set_justify(Gtk.Justification.CENTER)
        if is_disabled:
            name_label.add_css_class("disabled_text")
        content_box.append(name_label)
        
        # Option description - smaller font
        desc_label = Gtk.Label()
        desc_label.set_text(option["description"])
        desc_label.set_halign(Gtk.Align.CENTER)
        desc_label.set_wrap(True)
        desc_label.set_justify(Gtk.Justification.CENTER)
        desc_label.add_css_class("option_description")
        if is_disabled:
            desc_label.add_css_class("disabled_text")
        content_box.append(desc_label)
        
        # Add internet requirement notice if disabled
        if is_disabled:
            notice_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            notice_box.set_halign(Gtk.Align.CENTER)
            notice_box.set_margin_top(5)
            
            # Warning icon
            warning_icon = Gtk.Label()
            warning_icon.set_text("⚠️")
            notice_box.append(warning_icon)
            
            notice_label = Gtk.Label()
            notice_label.set_markup('<span size="small" weight="bold">Requires Internet</span>')
            notice_label.add_css_class("internet_notice")
            notice_box.append(notice_label)
            
            content_box.append(notice_box)
        
        main_box.set_child(content_box)
        
        # Store index for reference
        main_box.option_index = index
        main_box.is_disabled = is_disabled
        
        return main_box
    
    def on_option_selected(self, index):
        """Handle option selection"""
        # Check if the option is available
        option = self.options[index]
        if option.get("requires_internet", False) and not self.has_internet:
            print(f"DEBUG: Cannot select {option['name']} - no internet connection")
            return
        
        print(f"DEBUG: Option {index} selected: {option['name']}")
        self.selected_option = index
        self.update_selection(index)
    
    def update_selection(self, selected_index):
        """Update visual selection state"""
        for i, box in enumerate(self.option_boxes):
            if hasattr(box, 'is_disabled') and box.is_disabled:
                # Keep disabled state
                continue
                
            if i == selected_index:
                box.add_css_class("selected")
                box.remove_css_class("unselected")
                print(f"DEBUG: Marked box {i} as selected")
            else:
                box.add_css_class("unselected")
                box.remove_css_class("selected")
                print(f"DEBUG: Marked box {i} as unselected")
    
    def on_continue_clicked(self, button):
        """Handle continue button click"""
        selected_option = self.options[self.selected_option]
        print(f"DEBUG: Continue clicked with selection: {selected_option['name']}")
        
        # Write selection to file
        self.write_selection_to_file()
        
        if self.on_continue_callback:
            # Pass the selected option to the callback
            self.on_continue_callback(self.selected_option, selected_option)
        else:
            print("DEBUG: No continue callback provided")
    
    def write_selection_to_file(self):
        """Write the selected option index"""
        config_dir = "/tmp/installer_config"
        config_file = os.path.join(config_dir, "de_selection")
        
        try:
            # Check if we have write permission to the directory
            if os.path.exists(config_dir):
                can_write = os.access(config_dir, os.W_OK)
            else:
                # Check if we can write to parent directory
                can_write = os.access(os.path.dirname(config_dir), os.W_OK)
            
            if can_write:
                # We have permission, write directly
                os.makedirs(config_dir, exist_ok=True)
                with open(config_file, 'w') as f:
                    f.write(str(self.selected_option))
                print(f"DEBUG: Wrote selection index {self.selected_option} to {config_file}")
            else:
                # Need elevated privileges, use pkexec
                print("DEBUG: Elevated privileges required, using pkexec")
                self.write_selection_with_pkexec(config_dir, config_file)
            
        except Exception as e:
            print(f"ERROR: Failed to write selection to file: {e}")
            # Try with pkexec as fallback
            try:
                self.write_selection_with_pkexec(config_dir, config_file)
            except Exception as e2:
                print(f"ERROR: Fallback with pkexec also failed: {e2}")
    
    def write_selection_with_pkexec(self, config_dir, config_file):
        """Write selection file using pkexec for elevated privileges"""
        import subprocess
        
        # Create a temporary script to execute with elevated privileges
        script_content = f"""#!/bin/bash
mkdir -p "{config_dir}"
echo "{self.selected_option}" > "{config_file}"
chmod 644 "{config_file}"
"""
        
        # Write temp script
        temp_script = "/tmp/de_selection_writer.sh"
        with open(temp_script, 'w') as f:
            f.write(script_content)
        os.chmod(temp_script, 0o755)
        
        try:
            # Execute with pkexec
            result = subprocess.run(
                ['pkexec', 'bash', temp_script],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                print(f"DEBUG: Successfully wrote selection index {self.selected_option} to {config_file} using pkexec")
            else:
                print(f"ERROR: pkexec failed with return code {result.returncode}")
                print(f"STDERR: {result.stderr}")
                raise Exception(f"pkexec failed: {result.stderr}")
        finally:
            # Clean up temp script
            try:
                os.remove(temp_script)
            except:
                pass
    
    def get_selected_option(self):
        """Get the currently selected option"""
        return self.selected_option, self.options[self.selected_option]
    
    def on_widget_mapped(self, widget):
        """Start entrance animation"""
        if not self.animation_played:
            GLib.timeout_add(200, self.start_animation)
            self.animation_played = True
    
    def start_animation(self):
        """Fade in animation"""
        def animate(value, data):
            self.set_opacity(value)
        
        target = Adw.CallbackAnimationTarget.new(animate, None)
        animation = Adw.TimedAnimation.new(self, 0.0, 1.0, 1200, target)
        animation.set_easing(Adw.Easing.EASE_OUT_QUAD)
        animation.play()
        return False
    
    def setup_css(self):
        """Setup CSS styling"""
        css_provider = Gtk.CssProvider()
        css_data = """
        .option_box {
            background: @theme_base_color;
            border: 2px solid rgba(0,0,0,0.1);
            border-radius: 12px;
            margin: 8px;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 3px 10px rgba(0,0,0,0.1);
        }
        
        .option_box:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(0,0,0,0.15);
            background: alpha(@theme_base_color, 0.95);
        }
        
        .option_box.selected {
            border-color: @accent_color;
            background: alpha(@accent_color, 0.1);
            transform: scale(1.02);
            box-shadow: 0 6px 25px alpha(@accent_color, 0.3);
        }
        
        .option_box.selected:hover {
            transform: scale(1.02) translateY(-2px);
        }
        
        .option_box.unselected {
            opacity: 0.8;
        }
        
        .option_box.unselected:hover {
            opacity: 1.0;
        }
        
        .option_box.disabled {
            opacity: 0.5;
            background: alpha(@theme_base_color, 0.7);
            border-color: rgba(0,0,0,0.05);
            cursor: not-allowed;
        }
        
        .option_box.disabled:hover {
            transform: none;
            box-shadow: 0 3px 10px rgba(0,0,0,0.1);
        }
        
        .disabled_icon {
            opacity: 0.4;
            filter: grayscale(100%);
        }
        
        .disabled_text {
            opacity: 0.6;
        }
        
        .internet_notice {
            color: @warning_color;
            opacity: 1.0;
        }
        
        .large_fallback_icon {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 12px;
            transition: all 0.3s ease;
        }
        
        .option_icon_image {
            border-radius: 12px;
            transition: all 0.3s ease;
        }
        
        .option_icon_image:hover, .large_fallback_icon:hover {
            transform: scale(1.05);
        }
        
        .fallback_emoji {
            font-size: 96px;
            color: white;
            text-shadow: 0 2px 4px rgba(0,0,0,0.3);
        }
        
        .option_description {
            color: alpha(@theme_fg_color, 0.8);
            font-size: 0.95em;
            text-shadow: 0 1px 2px rgba(0,0,0,0.05);
        }
        
        .option_details {
            color: alpha(@theme_fg_color, 0.6);
            text-shadow: 0 1px 2px rgba(0,0,0,0.05);
        }
        
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
        
        label {
            text-shadow: 0 1px 2px rgba(0,0,0,0.05);
        }
        """
        
        css_provider.load_from_data(css_data.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )


