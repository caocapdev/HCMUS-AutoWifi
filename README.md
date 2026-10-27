# HCMUS AutoWifi

Ứng dụng Windows tự động phát hiện mạng Wi-Fi có trang đăng nhập (Captive Portal) và thực hiện đăng nhập tự động. Được thiết kế tối ưu cho Wi-Fi tại Trường Đại học Khoa học Tự nhiên (ĐHQG-HCM), Wi-Mesh Rescue KTX Khu B (tự động kết nối lại sau mỗi 15 phút) và hỗ trợ các hệ thống công cộng phổ biến khác (AWING, MikroTik,...).

## Sử dụng nhanh

- Tải file [HCMUS_AutoWifi.exe](https://github.com/caocapdev/HCMUS-AutoWifi/releases/latest/download/HCMUS_AutoWifi.exe) từ mục Releases.
- Chạy file. Ứng dụng sẽ tự động chạy nền trong khay hệ thống (System Tray) và đăng ký tự khởi động cùng Windows.
- Khi kết nối vào Wi-Fi cần đăng nhập (`HCMUS-STUDENT`, `HCMUS-PUBLIC`, `Highlands Coffee`, v.v.), ứng dụng sẽ tự động chấp nhận điều khoản và kết nối Internet.

## Chạy từ mã nguồn

Yêu cầu Python 3.10 trở lên trên Windows:

```bash
git clone https://github.com/caocapdev/HCMUS-AutoWifi.git
cd HCMUS-AutoWifi
pip install -r requirements.txt
python main.py
```

Để chạy ẩn trực tiếp vào khay hệ thống:
```bash
pythonw main.py --tray
```

Để đóng gói lại thành file exe:
```bash
python build_exe.py
```

## Cách thức hoạt động

1. **Giám sát mạng**: Định kỳ gửi request tới probe NCSI của Windows (`http://www.msftconnecttest.com/connecttest.txt`).
2. **Nhận diện cổng**: Nếu request bị redirect về captive portal, hệ thống sẽ phân tích URL và mã HTML để chọn cơ chế kết nối phù hợp:
   - **HCMUS (OPNsense)**: Gửi trực tiếp request `POST /api/captiveportal/access/logon/` để mở phiên truy cập tức thì, hoặc tương tác DOM trên trình duyệt để kích hoạt biến điều khoản và nút `#signin_anon`.
   - **AWING**: Tự động đợi đếm ngược quảng cáo và kích hoạt nút kết nối.
   - **Generic**: Dự phòng cho các hệ thống MikroTik, pfSense, Aruba bằng cách tự động đánh dấu checkbox điều khoản và submit form.
3. **Tương tác trình duyệt**: Sử dụng giao thức Chrome DevTools Protocol (CDP) kết nối trực tiếp với Microsoft Edge có sẵn trên Windows 10/11, không cần cài đặt hay cập nhật WebDriver.

## Tùy chọn khởi động cùng Windows (Startup on Boot)

Ứng dụng hỗ trợ 2 chế độ khởi động linh hoạt, dễ dàng thiết lập ngay trên giao diện hoặc menu khay hệ thống:

| Chế độ | Độ ưu tiên | Đặc điểm & Cơ chế |
| :--- | :--- | :--- |
| **Không khởi động** | - | Không tự động khởi chạy khi mở máy. |
| **Mặc định (Registry Run)** | Tiêu chuẩn | Sử dụng khóa Registry `HKCU\...\Run`. Không cần quyền Administrator, hoàn toàn an toàn và tương thích với mọi tài khoản người dùng. |
| **Task Scheduler (Khởi động nhanh)** | Nhanh không trễ | Sử dụng Windows Task Scheduler với độ trễ 0s (`PT0S`), kích hoạt tức thì khi vừa đăng nhập desktop (chạy cả khi máy đang dùng pin laptop). |

> [!TIP]
> Bạn có thể chuyển đổi nhanh giữa các chế độ bất cứ lúc nào bằng cách nhấp chuột phải vào biểu tượng khay hệ thống (System Tray) -> **Khởi động (Startup)** hoặc trong tab **Cài đặt hệ thống** của ứng dụng.

## Cấu trúc dự án

```text
HCMUS-AutoWifi/
├── HCMUS_AutoWifi.exe        # Bản phát hành độc lập
├── main.py                   # Điểm khởi chạy ứng dụng và vòng lặp giám sát
├── requirements.txt          # Danh sách thư viện phụ thuộc
├── build_exe.py              # Script build PyInstaller
├── config.json               # Cấu hình lưu trữ
├── assets/                   # Biểu tượng ứng dụng (.ico, .png)
├── core/
│   ├── config.py             # Đọc và ghi cấu hình
│   ├── network_checker.py    # Kiểm tra trạng thái Wi-Fi và NCSI probe
│   ├── startup_manager.py    # Đăng ký khởi động cùng Windows (Registry)
│   ├── notifier.py           # Thông báo hệ thống
│   ├── portal_solver.py      # Điều phối kết nối qua CDP hoặc HTTP
│   └── portals/              # Các module xử lý từng loại cổng
│       ├── base.py           # Interface BasePortal
│       ├── hcmus.py          # Xử lý cổng HCMUS
│       ├── awing.py          # Xử lý cổng AWING
│       └── generic.py        # Xử lý cổng tiêu chuẩn
└── ui/
    ├── main_window.py        # Cửa sổ giao diện chính
    └── tray_icon.py          # Quản lý biểu tượng khay hệ thống
```

## Giấy phép

Dự án này được phát hành theo giấy phép mã nguồn mở [GNU General Public License v3.0 (GPLv3)](LICENSE).

Mọi cá nhân được tự do sử dụng, nghiên cứu, chỉnh sửa và phân phối lại mã nguồn theo các điều khoản trong tệp [LICENSE](LICENSE). Phục vụ mục đích học tập và hỗ trợ cộng đồng sinh viên.
