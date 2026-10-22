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
        self.next_left = 2          # 2 màn hình biên tập có nút Tiếp
        self.post_clicked = False
        self.pushed = []
    # -- u2 surface --
    def shell(self, cmd): self.calls.append(("shell", tuple(cmd)))
    def push(self, local, remote): self.pushed.append((local, remote))
    def screen_on(self): pass
    def unlock(self): pass
    def app_start(self, pkg, stop=False): self.calls.append(("app_start", pkg))
    def window_size(self): return (1080, 2400)
    def click(self, x, y): self.calls.append(("tap", x, y))
    def screenshot(self, path): pathlib.Path(path).write_bytes(b"png")
    def send_keys(self, t, clear=False): self.captions.append(t)
    def dump_hierarchy(self):
        return ('<hierarchy><node clickable="true" bounds="[0,300][360,660]" class="android.widget.FrameLayout"/>'
                '<node clickable="true" bounds="[360,300][720,660]" class="android.widget.FrameLayout"/></hierarchy>')
    def __call__(self, **kw):
        key = kw.get("text") or kw.get("description") or kw.get("textContains") \
            or kw.get("descriptionContains") or kw.get("className") or "?"
        return FakeEl(self, key)
    # -- behaviour --
    def el_exists(self, key):
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
assert dev.captions == ["caption A #a"], dev.captions
assert any(c[0] == "tap" for c in dev.calls), "phải có thao tác chọn video trong thư viện"
print("post_one DRY-RUN OK (đẩy file, chọn video, nhập caption, dừng trước Đăng)")

dev2 = FakeDevice()
r = pp.post_one(dev2, job, q, dry_run=False)
assert r == "posted" and dev2.post_clicked
assert any(c[0] == "shell" and "rm" in c[1] for c in dev2.calls), "đăng xong phải xóa file trên máy"
print("post_one POST OK (bấm Đăng, dọn file trên điện thoại)")

pp._move_job(q, job, "_done")
assert (q / "_done" / "a.mp4").exists() and (q / "_done" / "a.txt").exists()
print("_move_job OK")
time.sleep = _real_sleep
print("ALL FAKE-DEVICE TESTS PASSED")
