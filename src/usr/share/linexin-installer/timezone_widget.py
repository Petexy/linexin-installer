#!/usr/bin/env python3

import gi
import subprocess
import json
import os
import math
import cairo

import gettext
import locale

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, GObject, Gdk
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

# Directory this module lives in, used to locate bundled assets.
WIDGET_DIR = os.path.dirname(os.path.abspath(__file__))


class WorldTimezoneMap(Gtk.DrawingArea):
    """
    A fully offline, native world map rendered with Cairo.

    The map is drawn from bundled public-domain Natural Earth land polygons
    (equirectangular projection) so it works without any network connection --
    the previous implementation relied on Leaflet and OpenStreetMap tiles loaded
    from the internet and showed nothing when offline.

    Emits ``timezone-picked`` with the nearest timezone name when the map is
    clicked.
    """

    __gsignals__ = {
        "timezone-picked": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    # The visible latitude window is biased slightly north, where the vast
    # majority of timezones live, so the empty polar caps get cropped first.
    LAT_CENTER = 10.0

    def __init__(self, coordinates, **kwargs):
        super().__init__(**kwargs)
        self.coordinates = coordinates          # {timezone: [lat, lng]}
        self.selected = None
        self.hovered = None
        self.polygons = self._load_land()
        self._view = None                       # (width, height, lat_top, lat_bottom)

        self.set_hexpand(True)
        self.set_vexpand(False)
        # A wide banner; the map fills whatever size it is given.
        self.set_content_width(600)
        self.set_content_height(285)
        self.set_draw_func(self._draw)

        click = Gtk.GestureClick()
        click.connect("pressed", self._on_click)
        self.add_controller(click)

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_motion)
        motion.connect("leave", self._on_leave)
        self.add_controller(motion)

        # Redraw when the system switches between light and dark themes.
        self.style_manager = Adw.StyleManager.get_default()
        self.style_manager.connect("notify::dark", lambda *a: self.queue_draw())

    # --- Asset loading -----------------------------------------------------
    def _load_land(self):
        """Load bundled land polygons. Degrades gracefully if unavailable."""
        path = os.path.join(WIDGET_DIR, "world_land.json")
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return data.get("polygons", [])
        except Exception as e:
            print(f"Timezone map: could not load land data ({e}); "
                  "drawing markers only.")
            return []

    # --- Projection helpers ------------------------------------------------
    def _compute_view(self, width, height):
        """Pick a latitude window that fills width x height without distortion.

        The full 360 deg of longitude always spans the width. The latitude span
        is chosen so that degrees-per-pixel matches horizontally and vertically
        (no stretching), then centered on ``LAT_CENTER`` and clamped to the
        poles. This fills the widget edge to edge -- no empty ocean bands --
        while only ever cropping the (mostly empty) polar caps.
        """
        if width <= 0 or height <= 0:
            self._view = None
            return
        lat_span = min(360.0 * height / width, 180.0)
        half = lat_span / 2.0
        center = max(-90.0 + half, min(90.0 - half, self.LAT_CENTER))
        self._view = (width, height, center + half, center - half)

    def _project(self, lat, lng):
        width, height, lat_top, lat_bottom = self._view
        x = (lng + 180.0) / 360.0 * width
        y = (lat_top - lat) / (lat_top - lat_bottom) * height
        return x, y

    def _palette(self):
        dark = self.style_manager.get_dark()
        if dark:
            return {
                "ocean": (0.11, 0.13, 0.17),
                "land": (0.26, 0.31, 0.30),
                "land_border": (0.16, 0.19, 0.18),
                "frame": (0.30, 0.34, 0.40),
            }
        return {
            "ocean": (0.80, 0.86, 0.92),
            "land": (0.66, 0.75, 0.65),
            "land_border": (0.52, 0.60, 0.52),
            "frame": (0.62, 0.68, 0.74),
        }

    # --- Drawing -----------------------------------------------------------
    def _rounded_rect(self, cr, x, y, w, h, r):
        r = min(r, w / 2.0, h / 2.0)
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -0.5 * math.pi, 0)
        cr.arc(x + w - r, y + h - r, r, 0, 0.5 * math.pi)
        cr.arc(x + r, y + h - r, r, 0.5 * math.pi, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
        cr.close_path()

    def _draw(self, area, cr, width, height):
        self._compute_view(width, height)
        if self._view is None:
            return
        colors = self._palette()

        # Clip to a rounded rectangle so the map has soft corners.
        self._rounded_rect(cr, 0, 0, width, height, 8.0)
        cr.clip()

        # Ocean fills the whole widget (the sea shows wherever there is no land).
        cr.set_source_rgb(*colors["ocean"])
        cr.paint()

        # Landmasses.
        if self.polygons:
            cr.set_line_width(0.6)
            for poly in self.polygons:
                cr.new_path()
                for ring in poly:
                    for i, point in enumerate(ring):
                        x, y = self._project(point[1], point[0])
                        if i == 0:
                            cr.move_to(x, y)
                        else:
                            cr.line_to(x, y)
                    cr.close_path()
                cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
                cr.set_source_rgb(*colors["land"])
                cr.fill_preserve()
                cr.set_source_rgb(*colors["land_border"])
                cr.stroke()

        # Timezone markers.
        for tz, coords in self.coordinates.items():
            if tz == self.selected:
                continue
            x, y = self._project(coords[0], coords[1])
            self._draw_marker(cr, x, y, hovered=(tz == self.hovered))

        # Selected marker drawn last so it sits on top.
        if self.selected and self.selected in self.coordinates:
            coords = self.coordinates[self.selected]
            x, y = self._project(coords[0], coords[1])
            self._draw_selected_marker(cr, x, y)

        # Thin frame following the widget's rounded edge.
        cr.set_source_rgb(*colors["frame"])
        cr.set_line_width(1.0)
        self._rounded_rect(cr, 0.5, 0.5, width - 1.0, height - 1.0, 8.0)
        cr.stroke()

    def _draw_marker(self, cr, x, y, hovered=False):
        r = 4.5 if hovered else 3.2
        # White halo for contrast against land/ocean.
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.9)
        cr.arc(x, y, r + 1.2, 0, 2 * math.pi)
        cr.fill()
        cr.set_source_rgb(0.20, 0.52, 0.89)   # GNOME blue
        cr.arc(x, y, r, 0, 2 * math.pi)
        cr.fill()

    def _draw_selected_marker(self, cr, x, y):
        # Outer glow ring.
        cr.set_source_rgba(0.90, 0.38, 0.12, 0.35)
        cr.arc(x, y, 11.0, 0, 2 * math.pi)
        cr.fill()
        # White outline.
        cr.set_source_rgb(1.0, 1.0, 1.0)
        cr.arc(x, y, 7.0, 0, 2 * math.pi)
        cr.fill()
        # Accent center.
        cr.set_source_rgb(0.90, 0.36, 0.12)
        cr.arc(x, y, 5.0, 0, 2 * math.pi)
        cr.fill()

    # --- Interaction -------------------------------------------------------
    def _nearest(self, px, py):
        """Nearest timezone marker (in pixel space) to a point."""
        if self._view is None:
            return None, None
        best = None
        best_dist = None
        for tz, coords in self.coordinates.items():
            mx, my = self._project(coords[0], coords[1])
            dist = (mx - px) ** 2 + (my - py) ** 2
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best = tz
        return best, best_dist

    def _on_click(self, gesture, n_press, x, y):
        tz, _dist = self._nearest(x, y)
        if tz:
            self.emit("timezone-picked", tz)

    def _on_motion(self, controller, x, y):
        tz, dist = self._nearest(x, y)
        within = tz is not None and dist is not None and dist <= (15.0 ** 2)
        new_hover = tz if within else None
        if new_hover != self.hovered:
            self.hovered = new_hover
            if new_hover:
                city = new_hover.split('/')[-1].replace('_', ' ')
                self.set_has_tooltip(True)
                self.set_tooltip_text(f"{city} — {new_hover}")
            else:
                self.set_has_tooltip(False)
            self.queue_draw()
        try:
            self.set_cursor_from_name("pointer" if within else "default")
        except Exception:
            pass

    def _on_leave(self, controller):
        if self.hovered is not None:
            self.hovered = None
            self.set_has_tooltip(False)
            self.queue_draw()

    def select(self, timezone):
        """Highlight ``timezone`` on the map (or clear if it has no marker)."""
        new_selected = timezone if timezone in self.coordinates else None
        if new_selected != self.selected:
            self.selected = new_selected
            self.queue_draw()


class TimezoneWidget(Gtk.Box):
    """
    A GTK widget for selecting a system timezone, with timezones
    grouped by continent in expandable rows and an interactive, fully
    offline map.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


        self.set_orientation(Gtk.Orientation.VERTICAL)
        self.set_spacing(20)
        self.set_margin_top(15)
        self.set_margin_bottom(15)

        # Setup CSS
        self.setup_css()

        # A list to hold the top-level expander rows for filtering
        self.expander_rows = []
        self.selected_row = None
        self.timezone_coordinates = {}
        self._syncing = False  # guards map<->list selection feedback loop

        # --- Title Label ---
        self.title = Gtk.Label()
        self.title.set_markup('<span size="xx-large" weight="bold">' + _("Select Your Timezone") + '</span>')
        self.title.set_halign(Gtk.Align.CENTER)
        self.append(self.title)

        # --- Adw.Clamp constrains the width of the content ---
        clamp = Adw.Clamp(margin_start=12, margin_end=12, maximum_size=800)
        clamp.set_vexpand(True)
        self.append(clamp)

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        clamp.set_child(content_box)

        # --- Load timezone coordinates before building the map ---
        self.load_timezone_coordinates()

        # --- Map banner (full width, fixed-height, always filled) ---
        self.map = WorldTimezoneMap(self.timezone_coordinates)
        self.map.connect("timezone-picked", self.on_timezone_selected_from_map)
        content_box.append(self.map)

        # --- Search Entry ---
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text(_("Search for your city or region..."))
        self.search_entry.connect("search-changed", self.on_search_changed)
        content_box.append(self.search_entry)

        # --- Scrolled Window for the List ---
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_has_frame(True)
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_vexpand(True)
        scrolled_window.set_size_request(-1, 120)
        self.scrolled_window = scrolled_window
        content_box.append(scrolled_window)

        # --- ListBox to display each timezone ---
        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.get_style_context().add_class("boxed-list")
        scrolled_window.set_child(self.list_box)

        # Populate the list
        self.populate_timezones()

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
            "Asia/Kolkata": [22.5726, 88.3639],
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

    def on_timezone_selected_from_map(self, world_map, timezone):
        """Handle timezone selection from the map."""
        print(f"Timezone selected from map: {timezone}")

        # Sync the list selection without re-triggering a map update.
        self._syncing = True
        try:
            success = self.select_timezone_in_list(timezone)
        finally:
            self._syncing = False

        if success:
            print(f"Successfully selected {timezone} in list")
        else:
            print(f"Timezone {timezone} not found in list; selecting on map only")

        # Highlight the marker on the map.
        self.map.select(timezone)

    def select_timezone_in_list(self, timezone):
        """Select the timezone in the list view and scroll it into view."""
        # First, expand the appropriate continent
        continent = timezone.split('/')[0] if '/' in timezone else "Other"

        for expander in self.expander_rows:
            if expander.get_title() == continent:
                was_expanded = expander.get_expanded()
                expander.set_expanded(True)

                # Find and select the timezone row
                for row in expander.child_rows:
                    if getattr(row, 'timezone_name', None) == timezone:
                        nested_listbox = row.get_parent()
                        nested_listbox.select_row(row)
                        row.grab_focus()
                        # Scroll the row into view. If the continent was already
                        # open we can scroll straight away; if we just expanded
                        # it, wait for its reveal animation to settle first --
                        # reading the row's position mid-animation returns
                        # transient (wrong) coordinates.
                        self._scroll_ticks = 0
                        if was_expanded:
                            GLib.idle_add(self._scroll_to_row, row)
                        else:
                            self._settle_ticks = 0
                            self._settle_upper = -1.0
                            GLib.timeout_add(25, self._settle_then_scroll, row)
                        return True
                break

        print(f"Could not find timezone {timezone} in the list")
        return False

    def _settle_then_scroll(self, row):
        """Wait for the expander's reveal to finish, then scroll to ``row``.

        The list's scroll range (``upper``) grows every frame while a section
        slides open; once it stops changing the layout has settled and the
        row's position can be read reliably. This adapts to any animation
        length or list size instead of guessing a fixed delay.
        """
        vadj = self.scrolled_window.get_vadjustment()
        if vadj is None:
            return False
        self._settle_ticks += 1
        upper = vadj.get_upper()
        settled = upper == self._settle_upper
        self._settle_upper = upper
        if settled or self._settle_ticks > 80:  # cap ~2s
            self._scroll_to_row(row)
            return False
        GLib.timeout_add(25, self._settle_then_scroll, row)
        return False

    def _scroll_to_row(self, row):
        """Centre ``row`` in the list; retry until it is actually visible."""
        vadj = self.scrolled_window.get_vadjustment()
        if vadj is None:
            return False

        self._scroll_ticks = getattr(self, "_scroll_ticks", 0) + 1
        retry = self._scroll_ticks <= 60  # ~1.5s worth of attempts

        # Row bounds in the coordinate space of the scrolled content
        # (self.list_box) -- independent of the current scroll offset.
        ok, rect = row.compute_bounds(self.list_box)
        row_height = rect.size.height if ok else 0

        # While the expander reveals, the row may not have a real allocation yet.
        if not ok or row_height <= 0:
            if retry:
                GLib.timeout_add(25, self._scroll_to_row, row)
            return False

        page = vadj.get_page_size()
        top = rect.origin.y
        bottom = top + row_height
        target = top - (page - row_height) / 2.0
        target = max(vadj.get_lower(), min(target, vadj.get_upper() - page))
        vadj.set_value(target)

        # Because upper/animation can lag, verify the row is now on screen and
        # keep trying if it is not.
        value = vadj.get_value()
        visible = top >= value - 1 and bottom <= value + page + 1
        if not visible and retry:
            GLib.timeout_add(25, self._scroll_to_row, row)
        return False  # Don't repeat this particular idle/timeout call

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
        """Save timezone config when a timezone is selected and update the map."""
        # ``row-selected`` also fires with row=None while we clear a selection in
        # another nested list box -- ignore those to avoid clobbering state.
        if row is None:
            return

        # Enforce a single selection across all the nested continent list boxes.
        if self.selected_row is not None and self.selected_row is not row:
            prev_parent = self.selected_row.get_parent()
            if prev_parent is not None and prev_parent is not listbox:
                prev_parent.unselect_row(self.selected_row)

        self.selected_row = row
        self.btn_proceed.set_sensitive(True)

        # Save timezone configuration when a timezone is selected
        self.save_timezone_config()

        # Update the map to show the selection (unless the change came from the
        # map itself, which updates the highlight on its own).
        if not self._syncing:
            tz = getattr(row, 'timezone_name', None)
            self.map.select(tz)

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
