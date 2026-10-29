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

    name = "AWING Connect"

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
            "v2.awingconnect.vn",
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
            'name="ciscomeraki"',
            "ciscomeraki",
            "awingconstants",
            "awingcaptiveutils",
            "hslogin.cgi",
            "network-auth.com",
        ]
        if any(ind in lower_html for ind in indicators):
            return True

        # 3. Check for hidden input with username 'awing...'
        if 'name="username"' in lower_html and 'value="awing' in lower_html:
            return True

        return False

    def solve_http(self, session: requests.Session, portal_url: str, html: str) -> Optional[Dict[str, Any]]:
        """
        Direct HTTP Fast Path supports three AWING gateway types:

        A) Extreme Networks (172.x.x.x:880/cgi-bin/hslogin.cgi) - Circle K, Ministop
           Parameters: hs_server and Qv from portal redirect URL
           Credentials: f_user=awing120, f_pass=Awing120@2018

        B) Cisco Meraki (apac.network-auth.com/splash/.../login) - GS25
           Form: form[name='ciscoMeraki']

        C) MikroTik (186.186.0.1/login) - Airports, cafes, Wi-Mesh Rescue
           Form: form[name='mikrotik']
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
                form = soup.find("form", {"name": "extreme"})
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
                    "message": f"Gửi xác thực Extreme Networks HTTP: {hs_server}"
                }
        except Exception:
            pass

        # --- 2. Try Cisco Meraki fast-path (GS25, retail stores) ---
        try:
            if not html:
                try:
                    resp = session.get(portal_url, timeout=3.0, allow_redirects=True)
                    portal_url = resp.url
                    html = resp.text
                except Exception:
                    pass

            if html:
                soup = BeautifulSoup(html, "html.parser")
                meraki_form = soup.find("form", {"name": "ciscoMeraki"}) or soup.find("form", id="frmLogin")
                if not meraki_form and ("network-auth.com" in portal_url or "splash" in portal_url):
                    # Follow redirect to AWING portal if needed
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
                        resp = session.get(redirect_url, timeout=3.0, allow_redirects=True)
                        portal_url = resp.url
                        html = resp.text
                        soup = BeautifulSoup(html, "html.parser")
                        meraki_form = soup.find("form", {"name": "ciscoMeraki"}) or soup.find("form", id="frmLogin")

                if meraki_form:
                    m_action = meraki_form.get("action") or ""
                    m_name = (meraki_form.get("name") or "").lower()
                    if m_name == "ciscomeraki" or "network-auth.com" in m_action:
                        data = {}
                        for input_tag in meraki_form.find_all("input"):
                            name = input_tag.get("name")
                            if name:
                                data[name] = input_tag.get("value", "")
                        if data.get("username") and m_action.startswith("http"):
                            headers = {
                                "Referer": portal_url,
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                            }
                            session.post(m_action, data=data, headers=headers, timeout=3.5)
                            return {
                                "success": True,
                                "message": f"Gửi xác thực Cisco Meraki HTTP: {data.get('username')}"
                            }
        except Exception:
            pass

        # --- 3. Try MikroTik fast-path (airports, cafes, Wi-Mesh Rescue) ---
        try:
            if not html:
                try:
                    resp = session.get(portal_url, timeout=3.0, allow_redirects=True)
                    portal_url = resp.url
                    html = resp.text
                except Exception:
                    pass

            if html:
                soup = BeautifulSoup(html, "html.parser")
                form = soup.find("form", {"name": "mikrotik"})

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
                        resp = session.get(redirect_url, timeout=3.0, allow_redirects=True)
                        portal_url = resp.url
                        html = resp.text
                        soup = BeautifulSoup(html, "html.parser")
                        form = soup.find("form", {"name": "mikrotik"})

                if not form and "186.186." in portal_url:
                    form = soup.find("form", {"id": "frmLogin"})

                if form:
                    action = form.get("action") or "http://186.186.0.1/login"
                    form_name = (form.get("name") or "").lower()
                    # Strictly ensure it is MikroTik, not Meraki or Extreme
                    if form_name == "mikrotik" or "186.186." in action or "186.186." in portal_url:
                        if not action.startswith("http"):
                            action = urllib.parse.urljoin(portal_url, action)

                        data = {}
                        for input_tag in form.find_all("input"):
                            name = input_tag.get("name")
                            if name:
                                data[name] = input_tag.get("value", "")

                        if data.get("username"):
                            method = (form.get("method") or "post").lower()
                            if method == "get":
                                session.get(action, params=data, timeout=3.5)
                            else:
                                session.post(action, data=data, timeout=3.5)
                            return {
                                "success": True,
                                "message": f"Gửi xác thực MikroTik HTTP: {data.get('username')}"
                            }
        except Exception:
            pass

        return None

    def get_browser_script(self) -> str:
        """
        Universal browser automation script for AWING portals.
        Prioritizes traditional button clicking (phương pháp bấm nút thủ công)
        so that ANY current or future AWING Wi-Fi network operates reliably!
        """
        return """
        (function() {
            let result = { status: "searching", buttonClicked: null };

            try {
                // Helper: safely check element visibility
                function isVisible(el) {
                    if (!el) return false;
                    try {
                        if (typeof el.checkVisibility === 'function') {
                            return el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true });
                        }
                        let style = window.getComputedStyle(el);
                        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                        return el.offsetParent !== null || (el.getClientRects && el.getClientRects().length > 0);
                    } catch(e) {
                        return true;
                    }
                }

                // Helper: safely click an element with full mouse event simulation
                function simulateClick(el) {
                    if (!el) return false;
                    try { el.scrollIntoView({ behavior: 'instant', block: 'center' }); } catch(e) {}
                    try {
                        if (typeof MouseEvent !== 'undefined') {
                            el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true, cancelable: true }));
                            el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
                            el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));
                        }
                    } catch(e) {}
                    try { el.click(); } catch(e) {}
                    return true;
                }

                // Helper: identify true MikroTik gateway (Wi-Mesh Rescue / 186.186.x.x)
                function isTrueMikrotikForm(f) {
                    if (!f) return false;
                    let name = (f.getAttribute("name") || "").toLowerCase();
                    let action = (f.getAttribute("action") || "").toLowerCase();
                    let href = window.location.href.toLowerCase();
                    if (name === "ciscomeraki" || name === "extreme" || action.includes("hslogin.cgi") || action.includes("network-auth.com")) {
                        return false;
                    }
                    return name === "mikrotik" || action.includes("186.186.") || href.includes("186.186.");
                }

                // 1. Check for promotional voucher / CPA overlay (Circle K style: "Miễn phí 01 Trà Chanh-Yuzu")
                // Target: "CHỈ KẾT NỐI WI-FI" / "BỎ QUA" to reveal main connect screen
                let cpaSecondary = Array.from(document.querySelectorAll("button.option-secondary, .option-button, button, a"))
                    .find(b => {
                        let t = (b.innerText || b.textContent || "").toLowerCase();
                        return (t.includes("chỉ kết nối") || t.includes("bỏ qua") || b.classList.contains("option-secondary")) && isVisible(b);
                    });
                if (cpaSecondary) {
                    try {
                        simulateClick(cpaSecondary);
                        result.status = "advanced_state";
                        result.buttonClicked = "Bỏ qua voucher";
                        return result;
                    } catch(e) {}
                }

                // 2. TRADITIONAL BUTTON CLICKING (PHƯƠNG PHÁP BẤM NÚT THỦ CÔNG)
                // Primary interactive connect button: #acceptconnection_BannerOverflow, button.connect-button, etc.
                // Ensures GS25, Circle K, Airports, Cafes, and ALL future AWING networks work naturally!
                let acceptBtn = document.getElementById("acceptconnection_BannerOverflow")
                    || document.querySelector("button.connect-button")
                    || Array.from(document.querySelectorAll("button, a, div[role='button']")).find(b => {
                        let t = (b.innerText || b.textContent || "").trim().toLowerCase();
                        return (t.includes("kết nối internet") || t.includes("internet access") || t.includes("tiếp tục để kết nối") || t.includes("kết nối ngay"))
                            && b.id !== "acceptconnection_BannerOverflow" && isVisible(b);
                    });

                if (acceptBtn && isVisible(acceptBtn)) {
                    let isDisabled = acceptBtn.disabled || acceptBtn.getAttribute("aria-disabled") === "true" || acceptBtn.classList.contains("disabled");
                    if (isDisabled) {
                        result.status = "waiting_ad_timer";
                        result.buttonClicked = "Đang đếm ngược";
                        return result;
                    }
                    if (acceptBtn.dataset && acceptBtn.dataset.autowificlicked === "true") {
                        result.status = "waiting_ad_timer";
                        result.buttonClicked = "Đang kết nối...";
                        return result;
                    }
                    try {
                        acceptBtn.dataset.autowificlicked = "true";
                        simulateClick(acceptBtn);
                        if (window.awingStateMachineContextActions && typeof window.awingStateMachineContextActions.nextView === "function") {
                            try { window.awingStateMachineContextActions.nextView(); } catch(e) {}
                        }
                        result.status = "clicked";
                        result.buttonClicked = "Kết nối Internet";
                        return result;
                    } catch(e) {}
                }

                // 3. Clickable banner image (#banner)
                let bannerImg = document.getElementById("banner");
                if (bannerImg && bannerImg.getAttribute("onclick") && isVisible(bannerImg)) {
                    if (bannerImg.dataset && bannerImg.dataset.autowificlicked === "true") {
                        result.status = "waiting_ad_timer";
                        result.buttonClicked = "Đang kết nối...";
                        return result;
                    }
                    try {
                        bannerImg.dataset.autowificlicked = "true";
                        simulateClick(bannerImg);
                        if (window.awingStateMachineContextActions && typeof window.awingStateMachineContextActions.nextView === "function") {
                            try { window.awingStateMachineContextActions.nextView(); } catch(e) {}
                        }
                        result.status = "clicked";
                        result.buttonClicked = "Kết nối Internet";
                        return result;
                    } catch(e) {}
                }

                // 4. Drive AWING State Machine directly if needed (completeAd / nextView)
                let stateAdvanced = false;
                if (window.awingStateMachineContextActions) {
                    let actions = window.awingStateMachineContextActions;
                    if (typeof actions.nextView === "function") {
                        try {
                            actions.nextView();
                            stateAdvanced = true;
                        } catch(e) {}
                    }
                    if (typeof actions.completeAd === "function") {
                        try {
                            actions.completeAd();
                            stateAdvanced = true;
                        } catch(e) {}
                    }
                }

                // 5. Click logo_button (AWING ad transition button)
                let logoBtn = document.getElementById("logo_button");
                if (logoBtn && !logoBtn.disabled && isVisible(logoBtn)) {
                    try {
                        simulateClick(logoBtn);
                        stateAdvanced = true;
                    } catch(e) {}
                }

                // 6. Handle Welcome / Authenticating Screen (#awing-captive__welcome-loading)
                let welcome = document.getElementById("awing-captive__welcome-loading");
                let isWelcomeVisible = welcome && isVisible(welcome);

                if (isWelcomeVisible || stateAdvanced) {
                    let frmLogin = document.getElementById("frmLogin");
                    let frmName = frmLogin ? (frmLogin.getAttribute("name") || "").toLowerCase() : "";

                    // True MikroTik bypass behind welcome screen (Wi-Mesh Rescue / 186.186.0.1)
                    let mBehind = document.querySelector("form[name='mikrotik']")
                        || (isTrueMikrotikForm(frmLogin) ? frmLogin : null);

                    if (mBehind && isTrueMikrotikForm(mBehind)) {
                        let uB = mBehind.querySelector("input[name='username']");
                        if (uB && uB.value) {
                            try {
                                if (!mBehind.action || mBehind.action === window.location.href) {
                                    mBehind.action = "http://186.186.0.1/login";
                                }
                                mBehind.submit();
                                result.status = "clicked";
                                result.buttonClicked = "Bypass MikroTik";
                                return result;
                            } catch(e) {}
                        }
                    }

                    // For Cisco Meraki (GS25) or Extreme (Circle K):
                    // AWING naturally submits via SubmitAuthenticationFormWithIframe().
                    // If not yet triggered, trigger it as fallback:
                    let isIframeAuthen = frmName === "ciscomeraki" || frmName === "extreme"
                        || (frmLogin && frmLogin.getAttribute("target") === "loginFrame")
                        || (window.awingStateMachineContext && window.awingStateMachineContext.getAuthenType && window.awingStateMachineContext.getAuthenType() === 2);

                    if (isIframeAuthen && !document.querySelector("#redirecting-iframe") && window.awingUIActions && typeof window.awingUIActions.SubmitAuthenticationFormWithIframe === "function") {
                        try {
                            window.awingUIActions.SubmitAuthenticationFormWithIframe();
                            result.status = "clicked";
                            result.buttonClicked = frmName === "ciscomeraki" ? "Xác thực Cisco Meraki" : "Xác thực Extreme Networks";
                            return result;
                        } catch(e) {}
                    }

                    if (isWelcomeVisible) {
                        result.status = "waiting_ad_timer";
                        result.buttonClicked = "Đang kết nối...";
                        return result;
                    }
                }

                if (stateAdvanced) {
                    result.status = "advanced_state";
                    result.buttonClicked = "Bỏ qua quảng cáo";
                    return result;
                }

                // 7. Generic connect/continue buttons fallback (for any future/unhandled AWING variants)
                let buttons = Array.from(document.querySelectorAll("button, a, div[role='button'], input[type='button'], input[type='submit']"));
                let keywords = [
                    "tiếp tục để kết nối", "tiếp tục", "kết nối internet",
                    "internet access", "kết nối ngay", "truy cập ngay", "chỉ kết nối",
                    "kết nối", "connect", "access"
                ];
                let target = null;
                for (let btn of buttons) {
                    let txt = (btn.innerText || btn.textContent || btn.value || "").trim().toLowerCase();
                    if (keywords.some(kw => txt.includes(kw)) && isVisible(btn)) {
                        target = btn;
                        break;
                    }
                }
                if (!target) {
                    let cand = document.querySelector(".btn-connect, .btn-primary, [class*='connect'], [class*='submit']");
                    if (cand && isVisible(cand)) {
                        target = cand;
                    }
                }
                if (target) {
                    let isDisabled = target.disabled || target.getAttribute("aria-disabled") === "true" || target.classList.contains("disabled");
                    if (isDisabled) {
                        result.status = "waiting_ad_timer";
                        result.buttonClicked = "Đang đếm ngược";
                        return result;
                    }
                    if (target.dataset && target.dataset.autowificlicked === "true") {
                        result.status = "waiting_ad_timer";
                        result.buttonClicked = "Đang kết nối...";
                        return result;
                    }
                    target.dataset.autowificlicked = "true";
                    simulateClick(target);
                    result.status = "clicked";
                    result.buttonClicked = "Kết nối Internet";
                    return result;
                }

            } catch (err) {
                result.status = "error: " + err.message;
            }

            return result;
        })();
        """
