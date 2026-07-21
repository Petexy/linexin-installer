#!/usr/bin/env python3


import gi
import json
import os
import weakref
import importlib

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from pathlib import Path
from gi.repository import GObject, Gtk, Adw

class SimpleLocalizationManager(GObject.Object):
    """
    A simple localization manager that automatically finds and updates
    translatable elements without requiring manual registration.
    """
    
    __gtype_name__ = 'SimpleLocalizationManager'
    
    # Signal emitted when language changes
    __gsignals__ = {
        'language-changed': (GObject.SignalFlags.RUN_FIRST, None, (str,))
    }
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        super().__init__()
        self.current_language = "en_US.UTF-8"
        self.original_texts = {}
        self.translations = {}
        self.registered_widgets = []
        self._original_texts = weakref.WeakKeyDictionary()
        self.translations_dir = Path(__file__).parent / "translations"
        self.load_translations()
        self._initialized = True
        
        # Patch Adw.MessageDialog to auto-translate
        self.patch_message_dialog()
        self.patch_preferences_group()
        self.patch_revealer()
        self.patch_clamp()
        self.patch_label()

    def _remember_original(self, widget, field, current_value):
        """Cache the first-seen (English) value for a widget's field and return it.
        Why: after first translation, visible text is no longer a valid key; we must
        always translate from the stable, original English string.
        """
        if widget not in self._original_texts:
            self._original_texts[widget] = {}
        bucket = self._original_texts[widget]
        
        # CRITICAL FIX: Only store text if it's actually an English key
        # Check if current_value exists in English translations
        if field not in bucket and current_value:
            # Only store if this text exists as a key in English translations
            if current_value in self.translations.get("en_US.UTF-8", {}):
                bucket[field] = current_value
            else:
                # If current text is not an English key, it might be already translated
                # Try to find the English key by reverse lookup
                english_key = self._find_english_key(current_value)
                if english_key:
                    bucket[field] = english_key
                    return english_key
        
        return bucket.get(field, current_value)

    def _find_english_key(self, translated_text):
        """Find the English key for a translated text by reverse lookup"""
        if not translated_text:
            return None
        
        # First check if it's already English
        if translated_text in self.translations.get("en_US.UTF-8", {}):
            return translated_text
        
        # Search through all non-English translations to find which English key maps to this text
        for lang_code, trans_dict in self.translations.items():
            if lang_code == "en_US.UTF-8":
                continue
            for english_key, translated_value in trans_dict.items():
                if translated_value == translated_text:
                    return english_key
        
        return None

    def _get_original(self, widget, field, fallback=None):
        """Fetch original English value for a widget's field if remembered."""
        d = self._original_texts.get(widget)
        if not d:
            return fallback
        return d.get(field, fallback)

    def translate_gtk_dialog(self, dialog):
        """Translate a GTK.Dialog and its content"""
        try:
            # Translate dialog title
            title = dialog.get_title()
            if title:
                dialog.set_title(self.get_text(title))
            
            # Recursively translate all children in the content area
            content_area = dialog.get_content_area()
            if content_area:
                self.update_widget_tree(content_area)
        except Exception as e:
            print(f"Error translating GTK dialog: {e}")        
    
    def patch_label(self):
        """Monkey-patch Gtk.Label to auto-translate text and markup"""
        original_init = Gtk.Label.__init__
        original_set_text = Gtk.Label.set_text
        original_set_markup = Gtk.Label.set_markup
        original_set_tooltip_text = Gtk.Label.set_tooltip_text
        
        def patched_init(label_self, **kwargs):
            # Call original init
            original_init(label_self, **kwargs)
            
            # Auto-translate if text was provided in kwargs
            if 'label' in kwargs:
                label_self.set_text(kwargs['label'])
            if 'tooltip_text' in kwargs:
                label_self.set_tooltip_text(kwargs['tooltip_text'])
        
        def patched_set_text(label_self, text):
            if text:
                text = self.get_text(text)
            original_set_text(label_self, text)
        
        def patched_set_markup(label_self, markup):
            if markup:
                # Extract text from markup and translate it
                import re
                # Simple regex to extract text content from markup
                text_matches = re.findall(r'>([^<]+)<', markup)
                for original_text in text_matches:
                    if original_text.strip():
                        translated_text = self.get_text(original_text.strip())
                        if translated_text != original_text.strip():
                            markup = markup.replace(original_text, translated_text)
                
                # Also handle text that might be outside tags
                if '>' not in markup or '<' not in markup:
                    markup = self.get_text(markup)
            original_set_markup(label_self, markup)
        
        def patched_set_tooltip_text(label_self, text):
            if text:
                text = self.get_text(text)
            original_set_tooltip_text(label_self, text)
        
        # Apply patches
        Gtk.Label.__init__ = patched_init
        Gtk.Label.set_text = patched_set_text
        Gtk.Label.set_markup = patched_set_markup
        Gtk.Label.set_tooltip_text = patched_set_tooltip_text

    def patch_revealer(self):
        """Monkey-patch Gtk.Revealer for any tooltip text"""
        original_set_tooltip_text = Gtk.Revealer.set_tooltip_text
        
        def patched_set_tooltip_text(revealer_self, text):
            if text:
                text = self.get_text(text)
            original_set_tooltip_text(revealer_self, text)
        
        # Apply patch
        Gtk.Revealer.set_tooltip_text = patched_set_tooltip_text

    def patch_clamp(self):
        """Monkey-patch Adw.Clamp for any tooltip text"""
        original_set_tooltip_text = Adw.Clamp.set_tooltip_text
        
        def patched_set_tooltip_text(clamp_self, text):
            if text:
                text = self.get_text(text)
            original_set_tooltip_text(clamp_self, text)
        
        # Apply patch
        Adw.Clamp.set_tooltip_text = patched_set_tooltip_text

    def patch_preferences_group(self):
        """Monkey-patch Adw.PreferencesGroup to auto-translate on creation"""
        original_init = Adw.PreferencesGroup.__init__
        original_set_title = Adw.PreferencesGroup.set_title
        original_set_description = Adw.PreferencesGroup.set_description
        
        def patched_init(group_self, **kwargs):
            # Call original init
            original_init(group_self, **kwargs)
            
            # Auto-translate if title/description were provided in kwargs
            if 'title' in kwargs:
                group_self.set_title(kwargs['title'])
            if 'description' in kwargs:
                group_self.set_description(kwargs['description'])
        
        def patched_set_title(group_self, title):
            if title:
                title = self.get_text(title)
            original_set_title(group_self, title)
        
        def patched_set_description(group_self, description):
            if description:
                description = self.get_text(description)
            original_set_description(group_self, description)
        
        # Apply patches
        Adw.PreferencesGroup.__init__ = patched_init
        Adw.PreferencesGroup.set_title = patched_set_title
        Adw.PreferencesGroup.set_description = patched_set_description

    def patch_message_dialog(self):
        """Monkey-patch Adw.MessageDialog to auto-translate on creation"""
        original_init = Adw.MessageDialog.__init__
        original_set_heading = Adw.MessageDialog.set_heading
        original_set_body = Adw.MessageDialog.set_body
        original_add_response = Adw.MessageDialog.add_response
        
        def patched_init(dialog_self, **kwargs):
            # Call original init
            original_init(dialog_self, **kwargs)
            
            # Auto-translate if heading/body were provided in kwargs
            if 'heading' in kwargs:
                dialog_self.set_heading(kwargs['heading'])
            if 'body' in kwargs:
                dialog_self.set_body(kwargs['body'])
        
        def patched_set_heading(dialog_self, heading):
            if heading:
                heading = self.get_text(heading)
            original_set_heading(dialog_self, heading)
        
        def translate_dynamic_text(self, text):
            """Translate text that may contain dynamic parts"""
            # Try direct translation first
            translated = self.get_text(text)
            if translated != text:
                return translated
            
            # Handle patterns with dynamic content
            patterns = [
                # Pattern: "Are you sure you want to remove partition /dev/vda1?"
                (r"Are you sure you want to remove partition (.+)\?", 
                "Are you sure you want to remove partition", "?"),
                # Pattern: "Toggle boot flag for /dev/vda1?"
                (r"Toggle boot flag for (.+)\?", 
                "Toggle boot flag for", "?"),
                # Pattern: "Select filesystem type for /dev/vda1:"
                (r"Select filesystem type for (.+):", 
                "Select filesystem type for", ":"),
                # Pattern: "Change filesystem type for /dev/vda1:"
                (r"Change filesystem type for (.+):", 
                "Change filesystem type for", ":"),
            ]
            
            import re
            for pattern, prefix, suffix in patterns:
                match = re.match(pattern, text)
                if match:
                    dynamic_part = match.group(1)
                    translated_prefix = self.get_text(prefix)
                    translated_suffix = self.get_text(suffix) if suffix and suffix != suffix.strip() else suffix
                    return f"{translated_prefix} {dynamic_part}{translated_suffix}"
            
            return text
        
        def patched_set_body(dialog_self, body):
            if body:
                # Translate body while preserving structure
                lines = body.splitlines()
                translated_lines = []
                for line in lines:
                    if not line.strip():
                        translated_lines.append(line)
                        continue
                    
                    # Handle bullet points
                    bullet = ""
                    stripped = line
                    if stripped.lstrip().startswith("• "):
                        bullet = "• "
                        stripped = stripped.lstrip()[2:].strip()
                    else:
                        stripped = stripped.strip()
                    
                    # Try to translate the line (with dynamic text support)
                    translated = translate_dynamic_text(self, stripped)
                    translated_lines.append(f"{bullet}{translated}")
                
                body = "\n".join(translated_lines)
            original_set_body(dialog_self, body)
        
        def patched_add_response(dialog_self, response_id, label):
            if label:
                label = self.get_text(label)
            original_add_response(dialog_self, response_id, label)
        
        # Apply patches
        Adw.MessageDialog.__init__ = patched_init
        Adw.MessageDialog.set_heading = patched_set_heading
        Adw.MessageDialog.set_body = patched_set_body
        Adw.MessageDialog.add_response = patched_add_response

    def load_translations(self):
        """Load translation data from separate files"""
        # List of supported languages
        supported_languages = [
            "en_US.UTF-8",
            "en_AU.UTF-8",
            "en_GB.UTF-8",
            "en_CA.UTF-8",
            "pl_PL.UTF-8", 
            "fr_FR.UTF-8",
            "de_DE.UTF-8",
            "ru_RU.UTF-8",
            "zh_CN.UTF-8",
            "hi_IN.UTF-8",
            "es_ES.UTF-8",
            "pt_BR.UTF-8",
            "fi_FI.UTF-8"
        ]
        
        for lang_code in supported_languages:
            # Convert language code to module name (e.g., "en_US.UTF-8" -> "en_US")
            module_name = lang_code.replace(".UTF-8", "")
            
            try:
                # Try multiple loading methods
                translation_data = self._load_translation_module(module_name)
                if translation_data:
                    self.translations[lang_code] = translation_data
                    print(f"Loaded translations for {lang_code}")
            except Exception as e:
                print(f"Warning: Could not load translations for {lang_code}: {e}")
                # Create empty dictionary for missing translations
                self.translations[lang_code] = {}    

    def _load_translation_module(self, module_name):
        """Load a translation module using various methods"""
        translation_data = None
        
        # Method 1: Try importing as a Python module
        try:
            if self.translations_dir.exists():
                # Add translations directory to Python path if needed
                import sys
                translations_path = str(self.translations_dir.parent)
                if translations_path not in sys.path:
                    sys.path.insert(0, translations_path)
                
                # Import the module
                module = importlib.import_module(f"translations.{module_name}")
                if hasattr(module, 'translations'):
                    return module.translations
        except ImportError:
            pass
        
        return None

    def reload_translations(self):
        """Reload all translations (useful for development)"""
        self.translations.clear()
        self.load_translations()
        self.update_all_widgets()



    def translate_dialog(self, dialog):
        """Immediately translate a dialog when it's created"""
        try:
            # Translate heading
            heading = dialog.get_heading()
            if heading:
                dialog.set_heading(self.get_text(heading))

            # Translate body with bullet preservation
            body = dialog.get_body()
            if body:
                lines = body.splitlines()
                translated_lines = []
                for line in lines:
                    if not line.strip():
                        translated_lines.append(line)
                        continue
                    
                    # Handle bullet points
                    bullet = ""
                    stripped = line
                    if stripped.lstrip().startswith("• "):
                        bullet = "• "
                        stripped = stripped.lstrip()[2:].strip()
                    else:
                        stripped = stripped.strip()
                    
                    translated = self.get_text(stripped)
                    translated_lines.append(f"{bullet}{translated}")
                
                dialog.set_body("\n".join(translated_lines))
            
            # Translate response labels
            responses = []
            # Unfortunately, GTK4 doesn't provide a direct way to get response labels
            # So we'll handle this when creating dialogs
            
        except Exception as e:
            print(f"Error translating dialog: {e}")


    def register_widget(self, widget):
        """Register a top-level widget for automatic translation updates"""
        if widget not in self.registered_widgets:
            self.registered_widgets.append(widget)
            print(f"Registered widget for translation: {widget.__class__.__name__}")
    
    def set_language(self, language_code):
        """Set the current language and update all registered widgets"""
        if language_code in self.translations:
            old_language = self.current_language
            self.current_language = language_code
            if old_language != language_code:
                print(f"Language changed from {old_language} to {language_code}")
                self.update_all_widgets()
                self.emit('language-changed', language_code)
            return True
        else:
            print(f"Warning: Language {language_code} not available, keeping {self.current_language}")
            return False
    
    def update_all_widgets(self):
        """Update all registered widgets by traversing their widget trees"""
        for widget in self.registered_widgets:
            if widget and not widget.get_destroyed() if hasattr(widget, 'get_destroyed') else True:
                self.update_widget_tree(widget)
    
    def update_widget_tree(self, widget):
        """Recursively update all translatable elements in a widget tree"""
        try:
            # Update current widget if it's translatable
            self.update_widget(widget)
            
            # Recursively update children
            if hasattr(widget, 'get_first_child'):
                # GTK4 style iteration
                child = widget.get_first_child()
                while child:
                    self.update_widget_tree(child)
                    child = child.get_next_sibling()
            elif hasattr(widget, 'get_child'):
                # Single child containers
                child = widget.get_child()
                if child:
                    self.update_widget_tree(child)
            elif hasattr(widget, 'get_children'):
                # GTK3 style (fallback)
                for child in widget.get_children():
                    self.update_widget_tree(child)
                    
                    
        except Exception as e:
            # Silently continue if we can't access a widget
            pass
    
    def update_widget(self, widget):
        """Update a single widget if it contains translatable text.
        This version preserves original English keys so language can be switched
        multiple times without losing the lookup source.
        """
        try:
            widget_type = type(widget).__name__

            # Gtk.Button
            if isinstance(widget, Gtk.Button):
                # Remember the original English label once
                original = self._remember_original(widget, "button.label", widget.get_label())
                if original:
                    translated = self.get_text(original)
                    if translated != widget.get_label():
                        widget.set_label(translated)

            # Gtk.Label (preserve markup if present)
            elif isinstance(widget, Gtk.Label):
                # Plain text (no markup)
                original_plain = self._remember_original(widget, "label.text_plain", widget.get_text())
                # Markup template (if any). We keep the first-seen markup structure.
                current_markup = widget.get_label()
                original_markup = self._remember_original(widget, "label.markup", current_markup)

                if original_plain:
                    translated = self.get_text(original_plain)
                    # If markup is used, rebuild using original markup so we don't replace
                    # inside already-translated strings.
                    if original_markup and ("<" in original_markup and ">" in original_markup):
                        import re
                        if "<span" in original_markup and "</span>" in original_markup:
                            # Keep original span attributes
                            match = re.match(r"<span([^>]*)>.*</span>", original_markup)
                            if match:
                                span_attrs = match.group(1)
                                widget.set_markup(f"<span{span_attrs}>{translated}</span>")
                            else:
                                widget.set_markup(f"<span>{translated}</span>")
                        elif "<b>" in original_markup and "</b>" in original_markup:
                            widget.set_markup(f"<b>{translated}</b>")
                        else:
                            # Best-effort: replace the *original* plain text inside the
                            # *original* markup template. If not found, fall back to a span.
                            if original_plain in original_markup:
                                new_markup = original_markup.replace(original_plain, translated)
                                widget.set_markup(new_markup)
                            else:
                                widget.set_markup(f"<span>{translated}</span>")
                    else:
                        # No markup: plain text
                        if translated != widget.get_text():
                            widget.set_text(translated)

            # Gtk.Entry / Gtk.SearchEntry (placeholder only)
            elif isinstance(widget, Gtk.SearchEntry) or isinstance(widget, Gtk.Entry):
                original_ph = self._remember_original(
                    widget, "entry.placeholder", widget.get_placeholder_text()
                )
                if original_ph:
                    translated = self.get_text(original_ph)
                    if translated != widget.get_placeholder_text():
                        widget.set_placeholder_text(translated)

            # Adw.WindowTitle
            elif isinstance(widget, Adw.WindowTitle):
                original_title = self._remember_original(
                    widget, "windowtitle.title", widget.get_title()
                )
                if original_title:
                    translated = self.get_text(original_title)
                    if translated != widget.get_title():
                        widget.set_title(translated)

            # Adw.MessageDialog (heading + body with bullets)
            elif isinstance(widget, Adw.MessageDialog):
                # Heading
                original_heading = self._remember_original(
                    widget, "messagedialog.heading", widget.get_heading()
                )
                if original_heading:
                    translated_heading = self.get_text(original_heading)
                    if translated_heading != widget.get_heading():
                        widget.set_heading(translated_heading)

                # Body: store the original full body once, then translate line-by-line each time
                original_body = self._remember_original(
                    widget, "messagedialog.body", widget.get_body()
                )
                if original_body:
                    lines = original_body.splitlines()
                    out = []
                    for line in lines:
                        if not line.strip():
                            out.append(line)
                            continue
                        bullet = ""
                        stripped = line
                        if stripped.lstrip().startswith("• "):
                            bullet = "• "
                            stripped = stripped.lstrip()[2:].strip()
                        else:
                            stripped = stripped.strip()
                        translated_line = self.get_text(stripped)
                        out.append(f"{bullet}{translated_line}")
                    new_body = "\n".join(out)
                    if new_body != widget.get_body():
                        widget.set_body(new_body)

        except Exception:
            # Silently continue if we can't update a specific widget
            pass

    
    def get_text(self, key):
        # always resolve through English
        if key in self.translations.get(self.current_language, {}):
            return self.translations[self.current_language][key]
        if key in self.translations["en_US.UTF-8"]:
            return self.translations["en_US.UTF-8"][key]
        return key
        
        def get_current_language(self):
            """Get the current language code"""
            return self.current_language

# Singleton access
def get_localization_manager():
    """Get the singleton SimpleLocalizationManager instance"""
    return SimpleLocalizationManager()

# Convenience function for getting translated text (optional)
def _(key):
    """Get translated text using the localization manager"""
    return get_localization_manager().get_text(key)
