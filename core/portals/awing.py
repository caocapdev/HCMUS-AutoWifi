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
      - Circle K, Ministop, GS25, 7-Eleven (v1.awingconnect.vn)
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
            "awingconnect.vn", "v1.awingconnect.vn", "v2.awingconnect.vn", "awing.vn",
            "powered by awing", "ads by awing", "free wi-fi | awing", "wi-fi miễn phí tài trợ bởi",
            "circle k wi-fi miễn phí", "tiếp tục để kết nối internet", "tiếp tục để kết nối",
            "186.186.", "awing-captive", "awingstatemachine", "awingcaptive", "frmlogin",
            'name="mikrotik"', 'name="extreme"', 'name="ciscomeraki"', "ciscomeraki",
            "awingconstants", "awingcaptiveutils", "hslogin.cgi", "network-auth.com",
        ]
        if any(ind in lower_html for ind in indicators):
            return True

        # 3. Hidden input with username starting with 'awing'
        return 'name="username"' in lower_html and 'value="awing' in lower_html

    def solve_http(self, session: requests.Session, portal_url: str, html: str) -> Optional[Dict[str, Any]]:
        """
        Direct HTTP Fast Path supports three AWING gateway types:
          A) Extreme Networks (172.x.x.x:880/cgi-bin/hslogin.cgi)
          B) Cisco Meraki (network-auth.com/splash/...) - Sign-on & Click-Through Grant
          C) MikroTik (186.186.0.1/login)
        """
        import time as _time

        parsed_url = urllib.parse.urlparse(portal_url)
        qs = urllib.parse.parse_qs(parsed_url.query, keep_blank_values=True)

        if not html:
            try:
                resp = session.get(portal_url, timeout=3.0, allow_redirects=True)
                portal_url, html = resp.url, resp.text
                parsed_url = urllib.parse.urlparse(portal_url)
                qs = urllib.parse.parse_qs(parsed_url.query, keep_blank_values=True)
            except Exception:
                pass

        soup = BeautifulSoup(html, "html.parser") if html else None

        # Resolve initial splash page meta/JS redirect if landing without forms
        if soup and not soup.find("form") and ("network-auth.com" in portal_url or "splash" in portal_url or "186.186." in portal_url):
            redir = None
            meta = soup.find("meta", attrs={"http-equiv": re.compile(r"refresh", re.I)})
            if meta and meta.get("content"):
                m = re.search(r"""url=['"]?([^'"]+)""", meta["content"], re.I)
                if m: redir = m.group(1).strip()
            if not redir:
                m = re.search(r"""(?:window\.)?location(?:\.href)?\s*=\s*['"]([^'"]+)['"]""", html, re.I)
                if m: redir = m.group(1).strip()
            if redir:
                try:
                    redir_url = urllib.parse.urljoin(portal_url, redir)
                    resp = session.get(redir_url, timeout=3.0, allow_redirects=True)
                    portal_url, html = resp.url, resp.text
                    parsed_url = urllib.parse.urlparse(portal_url)
                    qs = urllib.parse.parse_qs(parsed_url.query, keep_blank_values=True)
                    soup = BeautifulSoup(html, "html.parser")
                except Exception:
                    pass

        # 1. Extreme Networks
        try:
            hs_server = qs.get("hs_server", [None])[0]
            qv = qs.get("Qv", [None])[0]
            if (not hs_server or not qv) and soup:
                form = soup.find("form", {"name": "extreme"})
                if form:
                    hs_in = form.find("input", {"name": "f_hs_server"})
                    qv_in = form.find("input", {"name": "f_Qv"})
                    hs_server = hs_in.get("value") if hs_in else hs_server
                    qv = qv_in.get("value") if qv_in else qv

            if hs_server and qv:
                post_data = {
                    "f_user": "awing120", "f_pass": "Awing120@2018",
                    "f_hs_server": hs_server, "f_curr_time": str(int(_time.time())), "f_Qv": qv,
                }
                action = f"http://{hs_server}:880/cgi-bin/hslogin.cgi"
                headers = {
                    "Origin": f"{parsed_url.scheme}://{parsed_url.netloc}" if parsed_url.netloc else "http://v1.awingconnect.vn",
                    "Referer": portal_url,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                }
                session.post(action, data=post_data, headers=headers, timeout=3.5)
                return {"success": True, "message": f"Gửi xác thực Extreme Networks HTTP: {hs_server}"}
        except Exception:
            pass

        # 2. Cisco Meraki (Sign-on & Click-Through Grant)
        try:
            direct_login = qs.get("login_url", [None])[0]
            base_grant = qs.get("base_grant_url", [None])[0]
            if html:
                if not direct_login:
                    m = re.search(r"""["']login_url["']\s*:\s*["']([^"']+)["']""", html) or re.search(r"""login_url=([^&"']+)""", html)
                    if m: direct_login = urllib.parse.unquote(m.group(1))
                if not base_grant:
                    m = re.search(r"""["']base_grant_url["']\s*:\s*["']([^"']+)["']""", html) or re.search(r"""base_grant_url=([^&"']+)""", html)
                    if m: base_grant = urllib.parse.unquote(m.group(1))

            headers = {"Referer": portal_url, "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

            # 2a. Meraki Sign-on URL
            if direct_login and ("network-auth.com" in direct_login or "splash" in direct_login):
                session.post(direct_login, data={"success_url": "https://v2.awingconnect.vn/Success", "username": "awing60", "password": "Awing60@2018"}, headers=headers, timeout=3.5)
                return {"success": True, "message": "Gửi xác thực Cisco Meraki HTTP: awing60"}

            # 2b. Meraki Click-Through Grant URL
            if base_grant and ("network-auth.com" in base_grant or "splash" in base_grant):
                grant_params = {"continue_url": qs.get("user_continue_url", ["http://v1.awingconnect.vn/Success"])[0], "duration": "7200"}
                session.get(base_grant, params=grant_params, headers=headers, timeout=3.5)
                return {"success": True, "message": "Gửi xác thực Cisco Meraki Grant HTTP"}

            # 2c. Form-based extraction
            if soup:
                m_form = soup.find("form", {"name": "ciscoMeraki"}) or soup.find("form", id="frmLogin")
                if m_form:
                    m_action = m_form.get("action") or base_grant or direct_login or ""
                    m_name = (m_form.get("name") or "").lower()
                    if m_name == "ciscomeraki" or "network-auth.com" in m_action or "splash" in m_action:
                        data = {inp.get("name"): inp.get("value", "") for inp in m_form.find_all("input") if inp.get("name")}
                        m_method = (m_form.get("method") or "POST").upper()

                        if data.get("username") and m_action.startswith("http"):
                            session.post(m_action, data=data, headers=headers, timeout=3.5)
                            return {"success": True, "message": f"Gửi xác thực Cisco Meraki HTTP: {data.get('username')}"}
                        elif "grant" in m_action or "network-auth.com" in m_action or m_action.startswith("http"):
                            data.setdefault("continue_url", "http://v1.awingconnect.vn/Success")
                            data.setdefault("duration", "7200")
                            if m_method == "GET":
                                session.get(m_action, params=data, headers=headers, timeout=3.5)
                            else:
                                session.post(m_action, data=data, headers=headers, timeout=3.5)
                            return {"success": True, "message": "Gửi xác thực Cisco Meraki Grant HTTP"}
        except Exception:
            pass

        # 3. MikroTik
        try:
            if soup:
                form = soup.find("form", {"name": "mikrotik"}) or (soup.find("form", id="frmLogin") if "186.186." in portal_url else None)
                if form:
                    action = form.get("action") or "http://186.186.0.1/login"
                    form_name = (form.get("name") or "").lower()
                    if form_name == "mikrotik" or "186.186." in action or "186.186." in portal_url:
                        if not action.startswith("http"):
                            action = urllib.parse.urljoin(portal_url, action)
                        data = {inp.get("name"): inp.get("value", "") for inp in form.find_all("input") if inp.get("name")}
                        if data.get("username"):
                            method = (form.get("method") or "post").lower()
                            if method == "get":
                                session.get(action, params=data, timeout=3.5)
                            else:
                                session.post(action, data=data, timeout=3.5)
                            return {"success": True, "message": f"Gửi xác thực MikroTik HTTP: {data.get('username')}"}
        except Exception:
            pass

        return None

    def get_browser_script(self) -> str:
        """
        Universal browser automation script for AWING portals.
        Prioritizes traditional button clicking and top-level grant submissions.
        """
        return """
        (function() {
            let result = { status: "searching", buttonClicked: null };

            try {
                function isVisible(el) {
                    if (!el) return false;
                    try {
                        if (typeof el.checkVisibility === 'function') {
                            return el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true });
                        }
                        let s = window.getComputedStyle(el);
                        if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
                        return el.offsetParent !== null || (el.getClientRects && el.getClientRects().length > 0);
                    } catch(e) { return true; }
                }

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

                // 1. Dismiss Customer Survey / Profile Popup (Demographic modals)
                let remindBtn = document.getElementById("remind-me")
                    || document.querySelector(".popup-form__remind-me-btn")
                    || Array.from(document.querySelectorAll("#awing-captive__customer-popup button, #awing-captive__customerscreen button, button, a")).find(b => {
                        let t = (b.innerText || b.textContent || "").trim().toLowerCase();
                        return (t.includes("nhắc tôi sau") || t.includes("remind me") || t.includes("nhắc lại sau") || t.includes("để sau")) && isVisible(b);
                    });

                if (remindBtn && isVisible(remindBtn)) {
                    try {
                        simulateClick(remindBtn);
                        if (typeof helper !== "undefined" && typeof helper.remindLater === "function") {
                            try { helper.remindLater(); } catch(e) {}
                        }
                        if (window.awingStateMachineContextActions && typeof window.awingStateMachineContextActions.customerFilterFormRemindLater === "function") {
                            try { window.awingStateMachineContextActions.customerFilterFormRemindLater(); } catch(e) {}
                        }
                        result.status = "advanced_state";
                        result.buttonClicked = "Bỏ qua khảo sát";
                        return result;
                    } catch(e) {}
                }

                let customerPopup = document.getElementById("awing-captive__customer-popup") || document.getElementById("awing-captive__customerscreen");
                if (customerPopup && isVisible(customerPopup)) {
                    let handled = false;
                    if (typeof helper !== "undefined" && typeof helper.remindLater === "function") {
                        try { helper.remindLater(); handled = true; } catch(e) {}
                    }
                    if (window.awingStateMachineContextActions && typeof window.awingStateMachineContextActions.customerFilterFormRemindLater === "function") {
                        try { window.awingStateMachineContextActions.customerFilterFormRemindLater(); handled = true; } catch(e) {}
                    }
                    if (handled) {
                        result.status = "advanced_state";
                        result.buttonClicked = "Bỏ qua khảo sát";
                        return result;
                    }
                }

                // 2. Dismiss Promotional Voucher / CPA overlay
                let cpaSecondary = Array.from(document.querySelectorAll("button.option-secondary, .option-button, button, a")).find(b => {
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

                // 3. Unified Connect Button Clicking
                let connectKeywords = [
                    "kết nối internet", "tiếp tục để kết nối", "internet access",
                    "kết nối ngay", "truy cập ngay", "chỉ kết nối", "kết nối", "connect"
                ];
                let acceptBtn = document.getElementById("acceptconnection_BannerOverflow")
                    || document.getElementById("logo_button")
                    || document.querySelector("button.connect-button, .btn-connect, [class*='connect']")
                    || Array.from(document.querySelectorAll("button, a, div[role='button'], input[type='button'], input[type='submit']")).find(b => {
                        let t = (b.innerText || b.textContent || b.value || "").trim().toLowerCase();
                        return connectKeywords.some(kw => t.includes(kw)) && isVisible(b);
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

                // 4. Clickable banner image (#banner)
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

                // 5. Drive AWING State Machine directly if needed (completeAd / nextView)
                let stateAdvanced = false;
                if (window.awingStateMachineContextActions) {
                    let actions = window.awingStateMachineContextActions;
                    if (typeof actions.nextView === "function") {
                        try { actions.nextView(); stateAdvanced = true; } catch(e) {}
                    }
                    if (typeof actions.completeAd === "function") {
                        try { actions.completeAd(); stateAdvanced = true; } catch(e) {}
                    }
                }

                // 6. Handle Welcome / Authenticating Screen (#awing-captive__welcome-loading)
                let welcome = document.getElementById("awing-captive__welcome-loading");
                let isWelcomeVisible = welcome && isVisible(welcome);

                if (isWelcomeVisible || stateAdvanced) {
                    let frmLogin = document.getElementById("frmLogin");
                    let frmName = frmLogin ? (frmLogin.getAttribute("name") || "").toLowerCase() : "";

                    // MikroTik bypass behind welcome screen (186.186.0.1)
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

                    // Resolve frmLogin.action if needed
                    if (frmLogin && (!frmLogin.action || !frmLogin.action.startsWith("http"))) {
                        try {
                            let u = new URL(window.location.href);
                            let bg = u.searchParams.get("base_grant_url") || u.searchParams.get("login_url");
                            if (bg) frmLogin.action = bg;
                        } catch(e) {}
                    }

                    let authenType = (window.awingStateMachineContext && typeof window.awingStateMachineContext.getAuthenType === "function")
                        ? window.awingStateMachineContext.getAuthenType() : 0;
                    let counterEl = document.getElementById("awing-captive__welcome-counter");
                    let counterVal = counterEl ? parseInt(counterEl.innerText || counterEl.textContent || "0") : 0;
                    let frmAction = frmLogin ? (frmLogin.action || "").toLowerCase() : "";

                    // Case A: Click-Through Grant OR AUTHEN_TYPE.FORM (authenType === 1)
                    // Must submit TOP-LEVEL! Never use iframe because Cisco Meraki blocks iframes via X-Frame-Options (ERR_BLOCKED_BY_RESPONSE)!
                    let isFormGrant = authenType === 1 || frmAction.includes("/splash/grant");
                    if (isFormGrant && frmLogin && frmLogin.action && frmLogin.action.startsWith("http")) {
                        if (!frmLogin.dataset || frmLogin.dataset.autowififormsubmitted !== "true") {
                            if (frmLogin.dataset) frmLogin.dataset.autowififormsubmitted = "true";
                            frmLogin.removeAttribute("target");
                            try {
                                if (window.awingUIActions && typeof window.awingUIActions.SubmitAuthenticationForm === "function") {
                                    window.awingUIActions.SubmitAuthenticationForm();
                                } else {
                                    frmLogin.submit();
                                }
                            } catch(e) {
                                frmLogin.submit();
                            }
                            result.status = "clicked";
                            result.buttonClicked = "Xác thực Cisco Meraki Grant";
                            return result;
                        }
                    }

                    // Case B: Iframe Authentication (AUTHEN_TYPE.IFRAME === 2 or Extreme Networks)
                    let isIframeAuthen = (authenType === 2 || frmName === "extreme" || (frmLogin && frmLogin.getAttribute("target") === "loginFrame"))
                        && !isFormGrant;

                    if (isIframeAuthen && !document.querySelector("#redirecting-iframe") && window.awingUIActions && typeof window.awingUIActions.SubmitAuthenticationFormWithIframe === "function") {
                        try {
                            window.awingUIActions.SubmitAuthenticationFormWithIframe();
                            result.status = "clicked";
                            result.buttonClicked = frmName === "ciscomeraki" ? "Xác thực Cisco Meraki" : "Xác thực Extreme Networks";
                            return result;
                        } catch(e) {}
                    }

                    // Case C: Rescue stuck at 90-99% on ANY portal
                    // If counter reached >= 90% and page has not redirected, top-level submit rescues the session immediately!
                    if (counterVal >= 90 && frmLogin && frmLogin.action && frmLogin.action.startsWith("http")) {
                        if (!frmLogin.dataset || frmLogin.dataset.autowifirescued !== "true") {
                            if (frmLogin.dataset) frmLogin.dataset.autowifirescued = "true";
                            frmLogin.removeAttribute("target");
                            frmLogin.submit();
                            result.status = "clicked";
                            result.buttonClicked = "Giải cứu 99% (Top-level submit)";
                            return result;
                        }
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

            } catch (err) {
                result.status = "error: " + err.message;
            }

            return result;
        })();
        """
