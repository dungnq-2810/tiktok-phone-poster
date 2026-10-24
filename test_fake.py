"""Test logic phone_poster bằng thiết bị giả — chạy: python test_fake.py"""
import sys, time, pathlib, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).parent))
_real_sleep = time.sleep
time.sleep = lambda s: None  # test chạy tức thì
import phone_poster as pp

# ---------------------------------------------------------------- fake ----
class FakeEl:
    def __init__(self, dev, key):
        self.dev, self.key = dev, key
    @property
    def info(self):
        return {"bounds": self.dev.bounds_for(self.key)}
    def exists(self, timeout=0):
        return self.dev.el_exists(self.key)
    def click(self):
        self.dev.el_click(self.key)
    def set_text(self, t):
        self.dev.captions.append(t)

class FakeDevice:
    def __init__(self):
        self.calls = []
        self.captions = []
        self._els = {}            # key -> FakeEl đã tạo (để ánh xạ tap tọa độ)
        self.next_left = 2          # 2 màn hình biên tập có nút Tiếp
        self.post_clicked = False
        self.pushed = []
        # trạng thái acc: 2 acc đã đăng nhập trong cùng app, đang mở acc_one
        self.current = "acc_one"
        self.on_profile = False
        self.sheet_open = False
        # trạng thái màn hình: screen_on_flag + keyguard ("none"/"slide"/"pin")
        self.screen_on_flag = True
        self.keyguard = "none"
        self.current_pkg = ""
        self.one_account = False  # app chỉ đăng nhập 1 acc (sheet chỉ có acc_one)
        self._boxes = {}            # mỗi phần tử một khung tọa độ riêng (như máy thật)
    @property
    def info(self):
        return {"productName": "Fake", "screenOn": self.screen_on_flag,
                "currentPackageName": self.current_pkg}
    def bounds_for(self, key):
        if key not in self._boxes:
            i = len(self._boxes)
            self._boxes[key] = {"left": 100, "top": 200 + i * 300,
                                "right": 300, "bottom": 400 + i * 300}
        return self._boxes[key]
    # -- u2 surface --
    def shell(self, cmd): self.calls.append(("shell", tuple(cmd)))
    def push(self, local, remote): self.pushed.append((local, remote))
    def screen_on(self): self.screen_on_flag = True
    def unlock(self):
        pass  # giả lập đúng máy thật: unlock() mặc định hay vuốt trượt
    def _swipe_unlock(self, sy, ey):
        if self.keyguard == "slide" and sy > ey:
            self.keyguard = "none"
    def app_start(self, pkg, stop=False):
        self.calls.append(("app_start", pkg))
        # màn hình tắt hoặc còn khóa: app chạy sau màn hình khóa, không lên foreground
        if self.screen_on_flag and self.keyguard == "none":
            self.current_pkg = pkg
        else:
            self.current_pkg = "com.android.systemui"
    def window_size(self): return (1080, 2400)
    def click(self, x, y):
        self.calls.append(("tap", x, y))
        # tap tọa độ rơi vào khung phần tử nào đang hiện thì coi như bấm phần tử đó
        for key in reversed(list(self._els)):
            el = self._els[key]
            b = el.info["bounds"]
            if not el.exists():
                continue
            if b["left"] <= x <= b["right"] and b["top"] <= y <= b["bottom"]:
                self.el_click(key)
                break
    def swipe(self, sx, sy, ex, ey, dur=0.5, duration=None):
        self.calls.append(("swipe", sx, sy, ex, ey))
        self._swipe_unlock(sy, ey)
    def screenshot(self, path): pathlib.Path(path).write_bytes(b"png")
    def send_keys(self, t, clear=False): self.captions.append(t)
    def press(self, key):
        self.calls.append(("press", key))
        if key == "back":
            self.sheet_open = False
    def dump_hierarchy(self):
        if self.current_pkg != "com.zhiliaoapp.musically":
            return ('<hierarchy><node text="Vuốt lên để mở khóa" '
                    'bounds="[340,1200][740,1300]"/></hierarchy>')
        if self.sheet_open:  # bảng chuyển tài khoản: các dòng acc + Thêm tài khoản
            if self.one_account:
                return ('<hierarchy>'
                        '<node text="Acc One" bounds="[300,700][700,780]"/>'
                        '<node text="@acc_one" bounds="[300,780][700,840]"/>'
                        '<node text="Add account" bounds="[300,1100][700,1180]"/>'
                        '</hierarchy>')
            return ('<hierarchy>'
                    '<node text="Acc One" bounds="[300,700][700,780]"/>'
                    '<node text="@acc_one" bounds="[300,780][700,840]"/>'
                    '<node text="Acc Two" bounds="[300,900][700,980]"/>'
                    '<node text="@acc_two" bounds="[300,980][700,1040]"/>'
                    '<node text="Add account" bounds="[300,1100][700,1180]"/>'
                    '</hierarchy>')
        if self.on_profile:  # trang Hồ sơ: tên hiển thị trên cùng + @username
            name = "Acc One" if self.current == "acc_one" else "Acc Two"
            return ('<hierarchy>'
                    f'<node text="{name}" bounds="[340,120][740,200]"/>'
                    f'<node text="@{self.current}" bounds="[440,480][640,540]"/>'
                    '</hierarchy>')
        return ('<hierarchy><node clickable="true" bounds="[0,300][360,660]" class="android.widget.FrameLayout"/>'
                '<node clickable="true" bounds="[360,300][720,660]" class="android.widget.FrameLayout"/></hierarchy>')
    def __call__(self, **kw):
        key = kw.get("text") or kw.get("description") or kw.get("textContains") \
            or kw.get("descriptionContains") or kw.get("className") or "?"
        el = FakeEl(self, key)
        self._els[key] = el
        return el
    # -- behaviour --
    def el_exists(self, key):
        if key in ("Profile", "Hồ sơ"):
            return True
        if key in ("Acc One", "Acc Two"):
            return self.on_profile and not self.sheet_open
        if key in ("@acc_one", "@acc_two"):
            return self.sheet_open
        if key == "Add account":
            return self.sheet_open
        if key in ("Create", "Tạo", "Upload", "Tải lên"):
            return True
        if key in ("Next", "Tiếp", "Tiếp theo"):
            return self.next_left > 0
        if key in ("Add a description", "Thêm mô tả"):
            return not self.post_clicked  # đăng xong là rời màn hình đăng
        if key in ("Post", "Đăng"):
            return not self.post_clicked
        if key == "android.widget.EditText":
            return not self.post_clicked
        return False  # popup, lỗi tải lên...: không có
    def el_click(self, key):
        self.calls.append(("click", key))
        if key in ("Profile", "Hồ sơ"):
            self.on_profile = True
        if key in ("Acc One", "Acc Two") and self.on_profile:
            self.sheet_open = True
        if key in ("@acc_one", "@acc_two") and self.sheet_open:
            self.current = key.lstrip("@")
            self.sheet_open = False
            self.on_profile = False
        if key in ("Next", "Tiếp", "Tiếp theo"):
            self.next_left -= 1
        if key in ("Post", "Đăng"):
            self.post_clicked = True

# ---------------------------------------------------------------- tests ----
tmp = pathlib.Path(tempfile.mkdtemp())
q = tmp / "queue"; q.mkdir()
(q / "a.mp4").write_bytes(b"v"); (q / "a.txt").write_text("caption A #a", encoding="utf-8")
s1 = q / "story_1"; s1.mkdir()
(s1 / "b.mp4").write_bytes(b"v"); (s1 / "b_caption.txt").write_text("caption B #b", encoding="utf-8")
s2 = q / "story_2"; s2.mkdir()
(s2 / "c.mp4").write_bytes(b"v"); (s2 / "whatever.txt").write_text("caption C #c", encoding="utf-8")
done = q / "_done"; done.mkdir(); (done / "old.mp4").write_bytes(b"v")

jobs = pp.find_jobs(q)
assert len(jobs) == 3, jobs
caps = {j["video"].name: j["caption"] for j in jobs}
assert caps == {"a.mp4": "caption A #a", "b.mp4": "caption B #b", "c.mp4": "caption C #c"}, caps
print("find_jobs OK:", caps)

job = jobs[0]
dev = FakeDevice()
r = pp.post_one(dev, job, q, dry_run=True)
assert r == "dry-run" and not dev.post_clicked, "dry-run không được bấm Đăng"
assert dev.pushed and dev.pushed[0][1].endswith("/a.mp4"), dev.pushed
assert "".join(dev.captions) == "caption A #a", dev.captions
assert len(dev.captions) > 1, "caption phải được gõ từng cụm, không dán một phát"
assert any(c[0] == "tap" for c in dev.calls), "phải có thao tác chọn video trong thư viện"
print("post_one DRY-RUN OK (đẩy file, chọn video, gõ caption từng cụm, dừng trước Đăng)")

dev2 = FakeDevice()
r = pp.post_one(dev2, job, q, dry_run=False)
assert r == "posted" and dev2.post_clicked
assert any(c[0] == "shell" and "rm" in c[1] for c in dev2.calls), "đăng xong phải xóa file trên máy"
print("post_one POST OK (bấm Đăng, dọn file trên điện thoại)")

pp._move_job(q, job, "_done")
assert (q / "_done" / "a.mp4").exists() and (q / "_done" / "a.txt").exists()
print("_move_job OK")

# bấm rải trong khung nút, không bấm đúng tâm
dev3 = FakeDevice()
el = dev3(text="Upload")
for _ in range(20):
    assert pp._tap_human(dev3, el)
taps = [(c[1], c[2]) for c in dev3.calls if c[0] == "tap"]
assert len(taps) == 20 and len(set(taps)) > 1, "bấm phải rải ngẫu nhiên trong nút"
assert all(140 <= x <= 260 and 240 <= y <= 360 for x, y in taps), taps
print("_tap_human OK (20 cú bấm rải trong khung nút, không trùng tâm)")

# lướt feed khởi động
dev4 = FakeDevice()
pp.warmup_feed(dev4, swipes=3)
sw = [c for c in dev4.calls if c[0] == "swipe"]
assert len(sw) == 3, sw
assert all(432 <= c[1] <= 648 for c in sw), sw  # vuốt ở dải giữa màn hình
print("warmup_feed OK (vuốt 3 video)")

# nhãn acc tách thư mục _done/_failed riêng
pp._move_job(q, jobs[1], "_done", tag="irl")
assert (q / "_done-irl" / "b.mp4").exists(), list((q / "_done-irl").iterdir())
print("_move_job tag OK")

# ---- acc: đọc acc hiện tại, liệt kê acc, đổi acc, kiểm tra đúng acc ----
devA = FakeDevice()
assert pp.current_account(devA) == "acc_one"
print("current_account OK (đọc @username ở trang Hồ sơ)")

cur, all_acc = pp.list_logged_in_accounts(devA)
assert cur == "acc_one" and all_acc == ["acc_one", "acc_two"], (cur, all_acc)
print("list_logged_in_accounts OK:", all_acc)

got = pp.switch_account(devA, "acc_two")
assert got == "acc_two" and devA.current == "acc_two"
assert pp.current_account(devA) == "acc_two"
print("switch_account OK (đổi + xác nhận lại ở trang Hồ sơ)")

got = pp.ensure_account(devA, "@ACC_ONE")  # chịu cả @ và chữ hoa
assert got == "acc_one" and devA.current == "acc_one"
got = pp.ensure_account(devA, "acc_one")   # đã đúng acc: không đổi nữa
assert got == "acc_one"
print("ensure_account OK (sai thì tự đổi, đúng thì giữ nguyên)")

try:
    pp.switch_account(devA, "acc_three")
    raise AssertionError("đổi sang acc không tồn tại phải báo lỗi")
except pp.JobError:
    print("switch_account OK (acc không có trong máy -> JobError, không đăng bừa)")

# ---- màn hình tắt/khóa: mở TikTok phải xác nhận foreground, không bấm mò ----
devL = FakeDevice()
devL.screen_on_flag = False
devL.keyguard = "slide"   # khóa trượt: đánh thức + vuốt là qua
pp._open_tiktok(devL)
assert devL.screen_on_flag and devL.current_pkg == "com.zhiliaoapp.musically"
print("_open_tiktok OK (màn hình tắt + khóa trượt -> tự đánh thức, mở được TikTok)")

devP = FakeDevice()
devP.keyguard = "pin"     # khóa PIN: tool không tự qua được
try:
    pp._open_tiktok(devP)
    raise AssertionError("khóa PIN mà vẫn mở được là sai")
except pp.JobError as e:
    assert "MÀN HÌNH KHÓA" in str(e), e
    print("_open_tiktok OK (khóa PIN -> báo rõ KHÓA màn hình, dừng thay vì bấm mò)")

devP2 = FakeDevice()
devP2.keyguard = "pin"
try:
    pp.list_logged_in_accounts(devP2)
    raise AssertionError("khóa PIN mà vẫn lấy được acc là sai")
except pp.JobError as e:
    assert "MÀN HÌNH KHÓA" in str(e), e
    print("list_logged_in_accounts OK (điện thoại khóa -> lỗi rõ KHÓA màn hình, "
          "không còn lỗi mơ hồ 'không đọc được @username')")

# app chỉ có 1 acc: bảng mở được nhưng chỉ thấy acc đang dùng (không crash,
# không báo thiếu sai — đó là trạng thái thật của app này)
dev1 = FakeDevice()
dev1.one_account = True
cur1, acc1 = pp.list_logged_in_accounts(dev1)
assert cur1 == "acc_one" and acc1 == ["acc_one"], (cur1, acc1)
print("list_logged_in_accounts OK (app chỉ có 1 acc -> trả đúng [acc đang dùng])")
time.sleep = _real_sleep
print("ALL FAKE-DEVICE TESTS PASSED")
