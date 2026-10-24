import threading
import pystray
from PIL import Image, ImageDraw
from core.startup_manager import (
    get_current_startup_mode,
    set_startup_mode,
    MODE_LABELS,
    MODE_NONE,
    MODE_REGISTRY,
    MODE_TASK
)
from core.notifier import register_tray_icon, show_notification

STATUS_COLORS = {
    "online": (40, 167, 69),      # Green
    "captive": (255, 193, 7),     # Yellow / Amber
    "working": (0, 123, 255),     # Blue
    "offline": (220, 53, 69)      # Red
}

def create_tray_image(status="online"):
    """Creates a 64x64 RGBA icon with Wi-Fi arcs and a status badge dot."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Base HCMUS Navy Circle
    d.ellipse([2, 2, 62, 62], fill=(16, 52, 120, 255))

    # White Wi-Fi Signal Waves
    d.arc([16, 20, 48, 52], start=200, end=340, fill=(255, 255, 255), width=3)
    d.arc([22, 26, 42, 46], start=200, end=340, fill=(255, 255, 255), width=3)
    d.ellipse([29, 38, 35, 44], fill=(255, 255, 255))

    # Status Dot Badge in bottom-right
    dot_color = STATUS_COLORS.get(status, (40, 167, 69))
    d.ellipse([42, 42, 62, 62], fill=dot_color, outline=(255, 255, 255), width=2)
    return img

class TrayIconManager:
    def __init__(self, app_callbacks):
        self.callbacks = app_callbacks
        self.status = "online"
        self.status_text = "Đang kiểm tra kết nối..."
        self.icon = None
        self._init_tray()

    def _init_tray(self):
        img = create_tray_image(self.status)
        def _make_item(mode):
            return pystray.MenuItem(
                MODE_LABELS[mode],
                lambda icon, item: self._on_select_startup_mode(mode),
                checked=lambda item: self._is_mode(mode),
                radio=True
            )

        startup_items = [_make_item(m) for m in [MODE_TASK, MODE_REGISTRY, MODE_NONE]]
        menu = pystray.Menu(
            pystray.MenuItem(lambda text: f"Trạng thái: {self.status_text}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Đăng nhập ngay", lambda i, item: self.callbacks.get("manual_login", lambda: None)()),
            pystray.MenuItem("Kiểm tra kết nối", lambda i, item: self.callbacks.get("check_now", lambda: None)()),
            pystray.MenuItem("Mở giao diện chính", lambda i, item: self.callbacks.get("show_window", lambda: None)(), default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Khởi động (Startup)", pystray.Menu(*startup_items)),
            pystray.MenuItem("Thoát", lambda i, item: self.callbacks.get("exit_app", lambda: None)())
        )
        self.icon = pystray.Icon("HCMUSAutoWifi", img, "HCMUS AutoWifi", menu)
        register_tray_icon(self.icon)

    def update_menu(self):
        if self.icon:
            try:
                self.icon.update_menu()
            except Exception:
                pass

    def _is_mode(self, mode: str) -> bool:
        return get_current_startup_mode() == mode

    def _on_select_startup_mode(self, mode: str):
        def _apply():
            ok, msg = set_startup_mode(mode)
            show_notification("HCMUS AutoWifi", f"Đã chọn: {MODE_LABELS.get(mode)}" if ok else f"Lỗi: {msg}")
            if "on_startup_changed" in self.callbacks:
                self.callbacks["on_startup_changed"]()
            self.update_menu()
        threading.Thread(target=_apply, daemon=True).start()

    def update_status(self, status: str, text: str):
        self.status = status
        self.status_text = text
        if self.icon:
            try:
                self.icon.icon = create_tray_image(status)
                self.icon.title = f"HCMUS AutoWifi - {text}"
            except Exception:
                pass

    def run_detached(self):
        threading.Thread(target=self.icon.run, daemon=True).start()

    def stop(self):
        if self.icon:
            self.icon.stop()
