#!/usr/bin/env python
# -*- coding: utf-8 -*-

import gi
import os
import gettext
import locale
import math

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

# Import GLib for the timer and Adw for the animation
from gi.repository import Gtk, Adw, Gdk, GLib

# --- i18n Setup ---
WIDGET_NAME = "linexin-installer-welcome-widget"
LOCALE_DIR = "/usr/share/locale"
locale.setlocale(locale.LC_ALL, '')
locale.bindtextdomain(WIDGET_NAME, LOCALE_DIR)
gettext.bindtextdomain(WIDGET_NAME, LOCALE_DIR)
gettext.textdomain(WIDGET_NAME)
_ = gettext.gettext


class WelcomeWidget(Gtk.Box):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # --- Language Lists for Animation ---
        self.translations = [
            "Welcome to", "Witaj w", "Bienvenido a", "Bienvenue à",
            "Willkommen bei", "Benvenuto in", "Bem-vindo a", "Добро пожаловать в",
            "へようこそ", "欢迎来到", "مرحبا بك في", "में आपका स्वागत है", "Welkom bij",
            "Välkommen till", "'a hoş geldiniz", "에 오신 것을 환영합니다", "Καλώς ήρθατε στο",
            "Ласкаво просимо до", "Vítejte v", "Tervetuloa"
        ]
        
        self.button_translations = [
            "Begin Installation", "Rozpocznij instalację", "Iniciar instalación", "Commencer l'installation",
            "Installation beginnen", "Inizia l'installazione", "Iniciar instalação", "Начать установку",
            "インストールを開始", "开始安装", "بدء التثبيت", "इंस्टॉलेशन शुरू करें", "Installatie beginnen",
            "Påbörja installationen", "Kuruluma Başla", "설치 시작", "Έναρξη εγκατάστασης",
            "Почати встановлення", "Zahájit instalaci", "Aloita asennus"
        ]
        
        self.current_lang_index = 0
        self.animation_running = False
        self.initial_animation_done = False
        self.animation_scheduled = False

        script_dir = os.path.dirname(os.path.abspath(__file__))
        image_path = os.path.join(script_dir, "images", "logo.png")

        self.set_orientation(Gtk.Orientation.VERTICAL)
        self.set_spacing(0)
        self.set_valign(Gtk.Align.CENTER)
        self.set_halign(Gtk.Align.CENTER)

        # Add CSS for enhanced styling
        self.setup_custom_css()

        # Create main container with some breathing room
        self.main_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        self.main_container.set_margin_top(20)
        self.main_container.set_margin_bottom(20)
        self.main_container.set_margin_start(40)
        self.main_container.set_margin_end(40)
        self.main_container.set_valign(Gtk.Align.CENTER)
        self.main_container.set_halign(Gtk.Align.CENTER)
        
        # Add CSS class for animation
        self.main_container.add_css_class("main_widget_container")

        # Welcome text container - fixed height to prevent layout shifts
        text_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        text_container.set_halign(Gtk.Align.CENTER)
        text_container.set_valign(Gtk.Align.CENTER)
        text_container.set_size_request(-1, 50)

        # Animated welcome label
        self.welcome_label = Gtk.Label()
        self.welcome_label.add_css_class("welcome_text")
        self.welcome_label.set_markup(f'<span size="x-large" weight="bold">{_("Welcome to")}</span>')
        self.welcome_label.set_halign(Gtk.Align.CENTER)
        self.welcome_label.set_valign(Gtk.Align.CENTER)
        text_container.append(self.welcome_label)

        self.main_container.append(text_container)

        # Logo with scaling animation
        self.logo_container = Gtk.Box(halign=Gtk.Align.CENTER)
        self.welcome_image = Gtk.Picture.new_for_filename(image_path)
        self.welcome_image.set_can_shrink(True)
        self.welcome_image.set_halign(Gtk.Align.CENTER)
        self.welcome_image.set_valign(Gtk.Align.CENTER)
        self.welcome_image.add_css_class("logo_image")
        self.welcome_image.set_size_request(140, 140)
        self.logo_container.append(self.welcome_image)
        self.main_container.append(self.logo_container)

        # Button container with hover effects
        button_container = Gtk.Box(halign=Gtk.Align.CENTER, spacing=20)
        button_container.set_margin_top(15)
        
        self.btn_install = Gtk.Button(label=_("Begin Installation"))
        self.btn_install.add_css_class("suggested-action")
        self.btn_install.add_css_class("proceed_button")
        self.btn_install.add_css_class("animated_button")
        self.btn_install.set_size_request(200, 50)
        
        # Add hover effects
        hover_controller = Gtk.EventControllerMotion()
        hover_controller.connect("enter", self.on_button_hover_enter)
        hover_controller.connect("leave", self.on_button_hover_leave)
        self.btn_install.add_controller(hover_controller)
        
        button_container.append(self.btn_install)
        self.main_container.append(button_container)

        self.append(self.main_container)
        
        # Initially hide everything for the zoom animation
        self.main_container.set_opacity(0)
        
        # Connect to the map signal to trigger animation when widget becomes visible
        self.connect("map", self.on_widget_mapped)

    def setup_custom_css(self):
        """Setup enhanced CSS for modern look and animations"""
        css_provider = Gtk.CssProvider()
        css_data = """
        .main_widget_container {
            transition: all 1.2s cubic-bezier(0.25, 0.46, 0.45, 0.94);
        }
        
        .welcome_text {
            text-shadow: 0 1px 2px rgba(0,0,0,0.1);
            transition: all 0.5s ease;
        }
        
        .subtitle_text {
            font-style: italic;
            text-shadow: 0 1px 2px rgba(0,0,0,0.1);
        }
        
        .logo_image {
            transition: opacity 0.6s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        }
        
        .animated_button {
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            border-radius: 25px;
            font-weight: bold;
            text-shadow: 0 1px 2px rgba(0,0,0,0.1);
            box-shadow: 0 4px 12px rgba(201, 148, 218, 0.3);
        }
        
        .animated_button:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(201, 148, 218, 0.3);
        }
        
        .animated_button:active {
            transform: translateY(1px);
            box-shadow: 0 2px 8px rgba(201, 148, 218, 0.3);
        }
        
        /* Pulse animation for active elements */
        @keyframes pulse {
            0% { transform: scale(1); }
            50% { transform: scale(1.05); }
            100% { transform: scale(1); }
        }
        
        .pulse-animation {
            animation: pulse 2s ease-in-out infinite;
        }
        
        /* Zoom-in animation */
        @keyframes zoomIn {
            from {
                transform: scale(1.5);
                opacity: 0;
            }
            to {
                transform: scale(1);
                opacity: 1;
            }
        }
        
        .zoom-in-animation {
            animation: zoomIn 1.2s cubic-bezier(0.25, 0.46, 0.45, 0.94) forwards;
        }
        """
        css_provider.load_from_data(css_data.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def on_widget_mapped(self, widget):
        """Called when widget is mapped (becomes visible)"""
        if not self.animation_scheduled and not self.initial_animation_done:
            self.animation_scheduled = True
            # Small delay to ensure everything is rendered
            GLib.timeout_add(200, self.start_entrance_animation)
    
    def start_entrance_animation(self):
        """Start the smooth zoom-out entrance animation after widget is visible"""
        if self.initial_animation_done:
            return False
            
        self.initial_animation_done = True
        self.animation_scheduled = False
        
        # Create a smooth zoom-out effect with opacity fade
        # Starting from scale 1.5 (appears closer) to scale 1.0 (normal size)
        # Combined with opacity animation from 0 to 1
        
        def animation_callback(value, data):
            # Calculate scale: from 1.5 to 1.0
            scale = 1.5 - (0.5 * value)
            
            # Apply both opacity and scale
            self.main_container.set_opacity(value)
            
            # Use CSS transform for scaling - requires GTK 4.6+
            # For older versions, we'll rely on opacity only
            try:
                # This is a conceptual approach - actual implementation may vary
                # depending on GTK version and available methods
                transform = Gdk.Transform.new()
                transform = transform.scale(scale, scale)
                # Note: Direct transform application may require custom widget or CSS
            except:
                # Fallback to just opacity if transform is not available
                pass
        
        # Create the animation target
        target = Adw.CallbackAnimationTarget.new(animation_callback, None)
        
        # Create the timed animation with smooth easing
        animation = Adw.TimedAnimation.new(
            self.main_container,
            0.0,  # Start value (fully transparent)
            1.0,  # End value (fully opaque)
            1200, # Duration in milliseconds
            target
        )
        
        # Use a smooth easing function for natural motion
        animation.set_easing(Adw.Easing.EASE_OUT_QUAD)  # Changed from CUBIC for smoother feel
        
        # Connect completion handler to start language cycling
        animation.connect("done", self.on_entrance_animation_complete)
        
        # Play the animation
        animation.play()
        
        # Alternative approach using multiple synchronized animations
        self.animate_entrance_with_components()
        
        return False

    def animate_entrance_with_components(self):
        """Animate individual components with staggered timing for smoother effect"""
        # Since we can't directly apply CSS transforms in GTK4 easily,
        # we'll simulate the zoom effect using margin animations
        
        # Start with larger margins (simulating zoom) - reduced initial margin
        initial_margin = 80  # Reduced from 120
        self.main_container.set_margin_top(initial_margin + 60)
        self.main_container.set_margin_bottom(initial_margin + 60)
        self.main_container.set_margin_start(initial_margin + 80)
        self.main_container.set_margin_end(initial_margin + 80)
        
        # Animate margins back to normal
        def margin_callback(value, data):
            current_margin = initial_margin * (1 - value)
            self.main_container.set_margin_top(int(current_margin + 60))
            self.main_container.set_margin_bottom(int(current_margin + 60))
            self.main_container.set_margin_start(int(current_margin + 80))
            self.main_container.set_margin_end(int(current_margin + 80))
        
        margin_target = Adw.CallbackAnimationTarget.new(margin_callback, None)
        margin_animation = Adw.TimedAnimation.new(
            self.main_container,
            0.0,
            1.0,
            1200,
            margin_target
        )
        margin_animation.set_easing(Adw.Easing.EASE_OUT_EXPO)
        margin_animation.play()

    def on_entrance_animation_complete(self, animation):
        """Called when the entrance animation completes"""
        # Start language cycling after a delay
        GLib.timeout_add_seconds(3, self.start_language_cycling)

    def on_button_hover_enter(self, controller, x, y):
        """Enhanced hover enter effect"""
        self.btn_install.add_css_class("pulse-animation")

    def on_button_hover_leave(self, controller):
        """Enhanced hover leave effect"""
        self.btn_install.remove_css_class("pulse-animation")

    def start_language_cycling(self):
        """Begin the language cycling animation loop"""
        if not self.animation_running:
            self.animation_running = True
            GLib.timeout_add_seconds(3, self.cycle_language)
        return False

    def cycle_language(self):
        """Main language cycling with enhanced animations"""
        if not self.animation_running:
            return False
            
        self.start_text_fade_out_enhanced()
        return True

    def _on_welcome_opacity_update(self, value, user_data):
        """Update welcome label opacity"""
        self.welcome_label.set_opacity(value)

    def _on_button_opacity_update(self, value, user_data):
        """Update button opacity"""
        self.btn_install.set_opacity(value)

    def start_text_fade_out_enhanced(self):
        """Enhanced fade out with multiple elements"""
        welcome_target = Adw.CallbackAnimationTarget.new(self._on_welcome_opacity_update, None)
        welcome_animation = Adw.TimedAnimation.new(
            self.welcome_label, 1.0, 0.0, 400, welcome_target
        )
        welcome_animation.set_easing(Adw.Easing.EASE_IN_CUBIC)
        
        button_target = Adw.CallbackAnimationTarget.new(self._on_button_opacity_update, None)
        button_animation = Adw.TimedAnimation.new(
            self.btn_install, 1.0, 0.0, 400, button_target
        )
        button_animation.set_easing(Adw.Easing.EASE_IN_CUBIC)
        
        welcome_animation.connect("done", self.change_text_and_fade_in_enhanced)
        
        welcome_animation.play()
        button_animation.play()

    def change_text_and_fade_in_enhanced(self, animation):
        """Enhanced text change with smooth transitions"""
        self.current_lang_index = (self.current_lang_index + 1) % len(self.translations)
        
        new_text = self.translations[self.current_lang_index]
        self.welcome_label.set_markup(f'<span size="x-large" weight="bold">{new_text}</span>')

        new_button_text = self.button_translations[self.current_lang_index]
        self.btn_install.set_label(new_button_text)

        welcome_target = Adw.CallbackAnimationTarget.new(self._on_welcome_opacity_update, None)
        welcome_fade_in = Adw.TimedAnimation.new(
            self.welcome_label, 0.0, 1.0, 600, welcome_target
        )
        welcome_fade_in.set_easing(Adw.Easing.EASE_OUT_BACK)
        
        button_target = Adw.CallbackAnimationTarget.new(self._on_button_opacity_update, None)
        button_fade_in = Adw.TimedAnimation.new(
            self.btn_install, 0.0, 1.0, 600, button_target
        )
        button_fade_in.set_easing(Adw.Easing.EASE_OUT_CUBIC)
        
        welcome_fade_in.play()
        GLib.timeout_add(150, lambda: button_fade_in.play())

        GLib.timeout_add_seconds(5, self.start_text_fade_out_enhanced)

    def stop_animations(self):
        """Stop all running animations"""
        self.animation_running = False


class EnhancedWelcomeApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.linexin.installer.welcome")
        self.connect('activate', self.on_activate)

    def on_activate(self, app):
        # Create window with modern styling
        self.win = Adw.ApplicationWindow(application=app)
        self.win.set_title("LineXin OS Installer")
        self.win.set_default_size(800, 600)
        
        # Create and add welcome widget
        self.welcome_widget = WelcomeWidget()
        self.win.set_content(self.welcome_widget)
        
        # Add some window-level effects
        self.win.connect("close-request", self.on_window_close)
        
        # The widget will handle its own animation via the "map" signal
        self.win.present()

    def on_window_close(self, window):
        """Cleanup when window closes"""
        if hasattr(self, 'welcome_widget'):
            self.welcome_widget.stop_animations()
        return False


if __name__ == "__main__":
    app = EnhancedWelcomeApp()
    app.run(None)