import os
import re
import time
import subprocess
import tempfile
import xml.sax.saxutils as saxutils
import requests
from core.config import config

_PROBE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache"
}

_CAPTIVE_KEYWORDS = (
    "awing", "captive", "portal", "rescue", "hcmus", "wimesh", "wi-mesh",
    "free", "wifi", "wi-fi", "guest", "public", "login", "connect",
    "cafe", "coffee", "highlands", "phuclong", "phúc long", "katinat",
    "circlek", "circle k", "gs25", "7-eleven", "familymart", "ministop",
    "mall", "hotel", "airport", "sân bay", "bus", "vinbus", "vincom",
    "big c", "go!", "lotteria", "mcdonald", "jollibee", "starbucks",
    "passpoint", "splash", "welcome"
)

_IGNORED_SSID_PREFIXES = (
    "direct-", "hp-print", "epson", "canon", "brother",
    "dashcam", "printer", "[lg_", "tv", "cast"
)

def get_wifi_info() -> dict:
    """Retrieves current Wi-Fi status using Windows netsh command."""
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
    """Probes NCSI connecttest.txt to check for a captive portal."""
    result = {
        "has_internet": False,
        "is_captive": False,
        "portal_url": "",
        "details": "",
        "status_code": None
    }
    probe_url = config.get("connecttest_url", "http://www.msftconnecttest.com/connecttest.txt")
    redirect_url = config.get("portal_redirect_url", "http://www.msftconnecttest.com/redirect")

    # Probe connecttest.txt without following redirects
    try:
        r = requests.get(probe_url, headers=_PROBE_HEADERS, timeout=1.8, allow_redirects=False)
        result["status_code"] = r.status_code

        if r.status_code in (301, 302, 303, 307, 308):
            loc = r.headers.get("Location", "")
            if "go.microsoft.com" not in loc and "msftconnecttest" not in loc:
                result.update({
                    "is_captive": True,
                    "portal_url": loc or redirect_url,
                    "details": f"Phát hiện Captive Portal: {loc or redirect_url}"
                })
                return result

        if r.status_code == 200:
            if r.text.strip() == "Microsoft Connect Test":
                result.update({"has_internet": True, "details": "Đã kết nối Internet"})
                return result
            result.update({
                "is_captive": True,
                "portal_url": redirect_url,
                "details": "Phát hiện Captive Portal"
            })
            return result
    except Exception as e:
        result["details"] = f"Lỗi kết nối probe: {e}"

    # Fallback redirect probe
    try:
        r2 = requests.get(redirect_url, headers=_PROBE_HEADERS, timeout=1.8, allow_redirects=False)
        loc2 = r2.headers.get("Location", "")
        if r2.status_code in (301, 302, 303, 307, 308):
            if "go.microsoft.com" in loc2:
                result.update({"has_internet": True, "details": "Đã kết nối Internet"})
            else:
                result.update({
                    "is_captive": True,
                    "portal_url": loc2 or redirect_url,
                    "details": f"Phát hiện Captive Portal: {loc2 or redirect_url}"
                })
    except Exception:
        pass

    return result

def get_known_wifi_profiles() -> set:
    """Returns a set of all saved/known Wi-Fi profile names on the Windows system."""
    profiles = set()
    try:
        proc = subprocess.run(
            ["netsh", "wlan", "show", "profiles"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        for line in proc.stdout.splitlines():
            if ":" not in line:
                continue
            parts = line.split(":", 1)
            k = parts[0].strip().lower()
            if "profile" in k or "hồ sơ" in k:
                raw_v = parts[1]
                v = raw_v[1:] if raw_v.startswith(" ") else raw_v
                if v:
                    profiles.add(v)
                    profiles.add(v.strip())
    except Exception as e:
        print(f"[Network] Error getting known profiles: {e}")
    return profiles

_wlan_types = None

def _get_wlan_types():
    global _wlan_types
    if _wlan_types is None:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ('Data1', wintypes.DWORD),
                ('Data2', wintypes.WORD),
                ('Data3', wintypes.WORD),
                ('Data4', wintypes.BYTE * 8)
            ]

        class WLAN_INTERFACE_INFO(ctypes.Structure):
            _fields_ = [
                ('InterfaceGuid', GUID),
                ('strInterfaceDescription', wintypes.WCHAR * 256),
                ('isState', wintypes.DWORD)
            ]

        class WLAN_INTERFACE_INFO_LIST(ctypes.Structure):
            _fields_ = [
                ('dwNumberOfItems', wintypes.DWORD),
                ('dwIndex', wintypes.DWORD),
                ('InterfaceInfo', WLAN_INTERFACE_INFO * 1)
            ]

        _wlan_types = (ctypes, wintypes, ctypes.windll.wlanapi, WLAN_INTERFACE_INFO_LIST)
    return _wlan_types

def trigger_wifi_scan() -> bool:
    """Triggers an active 802.11 BSS scan via native Windows WlanScan API."""
    try:
        ctypes, wintypes, wlan, WLAN_INTERFACE_INFO_LIST = _get_wlan_types()
        negotiated_version = wintypes.DWORD()
        client_handle = wintypes.HANDLE()

        ret = wlan.WlanOpenHandle(2, None, ctypes.byref(negotiated_version), ctypes.byref(client_handle))
        if ret == 0:
            try:
                pp_list = ctypes.POINTER(WLAN_INTERFACE_INFO_LIST)()
                ret_enum = wlan.WlanEnumInterfaces(client_handle, None, ctypes.byref(pp_list))
                if ret_enum == 0 and pp_list.contents.dwNumberOfItems > 0:
                    guid = pp_list.contents.InterfaceInfo[0].InterfaceGuid
                    return wlan.WlanScan(client_handle, ctypes.byref(guid), None, None, None) == 0
            finally:
                wlan.WlanCloseHandle(client_handle, None)
    except Exception as e:
        print(f"[Network] WlanScan error: {e}")
    return False

def scan_available_networks(trigger_active_scan: bool = False) -> list:
    """Scans for currently visible Wi-Fi networks in range using netsh."""
    if trigger_active_scan:
        trigger_wifi_scan()
        time.sleep(1.2)

    networks = []
    current = None
    try:
        proc = subprocess.run(
            ["netsh", "wlan", "show", "networks", "mode=bssid"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        for line in proc.stdout.splitlines():
            line_s = line.strip()
            if not line_s:
                continue

            m_ssid = re.match(r'^SSID\s+\d+\s*:\s*(.*)$', line_s)
            if m_ssid:
                if current and current.get("ssid"):
                    networks.append(current)
                current = {
                    "ssid": m_ssid.group(1).strip(),
                    "auth": "",
                    "encryption": "",
                    "signal": 0,
                    "bssids": []
                }
                continue

            if current is not None and ":" in line_s:
                k, v = [x.strip() for x in line_s.split(":", 1)]
                kl = k.lower()
                if "authentication" in kl or "xác thực" in kl:
                    current["auth"] = v
                elif "encryption" in kl or "mã hóa" in kl:
                    current["encryption"] = v
                elif "signal" in kl or "tín hiệu" in kl:
                    sig_m = re.search(r'(\d+)%', v)
                    if sig_m:
                        val = int(sig_m.group(1))
                        if val > current["signal"]:
                            current["signal"] = val
                elif "bssid" in kl:
                    current["bssids"].append(v)

        if current and current.get("ssid"):
            networks.append(current)
    except Exception as e:
        print(f"[Network] Error scanning networks: {e}")

    return networks

def is_open_network(net: dict) -> bool:
    """Checks if a network is unencrypted/open."""
    auth = net.get("auth", "").lower()
    enc = net.get("encryption", "").lower()
    return "open" in auth or "none" in enc or auth == "mở" or enc == "không có"

def score_captive_candidate(net: dict, known_profiles: set = None) -> int:
    """Calculates priority score for candidate captive portal network."""
    ssid = net.get("ssid", "")
    ssid_lower = ssid.lower()
    score = net.get("signal", 0)
    if any(kw in ssid_lower for kw in _CAPTIVE_KEYWORDS):
        score += 50
    if known_profiles and ssid in known_profiles:
        score += 35
    return score

def get_available_open_networks(networks: list = None, known_profiles: set = None) -> list:
    """Returns candidate open networks sorted by captive portal likelihood and signal."""
    if networks is None:
        networks = scan_available_networks()

    if known_profiles is None:
        known_profiles = get_known_wifi_profiles()

    open_nets = []
    for n in networks:
        ssid = n.get("ssid", "").strip()
        if not ssid:
            continue
        ssid_lower = ssid.lower()
        if any(ssid_lower.startswith(p) for p in _IGNORED_SSID_PREFIXES):
            continue
        if is_open_network(n):
            open_nets.append(n)

    open_nets.sort(key=lambda n: score_captive_candidate(n, known_profiles), reverse=True)
    return open_nets

def create_open_wifi_profile(ssid: str) -> bool:
    """Creates and registers a temporary open Wi-Fi profile on Windows."""
    safe_ssid = saxutils.escape(ssid, {'"': '&quot;', "'": '&apos;'})
    hex_ssid = ssid.encode('utf-8').hex().upper()

    xml_content = f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{safe_ssid}</name>
    <SSIDConfig>
        <SSID>
            <hex>{hex_ssid}</hex>
            <name>{safe_ssid}</name>
        </SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>manual</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>open</authentication>
                <encryption>none</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
        </security>
    </MSM>
</WLANProfile>"""

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(xml_content)
            tmp_path = f.name

        res = subprocess.run(
            ["netsh", "wlan", "add", "profile", f"filename={tmp_path}", "user=current"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        return res.returncode == 0 or "added" in res.stdout.lower() or "đã thêm" in res.stdout.lower()
    except Exception as e:
        print(f"[Network] Error adding open wifi profile: {e}")
        return False
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

def connect_to_wifi(ssid: str, timeout: float = 7.0) -> bool:
    """Connects to a Wi-Fi network by SSID."""
    known = get_known_wifi_profiles()
    if ssid not in known and ssid.strip() not in known:
        create_open_wifi_profile(ssid)

    try:
        proc = subprocess.run(
            ["netsh", "wlan", "connect", f"name={ssid}", f"ssid={ssid}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        if proc.returncode != 0 and "completed successfully" not in proc.stdout.lower() and "thành công" not in proc.stdout.lower():
            subprocess.run(
                ["netsh", "wlan", "connect", f"name={ssid}"],
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )

        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(0.5)
            info = get_wifi_info()
            if info.get("connected") and info.get("ssid", "").strip().lower() == ssid.strip().lower():
                return True
    except Exception as e:
        print(f"[Network] Error connecting to wifi {ssid}: {e}")

    return False
