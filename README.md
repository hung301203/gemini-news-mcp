# Gemini News MCP Server

Remote **Stateless Streamable HTTP MCP Server** tối ưu để deploy 100% lên **Render** cho **Gemini Web** (`gemini.google.com`) gọi về cập nhật thời sự theo 3 mảng:

1. **Khoa học – Tự động hóa:** arXiv (`cs.RO`, `eess.SY`), IEEE Spectrum Robotics, ScienceDaily Robotics, Hacker News, VnExpress Khoa học & Công nghệ, Google News (EN/VI cho Robotics, PLC/SCADA, Tự động hóa công nghiệp).
2. **Tài chính & Nguyên nhân gây biến động:** Dữ liệu giá/chỉ số từ Yahoo Finance (`^GSPC`, `^IXIC`, `DX-Y.NYB`, `E1VFVN30.VN`, `VNM`, `USDVND=X`, `GC=F`, `CL=F`, `BTC-USD`, `ETH-USD` hoặc mã tùy chọn) ghép trực tiếp với cụm tin CNBC, MarketWatch, Yahoo Finance News, CafeF, VnExpress Kinh doanh, Vietstock + gắn thẻ nhóm nguyên nhân (*lãi suất, lạm phát, lợi nhuận, địa chính trị, hàng hóa/tỷ giá, dòng tiền*).
3. **Wellness có dẫn chứng:** PubMed (NIH — thử nghiệm lâm sàng/meta-analysis trên người), ScienceDaily (Health, Mind & Brain, Nutrition), VnExpress Sức khỏe & Google News chọn lọc.

Mọi bản tin đi qua bộ **chấm điểm độ uy tín minh bạch (0–100, Tier A / B / C / Low)** dựa trên uy tín nguồn gốc, xác nhận chéo đa nguồn, bằng chứng nghiên cứu/số liệu và bộ lọc phạt tin giật gân/clickbait/tin đồn.

---

## MCP Tools

| Tool | Công dụng |
| :--- | :--- |
| `get_daily_briefing` | Điểm tin nhanh cả 3 mảng trong 24h–7 ngày |
| `get_automation_news` | Tin & bài báo khoa học về Tự động hóa (`all`, `robotics`, `industrial`, `control_ai`, `papers`) |
| `get_market_movers_and_drivers` | Biến động thị trường/mã cổ phiếu + cụm tin lý giải nguyên nhân |
| `get_wellness_updates` | Thông tin sức khỏe & wellness có dẫn chứng (`all`, `sleep`, `nutrition`, `exercise`, `mental_health`, `research`) |
| `search_current_affairs` | Tìm kiếm chủ động theo từ khóa/sự kiện bất kỳ |
| `read_article` | Trích nội dung sạch của 1 bài báo (có chống SSRF & đánh giá độ uy tín domain) |

---

## Chạy thử local

```bash
uv sync
uv run uvicorn gemini_news_mcp.server:app --host 0.0.0.0 --port 8000
```

Kiểm tra nhanh:
```bash
curl http://localhost:8000/health
```

---

## Deploy 100% trên Render (không cần mở máy tính cá nhân)

### Bước 1: Đẩy code lên GitHub
Tạo 1 repository mới trên GitHub (public hoặc private đều được) rồi push thư mục dự án này lên.

### Bước 2: Tạo Web Service trên Render
1. Đăng nhập [Render Dashboard](https://dashboard.render.com/) → **New** → **Blueprint** (dùng sẵn `render.yaml`) hoặc **Web Service** → chọn repo GitHub của bạn.
2. Runtime: **Docker** (Render tự nhận `Dockerfile`).
3. Thêm biến môi trường (Environment Variables):
   * `MCP_PATH_SECRET`: đặt một chuỗi ngẫu nhiên (ví dụ chạy `openssl rand -hex 20`) để bảo vệ endpoint thành `https://<ten-app>.onrender.com/mcp/<MCP_PATH_SECRET>`. Nếu để trống, endpoint sẽ là `https://<ten-app>.onrender.com/mcp`.
   * `CACHE_TTL_SECONDS`: `600` (mặc định 10 phút).
   * `RATE_LIMIT_RPM`: `60`.
4. Bấm **Deploy**. Sau khi xong, kiểm tra `https://<ten-app>.onrender.com/health` trả về `{"status": "ok", ...}`.

### Bước 3: Kết nối vào Gemini Web
1. Mở [gemini.google.com](https://gemini.google.com/) (đảm bảo đã bật **Gemini Apps Activity**).
2. Vào **Settings & help → Connected Apps → Custom apps → Add a custom app**.
3. Dán URL MCP của bạn:
   * Có secret: `https://<ten-app>.onrender.com/mcp/<MCP_PATH_SECRET>`
   * Không secret: `https://<ten-app>.onrender.com/mcp`
4. Xác nhận kết nối và thử hỏi Gemini:
   * *"Dùng tool điểm tin sáng nay cho mình về tự động hóa, biến động tài chính và wellness"*
   * *"Kiểm tra VN-Index, vàng và S&P 500 hôm nay biến động vì nguyên nhân gì?"*
   * *"Tìm các nghiên cứu mới về giấc ngủ và dinh dưỡng đạt Tier A/B"*

### Mẹo giữ ấm Render Free Tier (tránh ngủ sau 15 phút)
* Nếu dùng gói **Render Free**, service sẽ ngủ sau 15 phút không có truy cập (lần gọi đầu mất 15–30s dễ làm Gemini timeout).
* Giải pháp miễn phí: tạo 1 monitor trên [UptimeRobot](https://uptimerobot.com/) hoặc [cron-job.org](https://cron-job.org/) gọi `GET https://<ten-app>.onrender.com/health` mỗi **10 phút**.
* Hoặc nâng lên gói **Render Starter (\$7/tháng)** để chạy 24/7 không cold start.
