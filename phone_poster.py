#!/usr/bin/env python3
"""Tự động chuyển video sang điện thoại Android và đăng lên TikTok.

Luồng: quét một thư mục hàng đợi trên PC -> với mỗi video: đẩy file sang
điện thoại qua ADB -> mở app TikTok, bấm đăng như người dùng thật
(uiautomator2) -> dán caption từ file .txt đi kèm -> bấm Đăng.

Ghép cặp video/caption: video `x.mp4` lấy caption từ `x.txt` hoặc
`x_caption.txt` trong CÙNG thư mục; quét đệ quy nên trỏ vào thư mục xuất
của clipgen (mỗi story một folder con chứa video + caption) là chạy luôn.

    python phone_poster.py --init            # cài agent lên điện thoại (USB, 1 lần)
    python phone_poster.py --list-accounts   # mở TikTok, liệt kê các acc đã đăng nhập trong app
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

VERSION = "20261024-8"  # in ra đầu mỗi lần chạy để biết chắc đang chạy bản nào

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
def _tap_human(d, el):
    """Bấm vào một điểm ngẫu nhiên BÊN TRONG khung phần tử (né bấm đúng tâm
    như máy — TikTok chấm điểm hành vi bấm trúng y hệt một tọa độ mỗi lần)."""
    try:
        b = el.info.get("bounds") or {}
        l, t, r, btm = b["left"], b["top"], b["right"], b["bottom"]
        if r - l < 8 or btm - t < 8:
            raise ValueError("bounds quá nhỏ")
        mx, my = max(3, (r - l) // 5), max(3, (btm - t) // 5)
        d.click(random.randint(l + mx, r - mx),
                random.randint(t + my, btm - my))
        return True
    except Exception:
        try:
            el.click()  # dự phòng khi không đọc được bounds
            return True
        except Exception:
            return False


def _try_click(d, variants, timeout=6.0, exact_first=True):
    """Bấm phần tử theo text/description trong danh sách biến thể. True nếu bấm được."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for v in variants:
            for kwargs in ({"text": v}, {"description": v},
                           {"textContains": v}, {"descriptionContains": v}):
                try:
                    el = d(**kwargs)
                    if el.exists(timeout=0.3):
                        if _tap_human(d, el):
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
    if _try_click(d, TXT_PROFILE, timeout=4.0):
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
    handles = []
    for handle, _y in _handles_on_screen(d):
        if handle not in handles:
            handles.append(handle)
    # Ghi rõ bảng được nhận biết nhờ điều kiện nào — để phân biệt 'bảng
    # chuyển acc thật chỉ có 1 acc' với 'sheet khác cũng có chữ Add account
    # nên bị nhận nhầm là bảng chuyển acc'.
    log(f"  (bảng nhận biết qua: {len(handles)} @handle, "
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
    for kwargs in ({"text": f"@{target}"}, {"textContains": target},
                   {"descriptionContains": target}):
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
    except Exception:
        field.set_text(text)  # dự phòng: máy nào không gõ được thì dán


def warmup_feed(d, min_s=60, max_s=120, swipes=None):
    """Lướt feed như người thật trước khi đăng: xem mỗi video vài giây rồi
    vuốt lên. Chạy 1 lần mỗi lần chạy tool (không phải mỗi video).
    `swipes=N` để test: vuốt đúng N lần thay vì tính theo thời gian."""
    if swipes is None:
        secs = random.uniform(min_s, max_s)
    else:
        secs = 0
    log(f"→ Khởi động phiên: lướt feed ~{int(secs)}s cho giống người thật")
    _try_click(d, TXT_HOME, timeout=3.0)
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
        time.sleep(random.uniform(5.0, 11.0))  # xem video vài giây như người thật
        x = int(w * random.uniform(0.40, 0.60))
        d.swipe(x, int(h * 0.72), x + random.randint(-15, 15),
                int(h * 0.28), random.uniform(0.3, 0.6))
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

    log("→ Bấm Đăng")
    if not _try_click(d, TXT_POST, timeout=6.0):
        raise JobError("không thấy nút Đăng (Post)")
    time.sleep(12)
    if _exists(d, TXT_UPLOAD_ERROR):
        raise JobError("TikTok báo lỗi tải lên")
    if _exists(d, TXT_POST) and _exists(d, TXT_CAPTION_HINT):
        raise JobError("vẫn ở màn hình đăng sau 12s — có thể chưa đăng được")

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
    try:
        d = u2.connect(serial or "")
        name = d.info.get("productName")
    except Exception:
        raise JobError("không nói chuyện được với điện thoại (cáp lỏng, chưa "
                       "bật USB debugging, hoặc MIUI đã tắt app agent ATX — "
                       "chạy lại menu 1 cài agent, cho app ATX chạy pin "
                       "'Không giới hạn' rồi thử lại)")
    log(f"Đã kết nối điện thoại: {name}")
    return d


def run_init(serial):
    log("Cài agent uiautomator2 lên điện thoại (cần cắm USB + đã bật USB debugging)...")
    cmd = [sys.executable, "-m", "uiautomator2", "init"]
    if serial:
        cmd += ["--serial", serial]
    subprocess.run(cmd, check=False)
    import uiautomator2 as u2
    d = u2.connect(serial or "")
    info = d.info
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
    args = ap.parse_args()
    log(f"TikTok Phone Poster, ban {VERSION}")

    if args.init:
        run_init(args.serial)
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
                log(f"Tổng {len(accounts)} acc đã đăng nhập trong app TikTok:")
                for a in accounts:
                    mark = "  ← đang mở" if a == current else ""
                    log(f"  • @{a}{mark}")
            else:
                now = switch_account(d, args.switch_to)
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
    tag = args.account_tag.strip()
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
