#!/usr/bin/env python3
import os
import gi
import subprocess
import locale
import gettext

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gdk
from simple_localization_manager import get_localization_manager

# --- Localization Setup ---
APP_NAME = "linexin-installer"
LOCALE_DIR = os.path.abspath("/usr/share/locale")

# Set initial language (will default to system language if not specified)
locale.setlocale(locale.LC_ALL, '')
locale.bindtextdomain(APP_NAME, LOCALE_DIR)
gettext.textdomain(APP_NAME)
_ = gettext.gettext

class KeyboardLayoutWidget(Gtk.Box):
    """
    A GTK widget for selecting a system keyboard layout, with layouts
    grouped by language in expandable rows. Includes live preview and a test area.
    This version correctly uses `localectl` as per Arch Linux documentation.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        

        get_localization_manager().register_widget(self)

        self.set_orientation(Gtk.Orientation.VERTICAL)
        self.set_spacing(20)
        self.set_margin_top(30)
        self.set_margin_bottom(30)
 
        # Setup CSS
        self.setup_css()
        
        # A list to hold the top-level expander rows for filtering
        # A list to hold the top-level expander rows for filtering
        self.expander_rows = []
        self.selected_row = None

        # --- UI Elements ---
        self.title = Gtk.Label()
        self.title.set_markup('<span size="xx-large" weight="bold">' + _("Select Your Keyboard Layout") + '</span>')
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
        label=_("You can add more after installation."),
        halign=Gtk.Align.CENTER
        )
        self.subtitle.add_css_class('dim-label')
        content_box.append(self.subtitle)

        self.search_entry = Gtk.SearchEntry()
        content_box.append(self.search_entry)
        
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_has_frame(True)
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_vexpand(True)
        content_box.append(scrolled_window)

        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.get_style_context().add_class("boxed-list")
        scrolled_window.set_child(self.list_box)

        # --- Test Area ---
        test_area_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=15)
        self.test_label = Gtk.Label(xalign=0, label="Test your layout here:")
        self.test_label.add_css_class('dim-label')
        self.test_entry = Gtk.Entry()
        test_area_box.append(self.test_label)
        test_area_box.append(self.test_entry)
        content_box.append(test_area_box)

        # --- Navigation Buttons ---
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        button_box.set_halign(Gtk.Align.CENTER)
        self.append(button_box)

        self.btn_back = Gtk.Button(label="Back")
        self.btn_back.add_css_class('back_button')
        self.btn_back.set_size_request(140, 50)
        
        # Add hover effects to back button
        back_hover = Gtk.EventControllerMotion()
        back_hover.connect("enter", lambda c, x, y: self.btn_back.add_css_class("pulse-animation"))
        back_hover.connect("leave", lambda c: self.btn_back.remove_css_class("pulse-animation"))
        self.btn_back.add_controller(back_hover)
        
        self.btn_proceed = Gtk.Button(label="Continue")
        self.btn_proceed.add_css_class('suggested-action')
        self.btn_proceed.add_css_class('continue_button')
        self.btn_proceed.set_size_request(140, 50)
        self.btn_proceed.set_sensitive(False)
        self.btn_proceed.connect("clicked", self.on_continue_clicked)
        
        # Add hover effects to continue button
        continue_hover = Gtk.EventControllerMotion()
        continue_hover.connect("enter", lambda c, x, y: self.btn_proceed.add_css_class("pulse-animation"))
        continue_hover.connect("leave", lambda c: self.btn_proceed.remove_css_class("pulse-animation"))
        self.btn_proceed.add_controller(continue_hover)

        button_box.append(self.btn_back)
        button_box.append(self.btn_proceed)

        # --- Connect signals ---
        self.search_entry.connect("search-changed", self.on_search_changed)
        
        # --- Initial Population and Text ---
        self.populate_layouts()

    def country_code_to_emoji(self, country_code):
        """Converts a two-letter country code to a flag emoji."""
        if len(country_code) != 2:
            return "" # Return empty string for invalid codes
        
        return "".join(chr(ord(char) - ord('A') + 0x1F1E6) for char in country_code.upper())

    def _group_layouts(self, keymaps):
        """Groups a flat list of console keymaps into a dictionary by language."""
        groups = {
            "English": [], "German": [], "French": [], "Spanish": [], "Russian": [],
            "Portuguese": [], "Polish": [], "Italian": [], "Swedish": [], "Norwegian": [],
            "Danish": [], "Finnish": [], "Dutch": [], "Czech": [], "Slovak": [],
            "Hungarian": [], "Romanian": [], "Bulgarian": [], "Greek": [],
            "Turkish": [], "Ukrainian": [], "Serbian": [], "Croatian": [], "Slovenian": [],
            "Ergonomic / Special": [], "Other": []
        }
        
        prefix_map = {
            'us': "English", 'gb': "English", 'uk': "English", 'ie': "English",
            'de': "German",
            'fr': "French", 'be': "French", 'ca': "French",
            'es': "Spanish", 'la-latin1': "Spanish",
            'ru': "Russian",
            'pt': "Portuguese", 'br': "Portuguese",
            'pl': "Polish",
            'it': "Italian",
            'sv': "Swedish", 'se': "Swedish",
            'no': "Norwegian",
            'dk': "Danish",
            'fi': "Finnish",
            'nl': "Dutch",
            'cz': "Czech",
            'sk': "Slovak",
            'hu': "Hungarian",
            'ro': "Romanian",
            'bg': "Bulgarian",
            'gr': "Greek",
            'tr': "Turkish",
            'ua': "Ukrainian", 'by': "Ukrainian",
            'sr': "Serbian", 'rs': "Serbian",
            'hr': "Croatian", 'croat': "Croatian",
            'slovene': "Slovenian", 'si': "Slovenian",
            'dvorak': "Ergonomic / Special", 'colemak': "Ergonomic / Special",
        }

        for keymap in keymaps:
            found = False
            # Check for two-letter codes first for better accuracy
            if len(keymap) >= 2:
                prefix_2 = keymap[:2]
                if prefix_2 in prefix_map:
                    groups[prefix_map[prefix_2]].append(keymap)
                    continue
            
            # Fallback to general prefix matching
            for prefix, group_name in prefix_map.items():
                if keymap.startswith(prefix):
                    groups[group_name].append(keymap)
                    found = True
                    break
            if not found:
                groups["Other"].append(keymap)
        
        return {k: sorted(v) for k, v in sorted(groups.items()) if v}

    def populate_layouts(self):
        """Fetches console keymaps, groups them, and populates the ListBox with flags."""
        try:
            result = subprocess.run(
                ['localectl', 'list-keymaps'], 
                capture_output=True, 
                text=True, 
                check=True
            )
            keymaps = result.stdout.strip().split('\n')
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"Error getting keymaps with `localectl`: {e}. Using fallback.")
            keymaps = ["us", "pl", "de", "fr", "es", "dvorak"]
        
        grouped_layouts = self._group_layouts(keymaps)

        # --- Map group names to a representative country code for the flag ---
        group_to_flag_map = {
            "English": "US", "German": "DE", "French": "FR", "Spanish": "ES",
            "Russian": "RU", "Portuguese": "PT", "Polish": "PL", "Italian": "IT",
            "Swedish": "SE", "Norwegian": "NO", "Danish": "DK", "Finnish": "FI",
            "Dutch": "NL", "Czech": "CZ", "Slovak": "SK", "Hungarian": "HU",
            "Romanian": "RO", "Bulgarian": "BG", "Greek": "GR", "Turkish": "TR",
            "Ukrainian": "UA", "Serbian": "RS", "Croatian": "HR", "Slovenian": "SI",
            "Ergonomic / Special": "⌨️", "Other": "🌐"
        }

        for group_name, layouts in grouped_layouts.items():
            flag_code = group_to_flag_map.get(group_name, "🏳️")
            # Check if the code is an emoji already or needs conversion
            flag_emoji = flag_code if len(flag_code) > 2 else self.country_code_to_emoji(flag_code)
            
            expander = Adw.ExpanderRow(title=f"{flag_emoji} {group_name}")
            self.list_box.append(expander)
            
            nested_list_box = Gtk.ListBox()
            nested_list_box.get_style_context().add_class("boxed-list")
            nested_list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
            nested_list_box.connect("row-selected", self.on_row_selected)
            expander.add_row(nested_list_box)
            
            expander.child_rows = []
            for code in layouts:
                row = Gtk.ListBoxRow()
                label = Gtk.Label(label=code, xalign=0, margin_start=20)
                row.set_child(label)
                row.layout_code = code
                row.search_term = f"{group_name.lower()} {code.lower()}"
                nested_list_box.append(row)
                expander.child_rows.append(row)
            
            self.expander_rows.append(expander)

    def _set_keyboard_layout_live(self, keymap):
        """
        Sets the keyboard layout for the CURRENT GRAPHICAL SESSION ONLY.
        """
        if not keymap:
            return
        
        print(f"Attempting to set live session keyboard layout to: {keymap}")
        try:
            # This gsettings command works for GNOME and some other desktops.
            gsettings_value = f"[('xkb', '{keymap}')]"
            subprocess.run(
                ['gsettings', 'set', 'org.gnome.desktop.input-sources', 'sources', gsettings_value],
                check=True, capture_output=True, text=True
            )
            print(f"Successfully set live session keyboard layout to {keymap}")
            self.keymap_code = keymap
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"Info: Could not set live layout using gsettings (expected on non-GNOME desktops). Error: {e}")

    def save_vconsole_config(self):
        """Save the selected keyboard layout to /tmp/installer_config/etc/vconsole.conf"""
        selected_layout = self.get_selected_layout()
        if not selected_layout:
            return False
        
        try:
            import os
            
            # Create directory structure in /tmp/installer_config/etc/
            etc_dir = "/tmp/installer_config/etc"
            os.makedirs(etc_dir, exist_ok=True)
            
            # Create vconsole.conf content
            # KEYMAP is the console keyboard layout
            # FONT is optional but we'll set a reasonable default
            vconsole_content = [
                f"KEYMAP={selected_layout}",
                "FONT=ter-v16n",  # Terminus font, good for console
                "FONT_MAP="
            ]
            
            # Save vconsole.conf to /tmp/installer_config/etc/
            vconsole_path = os.path.join(etc_dir, "vconsole.conf")
            
            with open(vconsole_path, 'w') as f:
                f.write('\n'.join(vconsole_content) + '\n')
            
            print(f"Console keyboard configuration saved to: {vconsole_path}")
            
            # Also create X11 keyboard configuration for graphical environments
            self.save_x11_keyboard_config(selected_layout)
            
            return True
            
        except Exception as e:
            print(f"Error saving vconsole configuration: {e}")
            return False


    def save_x11_keyboard_config(self, layout_code):
        """Save X11 keyboard configuration for graphical environments"""
        try:
            import os
            
            # Create X11 config directory
            x11_dir = "/tmp/installer_config/etc/X11/xorg.conf.d"
            os.makedirs(x11_dir, exist_ok=True)
            
            # Convert console keymap to X11 layout if needed
            # This is a simplified mapping - you might need to expand this
            x11_layout = layout_code
            x11_variant = ""
            
            # Handle special cases
            if layout_code == "uk":
                x11_layout = "gb"
            elif layout_code == "dvorak":
                x11_layout = "us"
                x11_variant = "dvorak"
            elif layout_code == "colemak":
                x11_layout = "us"
                x11_variant = "colemak"
            elif "-" in layout_code:
                # Handle layouts like "de-latin1"
                x11_layout = layout_code.split("-")[0]
            
            # Create 00-keyboard.conf for X11
            x11_config = f"""Section "InputClass"
        Identifier "system-keyboard"
        MatchIsKeyboard "on"
        Option "XkbLayout" "{x11_layout}"
        Option "XkbVariant" "{x11_variant}"
    EndSection
    """
            
            x11_config_path = os.path.join(x11_dir, "00-keyboard.conf")
            with open(x11_config_path, 'w') as f:
                f.write(x11_config)
            
            print(f"X11 keyboard configuration saved to: {x11_config_path}")
            
            return True
            
        except Exception as e:
            print(f"Error saving X11 keyboard configuration: {e}")
            return False

    def on_search_changed(self, entry):
        """Filters the list based on user input, showing and expanding relevant groups."""
        search_text = entry.get_text().lower()
        
        for expander in self.expander_rows:
            visible_children = 0
            for row in expander.child_rows:
                is_visible = search_text in row.search_term
                row.set_visible(is_visible)
                if is_visible:
                    visible_children += 1
            
            expander.set_visible(visible_children > 0)
            if search_text:
                expander.set_expanded(visible_children > 0)

    def on_row_selected(self, listbox, row):
        """Updated to save keyboard config when a layout is selected"""
        if self.selected_row and self.selected_row != row:
            if self.selected_row.get_parent() != listbox:
                self.selected_row.get_parent().unselect_row(self.selected_row)

        self.selected_row = row
        self.btn_proceed.set_sensitive(row is not None)
        
        if row:
            self._set_keyboard_layout_live(row.layout_code)
            self.test_entry.grab_focus()
            # Save keyboard configuration when a layout is selected
            self.save_vconsole_config()


    def create_keyboard_install_script(self, layout_code):
        """Create a script that the installer can run to set up keyboard layout"""
        try:
            import os
            
            installer_dir = "/tmp/installer_config"
            os.makedirs(installer_dir, exist_ok=True)
            
            script_path = os.path.join(installer_dir, "setup_keyboard.sh")
            
            script_content = f"""#!/bin/bash
    # Keyboard layout setup script generated by Linexin Installer
    # Generated layout: {layout_code}

    CHROOT_DIR="${{1:-}}"

    if [ -n "$CHROOT_DIR" ]; then
        echo "Setting keyboard layout to {layout_code} in $CHROOT_DIR"
        
        # Copy vconsole.conf
        cp /tmp/installer_config/etc/vconsole.conf "$CHROOT_DIR/etc/vconsole.conf"
        
        # Copy X11 configuration if it exists
        if [ -f /tmp/installer_config/etc/X11/xorg.conf.d/00-keyboard.conf ]; then
            mkdir -p "$CHROOT_DIR/etc/X11/xorg.conf.d"
            cp /tmp/installer_config/etc/X11/xorg.conf.d/00-keyboard.conf "$CHROOT_DIR/etc/X11/xorg.conf.d/"
        fi
        
        # Set keyboard layout for the installed system using systemd
        if [ -f "$CHROOT_DIR/usr/bin/localectl" ]; then
            chroot "$CHROOT_DIR" localectl set-keymap {layout_code} 2>/dev/null || true
        fi
    else
        echo "Setting keyboard layout to {layout_code} on current system"
        
        # For live system
        sudo loadkeys {layout_code}
        
        # Set using localectl if available
        if command -v localectl &> /dev/null; then
            sudo localectl set-keymap {layout_code}
        fi
    fi

    echo "Keyboard layout configuration completed successfully!"
    """
            
            with open(script_path, 'w') as f:
                f.write(script_content)
            
            os.chmod(script_path, 0o755)
            
            print(f"Keyboard setup script created at: {script_path}")
            return True
            
        except Exception as e:
            print(f"Error creating keyboard setup script: {e}")
            return False


    def on_row_selected(self, listbox, row):
        """Updated to save keyboard config when a layout is selected"""
        if self.selected_row and self.selected_row != row:
            if self.selected_row.get_parent() != listbox:
                self.selected_row.get_parent().unselect_row(self.selected_row)

        self.selected_row = row
        self.btn_proceed.set_sensitive(row is not None)
        
        if row:
            self._set_keyboard_layout_live(row.layout_code)
            self.test_entry.grab_focus()
            # Save keyboard configuration when a layout is selected
            self.save_vconsole_config()


    def on_continue_clicked(self, button):
        """Handle the Continue button click"""
        if self.save_vconsole_config():
            selected_layout = self.get_selected_layout()
            print(f"Keyboard configuration saved for layout: {selected_layout}")
            # Also create the installation script
            self.create_keyboard_install_script(selected_layout)
            # You can add navigation to the next widget here
        else:
            print("Failed to save keyboard configuration")

    def get_vconsole_config_path(self):
        """Get the path to the generated vconsole.conf file"""
        return "/tmp/installer_config/etc/vconsole.conf"

    def get_selected_layout(self):
        """Public method to get the selected layout code for persistent setting."""
        if self.selected_row:
            print(self.selected_row.layout_code)
            return self.selected_row.layout_code
        return None

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
        # Use Gdk.Display.get_default() via import or context
        display = Gtk.Widget.get_display(self) if hasattr(self, 'get_display') else Gdk.Display.get_default()
        if display:
             Gtk.StyleContext.add_provider_for_display(
                display,
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
        else:
             # Fallback if display not yet available (rare in init but possible)
             pass

