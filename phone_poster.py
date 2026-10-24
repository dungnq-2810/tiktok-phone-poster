#!/usr/bin/env python3
"""Tự động chuyển video sang điện thoại Android và đăng lên TikTok.

Luồng: quét một thư mục hàng đợi trên PC -> với mỗi video: đẩy file sang
điện thoại qua ADB -> mở app TikTok, bấm đăng như người dùng thật
(uiautomator2) -> dán caption từ file .txt đi kèm -> bấm Đăng.

Ghép cặp video/caption: video `x.mp4` lấy caption từ `x.txt` hoặc
`x_caption.txt` trong CÙNG thư mục; quét đệ quy nên trỏ vào thư mục xuất
của clipgen (mỗi story một folder con chứa video + caption) là chạy luôn.

    python phone_poster.py --init            # cài agent lên điện thoại (USB, 1 lần)
    python phone_poster.py --wifi            # chuyển sang ADB qua Wi-Fi để rút cáp
    python phone_poster.py --nurture --account username --nurture-keywords "dashcam,road rage"  # nuôi 1 acc ~20-40 phút: xem hết video rồi lướt
    python phone_poster.py --nurture-all  # nuôi TẤT CẢ acc: mỗi acc ~10 phút rồi đổi, theo ngách đã config (master)
    python phone_poster.py --list-accounts   # mở TikTok, liệt kê các acc đã đăng nhập trong app (+ ngách đã config)
    python phone_poster.py --config-niches   # lấy danh sách acc trước, rồi hỏi ngách từng acc và lưu vào accounts.json
    python phone_poster.py --set-niche username B  # gán nhanh 1 acc vào ngách B
    python phone_poster.py --switch-to username   # đổi sang acc khác (đã đăng nhập sẵn) để test
    python phone_poster.py --dir D:\\outbox --dry-run   # chạy thử, dừng trước nút Đăng
    python phone_poster.py --dir D:\\outbox             # đăng thật
    python phone_poster.py --dir D:\\outbox --account username  # đăng, bắt buộc đúng acc này:
                                             # tool tự đổi acc + kiểm tra trước mỗi lần đăng
    # Test 2 mảng trên 2 acc: mỗi acc một thư mục con + nhãn riêng
    python phone_poster.py --dir D:\\outbox\\irl --account-tag irl
    python phone_poster.py --dir D:\\outbox\\court --account-tag court

Né phát hiện tự động hóa: bấm vào điểm ngẫu nhiên trong nút (không bấm đúng
tâm), gõ caption từng cụm ký tự như tay người (không dán), và lướt feed 1–2
phút trước khi đăng. Tắt lướt feed bằng --no-warmup khi cần.

Việc đăng chỉ thực sự kiểm chứng được trên máy + điện thoại của bạn:
giao diện TikTok thay đổi theo phiên bản app, nên lần đầu hãy chạy
--dry-run và nhìn điện thoại làm tới màn hình nhập caption.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

VERSION = "20261024-18"  # in ra đầu mỗi lần chạy để biết chắc đang chạy bản nào

TIKTOK_PKG = "com.zhiliaoapp.musically"
PHONE_DIR = "/sdcard/DCIM/TikTokAuto"
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm"}

# Nhãn nút theo ngôn ngữ giao diện (Anh / Việt) — thử lần lượt.
TXT_CREATE = ["Create", "Tạo", "Create video", "Tạo video"]
TXT_UPLOAD = ["Upload", "Tải lên"]
TXT_NEXT = ["Next", "Tiếp", "Tiếp theo"]
TXT_POST = ["Post", "Đăng"]
TXT_CAPTION_HINT = ["Add a description", "Thêm mô tả", "Describe your video",
                    "Mô tả video", "Add description"]
TXT_DISMISS = ["Not now", "Để sau", "Skip", "Bỏ qua", "Later", "Lúc khác",
               "Allow", "Cho phép", "OK"]
TXT_UPLOAD_ERROR = ["Couldn't upload", "Không thể tải lên", "Upload failed",
                    "Tải lên thất bại", "Try again", "Thử lại"]
TXT_HOME = ["Home", "Trang chủ"]
TXT_SEARCH = ["Tìm kiếm", "Search"]
TXT_PROFILE = ["Profile", "Hồ sơ"]
TXT_ADD_ACCOUNT = ["Add account", "Thêm tài khoản"]
TXT_VERIFY_BLOCK = ["Verify your identity", "Enter the code sent",
                    "Xác minh danh tính", "Nhập mã xác minh",
                    "unusual activity", "Hoạt động bất thường"]
TXT_LOGIN = ["Log in", "Đăng nhập", "Sign up", "Đăng ký"]


class JobError(Exception):
    """Một bước trong quy trình đăng thất bại (đã chụp màn hình để xem)."""


def jitter(lo=1.2, hi=3.2):
    time.sleep(random.uniform(lo, hi))


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------- queue ----
def find_jobs(root: Path):
    """Trả về list dict {video, caption_file, caption} theo thứ tự cũ->mới."""
    jobs = []
    for dirpath, _dirs, files in os.walk(root):
        folder = Path(dirpath)
        if folder.name in ("_done", "_failed"):
            continue
        for name in files:
            if Path(name).suffix.lower() not in VIDEO_EXTS:
                continue
            video = folder / name
            stem = video.stem
            cap_file = None
            for cand in (folder / f"{stem}.txt", folder / f"{stem}_caption.txt"):
                if cand.exists():
                    cap_file = cand
                    break
            if cap_file is None:  # video nằm một mình trong folder con: lấy .txt đầu tiên
                txts = sorted(folder.glob("*.txt"))
                vids = [f for f in folder.iterdir()
                        if f.suffix.lower() in VIDEO_EXTS]
                if len(vids) == 1 and txts:
                    cap_file = txts[0]
            caption = ""
            if cap_file is not None:
                caption = cap_file.read_text(encoding="utf-8").strip()
            jobs.append({"video": video, "caption_file": cap_file,
                         "caption": caption})
    jobs.sort(key=lambda j: j["video"].stat().st_mtime)
    return jobs


def _move_job(root: Path, job: dict, bucket: str, tag: str = ""):
    dest_dir = root / (f"{bucket}-{tag}" if tag else bucket)
    dest_dir.mkdir(exist_ok=True)
    for f in (job["video"], job["caption_file"]):
        if f is not None and f.exists():
            shutil.move(str(f), str(dest_dir / f.name))


# ------------------------------------------------------------- UI helpers ----
def _tap_human(d, el, label=""):
    """Bấm vào một điểm ngẫu nhiên BÊN TRONG khung phần tử (né bấm đúng tâm
    như máy — TikTok chấm điểm hành vi bấm trúng y hệt một tọa độ mỗi lần).
    KHÔNG bấm phần tử quá lớn (>40% màn hình): đó là container/caption chứ
    không phải nút — bấm bừa vào đó là đúng bệnh 'ấn lung tung' (dính
    hashtag/mention trong caption rồi mở trang linh tinh)."""
    try:
        b = el.info.get("bounds") or {}
        l, t, r, btm = b["left"], b["top"], b["right"], b["bottom"]
        if r - l < 8 or btm - t < 8:
            raise ValueError("bounds quá nhỏ")
        w, h = d.window_size()
        if (r - l) * (btm - t) > 0.40 * w * h:
            log(f"   (bỏ qua phần tử quá lớn {r - l}x{btm - t} — không bấm bừa)")
            return False
        mx, my = max(3, (r - l) // 5), max(3, (btm - t) // 5)
        x = random.randint(l + mx, r - mx)
        y = random.randint(t + my, btm - my)
        d.click(x, y)
        if label:
            log(f"   bấm {label} @({x},{y}) [{r - l}x{btm - t}]")
        return True
    except Exception:
        try:
            el.click()  # dự phòng khi không đọc được bounds
            return True
        except Exception:
            return False


def _matches(d, kwargs):
    """Yield mọi phần tử khớp selector: trên uiautomator2 thật thì duyệt
    theo chỉ số (để bỏ qua caption trùng chữ mà lấy đúng nút); trên thiết
    bị giả (không hỗ trợ duyệt) thì chỉ yield phần tử duy nhất."""
    base = d(**kwargs)
    try:
        n = base.count
    except Exception:
        yield base
        return
    for i in range(n):
        try:
            yield base[i]
        except Exception:
            continue


def _in_region(bounds, region, w, h):
    """Phần tử có nằm đúng vùng không: nút Home/Profile ở thanh dưới,
    nút Search ở trên. Không có region thì chấp nhận mọi vị trí."""
    if not region or not bounds:
        return True
    try:
        cy = (bounds["top"] + bounds["bottom"]) / 2
    except Exception:
        return True
    if region == "bottom":
        return cy > 0.85 * h
    if region == "top":
        return cy < 0.15 * h
    return True


def _try_click(d, variants, timeout=6.0, exact_first=True, region=None):
    """Bấm phần tử theo text/description trong danh sách biến thể. True nếu
    bấm được. 2 lượt: lượt 1 chỉ khớp CHÍNH XÁC (tránh caption chứa chữ
    trùng — vd caption 'link in profile' không được tính là nút Profile);
    lượt 2 mới dùng Contains. Có region thì chỉ bấm phần tử đúng vùng."""
    w, h = d.window_size()
    passes = (("text", "description"), ("textContains", "descriptionContains"))
    if not exact_first:
        passes = (passes[1], passes[0])
    deadline = time.time() + timeout
    while time.time() < deadline:
        for keyset in passes:
            for v in variants:
                for key in keyset:
                    kwargs = {key: v}
                    try:
                        for el in _matches(d, kwargs):
                            if not el.exists(timeout=0.3):
                                continue
                            try:
                                bounds = (el.info or {}).get("bounds")
                            except Exception:
                                bounds = None
                            if not _in_region(bounds, region, w, h):
                                continue
                            if _tap_human(d, el, label=f"'{v}'"):
                                return True
                    except Exception:
                        continue
        time.sleep(0.5)
    return False


def _exists(d, variants):
    for v in variants:
        for kwargs in ({"text": v}, {"textContains": v}, {"description": v}):
            try:
                if d(**kwargs).exists(timeout=0.3):
                    return True
            except Exception:
                continue
    return False


def _dump_debug(d, root: Path, stem: str):
    out = root / "errors" / f"{time.strftime('%Y%m%d_%H%M%S')}_{stem}"
    out.mkdir(parents=True, exist_ok=True)
    try:
        d.screenshot(str(out / "screen.png"))
    except Exception:
        pass
    try:
        (out / "hierarchy.xml").write_text(d.dump_hierarchy(), encoding="utf-8")
    except Exception:
        pass
    return out


def _open_tiktok(d):
    """Mở app TikTok và XÁC NHẬN nó đang ở foreground mới làm tiếp.

    Hai bệnh đã gặp trên Redmi: (1) 'không có mật khẩu' không có nghĩa là
    không có màn hình khóa — MIUI mặc định vẫn có màn hình khóa VUỐT, và cú
    vuốt mặc định của unlock() hay trượt trên màn 720x1520; (2) máy yếu khởi
    động lạnh TikTok lâu hơn 2–3s nên check một phát đọc trượt.
    Giờ mỗi lần thử: đánh thức -> unlock() -> vuốt mở khóa dự phòng theo đúng
    kích thước màn hình -> mở app -> chờ tối đa 10s để app lên foreground
    thật. Không được thì báo rõ từng trường hợp (tắt màn / kẹt màn khóa /
    đang ở app khác) kèm trạng thái quan sát được, thay vì một lỗi chung.
    """
    last_pkg, last_screen_on = "", True
    for attempt in range(3):
        try:
            d.screen_on()
        except Exception:
            pass
        jitter(0.8, 1.5)
        try:
            d.unlock()
        except Exception:
            pass
        try:  # vuốt mở khóa dự phòng (khóa trượt MIUI) theo đúng màn hình máy
            w, h = d.window_size()
            d.swipe(w // 2, int(h * 0.85), w // 2, int(h * 0.25), duration=0.5)
        except Exception:
            pass
        try:
            d.app_start(TIKTOK_PKG, stop=False)
        except Exception:
            pass
        for _ in range(10):  # chờ app lên foreground (máy yếu khởi động lạnh lâu)
            try:
                info = d.info or {}
            except Exception:
                info = {}
            last_pkg = info.get("currentPackageName") or ""
            last_screen_on = info.get("screenOn", True)
            if last_screen_on and last_pkg == TIKTOK_PKG:
                break
            time.sleep(1.0)
        if last_screen_on and last_pkg == TIKTOK_PKG:
            break
        log(f"  … lần thử {attempt + 1}: màn hình="
            f"{'bật' if last_screen_on else 'TẮT'}, app trước mặt="
            f"{last_pkg or '?'}")
    if last_screen_on and last_pkg == TIKTOK_PKG:
        for _ in range(3):
            if not _try_click(d, TXT_DISMISS, timeout=0.8):
                break
            jitter(0.8, 1.5)
        return
    if not last_screen_on:
        raise JobError("Điện thoại vẫn TẮT màn hình sau 3 lần đánh thức — bấm "
                       "nút nguồn tay cho màn hình sáng rồi chạy lại.")
    if not last_pkg or "systemui" in last_pkg or "keyguard" in last_pkg:
        raise JobError("Điện thoại vẫn kẹt ở MÀN HÌNH KHÓA (vuốt chưa qua) — "
                       "tool chỉ qua được khóa trượt, KHÔNG qua được PIN/mẫu "
                       "hình/vân tay. Mở khóa tay rồi chạy lại; khi test nên "
                       "tắt hẳn màn hình khóa cho khỏi kẹt.")
    raise JobError(f"TikTok chưa lên foreground (đang ở app {last_pkg}) — mở "
                   "tay TikTok trên điện thoại rồi chạy lại.")


def _click_first_gallery_item(d):
    """Bấm ô video đầu tiên (mới nhất) trong lưới chọn video của TikTok."""
    w, h = d.window_size()
    try:
        root_el = ET.fromstring(d.dump_hierarchy())
    except Exception:
        root_el = None
    best = None
    if root_el is not None:
        for node in root_el.iter("node"):
            if node.get("clickable") != "true":
                continue
            m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.get("bounds", ""))
            if not m:
                continue
            x1, y1, x2, y2 = map(int, m.groups())
            cw, ch = x2 - x1, y2 - y1
            # Ô lưới: rộng khoảng 1/5–1/2 màn hình, nằm dưới thanh trên cùng
            if 0.18 * w <= cw <= 0.5 * w and y1 >= 0.10 * h and y2 <= 0.92 * h and ch > 40:
                key = (y1, x1)
                if best is None or key < best[0]:
                    best = (key, (x1 + x2) // 2, (y1 + y2) // 2)
    if best is not None:
        jx, jy = random.randint(-8, 8), random.randint(-8, 8)
        d.click(best[1] + jx, best[2] + jy)
        return True
    # Dự phòng: vị trí tương đối của ô đầu tiên trong lưới
    d.click(int(w * 0.17) + random.randint(-10, 10),
            int(h * 0.32) + random.randint(-10, 10))
    return True


# ------------------------------------------------------------- accounts ----
HANDLE_RE = re.compile(r"@([A-Za-z0-9._]{2,30})")


def _norm_user(u):
    return (u or "").strip().lstrip("@").lower()


def _config_path():
    """File config acc -> ngach. Mac dinh nam canh phone_poster.py (de
    chay tu bat hay tu thu muc nao cung cung 1 file); test co the ghi de
    qua bien moi truong PHONE_POSTER_CONFIG."""
    override = os.environ.get("PHONE_POSTER_CONFIG")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "accounts.json"


def load_niches():
    """Doc mapping username (da chuan hoa) -> ten ngach. File khong co
    hoac loi thi tra {} chu khong crash (config la tinh nang phu)."""
    try:
        data = json.loads(_config_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for k, v in data.items():
        if isinstance(v, str) and v.strip():
            out[_norm_user(k)] = v.strip()
    return out


def save_niches(mapping):
    _config_path().write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n", encoding="utf-8")


def tag_for_account(account, tag):
    """Tag dung cho thu muc _done/_failed: --account-tag neu co; neu
    khong thi lay ngach da config cho acc do (neu co)."""
    tag = (tag or "").strip()
    if tag:
        return tag
    if account:
        return load_niches().get(_norm_user(account), "")
    return ""


def _known_path():
    """File danh sach acc da biet (de goi y lan sau). Ghi de qua bien
    moi truong PHONE_POSTER_KNOWN cho test, giong accounts.json."""
    override = os.environ.get("PHONE_POSTER_KNOWN")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "known_accounts.json"


def load_known():
    """Doc {username chuan hoa: {'last_seen': str, 'current': bool}}.
    File khong co hoac loi thi tra {}."""
    try:
        data = json.loads(_known_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for k, v in data.items():
        if isinstance(v, dict):
            out[_norm_user(k)] = {"last_seen": v.get("last_seen", ""),
                                  "current": bool(v.get("current", False))}
    return out


def save_known(mapping):
    _known_path().write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n", encoding="utf-8")


def record_known(usernames, current):
    """Ghi nhan danh sach acc vua thay: cap nhat last_seen cho acc thay,
    chi 1 acc current=True (acc dang mo), giu nguyen acc cu da biet.
    Goi moi lan liet ke thanh cong (muc 5/8, doi acc) de lan sau goi y
    dung ma khong can mo dien thoai len xem."""
    mapping = load_known()
    now = time.strftime("%Y-%m-%d %H:%M")
    cur = _norm_user(current) if current else ""
    for u in usernames:
        u = _norm_user(u)
        if not u:
            continue
        entry = mapping.get(u, {"last_seen": "", "current": False})
        entry["last_seen"] = now
        mapping[u] = entry
    if cur:
        for u, entry in mapping.items():
            entry["current"] = (u == cur)
    save_known(mapping)
    return mapping


def _niche_kw_path():
    """File tu khoa tim kiem theo ngach (master setting cho nuoi). Ghi de
    qua bien moi truong PHONE_POSTER_NICHE_KW cho test."""
    override = os.environ.get("PHONE_POSTER_NICHE_KW")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "niche_keywords.json"


def load_niche_keywords():
    """Doc {ngach: [tu khoa, ...]}. File khong co hoac loi thi tra {}."""
    try:
        data = json.loads(_niche_kw_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for k, v in data.items():
        if isinstance(v, list):
            kws = [s.strip() for s in v if isinstance(s, str) and s.strip()]
            if kws:
                out[k.strip()] = kws
    return out


def save_niche_keywords(mapping):
    _niche_kw_path().write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n", encoding="utf-8")


def keywords_for_niche(niche):
    """Tu khoa tim kiem cho 1 ngach (master setting cho nuoi tat ca):
    1. niche_keywords.json co entry -> dung no.
    2. Khong co entry: nhan ngach dai >= 3 ky tu thi dung chinh nhan lam
       tu khoa (vd ngach 'dashcam' -> tim 'dashcam').
    3. Nhan qua ngan ('A', 'B') hoac chua config ngach -> [] -> luot FYP
       thoi, khong tim kiem."""
    if not niche:
        return []
    label = niche.strip()
    if not label:
        return []
    kws = load_niche_keywords().get(label, [])
    if kws:
        return kws
    if len(label) >= 3:
        return [label]
    return []


def _parse_nodes(d):
    try:
        return ET.fromstring(d.dump_hierarchy())
    except Exception:
        return None


def _node_bounds(node):
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.get("bounds", ""))
    if not m:
        return None
    return tuple(map(int, m.groups()))


def _handles_on_screen(d):
    """Mọi @username đang hiện trên màn hình: list (handle, y phía trên),
    sắp xếp từ trên xuống dưới."""
    root_el = _parse_nodes(d)
    found = []
    if root_el is None:
        return found
    for node in root_el.iter("node"):
        for attr in ("text", "content-desc"):
            m = HANDLE_RE.search(node.get(attr) or "")
            if m:
                b = _node_bounds(node)
                found.append((m.group(1).lower(), b[1] if b else 0))
                break
    found.sort(key=lambda t: t[1])
    return found


def _goto_profile(d):
    """Mở tab Hồ sơ (Profile) ở thanh điều hướng dưới."""
    if _try_click(d, TXT_PROFILE, timeout=4.0, region="bottom"):
        jitter(1.5, 2.5)
        return
    w, h = d.window_size()
    d.click(int(w * 0.90), int(h * 0.94))  # dự phòng: tab cuối bên phải = Hồ sơ
    jitter(1.5, 2.5)


def current_account(d):
    """@username của acc đang đăng nhập (đọc ở trang Hồ sơ của chính acc đó —
    @username nằm cao nhất trên màn hình). JobError nếu chưa đăng nhập.

    Header trang Hồ sơ (avatar, @handle, số liệu) tải chập chờn — có lần
    dump ra không có lấy một node @handle nào (trang chưa tải xong, hay gặp
    khi mạng/VPN chậm) nên đọc một phát là trượt oan. Giờ chờ tối đa ~12s,
    giữa chừng kéo làm mới trang một lần và bấm lại tab Hồ sơ một lần, rồi
    mới kết luận là không đọc được."""
    _open_tiktok(d)  # đảm bảo TikTok đang mở thật trước khi đọc (trước đây
    # ensure_account gọi thẳng vào đây khi app còn chưa mở, nên đọc trượt)
    _goto_profile(d)
    for attempt in range(12):
        handles = _handles_on_screen(d)
        if handles:
            return handles[0][0]
        if attempt == 4:
            try:  # kéo xuống làm mới trang (header tải dở)
                w, h = d.window_size()
                d.swipe(w // 2, int(h * 0.30), w // 2, int(h * 0.60),
                        duration=0.5)
            except Exception:
                pass
        if attempt == 8:
            _goto_profile(d)
        time.sleep(1.0)
    if _exists(d, TXT_LOGIN):
        raise JobError("TikTok đang ở trạng thái CHƯA đăng nhập acc nào")
    raise JobError("không đọc được @username ở trang Hồ sơ (header trang tải "
                   "chưa xong sau ~12s — mạng/VPN chậm có thể gây ra, chạy "
                   "lại thường là được)")


TXT_SWITCHER = ["Switch account", "Switch accounts", "Chuyển tài khoản",
                "Đổi tài khoản", "Manage accounts", "Quản lý tài khoản"]


def _switcher_open(d):
    handles = {h for h, _y in _handles_on_screen(d)}
    return (len(handles) >= 2 or _exists(d, TXT_ADD_ACCOUNT)
            or _exists(d, TXT_SWITCHER))


def _switcher_button_center(d, name_bounds):
    """Tâm của nút bấm thật chứa tên: trên bản TikTok này TextView tên
    KHÔNG clickable, nút thật là LinearLayout cha bao quanh nó
    (vd [244,55][488,159] chứa tên [244,85][488,129]). Trả về None nếu
    không tìm được khung cha clickable nào thì dùng cách chạm cũ."""
    if name_bounds is None:
        return None
    root_el = _parse_nodes(d)
    if root_el is None:
        return None
    nx1, ny1, nx2, ny2 = name_bounds
    best = None
    for node in root_el.iter("node"):
        if node.get("clickable") != "true":
            continue
        b = _node_bounds(node)
        if not b:
            continue
        if b[0] <= nx1 and b[1] <= ny1 and b[2] >= nx2 and b[3] >= ny2:
            area = (b[2] - b[0]) * (b[3] - b[1])
            if best is None or area < best[0]:
                best = (area, b)
    if best is None:
        return None
    b = best[1]
    return ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)


def _wait_switcher(d, timeout=5.0):
    """Chờ bảng chuyển tài khoản hiện ra (máy yếu + VPN chậm thì sheet mở
    có độ trễ, chờ 3s là đọc trượt)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _switcher_open(d):
            return True
        time.sleep(0.5)
    return _switcher_open(d)


def _open_switcher(d):
    """Mở bảng chuyển tài khoản từ trang Hồ sơ, thử lần lượt 3 cách:
    (1) chạm tên hiển thị ở thanh trên cùng — tên có thể nằm ở text hoặc
    content-desc tùy bản TikTok; (2) chạm thẳng vào giữa thanh trên cùng
    (chỗ tên + mũi tên xổ xuống) — không phụ thuộc vào nút nào đọc được;
    (3) nhấn giữ tab Hồ sơ — khớp cả chứa chuỗi vì content-desc của tab
    thường là 'Profile, Tab 5 of 5' chứ không đúng 'Profile'."""
    _goto_profile(d)
    if _switcher_open(d):
        return True
    w, h = d.window_size()
    root_el = _parse_nodes(d)
    name, name_bounds, best_w = None, None, -1
    if root_el is not None:
        for node in root_el.iter("node"):
            text = ((node.get("text") or "").strip()
                    or (node.get("content-desc") or "").strip())
            if not text or text.startswith("@"):
                continue
            b = _node_bounds(node)
            if not b:
                continue
            cx = (b[0] + b[2]) / 2
            if b[1] < 0.14 * h and 0.25 * w < cx < 0.75 * w and (b[2] - b[0]) > best_w:
                best_w, name, name_bounds = b[2] - b[0], text, b
    center = _switcher_button_center(d, name_bounds)
    if center is not None:  # chạm tâm nút cha clickable (cách chắc ăn nhất)
        try:
            jx, jy = random.randint(-8, 8), random.randint(-8, 8)
            d.click(center[0] + jx, center[1] + jy)
        except Exception:
            pass
        jitter(1.0, 2.0)
        if _wait_switcher(d):
            return True
    if name:
        for kwargs in ({"text": name}, {"description": name},
                       {"textContains": name}):
            try:
                el = d(**kwargs)
                if el.exists(timeout=0.5) and _tap_human(d, el):
                    jitter(1.0, 2.0)
                    if _wait_switcher(d):
                        return True
            except Exception:
                continue
    # chạm thẳng vào thanh trên cùng: giữa (chỗ tên) và lệch phải (gần mũi
    # tên). Lưu ý: mũi tên chỉ là hình vẽ trong nút, không phải node riêng;
    # điểm cũ (0.68w, 0.06h) rơi ra ngoài nút cha đúng 2px, trúng nút
    # 'Profile views' bên cạnh nên vô dụng — điểm mới nằm trong nút cha.
    for xf, yf in ((0.5, 0.055), (0.5, 0.08), (0.64, 0.07)):
        try:
            d.click(int(w * xf), int(h * yf))
        except Exception:
            pass
        jitter(1.0, 2.0)
        if _wait_switcher(d):
            return True
        try:
            d.press("back")
        except Exception:
            pass
        jitter(0.8, 1.5)
    for kwargs in ({"description": "Profile"}, {"text": "Profile"},
                   {"description": "Hồ sơ"}, {"text": "Hồ sơ"},
                   {"descriptionContains": "Profile"}, {"textContains": "Profile"},
                   {"descriptionContains": "Hồ sơ"}, {"textContains": "Hồ sơ"}):
        try:
            el = d(**kwargs)
            if el.exists(timeout=0.3):
                el.long_click()
                jitter(1.0, 2.0)
                if _wait_switcher(d):
                    return True
                break
        except Exception:
            continue
    return _switcher_open(d)


BARE_USER_RE = re.compile(r"^[A-Za-z0-9._]{2,30}$")
SHEET_NON_USER = {"add account", "switch account", "switch accounts"}


def _sheet_usernames(d):
    """Username các acc trong bảng Switch account, theo thứ tự trong bảng.

    Bảng này ghi username TRẦN (không có @): mỗi dòng acc là một nút bấm có
    content-desc đúng bằng username, bên trong là TextView cùng chữ đó
    (vd nút desc='sandracruzkay183' chứa TextView 'sandracruzkay183').
    Regex @ cũ mù tịt dạng này — đó là lý do bảng mở ra mà chỉ thấy acc
    đang mở (lấy @ từ trang Hồ sơ phía sau). Dự phòng: nếu không khớp nút
    nào thì lấy các TextView username trần nằm dưới tiêu đề 'Switch account'
    (trừ 'Add account')."""
    root_el = _parse_nodes(d)
    if root_el is None:
        return []
    nodes = list(root_el.iter("node"))
    found = []
    for node in nodes:
        if node.get("clickable") != "true":
            continue
        desc = (node.get("content-desc") or "").strip()
        if not desc or not BARE_USER_RE.match(desc):
            continue
        if desc.lower() in SHEET_NON_USER:
            continue
        b = _node_bounds(node)
        if not b:
            continue
        for inner in nodes:
            t = (inner.get("text") or "").strip()
            if t != desc:
                continue
            ib = _node_bounds(inner)
            if ib and b[0] <= ib[0] and b[1] <= ib[1] and b[2] >= ib[2] and b[3] >= ib[3]:
                found.append(desc.lower())
                break
    if found:
        return found
    title_bottom = None
    for node in nodes:
        if (node.get("text") or "").strip().lower() == "switch account":
            b = _node_bounds(node)
            if b:
                title_bottom = b[3]
            break
    if title_bottom is None:
        return []
    for node in nodes:
        t = (node.get("text") or "").strip()
        b = _node_bounds(node)
        if not t or not b or b[1] < title_bottom:
            continue
        if not BARE_USER_RE.match(t) or t.lower() in SHEET_NON_USER:
            continue
        if t.lower() not in found:
            found.append(t.lower())
    return found


def list_logged_in_accounts(d, root=None):
    """Trả về (acc đang mở, [mọi acc đã đăng nhập trong app, theo thứ tự
    trong bảng chuyển tài khoản]). Phân biệt rõ 2 trường hợp 'chỉ thấy 1':
    bảng không mở được (danh sách có thể thiếu — lúc này lưu luôn ảnh chụp +
    cấu trúc màn hình để chẩn đoán) vs bảng mở ra mà chỉ có 1 acc (tức app
    này thực sự chỉ đăng nhập 1 acc — các acc khác nếu có thì đang nằm ở
    Second Space/Dual App, tức app khác, tool không đọc tới)."""
    _open_tiktok(d)
    current = current_account(d)
    if not _open_switcher(d):
        log("⚠️ Không mở được bảng chuyển tài khoản — chỉ đọc được acc đang "
            "mở, danh sách có thể thiếu.")
        if root is not None:
            where = _dump_debug(d, root, "account-switcher")
            log(f"   Ảnh chụp + cấu trúc màn hình đã lưu ở {where} — gửi thư "
                "mục này cho Muse để xem nút chuyển acc trên máy này nằm ở đâu.")
        return current, [current]
    sheet = _sheet_usernames(d)
    if sheet:
        handles = sheet  # bảng ghi username trần: thứ tự trong bảng là chuẩn
    else:
        handles = []
        for handle, _y in _handles_on_screen(d):
            if handle not in handles:
                handles.append(handle)
    # Ghi rõ bảng được nhận biết nhờ điều kiện nào — để phân biệt 'bảng
    # chuyển acc thật chỉ có 1 acc' với 'sheet khác cũng có chữ Add account
    # nên bị nhận nhầm là bảng chuyển acc'.
    log(f"  (bảng nhận biết qua: {len(handles)} acc, "
        f"Add account={'có' if _exists(d, TXT_ADD_ACCOUNT) else 'không'}, "
        f"nhãn Switch={'có' if _exists(d, TXT_SWITCHER) else 'không'})")
    if len(handles) <= 1 and root is not None:
        # Bảng 'mở được' mà chỉ thấy 1 acc là trường hợp cần chẩn đoán nhất
        # (sai sheet? acc khác không hiện dạng @handle?) nên lưu dump luôn,
        # chứ không im lặng trả về như trước.
        where = _dump_debug(d, root, "account-switcher-1acc")
        log(f"   Ảnh chụp + cấu trúc màn hình đã lưu ở {where} — gửi thư mục "
            "này cho Muse để xem bảng vừa mở thực sự là bảng gì.")
    try:
        d.press("back")
    except Exception:
        pass
    jitter(0.8, 1.5)
    if len(handles) <= 1:
        log("ℹ️ Bảng chuyển tài khoản mở được nhưng trong app này chỉ có 1 acc "
            "đã đăng nhập. Acc khác nếu có thì đang ở Second Space/Dual App "
            "(app khác) — đăng nhập nó vào app TikTok này rồi chạy lại menu 5.")
    return current, handles or [current]


def switch_account(d, target):
    """Đổi sang acc @target (phải đã đăng nhập sẵn trong app) rồi đọc lại
    trang Hồ sơ để XÁC NHẬN acc hiện tại đúng là @target mới trả về."""
    target = _norm_user(target)
    if not target:
        raise JobError("chưa cho biết acc cần đổi sang")
    _open_tiktok(d)
    cur = current_account(d)
    if cur == target:
        log(f"→ Acc đang mở đã là @{target} — không cần đổi.")
        return cur
    log(f"→ Đổi acc: @{cur} → @{target}")
    if not _open_switcher(d):
        raise JobError("không mở được bảng chuyển tài khoản của TikTok")
    tapped = False
    for kwargs in ({"text": f"@{target}"}, {"text": target},
                   {"textContains": target}, {"descriptionContains": target}):
        try:
            el = d(**kwargs)
            if el.exists(timeout=0.5):
                tapped = _tap_human(d, el)
                if tapped:
                    break
        except Exception:
            continue
    if not tapped:
        raise JobError(f"không thấy acc @{target} trong danh sách đã đăng nhập")
    jitter(3.0, 5.0)
    if _exists(d, TXT_VERIFY_BLOCK):
        raise JobError("TikTok yêu cầu XÁC MINH khi đổi acc — mở điện thoại xử lý "
                       "tay (nhập mã / bấm xác nhận) rồi chạy lại")
    cur2 = current_account(d)
    if cur2 != target:
        raise JobError(f"đổi acc chưa thành công: đang ở @{cur2}, cần @{target}")
    log(f"✅ Đã đổi sang acc @{target} (đã xác nhận ở trang Hồ sơ).")
    return cur2


def ensure_account(d, target):
    """Đảm bảo acc đang mở đúng @target: đúng thì thôi, sai thì tự đổi."""
    target = _norm_user(target)
    cur = current_account(d)
    if cur == target:
        return cur
    log(f"→ Acc đang mở là @{cur}, cần @{target} — tự đổi...")
    return switch_account(d, target)


# -------------------------------------------------------------- nurture ----
def _watch_one(d, like_cap, likes_done, idx=0):
    """Xem 1 video như người thật rồi vuốt lên, LOG REALTIME từng bước để
    người ngồi xem log thấy action liên tục (trước đây chỉ log mỗi 10
    video nên giữa các lần dwell 15-120s log im lặng, nhìn như treo):
    xem đủ lâu (phần lớn 15-45s là hết video ngắn, thỉnh thoảng xem dài
    45-120s), vuốt lên có kiểm chứng, rồi CHỈ like khi đã xác nhận qua
    video mới (trước đây like bấm mù vào màn hình cũ — 1 nguồn 'ấn lung
    tung'). Trả (likes_done mới, có like video này không)."""
    w, h = d.window_size()
    r = random.random()
    if r < 0.6:
        dwell = random.uniform(15.0, 45.0)
    elif r < 0.9:
        dwell = random.uniform(45.0, 75.0)
    else:
        dwell = random.uniform(75.0, 120.0)
    log(f"   ▶ video #{idx}: xem ~{dwell:.0f}s")
    time.sleep(dwell)
    advanced = _swipe_next_verified(d)
    if advanced:
        log(f"   ↑ đã qua video mới")
    else:
        log(f"   ⚠️ kẹt ở video cũ — bỏ qua like video này")
    liked = False
    if advanced and likes_done < like_cap and random.random() < 0.20:
        try:
            d.double_click(w // 2, h // 2)
        except Exception:
            pass
        likes_done += 1
        liked = True
        log(f"   ♥ like video #{idx}")
        jitter(0.5, 1.5)
    jitter(0.5, 1.5)
    return likes_done, liked


def _nurture_search(d, keyword, like_cap, likes_done, watched, per_keyword=6):
    """Mở tìm kiếm, gõ từ khóa ngách, xem vài video từ kết quả rồi quay
    lại. Mở không được (giao diện khác bản) thì trả (..., False) để phiên
    chính vẫn nuôi bằng FYP — 1 bước phụ không được crash cả phiên."""
    try:
        if not _try_click(d, TXT_SEARCH, timeout=3.0, region="top"):
            log("   (không mở được ô tìm kiếm trên giao diện này — bỏ qua, nuôi bằng FYP)")
            return watched, likes_done, False
        jitter(1.0, 2.0)
        edits = d(className="android.widget.EditText")
        if not edits.exists(timeout=3.0):
            d.press("back")
            return watched, likes_done, False
        _type_human(d, edits, keyword)
        jitter(1.0, 2.0)
        d.press("enter")
        jitter(2.0, 3.5)
        for _ in range(per_keyword):
            likes_done, _ = _watch_one(d, like_cap, likes_done,
                                       idx=watched + 1)
            watched += 1
        d.press("back")
        jitter(1.0, 2.0)
        return watched, likes_done, True
    except Exception as e:
        log(f"   (tìm kiếm '{keyword}' lỗi: {e} — bỏ qua, nuôi bằng FYP)")
        try:
            d.press("back")
        except Exception:
            pass
        return watched, likes_done, False


def nurture_session(d, min_s=1200, max_s=2400, keywords=None, like_cap=8):
    """Nuôi acc tự động như người thật: xem hết video rồi lướt.
    - Mở TikTok, về Home.
    - Nếu có từ khóa ngách: tìm kiếm từng từ khóa, xem ~6 video/từ để
      FYP học đúng ngách (mở không được thì nuôi bằng FYP).
    - Lướt FYP đến hết ngân sách thời gian (~20-40 phút mặc định).
    - Like thưa bằng double-tap (tối đa like_cap/phiên).
    KHÔNG tự comment, KHÔNG tự follow: 2 hành động đó cần ý thật và là
    tín hiệu spam dễ bị bắt nhất — để người làm tay (1-2 comment/ngày,
    2-3 follow/ngày). Ctrl+C dừng phiên nhưng vẫn in tổng kết.
    Trả dict tổng kết {'watched', 'likes', 'minutes'}."""
    budget = random.uniform(min_s, max_s)
    log(f"→ Bắt đầu nuôi tự động ~{budget / 60:.0f} phút: xem hết video rồi "
        f"lướt, like tối đa {like_cap}/phiên, không comment/follow tự động.")
    _open_tiktok(d)
    _try_click(d, TXT_HOME, timeout=3.0, region="bottom")
    jitter(2.0, 3.0)
    watched = 0
    likes_done = 0
    interrupted = False
    end = time.time() + budget
    try:
        for kw in (keywords or []):
            kw = kw.strip()
            if not kw:
                continue
            log(f"→ Tìm kiếm ngách: {kw}")
            watched, likes_done, _ = _nurture_search(
                d, kw, like_cap, likes_done, watched)
        while time.time() < end:
            likes_done, _ = _watch_one(d, like_cap, likes_done,
                                       idx=watched + 1)
            watched += 1
    except KeyboardInterrupt:
        interrupted = True
        log("   (đã dừng nuôi bằng Ctrl+C)")
    log(f"✅ Nuôi xong: xem {watched} video, like {likes_done} "
        f"trong ~{budget / 60:.0f} phút.")
    return {"watched": watched, "likes": likes_done, "minutes": budget / 60,
            "interrupted": interrupted}


def nurture_all(d, root, like_cap=8, min_s=540, max_s=660):
    """Nuôi TẤT CẢ acc đang đăng nhập trong app, mỗi acc ~10 phút rồi đổi.
    Ngách đã config (accounts.json) là master: acc có ngách -> tìm kiếm
    từ khóa của ngách đó (niche_keywords.json, hoặc chính nhãn ngách nếu
    đủ dài); acc chưa config ngách -> lướt FYP thôi.
    Acc nào đổi không được thì bỏ qua, nuôi tiếp acc khác (không dừng cả
    phiên vì 1 acc); cuối phiên in tổng kết từng acc. Trả list tổng kết."""
    current, accounts = list_logged_in_accounts(d, root)
    if not accounts:
        raise JobError("không thấy acc nào đăng nhập trong app TikTok")
    niches = load_niches()
    log(f"→ Nuôi tất cả {len(accounts)} acc, mỗi acc ~10 phút rồi đổi acc.")
    results = []
    for user in accounts:
        niche = niches.get(user, "")
        kws = keywords_for_niche(niche)
        try:
            switch_account(d, user)
        except Exception as e:
            log(f"❌ Bỏ qua @{user}: không đổi được acc ({e})")
            results.append({"user": user, "niche": niche, "status": "skip",
                            "reason": str(e)})
            continue
        if niche and kws:
            log(f"→ Nuôi @{user} (ngách {niche}, từ khóa: {', '.join(kws)})")
        elif niche:
            log(f"→ Nuôi @{user} (ngách {niche} chưa có từ khóa — lướt FYP thôi)")
        else:
            log(f"→ Nuôi @{user} (chưa config ngách — lướt FYP thôi)")
        try:
            s = nurture_session(d, min_s=min_s, max_s=max_s,
                                keywords=kws, like_cap=like_cap)
            results.append({"user": user, "niche": niche, "status": "done",
                            "watched": s["watched"], "likes": s["likes"],
                            "minutes": s["minutes"]})
            if s.get("interrupted"):
                log("Đã dừng toàn bộ phiên nuôi tất cả.")
                break
        except JobError as e:
            log(f"❌ Nuôi @{user} lỗi: {e}")
            results.append({"user": user, "niche": niche, "status": "error",
                            "reason": str(e)})
    log("===== Tổng kết nuôi tất cả =====")
    for r in results:
        if r["status"] == "done":
            log(f"  • @{r['user']} (ngách {r['niche'] or 'chưa config'}): "
                f"xem {r['watched']} video, like {r['likes']} "
                f"trong ~{r['minutes']:.0f} phút")
        else:
            log(f"  • @{r['user']}: {r['status']} ({r.get('reason', '')})")
    return results


# -------------------------------------------------------------- one post ----
def _type_human(d, field, text):
    """Gõ caption từng cụm 2–6 ký tự với nhịp ngẫu nhiên — giống tay người gõ,
    thay vì dán (paste) một phát cả đoạn như bản cũ."""
    field.click()
    jitter(0.5, 1.2)
    try:
        i = 0
        while i < len(text):
            n = random.randint(2, 6)
            d.send_keys(text[i:i + n])
            i += n
            time.sleep(random.uniform(0.04, 0.22))
            if random.random() < 0.15:
                # thỉnh thoảng khựng lại như đang nghĩ câu chữ rồi gõ tiếp
                time.sleep(random.uniform(0.8, 2.0))
    except Exception:
        field.set_text(text)  # dự phòng: máy nào không gõ được thì dán


def _swipe_next(d):
    """Vuốt lên sang video tiếp theo: vuốt DÀI và NHANH (0.80-0.88h xuống
    0.12-0.20h trong 0.15-0.35s). Vuốt ngắn/chậm (bản cũ 0.72h->0.28h trong
    0.3-0.6s) bị TikTok kéo trả lại, không qua được video khác — đúng bệnh
    nuôi tự động gặp trên Redmi (lướt nhẹ quá nên kẹt 1 video)."""
    w, h = d.window_size()
    x = int(w * random.uniform(0.40, 0.60))
    d.swipe(x, int(h * random.uniform(0.80, 0.88)),
            x + random.randint(-15, 15), int(h * random.uniform(0.12, 0.20)),
            random.uniform(0.15, 0.35))


def _screen_sig(d):
    """Dấu hiệu màn hình hiện tại (hash cây UI): đổi video thì caption/
    tác giả/lượt like đổi theo nên hash đổi. Không đọc được thì None."""
    for fn in ("dump", "dump_hierarchy"):
        try:
            s = getattr(d, fn)()
            if s:
                return hash(s)
        except Exception:
            continue
    return None


def _swipe_next_verified(d, tries=3):
    """Vuốt lên và KIỂM CHỨNG đã qua video mới (so hash cây UI trước/sau).
    Vuốt không qua thì thử lại kiểu khác, cuối cùng thử kéo chậm dài;
    vẫn không qua thì trả False để caller biết mà không like mù lên màn
    hình cũ — và log báo rõ thay vì im lặng kẹt 1 video như trước."""
    before = _screen_sig(d)
    for attempt in range(1, tries + 1):
        _swipe_next(d)
        jitter(2.0, 3.0)
        after = _screen_sig(d)
        if before is None or after is None or after != before:
            return True
        log(f"   vuốt lần {attempt} chưa qua video — thử lại kiểu khác")
    w, h = d.window_size()
    x = int(w * 0.5)
    try:
        d.swipe(x, int(h * 0.75), x, int(h * 0.25), 0.9)  # kéo chậm dài
    except Exception:
        pass
    jitter(2.0, 3.0)
    after = _screen_sig(d)
    if before is None or after is None or after != before:
        return True
    log("   ⚠️ vuốt 3 lần + kéo chậm vẫn không qua video mới")
    return False


def warmup_feed(d, min_s=60, max_s=120, swipes=None):
    """Lướt feed như người thật trước khi đăng: xem mỗi video vài giây rồi
    vuốt lên. Chạy 1 lần mỗi lần chạy tool (không phải mỗi video).
    `swipes=N` để test: vuốt đúng N lần thay vì tính theo thời gian."""
    if swipes is None:
        secs = random.uniform(min_s, max_s)
    else:
        secs = 0
    log(f"→ Khởi động phiên: lướt feed ~{int(secs)}s cho giống người thật")
    _try_click(d, TXT_HOME, timeout=3.0, region="bottom")
    jitter(2.0, 3.0)
    w, h = d.window_size()
    end = time.time() + secs
    n = 0
    while True:
        if swipes is not None:
            if n >= swipes:
                break
        elif time.time() >= end:
            break
        n += 1
        if random.random() < 0.25:
            time.sleep(random.uniform(12.0, 20.0))  # video hay thì xem lâu hơn
        else:
            time.sleep(random.uniform(5.0, 11.0))  # xem video vài giây như người thật
        _swipe_next(d)
        jitter(0.5, 1.5)


def post_one(d, job: dict, root: Path, dry_run=False, keep_on_phone=False):
    video: Path = job["video"]
    caption: str = job["caption"]
    stem = video.stem
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", video.name)
    remote = f"{PHONE_DIR}/{safe_name}"

    log(f"→ Đẩy video sang điện thoại: {video.name}")
    d.shell(["mkdir", "-p", PHONE_DIR])
    d.push(str(video), remote)
    d.shell(["am", "broadcast", "-a",
             "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
             "-d", f"file://{remote}"])
    jitter(2.0, 3.5)

    _open_tiktok(d)

    log("→ Mở màn hình tạo video")
    if not _try_click(d, TXT_CREATE, timeout=5.0):
        w, h = d.window_size()
        d.click(w // 2 + random.randint(-12, 12),
                int(h * 0.93) + random.randint(-8, 8))  # nút + ở giữa thanh dưới
        jitter()
    if not _try_click(d, TXT_UPLOAD, timeout=8.0):
        raise JobError("không thấy nút Tải lên (Upload) trong màn hình tạo video")
    jitter(2.0, 3.5)

    log("→ Chọn video mới nhất trong thư viện")
    _click_first_gallery_item(d)
    jitter(2.0, 3.5)

    for _ in range(4):  # các màn hình biên tập đều qua nút Tiếp/Next
        if not _try_click(d, TXT_NEXT, timeout=4.0):
            break
        jitter(2.0, 3.5)

    log("→ Nhập caption")
    field = None
    for v in TXT_CAPTION_HINT:
        el = d(textContains=v)
        if el.exists(timeout=0.5):
            field = el
            break
    if field is None:
        edits = d(className="android.widget.EditText")
        if edits.exists(timeout=2.0):
            field = edits
    if field is None:
        raise JobError("không thấy ô nhập mô tả/caption")
    _type_human(d, field, caption)
    jitter()

    if dry_run:
        log("🧪 DRY-RUN: dừng tại màn hình đăng — KHÔNG bấm Đăng.")
        d.screenshot(str(root / f"dryrun_{stem}.png"))
        return "dry-run"

    log("→ Xem lại caption một lúc như người thật rồi mới bấm Đăng")
    jitter(3.0, 8.0)
    log("→ Bấm Đăng")
    if not _try_click(d, TXT_POST, timeout=6.0):
        raise JobError("không thấy nút Đăng (Post)")
    jitter(10.0, 16.0)  # chờ tải lên: khoảng chờ cố định cũng là dấu vết máy móc
    if _exists(d, TXT_UPLOAD_ERROR):
        raise JobError("TikTok báo lỗi tải lên")
    if _exists(d, TXT_POST) and _exists(d, TXT_CAPTION_HINT):
        raise JobError("vẫn ở màn hình đăng sau khi chờ — có thể chưa đăng được")

    if not keep_on_phone:
        d.shell(["rm", remote])
    log(f"✅ Đã đăng: {video.name}")
    return "posted"


# ------------------------------------------------------------------ main ----
def _connect(serial):
    """Kết nối ADB/agent, lỗi thì báo rõ nguyên nhân thay vì traceback.

    Bệnh thường gặp trên Redmi: MIUI tắt app agent ATX chạy nền (pin) nên
    điện thoại vẫn cắm cáp mà tool không nói chuyện được — lúc đó chạy lại
    menu 1, rồi vào Cài đặt > Pin cho app ATX chọn 'Không giới hạn' và
    khóa nó trong đa nhiệm cho khỏi bị tắt."""
    import uiautomator2 as u2
    use_serial = serial or ""
    if not use_serial:
        # Không chỉ serial: chọn máy đầu tiên ở trạng thái device trong
        # `adb devices` để khỏi vớ phải máy offline/unauthorized đứng
        # trước trong danh sách (bệnh gặp sau khi rút cáp). Không có adb
        # hoặc không có máy nào thì giữ nguyên cách nối cũ.
        try:
            import shutil
            import subprocess
            adb = shutil.which("adb")
            if adb:
                out = subprocess.run([adb, "devices"], capture_output=True,
                                     text=True, timeout=10).stdout
                for line in out.splitlines():
                    if "\tdevice" in line:
                        use_serial = line.split("\t")[0].strip()
                        break
        except Exception:
            pass
    try:
        d = u2.connect(use_serial)
        name = d.info.get("productName")
    except Exception:
        raise JobError("không nói chuyện được với điện thoại (cáp lỏng, chưa "
                       "bật USB debugging, hoặc MIUI đã tắt app agent ATX — "
                       "chạy lại menu 1 cài agent, cho app ATX chạy pin "
                       "'Không giới hạn' rồi thử lại)")
    log(f"Đã kết nối điện thoại: {name}")
    return d


def _adb_devices(text):
    """Parse `adb devices` -> {serial: state}. Chỉ để đọc trạng thái máy,
    không dùng để quyết định gì khác."""
    out = {}
    for line in (text or "").splitlines():
        if "\t" in line:
            serial, state = line.split("\t", 1)
            serial, state = serial.strip(), state.strip()
            if serial:
                out[serial] = state
    return out


def run_wifi():
    """Chuyển điện thoại đang cắm USB sang ADB qua Wi-Fi để rút cáp được.

    Thứ tự bắt buộc: lấy IP Wi-Fi TRƯỚC (khi còn nối USB), rồi mới tcpip
    (lệnh này khởi động lại adbd nên USB rớt ngay sau đó), rồi connect IP.
    Cắm cáp lại là về USB, không cần làm gì thêm.
    Khác bản cũ: thử connect lại nhiều lần (máy yếu khởi động lại adbd
    chậm, thử 1 lần sau 2s là trượt oan) và đọc đúng trạng thái máy —
    'unauthorized' (chưa bấm Cho phép trên điện thoại) phải báo riêng,
    không được tính là nối được."""
    import shutil
    import subprocess
    adb = shutil.which("adb")
    if not adb:
        log("❌ Không tìm thấy lệnh adb trên PC này — cài Android platform-tools "
            "rồi chạy lại (menu 1 đã từng chạy được thì adb phải có sẵn).")
        return
    out = subprocess.run([adb, "devices"], capture_output=True,
                         text=True).stdout
    usb = [s for s, st in _adb_devices(out).items() if st == "device"]
    if not usb:
        log("❌ Không thấy điện thoại nào qua USB — cắm cáp + bật USB debugging "
            "rồi chạy lại.")
        return
    serial = next((s for s in usb if ":" not in s), usb[0])
    log(f"Điện thoại qua USB: {serial}")
    ip = None
    r = subprocess.run([adb, "-s", serial, "shell", "ip", "addr", "show",
                        "wlan0"], capture_output=True, text=True)
    m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/", r.stdout)
    if m:
        ip = m.group(1)
    if not ip:
        r = subprocess.run([adb, "-s", serial, "shell", "ip", "route"],
                           capture_output=True, text=True)
        m = re.search(r"src (\d+\.\d+\.\d+\.\d+)", r.stdout)
        if m:
            ip = m.group(1)
    if not ip:
        log("❌ Không lấy được IP Wi-Fi — điện thoại đã nối Wi-Fi (cùng mạng "
            "với PC) chưa?")
        return
    log(f"IP Wi-Fi của điện thoại: {ip}")
    subprocess.run([adb, "-s", serial, "tcpip", "5555"], check=False)
    target = f"{ip}:5555"
    state = None
    for attempt in range(1, 11):
        r = subprocess.run([adb, "connect", target],
                           capture_output=True, text=True)
        msg = (r.stdout or "").strip()
        if msg:
            log(f"   adb connect (lần {attempt}): {msg}")
        time.sleep(3)
        out = subprocess.run([adb, "devices"], capture_output=True,
                             text=True).stdout
        state = _adb_devices(out).get(target)
        if state == "device":
            break
        if state == "unauthorized":
            log("❌ Máy hiện 'unauthorized' — kiểm tra màn hình điện thoại, "
                "bấm Cho phép (Allow) hộp thoại gỡ lỗi rồi chạy lại mục này.")
            return
    if state != "device":
        log("❌ Sau nhiều lần thử vẫn chưa thấy máy qua Wi-Fi — kiểm tra: "
            "PC và điện thoại có cùng mạng Wi-Fi không? Điện thoại đã nối "
            "Wi-Fi chưa? Khởi động lại điện thoại là mất chế độ tcpip, phải "
            "cắm cáp chạy lại mục này.")
        return
    log(f"✅ Xong: rút cáp được. Từ giờ chạy các mục khác bình thường "
        f"(chỉ còn máy Wi-Fi nên tool tự chọn nó); hoặc chạy kèm "
        f"--serial {ip}:5555 để chắc chắn.")
    try:
        import uiautomator2 as u2
        d = u2.connect(target)
        log(f"   Kiểm tra qua uiautomator2 OK: {d.info.get('productName')}")
    except Exception:
        log("   (adb nối được nhưng chưa nói chuyện được qua uiautomator2 "
            "— thử chạy lại menu 2 để kiểm tra)")


def run_init(serial):
    log("Cài agent uiautomator2 lên điện thoại (cần cắm USB + đã bật USB debugging)...")
    cmd = [sys.executable, "-m", "uiautomator2", "init"]
    if serial:
        cmd += ["--serial", serial]
    subprocess.run(cmd, check=False)
    import uiautomator2 as u2
    # Server trên máy vừa được cài xong hay khởi động lại / bị MIUI tắt ngay
    # sau đó (đúng bệnh trong log: ping OK rồi d.info rớt kết nối) — thử
    # lại vài lần thay vì văng traceback ngay lần đầu.
    info = None
    last_err = None
    for attempt in range(1, 6):
        try:
            d = u2.connect(serial or "")
            info = d.info
            break
        except Exception as e:
            last_err = e
            log(f"   Chờ server trên máy ổn định lại (lần {attempt}/5)...")
            time.sleep(3)
    if info is None:
        raise JobError(
            "cài agent xong nhưng không nói chuyện được với server trên máy "
            f"({last_err}). Server đã chạy rồi nhưng rớt ngay sau khi cài — "
            "thường do MIUI tắt app agent chạy nền. Thử chạy lại menu 1 một "
            "lần nữa; nếu vẫn rớt thì vào Cài đặt > Pin cho app ATX chọn "
            "'Không giới hạn' và khóa nó trong đa nhiệm, rồi chạy lại menu 1.")
    log(f"Kết nối OK: {info.get('productName')} | Android API {info.get('sdkInt')} "
        f"| màn hình {info.get('displayWidth')}x{info.get('displayHeight')}")
    log("Mở thử TikTok trong 3 giây...")
    d.app_start(TIKTOK_PKG, stop=False)
    time.sleep(3)
    log("Xong. Rút cáp được rồi nếu đã bật gỡ lỗi qua Wi-Fi (adb tcpip); "
        "không thì cứ để cắm USB khi đăng.")


def main():
    ap = argparse.ArgumentParser(description="Tự chuyển video sang điện thoại Android và đăng TikTok")
    ap.add_argument("--dir", default="outbox", help="thư mục hàng đợi chứa video (+ .txt caption)")
    ap.add_argument("--serial", default="", help="serial ADB hoặc IP:5555 (mặc định: máy USB đầu tiên)")
    ap.add_argument("--max-posts", type=int, default=0, help="tối đa N video trong lần chạy này (0 = tất cả)")
    ap.add_argument("--gap-min", type=int, default=240, help="nghỉ tối thiểu giữa 2 lần đăng (giây)")
    ap.add_argument("--gap-max", type=int, default=540, help="nghỉ tối đa giữa 2 lần đăng (giây)")
    ap.add_argument("--dry-run", action="store_true", help="làm mọi bước nhưng KHÔNG bấm Đăng")
    ap.add_argument("--keep-on-phone", action="store_true", help="giữ video trên điện thoại sau khi đăng")
    ap.add_argument("--no-warmup", action="store_true",
                    help="bỏ qua bước lướt feed khởi động trước khi đăng")
    ap.add_argument("--warmup-min", type=int, default=60, help="lướt feed tối thiểu (giây)")
    ap.add_argument("--warmup-max", type=int, default=120, help="lướt feed tối đa (giây)")
    ap.add_argument("--account-tag", default="",
                    help="nhãn acc cho lần chạy này (vd: irl, court) — file xong/lỗi "
                         "sẽ vào _done-<tag>/_failed-<tag> riêng, khỏi lẫn 2 mảng test")
    ap.add_argument("--account", default="",
                    help="@username acc PHẢI đăng cho lần chạy này: tool kiểm tra acc "
                         "đang mở trước mỗi lần đăng, sai thì TỰ ĐỔI, đổi không được "
                         "thì DỪNG không đăng (khác --account-tag: đó chỉ là nhãn thư mục)")
    ap.add_argument("--list-accounts", action="store_true",
                    help="mở TikTok, liệt kê các acc đã đăng nhập trong app rồi thoát")
    ap.add_argument("--switch-to", default="",
                    help="đổi sang acc @username đã đăng nhập sẵn, xác nhận xong thì "
                         "thoát (để test đổi acc)")
    ap.add_argument("--init", action="store_true", help="cài agent + kiểm tra kết nối rồi thoát")
    ap.add_argument("--wifi", action="store_true",
                    help="chuyển điện thoại đang cắm USB sang ADB qua Wi-Fi để rút cáp")
    ap.add_argument("--set-niche", nargs=2, metavar=("USER", "NGACH"),
                    help="gán ngách cho 1 acc (vd: --set-niche sandracruzkay183 B)")
    ap.add_argument("--known-accounts", action="store_true",
                    help="in danh sách acc đã biết (đã lưu từ những lần liệt kê trước, không cần mở điện thoại)")
    ap.add_argument("--set-niche-keywords", nargs=2, metavar=("NGACH", "TU_KHOA"),
                    help="gán từ khóa tìm kiếm cho 1 ngách (vd: --set-niche-keywords A \"loyalty test,street fight\")")
    ap.add_argument("--nurture-all", action="store_true",
                    help="nuôi TẤT CẢ acc đang đăng nhập: mỗi acc ~10 phút rồi đổi acc, theo ngách đã config")
    ap.add_argument("--config-niches", action="store_true",
                    help="lấy danh sách acc trước, rồi hỏi ngách từng acc và lưu")
    ap.add_argument("--nurture", action="store_true",
                    help="nuôi acc tự động: xem hết video rồi lướt như người thật")
    ap.add_argument("--nurture-min", type=int, default=1200,
                    help="nuôi tối thiểu mỗi phiên (giây, mặc định 1200 = 20 phút)")
    ap.add_argument("--nurture-max", type=int, default=2400,
                    help="nuôi tối đa mỗi phiên (giây, mặc định 2400 = 40 phút)")
    ap.add_argument("--nurture-keywords", default="",
                    help="từ khóa ngách cách nhau bằng dấu phẩy (để trống = chỉ lướt FYP)")
    ap.add_argument("--nurture-likes", type=int, default=8,
                    help="like tối đa mỗi phiên nuôi (0 = không like)")
    args = ap.parse_args()
    log(f"TikTok Phone Poster, ban {VERSION}")

    if args.init:
        try:
            run_init(args.serial)
        except JobError as e:
            log(f"❌ {e}")
            sys.exit(1)
        return

    if args.wifi:
        run_wifi()
        return

    if args.set_niche:
        user, niche = args.set_niche
        user = _norm_user(user)
        niche = (niche or "").strip()
        if not user or not niche:
            log("❌ --set-niche cần username và tên ngách (vd: --set-niche sandracruzkay183 B).")
            sys.exit(1)
        mapping = load_niches()
        mapping[user] = niche
        save_niches(mapping)
        log(f"✅ Đã config: @{user} -> ngách {niche}")
        return

    if args.known_accounts:
        known = load_known()
        niches = load_niches()
        if not known:
            log("Chưa lưu acc nào — chạy mục 5 (Xem các acc) một lần để lưu danh sách.")
            return
        log(f"Các acc đã biết ({len(known)} acc, lưu từ những lần liệt kê trước):")
        for u, e in sorted(known.items()):
            mark = "  ← đang mở (lần liệt kê gần nhất)" if e.get("current") else ""
            n = niches.get(u)
            ntag = f" [ngách: {n}]" if n else " [chưa config ngách]"
            seen = f" (thấy lần cuối {e['last_seen']})" if e.get("last_seen") else ""
            log(f"  • @{u}{mark}{ntag}{seen}")
        return

    if args.set_niche_keywords:
        niche, kws = args.set_niche_keywords
        niche = (niche or "").strip()
        kw_list = [k.strip() for k in (kws or "").split(",") if k.strip()]
        if not niche or not kw_list:
            log("❌ --set-niche-keywords cần tên ngách và ít nhất 1 từ khóa.")
            sys.exit(1)
        mapping = load_niche_keywords()
        mapping[niche] = kw_list
        save_niche_keywords(mapping)
        log(f"✅ Đã config từ khóa cho ngách {niche}: {', '.join(kw_list)}")
        return

    if args.config_niches:
        try:
            d = _connect(args.serial)
        except JobError as e:
            log(f"❌ {e}")
            sys.exit(1)
        try:
            current, accounts = list_logged_in_accounts(
                d, Path(args.dir).resolve())
        except Exception as e:
            where = _dump_debug(d, Path(args.dir).resolve(), "account")
            log(f"❌ {e} — ảnh chụp + cấu trúc màn hình đã lưu ở {where}")
            sys.exit(1)
        known_before = load_known()
        missing = [u for u in known_before if u not in accounts]
        if missing:
            log("ℹ️ Các acc đã biết nhưng hiện không đăng nhập trong app: "
                f"{', '.join('@' + u for u in missing)}")
        record_known(accounts, current)
        mapping = load_niches()
        log(f"Tổng {len(accounts)} acc đã đăng nhập trong app TikTok (gán ngách từng acc, Enter = giữ nguyên):")
        changed = False
        for a in accounts:
            cur = mapping.get(a, "")
            try:
                ans = input(f"  @{a} (hiện tại: {cur or 'chưa có'}) -> ngách nào? ").strip()
            except EOFError:
                ans = ""
            if ans:
                mapping[a] = ans
                changed = True
        stale = [u for u in mapping if u not in accounts]
        if stale:
            log("ℹ️ Các acc sau có trong config nhưng hiện không đăng nhập trong app "
                f"(giữ nguyên, không xóa): {', '.join('@' + u for u in stale)}")
        if changed:
            save_niches(mapping)
            log("✅ Đã lưu config ngách.")
        else:
            log("Không đổi gì.")
        # Pha 2: tu khoa tim kiem cho tung ngach (master setting cho nuoi
        # tat ca — nuoi khong hoi lai tu khoa tung lan chay nua).
        kw_map = load_niche_keywords()
        kw_changed = False
        for niche in sorted(set(mapping.values())):
            cur_kw = kw_map.get(niche, [])
            try:
                ans = input(f"  Từ khóa tìm kiếm cho ngách '{niche}' (hiện tại: "
                            f"{', '.join(cur_kw) or 'chưa có'}; cách nhau bằng dấu "
                            f"phẩy, Enter = giữ nguyên): ").strip()
            except EOFError:
                ans = ""
            if ans:
                kws = [k.strip() for k in ans.split(",") if k.strip()]
                if kws:
                    kw_map[niche] = kws
                    kw_changed = True
        if kw_changed:
            save_niche_keywords(kw_map)
            log("✅ Đã lưu từ khóa ngách.")
        return

    if args.nurture:
        try:
            d = _connect(args.serial)
        except JobError as e:
            log(f"❌ {e}")
            sys.exit(1)
        if args.account:
            try:
                ensure_account(d, args.account)
            except Exception as e:
                where = _dump_debug(d, Path(args.dir).resolve(), "account")
                log(f"❌ Không đảm bảo được đúng acc @{_norm_user(args.account)}: {e} "
                    f"— ảnh chụp + cấu trúc màn hình đã lưu ở {where}")
                sys.exit(1)
        keywords = [k.strip() for k in args.nurture_keywords.split(",") if k.strip()]
        try:
            nurture_session(d, min_s=args.nurture_min, max_s=args.nurture_max,
                            keywords=keywords, like_cap=args.nurture_likes)
        except JobError as e:
            log(f"❌ {e}")
            sys.exit(1)
        return

    if args.nurture_all:
        try:
            d = _connect(args.serial)
        except JobError as e:
            log(f"❌ {e}")
            sys.exit(1)
        try:
            nurture_all(d, Path(args.dir).resolve(),
                        like_cap=args.nurture_likes)
        except JobError as e:
            log(f"❌ {e}")
            sys.exit(1)
        return

    if args.list_accounts or args.switch_to:
        try:
            d = _connect(args.serial)
        except JobError as e:
            log(f"❌ {e}")
            sys.exit(1)
        try:
            if args.list_accounts:
                current, accounts = list_logged_in_accounts(
                    d, Path(args.dir).resolve())
                niches = load_niches()
                log(f"Tổng {len(accounts)} acc đã đăng nhập trong app TikTok:")
                for a in accounts:
                    mark = "  ← đang mở" if a == current else ""
                    n = niches.get(a)
                    ntag = f" [ngách: {n}]" if n else " [chưa config ngách]"
                    log(f"  • @{a}{mark}{ntag}")
                record_known(accounts, current)
                log("Đã lưu danh sách acc — lần sau mục 3/4/6/10 và GUI sẽ gợi ý từ danh sách này.")
            else:
                now = switch_account(d, args.switch_to)
                record_known([now], now)
                log(f"Xong: acc đang mở là @{now}")
        except Exception as e:
            where = _dump_debug(d, Path(args.dir).resolve(), "account")
            log(f"❌ {e} — ảnh chụp + cấu trúc màn hình đã lưu ở {where}")
            sys.exit(1)
        return

    root = Path(args.dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    jobs = find_jobs(root)
    if not jobs:
        log(f"Không có video nào trong {root} — thả .mp4 (+ .txt caption cùng tên) vào đó rồi chạy lại.")
        return
    if args.max_posts:
        jobs = jobs[: args.max_posts]
    log(f"Hàng đợi: {len(jobs)} video trong {root}")

    try:
        d = _connect(args.serial)
    except JobError as e:
        log(f"❌ {e} — chưa đăng gì.")
        return
    tag = tag_for_account(args.account, args.account_tag)
    if tag and not args.account_tag.strip() and args.account:
        log(f"Acc @{_norm_user(args.account)} đã config ngách {tag} — "
            f"file xong/lỗi sẽ vào _done-{tag}/_failed-{tag}.")
    prefix = f"[{tag}] " if tag else ""

    if args.account:
        try:
            ensure_account(d, args.account)
        except Exception as e:
            where = _dump_debug(d, root, "account")
            log(f"❌ Không đảm bảo được đúng acc @{_norm_user(args.account)}: {e}")
            log(f"   Ảnh chụp + cấu trúc màn hình ở {where} — DỪNG, chưa đăng gì.")
            return

    if not args.no_warmup:
        warmup_feed(d, min_s=args.warmup_min, max_s=args.warmup_max)

    posted = failed = 0
    for i, job in enumerate(jobs):
        if i > 0:
            gap = random.randint(args.gap_min, args.gap_max)
            log(f"⏳ Nghỉ {gap}s cho giống người thật...")
            time.sleep(gap)
        log(f"===== {prefix}{i + 1}/{len(jobs)}: {job['video'].name} =====")
        if args.account:
            try:
                ensure_account(d, args.account)
            except Exception as e:
                where = _dump_debug(d, root, job["video"].stem)
                log(f"❌ Sai acc trước khi đăng {job['video'].name}: {e} — DỪNG cả "
                    f"lần chạy, video còn nguyên trong hàng đợi. Xem {where}")
                return
        try:
            result = post_one(d, job, root, dry_run=args.dry_run,
                              keep_on_phone=args.keep_on_phone)
            if result == "posted":
                posted += 1
                _move_job(root, job, "_done", tag)
        except Exception as e:
            failed += 1
            where = _dump_debug(d, root, job["video"].stem)
            log(f"❌ Lỗi: {e} — ảnh chụp + cấu trúc màn hình đã lưu ở {where}")
            _move_job(root, job, "_failed", tag)
            try:
                d.app_start(TIKTOK_PKG, stop=False)
            except Exception:
                pass
    log(f"Hoàn tất: đăng {posted}, lỗi {failed}, dry-run/khác {len(jobs) - posted - failed}.")


if __name__ == "__main__":
    main()
