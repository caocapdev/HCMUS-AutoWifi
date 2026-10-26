import re
import urllib.parse
from typing import Optional, Dict, Any
import requests
from bs4 import BeautifulSoup
from core.portals.base import BasePortal

class AwingPortal(BasePortal):
    """
    Strategy for AWING Connect Wi-Fi portals.
    Commonly found at:
      - Circle K, Ministop, GS25 (v1.awingconnect.vn)
      - Noi Bai & Tan Son Nhat Airport
      - Highlands Coffee, Phuc Long, The Coffee House
      - Vincom, Big C / GO!, KTX Wi-Mesh Rescue
    """

    name = "AWING Connect (Sân bay / Quán Cafe / Cửa hàng tiện lợi)"

    def match(self, url: str, html: str) -> bool:
        lower_url = url.lower()
        lower_html = html.lower()

        # 1. Direct domain, gateway IP, or portal network matches
        if any(d in lower_url for d in ["awingconnect.vn", "v1.awingconnect.vn", "awing.vn", "awing", "186.186."]):
            return True

        # 2. Key phrases in HTML from AWING template
        indicators = [
            "awingconnect.vn",
            "v1.awingconnect.vn",
            "awing.vn",
            "powered by awing",
            "ads by awing",
            "free wi-fi | awing",
            "wi-fi miễn phí tài trợ bởi",
            "circle k wi-fi miễn phí",
            "tiếp tục để kết nối internet",
            "tiếp tục để kết nối",
            "186.186.",
            "awing-captive",
            "awingstatemachine",
            "awingcaptive",
            "frmlogin",
            'name="mikrotik"',
            'name="extreme"',
            "awingconstants",
            "awingcaptiveutils",
            "hslogin.cgi",
        ]
        if any(ind in lower_html for ind in indicators):
            return True

        # 3. Check for hidden input with username 'awing...'
        if 'name="username"' in lower_html and 'value="awing' in lower_html:
            return True

        return False

    def solve_http(self, session: requests.Session, portal_url: str, html: str) -> Optional[Dict[str, Any]]:
        """
        Direct HTTP Fast Path supports two AWING gateway types:

        A) Extreme Networks (172.x.x.x:880/cgi-bin/hslogin.cgi) - Circle K, GS25, Ministop
           Parameters: hs_server and Qv from portal redirect URL
           Credentials: f_user=awing120, f_pass=Awing120@2018
           POST is sent directly to http://{hs_server}:880/cgi-bin/hslogin.cgi

        B) MikroTik (186.186.0.1/login) - Airports, cafes, Wi-Mesh Rescue
           Extracted from HTML form[name='mikrotik'] or #frmLogin
        """
        import time as _time

        # --- 1. Try Extreme Networks fast-path directly from URL query parameters ---
        try:
            parsed_url = urllib.parse.urlparse(portal_url)
            qs = urllib.parse.parse_qs(parsed_url.query, keep_blank_values=True)
            hs_server = qs.get("hs_server", [None])[0]
            qv = qs.get("Qv", [None])[0]

            # If not in URL, try extracting from HTML form
            if (not hs_server or not qv) and html:
                soup = BeautifulSoup(html, "html.parser")
                form = soup.find("form", {"name": "extreme"}) or soup.find("form", {"id": "frmLogin"})
                if form:
                    if not hs_server:
                        hs_in = form.find("input", {"name": "f_hs_server"})
                        hs_server = hs_in.get("value", "") if hs_in else None
                    if not qv:
                        qv_in = form.find("input", {"name": "f_Qv"})
                        qv = qv_in.get("value", "") if qv_in else None

            if hs_server and qv:
                post_data = {
                    "f_user": "awing120",
                    "f_pass": "Awing120@2018",
                    "f_hs_server": hs_server,
                    "f_curr_time": str(int(_time.time())),
                    "f_Qv": qv,
                }
                action = f"http://{hs_server}:880/cgi-bin/hslogin.cgi"
                headers = {
                    "Origin": f"{parsed_url.scheme}://{parsed_url.netloc}" if parsed_url.netloc else "http://v1.awingconnect.vn",
                    "Referer": portal_url,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                }
                session.post(action, data=post_data, headers=headers, timeout=3.5)
                return {
                    "success": True,
                    "message": f"Đã gửi xác thực Extreme Networks ({hs_server}) qua HTTP"
                }
        except Exception:
            pass

        # --- 2. Try MikroTik fast-path (airports, cafes, Wi-Mesh Rescue) ---
        try:
            soup = BeautifulSoup(html, "html.parser")
            form = soup.find("form", {"name": "mikrotik"}) or soup.find("form", {"id": "frmLogin"})

            if not form:
                # Follow redirects if needed
                redirect_url = None
                meta = soup.find("meta", attrs={"http-equiv": re.compile(r"refresh", re.I)})
                if meta and meta.get("content"):
                    m = re.search(r"url=['\"]?([^'\"]+)", meta["content"], re.I)
                    if m:
                        redirect_url = m.group(1).strip()
                if not redirect_url:
                    m = re.search(r"(?:window\.)?location(?:\.href)?\s*=\s*['\"]([^'\"]+)['\"]", html, re.I)
                    if m:
                        redirect_url = m.group(1).strip()
                if redirect_url:
                    redirect_url = urllib.parse.urljoin(portal_url, redirect_url)
                    resp = session.get(redirect_url, timeout=3.5, allow_redirects=True)
                    portal_url = resp.url
                    html = resp.text
                    soup = BeautifulSoup(html, "html.parser")
                    form = soup.find("form", {"name": "mikrotik"}) or soup.find("form", {"id": "frmLogin"})

            if not form:
                for f in soup.find_all("form"):
                    u_in = f.find("input", {"name": "username"})
                    if u_in and "awing" in u_in.get("value", "").lower():
                        form = f
                        break

            if form:
                u_in = form.find("input", {"name": "username"})
                action = form.get("action") or "http://186.186.0.1/login"
                if not action.startswith("http"):
                    action = urllib.parse.urljoin(portal_url, action)

                if u_in or "186.186." in action or "mikrotik" in str(form.get("name", "")).lower():
                    data = {}
                    for input_tag in form.find_all("input"):
                        name = input_tag.get("name")
                        if name:
                            data[name] = input_tag.get("value", "")
                    method = (form.get("method") or "post").lower()
                    if method == "get":
                        session.get(action, params=data, timeout=4)
                    else:
                        session.post(action, data=data, timeout=4)
                    return {
                        "success": True,
                        "message": f"Đã gửi xác thực AWING MikroTik ({data.get('username', 'auto')}) qua HTTP"
                    }
        except Exception:
            pass

        return None

    def get_browser_script(self) -> str:
        """
        Browser automation script for AWING portals:
        1. Clicks CPA voucher skip button: 'CHỈ KẾT NỐI WI-FI' (Circle K)
        2. Clicks banner connect buttons: #acceptconnection_BannerOverflow, .connect-button
        3. Drives AWING State Machine directly: completeAd() / nextView()
        4. Clicks logo_button (tiếp tục để kết nối)
        5. Handles MikroTik / Extreme Networks iframe authentications safely
        """
        return """
        (function() {
            let result = { status: "searching", buttonClicked: null };

            try {
                // 1. Check for CPA Voucher screen (Circle K style: "Miễn phí 01 Trà Chanh-Yuzu")
                // Target: "CHỈ KẾT NỐI WI-FI" button to bypass voucher ad
                let cpaSecondary = Array.from(document.querySelectorAll("button.option-secondary, .option-button, button, a"))
                    .find(b => {
                        let t = (b.innerText || b.textContent || "").toLowerCase();
                        return t.includes("chỉ kết nối") || t.includes("bỏ qua") || b.classList.contains("option-secondary");
                    });
                if (cpaSecondary) {
                    try {
                        cpaSecondary.click();
                        result.status = "advanced_state";
                        result.buttonClicked = "CHỈ KẾT NỐI WI-FI (CPA Voucher)";
                        return result;
                    } catch(e) {}
                }

                // 2. Check for AWING banner connect buttons (Circle K 2/3 style, airport/cafe banners)
                // Button: id="acceptconnection_BannerOverflow" or class="connect-button"
                let acceptBtn = document.getElementById("acceptconnection_BannerOverflow")
                    || document.querySelector("button.connect-button")
                    || Array.from(document.querySelectorAll("button, a")).find(b => {
                        let t = (b.innerText || b.textContent || "").trim().toLowerCase();
                        return t.includes("kết nối internet") || t.includes("internet access");
                    });
                if (acceptBtn && !acceptBtn.disabled) {
                    try {
                        acceptBtn.click();
                        result.status = "advanced_state";
                        result.buttonClicked = (acceptBtn.innerText || "KẾT NỐI INTERNET").trim();
                        return result;
                    } catch(e) {}
                }

                // 3. Drive AWING State Machine directly
                // If window.awingStateMachineContextActions is available, trigger completeAd()
                // completeAd() transitions straight to "Submit" -> "Authentication" -> SubmitAuthenticationFormWithIframe()
                if (window.awingStateMachineContextActions) {
                    let actions = window.awingStateMachineContextActions;
                    if (typeof actions.completeAd === "function") {
                        try {
                            actions.completeAd();
                            result.status = "clicked";
                            result.buttonClicked = "completeAd (State Machine)";
                            return result;
                        } catch(e) {}
                    }
                    if (typeof actions.nextView === "function") {
                        try {
                            actions.nextView();
                            result.status = "advanced_state";
                            result.buttonClicked = "nextView (State Machine)";
                            return result;
                        } catch(e) {}
                    }
                }

                // 4. Click logo_button (AWING ad transition button)
                let logoBtn = document.getElementById("logo_button");
                if (logoBtn && !logoBtn.disabled) {
                    try {
                        logoBtn.click();
                        result.status = "advanced_state";
                        result.buttonClicked = "logo_button (Tiếp tục)";
                        return result;
                    } catch(e) {}
                }

                // 5. If welcome/authenticating animation is currently running:
                let welcome = document.getElementById("awing-captive__welcome-loading");
                if (welcome && getComputedStyle(welcome).display !== "none") {
                    result.status = "waiting_ad_timer";
                    result.buttonClicked = "Đang kết nối Internet...";
                    return result;
                }

                // 6. Direct iframe authentication fallback if Extreme form is in DOM
                let exForm = document.querySelector("form[name='extreme']");
                if (exForm && window.awingUIActions && typeof window.awingUIActions.SubmitAuthenticationFormWithIframe === "function") {
                    try {
                        window.awingUIActions.SubmitAuthenticationFormWithIframe();
                        result.status = "clicked";
                        result.buttonClicked = "SubmitAuthenticationFormWithIframe (Extreme Networks)";
                        return result;
                    } catch(e) {}
                }

                // 7. MikroTik standalone form fallback (airports / cafes / Wi-Mesh Rescue)
                let mForm = document.querySelector("form[name='mikrotik']");
                if (mForm) {
                    try {
                        if (!mForm.action || mForm.action === window.location.href) {
                            mForm.action = "http://186.186.0.1/login";
                        }
                        mForm.submit();
                        result.status = "clicked";
                        result.buttonClicked = "frmLogin (MikroTik)";
                        return result;
                    } catch(e) {}
                }

                // 8. Generic connect/continue buttons
                let buttons = Array.from(document.querySelectorAll("button, a, div[role='button'], input[type='button'], input[type='submit']"));
                let keywords = [
                    "tiếp tục để kết nối", "tiếp tục", "kết nối internet",
                    "internet access", "kết nối ngay", "truy cập ngay", "chỉ kết nối"
                ];
                let target = null;
                for (let btn of buttons) {
                    let txt = (btn.innerText || btn.textContent || btn.value || "").trim().toLowerCase();
                    if (keywords.some(kw => txt.includes(kw))) {
                        target = btn;
                        break;
                    }
                }
                if (!target) {
                    target = document.querySelector(".btn-connect, .btn-primary, [class*='connect'], [class*='submit']");
                }
                if (target) {
                    let isDisabled = target.disabled || target.getAttribute("aria-disabled") === "true" || target.classList.contains("disabled");
                    if (isDisabled) {
                        result.status = "waiting_ad_timer";
                        result.buttonClicked = (target.innerText || "Đang đếm ngược").trim();
                        return result;
                    }
                    target.scrollIntoView({ behavior: 'instant', block: 'center' });
                    target.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                    target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                    target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                    target.click();
                    result.status = "advanced_state";
                    result.buttonClicked = (target.innerText || "KẾT NỐI INTERNET").trim();
                    return result;
                }

            } catch (err) {
                result.status = "error: " + err.message;
            }

            return result;
        })();
        """
