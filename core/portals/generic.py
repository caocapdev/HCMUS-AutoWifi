import urllib.parse
from typing import Optional, Dict, Any
import requests
from bs4 import BeautifulSoup
from core.portals.base import BasePortal

class GenericPortal(BasePortal):
    """
    Universal fallback strategy for standard Captive Portals
    (MikroTik RouterOS, Aruba Networks, Cisco Meraki, pfSense, hotels, cafes).
    """

    name = "Cổng tiêu chuẩn"

    def match(self, url: str, html: str) -> bool:
        # Match any portal as the default fallback
        return True

    def solve_http(self, session: requests.Session, portal_url: str, html: str) -> Optional[Dict[str, Any]]:
        """
        Attempts standard HTML form submission if present.
        """
        try:
            soup = BeautifulSoup(html, "html.parser")
            form = soup.find("form")
            if not form:
                return None

            action = form.get("action") or portal_url
            if not action.startswith("http"):
                action = urllib.parse.urljoin(portal_url, action)

            data = {}
            for input_tag in form.find_all("input"):
                name = input_tag.get("name")
                if not name:
                    continue
                itype = input_tag.get("type", "").lower()
                val = input_tag.get("value", "")
                if itype == "checkbox":
                    data[name] = val or "on"
                elif itype not in ("submit", "button", "reset"):
                    data[name] = val

            submit_btn = form.find("button") or form.find("input", {"type": "submit"})
            if submit_btn and submit_btn.get("name"):
                data[submit_btn["name"]] = submit_btn.get("value", "submit")

            method = form.get("method", "post").lower()
            if method == "get":
                session.get(action, params=data, timeout=4)
            else:
                session.post(action, data=data, timeout=4)

            return {
                "success": True,
                "message": "Gửi form đăng nhập HTTP"
            }
        except Exception:
            return None

    def get_browser_script(self) -> str:
        """
        Universal DOM script:
        1. Checks any terms/agreement checkboxes.
        2. Finds and clicks connect/login/submit buttons.
        """
        return """
        (function() {
            let result = { status: "searching", buttonClicked: null };

            try {
                // 0. Direct form submission if MikroTik / Captive portal form is present
                let frm = document.getElementById("frmLogin") || document.querySelector("form[name='mikrotik']");
                if (frm) {
                    try {
                        frm.submit();
                        result.status = "clicked";
                        result.buttonClicked = "Form MikroTik";
                        return result;
                    } catch(e) {}
                }

                // 1. Tick all unchecked checkboxes
                let checkboxes = Array.from(document.querySelectorAll("input[type='checkbox']"));
                for (let cb of checkboxes) {
                    if (!cb.checked) {
                        cb.click();
                        if (!cb.checked) {
                            cb.checked = true;
                            cb.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    }
                }

                // 2. Identify submit or connect buttons
                let candidates = Array.from(document.querySelectorAll(
                    "button, input[type='submit'], input[type='button'], a[role='button'], a, .btn, .button"
                ));

                let keywords = [
                    "đồng ý và kết nối", "kết nối internet", "kết nối ngay", "đồng ý",
                    "kết nối", "connect", "login", "đăng nhập", "truy cập", "tiếp tục",
                    "continue", "agree", "accept", "submit"
                ];

                let target = null;
                for (let el of candidates) {
                    let text = (el.innerText || el.value || el.textContent || "").trim().toLowerCase();
                    if (keywords.some(kw => text.includes(kw))) {
                        target = el;
                        break;
                    }
                }

                // Fallback: Primary form submit button
                if (!target) {
                    target = document.querySelector("form button[type='submit'], form input[type='submit'], .btn-primary");
                }

                if (target) {
                    target.disabled = false;
                    target.removeAttribute('disabled');
                    target.removeAttribute('aria-disabled');
                    target.classList.remove('disabled');

                    target.scrollIntoView({ behavior: 'instant', block: 'center' });
                    target.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                    target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                    target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                    target.click();

                    // If inside a form, submit as well
                    let form = target.closest('form');
                    if (form) {
                        try { form.submit(); } catch(e) {}
                    }

                    result.status = "clicked";
                    result.buttonClicked = (target.innerText || target.value || target.tagName).trim();
                    return result;
                }
            } catch (err) {
                result.status = "error: " + err.message;
            }

            return result;
        })();
        """
