#!/usr/bin/env python3

import os
import gi
import json
import hashlib
import random
import string
import re
import subprocess

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib
from simple_localization_manager import get_localization_manager

import gettext
import locale

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

class UserCreationWidget(Gtk.Box):
    """
    A GTK widget for creating user accounts during system installation.
    Generates a script to create users and configure the system during installation.
    """
    def __init__(self, config_output_dir=None, **kwargs):
        super().__init__(**kwargs)
        get_localization_manager().register_widget(self)

        self.set_orientation(Gtk.Orientation.VERTICAL)
        self.set_spacing(20)
        self.set_margin_top(30)
        self.set_margin_bottom(30)
        
        # State tracking
        self.root_enabled = False
        self.validation_errors = set()
        
        # Configuration output directory
        # Default to /tmp which is usually tmpfs but has more space allocated
        # Or use a custom directory (like a mounted partition)
        self.config_output_dir = config_output_dir or "/tmp"
        
        # --- Title Label ---
        self.title = Gtk.Label()
        self.title.set_markup('<span size="xx-large" weight="bold">' + _("Create Your User Account") + '</span>')
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
            label=_("Set up your account to log in to the system."),
            halign=Gtk.Align.CENTER
        )
        self.subtitle.add_css_class('dim-label')
        content_box.append(self.subtitle)
        
        # --- Scrolled Window for the form ---
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_vexpand(True)
        content_box.append(scrolled_window)
        
        # Form container
        form_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        form_box.set_margin_top(20)
        form_box.set_margin_start(20)
        form_box.set_margin_end(20)
        scrolled_window.set_child(form_box)
        
        # --- User Account Section ---
        user_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        form_box.append(user_section)
        
        user_header = Gtk.Label(label="User Account", xalign=0)
        user_header.set_markup('<b>User Account</b>')
        user_section.append(user_header)
        
        # Username field
        username_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        user_section.append(username_box)
        
        username_label = Gtk.Label(label="Username", xalign=0)
        username_label.add_css_class('dim-label')
        username_box.append(username_label)
        
        self.username_entry = Gtk.Entry()
        self.username_entry.set_placeholder_text("e.g., john")
        self.username_entry.connect("changed", self.validate_fields)
        username_box.append(self.username_entry)
        
        self.username_error = Gtk.Label(xalign=0)
        self.username_error.add_css_class('error')
        self.username_error.set_wrap(True)
        self.username_error.set_max_width_chars(50)
        self.username_error.set_visible(False)
        username_box.append(self.username_error)
        
        # Full Name field
        fullname_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        user_section.append(fullname_box)
        
        fullname_label = Gtk.Label(label="Full Name", xalign=0)
        fullname_label.add_css_class('dim-label')
        fullname_box.append(fullname_label)
        
        self.fullname_entry = Gtk.Entry()
        self.fullname_entry.set_placeholder_text("e.g., John Doe")
        self.fullname_entry.connect("changed", self.validate_fields)
        fullname_box.append(self.fullname_entry)
        
        # Password field
        password_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        user_section.append(password_box)
        
        password_label = Gtk.Label(label="Password", xalign=0)
        password_label.add_css_class('dim-label')
        password_box.append(password_label)
        
        self.password_entry = Gtk.PasswordEntry()
        self.password_entry.set_show_peek_icon(True)
        self.password_entry.connect("changed", self.validate_fields)
        password_box.append(self.password_entry)
        
        self.password_strength = Gtk.Label(xalign=0)
        self.password_strength.add_css_class('dim-label')
        password_box.append(self.password_strength)
        
        # Repeat Password field
        repeat_password_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        user_section.append(repeat_password_box)
        
        repeat_password_label = Gtk.Label(label="Repeat Password", xalign=0)
        repeat_password_label.add_css_class('dim-label')
        repeat_password_box.append(repeat_password_label)
        
        self.repeat_password_entry = Gtk.PasswordEntry()
        self.repeat_password_entry.set_show_peek_icon(True)
        self.repeat_password_entry.connect("changed", self.validate_fields)
        repeat_password_box.append(self.repeat_password_entry)
        
        self.password_match_error = Gtk.Label(xalign=0)
        self.password_match_error.add_css_class('error')
        self.password_match_error.set_wrap(True)
        self.password_match_error.set_max_width_chars(50)
        self.password_match_error.set_visible(False)
        repeat_password_box.append(self.password_match_error)
        
        # --- System Configuration Section ---
        system_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        form_box.append(system_section)
        
        separator1 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        system_section.append(separator1)
        
        system_header = Gtk.Label(label="System Configuration", xalign=0)
        system_header.set_markup('<b>System Configuration</b>')
        system_section.append(system_header)
        
        # Computer Name field
        hostname_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        system_section.append(hostname_box)
        
        hostname_label = Gtk.Label(label="Computer's Name", xalign=0)
        hostname_label.add_css_class('dim-label')
        hostname_box.append(hostname_label)
        
        self.hostname_entry = Gtk.Entry()
        self.hostname_entry.set_text("Linexin-PC")
        self.hostname_entry.connect("changed", self.validate_fields)
        hostname_box.append(self.hostname_entry)
        
        self.hostname_error = Gtk.Label(xalign=0)
        self.hostname_error.add_css_class('error')
        self.hostname_error.set_wrap(True)
        self.hostname_error.set_max_width_chars(50)
        self.hostname_error.set_visible(False)
        hostname_box.append(self.hostname_error)
        
        # --- Root Account Section ---
        root_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        form_box.append(root_section)
        
        separator2 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        root_section.append(separator2)
        
        # Root account toggle
        root_toggle_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        root_section.append(root_toggle_box)
        
        root_toggle_label = Gtk.Label(label="Enable Root account?", xalign=0, hexpand=True)
        root_toggle_label.set_markup('<b>Enable Root account?</b>')
        root_toggle_box.append(root_toggle_label)
        
        self.root_switch = Gtk.Switch()
        self.root_switch.set_valign(Gtk.Align.CENTER)
        self.root_switch.connect("notify::active", self.on_root_toggled)
        root_toggle_box.append(self.root_switch)
        
        # Root password fields (initially hidden)
        self.root_fields_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.root_fields_box.set_visible(False)
        root_section.append(self.root_fields_box)
        
        # Root Password field
        root_password_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.root_fields_box.append(root_password_box)
        
        root_password_label = Gtk.Label(label="Root Password", xalign=0)
        root_password_label.add_css_class('dim-label')
        root_password_box.append(root_password_label)
        
        self.root_password_entry = Gtk.PasswordEntry()
        self.root_password_entry.set_show_peek_icon(True)
        self.root_password_entry.connect("changed", self.validate_fields)
        root_password_box.append(self.root_password_entry)
        
        self.root_password_strength = Gtk.Label(xalign=0)
        self.root_password_strength.add_css_class('dim-label')
        root_password_box.append(self.root_password_strength)
        
        # Repeat Root Password field
        repeat_root_password_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.root_fields_box.append(repeat_root_password_box)
        
        repeat_root_password_label = Gtk.Label(label="Repeat Root Password", xalign=0)
        repeat_root_password_label.add_css_class('dim-label')
        repeat_root_password_box.append(repeat_root_password_label)
        
        self.repeat_root_password_entry = Gtk.PasswordEntry()
        self.repeat_root_password_entry.set_show_peek_icon(True)
        self.repeat_root_password_entry.connect("changed", self.validate_fields)
        repeat_root_password_box.append(self.repeat_root_password_entry)
        
        self.root_password_match_error = Gtk.Label(xalign=0)
        self.root_password_match_error.add_css_class('error')
        self.root_password_match_error.set_wrap(True)
        self.root_password_match_error.set_max_width_chars(50)
        self.root_password_match_error.set_visible(False)
        repeat_root_password_box.append(self.root_password_match_error)
        
        # --- Navigation Buttons ---
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        button_box.set_halign(Gtk.Align.CENTER)
        self.append(button_box)
        
        self.btn_back = Gtk.Button(label="Back")
        self.btn_back.add_css_class('buttons_all')
        button_box.append(self.btn_back)
        
        self.btn_proceed = Gtk.Button(label="Install the system")
        self.btn_proceed.add_css_class('suggested-action')
        self.btn_proceed.add_css_class('buttons_all')
        self.btn_proceed.set_sensitive(False)
        self.btn_proceed.connect("clicked", self.on_continue_clicked)
        button_box.append(self.btn_proceed)
        
        # Initial validation
        self.validate_fields()
        get_localization_manager().update_widget_tree(self)
    
    def on_root_toggled(self, switch, param):
        """Handle root account toggle."""
        self.root_enabled = switch.get_active()
        self.root_fields_box.set_visible(self.root_enabled)
        
        # Clear root password fields when disabled
        if not self.root_enabled:
            self.root_password_entry.set_text("")
            self.repeat_root_password_entry.set_text("")
        
        self.validate_fields()
    
    def check_password_strength(self, password):
        """Check password strength and return a rating."""
        if not password:
            return "", ""
        
        # Define translation keys as variables
        at_least_8 = _("at least 8 characters")
        lower_letters = _("lowercase letters")
        upper_letters = _("uppercase letters")
        numbers_text = _("numbers")
        special_characters = _("special characters")
        weak = _("Weak")
        fair = _("Fair")
        good = _("Good")
        strong = _("Strong")
        add_text = _("add")
        
        strength = 0
        feedback = []
        
        if len(password) >= 8:
            strength += 1
        else:
            feedback.append(at_least_8)
        
        if re.search(r'[a-z]', password):
            strength += 1
        else:
            feedback.append(lower_letters)
        
        if re.search(r'[A-Z]', password):
            strength += 1
        else:
            feedback.append(upper_letters)
        
        if re.search(r'[0-9]', password):
            strength += 1
        else:
            feedback.append(numbers_text)
        
        if re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            strength += 1
        else:
            feedback.append(special_characters)
        
        if strength <= 2:
            color = "red"
            text = weak
        elif strength <= 3:
            color = "orange"
            text = fair
        elif strength <= 4:
            color = "yellow"
            text = good
        else:
            color = "green"
            text = strong
        
        if feedback and strength < 5:
            feedback_list = ", ".join(feedback[:2])
            text += f" ({add_text} {feedback_list})"
        
        return f'<span foreground="{color}">{text}</span>', strength
    
    def validate_username(self, username):
        """Validate username according to Linux standards."""
        if not username:
            return False, "Username is required"
        
        if not re.match(r'^[a-z_][a-z0-9_-]*$', username):
            return False, "Username must start with a letter or underscore, and contain only lowercase letters, numbers, underscores, and hyphens"
        
        if len(username) > 32:
            return False, "Username must be 32 characters or less"
        
        # Check for reserved usernames
        reserved = ['root', 'daemon', 'bin', 'sys', 'sync', 'games', 'man', 'lp', 
                   'mail', 'news', 'uucp', 'proxy', 'www-data', 'backup', 'nobody']
        if username in reserved:
            return False, f"'{username}' is a reserved system username"
        
        return True, ""
    
    def validate_hostname(self, hostname):
        """Validate hostname according to RFC standards."""
        if not hostname:
            return False, "Computer name is required"
        
        if not re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$', hostname):
            return False, "Must start and end with a letter or number, and contain only letters, numbers, and hyphens"
        
        if len(hostname) > 63:
            return False, "Computer name must be 63 characters or less"
        
        return True, ""
    
    def validate_fields(self, widget=None):
        """Validate all form fields and update UI accordingly."""
        self.validation_errors.clear()
        all_valid = True
        
        # Validate username
        username = self.username_entry.get_text()
        username_valid, username_error = self.validate_username(username)
        if not username_valid:
            self.username_error.set_text(username_error)
            self.username_error.set_visible(True)
            self.validation_errors.add("username")
            all_valid = False
        else:
            self.username_error.set_visible(False)
        
        # Validate hostname
        hostname = self.hostname_entry.get_text()
        hostname_valid, hostname_error = self.validate_hostname(hostname)
        if not hostname_valid:
            self.hostname_error.set_text(hostname_error)
            self.hostname_error.set_visible(True)
            self.validation_errors.add("hostname")
            all_valid = False
        else:
            self.hostname_error.set_visible(False)
        
        # Check user password strength
        user_password = self.password_entry.get_text()
        repeat_password = self.repeat_password_entry.get_text()
        
        if not user_password:
            self.password_strength.set_text("")
            self.validation_errors.add("no_password")
            all_valid = False
        else:
            strength_text, strength_level = self.check_password_strength(user_password)
            self.password_strength.set_markup(strength_text)
        
        # Check user password match - FIXED LOGIC
        if user_password and repeat_password:
            if user_password != repeat_password:
                self.password_match_error.set_text("Passwords do not match")
                self.password_match_error.set_visible(True)
                self.validation_errors.add("password_mismatch")
                all_valid = False
            else:
                self.password_match_error.set_visible(False)
        elif user_password and not repeat_password:
            # User has entered password but not repeated it
            self.password_match_error.set_text("Repeat Password")
            self.password_match_error.set_visible(True)
            self.validation_errors.add("password_not_repeated")
            all_valid = False
        elif not user_password and repeat_password:
            # User has entered repeat password but not main password
            self.password_match_error.set_text("Please enter your password first")
            self.password_match_error.set_visible(True)
            self.validation_errors.add("password_missing")
            all_valid = False
        else:
            # Both fields are empty
            self.password_match_error.set_visible(False)
        
        # Validate root password if enabled
        if self.root_enabled:
            root_password = self.root_password_entry.get_text()
            repeat_root_password = self.repeat_root_password_entry.get_text()
            
            if not root_password:
                self.root_password_strength.set_text("")
                self.validation_errors.add("no_root_password")
                all_valid = False
            else:
                strength_text, strength_level = self.check_password_strength(root_password)
                self.root_password_strength.set_markup(strength_text)
            
            # Check root password match - FIXED LOGIC
            if root_password and repeat_root_password:
                if root_password != repeat_root_password:
                    self.root_password_match_error.set_text("Root passwords do not match")
                    self.root_password_match_error.set_visible(True)
                    self.validation_errors.add("root_password_mismatch")
                    all_valid = False
                else:
                    self.root_password_match_error.set_visible(False)
            elif root_password and not repeat_root_password:
                # User has entered root password but not repeated it
                self.root_password_match_error.set_text("Please repeat your root password")
                self.root_password_match_error.set_visible(True)
                self.validation_errors.add("root_password_not_repeated")
                all_valid = False
            elif not root_password and repeat_root_password:
                # User has entered repeat root password but not main root password
                self.root_password_match_error.set_text("Please enter your root password first")
                self.root_password_match_error.set_visible(True)
                self.validation_errors.add("root_password_missing")
                all_valid = False
            else:
                # Both root password fields are empty
                self.root_password_match_error.set_visible(False)
        
        # Check if required fields are filled
        if not self.fullname_entry.get_text():
            self.validation_errors.add("no_fullname")
            all_valid = False
        
        self.btn_proceed.set_sensitive(all_valid)
        return all_valid
    
    def generate_salt(self, length=16):
        """Generate a random salt for password hashing."""
        chars = string.ascii_letters + string.digits + './'
        return ''.join(random.choice(chars) for _ in range(length))
    
    def hash_password(self, password):
        """
        Hash password using SHA512 (standard for modern Linux systems).
        Uses openssl as a fallback if crypt module is not available.
        """
        salt = self.generate_salt()
        
        # Try using openssl command (standard on most Linux systems)
        try:
            result = subprocess.run(
                ['openssl', 'passwd', '-6', '-salt', salt, password],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        
        # Try using Python's crypt module if available
        try:
            import crypt
            return crypt.crypt(password, f'$6${salt}$')
        except ImportError:
            pass
        
        # Fallback: use mkpasswd if available
        try:
            result = subprocess.run(
                ['mkpasswd', '-m', 'sha-512', '-S', salt, password],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        
        # Last resort: use a simple SHA512 hash (less secure but better than plain text)
        print("Warning: Using fallback password hashing (less secure)")
        salted = salt + password
        hash_obj = hashlib.sha512(salted.encode())
        return f"$6${salt}${hash_obj.hexdigest()}"
    
    def on_continue_clicked(self, button):
        """Handle the continue button click and generate configuration files."""
        if not self.validate_fields():
            return
        
        # Collect user data and hash passwords
        user_data = {
            'username': self.username_entry.get_text(),
            'fullname': self.fullname_entry.get_text(),
            'password_hash': self.hash_password(self.password_entry.get_text()),
            'hostname': self.hostname_entry.get_text(),
            'root_enabled': self.root_enabled
        }
        
        if self.root_enabled:
            user_data['root_password_hash'] = self.hash_password(self.root_password_entry.get_text())
        
        # Create configuration directory in the specified output location
        config_dir = os.path.join(self.config_output_dir, 'installer_config')
        os.makedirs(config_dir, exist_ok=True)
        
        try:
            # Generate single combined configuration script
            self.generate_configuration_script(config_dir, user_data)
            
            print(f"Configuration script generated successfully in {config_dir}")
            
            # Emit signal or callback for next step
            # self.emit('user-created', user_data)
            
        except Exception as e:
            print(f"Error generating configuration files: {e}")
            # Show error dialog
            dialog = Adw.MessageDialog(
                transient_for=self.get_root(),
                heading="Error",
                body=f"Failed to generate configuration files: {str(e)}\n\nTry specifying a different output directory with more space."
            )
            dialog.add_response("ok", "OK")
            dialog.present()
    
    def generate_configuration_script(self, config_dir, user_data):
        """Generate a single script that handles all user and system configuration."""
        script_file = os.path.join(config_dir, 'add_users.sh')
        
        # Password hashes are already generated, no need to escape
        user_password_hash = user_data['password_hash']
        root_password_hash = user_data.get('root_password_hash', '') if user_data['root_enabled'] else ''
        
        script_content = f"""#!/bin/bash
# System configuration script generated by Linexin Installer
# This script should be run in the chrooted environment
# Passwords are stored as SHA512 hashes for security

set -e

echo "========================================="
echo "Starting system configuration..."
echo "========================================="

# Configuration variables
USERNAME='{user_data['username']}'
FULLNAME='{user_data['fullname']}'
USER_PASSWORD_HASH='{user_password_hash}'
HOSTNAME='{user_data['hostname']}'
ROOT_ENABLED={'true' if user_data['root_enabled'] else 'false'}
ROOT_PASSWORD_HASH='{root_password_hash}'

# Function to report errors
error_exit() {{
    echo "Error: $1" >&2
    exit 1
}}

# =========================================
# HOSTNAME CONFIGURATION
# =========================================
echo ""
echo "Configuring hostname..."
echo "Setting hostname to: $HOSTNAME"

# Set hostname
echo "$HOSTNAME" > /etc/hostname

# Update /etc/hosts
echo "Updating /etc/hosts..."
if ! grep -q "127.0.1.1" /etc/hosts; then
    echo "127.0.1.1	$HOSTNAME" >> /etc/hosts
else
    sed -i "s/127.0.1.1.*/127.0.1.1	$HOSTNAME/" /etc/hosts
fi

# Ensure localhost entries exist
if ! grep -q "127.0.0.1.*localhost" /etc/hosts; then
    sed -i '1i 127.0.0.1	localhost' /etc/hosts
fi

if ! grep -q "::1.*localhost" /etc/hosts; then
    echo "::1		localhost" >> /etc/hosts
fi

echo "✓ Hostname configuration completed"

# =========================================
# USER ACCOUNT CREATION
# =========================================
echo ""
echo "Configuring user accounts..."

# Create user account
echo "Creating user account: $USERNAME"
if id "$USERNAME" &>/dev/null; then
    echo "User $USERNAME already exists, updating configuration..."
    # Update groups if user exists
    usermod -aG wheel,audio,video,network,storage,input,power "$USERNAME" || error_exit "Failed to update user groups"
else
    useradd -m -G wheel,audio,video,network,storage,input,power -s /bin/bash -c "$FULLNAME" "$USERNAME" || error_exit "Failed to create user"
    echo "✓ User $USERNAME created successfully"
fi

# Set user password using the hash
echo "Setting password for user $USERNAME"
# Use usermod to set the password hash directly
usermod -p "$USER_PASSWORD_HASH" "$USERNAME" || error_exit "Failed to set user password"
echo "✓ Password set for $USERNAME"

# Create user directories
echo "Creating user directories..."
for dir in Desktop Documents Downloads Music Pictures Videos; do
    mkdir -p "/home/$USERNAME/$dir"
done
echo "✓ User directories created"

# Set proper ownership
chown -R "$USERNAME:$USERNAME" "/home/$USERNAME"

# Configure sudo for wheel group
echo "Configuring sudo access..."
if [ ! -f /etc/sudoers.d/10-installer ]; then
    echo '%wheel ALL=(ALL:ALL) ALL' > /etc/sudoers.d/10-installer
    chmod 440 /etc/sudoers.d/10-installer
    echo "✓ Sudo configured for wheel group"
fi

# =========================================
# ROOT ACCOUNT CONFIGURATION
# =========================================
echo ""
if [ "$ROOT_ENABLED" = "true" ]; then
    echo "Enabling root account..."
    # Set root password using the hash
    usermod -p "$ROOT_PASSWORD_HASH" root || error_exit "Failed to set root password"
    # Ensure root account is unlocked
    passwd -u root &>/dev/null || true
    echo "✓ Root account enabled with password"
else
    echo "Disabling root account..."
    # Lock root account
    passwd -l root &>/dev/null || true
    echo "✓ Root account disabled"
fi

# =========================================
# SHELL CONFIGURATION
# =========================================
echo ""
echo "Setting up shell configuration..."

# Set up user's shell configuration
if [ -f /etc/skel/.bashrc ]; then
    cp -f /etc/skel/.bashrc "/home/$USERNAME/.bashrc"
fi

if [ -f /etc/skel/.bash_profile ]; then
    cp -f /etc/skel/.bash_profile "/home/$USERNAME/.bash_profile"
fi

# If zsh is installed and skel has zshrc
if command -v zsh &>/dev/null; then
    if [ -f /etc/skel/.zshrc ]; then
        cp -f /etc/skel/.zshrc "/home/$USERNAME/.zshrc"
    fi
    # Set zsh as default shell if available
    chsh -s /bin/zsh "$USERNAME" &>/dev/null || true
    echo "✓ Zsh set as default shell"
fi

# Copy any other skel files
if [ -d /etc/skel ]; then
    echo "Copying skeleton files..."
    find /etc/skel -mindepth 1 -maxdepth 1 \\( -name ".*" -o -type d \\) | while read -r item; do
        basename_item=$(basename "$item")
        if [ ! -e "/home/$USERNAME/$basename_item" ]; then
            cp -r "$item" "/home/$USERNAME/"
        fi
    done
fi

# Fix ownership again after copying files
chown -R "$USERNAME:$USERNAME" "/home/$USERNAME"

# Create .config directory if it doesn't exist
mkdir -p "/home/$USERNAME/.config"
chown "$USERNAME:$USERNAME" "/home/$USERNAME/.config"

# Set up XDG user directories
if command -v xdg-user-dirs-update &>/dev/null; then
    su - "$USERNAME" -c "xdg-user-dirs-update" &>/dev/null || true
    echo "✓ XDG user directories configured"
fi

# =========================================
# SECURITY CLEANUP
# =========================================
echo ""
echo "Performing security cleanup..."

# Ensure shadow file has correct permissions
chmod 000 /etc/shadow
chmod 000 /etc/gshadow

echo "✓ Security settings applied"

# =========================================
# SUMMARY
# =========================================
echo ""
echo "========================================="
echo "System configuration completed successfully!"
echo "========================================="
echo "  Hostname: $HOSTNAME"
echo "  Username: $USERNAME"
echo "  Full Name: $FULLNAME"
echo "  Groups: wheel, audio, video, network, storage, input, power"
echo "  Root account: $([ "$ROOT_ENABLED" = "true" ] && echo "Enabled" || echo "Disabled")"
echo "========================================="
"""
        
        with open(script_file, 'w') as f:
            f.write(script_content)
        
        # Set restrictive permissions on the script since it contains password hashes
        # Only root should be able to read/execute this script
        os.chmod(script_file, 0o700)
        
        print(f"Configuration script saved to {script_file} (with restricted permissions)")
    
    def set_config_output_dir(self, directory):
        """Set the output directory for configuration files."""
        if os.path.exists(directory) and os.access(directory, os.W_OK):
            self.config_output_dir = directory
            return True
        else:
            print(f"Warning: Directory {directory} is not writable, using {self.config_output_dir}")
            return False
    
    def get_user_data(self):
        """Public method to get the configured user data."""
        if not self.validate_fields():
            return None
        
        return {
            'username': self.username_entry.get_text(),
            'fullname': self.fullname_entry.get_text(),
            'hostname': self.hostname_entry.get_text(),
            'root_enabled': self.root_enabled
        }


if __name__ == "__main__":
    # Example window to display the widget
    app = Gtk.Application()
    
    def on_activate(app):
        win = Adw.ApplicationWindow(application=app, title="User Creation Test")
        win.set_default_size(600, 800)
        
        # You can specify a custom output directory here
        # For example, if you have a mounted partition at /mnt/install
        # user_widget = UserCreationWidget(config_output_dir="/mnt/install")
        
        # Or use the default /tmp directory
        user_widget = UserCreationWidget()
        
        # Or set it after creation
        # user_widget.set_config_output_dir("/path/to/mounted/partition")
        
        # Example callback for back button
        def on_back():
            print("Back button clicked")
        
        user_widget.btn_back.connect("clicked", lambda x: on_back())
        
        win.set_content(user_widget)
        win.present()
    
    app.connect('activate', on_activate)
    app.run(None)