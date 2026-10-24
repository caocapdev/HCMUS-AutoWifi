import subprocess
import requests
from core.config import config

def get_wifi_info() -> dict:
    """
    Retrieves current Wi-Fi status using Windows netsh command.
    """
    info = {
        "connected": False,
        "ssid": "Không có kết nối",
        "bssid": "",
        "signal": "0%",
        "state": "disconnected",
        "interface": ""
    }
    try:
        proc = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        for line in proc.stdout.splitlines():
            if ":" not in line:
                continue
            key, val = [x.strip() for x in line.split(":", 1)]
            kl = key.lower()
            if "state" in kl or "trạng thái" in kl:
                info["state"] = val
                if val.lower() == "connected" or "kết nối" in val.lower():
                    info["connected"] = True
            elif "ssid" == kl or "tên" in kl:
                info["ssid"] = val
            elif "bssid" in kl:
                info["bssid"] = val
            elif "signal" in kl or "tín hiệu" in kl:
                info["signal"] = val
            elif "name" == kl:
                info["interface"] = val
    except Exception as e:
        print(f"[Network] Error getting wifi info: {e}")

    return info

def check_captive_portal() -> dict:
    """
    Checks if current connection is behind a captive portal.
    Probes NCSI connecttest.txt and redirects.
    """
    result = {
        "has_internet": False,
        "is_captive": False,
        "portal_url": "",
        "details": "",
        "status_code": None
    }
    probe_url = config.get("connecttest_url", "http://www.msftconnecttest.com/connecttest.txt")
    redirect_url = config.get("portal_redirect_url", "http://www.msftconnecttest.com/redirect")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache"
    }

    # Step 1: probe connecttest.txt without following redirects
    try:
        r = requests.get(probe_url, headers=headers, timeout=1.8, allow_redirects=False)
        result["status_code"] = r.status_code

        if r.status_code in (301, 302, 303, 307, 308):
            loc = r.headers.get("Location", "")
            if "go.microsoft.com" not in loc and "msftconnecttest" not in loc:
                result.update({
                    "is_captive": True,
                    "portal_url": loc or redirect_url,
                    "details": f"Phát hiện Captive Portal qua chuyển hướng (HTTP {r.status_code}) -> {loc or redirect_url}"
                })
                return result

        if r.status_code == 200:
            if r.text.strip() == "Microsoft Connect Test":
                result.update({"has_internet": True, "details": "Đã kết nối Internet trực tiếp (NCSI OK)"})
                return result
            result.update({
                "is_captive": True,
                "portal_url": redirect_url,
                "details": "Trang Captive Portal trả về mã 200 thay vì NCSI string"
            })
            return result
    except Exception as e:
        result["details"] = f"Lỗi kết nối probe: {e}"

    # Step 2: Probe redirect_url fallback
    try:
        r2 = requests.get(redirect_url, headers=headers, timeout=1.8, allow_redirects=False)
        loc2 = r2.headers.get("Location", "")
        if r2.status_code in (301, 302, 303, 307, 308):
            if "go.microsoft.com" in loc2:
                result.update({"has_internet": True, "details": "Kết nối Internet bình thường (Redirect Microsoft)"})
            else:
                result.update({
                    "is_captive": True,
                    "portal_url": loc2 or redirect_url,
                    "details": f"Captive Portal phát hiện tại chuyển hướng: {loc2 or redirect_url}"
                })
    except Exception:
        pass

    return result
