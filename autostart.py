import os
import sys
from pathlib import Path
import platform
import plistlib

APP_NAME = "DuckAIWrapper"

def get_exec_command() -> str:
    exe = sys.executable
    entry = os.path.abspath(sys.argv[0])
    return f'"{exe}" "{entry}"'

# Windows: registry
def _win_set(enable: bool):
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE)
        if enable:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, get_exec_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception:
        return False

# Linux: XDG autostart .desktop
def _linux_set(enable: bool):
    try:
        autostart_dir = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart"
        autostart_dir.mkdir(parents=True, exist_ok=True)
        desktop_path = autostart_dir / f"{APP_NAME}.desktop"
        if enable:
            cmd = get_exec_command()
            desktop = [
                "[Desktop Entry]",
                "Type=Application",
                f"Name={APP_NAME}",
                f"Exec={cmd}",
                "X-GNOME-Autostart-enabled=true",
            ]
            desktop_path.write_text("\n".join(desktop), encoding="utf-8")
        else:
            if desktop_path.exists():
                desktop_path.unlink()
        return True
    except Exception:
        return False

# macOS: LaunchAgents plist
def _mac_set(enable: bool):
    try:
        la_dir = Path.home() / "Library" / "LaunchAgents"
        la_dir.mkdir(parents=True, exist_ok=True)
        plist_path = la_dir / f"com.{APP_NAME.lower()}.plist"
        if enable:
            # ProgramArguments expects a list
            cmd = get_exec_command().split()
            plist = {
                "Label": f"com.{APP_NAME.lower()}",
                "ProgramArguments": cmd,
                "RunAtLoad": True,
            }
            with plist_path.open("wb") as f:
                plistlib.dump(plist, f)
        else:
            if plist_path.exists():
                plist_path.unlink()
        return True
    except Exception:
        return False

def set_autostart(enable: bool) -> bool:
    sys_plat = platform.system()
    if sys_plat == "Windows":
        return _win_set(enable)
    if sys_plat == "Linux":
        return _linux_set(enable)
    if sys_plat == "Darwin":
        return _mac_set(enable)
    return False

def is_autostart_enabled() -> bool:
    sys_plat = platform.system()
    if sys_plat == "Windows":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run",
                                 0, winreg.KEY_READ)
            try:
                val, _ = winreg.QueryValueEx(key, APP_NAME)
                return bool(val)
            except FileNotFoundError:
                return False
        except Exception:
            return False
    if sys_plat == "Linux":
        desktop_path = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart" / f"{APP_NAME}.desktop"
        return desktop_path.exists()
    if sys_plat == "Darwin":
        plist_path = Path.home() / "Library" / "LaunchAgents" / f"com.{APP_NAME.lower()}.plist"
        return plist_path.exists()
    return False
