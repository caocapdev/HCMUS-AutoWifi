from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import requests

class BasePortal(ABC):
    """
    Abstract base class for all captive portal strategies.
    Each strategy provides:
      1. Pattern matching against the current portal URL and page HTML.
      2. Fast direct HTTP/API login (if supported by the portal backend).
      3. Browser automation script (evaluated via CDP in Edge).
    """

    name: str = "Base Portal"

    @abstractmethod
    def match(self, url: str, html: str) -> bool:
        """Return True if this strategy handles the given portal."""
        pass

    def solve_http(self, session: requests.Session, portal_url: str, html: str) -> Optional[Dict[str, Any]]:
        """
        Fast path: solve via direct HTTP/API without starting a browser.
        Return dict with {'success': True/False, 'message': str} or None if not supported.
        """
        return None

    @abstractmethod
    def get_browser_script(self) -> str:
        """
        Return a self-executing JavaScript snippet for Chrome DevTools Protocol.
        The script should return a JS object: { status: 'clicked'|'no_button'|'waiting', buttonClicked: str }
        """
        pass
