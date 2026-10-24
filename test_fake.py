"""Test logic phone_poster bằng thiết bị giả — chạy: python test_fake.py"""
import sys, time, pathlib, tempfile, re
import xml.etree.ElementTree as ET
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
        self.hide_handle = 0      # số lần dump trang Hồ sơ đầu tiên chưa có @handle (giả lập header tải chậm)
        self.profile_dumps = 0
        self.video_idx = 0        # video FYP hiện tại: vuốt là đổi (để test vuốt có kiểm chứng)
        self.stuck_video = False  # True = vuốt không đổi video (giả lập kẹt 1 video)
        self.feed_author = None   # @ tác giả video đang xem ở FYP (nửa dưới màn hình)
        self._auto_i = 0          # đếm riêng cho hộp tự động (không tính hộp định sẵn)
        self._boxes = {           # nút điều hướng ở đúng vùng như TikTok thật
            "Home": {"left": 100, "top": 2200, "right": 260, "bottom": 2350},
            "Trang chủ": {"left": 100, "top": 2200, "right": 260, "bottom": 2350},
            "Profile": {"left": 820, "top": 2200, "right": 980, "bottom": 2350},
            "Hồ sơ": {"left": 820, "top": 2200, "right": 980, "bottom": 2350},
            "Search": {"left": 900, "top": 100, "right": 1000, "bottom": 200},
            "Tìm kiếm": {"left": 900, "top": 100, "right": 1000, "bottom": 200},
        }
    @property
    def info(self):
        return {"productName": "Fake", "screenOn": self.screen_on_flag,
                "currentPackageName": self.current_pkg}
    def bounds_for(self, key):
        if key not in self._boxes:
            i = self._auto_i
            self._auto_i += 1
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
                return
        # không trúng phần tử nào đã tìm trước đó: thử nút thật trong cây UI
        # (vd bấm tâm nút cha clickable của dòng acc trong bảng chuyển acc)
        try:
            root = ET.fromstring(self.dump_hierarchy())
            for node in root.iter("node"):
                if node.get("clickable") != "true":
                    continue
                m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]",
                             node.get("bounds") or "")
                if not m:
                    continue
                x1, y1, x2, y2 = map(int, m.groups())
                desc = (node.get("content-desc") or "").strip()
                if desc and x1 <= x <= x2 and y1 <= y <= y2:
                    self.el_click(desc)
                    return
        except Exception:
            pass
    def swipe(self, sx, sy, ex, ey, dur=0.5, duration=None):
        self.calls.append(("swipe", sx, sy, ex, ey,
                           dur if duration is None else duration))
        self._swipe_unlock(sy, ey)
        if not self.stuck_video:
            self.video_idx += 1
    def dump(self):
        return f"<hierarchy video='{self.video_idx}' current='{self.current}'/>"
    def screenshot(self, path): pathlib.Path(path).write_bytes(b"png")
    def send_keys(self, t, clear=False): self.captions.append(t)
    def press(self, key):
        self.calls.append(("press", key))
        if key == "back":
            self.sheet_open = False
    def double_click(self, x, y):
        self.calls.append(("double_click", x, y))
    def dump_hierarchy(self):
        if self.current_pkg != "com.zhiliaoapp.musically":
            return ('<hierarchy><node text="Vuốt lên để mở khóa" '
                    'bounds="[340,1200][740,1300]"/></hierarchy>')
        if self.sheet_open:  # bảng Switch account kiểu thật: dòng acc là nút
            # mang content-desc username TRẦN (không @), trong là TextView cùng chữ
            if self.one_account:
                return ('<hierarchy>'
                        '<node text="Switch account" content-desc="Switch account" bounds="[235,886][486,930]"/>'
                        '<node text="" content-desc="acc_one" bounds="[0,976][656,1120]" clickable="true"/>'
                        '<node text="acc_one" bounds="[168,1028][391,1068]"/>'
                        '<node text="Add account" bounds="[168,1316][362,1356]"/>'
                        '</hierarchy>')
            return ('<hierarchy>'
                    '<node text="Switch account" content-desc="Switch account" bounds="[235,886][486,930]"/>'
                    '<node text="" content-desc="acc_one" bounds="[0,976][656,1120]" clickable="true"/>'
                    '<node text="acc_one" bounds="[168,1028][391,1068]"/>'
                    '<node text="" content-desc="acc_two" bounds="[0,1120][656,1264]" clickable="true"/>'
                    '<node text="acc_two" bounds="[168,1172][444,1212]"/>'
                    '<node text="Add account" bounds="[168,1316][362,1356]"/>'
                    '</hierarchy>')
        if self.on_profile:  # trang Hồ sơ: tên hiển thị trên cùng + @username
            name = "Acc One" if self.current == "acc_one" else "Acc Two"
            self.profile_dumps += 1
            handle_row = '' if self.profile_dumps <= self.hide_handle else \
                f'<node text="@{self.current}" bounds="[440,480][640,540]"/>'
            return ('<hierarchy>'
                    f'<node text="{name}" bounds="[340,120][740,200]"/>'
                    f'{handle_row}'
                    '</hierarchy>')
        feed = (f'<node text="@{self.feed_author}" bounds="[800,1900][1000,1950]"/>'
                if self.feed_author else "")
        return ('<hierarchy><node clickable="true" bounds="[0,300][360,660]" class="android.widget.FrameLayout"/>'
                '<node clickable="true" bounds="[360,300][720,660]" class="android.widget.FrameLayout"/>'
                f'{feed}</hierarchy>')
    def __call__(self, **kw):
        key = kw.get("text") or kw.get("description") or kw.get("textContains") \
            or kw.get("descriptionContains") or kw.get("className") or "?"
        el = FakeEl(self, key)
        self._els[key] = el
        return el
    # -- behaviour --
    def el_exists(self, key):
        if key in ("Tìm kiếm", "Search"):
            return True  # nut tim kiem tren trang chu (de test duong tim kiem ngach)
        if key in ("Home", "Trang chủ"):
            return True  # tab Home (de test nurture khoi quay 3s tim Home)
        if key in ("Profile", "Hồ sơ"):
            return True
        if key in ("Acc One", "Acc Two"):
            return self.on_profile and not self.sheet_open
        if key in ("acc_one", "acc_two"):
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
        if key in ("acc_one", "acc_two") and self.sheet_open:
            self.current = key
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

# header trang Hồ sơ tải chậm: 2 lần dump đầu chưa có @handle, lần 3 mới có
devH = FakeDevice()
devH.hide_handle = 2
assert pp.current_account(devH) == "acc_one"
print("current_account OK (header tải chậm -> chờ + kéo làm mới rồi mới đọc được)")

# --- config acc -> ngach (ghi vao file tam, khong cham vao accounts.json that)
import os, json
cfg = tmp / "accounts-test.json"
os.environ["PHONE_POSTER_CONFIG"] = str(cfg)
assert pp.load_niches() == {}, pp.load_niches()
pp.save_niches({"@Acc_One": "A", "acc_two": " B "})
got = pp.load_niches()
assert got == {"acc_one": "A", "acc_two": "B"}, got
print("load/save_niches OK (chuan hoa username + cat khoang trang, file thieu -> {})")
assert pp.tag_for_account("acc_one", "") == "A"
assert pp.tag_for_account("acc_one", "rieng") == "rieng", "tag go tay phai thang config"
assert pp.tag_for_account("chua-co", "") == ""
assert pp.tag_for_account("", "") == ""
print("tag_for_account OK (ngach tu config khi khong co tag, tag tay thang)")
_old_argv = sys.argv
sys.argv = ["phone_poster.py", "--set-niche", "@Acc_Two", "dashcam"]
pp.main()
sys.argv = _old_argv
assert pp.load_niches()["acc_two"] == "dashcam", pp.load_niches()
print("--set-niche OK (ghi qua main, khong can dien thoai)")
del os.environ["PHONE_POSTER_CONFIG"]

# run_init: server rot 2 lan dau roi moi tra info -> phai thu lai, khong
# traceback; server chet han -> bao ro (khong traceback)
import types
class _FlakyDev:
    def __init__(self, fails):
        self.left = fails
    @property
    def info(self):
        if self.left > 0:
            self.left -= 1
            raise ConnectionError("Remote end closed connection without response")
        return {"productName": "olive", "sdkInt": 29,
                "displayWidth": 720, "displayHeight": 1520}
    def app_start(self, *a, **k):
        pass
_fake_u2 = types.ModuleType("uiautomator2")
_flaky = _FlakyDev(2)  # cung 1 may: rot 2 lan dau roi moi tra info
_fake_u2.connect = lambda serial="": _flaky
sys.modules["uiautomator2"] = _fake_u2
_real_run = pp.subprocess.run
pp.subprocess.run = lambda *a, **k: None
pp.run_init("")
print("run_init OK (server rot 2 lan dau -> thu lai roi moi OK, khong traceback)")
_flaky_dead = _FlakyDev(99)
_fake_u2.connect = lambda serial="": _flaky_dead
try:
    pp.run_init("")
    raise AssertionError("server chet han ma van OK la sai")
except pp.JobError as e:
    assert "menu 1" in str(e), e
    print("run_init OK (server chet han -> bao ro chay lai menu 1, khong traceback)")
pp.subprocess.run = _real_run
del sys.modules["uiautomator2"]

# --- nuoi tu dong: xem het video roi luot (budget that ngan, sleep da mock)
devN = FakeDevice()
s = pp.nurture_session(devN, min_s=0.05, max_s=0.1, keywords=[], like_cap=2)
assert s["watched"] >= 1, s
assert s["likes"] <= 2, s
assert any(c[0] == "swipe" for c in devN.calls), "nuoi phai luot feed"
assert sum(1 for c in devN.calls if c[0] == "double_click") == s["likes"]
print(f"nurture_session OK (FYP: xem {s['watched']} video, like {s['likes']} <= cap 2)")
devN2 = FakeDevice()
s2 = pp.nurture_session(devN2, min_s=0.05, max_s=0.1,
                        keywords=["dashcam"], like_cap=0)
assert s2["watched"] >= 6, s2  # 6 video tu ket qua tim kiem, chua tinh FYP
assert s2["likes"] == 0, s2
assert ("press", "enter") in devN2.calls, "phai go tu khoa roi Enter de tim kiem"
assert not any(c[0] == "double_click" for c in devN2.calls), "like_cap=0 thi khong like"
print(f"nurture_session OK (tim kiem ngach: xem {s2['watched']} video, khong like)")
# --- run_wifi: connect rot 2 lan dau (may yeu khoi dong lai adbd cham) -> thu
# lai, lan 3 moi thay may; may unauthorized -> bao rieng, dung ngay
assert pp._adb_devices("List of devices attached\nUSB123\tdevice\n"
                       "192.168.1.50:5555\tunauthorized\nX\t offline\n") == \
    {"USB123": "device", "192.168.1.50:5555": "unauthorized", "X": "offline"}
print("_adb_devices OK (parse dung trang thai device/unauthorized/offline)")
import shutil as _shutil_mod, subprocess as _sp_mod
_calls = {"connect": 0}
class _R:
    def __init__(self, out): self.stdout = out
def _fake_adb(argv, capture_output=False, text=False, timeout=None, check=False):
    if argv[1] == "devices":
        if _calls["connect"] >= 3:
            return _R("List of devices attached\n192.168.1.50:5555\tdevice\n")
        return _R("List of devices attached\nUSB123\tdevice\n")
    if argv[1] == "-s":
        if "tcpip" in argv:
            return _R("")
        return _R("    inet 192.168.1.50/24 brd 192.168.1.255 scope global wlan0\n")
    if argv[1] == "connect":
        _calls["connect"] += 1
        if _calls["connect"] >= 3:
            return _R("connected to 192.168.1.50:5555")
        return _R("failed to connect to 192.168.1.50:5555")
    return _R("")
_real_which = _shutil_mod.which
_shutil_mod.which = lambda name: "/fake/adb" if name == "adb" else _real_which(name)
_real_sp_run = _sp_mod.run
_sp_mod.run = _fake_adb
_fake_u2w = types.ModuleType("uiautomator2")
class _WifiDev:
    @property
    def info(self): return {"productName": "olive"}
_fake_u2w.connect = lambda serial="": _WifiDev()
sys.modules["uiautomator2"] = _fake_u2w
pp.run_wifi()
assert _calls["connect"] == 3, _calls
print("run_wifi OK (connect rot 2 lan dau -> thu lai, lan 3 moi thay may device)")
def _fake_adb_unauth(argv, capture_output=False, text=False, timeout=None, check=False):
    if argv[1] == "devices":
        if _calls["connect"] >= 1:
            return _R("List of devices attached\n192.168.1.50:5555\tunauthorized\n")
        return _R("List of devices attached\nUSB123\tdevice\n")
    if argv[1] == "-s":
        if "tcpip" in argv:
            return _R("")
        return _R("    inet 192.168.1.50/24 brd 192.168.1.255 scope global wlan0\n")
    if argv[1] == "connect":
        _calls["connect"] += 1
        return _R("connected to 192.168.1.50:5555")
    return _R("")
_calls["connect"] = 0
_sp_mod.run = _fake_adb_unauth
pp.run_wifi()
assert _calls["connect"] == 1, _calls
print("run_wifi OK (may unauthorized -> bao rieng, dung ngay lan 1)")
_sp_mod.run = _real_sp_run
_shutil_mod.which = _real_which
del sys.modules["uiautomator2"]

# --- vuot manh: phai dai (0.80-0.88h -> 0.12-0.20h) va nhanh (0.15-0.35s)
devS = FakeDevice()
pp._swipe_next(devS)
_, sx, sy, ex, ey, dur = [c for c in devS.calls if c[0] == "swipe"][-1]
assert sy >= 0.80 * 2400 and ey <= 0.20 * 2400, (sy, ey)
assert 0.15 <= dur <= 0.35, dur
print(f"_swipe_next OK (vuot {sy}->{ey} trong {dur:.2f}s, du dai + du nhanh)")

# --- danh sach acc da biet: ghi nhan + goi y
known_f = tmp / "known-test.json"
os.environ["PHONE_POSTER_KNOWN"] = str(known_f)
assert pp.load_known() == {}
pp.record_known(["@Acc_One", "acc_two"], "acc_one")
got = pp.load_known()
assert set(got) == {"acc_one", "acc_two"}, got
assert got["acc_one"]["current"] is True and got["acc_two"]["current"] is False, got
assert got["acc_one"]["last_seen"], got
pp.record_known(["acc_two"], "acc_two")  # chi thay acc_two: acc_one giu last_seen, mat current
got = pp.load_known()
assert got["acc_one"]["current"] is False and got["acc_one"]["last_seen"], got
assert got["acc_two"]["current"] is True, got
print("record_known OK (chuan hoa, 1 acc current, giu last_seen acc cu)")
_old_argv = sys.argv
sys.argv = ["phone_poster.py", "--known-accounts"]
pp.main()  # khong can dien thoai, chi in danh sach da luu
sys.argv = _old_argv
print("--known-accounts OK (in duoc ma khong can mo dien thoai)")
del os.environ["PHONE_POSTER_KNOWN"]

# --- tu khoa ngach (master setting cho nuoi tat ca)
kw_f = tmp / "niche-kw-test.json"
os.environ["PHONE_POSTER_NICHE_KW"] = str(kw_f)
assert pp.keywords_for_niche("") == [] and pp.keywords_for_niche("B") == []
assert pp.keywords_for_niche("dashcam") == ["dashcam"]  # nhan dai -> tu la tu khoa
_old_argv = sys.argv
sys.argv = ["phone_poster.py", "--set-niche-keywords", "A", "loyalty test, street fight"]
pp.main()
sys.argv = _old_argv
assert pp.load_niche_keywords() == {"A": ["loyalty test", "street fight"]}
assert pp.keywords_for_niche("A") == ["loyalty test", "street fight"]
print("keywords_for_niche + --set-niche-keywords OK (entry rieng thang nhan)")
del os.environ["PHONE_POSTER_NICHE_KW"]

# --- config-niches 2 pha qua main (mock input + may gia): gan ngach tung
# acc roi hoi tu khoa tung ngach
import builtins
cfg2 = tmp / "accounts2.json"
kw2 = tmp / "niche-kw2.json"
known2 = tmp / "known2.json"
os.environ["PHONE_POSTER_CONFIG"] = str(cfg2)
os.environ["PHONE_POSTER_NICHE_KW"] = str(kw2)
os.environ["PHONE_POSTER_KNOWN"] = str(known2)
_fake_u2c = types.ModuleType("uiautomator2")
_fake_u2c.connect = lambda serial="": FakeDevice()
sys.modules["uiautomator2"] = _fake_u2c
_inputs = iter(["A", "dashcam", "loyalty test, street fight", "dashcam, road rage"])
_real_input = builtins.input
builtins.input = lambda prompt="": next(_inputs)
_old_argv = sys.argv
sys.argv = ["phone_poster.py", "--config-niches", "--dir", str(tmp)]
pp.main()
sys.argv = _old_argv
builtins.input = _real_input
del sys.modules["uiautomator2"]
assert pp.load_niches() == {"acc_one": "A", "acc_two": "dashcam"}, pp.load_niches()
assert pp.load_niche_keywords() == {"A": ["loyalty test", "street fight"],
                                    "dashcam": ["dashcam", "road rage"]}, pp.load_niche_keywords()
print("config-niches OK (2 pha: gan ngach + tu khoa tung ngach)")
del os.environ["PHONE_POSTER_CONFIG"]
del os.environ["PHONE_POSTER_NICHE_KW"]
del os.environ["PHONE_POSTER_KNOWN"]

# --- nurture_all: acc_one ngach A (co tu khoa -> tim kiem), acc_two chua
# config ngach (chi luot FYP); moi acc budget nho de test nhanh
cfg3 = tmp / "accounts3.json"
kw3 = tmp / "niche-kw3.json"
os.environ["PHONE_POSTER_CONFIG"] = str(cfg3)
os.environ["PHONE_POSTER_NICHE_KW"] = str(kw3)
pp.save_niches({"acc_one": "A"})
pp.save_niche_keywords({"A": ["loyalty test"]})
devA = FakeDevice()
res = pp.nurture_all(devA, tmp, like_cap=0, min_s=0.05, max_s=0.1)
assert [r["user"] for r in res] == ["acc_one", "acc_two"], res
assert all(r["status"] == "done" for r in res), res
assert devA.current == "acc_two", devA.current
enters = sum(1 for c in devA.calls if c == ("press", "enter"))
assert enters == 1, enters  # chi acc co ngach moi tim kiem; acc chua config thi khong
assert not any(c[0] == "double_click" for c in devA.calls)
print("nurture_all OK (2 acc: 1 tim kiem theo ngach, 1 luot FYP; doi acc co xac nhan)")
del os.environ["PHONE_POSTER_CONFIG"]
del os.environ["PHONE_POSTER_NICHE_KW"]

# --- vuot co kiem chung: qua video -> True + 1 lan vuot; ket -> False + 4 lan (3 fling + 1 keo cham)
devV = FakeDevice()
assert pp._swipe_next_verified(devV) is True
assert sum(1 for c in devV.calls if c[0] == "swipe") == 1
devS = FakeDevice()
devS.stuck_video = True
assert pp._swipe_next_verified(devS) is False
assert sum(1 for c in devS.calls if c[0] == "swipe") == 4, devS.calls
print("swipe_verified OK (qua video 1 lan; ket thi 3 fling + 1 keo cham roi bao loi)")

# --- chan bam phan tu qua lon + chi bam nut dung vung
devT = FakeDevice()
devT._boxes["BIG"] = {"left": 0, "top": 0, "right": 1080, "bottom": 2400}
assert pp._tap_human(devT, FakeEl(devT, "BIG")) is False
assert not any(c[0] == "tap" for c in devT.calls), devT.calls
assert pp._try_click(devT, ["Home"], timeout=1.0, region="bottom") is True
devT2 = FakeDevice()
devT2._boxes["Home"] = {"left": 100, "top": 1000, "right": 300, "bottom": 1200}
assert pp._try_click(devT2, ["Home"], timeout=0.5, region="bottom") is False
print("tap guards OK (phan tu to = khong bam; Home giua man hinh khong tinh la tab duoi)")

# --- lay profile: @ tac gia video o nua duoi man hinh khong duoc tinh la acc dang dung
devF = FakeDevice()
devF.feed_author = "someauthor"
assert pp._own_profile_handle(devF) is None
assert pp.current_account(devF) == "acc_one"
print("profile_handle OK (@ tac gia video khong nhan nham thanh acc dang dung)")

# --- doi acc: bam tam nut cha clickable cua dong acc (khong bam TextView)
devS = FakeDevice()
assert pp.current_account(devS) == "acc_one"
assert pp._open_switcher(devS) is True
assert pp._tap_sheet_row(devS, "acc_two") is True
assert devS.current == "acc_two" and not devS.sheet_open
print("tap_sheet_row OK (bam tam nut cha clickable cua dong acc)")

# --- like chi sau khi qua video moi + log realtime tung video
import io, contextlib
devW = FakeDevice()
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    ld, liked = pp._watch_one(devW, 8, 0, idx=1)
assert "video #1" in buf.getvalue(), buf.getvalue()
devW2 = FakeDevice()
devW2.stuck_video = True
ld2, liked2 = pp._watch_one(devW2, 8, 0, idx=1)
assert (ld2, liked2) == (0, False), (ld2, liked2)
assert not any(c[0] == "double_click" for c in devW2.calls), devW2.calls
print("watch_one OK (log realtime video #N; ket video thi khong like mu)")
time.sleep = _real_sleep
print("ALL FAKE-DEVICE TESTS PASSED")
