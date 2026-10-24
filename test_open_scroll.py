#!/usr/bin/env python3
"""Test mức 1: mở app TikTok và lướt feed — chưa đăng, chưa bấm gì khác.

    python phone_poster.py --init        # (nếu chưa cài agent)
    python test_open_scroll.py           # mở TikTok, lướt 5 video
    python test_open_scroll.py --scrolls 8 --serial 192.168.1.50:5555

Giữa mỗi lần lướt, script dừng xem ngẫu nhiên vài giây như người thật.
Cuối buổi test chụp màn hình vào test_scroll.png để đối chiếu.
"""
from __future__ import annotations

import argparse
import random
import time
from pathlib import Path

from phone_poster import TIKTOK_PKG, TXT_DISMISS, _try_click, jitter, log


def run_scroll(d, scrolls=5, watch_min=4.0, watch_max=10.0, shot_path=None):
    """Mở TikTok trên thiết bị d và lướt `scrolls` video. True nếu ổn."""
    d.screen_on()
    try:
        d.unlock()
    except Exception:
        pass
    d.app_start(TIKTOK_PKG, stop=False)
    jitter(3.0, 5.0)

    current = {}
    try:
        current = d.app_current()
    except Exception:
        pass
    pkg = current.get("package", "")
    log(f"App đang mở: {pkg or '(không đọc được)'}")
    if pkg and pkg != TIKTOK_PKG:
        log(f"⚠️ App phía trước không phải TikTok ({pkg}) — kiểm tra lại máy.")
        return False

    for _ in range(3):  # dẹp popup nếu có
        if not _try_click(d, TXT_DISMISS, timeout=0.8):
            break
        jitter(0.8, 1.5)

    w, h = d.window_size()
    log(f"Bắt đầu lướt {scrolls} video (màn hình {w}x{h})...")
    for i in range(scrolls):
        x = int(w * random.uniform(0.46, 0.54))
        # Vuot DAI + NHANH nhu _swipe_next: vuot ngan/cham bi TikTok keo tra lai
        y1 = int(h * random.uniform(0.80, 0.88))
        y2 = int(h * random.uniform(0.12, 0.20))
        d.swipe(x, y1, x, y2, 0.25)
        watch = random.uniform(watch_min, watch_max)
        log(f"  · video {i + 1}/{scrolls} — xem {watch:.0f}s rồi lướt tiếp")
        time.sleep(watch)
    if shot_path:
        d.screenshot(str(shot_path))
        log(f"Đã chụp màn hình cuối buổi test: {shot_path}")
    log("✅ Test mở app + lướt xong — điện thoại nghe lệnh tốt.")
    return True


def main():
    ap = argparse.ArgumentParser(description="Test mở TikTok + lướt feed")
    ap.add_argument("--serial", default="", help="serial ADB hoặc IP:5555")
    ap.add_argument("--scrolls", type=int, default=5, help="số video sẽ lướt qua")
    ap.add_argument("--watch-min", type=float, default=4.0)
    ap.add_argument("--watch-max", type=float, default=10.0)
    args = ap.parse_args()

    import uiautomator2 as u2
    d = u2.connect(args.serial or "")
    log(f"Đã kết nối: {d.info.get('productName')}")
    ok = run_scroll(d, scrolls=args.scrolls, watch_min=args.watch_min,
                    watch_max=args.watch_max,
                    shot_path=Path(__file__).with_name("test_scroll.png"))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
