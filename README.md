# TikTok Phone Poster — tự chuyển video sang điện thoại Android và tự đăng TikTok

PC làm phần nặng (render video), điện thoại chỉ làm khâu đăng: script tự đẩy
video sang điện thoại qua ADB, mở app TikTok và bấm đăng như người dùng thật
(uiautomator2), caption lấy từ file `.txt` đi kèm video.

## Chuẩn bị trên điện thoại (làm 1 lần)

1. Bật **Tùy chọn nhà phát triển**: Cài đặt → Giới thiệu điện thoại → chạm
   **Số bản dựng (Build number)** 7 lần.
2. Trong Tùy chọn nhà phát triển: bật **Gỡ lỗi USB (USB debugging)**.
3. Cắm cáp USB vào PC, trên điện thoại bấm **Cho phép** khi hỏi gỡ lỗi USB.
4. Đăng nhập sẵn tài khoản TikTok cần đăng trong app.
5. Khuyên dùng cho máy phụ: **tắt khóa màn hình** (hoặc Smart Lock) — script
   mở khóa được màn hình không mật khẩu; có PIN thì nó không qua được.
6. Để máy cắm sạc + Wi-Fi nhà khi chạy đăng.

## Chuẩn bị trên PC

- Cài Python 3.11+ (nhớ tick "Add python.exe to PATH").
- Sau đó chỉ cần **bấm đúp `run_poster.bat`**: lần đầu nó tự tạo môi trường
  riêng (`.venv`) + cài thư viện, rồi hiện menu chọn số:
  `1` cài agent lên điện thoại · `2` test mở TikTok + lướt · `3` đăng thử
  (dry-run) · `4` đăng thật. Các lệnh `python ...` dưới đây là đường gõ tay
  tương đương cho ai thích dùng terminal.

## Cài agent lên điện thoại (1 lần, qua USB)

```
python phone_poster.py --init
```

Lệnh này cài agent điều khiển lên điện thoại, kiểm tra kết nối và mở thử
TikTok. Sau đó có thể rút cáp nếu đã bật ADB qua Wi-Fi
(`adb tcpip 5555` rồi `--serial 192.168.x.x:5555`); không thì cứ cắm USB.

## Test mức 1: mở app + lướt feed (nên chạy đầu tiên)

```
python test_open_scroll.py
```

Mở TikTok, lướt 5 video (mỗi video dừng xem ngẫu nhiên 4–10 giây như người
thật), chụp màn hình cuối vào `test_scroll.png`. Chưa đăng, chưa bấm thích,
chưa động vào gì khác — chỉ để chắc chắn PC điều khiển được điện thoại và
TikTok mở đúng app. Thêm `--scrolls 8` nếu muốn lướt nhiều hơn.

## Cách dùng

Thả video vào thư mục `outbox/` (mặc định) — hoặc trỏ `--dir` vào bất kỳ
thư mục nào, kể cả thư mục xuất của clipgen (quét đệ quy):

- `video.mp4` + `video.txt` (cùng tên) → caption/hashtag nằm trong `.txt`.
- Layout mỗi story một folder con (video + file caption trong folder) cũng
  được tự nhận.

Chạy thử trước (làm mọi bước, chụp ảnh màn hình ở bước cuối, **không** bấm Đăng):

```
python phone_poster.py --dir D:\outbox --dry-run
```

Đăng thật:

```
python phone_poster.py --dir D:\outbox
```

Tùy chọn:

- `--max-posts 3` — chỉ đăng tối đa 3 video trong lần chạy này.
- `--gap-min 240 --gap-max 540` — nghỉ ngẫu nhiên 4–9 phút giữa hai lần đăng
  (mặc định đúng như vậy — đăng dồn dập là dấu hiệu bot rõ nhất).
- `--keep-on-phone` — giữ lại video trên điện thoại sau khi đăng (mặc định
  xóa cho đỡ đầy máy phụ).
- `--serial ...` — chọn đúng máy khi cắm nhiều thiết bị / dùng Wi-Fi ADB.

Sau khi đăng xong, video + caption được chuyển vào `_done/`; lỗi thì vào
`_failed/` kèm thư mục `errors/<thời gian>_<tên video>/` chứa ảnh chụp màn
hình + cấu trúc giao diện tại bước lỗi — gửi thư mục đó cho Muse là chẩn
đoán được TikTok đã đổi giao diện ở đâu.

## Lưu ý thật

- Lần đăng thật đầu tiên **chưa kiểm chứng được từ phía Muse** (không có
  điện thoại của bạn ở đây) — hãy chạy `--dry-run` trước và nhìn điện thoại
  đi hết các bước tới màn hình nhập caption; nếu kẹt ở bước nào, thư mục
  `errors/` cho biết chính xác bước đó.
- Giao diện TikTok đổi theo phiên bản app → thỉnh thoảng phải chỉnh lại nhãn
  nút trong `phone_poster.py` (đã hỗ trợ sẵn tiếng Anh + tiếng Việt).
- Script chọn **video mới nhất** trong thư viện của TikTok sau khi đẩy file —
  đừng mở thư viện/chụp thêm ảnh trong lúc nó chạy.
