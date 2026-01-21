# Linexin Installer Documentation

## Overview

The **Linexin Installer** is a modern, user-friendly Linux installer built with **Python 3**, **GTK 4**, and **Libadwaita**. It provides a guided step-by-step process to install the Linexin operating system (or other customized distributions) onto a target machine.

### Key Technologies
-   **Language**: Python 3
-   **UI Toolkit**: GTK 4 + Libadwaita (provides modern GNOME aesthetics and adaptive widgets)
-   **System Tools**: `parted`, `lsblk`, `rsync`, `mkfs`, `btrfs-progs`, `arch-chroot` (for Arch base)

### Directory Structure
The application source is located in `src/usr/share/linexin-installer/`.
-   **`installer`**: The main entry point script. Initializes the application, window, and manages navigation between screens.
-   **`*_widget.py`**: Individual screens (pages) of the installer.
-   **`simple_localization_manager.py`**: Handles translation loading and mapping.
-   **`disk_utils.py`**: Utility functions for disk operations.
-   **`translations/`**: Directory containing localization files.

---

## Widget Reference

The installer is composed of a stack of "Widgets" (Pages). The main window switches between these widgets as the user progresses.

| Widget Name | File | Purpose |
| :--- | :--- | :--- |
| **WelcomeWidget** | `welcome_widget.py` | Initial screen. Features language cycling animation and "Begin Installation" button. |
| **LanguageWidget** | `language_widget.py` | List of available languages for the system. |
| **TimezoneWidget** | `timezone_widget.py` | Interactive map and list to select the system timezone. |
| **KeyboardLayoutWidget** | `keyboard_layout_widget.py` | Searchable list of keyboard layouts with a test entry field. |
| **InstallationTemplateWidget** | `installation_template_widget.py` | High-level partitioning choices: "Erase Disk", "Install Alongside", or "Manual Partitioning". |
| **DiskUtilityWidget** | `disk_utility_widget.py` | Advanced partition manager. Allows creating/deleting partitions, formatting, and assigning mount points manually. |
| **DEPicker** | `de_picker_widget.py` | Selection screen for Desktop Environment (e.g., Linexin vs. Kinexin). Writes selection to `/tmp/installer_config`. |
| **UserCreationWidget** | `user_creation_widget.py` | Form for Username, Password, Hostname, and optionally enabling the Root account. |
| **InstallationWidget** | `installation_widget.py` | The execution runner. Performs partitioning, mounting, and file copying (`rsync`). Shows a progress bar and detailed terminal log. |
| **FinishWidget** | `finish_widget.py` | Success screen with a "Reboot" button. |

---

## Modifying the Application

### 1. Application Structure (How it works)
The `installer` file contains the `MainWindow` class.
-   **Initialization**: It imports all widget classes and instantiates them in `__init__`.
-   **Stack Management**: It uses a `Gtk.Stack` (`self.main_stack`) to hold all widgets. Each widget is added with a unique name (e.g., `"welcome"`, `"language"`).
-   **Navigation**: Navigation is handled by connecting button signals (e.g., `.connect("clicked", ...)`) to methods that change the visible child of the stack (e.g., `self.main_stack.set_visible_child_name("next_page")`).

### 2. Modifying Existing Widgets
To modify a widget (e.g., `WelcomeWidget`):
1.  Open the corresponding file (`welcome_widget.py`).
2.  Modify the UI construction in `__init__`.
3.  **Localization**: Wrap any new user-facing strings in `_("Your Text")` to ensure they can be translated.
4.  **Styling**: Most widgets have a `setup_custom_css` method or embedded CSS strings. Modify these to change the look and feel.

### 3. Adding a Custom Widget
To add a new screen (e.g., a "License Agreement" page):

1.  **Create the File**: Create `license_widget.py`.
    ```python
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Gtk, Adw
    from simple_localization_manager import get_localization_manager

    class LicenseWidget(Gtk.Box):
        def __init__(self, **kwargs):
            super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
            # Layout your UI here...
            self.btn_next = Gtk.Button(label="Accept & Continue")
            self.append(self.btn_next)
            
            # Register for translation
            get_localization_manager().register_widget(self)
    ```

2.  **Register in `installer`**:
    -   Import the new class: `from license_widget import LicenseWidget`
    -   Instantiate it in `MainWindow.__init__`: `self.license_page = LicenseWidget()`
    -   Add it to the stack: `self.main_stack.add_named(self.license_page, "license")`
    -   Register it for localization in the localization loop.

3.  **Wire up Navigation**:
    -   Connect the previous page's "Next" button to show `"license"`.
    -   Connect `self.license_page.btn_next` to show the subsequent page.

---

## Customizing Installation Steps

To change the actual installation logic (what commands are run), you need to modify `installation_widget.py`.

### 1. The `InstallationStep` Structure
The installation process is a sequence of `InstallationStep` objects defined in the `start_installation` method.
```python
@dataclass
class InstallationStep:
    label: str           # Visible title in the UI
    command: List[str]   # The command list (e.g., ["sudo", "cp", ...])
    description: str     # Subtitle description
    weight: float        # Progress bar weight (relative to others)
    critical: bool       # If True, failure stops the whole installation
```

### 2. Adding a Custom Step
Locate the `start_installation` method in `installation_widget.py`. You will see `steps.append(...)` calls. To add your own step, generally standard bash commands, simply append a new step object.

**Example: Running a custom setup script**
```python
steps.append(InstallationStep(
    label="Running Custom Setup",
    command=["sudo", "/usr/share/linexin-installer/custom-setup.sh"],
    description="Applying custom configurations...",
    weight=1.0,
    critical=False
))
```

### 3. Using Custom Scripts
If you have complex logic (e.g., extensive `sed` replacements, downloading extra files), it is cleaner to put it in a separate script.

1.  **Create your script** in the source directory (e.g., `src/usr/share/linexin-installer/myscript.sh`).
2.  **Ensure it's executable** (`chmod +x myscript.sh`).
3.  **Include it in the build** (ensure it's installed to `/usr/share/linexin-installer/` on the live system).
4.  **Reference it** in an `InstallationStep` using its absolute path.

**Running scripts inside the new system (Chroot)**
If you want to run a script *inside* the newly installed OS (e.g., to install packages with `pacman`/`apt` or enable systemd services):
1.  Copy the script to the new root first:
    ```python
    steps.append(InstallationStep(
        label="Copying setup script",
        command=["sudo", "cp", "/path/to/myscript.sh", "/tmp/linexin_installer/root/tmp/"],
        description="Preparing setup script",
        weight=0.1
    ))
    ```
2.  Run it via `arch-chroot` (or standard `chroot`):
    ```python
    steps.append(InstallationStep(
        label="Configuring System",
        command=["sudo", "arch-chroot", "/tmp/linexin_installer/root", "/bin/bash", "/tmp/myscript.sh"],
        description="Running post-install configuration",
        weight=1.0
    ))
    ```

---

## Customizing for Other Distributions

The installer is currently optimized for Arch Linux-based systems but can be adapted for others (Debian, Fedora, etc.).

### 1. Installation Logic (`installation_widget.py`)
This is the core that needs the most change.
-   **Source Image**: Currently, it mounts a loop device (`/dev/loop0`) or assumes a live system structure at `/run/archiso/...`. You need to point this to your distro's squashfs or root source.
-   **File Copying**: It uses `rsync` to copy the live system to the target. This is generic and works for most "Live CD to Disk" installers.
-   **Bootloader**: The `_get_mount_boot_command` and related logic handle EFI/Legacy mounting.
-   **Chroot**: The script uses `arch-chroot`. For non-Arch distros, replace this with standard `chroot` commands (mounting `/dev`, `/proc`, `/sys` manually) or your distro's specific chroot wrapper.

### 2. Post-Install Scripts
The installer copies and runs scripts like `post-install.sh` and `bootloader.sh` inside the new target system.
-   **`bootloader.sh`**: Handles GRUB/Systemd-boot installation. You must ensure the package manager commands (e.g., `pacman -S grub`) are changed to `apt install`, `dnf install`, etc.
-   **`post-install.sh`**: Handles user creation, enabling services, etc. Update `systemctl` usage or package installation commands as needed for your base system.

### 3. Partitioning
The underlying partitioning logic (`disk_utility_widget.py`) uses standard *nix tools (`parted`, `mkfs`). This is generally distro-agnostic but verify that the target filesystem types (ext4, btrfs, xfs) are supported by your live kernel.
