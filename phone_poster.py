#!/usr/bin/env python3
"""Tự động chuyển video sang điện thoại Android và đăng lên TikTok.

Luồng: quét một thư mục hàng đợi trên PC -> với mỗi video: đẩy file sang
điện thoại qua ADB -> mở app TikTok, bấm đăng như người dùng thật
(uiautomator2) -> dán caption từ file .txt đi kèm -> bấm Đăng.

Ghép cặp video/caption: video `x.mp4` lấy caption từ `x.txt` hoặc
`x_caption.txt` trong CÙNG thư mục; quét đệ quy nên trỏ vào thư mục xuất
của clipgen (mỗi story một folder con chứa video + caption) là chạy luôn.

    python phone_poster.py --init            # cài agent lên điện thoại (USB, 1 lần)
    python phone_poster.py --dir D:\\outbox --dry-run   # chạy thử, dừng trước nút Đăng
    python phone_poster.py --dir D:\\outbox             # đăng thật

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


def _move_job(root: Path, job: dict, bucket: str):
    dest_dir = root / bucket
    dest_dir.mkdir(exist_ok=True)
    for f in (job["video"], job["caption_file"]):
        if f is not None and f.exists():
            shutil.move(str(f), str(dest_dir / f.name))


# ------------------------------------------------------------- UI helpers ----
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
                        el.click()
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
        d.click(best[1], best[2])
        return True
    # Dự phòng: vị trí tương đối của ô đầu tiên trong lưới
    d.click(int(w * 0.17), int(h * 0.32))
    return True


# -------------------------------------------------------------- one post ----
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

    d.screen_on()
    try:
        d.unlock()
    except Exception:
        pass
    d.app_start(TIKTOK_PKG, stop=False)
    jitter(3.0, 5.0)
    for _ in range(3):  # dẹp popup cho phép/thông báo nếu có
        if not _try_click(d, TXT_DISMISS, timeout=0.8):
            break
        jitter(0.8, 1.5)

    log("→ Mở màn hình tạo video")
    if not _try_click(d, TXT_CREATE, timeout=5.0):
        w, h = d.window_size()
        d.click(w // 2, int(h * 0.93))  # nút + ở giữa thanh dưới
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
    field.click()
    jitter()
    try:
        field.set_text(caption)
    except Exception:
        d.send_keys(caption, clear=True)
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
    ap.add_argument("--init", action="store_true", help="cài agent + kiểm tra kết nối rồi thoát")
    args = ap.parse_args()

    if args.init:
        run_init(args.serial)
        return

    import uiautomator2 as u2
    root = Path(args.dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    jobs = find_jobs(root)
    if not jobs:
        log(f"Không có video nào trong {root} — thả .mp4 (+ .txt caption cùng tên) vào đó rồi chạy lại.")
        return
    if args.max_posts:
        jobs = jobs[: args.max_posts]
    log(f"Hàng đợi: {len(jobs)} video trong {root}")

    d = u2.connect(args.serial or "")
    log(f"Đã kết nối điện thoại: {d.info.get('productName')}")

    posted = failed = 0
    for i, job in enumerate(jobs):
        if i > 0:
            gap = random.randint(args.gap_min, args.gap_max)
            log(f"⏳ Nghỉ {gap}s cho giống người thật...")
            time.sleep(gap)
        log(f"===== {i + 1}/{len(jobs)}: {job['video'].name} =====")
        try:
            result = post_one(d, job, root, dry_run=args.dry_run,
                              keep_on_phone=args.keep_on_phone)
            if result == "posted":
                posted += 1
                _move_job(root, job, "_done")
        except Exception as e:
            failed += 1
            where = _dump_debug(d, root, job["video"].stem)
            log(f"❌ Lỗi: {e} — ảnh chụp + cấu trúc màn hình đã lưu ở {where}")
            _move_job(root, job, "_failed")
            try:
                d.app_start(TIKTOK_PKG, stop=False)
            except Exception:
                pass
    log(f"Hoàn tất: đăng {posted}, lỗi {failed}, dry-run/khác {len(jobs) - posted - failed}.")


if __name__ == "__main__":
    main()
