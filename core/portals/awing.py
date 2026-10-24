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
      - Noi Bai & Tan Son Nhat Airport ("Free Wifi NoiBai Airport")
      - Highlands Coffee, Phuc Long, Trung Nguyen, The Coffee House
      - Vincom, Big C / GO!, and shopping centers across Vietnam
    """

    name = "AWING Connect (Sân bay / Quán Cafe)"

    def match(self, url: str, html: str) -> bool:
        lower_url = url.lower()
        lower_html = html.lower()

        # 1. Direct domain, gateway IP, or portal network matches (Dynamic, no hardcoded SSIDs)
        if any(d in lower_url for d in ["awingconnect.vn", "awing.vn", "awing", "186.186."]):
            return True

        # 2. Key phrases in HTML from AWING template
        indicators = [
            "awingconnect.vn",
            "awing.vn",
            "powered by awing",
            "ads by awing",
            "free wi-fi | awing",
            "tiếp tục để kết nối internet",
            "tiếp tục để kết nối",
            "186.186.",
            "awing-captive",
            "awingstatemachine",
            "awingcaptive",
            "frmlogin",
            'name="mikrotik"',
            "awingconstants",
            "awingcaptiveutils"
        ]
        if any(ind in lower_html for ind in indicators):
            return True

        # 3. Check for hidden input with username 'awing...'
        if 'name="username"' in lower_html and 'value="awing' in lower_html:
            return True

        return False

    def solve_http(self, session: requests.Session, portal_url: str, html: str) -> Optional[Dict[str, Any]]:
        """
        Direct HTTP Fast Path:
        AWING embeds a hidden MikroTik login form with pre-generated credentials
        (username='awing...', password, dst, popup) in the Connecting page.
        Submitting this form directly to the router's action (http://186.186.0.1/login)
        instantly authorizes the client without waiting for ads or launching a browser.
        """
        try:
            # If initial HTML was not fetched or empty, fetch the portal landing page
            if not html or ("frmlogin" not in html.lower() and "mikrotik" not in html.lower()):
                try:
                    resp = session.get(portal_url, timeout=3.5, allow_redirects=True)
                    portal_url = resp.url
                    html = resp.text
                except Exception:
                    pass

            soup = BeautifulSoup(html, "html.parser")
            form = soup.find("form", {"id": "frmLogin"}) or soup.find("form", {"name": "mikrotik"})

            # If not in the initial page, check for redirect to awing connecting page
            if not form:
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
                    resp = session.get(redirect_url, timeout=4, allow_redirects=True)
                    portal_url = resp.url
                    html = resp.text
                    soup = BeautifulSoup(html, "html.parser")
                    form = soup.find("form", {"id": "frmLogin"}) or soup.find("form", {"name": "mikrotik"})

            # Fallback search: any form containing an input with 'awing' in value
            if not form:
                for f in soup.find_all("form"):
                    u_in = f.find("input", {"name": "username"})
                    if u_in and "awing" in u_in.get("value", "").lower():
                        form = f
                        break

            if not form:
                return None

            action = form.get("action") or "http://186.186.0.1/login"
            if not action.startswith("http"):
                action = urllib.parse.urljoin(portal_url, action)

            data = {}
            for input_tag in form.find_all("input"):
                name = input_tag.get("name")
                if not name:
                    continue
                data[name] = input_tag.get("value", "")

            # Submit credentials directly to the gateway router
            method = (form.get("method") or "post").lower()
            if method == "get":
                session.get(action, params=data, timeout=5)
            else:
                session.post(action, data=data, timeout=5)

            return {
                "success": True,
                "message": f"Đã gửi thông tin xác thực AWING (MikroTik: {data.get('username', 'auto')}) trực tiếp qua HTTP"
            }
        except Exception as e:
            return None

    def get_browser_script(self) -> str:
        """
        Browser automation script for AWING portals:
        1. Submits #frmLogin directly if already present in DOM.
        2. Triggers AWING state machine transition if available.
        3. Clicks primary connect / continue buttons.
        """
        return """
        (function() {
            let result = { status: "searching", buttonClicked: null };

            try {
                // 1. Check if frmLogin already present in DOM
                let frm = document.getElementById("frmLogin") || document.querySelector("form[name='mikrotik']");
                if (frm) {
                    try {
                        if (!frm.action || frm.action === window.location.href) {
                            frm.action = "http://186.186.0.1/login";
                        }
                        frm.submit();
                        result.status = "clicked";
                        result.buttonClicked = "frmLogin (Bypass trực tiếp MikroTik)";
                        return result;
                    } catch(e) {}
                }

                // 2. Advance AWING State Machine / Button
                let stateAdvanced = false;
                if (window.awingStateMachineContextActions) {
                    if (typeof window.awingStateMachineContextActions.completeAd === "function") {
                        try {
                            window.awingStateMachineContextActions.completeAd();
                            stateAdvanced = true;
                        } catch(e) {}
                    }
                    if (typeof window.awingStateMachineContextActions.nextView === "function") {
                        try {
                            window.awingStateMachineContextActions.nextView();
                            stateAdvanced = true;
                        } catch(e) {}
                    }
                }

                let logoBtn = document.getElementById("logo_button");
                if (logoBtn && !logoBtn.disabled) {
                    try {
                        logoBtn.click();
                        stateAdvanced = true;
                    } catch(e) {}
                }

                // 3. Immediately re-check for frmLogin right after advancing state
                frm = document.getElementById("frmLogin") || document.querySelector("form[name='mikrotik']");
                if (frm) {
                    try {
                        if (!frm.action || frm.action === window.location.href) {
                            frm.action = "http://186.186.0.1/login";
                        }
                        frm.submit();
                        result.status = "clicked";
                        result.buttonClicked = "frmLogin (Bypass trực tiếp MikroTik)";
                        return result;
                    } catch(e) {}
                }

                if (stateAdvanced) {
                    result.status = "clicked";
                    result.buttonClicked = "completeAd (State Machine)";
                    return result;
                }

                // 4. Search for connect/continue buttons
                let buttons = Array.from(document.querySelectorAll("button, a, div[role='button'], input[type='button'], input[type='submit']"));
                let keywords = [
                    "tiếp tục để kết nối", "tiếp tục", "kết nối internet",
                    "internet access", "kết nối ngay", "truy cập ngay"
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
                    let isDisabled = target.disabled || 
                                     target.getAttribute("aria-disabled") === "true" ||
                                     target.classList.contains("disabled");

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

                    result.status = "clicked";
                    result.buttonClicked = (target.innerText || "KẾT NỐI INTERNET").trim();
                    return result;
                }
            } catch (err) {
                result.status = "error: " + err.message;
            }

            return result;
        })();
        """
