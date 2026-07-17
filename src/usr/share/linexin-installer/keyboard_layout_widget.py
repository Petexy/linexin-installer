#!/usr/bin/env python3
import os
import gi
import subprocess
import locale
import gettext
import xml.etree.ElementTree as ET

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

# The X11/xkb rules database is the canonical source of *normalized*, human
# readable layout names (e.g. "English (US)", "Polish (QWERTZ)"). We read the
# layouts, their variants and the associated country from it so the widget can
# show names a person actually recognizes instead of raw console keymap codes.
XKB_RULES_FILES = [
    "/usr/share/X11/xkb/rules/evdev.xml",
    "/usr/share/X11/xkb/rules/base.xml",
]
# systemd's table mapping console keymaps <-> xkb layout/variant. Used to pick a
# sensible /etc/vconsole.conf KEYMAP for the TTY from the chosen xkb layout.
KBD_MODEL_MAP = "/usr/share/systemd/kbd-model-map"


class KeyboardLayoutWidget(Gtk.Box):
    """
    A GTK widget for selecting a system keyboard layout. Layouts are read from
    the X11/xkb database so every entry has a proper, normalized name, grouped
    by layout in expandable rows with their named variants. Includes a live
    preview and a test area.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


        get_localization_manager().register_widget(self)

        self.set_orientation(Gtk.Orientation.VERTICAL)
        self.set_spacing(20)
        self.set_margin_top(15)
        self.set_margin_bottom(15)

        # Setup CSS
        self.setup_css()

        # A list to hold the top-level expander rows for filtering
        self.expander_rows = []
        self.selected_row = None
        # Currently selected xkb layout/variant (e.g. "pl" / "dvorak").
        self.selected_layout = None
        self.selected_variant = None

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

        # Console keymap lookup table for deriving vconsole.conf's KEYMAP.
        self._keymap_exact, self._keymap_base = self._load_console_keymap_map()
        self._console_keymaps = self._load_console_keymaps()

        # --- Initial Population and Text ---
        self.populate_layouts()

    def country_code_to_emoji(self, country_code):
        """Converts a two-letter country code to a flag emoji."""
        if not country_code or len(country_code) != 2:
            return "" # Return empty string for invalid codes

        return "".join(chr(ord(char) - ord('A') + 0x1F1E6) for char in country_code.upper())

    def _load_console_keymaps(self):
        """Return the set of console keymaps known to this system."""
        try:
            result = subprocess.run(
                ['localectl', 'list-keymaps'],
                capture_output=True, text=True, check=True
            )
            return set(result.stdout.split())
        except (subprocess.CalledProcessError, FileNotFoundError):
            return set()

    def _load_console_keymap_map(self):
        """Parse systemd's kbd-model-map into reverse lookup tables.

        Returns (exact, base) where:
          exact[(xkb_layout, xkb_variant)] -> console keymap
          base[xkb_layout]                 -> console keymap (variant-less rows)
        """
        exact, base = {}, {}
        if not os.path.exists(KBD_MODEL_MAP):
            return exact, base
        try:
            with open(KBD_MODEL_MAP, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split()
                    if len(parts) < 4:
                        continue
                    keymap = parts[0]
                    layout0 = parts[1].split(',')[0]
                    variant0 = parts[3].split(',')[0]
                    variant0 = '' if variant0 == '-' else variant0
                    exact.setdefault((layout0, variant0), keymap)
                    if variant0 == '':
                        base.setdefault(layout0, keymap)
        except OSError as e:
            print(f"Could not read {KBD_MODEL_MAP}: {e}")
        return exact, base

    def _derive_console_keymap(self, layout, variant):
        """Best-effort console (vconsole) KEYMAP for an xkb layout/variant."""
        keymap = self._keymap_exact.get((layout, variant)) or self._keymap_base.get(layout)
        if keymap:
            return keymap
        # Many layouts share their name with a console keymap (de, fr, pl, ...).
        if not self._console_keymaps or layout in self._console_keymaps:
            return layout
        return 'us'

    def _load_xkb_layouts(self):
        """Load layouts and their variants (with normalized names) from xkb.

        Returns a list of dicts sorted by display name:
          {'code', 'description', 'country', 'variants': [{'code', 'description'}]}
        The first variant entry (code '') represents the plain layout itself.
        """
        path = next((p for p in XKB_RULES_FILES if os.path.exists(p)), None)
        if not path:
            return []
        try:
            root = ET.parse(path).getroot()
        except (ET.ParseError, OSError) as e:
            print(f"Could not parse xkb rules ({path}): {e}")
            return []

        layout_list = root.find('layoutList')
        if layout_list is None:
            return []

        def _text(element, fallback=""):
            """Return an element's text, or the fallback when missing/empty."""
            return element.text if (element is not None and element.text) else fallback

        layouts = []
        for li in layout_list:
            ci = li.find('configItem')
            if ci is None:
                continue
            code = _text(ci.find('name'))
            # Skip nameless rows and the placeholder "custom" (not selectable).
            if not code or code == 'custom':
                continue
            description = _text(ci.find('description'), code)

            country = ""
            cl = ci.find('countryList')
            if cl is not None and len(cl) and cl[0].text:
                country = cl[0].text

            # First entry is the layout on its own (no variant).
            variants = [{'code': '', 'description': description}]
            vl = li.find('variantList')
            if vl is not None:
                for v in vl:
                    vci = v.find('configItem')
                    if vci is None:
                        continue
                    vcode = _text(vci.find('name'))
                    if not vcode:
                        continue
                    variants.append({
                        'code': vcode,
                        'description': _text(vci.find('description'), vcode),
                    })

            layouts.append({
                'code': code,
                'description': description,
                'country': country,
                'variants': variants,
            })

        layouts.sort(key=lambda l: l['description'].lower())
        return layouts

    def populate_layouts(self):
        """Populate the ListBox with xkb layouts grouped into expandable rows."""
        layouts = self._load_xkb_layouts()

        if not layouts:
            # Minimal fallback so the screen is still usable if the xkb database
            # is unavailable for some reason.
            print("Warning: no xkb layouts found, using a minimal fallback list.")
            layouts = [
                {'code': 'us', 'description': 'English (US)', 'country': 'US',
                 'variants': [{'code': '', 'description': 'English (US)'}]},
                {'code': 'gb', 'description': 'English (UK)', 'country': 'GB',
                 'variants': [{'code': '', 'description': 'English (UK)'}]},
                {'code': 'de', 'description': 'German', 'country': 'DE',
                 'variants': [{'code': '', 'description': 'German'}]},
                {'code': 'fr', 'description': 'French', 'country': 'FR',
                 'variants': [{'code': '', 'description': 'French'}]},
            ]

        for layout in layouts:
            flag = self.country_code_to_emoji(layout['country']) or "⌨️"
            expander = Adw.ExpanderRow(title=f"{flag} {layout['description']}")
            self.list_box.append(expander)

            nested_list_box = Gtk.ListBox()
            nested_list_box.get_style_context().add_class("boxed-list")
            nested_list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
            nested_list_box.connect("row-selected", self.on_row_selected)
            expander.add_row(nested_list_box)

            expander.child_rows = []
            for variant in layout['variants']:
                row = Gtk.ListBoxRow()
                label = Gtk.Label(label=variant['description'], xalign=0,
                                  margin_start=20, margin_top=6, margin_bottom=6)
                row.set_child(label)
                row.xkb_layout = layout['code']
                row.xkb_variant = variant['code']
                # Search matches the readable name plus the raw codes/country.
                row.search_term = " ".join(filter(None, [
                    variant['description'].lower(),
                    layout['description'].lower(),
                    layout['code'].lower(),
                    variant['code'].lower(),
                    layout['country'].lower(),
                ]))
                nested_list_box.append(row)
                expander.child_rows.append(row)

            self.expander_rows.append(expander)

    def _set_keyboard_layout_live(self, layout, variant):
        """
        Sets the keyboard layout for the CURRENT GRAPHICAL SESSION ONLY.
        """
        if not layout:
            return

        source = f"{layout}+{variant}" if variant else layout
        print(f"Attempting to set live session keyboard layout to: {source}")
        try:
            # This gsettings command works for GNOME and some other desktops.
            gsettings_value = f"[('xkb', '{source}')]"
            subprocess.run(
                ['gsettings', 'set', 'org.gnome.desktop.input-sources', 'sources', gsettings_value],
                check=True, capture_output=True, text=True
            )
            print(f"Successfully set live session keyboard layout to {source}")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"Info: Could not set live layout using gsettings (expected on non-GNOME desktops). Error: {e}")

    def save_vconsole_config(self):
        """Save the selected keyboard layout to /tmp/installer_config/etc/vconsole.conf"""
        if not self.selected_layout:
            return False

        try:
            keymap = self._derive_console_keymap(self.selected_layout, self.selected_variant or "")

            # Create directory structure in /tmp/installer_config/etc/
            etc_dir = "/tmp/installer_config/etc"
            os.makedirs(etc_dir, exist_ok=True)

            # KEYMAP is the console keyboard layout; FONT is a reasonable default.
            vconsole_content = [
                f"KEYMAP={keymap}",
                "FONT=ter-v16n",  # Terminus font, good for console
                "FONT_MAP="
            ]

            vconsole_path = os.path.join(etc_dir, "vconsole.conf")
            with open(vconsole_path, 'w') as f:
                f.write('\n'.join(vconsole_content) + '\n')

            print(f"Console keyboard configuration saved to: {vconsole_path}")

            # Also create X11 keyboard configuration for graphical environments
            self.save_x11_keyboard_config(self.selected_layout, self.selected_variant or "")

            return True

        except Exception as e:
            print(f"Error saving vconsole configuration: {e}")
            return False


    def save_x11_keyboard_config(self, layout, variant):
        """Save X11/Wayland keyboard configuration for graphical environments."""
        try:
            # Create X11 config directory
            x11_dir = "/tmp/installer_config/etc/X11/xorg.conf.d"
            os.makedirs(x11_dir, exist_ok=True)

            # Create 00-keyboard.conf for X11 using the real xkb layout/variant.
            x11_config = f"""Section "InputClass"
    Identifier "system-keyboard"
    MatchIsKeyboard "on"
    Option "XkbLayout" "{layout}"
    Option "XkbVariant" "{variant}"
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
        """Save keyboard config and update the live preview when a layout is selected."""
        if self.selected_row and self.selected_row != row:
            if self.selected_row.get_parent() != listbox:
                self.selected_row.get_parent().unselect_row(self.selected_row)

        self.selected_row = row
        self.btn_proceed.set_sensitive(row is not None)

        if row:
            self.selected_layout = row.xkb_layout
            self.selected_variant = row.xkb_variant
            self._set_keyboard_layout_live(row.xkb_layout, row.xkb_variant)
            self.test_entry.grab_focus()
            # Save keyboard configuration when a layout is selected
            self.save_vconsole_config()
        else:
            self.selected_layout = None
            self.selected_variant = None


    def create_keyboard_install_script(self, layout, variant, keymap):
        """Create a script the installer runs (in chroot) to set up the keyboard."""
        try:
            installer_dir = "/tmp/installer_config"
            os.makedirs(installer_dir, exist_ok=True)

            script_path = os.path.join(installer_dir, "setup_keyboard.sh")

            # Runs inside the freshly installed system. The config files were
            # already copied in, but we (re)write them here so the script is
            # self-sufficient, then let localed record the setting if available.
            script_content = f"""#!/bin/bash
# Keyboard layout setup script generated by Linexin Installer
# xkb layout: {layout}  variant: {variant}  console keymap: {keymap}

XKB_LAYOUT="{layout}"
XKB_VARIANT="{variant}"
KEYMAP="{keymap}"

# Console keymap for the TTY / early boot.
cat > /etc/vconsole.conf <<EOF
KEYMAP=$KEYMAP
FONT=ter-v16n
FONT_MAP=
EOF

# X11 / Wayland keyboard configuration for the graphical session.
mkdir -p /etc/X11/xorg.conf.d
cat > /etc/X11/xorg.conf.d/00-keyboard.conf <<EOF
Section "InputClass"
    Identifier "system-keyboard"
    MatchIsKeyboard "on"
    Option "XkbLayout" "$XKB_LAYOUT"
    Option "XkbVariant" "$XKB_VARIANT"
EndSection
EOF

# Best-effort: let systemd record the setting too (no-op if localed is down).
if command -v localectl >/dev/null 2>&1; then
    localectl set-x11-keymap "$XKB_LAYOUT" "" "$XKB_VARIANT" 2>/dev/null || true
fi

echo "Keyboard layout configured: layout=$XKB_LAYOUT variant=$XKB_VARIANT keymap=$KEYMAP"
"""

            with open(script_path, 'w') as f:
                f.write(script_content)

            os.chmod(script_path, 0o755)

            print(f"Keyboard setup script created at: {script_path}")
            return True

        except Exception as e:
            print(f"Error creating keyboard setup script: {e}")
            return False


    def on_continue_clicked(self, button):
        """Handle the Continue button click"""
        if self.save_vconsole_config():
            keymap = self._derive_console_keymap(self.selected_layout, self.selected_variant or "")
            print(f"Keyboard configuration saved for layout: {self.selected_layout} "
                  f"variant: {self.selected_variant} keymap: {keymap}")
            # Also create the installation script
            self.create_keyboard_install_script(
                self.selected_layout, self.selected_variant or "", keymap)
        else:
            print("Failed to save keyboard configuration")

    def get_vconsole_config_path(self):
        """Get the path to the generated vconsole.conf file"""
        return "/tmp/installer_config/etc/vconsole.conf"

    def get_selected_layout(self):
        """Public method to get the selected xkb layout code."""
        return self.selected_layout

    def get_selected_variant(self):
        """Public method to get the selected xkb variant code (may be empty)."""
        return self.selected_variant

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
