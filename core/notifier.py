import subprocess
import threading
from core.config import config

_tray_icon_ref = None

def register_tray_icon(icon):
    global _tray_icon_ref
    _tray_icon_ref = icon

def show_notification(title: str, message: str):
    if not config.get("notifications", True):
        return

    global _tray_icon_ref
    if _tray_icon_ref is not None:
        try:
            _tray_icon_ref.notify(message, title)
            return
        except Exception:
            pass

    def _fallback():
        try:
            cmd = f'Add-Type -AssemblyName System.Windows.Forms; $n = New-Object System.Windows.Forms.NotifyIcon; $n.Icon = [System.Drawing.SystemIcons]::Information; $n.Visible = $True; $n.ShowBalloonTip(3000, "{title}", "{message}", [System.Windows.Forms.ToolTipIcon]::Info)'
            subprocess.run(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", cmd],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
        except Exception:
            pass

    threading.Thread(target=_fallback, daemon=True).start()
