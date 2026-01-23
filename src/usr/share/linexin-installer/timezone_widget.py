#!/usr/bin/env python3

import gi
import subprocess
import json
import os

import gettext
import locale

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("WebKit", "6.0")
from gi.repository import Gtk, Adw, Gio, GLib, GObject, WebKit, Gdk
from simple_localization_manager import get_localization_manager

# --- Localization Setup ---
APP_NAME = "linexin-installer"
LOCALE_DIR = "/usr/share/locale"

# Set initial language (will default to system language if not specified)
try:
    locale.setlocale(locale.LC_ALL, '')
except locale.Error:
    pass

locale.bindtextdomain(APP_NAME, LOCALE_DIR)
gettext.textdomain(APP_NAME)
_ = gettext.gettext

class TimezoneWidget(Gtk.Box):
    """
    A GTK widget for selecting a system timezone, with timezones
    grouped by continent in expandable rows and an interactive map.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        

        self.set_orientation(Gtk.Orientation.VERTICAL)
        self.set_spacing(20)
        self.set_margin_top(30)
        self.set_margin_bottom(30)
        
        # Setup CSS
        self.setup_css()

        # A list to hold the top-level expander rows for filtering
        self.expander_rows = []
        self.selected_row = None
        self.timezone_coordinates = {}

        # --- Title Label ---
        self.title = Gtk.Label()
        self.title.set_markup('<span size="xx-large" weight="bold">' + _("Select Your Timezone") + '</span>')
        self.title.set_halign(Gtk.Align.CENTER)
        self.append(self.title)

        # --- Adw.Clamp constrains the width of the content ---
        clamp = Adw.Clamp(margin_start=12, margin_end=12, maximum_size=800)
        clamp.set_vexpand(True)
        self.append(clamp)

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        clamp.set_child(content_box)

        # --- Subtitle Label ---
        subtitle_label = _("Choose a city in your region. This will be used to set the clock.")
        self.subtitle = Gtk.Label(
            label=subtitle_label,
            halign=Gtk.Align.CENTER
        )
        self.subtitle.add_css_class('dim-label')
        content_box.append(self.subtitle)

        # --- Search Entry ---
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text(_("Search for your city or region..."))
        self.search_entry.connect("search-changed", self.on_search_changed)
        content_box.append(self.search_entry)

        # --- Create a paned view: map on left, list on right ---
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(400)  # Initial position
        paned.set_vexpand(True)
        content_box.append(paned)

        # --- Map Container (Left side) ---
        map_frame = Gtk.Frame()
        map_frame.set_size_request(400, 300)
        paned.set_start_child(map_frame)

        # Create WebView for the map
        self.web_view = WebKit.WebView()
        self.web_view.connect("load-changed", self.on_map_load_changed)
        map_frame.set_child(self.web_view)

        # --- List Container (Right side) ---
        list_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        list_container.set_margin_start(10)
        paned.set_end_child(list_container)

        # --- Scrolled Window for the List ---
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_has_frame(True)
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_vexpand(True)
        list_container.append(scrolled_window)

        # --- ListBox to display each timezone ---
        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.get_style_context().add_class("boxed-list")
        scrolled_window.set_child(self.list_box)
        
        # Load timezone coordinates and populate the list
        self.load_timezone_coordinates()
        self.populate_timezones()
        self.load_timezone_map()

        # --- Bottom Navigation Buttons ---
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
        
        button_box.append(self.btn_back)

        self.btn_proceed = Gtk.Button(label="Continue")
        self.btn_proceed.add_css_class('suggested-action')
        self.btn_proceed.add_css_class('continue_button')
        self.btn_proceed.set_size_request(140, 50)
        self.btn_proceed.set_sensitive(False) # Disabled until a selection is made
        self.btn_proceed.connect("clicked", self.on_continue_clicked)
        
        # Add hover effects to continue button
        continue_hover = Gtk.EventControllerMotion()
        continue_hover.connect("enter", lambda c, x, y: self.btn_proceed.add_css_class("pulse-animation"))
        continue_hover.connect("leave", lambda c: self.btn_proceed.remove_css_class("pulse-animation"))
        self.btn_proceed.add_controller(continue_hover)
        
        button_box.append(self.btn_proceed)

    def load_timezone_coordinates(self):
        """Load timezone coordinates for map markers"""
        # Major timezone coordinates (lat, lng)
        self.timezone_coordinates = {
            # North America
            "America/New_York": [40.7128, -74.0060],
            "America/Chicago": [41.8781, -87.6298],
            "America/Denver": [39.7392, -104.9903],
            "America/Los_Angeles": [34.0522, -118.2437],
            "America/Vancouver": [49.2827, -123.1207],
            "America/Toronto": [43.651070, -79.347015],
            "America/Mexico_City": [19.4326, -99.1332],
            "America/Sao_Paulo": [-23.5558, -46.6396],
            "America/Buenos_Aires": [-34.6118, -58.3960],
            "America/Lima": [-12.0464, -77.0428],
            "America/Bogota": [4.7110, -74.0721],
            
            # Europe
            "Europe/London": [51.5074, -0.1278],
            "Europe/Paris": [48.8566, 2.3522],
            "Europe/Berlin": [52.5200, 13.4050],
            "Europe/Rome": [41.9028, 12.4964],
            "Europe/Madrid": [40.4168, -3.7038],
            "Europe/Amsterdam": [52.3676, 4.9041],
            "Europe/Warsaw": [52.2297, 21.0122],
            "Europe/Moscow": [55.7558, 37.6173],
            "Europe/Vienna": [48.2082, 16.3738],
            "Europe/Stockholm": [59.3293, 18.0686],
            "Europe/Athens": [37.9838, 23.7275],
            "Europe/Kiev": [50.4501, 30.5234],
            "Europe/Zurich": [47.3769, 8.5417],
            
            # Asia
            "Asia/Tokyo": [35.6762, 139.6503],
            "Asia/Shanghai": [31.2304, 121.4737],
            "Asia/Hong_Kong": [22.3193, 114.1694],
            "Asia/Singapore": [1.3521, 103.8198],
            "Asia/Mumbai": [19.0760, 72.8777],
            "Asia/Dubai": [25.2048, 55.2708],
            "Asia/Bangkok": [13.7563, 100.5018],
            "Asia/Jakarta": [-6.2088, 106.8456],
            "Asia/Seoul": [37.5665, 126.9780],
            "Asia/Manila": [14.5995, 120.9842],
            "Asia/Karachi": [24.8607, 67.0011],
            "Asia/Tehran": [35.6892, 51.3890],
            "Asia/Baghdad": [33.3152, 44.3661],
            "Asia/Riyadh": [24.7136, 46.6753],
            
            # Africa
            "Africa/Cairo": [30.0444, 31.2357],
            "Africa/Lagos": [6.5244, 3.3792],
            "Africa/Johannesburg": [-26.2041, 28.0473],
            "Africa/Nairobi": [-1.2921, 36.8219],
            "Africa/Casablanca": [33.5731, -7.5898],
            "Africa/Tunis": [36.8065, 10.1815],
            "Africa/Algiers": [36.7538, 3.0588],
            
            # Australia/Oceania
            "Australia/Sydney": [-33.8688, 151.2093],
            "Australia/Melbourne": [-37.8136, 144.9631],
            "Australia/Perth": [-31.9505, 115.8605],
            "Australia/Brisbane": [-27.4698, 153.0251],
            "Australia/Adelaide": [-34.9285, 138.6007],
            "Pacific/Auckland": [-36.8485, 174.7633],
            "Pacific/Fiji": [-18.1248, 178.4501],
            "Pacific/Honolulu": [21.3099, -157.8581],
            
            # Other
            "UTC": [51.4769, -0.0005],  # Greenwich
            "GMT": [51.4769, -0.0005],   # Greenwich
        }

    def create_map_html(self):
        """Create HTML content for the interactive map"""
        markers_js = []
        for timezone, coords in self.timezone_coordinates.items():
            lat, lng = coords
            city = timezone.split('/')[-1].replace('_', ' ')
            markers_js.append(f"""
                L.marker([{lat}, {lng}])
                    .addTo(map)
                    .bindPopup('<b>{city}</b><br>{timezone}')
                    .on('click', function(e) {{
                        selectTimezone('{timezone}');
                    }});
            """)

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Timezone Map</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css" />
    <style>
        body {{
            margin: 0;
            padding: 0;
            font-family: sans-serif;
        }}
        #map {{
            height: 100vh;
            width: 100%;
        }}
        .timezone-marker {{
            background-color: #3498db;
            border-radius: 50%;
            border: 2px solid white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.3);
        }}
    </style>
</head>
<body>
    <div id="map"></div>
    
    <script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
    <script>
        // Initialize the map
        var map = L.map('map', {{
            maxBounds: [[-90, -180], [90, 180]],
            maxBoundsViscosity: 1.0
        }}).setView([20, 0], 2);
        
        // Add OpenStreetMap tiles
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: '© OpenStreetMap contributors',
            maxZoom: 10,
            minZoom: 1,
            noWrap: true,
            bounds: [[-90, -180], [90, 180]]
        }}).addTo(map);
        
        // Add timezone markers
        {' '.join(markers_js)}
        
        // Function to communicate with GTK
        function selectTimezone(timezone) {{
            // This will be caught by the WebKit message handler
            window.webkit.messageHandlers.timezoneSelected.postMessage(timezone);
        }}
        
        // Handle map clicks for approximate timezone selection
        map.on('click', function(e) {{
            var lat = e.latlng.lat;
            var lng = e.latlng.lng;
            
            // Find the closest timezone marker
            var closest = null;
            var minDistance = Infinity;
            
            Object.entries(timezoneCoords).forEach(([timezone, coords]) => {{
                var distance = Math.sqrt(
                    Math.pow(lat - coords[0], 2) + 
                    Math.pow(lng - coords[1], 2)
                );
                if (distance < minDistance) {{
                    minDistance = distance;
                    closest = timezone;
                }}
            }});
            
            if (closest) {{
                selectTimezone(closest);
            }}
        }});
        
        // Store coordinates for distance calculation
        var timezoneCoords = {json.dumps(self.timezone_coordinates)};
    </script>
</body>
</html>
        """
        return html_content

    def load_timezone_map(self):
        """Load the timezone map in the WebView"""
        html_content = self.create_map_html()
        
        # Create a temporary HTML file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            f.write(html_content)
            self.map_file_path = f.name
        
        # Load the HTML file in WebView
        file_uri = f"file://{self.map_file_path}"
        self.web_view.load_uri(file_uri)

    def on_map_load_changed(self, web_view, load_event):
        """Handle WebView load events"""
        if load_event == WebKit.LoadEvent.FINISHED:
            # Set up message handler for timezone selection from map
            content_manager = web_view.get_user_content_manager()
            content_manager.register_script_message_handler("timezoneSelected")
            content_manager.connect("script-message-received::timezoneSelected", 
                                   self.on_timezone_selected_from_map)
            print("Map loaded successfully and message handler registered")

    def on_timezone_selected_from_map(self, content_manager, result):
        """Handle timezone selection from map"""
        try:
            # Handle different WebKit API versions
            if hasattr(result, 'get_js_value'):
                # Newer WebKit API
                timezone = result.get_js_value().to_string()
            elif hasattr(result, 'to_string'):
                # Direct string conversion
                timezone = result.to_string()
            else:
                # Fallback - treat as string directly
                timezone = str(result)
            
            print(f"Timezone selected from map: {timezone}")
            
            # Find and select the corresponding row in the list
            success = self.select_timezone_in_list(timezone)
            if success:
                print(f"Successfully selected {timezone} in list")
            else:
                print(f"Failed to find {timezone} in list")
            
            # Update the map to highlight the selection
            self.highlight_timezone_on_map(timezone)
            
        except Exception as e:
            print(f"Error handling timezone selection from map: {e}")
            print(f"Result object type: {type(result)}")
            print(f"Result object methods: {dir(result)}")

    def select_timezone_in_list(self, timezone):
        """Select the timezone in the list view"""
        print(f"Attempting to select timezone: {timezone}")
        
        # First, expand the appropriate continent
        continent = timezone.split('/')[0] if '/' in timezone else "Other"
        print(f"Looking for continent: {continent}")
        
        for expander in self.expander_rows:
            if expander.get_title() == continent:
                print(f"Found continent expander: {continent}")
                expander.set_expanded(True)
                
                # Find and select the timezone row
                for row in expander.child_rows:
                    if hasattr(row, 'timezone_name') and row.timezone_name == timezone:
                        print(f"Found timezone row: {timezone}")
                        
                        # Get the nested listbox and select the row
                        nested_listbox = row.get_parent()
                        
                        # Clear previous selections first
                        if self.selected_row and self.selected_row.get_parent():
                            self.selected_row.get_parent().unselect_all()
                        
                        # Select the new row
                        nested_listbox.select_row(row)
                        
                        # Manually trigger the selection handler
                        self.on_row_selected(nested_listbox, row)
                        
                        # Scroll to make the row visible
                        row.grab_focus()
                        
                        # Use GLib.idle_add to ensure the UI updates
                        GLib.idle_add(lambda: self.scroll_to_row(row))
                        
                        return True
                break
        
        print(f"Could not find timezone {timezone} in the list")
        return False
    
    def scroll_to_row(self, row):
        """Helper function to scroll to a specific row"""
        try:
            # Get the scrolled window from the widget hierarchy
            widget = row
            while widget and not isinstance(widget, Gtk.ScrolledWindow):
                widget = widget.get_parent()
            
            if widget and isinstance(widget, Gtk.ScrolledWindow):
                # Get the adjustment and scroll to the row
                vadj = widget.get_vadjustment()
                if vadj:
                    # This is a simplified scroll - you might need to calculate exact position
                    row_allocation = row.get_allocation()
                    if row_allocation.height > 0:
                        vadj.set_value(max(0, row_allocation.y - vadj.get_page_size() / 2))
        except Exception as e:
            print(f"Error scrolling to row: {e}")
        
        return False  # Don't repeat the idle call

    def highlight_timezone_on_map(self, timezone):
        """Highlight the selected timezone on the map"""
        js_code = f"""
        // Remove previous highlights
        map.eachLayer(function(layer) {{
            if (layer instanceof L.Marker) {{
                layer.setOpacity(0.7);
            }}
        }});
        
        // Highlight the selected timezone
        // This is a simplified version - you could make it more sophisticated
        console.log('Highlighted timezone: {timezone}');
        """
        
        self.web_view.evaluate_javascript(js_code, -1, None, None, None, None)

    def populate_timezones(self):
        """Fetches timezones, groups them by continent, and populates the list."""
        try:
            result = subprocess.run(
                ['timedatectl', 'list-timezones'], 
                capture_output=True, 
                text=True, 
                check=True
            )
            timezones = result.stdout.strip().split('\n')
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"Error getting timezones: {e}. Using a fallback list.")
            timezones = list(self.timezone_coordinates.keys()) + ["UTC"]
        
        # --- Group timezones by continent ---
        grouped_timezones = {}
        for tz in timezones:
            if "/" in tz:
                continent = tz.split('/')[0]
                if continent not in grouped_timezones:
                    grouped_timezones[continent] = []
                grouped_timezones[continent].append(tz)
            else: # For timezones like 'UTC'
                if "Other" not in grouped_timezones:
                    grouped_timezones["Other"] = []
                grouped_timezones["Other"].append(tz)

        # --- Populate the list with expandable rows ---
        for continent in sorted(grouped_timezones.keys()):
            expander = Adw.ExpanderRow(title=continent)
            self.list_box.append(expander)

            nested_list_box = Gtk.ListBox()
            nested_list_box.get_style_context().add_class("boxed-list")
            nested_list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
            nested_list_box.connect("row-selected", self.on_row_selected)
            expander.add_row(nested_list_box)
            
            expander.child_rows = []
            for tz_name in sorted(grouped_timezones[continent]):
                row = Gtk.ListBoxRow()
                
                # Create a box to hold the label and optional map icon
                row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                row_box.set_margin_start(10)
                row_box.set_margin_end(10)
                row_box.set_margin_top(10)
                row_box.set_margin_bottom(10)
                
                label = Gtk.Label(label=tz_name, xalign=0)
                label.set_hexpand(True)
                row_box.append(label)
                
                # Add a small icon if this timezone has map coordinates
                if tz_name in self.timezone_coordinates:
                    map_icon = Gtk.Image.new_from_icon_name("mark-location-symbolic")
                    map_icon.set_opacity(0.6)
                    row_box.append(map_icon)
                
                row.set_child(row_box)
                
                row.timezone_name = tz_name
                row.search_term = tz_name.lower().replace("_", " ")
                
                nested_list_box.append(row)
                expander.child_rows.append(row)
            
            self.expander_rows.append(expander)

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

    def save_timezone_config(self):
        """Save the selected timezone configuration to /tmp/installer_config/etc/"""
        selected_timezone = self.get_selected_timezone()
        if not selected_timezone:
            return False
        
        try:
            import os
            
            # Create directory structure in /tmp/installer_config/etc/
            etc_dir = "/tmp/installer_config/etc"
            os.makedirs(etc_dir, exist_ok=True)
            
            # Save timezone to a plain text file (like Arch's /etc/timezone)
            timezone_path = os.path.join(etc_dir, "timezone")
            with open(timezone_path, 'w') as f:
                f.write(selected_timezone + '\n')
            
            print(f"Timezone configuration saved to: {timezone_path}")
            
            # Also create a localtime configuration file for the installer to process
            # This file will tell the installer which timezone file to symlink
            localtime_config_path = os.path.join(etc_dir, "localtime.conf")
            with open(localtime_config_path, 'w') as f:
                f.write(f"TIMEZONE={selected_timezone}\n")
                f.write(f"# This file should be used by the installer to create the symlink:\n")
                f.write(f"# ln -sf /usr/share/zoneinfo/{selected_timezone} /etc/localtime\n")
            
            print(f"Localtime configuration saved to: {localtime_config_path}")
            
            # Create an installer script for timezone setup
            self.create_timezone_install_script(selected_timezone)
            
            return True
            
        except Exception as e:
            print(f"Error saving timezone configuration: {e}")
            return False

    def create_timezone_install_script(self, timezone):
        """Create a script that the installer can run to set up the timezone"""
        try:
            import os
            
            # Create the installer config directory if it doesn't exist
            installer_dir = "/tmp/installer_config"
            os.makedirs(installer_dir, exist_ok=True)
            
            script_path = os.path.join(installer_dir, "setup_timezone.sh")
            
            script_content = f"""#!/bin/bash
    # Timezone setup script generated by Linexin Installer
    # Generated timezone: {timezone}

    CHROOT_DIR="${{1:-}}"

    if [ -n "$CHROOT_DIR" ]; then
        # If running in chroot environment during installation
        echo "Setting timezone to {timezone} in $CHROOT_DIR"
        
        # Create the symlink for localtime
        ln -sf "/usr/share/zoneinfo/{timezone}" "$CHROOT_DIR/etc/localtime"
        
        # Set the timezone in /etc/timezone (some systems use this)
        echo "{timezone}" > "$CHROOT_DIR/etc/timezone"
        
        # If systemd is available, set timezone there too
        if [ -f "$CHROOT_DIR/usr/bin/timedatectl" ]; then
            chroot "$CHROOT_DIR" timedatectl set-timezone "{timezone}" 2>/dev/null || true
        fi
    else
        # If running on live system
        echo "Setting timezone to {timezone} on current system"
        
        # Create the symlink for localtime
        sudo ln -sf "/usr/share/zoneinfo/{timezone}" /etc/localtime
        
        # Set the timezone in /etc/timezone
        echo "{timezone}" | sudo tee /etc/timezone
        
        # Use timedatectl if available
        if command -v timedatectl &> /dev/null; then
            sudo timedatectl set-timezone "{timezone}"
        fi
    fi

    # Generate /etc/adjtime for hardware clock
    if [ -n "$CHROOT_DIR" ]; then
        echo "0.0 0 0.0" > "$CHROOT_DIR/etc/adjtime"
        echo "0" >> "$CHROOT_DIR/etc/adjtime"
        echo "UTC" >> "$CHROOT_DIR/etc/adjtime"
    else
        echo "0.0 0 0.0" | sudo tee /etc/adjtime
        echo "0" | sudo tee -a /etc/adjtime
        echo "UTC" | sudo tee -a /etc/adjtime
    fi

    echo "Timezone configuration completed successfully!"
    """
            
            with open(script_path, 'w') as f:
                f.write(script_content)
            
            # Make the script executable
            os.chmod(script_path, 0o755)
            
            print(f"Timezone setup script created at: {script_path}")
            return True
            
        except Exception as e:
            print(f"Error creating timezone setup script: {e}")
            return False

    def on_row_selected(self, listbox, row):
        """Updated to save timezone config when a timezone is selected and update map"""
        # Avoid recursive calls when selecting from map
        if hasattr(self, '_selecting_from_map') and self._selecting_from_map:
            self._selecting_from_map = False
        else:
            # Clear other selections if this is a user-initiated selection
            if self.selected_row and self.selected_row != row:
                if self.selected_row.get_parent() != listbox:
                    self.selected_row.get_parent().unselect_row(self.selected_row)

        self.selected_row = row
        self.btn_proceed.set_sensitive(row is not None)
        
        # Save timezone configuration when a timezone is selected
        if row is not None:
            self.save_timezone_config()
            # Update map to show selected timezone (only if not selecting from map)
            if hasattr(row, 'timezone_name') and not hasattr(self, '_selecting_from_map'):
                self.highlight_timezone_on_map(row.timezone_name)

    def get_timezone_config_path(self):
        """Get the path to the generated timezone configuration file"""
        return "/tmp/installer_config/etc/timezone"

    def on_continue_clicked(self, button):
        """Handle the Continue button click"""
        if self.save_timezone_config():
            selected_tz = self.get_selected_timezone()
            print(f"Timezone configuration saved for: {selected_tz}")
            # You can add navigation to the next widget here
        else:
            print("Failed to save timezone configuration")

    def get_selected_timezone(self):
        """Public method to get the selected timezone string."""
        if self.selected_row:
            return self.selected_row.timezone_name
        return None

    def __del__(self):
        """Clean up temporary files"""
        if hasattr(self, 'map_file_path') and os.path.exists(self.map_file_path):
            try:
                os.unlink(self.map_file_path)
            except:
                pass

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