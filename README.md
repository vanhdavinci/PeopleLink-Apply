# PeopleLink Apply Tool

App local (Windows + macOS) để sync địa chỉ, lấy project/link ứng tuyển, import Excel và submit form apply hàng loạt.

## Yêu cầu

- Python **3.11+** (đã test với 3.13)
- Không cần Docker / không cần deploy

## Cài đặt

```bash
cd peoplelink-apply

# Windows (dùng py launcher)
py -3 -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

## Chạy

```bash
streamlit run app/main.py
```

Lần đầu app sẽ tạo `data/peoplelink.db` (SQLite).

Mở trình duyệt tại URL Streamlit in ra (thường `http://localhost:8501`).

Trang đầu yêu cầu **đăng nhập**. Một account: `PEOPLELINK_AUTH_USERNAME` / `PEOPLELINK_AUTH_PASSWORD` (mặc định `kimngaan` / `230426`). Nhiều account dùng JSON:

```env
PEOPLELINK_AUTH_USERS={"kimngaan":"230426","vietanh":"pass2","admin":"pass3"}
```

Phiên dùng **token ký ngắn hạn** theo từng tab/browser: mặc định **4 giờ** (`PEOPLELINK_AUTH_SESSION_HOURS`), tự gia hạn khi còn dùng; hết hạn hoặc **Đăng xuất** phải login lại.

## Cấu trúc

```
peoplelink-apply/
  app/
    main.py          # UI entry (Streamlit)
    config.py        # đường dẫn, URL API, settings
    db/              # SQLite schema + connection
    services/        # sync địa chỉ, project, submit (bước sau)
    ui/              # page helpers
  data/              # peoplelink.db (tạo lúc chạy)
  templates/         # Excel mẫu (bước sau)
```

## Stack

| Thành phần | Công nghệ |
|---|---|
| UI | Streamlit |
| HTTP | httpx |
| HTML parse | BeautifulSoup + lxml |
| Excel | pandas + openpyxl |
| DB | SQLite (1 file trong `data/`) |

## Roadmap

1. **Công nghệ (bước này)** — scaffold, DB, app shell
2. Location Sync (tỉnh → huyện → xã)
3. Form public + Excel import + submit
4. (Optional) sync project/Detail bằng cookie portal
