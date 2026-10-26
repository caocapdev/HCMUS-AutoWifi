import sys
import os
import time
import socket
import threading
import argparse

for s in (sys.stdout, sys.stderr):
    if s:
        s.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config import config, APP_VERSION
from core.startup_manager import (
    set_startup_mode,
    apply_startup_mode_internal,
    get_current_startup_mode,
    is_task_enabled,
    enable_registry
)
from core.network_checker import get_wifi_info, check_captive_portal
from core.portal_solver import PortalSolver
from core.notifier import show_notification
from ui.main_window import MainWindow
from ui.tray_icon import TrayIconManager

SINGLE_INSTANCE_PORT = 49382

class AutoWifiApp:
    def __init__(self, start_in_tray=False):
        self.start_in_tray = start_in_tray
        self.is_running = True
        self.is_logging_in = False
        self.last_attempt_time = 0
        self._stop_event = threading.Event()

        callbacks = {
            "show_window": self.show_window,
            "manual_login": self.trigger_manual_login,
            "check_now": self.trigger_check_now,
            "exit_app": self.exit_app,
            "on_startup_changed": lambda: self.main_window.sync_startup_mode_ui()
        }

        self.main_window = MainWindow(callbacks)
        self.tray = TrayIconManager(callbacks)
        self.solver = PortalSolver(log_callback=self.main_window.log)

        self.tray.run_detached()
        self._start_single_instance_listener()

        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

        if self.start_in_tray:
            self.main_window.hide_to_tray()
            self.main_window.log("Đang chạy ngầm trong khay hệ thống.", "info")

        # Load UI hoàn tất trước rồi mới tiến hành kiểm tra / cài đặt Task Scheduler
        self.main_window.root.after(600, self._setup_startup_on_first_run)

    def _setup_startup_on_first_run(self):
        def _task():
            if not config.get("start_with_windows", True):
                return
            configured_mode = config.get("startup_mode", "task")
            current_mode = get_current_startup_mode()

            if current_mode != configured_mode or (configured_mode == "task" and not is_task_enabled()):
                self.main_window.log("Cài đặt khởi động Task Scheduler...", "info")
                ok, _ = set_startup_mode(configured_mode)
                if ok and is_task_enabled():
                    self.main_window.log("Đã cài đặt khởi động Task Scheduler.", "success")
                elif not ok and configured_mode == "task" and not is_task_enabled():
                    self.main_window.log("Chưa thể bật Task Scheduler, chuyển sang Registry...", "warning")
                    enable_registry()
                    config.set("startup_mode", "registry")
                    self.main_window.log("Đã kích hoạt khởi động Registry.", "info")
            elif configured_mode == "task" and is_task_enabled():
                self.main_window.log("Khởi động cùng Windows: Task Scheduler.", "info")

            self.main_window.sync_startup_mode_ui()

        threading.Thread(target=_task, daemon=True).start()

    def _start_single_instance_listener(self):
        def _listen():
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
                    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    server.bind(("127.0.0.1", SINGLE_INSTANCE_PORT))
                    server.listen(2)
                    while self.is_running:
                        client, _ = server.accept()
                        with client:
                            data = client.recv(64).decode("utf-8", errors="ignore")
                            if "SHOW" in data:
                                self.main_window.root.after(0, self.show_window)
            except Exception:
                pass
        threading.Thread(target=_listen, daemon=True).start()

    def show_window(self):
        self.main_window.show_window()

    def trigger_check_now(self):
        self.main_window.log("Kiểm tra kết nối mạng...", "info")
        threading.Thread(target=self._check_network_once, daemon=True).start()

    def trigger_manual_login(self):
        if self.is_logging_in:
            self.main_window.log("Đang đăng nhập, vui lòng đợi...", "warning")
            return
        self.main_window.log("Bắt đầu đăng nhập Wi-Fi...", "info")
        cap = check_captive_portal()
        threading.Thread(target=self._perform_login, args=(cap.get("portal_url", ""),), daemon=True).start()

    def _monitor_loop(self):
        self._stop_event.wait(1.0)
        while self.is_running and not self._stop_event.is_set():
            try:
                self._check_network_once()
            except Exception as e:
                self.main_window.log(f"Lỗi vòng lặp giám sát: {e}", "error")

            interval = max(1, config.get("check_interval", 1))
            self._stop_event.wait(interval)

    def _check_network_once(self):
        wifi = get_wifi_info()
        captive = check_captive_portal()
        self.main_window.update_network_status(wifi, captive)
        ssid = wifi.get("ssid", "Wi-Fi")

        if captive.get("has_internet"):
            self.tray.update_status("online", f"Đã kết nối: {ssid}")
        elif captive.get("is_captive"):
            self.tray.update_status("captive", f"Yêu cầu đăng nhập: {ssid}")
            now = time.time()
            if config.get("auto_login_enabled", True) and not self.is_logging_in:
                if now - self.last_attempt_time >= 8:
                    self.last_attempt_time = now
                    self.main_window.log(f"Phát hiện '{ssid}' yêu cầu đăng nhập portal.", "warning")
                    threading.Thread(target=self._perform_login, args=(captive.get("portal_url", ""),), daemon=True).start()
        else:
            self.tray.update_status("offline", "Không có kết nối mạng")

    def _perform_login(self, portal_url=None):
        if self.is_logging_in:
            return
        self.is_logging_in = True
        self.tray.update_status("working", "Đang đăng nhập...")
        try:
            ssid = get_wifi_info().get("ssid", "Wi-Fi")
            self.main_window.log(f"Đang đăng nhập: {ssid}...", "info")
            res = self.solver.solve(portal_url=portal_url)
            if res.get("success"):
                msg = res.get("message", "Đã kết nối Internet thành công!")
                self.tray.update_status("online", f"Đã kết nối: {ssid}")
                show_notification("HCMUS AutoWifi", msg)
            else:
                self.main_window.log(res.get("message", "Đăng nhập thất bại."), "warning")
                self.tray.update_status("captive", "Đăng nhập thất bại, thử lại sau.")
        except Exception as e:
            self.main_window.log(f"Lỗi quá trình đăng nhập: {e}", "error")
        finally:
            self.is_logging_in = False
            self._check_network_once()

    def exit_app(self):
        self.is_running = False
        self._stop_event.set()
        try:
            self.tray.stop()
        except Exception:
            pass
        try:
            self.main_window.root.quit()
            self.main_window.root.destroy()
        except Exception:
            pass
        sys.exit(0)

    def run(self):
        self.main_window.root.mainloop()

def check_single_instance() -> bool:
    """Checks if another instance is running on localhost port 49382."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            sock.connect(("127.0.0.1", SINGLE_INSTANCE_PORT))
            sock.sendall(b"SHOW")
            return False
    except Exception:
        return True

def main():
    parser = argparse.ArgumentParser(description="HCMUS AutoWifi - Tự động đăng nhập Wi-Fi")
    parser.add_argument("--version", "-v", action="version", version=f"%(prog)s {APP_VERSION}")
    parser.add_argument("--tray", action="store_true", help="Khởi động ẩn trong khay hệ thống")
    parser.add_argument("--login-now", action="store_true", help="Đăng nhập ngay rồi thoát")
    parser.add_argument("--set-startup-elevated", type=str, choices=["none", "registry", "task"], help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.set_startup_elevated:
        ok, msg = apply_startup_mode_internal(args.set_startup_elevated)
        print(f"[Khởi động] Cài đặt '{args.set_startup_elevated}': ok={ok}, msg={msg}")
        sys.exit(0 if ok else 1)

    if args.login_now:
        print("[CLI] Đang đăng nhập portal...")
        res = PortalSolver().solve()
        print(f"[CLI] Kết quả: {res.get('message', res)}")
        sys.exit(0 if res.get("success") else 1)

    if not check_single_instance():
        print("[App] AutoWifi đang chạy. Đã hiện cửa sổ.")
        sys.exit(0)

    app = AutoWifiApp(start_in_tray=args.tray)
    app.run()

if __name__ == "__main__":
    main()
