from typing import List
from core.portals.base import BasePortal
from core.portals.hcmus import HCMUSPortal
from core.portals.awing import AwingPortal
from core.portals.generic import GenericPortal

# Registered portal strategies evaluated in order
PORTAL_STRATEGIES: List[BasePortal] = [
    HCMUSPortal(),
    AwingPortal(),
    GenericPortal()  # Fallback must be last
]

def find_portal_strategy(url: str, html: str = "") -> BasePortal:
    """
    Selects the first matching strategy for the given portal URL and HTML content.
    Returns GenericPortal if no specialized strategy matches.
    """
    for strategy in PORTAL_STRATEGIES:
        if strategy.match(url, html):
            return strategy
    return PORTAL_STRATEGIES[-1]
