import os
import time
import json
import socket
import shutil
import tempfile
import subprocess
import urllib.request
import threading
import websocket
import requests

from core.config import config
from core.network_checker import get_wifi_info
from core.portals import find_portal_strategy, BasePortal

# NCSI probe constants
_NCSI_URL = "http://www.msftconnecttest.com/connecttest.txt"
_NCSI_EXPECTED = "Microsoft Connect Test"

# Browser automation timing constants
_MAX_BROWSER_DURATION = 35      # seconds – max time to wait for portal login via browser
_FORM_SUBMIT_WAIT_STEPS = 6     # extra verify iterations after a form submit click
_QUICK_SUBMIT_WAIT_STEPS = 1    # verify iterations after a fast button click
_FORM_SUBMIT_STEP_DELAY = 0.5   # seconds between form-submit verify steps
_QUICK_SUBMIT_STEP_DELAY = 0.2  # seconds between quick-click verify steps


def find_system_browser() -> str:
    """Finds installed Microsoft Edge or Google Chrome executable."""
    bases = [os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", ""), os.environ.get("LOCALAPPDATA", "")]
    for b in bases:
        for rel in [r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"]:
            p = os.path.join(b, rel)
            if p and os.path.isfile(p):
                return p
    for name in ["msedge", "chrome"]:
        p = shutil.which(name)
        if p and os.path.isfile(p):
            return p
    return None

def find_available_port() -> int:
    """Finds an unused TCP port for remote debugging."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

class PortalSolver:
    """
    Orchestrates captive portal authentication:
      1. Inspects the portal gateway response.
      2. Selects the appropriate portal strategy (HCMUS, AWING, Generic).
      3. Attempts fast API/HTTP authorization.
      4. Falls back to headless browser automation via Chrome DevTools Protocol.
    """

    def __init__(self, log_callback=None):
        self.log = log_callback or (lambda msg, tag="info": print(f"[{tag.upper()}] {msg}"))
        self._lock = threading.Lock()

    def solve(self, portal_url: str = None) -> dict:
        if not self._lock.acquire(blocking=False):
            self.log("Một tiến trình đăng nhập khác đang chạy, vui lòng đợi...", "warning")
            return {"success": False, "message": "Đang có tiến trình đăng nhập khác"}
        try:
            return self._solve_internal(portal_url)
        finally:
            self._lock.release()

    def _solve_internal(self, portal_url: str = None) -> dict:
        if not portal_url:
            try:
                from core.network_checker import check_captive_portal
                cap = check_captive_portal()
                p_url = cap.get("portal_url", "")
                if p_url and "msftconnecttest" not in p_url:
                    portal_url = p_url
            except Exception:
                pass

        target_url = portal_url or config.get("portal_redirect_url", "http://www.msftconnecttest.com/redirect")
        self.log(f"Bắt đầu kết nối portal: {target_url}", "info")

        # Step 1: Probe the portal to discover gateway URL and HTML content (1.5s timeout)
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        landing_url, page_html = target_url, ""
        try:
            resp = session.get(target_url, timeout=1.5, allow_redirects=True)
            landing_url, page_html = resp.url, resp.text
        except Exception:
            pass

        portal_strategy = find_portal_strategy(landing_url, page_html)
        self.log(f"Loại portal: {portal_strategy.name}", "info")

        # Step 2: Fast Path - Direct HTTP / API Logon
        try:
            res_http = portal_strategy.solve_http(session, landing_url, page_html)
            if res_http and res_http.get("success"):
                self.log(res_http.get("message", "Đã xác thực thành công qua API"), "success")
                time.sleep(0.3)
                if self.verify_internet(0.8):
                    return self._build_success_result(portal_strategy.name)
        except Exception as e:
            self.log(f"API fast-path chưa hoàn tất ({e}), chuyển qua trình duyệt...", "warning")

        # Step 3: Headless Browser Automation via CDP
        browser_exe = find_system_browser()
        if not browser_exe:
            return {"success": False, "message": "Không tìm thấy Edge hoặc Chrome trên hệ thống."}

        self.log(f"Khởi chạy trình duyệt: {os.path.basename(browser_exe)}", "info")
        return self._solve_with_browser(browser_exe, target_url, portal_strategy)

    def _solve_with_browser(self, browser_exe: str, target_url: str, strategy: BasePortal) -> dict:
        port = find_available_port()
        temp_dir = os.path.join(tempfile.gettempdir(), f"autowifi_profile_{port}")
        os.makedirs(temp_dir, exist_ok=True)

        headless = config.get("headless", True)
        args = [
            browser_exe,
            f"--remote-debugging-port={port}",
            "--remote-allow-origins=*",
            f"--user-data-dir={temp_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--disable-sync",
            "--disable-background-networking",
            "--lang=vi-VN",
            "--window-size=1024,768"
        ]
        if headless:
            args.append("--headless=new")

        proc, ws = None, None
        try:
            startupinfo = subprocess.STARTUPINFO()
            if headless and hasattr(subprocess, "STARTF_USESHOWWINDOW"):
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW if headless and hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            )

            # Wait for CDP endpoint (up to 3.0s)
            json_url = f"http://127.0.0.1:{port}/json/list"
            targets = None
            for _ in range(30):
                time.sleep(0.1)
                try:
                    with urllib.request.urlopen(json_url, timeout=0.25) as resp:
                        targets = json.loads(resp.read().decode("utf-8"))
                        if targets:
                            break
                except Exception:
                    pass

            if not targets:
                return {"success": False, "message": "Không thể kết nối Chrome DevTools Protocol."}

            page_target = next((t for t in targets if t.get("type") == "page"), targets[0])
            ws = websocket.create_connection(page_target.get("webSocketDebuggerUrl"), timeout=5)

            msg_counter = 0
            def _cdp_call(method: str, params: dict = None, timeout: float = 3.0) -> dict:
                nonlocal msg_counter
                msg_counter += 1
                req_id = msg_counter
                payload = {"id": req_id, "method": method}
                if params:
                    payload["params"] = params
                ws.send(json.dumps(payload))

                deadline = time.time() + timeout
                while time.time() < deadline:
                    try:
                        raw = ws.recv()
                        if raw:
                            msg = json.loads(raw)
                            if msg.get("id") == req_id:
                                return msg
                    except Exception:
                        pass
                return {}

            _cdp_call("Page.navigate", {"url": target_url})
            start_time = time.time()
            js_script = strategy.get_browser_script()
            time.sleep(0.5)

            while time.time() - start_time < _MAX_BROWSER_DURATION:
                if self.verify_internet(timeout=0.4):
                    return self._build_success_result(strategy.name)

                # Dynamically detect redirect to AWING portal
                try:
                    cur_url_res = _cdp_call("Runtime.evaluate", {
                        "expression": "window.location.href + ' ' + (document.title || '')",
                        "returnByValue": True
                    }, timeout=1.0)
                    cur_info = cur_url_res.get("result", {}).get("result", {}).get("value", "").lower()
                    if strategy.name != "AWING Connect (Sân bay / Quán Cafe)" and any(k in cur_info for k in ["awing", "186.186.", "wi-fi | awing"]):
                        from core.portals.awing import AwingPortal
                        strategy = AwingPortal()
                        js_script = strategy.get_browser_script()
                        self.log(f"Trình duyệt nhận diện: {strategy.name}", "info")
                except Exception:
                    pass

                # Execute strategy DOM script
                try:
                    res = _cdp_call("Runtime.evaluate", {
                        "expression": js_script,
                        "returnByValue": True
                    }, timeout=2.0)
                    val = res.get("result", {}).get("result", {}).get("value", {})
                    status = val.get("status")
                    button_name = val.get("buttonClicked")

                    if status == "clicked":
                        self.log(f"Đã kích hoạt: '{button_name}'. Đang đợi kết nối...", "success")
                        is_form_submit = any(k in (button_name or "").lower() for k in ["frmlogin", "submit", "mikrotik"])
                        max_wait_steps = _FORM_SUBMIT_WAIT_STEPS if is_form_submit else _QUICK_SUBMIT_WAIT_STEPS
                        step_delay = _FORM_SUBMIT_STEP_DELAY if is_form_submit else _QUICK_SUBMIT_STEP_DELAY

                        for _ in range(max_wait_steps):
                            time.sleep(step_delay)
                            if self.verify_internet(timeout=0.4):
                                return self._build_success_result(strategy.name)
                    elif status == "waiting_ad_timer":
                        time.sleep(0.4)
                except Exception as eval_err:
                    self.log(f"Lỗi tương tác DOM: {eval_err}", "warning")

                time.sleep(0.5)

            if self.verify_internet(timeout=1.0):
                return self._build_success_result(strategy.name)

            return {"success": False, "message": "Đã bấm nút kết nối nhưng chưa nhận được tín hiệu Internet."}

        except Exception as e:
            self.log(f"Lỗi trình duyệt: {e}", "error")
            return {"success": False, "message": str(e)}
        finally:
            if ws:
                try: ws.close()
                except Exception: pass
            if proc:
                try:
                    proc.terminate()
                    proc.wait(timeout=1)
                except Exception:
                    try: proc.kill()
                    except Exception: pass
            if os.path.exists(temp_dir):
                threading.Thread(target=shutil.rmtree, args=(temp_dir,), kwargs={"ignore_errors": True}, daemon=True).start()

    def verify_internet(self, timeout: float = 0.8) -> bool:
        """Lightweight ultra-fast probe directly to NCSI without full overhead."""
        try:
            r = requests.get(_NCSI_URL, timeout=timeout, allow_redirects=False)
            return r.status_code == 200 and r.text.strip() == _NCSI_EXPECTED
        except Exception:
            return False

    def _build_success_result(self, portal_name: str) -> dict:
        wifi = get_wifi_info()
        ssid = wifi.get("ssid", "Wi-Fi")
        config.increment_logins(ssid)
        msg = f"Đã kết nối Internet thành công vào {ssid} ({portal_name})!"
        self.log(msg, "success")
        return {"success": True, "message": msg, "ssid": ssid}
