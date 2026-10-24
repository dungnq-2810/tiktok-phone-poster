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
Nếu cuối lệnh báo không nói chuyện được với server thì đừng lo: server
vừa cài hay khởi động lại, tool tự thử lại 5 lần; vẫn rớt thì chạy lại
menu 1 một lần nữa, và nếu vẫn rớt thì cho app ATX chạy pin "Không giới
hạn" + khóa nó trong đa nhiệm (MIUI hay tắt app agent chạy nền).

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

Đọc acc chỉ lấy @ ở vùng header trang Hồ sơ (không nhận nhầm @ tác giả
video khi bấm tab Hồ sơ trượt), bấm dòng acc bằng tâm nút cha clickable
(khớp chính xác, không bấm nhầm acc có username là tiền tố của nhau), và
đổi acc xong thì chờ tới khi handle đổi thật (tối đa ~20s) thay vì đọc
một lần sau 3-5s rồi báo lỗi oan.
```

Cách B — mỗi acc một **không gian** trên máy (Không gian thứ hai của Xiaomi):
tách bạch hơn nhưng tool không tự chuyển không gian được — mở đúng không
gian của acc đó rồi chạy lệnh tương ứng (không cần `--account`, giữ
`--account-tag` để tách kết quả).

Gom đăng theo acc (đăng hết acc A rồi mới đổi sang acc B) thay vì đổi qua
lại từng video — ít lần đổi thì giống người thật hơn và ít bị TikTok hỏi
xác minh lại. Đừng để 2 acc tương tác chéo nhau (không follow/like chéo).

## Né phát hiện tự động hóa

Tool đã né các dấu vết hành vi dễ lộ nhất: **bấm rải** — mỗi cú bấm rơi vào
điểm ngẫu nhiên trong khung nút thay vì đúng tâm; **gõ caption** — gõ từng
cụm 2–6 ký tự với nhịp ngẫu nhiên, thỉnh thoảng khựng 0.8–2s như đang nghĩ
câu chữ, thay vì dán một phát; **khởi động phiên** — lướt feed 1–2 phút
trước khi đăng, mỗi video xem 5–11s, thỉnh thoảng xem lâu 12–20s, vuốt với
tốc độ và vị trí ngẫu nhiên; **ngừng xem lại** — trước khi bấm Đăng thì dừng
3–8s như người thật đọc lại caption; **chờ tải lên** — khoảng chờ sau khi
bấm Đăng cũng ngẫu nhiên 10–16s thay vì đúng 12s. Cộng với nghỉ ngẫu nhiên
4–9 phút giữa các lần đăng và chạy trên máy thật + IP nhà, đây là mức rủi
ro thấp nhất trong các kiểu tự động hóa — nhưng "không bị biết" tuyệt đối
thì không tồn tại: acc chính đang ăn tiền thì cân nhắc đăng tay.

Ngoài code, kỷ luật dùng cũng quan trọng không kém: mỗi acc đăng 1–2
video/ngày trong giai đoạn test; không đăng cùng 1 file lên nhiều acc; đăng
xong hết video của acc này rồi mới đổi sang acc khác (đừng đổi acc liên
tục); không đăng ngay sau khi đăng nhập (để warmup chạy); caption, hashtag
và nhạc mỗi acc khác nhau; giữ VPN ổn định trong cả phiên, đừng để IP nhảy
quốc gia giữa chừng.

Sau khi đăng xong, video + caption được chuyển vào `_done/`; lỗi thì vào
`_failed/` kèm thư mục `errors/<thời gian>_<tên video>/` chứa ảnh chụp màn
hình + cấu trúc giao diện tại bước lỗi — gửi thư mục đó cho Muse là chẩn
đoán được TikTok đã đổi giao diện ở đâu.

## Tự cập nhật code

Mỗi lần mở `run_poster.bat`, nó tự `git pull --ff-only` nếu thư mục là git
repo và máy có git — khỏi pull tay mỗi lần có bản sửa. Pull lỗi (không có
mạng, file sửa tay xung đột...) thì nó báo một dòng rồi vẫn chạy bản hiện
có, không dừng lại; file sửa tay của bạn không bị ghi đè (pull --ff-only
không merge khi có xung đột).

## Giao diện GUI (không cần gõ lệnh)

Mở `run_poster.bat` → mục **9**, hoặc bấm đúp trực tiếp `gui.bat` (chỉ
dùng thư viện chuẩn tkinter nên không cần cài thêm gì; nếu Python của bạn
thiếu tkinter thì `gui.bat` báo rõ và hướng dẫn cài lại Python từ
python.org). Giao diện có đủ 8 nút tương ứng 8 mục menu (cài agent, test
lướt feed, đăng thử, đăng thật, xem acc, đổi acc, Wi-Fi ADB, config
ngách), ô chọn thư mục hàng đợi, ô nhập acc, tùy chọn đăng (bỏ warmup,
giữ video, tối đa số video, khoảng nghỉ giữa 2 lần đăng), khung log chạy
trực tiếp và ô "Trả lời" để gõ ngách khi chạy config (vì config hỏi tương
tác từng acc). Nút "Đăng thật" luôn hỏi xác nhận trước khi chạy. Lưu ý:
không có tick chọn dry-run riêng — 2 nút "Đăng thử"/"Đăng thật" là bộ
chọn duy nhất, tránh trường hợp tick dry-run rồi bấm đăng thật mà không
được hỏi lại.

## Config acc theo ngách (lấy danh sách trước, rồi gán)

Mở `run_poster.bat` → mục **8**: tool lấy danh sách acc đang đăng nhập
trong app TikTok trước (giống mục 5), rồi hỏi ngách từng acc một — gõ tên
ngách (vd `A`, `B`, `irl`, `dashcam`), Enter là giữ nguyên — xong lưu vào
file `accounts.json` cạnh `phone_poster.py`. Gán nhanh 1 acc không cần vào
menu: `phone_poster.py --set-niche sandracruzkay183 B`.

Từ đó mục 5 hiển thị thêm ngách từng acc (`[ngách: A]` hoặc `[chưa config
ngách]`), và khi đăng với `--account @user` mà không kèm `--account-tag`
thì tool tự lấy ngách đã config làm nhãn thư mục (`_done-A`,
`_failed-A`), khỏi gõ tay mỗi lần. `--account-tag` gõ tay vẫn thắng config.

Lưu ý: config chỉ gán được cho acc đã đăng nhập trong app. Acc mua về chưa
đăng nhập thì đăng nhập vào app trước, rồi chạy lại mục 8 là thấy nó trong
danh sách.

## Nuôi acc tự động (nuôi là nuôi hết)

Mở `run_poster.bat` → mục **10** (hoặc nút 9 trong GUI): tool lấy danh
sách acc đang đăng nhập trong app rồi nuôi hết, mỗi acc ~10 phút (ngẫu
nhiên 9–11 phút cho đỡ đều) rồi tự đổi acc, cuối phiên in tổng kết từng
acc. Acc nào đổi không được thì bỏ qua, nuôi tiếp acc khác. Ctrl+C dừng
cả phiên (vẫn in tổng kết).

Log realtime từng bước: mỗi video log 1 dòng (đang xem video #N ~Xs, đã
qua video mới, like video #N) — nếu vuốt kẹt thì log báo rõ "vuốt 3 lần +
kéo chậm vẫn không qua video mới" thay vì im lặng. Tool chỉ bấm nút đúng
vị trí (Home/Profile ở thanh dưới, Search ở trên), phần tử nào to quá
khung thì không bấm bừa, và chỉ like sau khi đã xác nhận qua video mới.

Ngách đã config là master, không hỏi lại từ khóa mỗi lần chạy: mục 8
giờ hỏi 2 pha — gán ngách từng acc, rồi hỏi từ khóa tìm kiếm cho từng
ngách (lưu vào `niche_keywords.json`; gán nhanh 1 ngách bằng
`--set-niche-keywords <ngách> "<kw1,kw2>"`). Khi nuôi, acc có ngách thì
đầu phiên tìm kiếm từ khóa của ngách đó và xem ~6 video/từ để FYP học
đúng ngách; acc chưa config ngách thì lướt FYP thôi. Ngách chưa có từ
khóa riêng mà nhãn đủ dài (vd `dashcam`) thì dùng chính nhãn làm từ
khóa; nhãn quá ngắn (vd `A`, `B`) mà chưa có từ khóa thì lướt FYP thôi
— thêm từ khóa ở mục 8 là xong. Mở tìm kiếm không được trên giao diện
của bạn thì nó tự bỏ qua và nuôi bằng FYP, không crash phiên.

Nuôi 1 acc lẻ vẫn được qua dòng lệnh: `--nurture --account <user>` (mặc
định ~20–40 phút/phiên, chỉnh bằng `--nurture-min`, `--nurture-max`;
`--nurture-keywords`, `--nurture-likes` 0 = không like).

Cố tình KHÔNG tự động 2 việc: **comment** và **follow**. Comment máy
viết không ra ý thật và là tín hiệu spam dễ bị bắt nhất; follow cũng
vậy. 2 việc đó làm tay: 1–2 comment thật/ngày, 2–3 follow/ngày. Bật VPN
trước khi mở TikTok.

## Danh sách acc đã biết (để gợi ý đúng hơn)

Mỗi lần chạy mục 5 (Xem các acc), mục 6 (Đổi acc) hoặc mục 8 (Config
ngách) thành công, tool tự lưu danh sách acc vào file
`known_accounts.json` cạnh `phone_poster.py` (username + lần thấy cuối +
acc đang mở). Từ đó:

- Chạy `phone_poster.py --known-accounts` là in ra danh sách đã lưu,
  kèm ngách từng acc — không cần mở điện thoại.
- Mục 3, 4, 6, 10 trong bat in danh sách này ra trước khi hỏi acc, khỏi
  gõ mò username.
- Trong GUI, ô acc thành hộp chọn gợi ý từ danh sách đã lưu (vẫn gõ tay
  được acc mới); nút ↻ tải lại danh sách sau khi chạy "Xem các acc".

Lần đầu: đăng nhập đủ các acc vào app rồi chạy mục 5 một lần là danh
sách đầy đủ. Acc nào không còn đăng nhập trong app thì mục 8 sẽ báo
riêng, không tự xóa khỏi danh sách đã biết.

## ADB qua Wi-Fi (rút cáp)

Tool nói chuyện với điện thoại qua ADB nên rút cáp là mất kết nối, trừ khi
đã chuyển sang ADB qua Wi-Fi. Mở `run_poster.bat` → mục **7**: nó tự lấy IP
Wi-Fi của điện thoại (khi còn cắm cáp), chạy `tcpip 5555`, nối lại qua Wi-Fi
rồi báo — từ đó rút cáp được, các mục khác chạy bình thường (chỉ còn máy
Wi-Fi nên tool tự chọn nó; muốn chắc thì chạy kèm `--serial <IP>:5555`).
Cắm cáp lại là về USB, không cần làm gì thêm. Lưu ý: PC và điện thoại phải
cùng mạng Wi-Fi nhà (đừng bật kiểu này ở mạng công cộng); khởi động lại
điện thoại là mất chế độ tcpip, phải cắm cáp chạy lại mục 7; IP có thể đổi
khi router cấp lại nên đặt IP tĩnh cho điện thoại thì khỏi lo. Mục 7 tự
thử nối lại nhiều lần (máy yếu khởi động lại adbd chậm, thử 1 lần là
trượt oan); nếu nó báo máy 'unauthorized' thì kiểm tra màn hình điện
thoại và bấm Cho phép hộp thoại gỡ lỗi rồi chạy lại. Rút cáp xong mà mục
khác báo không nói chuyện được thì thường là link Wi-Fi rớt (màn hình tắt
lâu, MIUI tắt nền) — để màn hình sáng trong lúc chạy, hoặc cắm cáp chạy
lại mục 7.

## Điện thoại tắt màn hình / khóa màn hình

Trước mỗi lần mở TikTok, tool tự đánh thức màn hình + vuốt mở khóa (cú vuốt
mặc định của thư viện hay trượt trên màn Redmi nên có thêm cú vuốt dự phòng
theo đúng kích thước màn hình máy), rồi **chờ tối đa 10s để TikTok lên
foreground thật** mới làm tiếp — máy yếu khởi động lạnh lâu, check một phát
là đọc trượt. Mỗi lần thử đều in trạng thái quan sát được (màn hình bật/tắt,
app nào đang trước mặt). Nếu không được, nó dừng ngay và báo rõ từng trường
hợp thay vì bấm mò trên màn hình khóa:

- Báo `kẹt ở MÀN HÌNH KHÓA` → vẫn ở màn hình khóa vuốt: "không có mật khẩu"
  không có nghĩa là không có màn hình khóa — MIUI mặc định vẫn có màn hình
  khóa vuốt. Mở khóa tay rồi chạy lại; khi test nên tắt hẳn màn hình khóa
  cho khỏi kẹt. (Khóa PIN/mẫu hình/vân tay thì tool không tự qua được.)
- Báo `không nói chuyện được với điện thoại` → cáp lỏng, chưa bật USB
  debugging, hoặc MIUI đã tắt app agent ATX chạy nền: chạy lại menu 1, rồi
  vào Cài đặt > Pin cho app ATX chọn "Không giới hạn" và khóa nó trong đa
  nhiệm cho khỏi bị tắt.

## Lưu ý thật

- Lần đăng thật đầu tiên **chưa kiểm chứng được từ phía Muse** (không có
  điện thoại của bạn ở đây) — hãy chạy `--dry-run` trước và nhìn điện thoại
  đi hết các bước tới màn hình nhập caption; nếu kẹt ở bước nào, thư mục
  `errors/` cho biết chính xác bước đó.
- Giao diện TikTok đổi theo phiên bản app → thỉnh thoảng phải chỉnh lại nhãn
  nút trong `phone_poster.py` (đã hỗ trợ sẵn tiếng Anh + tiếng Việt).
- Script chọn **video mới nhất** trong thư viện của TikTok sau khi đẩy file —
  đừng mở thư viện/chụp thêm ảnh trong lúc nó chạy.
