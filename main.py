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
from core.network_checker import (
    get_wifi_info,
    check_captive_portal,
    get_known_wifi_profiles,
    scan_available_networks,
    is_open_network,
    get_available_open_networks,
    connect_to_wifi
)
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
        self.last_scan_attempt_time = 0
        self._is_connecting_open = False
        self._failed_open_ssids = {}
        self._last_connected_ssid = None
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

        # Defer startup setup until UI has fully rendered
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
        self._failed_open_ssids.clear()
        self.last_scan_attempt_time = 0
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
        last_tick = time.time()
        while self.is_running and not self._stop_event.is_set():
            now = time.time()
            elapsed = now - last_tick
            interval = max(1, config.get("check_interval", 1))

            # System resumed from Sleep / Standby
            if elapsed > interval + 3.0:
                self._handle_system_resume(elapsed)

            try:
                self._check_network_once()
            except Exception as e:
                self.main_window.log(f"Lỗi vòng lặp giám sát: {e}", "error")

            last_tick = time.time()
            self._stop_event.wait(interval)

    def _handle_system_resume(self, elapsed: float):
        sleep_sec = int(elapsed)
        self.main_window.log(f"Phát hiện máy tính vừa thức dậy từ chế độ Sleep ({sleep_sec}s).", "info")
        self.tray.update_status("working", "Khôi phục kết nối Wi-Fi sau Sleep...")

        self._failed_open_ssids.clear()
        self._is_connecting_open = False
        self.last_scan_attempt_time = 0
        self._last_connected_ssid = None

        # Allow Wi-Fi radio hardware time to reinitialize
        time.sleep(1.5)

    def _check_network_once(self):
        wifi = get_wifi_info()
        captive = check_captive_portal()
        self.main_window.update_network_status(wifi, captive)
        is_connected = wifi.get("connected", False)
        ssid = wifi.get("ssid", "")

        if is_connected and ssid:
            self._last_connected_ssid = ssid
            self._failed_open_ssids.pop(ssid, None)
        else:
            self._last_connected_ssid = None

        if captive.get("has_internet"):
            self.tray.update_status("online", f"Đã kết nối: {ssid or 'Wi-Fi'}")
        elif captive.get("is_captive"):
            self.tray.update_status("captive", f"Yêu cầu đăng nhập: {ssid or 'Wi-Fi'}")
            now = time.time()
            if config.get("auto_login_enabled", True) and not self.is_logging_in:
                if now - self.last_attempt_time >= 8:
                    self.last_attempt_time = now
                    self.main_window.log(f"Phát hiện '{ssid}' yêu cầu đăng nhập portal.", "warning")
                    threading.Thread(target=self._perform_login, args=(captive.get("portal_url", ""),), daemon=True).start()
        else:
            self.tray.update_status("offline", "Không có kết nối mạng")
            now = time.time()
            scan_cooldown = max(5, config.get("scan_open_cooldown", 12))
            if (config.get("auto_connect_open_portals", True)
                    and not self.is_logging_in
                    and not self._is_connecting_open
                    and not is_connected
                    and (now - self.last_scan_attempt_time >= scan_cooldown)):
                self.last_scan_attempt_time = now
                threading.Thread(target=self._scan_and_connect_open_portal, daemon=True).start()

    def _scan_and_connect_open_portal(self):
        if self._is_connecting_open or self.is_logging_in:
            return
        self._is_connecting_open = True
        try:
            cur_wifi = get_wifi_info()
            if cur_wifi.get("connected"):
                return

            # Scan visible networks in range
            visible = scan_available_networks(trigger_active_scan=True)
            if not visible or not self.is_running:
                return

            now = time.time()
            self._failed_open_ssids = {
                k: v for k, v in self._failed_open_ssids.items()
                if now - v < 60
            }

            known_profiles = get_known_wifi_profiles()
            known_normalized = {p.strip().lower() for p in known_profiles if p.strip()}

            # If any known secured network is in range, let Windows handle connection natively
            visible_known_secured = [
                n for n in visible
                if n.get("ssid")
                and (n["ssid"].strip().lower() in known_normalized or n["ssid"] in known_profiles)
                and not is_open_network(n)
            ]

            if visible_known_secured:
                # Let Windows handle connecting to saved profiles natively
                return

            # Fall back to candidate open networks with captive portals
            open_nets = get_available_open_networks(visible, known_profiles=known_profiles)
            if not open_nets or not self.is_running:
                return

            candidates = [
                n for n in open_nets
                if n.get("ssid")
                and n["ssid"] not in self._failed_open_ssids
            ]

            if not candidates:
                return

            target = candidates[0]
            target_ssid = target["ssid"]
            target_sig = target.get("signal", 0)

            self.main_window.log(f"Tìm thấy mạng mở: {target_ssid} ({target_sig}%). Đang kết nối thử...", "info")
            self.tray.update_status("working", f"Kết nối: {target_ssid}...")

            if not connect_to_wifi(target_ssid, timeout=7.0):
                self.main_window.log(f"Không thể kết nối đến mạng mở {target_ssid}.", "warning")
                self._failed_open_ssids[target_ssid] = time.time()
                return

            self.main_window.log(f"Đã kết nối vào {target_ssid}. Đang kiểm tra Captive Portal...", "info")
            time.sleep(1.8)

            cap = check_captive_portal()
            if cap.get("is_captive"):
                self.main_window.log(f"Phát hiện '{target_ssid}' có Captive Portal! Đang tiến hành đăng nhập...", "warning")
                self._perform_login(portal_url=cap.get("portal_url", ""))
            elif cap.get("has_internet"):
                self.main_window.log(f"Đã kết nối thành công vào mạng mở: {target_ssid} (Có sẵn Internet).", "success")
                self.tray.update_status("online", f"Đã kết nối: {target_ssid}")
            else:
                self.main_window.log(f"Mạng mở '{target_ssid}' không có Captive Portal hoặc Internet.", "warning")
                self._failed_open_ssids[target_ssid] = time.time()

        except Exception as e:
            self.main_window.log(f"Lỗi quét và kết nối mạng: {e}", "error")
        finally:
            self._is_connecting_open = False

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
