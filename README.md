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
  (dry-run) · `4` đăng thật · `5` xem các acc đã đăng nhập · `6` đổi acc thử.
  Các lệnh `python ...` dưới đây là đường gõ tay tương đương cho ai thích
  dùng terminal.

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
- `--no-warmup` — bỏ qua bước lướt feed khởi động (mặc định mỗi lần chạy sẽ
  lướt feed 1–2 phút trước khi đăng, như người thật mở app).
- `--warmup-min 60 --warmup-max 120` — chỉnh thời gian lướt feed khởi động.
- `--account-tag irl` — nhãn acc cho lần chạy này: file xong/lỗi vào
  `_done-irl/` / `_failed-irl/` riêng. Dùng khi test 2 mảng trên 2 acc:
  mỗi acc một thư mục queue + một tag, khỏi lẫn kết quả.
- `--account username` — acc PHẢI đăng cho lần chạy này (khác `--account-tag`
  ở trên: tag chỉ là nhãn thư mục, còn `--account` là username thật). Tool
  kiểm tra acc đang mở trước mỗi lần đăng: sai acc thì **tự đổi** sang đúng
  acc, đổi không được (hoặc TikTok đòi xác minh) thì **dừng, không đăng** —
  tránh thảm họa đăng video mảng A sang kênh B.
- `--list-accounts` — mở TikTok và liệt kê mọi acc đã đăng nhập trong app
  (đánh dấu acc đang mở) rồi thoát. Kiểm tra nhanh "máy đang có những acc nào".
- `--switch-to username` — đổi sang acc khác đã đăng nhập sẵn, đọc lại trang
  Hồ sơ xác nhận xong thì thoát. Dùng để test riêng tính năng đổi acc.

## Test 2 mảng trên 2 acc (1 máy)

Cách A — cả 2 acc đăng nhập trong **cùng một app TikTok** (dùng bộ chuyển
tài khoản có sẵn của TikTok): tool tự đổi acc theo `--account`, khỏi mở tay:

```
python phone_poster.py --dir D:\outbox\irl   --account acc_irl   --account-tag irl
python phone_poster.py --dir D:\outbox\court --account acc_court --account-tag court
```

Trước khi chạy thật, test 2 lệnh này trước:

```
python phone_poster.py --list-accounts     # thấy đủ 2 acc chưa?
python phone_poster.py --switch-to acc_court   # đổi thử + xác nhận
```

Cách B — mỗi acc một **không gian** trên máy (Không gian thứ hai của Xiaomi):
tách bạch hơn nhưng tool không tự chuyển không gian được — mở đúng không
gian của acc đó rồi chạy lệnh tương ứng (không cần `--account`, giữ
`--account-tag` để tách kết quả).

Gom đăng theo acc (đăng hết acc A rồi mới đổi sang acc B) thay vì đổi qua
lại từng video — ít lần đổi thì giống người thật hơn và ít bị TikTok hỏi
xác minh lại. Đừng để 2 acc tương tác chéo nhau (không follow/like chéo).

## Né phát hiện tự động hóa

Tool đã né 3 dấu vết hành vi dễ lộ nhất: **bấm rải** — mỗi cú bấm rơi vào
điểm ngẫu nhiên trong khung nút thay vì đúng tâm; **gõ caption** — gõ từng
cụm 2–6 ký tự với nhịp ngẫu nhiên thay vì dán một phát; **khởi động phiên** —
lướt feed 1–2 phút trước khi đăng thay vì vào thẳng luồng đăng. Cộng với nghỉ
ngẫu nhiên 4–9 phút giữa các lần đăng và chạy trên máy thật + IP nhà, đây là
mức rủi ro thấp nhất trong các kiểu tự động hóa — nhưng "không bị biết" tuyệt
đối thì không tồn tại: acc chính đang ăn tiền thì cân nhắc đăng tay.

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
