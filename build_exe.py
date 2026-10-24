import subprocess
import sys
import os
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.config import APP_VERSION

if sys.stdout:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def build():
    print(f"[Build] Đang đóng gói HCMUS AutoWifi v{APP_VERSION} thành file .exe độc lập...")
    root_dir = os.path.abspath(os.path.dirname(__file__))
    target_exe = os.path.join(root_dir, "HCMUS_AutoWifi.exe")
    old_exe = os.path.join(root_dir, "HCMUS_AutoWifi.exe.old")

    # Xóa file .old cũ nếu có
    if os.path.exists(old_exe):
        try:
            os.remove(old_exe)
        except OSError:
            pass

    # Tắt tiến trình cũ nếu có thể
    subprocess.run(["taskkill", "/F", "/IM", "HCMUS_AutoWifi.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Nếu file exe đang bị khóa bởi Windows Service, đổi tên sang .old để giải phóng tên file
    if os.path.exists(target_exe):
        try:
            os.rename(target_exe, old_exe)
        except OSError:
            pass
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name=HCMUS_AutoWifi",
        "--icon=assets/icon.ico",
        "--add-data=assets;assets",
        "--clean",
        "--distpath=.",
        "main.py"
    ]
    subprocess.check_call(cmd, cwd=root_dir)

    # Dọn dẹp thư mục tạm và file spec thừa sau khi build xong
    for item in ["build", "dist", "HCMUS_AutoWifi.spec", "HCMUS_AutoWifi.exe.old"]:
        p = os.path.join(root_dir, item)
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)
        elif os.path.isfile(p):
            try:
                os.remove(p)
            except OSError:
                pass

    target_exe = os.path.join(root_dir, "HCMUS_AutoWifi.exe")
    if os.path.exists(target_exe):
        print(f"\n[Build] THÀNH CÔNG! File thực thi đã được tạo trực tiếp tại: {target_exe}")
    else:
        print("\n[Build] Không tìm thấy file exe sau khi build.")

if __name__ == "__main__":
    build()
