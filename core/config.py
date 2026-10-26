import os
import json
import sys

APP_VERSION = "1.0.1"
AUTHOR_URL = "https://caocap.dev"
GITHUB_REPO_URL = "https://github.com/caocapdev/HCMUS-AutoWifi"

DEFAULT_CONFIG = {
    "version": APP_VERSION,
    "start_with_windows": True,
    "startup_mode": "task",
    "auto_login_enabled": True,
    "check_interval": 1,
    "headless": True,
    "notifications": False,
    "close_to_tray": True,
    "portal_redirect_url": "http://www.msftconnecttest.com/redirect",
    "connecttest_url": "http://www.msftconnecttest.com/connecttest.txt",
    "total_logins": 0,
    "last_login_time": "",
    "last_ssid": ""
}

def get_app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def get_resource_path(relative_path: str) -> str:
    """Resolves path for resources in both source and PyInstaller bundle."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(get_app_dir(), relative_path)

def get_config_path():
    return os.path.join(get_app_dir(), "config.json")

class ConfigManager:
    def __init__(self):
        self.config_path = get_config_path()
        self.data = DEFAULT_CONFIG.copy()
        self.load()

    def load(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    self.data.update(saved)
            except Exception as e:
                print(f"[Config] Error loading config: {e}")
        else:
            self.save()
        self.data["version"] = APP_VERSION

    def save(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[Config] Error saving config: {e}")

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def increment_logins(self, ssid: str):
        import datetime
        self.data["total_logins"] = self.data.get("total_logins", 0) + 1
        self.data["last_login_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.data["last_ssid"] = ssid
        self.save()

config = ConfigManager()
