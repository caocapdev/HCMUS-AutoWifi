import urllib.parse
from typing import Optional, Dict, Any
import requests
from core.portals.base import BasePortal

class HCMUSPortal(BasePortal):
    """
    Strategy for VNU-HCM University of Science (HCMUS) Wi-Fi Captive Portal.
    Used for HCMUS-PUBLIC, HCMUS-STUDENT, HCMUS-PHONGHOC across all campuses.
    Backend: OPNsense Captive Portal.
    """

    name = "ĐH Khoa học Tự nhiên (HCMUS)"

    def match(self, url: str, html: str) -> bool:
        lower_url = url.lower()
        lower_html = html.lower()

        indicators = [
            "10.232.0.1",
            "hcmus.edu.vn",
            "termscheckboxcustomanon",
            "signin_anon",
            "khoa học tự nhiên",
            "đhqg-hcm"
        ]
        return any(ind in lower_url or ind in lower_html for ind in indicators)

    def solve_http(self, session: requests.Session, portal_url: str, html: str) -> Optional[Dict[str, Any]]:
        """
        Fast path: OPNsense Captive Portal exposes a JSON API endpoint.
        Calling POST /api/captiveportal/access/logon/ with empty user/password
        authorizes the anonymous guest session immediately.
        """
        try:
            logon_url = urllib.parse.urljoin(portal_url, "/api/captiveportal/access/logon/")
            resp = session.post(logon_url, data={"user": "", "password": ""}, timeout=4)
            data = resp.json()

            if data.get("clientState") == "AUTHORIZED":
                return {
                    "success": True,
                    "message": "Đã xác thực thành công qua HCMUS OPNsense API"
                }
        except Exception:
            pass
        return None

    def get_browser_script(self) -> str:
        """
        DOM automation script for HCMUS Wi-Fi portal.
        Handles the custom terms checkbox and submits the anonymous login button.
        """
        return """
        (function() {
            let result = { status: "searching", buttonClicked: null };

            try {
                // 1. Accept terms in global JavaScript state
                if (typeof toggleTermsAnon === 'function' && typeof termsAnonAccepted !== 'undefined') {
                    if (!termsAnonAccepted) {
                        toggleTermsAnon();
                    }
                }
                if (typeof termsAnonAccepted !== 'undefined') {
                    termsAnonAccepted = true;
                }

                // 2. Visually update custom checkbox and terms content
                let customCheckbox = document.getElementById('termsCheckboxCustomAnon');
                if (customCheckbox) {
                    customCheckbox.classList.add('checked');
                }
                let termsBox = document.getElementById('termsContentAnon');
                if (termsBox) {
                    termsBox.classList.add('show');
                }

                // 3. Enable and click anonymous connection button
                let anonButton = document.getElementById('signin_anon');
                if (anonButton) {
                    anonButton.disabled = false;
                    if (window.jQuery) {
                        window.jQuery("#signin_anon").prop("disabled", false);
                        window.jQuery("#signin_anon").click();
                    } else {
                        anonButton.click();
                    }
                    result.status = "clicked";
                    result.buttonClicked = "Đồng ý và kết nối Internet (#signin_anon)";
                    return result;
                }

                // 4. Fallback: Password login form (if anonymous is disabled)
                let pwButton = document.getElementById('signin');
                if (pwButton && !document.getElementById('login_password')?.classList.contains('hidden')) {
                    if (typeof toggleTerms === 'function' && typeof termsAccepted !== 'undefined' && !termsAccepted) {
                        toggleTerms();
                    }
                    if (typeof termsAccepted !== 'undefined') {
                        termsAccepted = true;
                    }
                    pwButton.disabled = false;
                    pwButton.click();
                    result.status = "clicked";
                    result.buttonClicked = "Đồng ý và đăng nhập (#signin)";
                    return result;
                }
            } catch (err) {
                result.status = "error: " + err.message;
            }

            return result;
        })();
        """
