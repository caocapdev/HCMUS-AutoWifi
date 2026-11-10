# HCMUS AutoWifi

Ứng dụng Windows tự động phát hiện mạng Wi-Fi có trang đăng nhập (Captive Portal) và thực hiện đăng nhập tự động. Được thiết kế tối ưu cho Wi-Fi tại Trường Đại học Khoa học Tự nhiên (ĐHQG-HCM), Wi-Mesh Rescue KTX Khu B (tự động kết nối lại sau mỗi 15 phút) và hỗ trợ các hệ thống công cộng phổ biến khác (AWING, ChilliSpot UAM VinBus, MikroTik,...).

## Sử dụng nhanh

1. Tải [HCMUS_AutoWifi.exe](https://github.com/caocapdev/HCMUS-AutoWifi/releases/latest/download/HCMUS_AutoWifi.exe).
2. Chạy file. Ứng dụng tự động chạy nền ở khay hệ thống và đăng nhập khi phát hiện portal.

## Chạy từ mã nguồn

Yêu cầu Python 3.10+ trên Windows:

```bash
git clone https://github.com/caocapdev/HCMUS-AutoWifi.git
cd HCMUS-AutoWifi
pip install -r requirements.txt
python main.py
```

- Chạy ẩn khay hệ thống: `pythonw main.py --tray`
- Đóng gói file exe: `python build_exe.py`

## Tính năng

- **Hỗ trợ đa dạng portal**: HCMUS (OPNsense API), AWING, ChilliSpot UAM (VinBus), MikroTik, Aruba, pfSense.
- **HTTP Fast-path**: Kết nối trực tiếp qua API/HTTP không cần mở trình duyệt khi hỗ trợ.
- **Trình duyệt tự động (CDP)**: Tương tác qua Microsoft Edge có sẵn, tự động bỏ qua quảng cáo và form đăng nhập.
- **Vượt cảnh báo bảo mật**: Tự động bỏ qua lỗi SSL / Not Secure ("Tiếp tục đến trang web") và chống nghẽn timer nền.
- **Khởi động cùng Windows**: Tùy chọn Registry Run hoặc Task Scheduler (không trễ).

## Khởi động cùng Windows

| Chế độ | Cơ chế |
| :--- | :--- |
| **Mặc định** | Registry `HKCU\...\Run` (không cần quyền Admin). |
| **Task Scheduler** | Windows Task Scheduler độ trễ 0s, kích hoạt tức thì khi đăng nhập desktop. |

> Đổi chế độ nhanh qua chuột phải khay hệ thống -> **Khởi động (Startup)** hoặc tab **Cài đặt**.

## Cấu trúc dự án

```text
HCMUS-AutoWifi/
├── HCMUS_AutoWifi.exe        # File thực thi độc lập
├── main.py                   # Điểm khởi chạy và vòng lặp giám sát
├── requirements.txt          # Thư viện phụ thuộc
├── build_exe.py              # Script đóng gói PyInstaller
├── config.json               # File cấu hình
├── assets/                   # Icon ứng dụng
├── core/
│   ├── config.py             # Quản lý cấu hình
│   ├── network_checker.py    # Kiểm tra Wi-Fi và NCSI probe
│   ├── startup_manager.py    # Quản lý khởi động Windows
│   ├── notifier.py           # Thông báo hệ thống
│   ├── portal_solver.py      # Điều phối kết nối HTTP & CDP
│   └── portals/              # Chiến lược xử lý portal (HCMUS, AWING, Generic)
└── ui/
    ├── main_window.py        # Cửa sổ giao diện chính
    └── tray_icon.py          # Khay hệ thống
```

## Giấy phép

Phát hành theo giấy phép [GNU GPLv3](LICENSE).
