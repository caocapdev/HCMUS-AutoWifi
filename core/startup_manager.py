import os
import sys
import winreg
import subprocess
import ctypes
from ctypes import wintypes
from core.config import get_app_dir, config

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "HCMUSAutoWifi"
TASK_NAME = "HCMUSAutoWifi"

MODE_NONE = "none"
MODE_REGISTRY = "registry"
MODE_TASK = "task"

STARTUP_MODES = [MODE_TASK, MODE_REGISTRY, MODE_NONE]

MODE_LABELS = {
    MODE_TASK: "Task Scheduler (Khởi động nhanh)",
    MODE_REGISTRY: "Mặc định (Registry Run)",
    MODE_NONE: "Không khởi động cùng Windows",
}

class _SHELLEXECUTEINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", wintypes.ULONG),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", wintypes.LPVOID),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIconOrMonitor", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE)
    ]

def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

def get_task_command_parts() -> tuple[str, str]:
    """Returns (executable_path, arguments) for startup execution."""
    if getattr(sys, "frozen", False):
        return sys.executable, "--tray"
    compiled_exe = os.path.join(get_app_dir(), "HCMUS_AutoWifi.exe")
    if os.path.exists(compiled_exe):
        return compiled_exe, "--tray"
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    py = pythonw if os.path.exists(pythonw) else sys.executable
    return py, f'"{os.path.join(get_app_dir(), "main.py")}" --tray'

def get_launch_command() -> str:
    """Returns the full command string for Registry Run."""
    exe, args = get_task_command_parts()
    return f'"{exe}" {args}'

# --- Registry Mode ---

def is_registry_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, APP_NAME)
            return bool(val)
    except Exception:
        return False

def enable_registry() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, get_launch_command())
        return True
    except Exception:
        return False

def disable_registry() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, APP_NAME)
    except Exception:
        pass
    return True

# --- Task Scheduler Mode ---

def is_task_enabled() -> bool:
    try:
        p = subprocess.run(
            ["schtasks.exe", "/Query", "/TN", TASK_NAME],
            capture_output=True,
            text=True,
            creationflags=_NO_WINDOW
        )
        return p.returncode == 0
    except Exception:
        return False

def enable_scheduled_task() -> tuple[bool, str]:
    cmd_path, cmd_args = get_task_command_parts()
    # Attempt 1: schtasks.exe
    cmd = [
        "schtasks.exe", "/Create",
        "/TN", TASK_NAME,
        "/TR", f'"{cmd_path}" {cmd_args}',
        "/SC", "ONLOGON",
        "/RL", "HIGHEST",
        "/F"
    ]
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            creationflags=_NO_WINDOW
        )
        if p.returncode == 0:
            return True, "Đã tạo tác vụ Task Scheduler thành công."
    except Exception:
        pass

    # Attempt 2: PowerShell Register-ScheduledTask fallback
    try:
        ps = f"$a=New-ScheduledTaskAction -Execute '{cmd_path}' -Argument '{cmd_args}'; $t=New-ScheduledTaskTrigger -AtLogOn; $p=New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest; $s=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries; Register-ScheduledTask -TaskName '{TASK_NAME}' -Action $a -Trigger $t -Principal $p -Settings $s -Force"
        p = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            creationflags=_NO_WINDOW
        )
        if p.returncode == 0 and is_task_enabled():
            return True, "Đã tạo tác vụ Task Scheduler thành công."
    except Exception as e:
        return False, str(e)

    return False, "Không thể tạo tác vụ Task Scheduler."

def disable_scheduled_task() -> tuple[bool, str]:
    try:
        subprocess.run(
            ["schtasks.exe", "/Delete", "/TN", TASK_NAME, "/F"],
            capture_output=True,
            text=True,
            creationflags=_NO_WINDOW
        )
        return True, "Đã xóa Task Scheduler."
    except Exception as e:
        return False, str(e)

# --- UAC Elevation Helper ---

def run_elevated(action_args: list[str]) -> tuple[bool, str]:
    """Runs elevated process via ShellExecuteExW with verb 'runas' and waits for exit."""
    if getattr(sys, "frozen", False):
        exe, params = sys.executable, " ".join(action_args)
    else:
        compiled_exe = os.path.join(get_app_dir(), "HCMUS_AutoWifi.exe")
        if os.path.exists(compiled_exe):
            exe, params = compiled_exe, " ".join(action_args)
        else:
            exe = sys.executable
            main_py = os.path.abspath(os.path.join(get_app_dir(), "main.py"))
            params = f'"{main_py}" ' + " ".join(action_args)

    sei = _SHELLEXECUTEINFO()
    sei.cbSize = ctypes.sizeof(_SHELLEXECUTEINFO)
    sei.fMask = 0x00000040  # SEE_MASK_NOCLOSEPROCESS
    sei.lpVerb = "runas"
    sei.lpFile = exe
    sei.lpParameters = params
    sei.lpDirectory = get_app_dir()
    sei.nShow = 1  # SW_SHOWNORMAL ensures UAC prompt is displayed to user

    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei)):
        err = ctypes.GetLastError()
        if err == 1223:  # ERROR_CANCELLED (User clicked 'No' on UAC)
            return False, "Yêu cầu quyền Admin (UAC) đã bị hủy."
        return False, f"Không thể yêu cầu quyền Admin (Mã: {err})."

    hProcess = sei.hProcess
    if hProcess:
        ctypes.windll.kernel32.WaitForSingleObject(hProcess, 15000)
        exit_code = wintypes.DWORD()
        ctypes.windll.kernel32.GetExitCodeProcess(hProcess, ctypes.byref(exit_code))
        ctypes.windll.kernel32.CloseHandle(hProcess)
        if exit_code.value != 0:
            return False, f"Tiến trình nâng quyền thất bại (Mã: {exit_code.value})."

    return True, "Thao tác admin đã hoàn tất."

# --- Core Startup Mode APIs ---

def get_current_startup_mode() -> str:
    if is_task_enabled():
        return MODE_TASK
    if is_registry_enabled():
        return MODE_REGISTRY
    return MODE_NONE

def apply_startup_mode_internal(target_mode: str) -> tuple[bool, str]:
    if target_mode not in STARTUP_MODES:
        return False, f"Chế độ không hợp lệ: {target_mode}"
    try:
        if target_mode != MODE_REGISTRY:
            disable_registry()
        if target_mode != MODE_TASK and is_task_enabled():
            disable_scheduled_task()

        if target_mode == MODE_NONE:
            config.set("startup_mode", MODE_NONE)
            config.set("start_with_windows", False)
            return True, "Đã tắt khởi động cùng Windows."

        if target_mode == MODE_REGISTRY:
            if enable_registry():
                config.set("startup_mode", MODE_REGISTRY)
                config.set("start_with_windows", True)
                return True, "Đã bật khởi động Registry Run."
            return False, "Không thể ghi Registry Run."

        if target_mode == MODE_TASK:
            ok, msg = enable_scheduled_task()
            if ok:
                config.set("startup_mode", MODE_TASK)
                config.set("start_with_windows", True)
            return ok, msg

        return False, "Chế độ không xác định."
    except Exception as e:
        return False, str(e)

def set_startup_mode(target_mode: str) -> tuple[bool, str]:
    curr = get_current_startup_mode()
    if target_mode == curr and (target_mode == MODE_NONE or (is_task_enabled() if target_mode == MODE_TASK else is_registry_enabled())):
        return True, f"Chế độ {MODE_LABELS.get(target_mode)} đã được chọn."

    needs_admin = (target_mode == MODE_TASK or curr == MODE_TASK)
    if needs_admin and not is_admin():
        ok, msg = run_elevated(["--set-startup-elevated", target_mode])
        if ok:
            if target_mode == MODE_TASK and not is_task_enabled():
                return False, "Task Scheduler chưa được tạo thành công."
            config.set("startup_mode", target_mode)
            config.set("start_with_windows", target_mode != MODE_NONE)
            return True, f"Đã thiết lập: {MODE_LABELS.get(target_mode)}"
        return False, msg

    return apply_startup_mode_internal(target_mode)
