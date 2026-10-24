import tkinter as tk
from tkinter import ttk, messagebox
import datetime
import os
import webbrowser
from core.config import config, get_resource_path, APP_VERSION, GITHUB_REPO_URL, AUTHOR_URL
from core.startup_manager import (
    get_current_startup_mode,
    set_startup_mode,
    MODE_LABELS,
    MODE_NONE
)

# Color Palette - Modern Dark Slate & HCMUS Royal Blue
BG_COLOR = "#0f172a"          # Slate 900
CARD_BG = "#1e293b"           # Slate 800
CARD_BORDER = "#334155"       # Slate 700
PRIMARY_BLUE = "#2563eb"      # Blue 600
PRIMARY_HOVER = "#1d4ed8"     # Blue 700
SUCCESS_GREEN = "#10b981"     # Emerald 500
WARNING_AMBER = "#f59e0b"     # Amber 500
ERROR_RED = "#ef4444"         # Red 500
TEXT_MAIN = "#f8fafc"         # Slate 50
TEXT_MUTED = "#94a3b8"        # Slate 400

LABEL_TO_MODE = {v: k for k, v in MODE_LABELS.items()}
STARTUP_CHOICES = list(MODE_LABELS.values())

class MainWindow:
    def __init__(self, callbacks):
        self.callbacks = callbacks
        self.root = tk.Tk()
        self.root.title(f"HCMUS AutoWifi v{APP_VERSION} - Tự động đăng nhập Wi-Fi")
        self.root.configure(bg=BG_COLOR)

        icon_path = get_resource_path(os.path.join("assets", "icon.ico"))
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception:
                pass

        self.root.protocol("WM_DELETE_WINDOW", self.on_close_requested)
        self._init_styles()
        self._build_ui()
        self._auto_scale_window()
        self.log(f"Khởi động thành công (v{APP_VERSION}).", "info")

    def _init_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TNotebook", background=BG_COLOR, borderwidth=0)
        style.configure("TNotebook.Tab", background=CARD_BG, foreground=TEXT_MUTED, padding=[16, 8], font=("Segoe UI", 10, "bold"))
        style.map("TNotebook.Tab", background=[("selected", PRIMARY_BLUE)], foreground=[("selected", "#ffffff")])

        style.configure(
            "TCombobox", fieldbackground="#090d16", background=CARD_BG, foreground=TEXT_MAIN,
            arrowcolor=TEXT_MAIN, bordercolor=CARD_BORDER, lightcolor=CARD_BORDER, darkcolor=CARD_BORDER, padding=6
        )
        style.map(
            "TCombobox", fieldbackground=[("readonly", "#090d16")], selectbackground=[("readonly", "#090d16")],
            selectforeground=[("readonly", TEXT_MAIN)], foreground=[("readonly", TEXT_MAIN)]
        )
        for opt, val in [("background", CARD_BG), ("foreground", TEXT_MAIN), ("selectBackground", PRIMARY_BLUE), ("selectForeground", "#ffffff")]:
            self.root.option_add(f"*TCombobox*Listbox.{opt}", val)
        self.root.option_add("*TCombobox*Listbox.font", ("Segoe UI", 10))

    def _build_ui(self):
        # 1. Header Bar
        header = tk.Frame(self.root, bg=BG_COLOR, padx=20, pady=14)
        header.pack(fill=tk.X)

        title_box = tk.Frame(header, bg=BG_COLOR)
        title_box.pack(side=tk.LEFT)
        tk.Label(title_box, text="HCMUS AutoWifi", font=("Segoe UI", 18, "bold"), fg=TEXT_MAIN, bg=BG_COLOR).pack(anchor="w")
        tk.Label(title_box, text="Tự động đăng nhập Wi-Fi (HCMUS, AWING, MikroTik, v.v.)", font=("Segoe UI", 9), fg=TEXT_MUTED, bg=BG_COLOR).pack(anchor="w", pady=(2, 0))

        self.status_pill = tk.Label(header, text="● Đang kiểm tra...", font=("Segoe UI", 10, "bold"), fg="#ffffff", bg=CARD_BG, padx=14, pady=6)
        self.status_pill.pack(side=tk.RIGHT, pady=4)

        # 2. Network Info Card
        card = tk.Frame(self.root, bg=CARD_BG, padx=18, pady=14, highlightbackground=CARD_BORDER, highlightthickness=1)
        card.pack(fill=tk.X, padx=20, pady=(0, 12))
        card.columnconfigure(1, weight=1)
        card.columnconfigure(3, weight=1)

        tk.Label(card, text="Mạng Wi-Fi:", font=("Segoe UI", 10), fg=TEXT_MUTED, bg=CARD_BG).grid(row=0, column=0, sticky="w", pady=4)
        self.lbl_ssid = tk.Label(card, text="Đang tải...", font=("Segoe UI", 11, "bold"), fg=TEXT_MAIN, bg=CARD_BG)
        self.lbl_ssid.grid(row=0, column=1, sticky="w", padx=(8, 20), pady=4)

        tk.Label(card, text="Tín hiệu:", font=("Segoe UI", 10), fg=TEXT_MUTED, bg=CARD_BG).grid(row=0, column=2, sticky="w", pady=4)
        self.lbl_signal = tk.Label(card, text="0%", font=("Segoe UI", 11, "bold"), fg=TEXT_MAIN, bg=CARD_BG)
        self.lbl_signal.grid(row=0, column=3, sticky="w", padx=(8, 0), pady=4)

        tk.Label(card, text="Trạng thái:", font=("Segoe UI", 10), fg=TEXT_MUTED, bg=CARD_BG).grid(row=1, column=0, sticky="w", pady=4)
        self.lbl_portal_status = tk.Label(card, text="Đang quét...", font=("Segoe UI", 10), fg=TEXT_MAIN, bg=CARD_BG)
        self.lbl_portal_status.grid(row=1, column=1, sticky="w", padx=(8, 20), pady=4)

        tk.Label(card, text="Số lần đăng nhập:", font=("Segoe UI", 10), fg=TEXT_MUTED, bg=CARD_BG).grid(row=1, column=2, sticky="w", pady=4)
        self.lbl_total_logins = tk.Label(card, text=str(config.get("total_logins", 0)), font=("Segoe UI", 11, "bold"), fg=SUCCESS_GREEN, bg=CARD_BG)
        self.lbl_total_logins.grid(row=1, column=3, sticky="w", padx=(8, 0), pady=4)

        # 3. Action Buttons
        btn_bar = tk.Frame(self.root, bg=BG_COLOR, padx=20)
        btn_bar.pack(fill=tk.X, pady=(0, 12))

        self.btn_login = tk.Button(
            btn_bar, text="ĐĂNG NHẬP NGAY", font=("Segoe UI", 11, "bold"), fg="#ffffff", bg=PRIMARY_BLUE,
            activebackground=PRIMARY_HOVER, activeforeground="#ffffff", relief=tk.FLAT, padx=20, pady=8, cursor="hand2", command=self._on_manual_login
        )
        self.btn_login.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        self.btn_check = tk.Button(
            btn_bar, text="Kiểm tra kết nối", font=("Segoe UI", 10, "bold"), fg=TEXT_MAIN, bg=CARD_BG,
            activebackground=CARD_BORDER, activeforeground=TEXT_MAIN, relief=tk.FLAT, padx=16, pady=8, cursor="hand2", command=self._on_check_now
        )
        self.btn_check.pack(side=tk.RIGHT)

        # 4. Footer Status Bar (Pack BOTTOM first so it is never pushed off screen)
        footer = tk.Frame(self.root, bg=BG_COLOR, padx=20, pady=8)
        footer.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 6))

        footer_left = tk.Frame(footer, bg=BG_COLOR)
        footer_left.pack(side=tk.LEFT)

        lbl_made = tk.Label(footer_left, text="made with ", font=("Segoe UI", 9), fg=TEXT_MUTED, bg=BG_COLOR, padx=0, pady=0, bd=0, highlightthickness=0, cursor="hand2")
        lbl_made.pack(side=tk.LEFT)

        lbl_heart = tk.Label(footer_left, text="♥", font=("Segoe UI", 9), fg="#ef4444", bg=BG_COLOR, padx=0, pady=0, bd=0, highlightthickness=0, cursor="hand2")
        lbl_heart.pack(side=tk.LEFT)

        lbl_by = tk.Label(footer_left, text=" by ", font=("Segoe UI", 9), fg=TEXT_MUTED, bg=BG_COLOR, padx=0, pady=0, bd=0, highlightthickness=0, cursor="hand2")
        lbl_by.pack(side=tk.LEFT)

        lbl_author = tk.Label(footer_left, text="caocap.dev", font=("Segoe UI", 9, "bold"), fg="#38bdf8", bg=BG_COLOR, padx=0, pady=0, bd=0, highlightthickness=0, cursor="hand2")
        lbl_author.pack(side=tk.LEFT)

        for w in [lbl_made, lbl_heart, lbl_by, lbl_author]:
            w.bind("<Button-1>", lambda e: webbrowser.open(AUTHOR_URL))

        lbl_author.bind("<Enter>", lambda e: lbl_author.config(fg="#93c5fd"))
        lbl_author.bind("<Leave>", lambda e: lbl_author.config(fg="#38bdf8"))

        tk.Label(footer_left, text="•", font=("Segoe UI", 8), fg="#475569", bg=BG_COLOR, padx=6, pady=0, bd=0, highlightthickness=0).pack(side=tk.LEFT)

        lbl_repo = tk.Label(footer_left, text="GitHub", font=("Segoe UI", 9, "bold"), fg="#38bdf8", bg=BG_COLOR, padx=0, pady=0, bd=0, highlightthickness=0, cursor="hand2")
        lbl_repo.pack(side=tk.LEFT)
        lbl_repo.bind("<Button-1>", lambda e: webbrowser.open(GITHUB_REPO_URL))
        lbl_repo.bind("<Enter>", lambda e: lbl_repo.config(fg="#93c5fd"))
        lbl_repo.bind("<Leave>", lambda e: lbl_repo.config(fg="#38bdf8"))

        tk.Label(footer_left, text="•", font=("Segoe UI", 8), fg="#475569", bg=BG_COLOR, padx=6, pady=0, bd=0, highlightthickness=0).pack(side=tk.LEFT)

        lbl_version = tk.Label(footer_left, text=f"v{APP_VERSION}", font=("Segoe UI", 9), fg=TEXT_MUTED, bg=BG_COLOR, padx=0, pady=0, bd=0, highlightthickness=0)
        lbl_version.pack(side=tk.LEFT)

        tk.Button(
            footer, text="Thu nhỏ vào khay", font=("Segoe UI", 8),
            fg=TEXT_MUTED, bg=CARD_BG, activebackground=CARD_BORDER, activeforeground=TEXT_MAIN,
            relief=tk.FLAT, padx=10, pady=3, cursor="hand2", command=self.hide_to_tray
        ).pack(side=tk.RIGHT)

        # 5. Notebook (Tabs) (Pack TOP with expand=True, fills the area above footer)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=20, pady=(0, 6))

        # Tab 1: Activity Log
        tab_log = tk.Frame(self.notebook, bg=BG_COLOR)
        self.notebook.add(tab_log, text="Nhật ký hoạt động")

        log_box = tk.Frame(tab_log, bg=CARD_BG, highlightbackground=CARD_BORDER, highlightthickness=1)
        log_box.pack(fill=tk.BOTH, expand=True, pady=6)

        self.log_text = tk.Text(log_box, bg="#090d16", fg=TEXT_MAIN, font=("Consolas", 9), height=11, padx=10, pady=10, wrap=tk.WORD, borderwidth=0)
        scrollbar = tk.Scrollbar(log_box, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.log_text.tag_config("time", foreground="#64748b")
        self.log_text.tag_config("info", foreground="#38bdf8")
        self.log_text.tag_config("success", foreground="#34d399")
        self.log_text.tag_config("warning", foreground="#fbbf24")
        self.log_text.tag_config("error", foreground="#f87171")

        log_foot = tk.Frame(tab_log, bg=BG_COLOR)
        log_foot.pack(fill=tk.X, pady=(0, 2))
        tk.Button(log_foot, text="Xóa nhật ký", font=("Segoe UI", 9), fg=TEXT_MUTED, bg=CARD_BG, relief=tk.FLAT, padx=10, pady=2, command=self._clear_logs).pack(side=tk.RIGHT)

        # Tab 2: Settings
        tab_settings = tk.Frame(self.notebook, bg=BG_COLOR)
        self.notebook.add(tab_settings, text="Cài đặt hệ thống")
        self._build_settings_tab(tab_settings)

    def _auto_scale_window(self):
        w, h = 660, 640
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 2)}")
        self.root.minsize(580, 560)

    def _build_settings_tab(self, parent):
        card = tk.Frame(parent, bg=CARD_BG, padx=18, pady=12, highlightbackground=CARD_BORDER, highlightthickness=1)
        card.pack(fill=tk.BOTH, expand=True, pady=6)

        # Startup Dropdown
        row_startup = tk.Frame(card, bg=CARD_BG)
        row_startup.pack(fill=tk.X, pady=(0, 8))
        tk.Label(row_startup, text="Khởi động cùng Windows:", font=("Segoe UI", 10, "bold"), fg=TEXT_MAIN, bg=CARD_BG).pack(side=tk.LEFT, padx=(0, 10))
        self.combo_startup = ttk.Combobox(row_startup, values=STARTUP_CHOICES, state="readonly", font=("Segoe UI", 10))
        self.combo_startup.set(MODE_LABELS.get(get_current_startup_mode(), STARTUP_CHOICES[0]))
        self.combo_startup.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # General Checkboxes
        self.checkbox_vars = {
            "auto_login_enabled": (tk.BooleanVar(value=config.get("auto_login_enabled", True)), "Tự động đăng nhập khi phát hiện Captive Portal"),
            "headless": (tk.BooleanVar(value=config.get("headless", True)), "Chế độ ẩn trình duyệt (Headless)"),
            "notifications": (tk.BooleanVar(value=config.get("notifications", True)), "Gửi thông báo khi đăng nhập thành công"),
            "close_to_tray": (tk.BooleanVar(value=config.get("close_to_tray", True)), "Thu nhỏ vào khay hệ thống khi đóng")
        }

        for var, text in self.checkbox_vars.values():
            tk.Checkbutton(card, text=text, variable=var, font=("Segoe UI", 10), fg=TEXT_MAIN, bg=CARD_BG,
                           activebackground=CARD_BG, activeforeground=TEXT_MAIN, selectcolor="#090d16", cursor="hand2").pack(anchor="w", pady=2)

        # Row with Interval + Save Button side by side
        row_bottom = tk.Frame(card, bg=CARD_BG)
        row_bottom.pack(fill=tk.X, pady=(8, 0))

        tk.Label(row_bottom, text="Chu kỳ quét kết nối Wi-Fi (giây):", font=("Segoe UI", 10), fg=TEXT_MAIN, bg=CARD_BG).pack(side=tk.LEFT)
        self.var_interval = tk.StringVar(value=str(config.get("check_interval", 1)))
        spn = tk.Spinbox(row_bottom, from_=1, to=60, width=5, textvariable=self.var_interval, bg="#090d16", fg=TEXT_MAIN, font=("Segoe UI", 10))
        spn.pack(side=tk.LEFT, padx=10)

        btn_save = tk.Button(
            row_bottom, text="Lưu cấu hình", font=("Segoe UI", 10, "bold"), fg="#ffffff", bg=PRIMARY_BLUE,
            activebackground=PRIMARY_HOVER, activeforeground="#ffffff", relief=tk.FLAT, padx=16, pady=5, cursor="hand2", command=self._save_settings
        )
        btn_save.pack(side=tk.RIGHT)

    def sync_startup_mode_ui(self):
        def _sync():
            mode = get_current_startup_mode()
            self.combo_startup.set(MODE_LABELS.get(mode, STARTUP_CHOICES[0]))
        self.root.after(0, _sync)

    def _save_settings(self):
        selected_label = self.combo_startup.get()
        new_mode = LABEL_TO_MODE.get(selected_label, MODE_NONE)
        current_mode = get_current_startup_mode()

        if new_mode != current_mode:
            self.log(f"Đang cấu hình chế độ khởi động '{selected_label}'...", "info")
            ok, msg = set_startup_mode(new_mode)
            if ok:
                self.log(f"Đã cập nhật chế độ khởi động: {selected_label}", "success")
            else:
                self.log(f"Không thể áp dụng chế độ khởi động: {msg}", "error")
                messagebox.showerror("Lỗi thiết lập khởi động", f"Không thể thiết lập chế độ {selected_label}:\n{msg}")
                self.combo_startup.set(MODE_LABELS.get(current_mode, STARTUP_CHOICES[0]))
                return

        for key, (var, _) in self.checkbox_vars.items():
            config.set(key, var.get())

        try:
            interval = max(1, int(self.var_interval.get()))
            config.set("check_interval", interval)
        except ValueError:
            pass

        self.log("Đã cập nhật và lưu cài đặt cấu hình thành công.", "success")
        messagebox.showinfo("Cài đặt", "Cấu hình đã được lưu thành công!")

    def _clear_logs(self):
        self.log_text.delete("1.0", tk.END)

    def log(self, message: str, tag: str = "info"):
        def _append():
            ts = datetime.datetime.now().strftime("[%H:%M:%S] ")
            self.log_text.insert(tk.END, ts, "time")
            self.log_text.insert(tk.END, f"{message}\n", tag)
            self.log_text.see(tk.END)
        self.root.after(0, _append)

    def update_network_status(self, wifi_info: dict, captive_info: dict):
        def _update():
            self.lbl_ssid.config(text=wifi_info.get("ssid", "Không có kết nối"))
            self.lbl_signal.config(text=wifi_info.get("signal", "0%"))
            self.lbl_total_logins.config(text=str(config.get("total_logins", 0)))

            if captive_info.get("has_internet", False):
                self.status_pill.config(text="● Đã kết nối Internet", bg=SUCCESS_GREEN)
                self.lbl_portal_status.config(text="Internet bình thường", fg=SUCCESS_GREEN)
            elif captive_info.get("is_captive", False):
                self.status_pill.config(text="● Cần đăng nhập Portal", bg=WARNING_AMBER)
                self.lbl_portal_status.config(text="Phát hiện Captive Portal", fg=WARNING_AMBER)
            else:
                self.status_pill.config(text="● Mất kết nối", bg=ERROR_RED)
                self.lbl_portal_status.config(text="Không có kết nối mạng", fg=ERROR_RED)

        self.root.after(0, _update)

    def _on_manual_login(self):
        self.callbacks.get("manual_login", lambda: None)()

    def _on_check_now(self):
        self.callbacks.get("check_now", lambda: None)()

    def on_close_requested(self):
        if config.get("close_to_tray", True):
            self.hide_to_tray()
        else:
            self.exit_app()

    def hide_to_tray(self):
        self.root.withdraw()

    def show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def exit_app(self):
        self.callbacks.get("exit_app", self.root.destroy)()
