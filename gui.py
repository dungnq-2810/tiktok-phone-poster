#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Giao diện đồ họa (tkinter, chỉ dùng thư viện chuẩn) cho TikTok Phone Poster.

Chạy bằng cách nhấp đúp gui.bat (Windows). Mọi nút bấm chỉ gọi lại các
lệnh CLI của phone_poster.py / test_open_scroll.py — không sửa logic đăng.
"""

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
POSTER = os.path.join(SCRIPT_DIR, "phone_poster.py")
SCROLL_TEST = os.path.join(SCRIPT_DIR, "test_open_scroll.py")
DEFAULT_QUEUE = os.path.join(SCRIPT_DIR, "outbox")


class Gui:
    def __init__(self, root):
        self.root = root
        root.title("TikTok Phone Poster")
        root.geometry("900x650")

        self.proc = None          # subprocess đang chạy (hoặc None)
        self.out_queue = queue.Queue()
        self.action_buttons = []  # các nút lệnh, khóa khi đang chạy

        # ---- (a) Thư mục hàng đợi -------------------------------------
        frm_q = tk.LabelFrame(root, text="Thư mục hàng đợi")
        frm_q.pack(fill="x", padx=8, pady=4)
        self.queue_var = tk.StringVar(value=DEFAULT_QUEUE)
        tk.Entry(frm_q, textvariable=self.queue_var).pack(
            side="left", fill="x", expand=True, padx=4, pady=4)
        tk.Button(frm_q, text="Chọn...", command=self.choose_queue).pack(
            side="left", padx=4, pady=4)

        # ---- (b) Acc đăng ----------------------------------------------
        frm_a = tk.LabelFrame(root, text="Acc đăng")
        frm_a.pack(fill="x", padx=8, pady=4)
        self.account_var = tk.StringVar()
        self.account_box = ttk.Combobox(frm_a, textvariable=self.account_var)
        self.account_box.pack(side="left", fill="x", expand=True,
                              padx=4, pady=4)
        self.account_box["values"] = self.known_usernames()
        tk.Button(frm_a, text="↻", command=self.refresh_known).pack(
            side="left", padx=4, pady=4)
        tk.Label(frm_a, text="Để trống = dùng acc đang mở trong app. "
                 "Chọn trong danh sách đã lưu hoặc gõ @username. Nút ↻ tải "
                 "lại danh sách (chạy 'Xem các acc' để cập nhật).").pack(
                     side="left", padx=4, pady=4)

        # ---- (b2) Nuôi acc: từ khóa ngách -------------------------------
        frm_n = tk.LabelFrame(root, text="Nuôi acc: từ khóa ngách")
        frm_n.pack(fill="x", padx=8, pady=4)
        self.keywords_var = tk.StringVar()
        tk.Entry(frm_n, textvariable=self.keywords_var).pack(
            side="left", fill="x", expand=True, padx=4, pady=4)
        tk.Label(frm_n, text="Cách nhau bằng dấu phẩy. Để trống = chỉ "
                 "lướt FYP, không tìm kiếm.").pack(side="left", padx=4, pady=4)

        # ---- (c) Tùy chọn (chỉ áp dụng cho 2 nút đăng) ------------------
        frm_o = tk.LabelFrame(root, text="Tùy chọn đăng")
        frm_o.pack(fill="x", padx=8, pady=4)
        # Khong co checkbox dry-run: 2 nut "Dang thu"/"Dang that" la bo chon
        # duy nhat (checkbox cu tung gay hieu lam: tick dry-run roi bam "Dang
        # that" van dang that ma lai khong hoi xac nhan).
        self.no_warmup_var = tk.BooleanVar(value=False)
        self.keep_var = tk.BooleanVar(value=False)
        tk.Checkbutton(frm_o, text="Bỏ qua lướt feed warmup",
                       variable=self.no_warmup_var).grid(
                           row=0, column=0, sticky="w", padx=4, pady=2)
        tk.Checkbutton(frm_o, text="Giữ video trên điện thoại",
                       variable=self.keep_var).grid(
                           row=0, column=1, sticky="w", padx=4, pady=2)
        tk.Label(frm_o, text="Tối đa số video (0 = tất cả):").grid(
            row=1, column=0, sticky="w", padx=4, pady=2)
        self.max_posts_var = tk.StringVar(value="0")
        tk.Entry(frm_o, textvariable=self.max_posts_var, width=8).grid(
            row=1, column=1, sticky="w", padx=4, pady=2)
        tk.Label(frm_o, text="Nghỉ giữa 2 lần đăng: từ").grid(
            row=2, column=0, sticky="w", padx=4, pady=2)
        self.gap_min_var = tk.StringVar(value="240")
        self.gap_max_var = tk.StringVar(value="540")
        tk.Entry(frm_o, textvariable=self.gap_min_var, width=8).grid(
            row=2, column=1, sticky="w", padx=4, pady=2)
        # cụm "đến ... giây" nằm cùng hàng, gom trong frame nhỏ
        frm_gap = tk.Frame(frm_o)
        frm_gap.grid(row=2, column=2, sticky="w", padx=4, pady=2)
        tk.Label(frm_gap, text="đến").pack(side="left")
        tk.Entry(frm_gap, textvariable=self.gap_max_var, width=8).pack(
            side="left", padx=4)
        tk.Label(frm_gap, text="giây").pack(side="left")

        # ---- (d) Các nút lệnh -------------------------------------------
        frm_b = tk.LabelFrame(root, text="Lệnh")
        frm_b.pack(fill="x", padx=8, pady=4)
        buttons = [
            ("1. Cài agent", self.cmd_init),
            ("2. Test lướt feed", self.cmd_scroll_test),
            ("3. Đăng thử (dry-run)", self.cmd_dry_run),
            ("4. Đăng thật", self.cmd_post),
            ("5. Xem các acc", self.cmd_list_accounts),
            ("6. Đổi acc", self.cmd_switch),
            ("7. Wi-Fi ADB", self.cmd_wifi),
            ("8. Config acc theo ngách", self.cmd_config_niches),
            ("9. Nuôi acc tự động", self.cmd_nurture),
        ]
        for i, (label, cmd) in enumerate(buttons):
            btn = tk.Button(frm_b, text=label, command=cmd, width=28)
            btn.grid(row=i // 2, column=i % 2, padx=4, pady=3, sticky="ew")
            self.action_buttons.append(btn)
        frm_b.columnconfigure(0, weight=1)
        frm_b.columnconfigure(1, weight=1)

        # ---- (e) Log ------------------------------------------------------
        frm_l = tk.LabelFrame(root, text="Log")
        frm_l.pack(fill="both", expand=True, padx=8, pady=4)
        self.log = scrolledtext.ScrolledText(frm_l, state="disabled")
        self.log.pack(fill="both", expand=True, padx=4, pady=4)

        # ---- (f) Trả lời tiến trình + (g) Dừng / Xóa log ------------------
        frm_r = tk.Frame(root)
        frm_r.pack(fill="x", padx=8, pady=4)
        tk.Label(frm_r, text="Trả lời:").pack(side="left", padx=4)
        self.reply_var = tk.StringVar()
        self.reply_entry = tk.Entry(frm_r, textvariable=self.reply_var)
        self.reply_entry.pack(side="left", fill="x", expand=True, padx=4)
        self.reply_entry.bind("<Return>", lambda _e: self.send_reply())
        tk.Button(frm_r, text="Gửi", command=self.send_reply).pack(
            side="left", padx=4)
        self.stop_btn = tk.Button(frm_r, text="Dừng", command=self.stop_proc,
                                  state="disabled")
        self.stop_btn.pack(side="left", padx=4)
        tk.Button(frm_r, text="Xóa log", command=self.clear_log).pack(
            side="left", padx=4)

        self.root.after(100, self.poll)

    # ---- helpers --------------------------------------------------------
    def choose_queue(self):
        d = filedialog.askdirectory(initialdir=self.queue_var.get())
        if d:
            self.queue_var.set(d)

    def append_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def known_usernames(self):
        """Đọc known_accounts.json cạnh script: acc đang mở trước, còn
        lại A-Z. File không có/hỏng thì trả [] (vẫn gõ tay được)."""
        try:
            import json
            with open(os.path.join(SCRIPT_DIR, "known_accounts.json"),
                      encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return []
        if not isinstance(data, dict):
            return []
        cur = [u for u, e in data.items()
               if isinstance(e, dict) and e.get("current")]
        rest = sorted(u for u in data if u not in cur)
        return ["@" + u for u in cur + rest]

    def refresh_known(self):
        self.account_box["values"] = self.known_usernames()

    def account(self):
        return self.account_var.get().strip().lstrip("@")

    def post_options(self):
        """Đọc các tùy chọn đăng; sai định dạng số thì báo và trả None."""
        try:
            max_posts = int(self.max_posts_var.get().strip())
            gap_min = int(self.gap_min_var.get().strip())
            gap_max = int(self.gap_max_var.get().strip())
        except ValueError:
            messagebox.showwarning(
                "Số không hợp lệ",
                "Tối đa số video và khoảng nghỉ phải là số nguyên.")
            return None
        args = ["--dir", self.queue_var.get().strip()]
        if self.account():
            args += ["--account", self.account()]
        if self.no_warmup_var.get():
            args.append("--no-warmup")
        if self.keep_var.get():
            args.append("--keep-on-phone")
        if max_posts > 0:
            args += ["--max-posts", str(max_posts)]
        args += ["--gap-min", str(gap_min), "--gap-max", str(gap_max)]
        return args

    def run(self, script, args):
        """Chạy 1 lệnh trong luồng nền; log đổ về qua queue (không ghi
        trực tiếp vào widget từ luồng nền)."""
        if self.proc is not None and self.proc.poll() is None:
            messagebox.showinfo("Đang chạy",
                                "Đang có lệnh chạy rồi, đợi xong hãy chạy tiếp.")
            return
        if not os.path.isfile(script):
            messagebox.showerror("Thiếu file",
                                f"Không tìm thấy file:\n{script}")
            return
        cmd = [sys.executable, script] + args
        self.append_log(f"\n$ {' '.join(cmd)}\n")
        try:
            self.proc = subprocess.Popen(
                cmd, cwd=SCRIPT_DIR,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", bufsize=1)
        except OSError as e:
            messagebox.showerror("Không chạy được", f"Không khởi động được "
                                 f"tiến trình:\n{e}")
            self.proc = None
            return
        for btn in self.action_buttons:
            btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        try:
            for line in self.proc.stdout:
                self.out_queue.put(line)
        except Exception:
            pass

    def poll(self):
        try:
            while True:
                self.append_log(self.out_queue.get_nowait())
        except queue.Empty:
            pass
        if self.proc is not None and self.proc.poll() is not None:
            code = self.proc.returncode
            self.append_log(f"--- đã xong (mã thoát {code}) ---\n")
            self.proc = None
            for btn in self.action_buttons:
                btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
        self.root.after(100, self.poll)

    def send_reply(self):
        """Ghi 1 dòng vào stdin của tiến trình đang chạy (dùng cho các
        prompt của config-niches). Không có tiến trình thì không làm gì."""
        if self.proc is None or self.proc.poll() is not None:
            return
        line = self.reply_var.get()
        try:
            self.proc.stdin.write(line + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError):
            return
        self.append_log(f"> {line}\n")
        self.reply_var.set("")

    def stop_proc(self):
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except OSError:
                pass

    # ---- các lệnh ---------------------------------------------------------
    def cmd_init(self):
        self.run(POSTER, ["--init"])

    def cmd_scroll_test(self):
        self.run(SCROLL_TEST, [])

    def cmd_dry_run(self):
        args = self.post_options()
        if args is not None:
            self.run(POSTER, args + ["--dry-run"])

    def cmd_post(self):
        if not messagebox.askyesno(
                "Xác nhận đăng thật",
                "Đăng thật sẽ bấm nút Đăng trên TikTok. Tiếp tục?"):
            return
        args = self.post_options()
        if args is not None:
            self.run(POSTER, args)

    def cmd_list_accounts(self):
        self.run(POSTER, ["--list-accounts"])

    def cmd_switch(self):
        if not self.account():
            messagebox.showwarning(
                "Chưa nhập acc",
                "Nhập @username vào ô \"Acc đăng\" trước khi đổi acc.")
            return
        self.run(POSTER, ["--switch-to", self.account()])

    def cmd_wifi(self):
        self.run(POSTER, ["--wifi"])

    def cmd_config_niches(self):
        self.run(POSTER, ["--config-niches"])

    def cmd_nurture(self):
        args = ["--nurture"]
        if self.account():
            args += ["--account", self.account()]
        kw = self.keywords_var.get().strip()
        if kw:
            args += ["--nurture-keywords", kw]
        self.run(POSTER, args)


def main():
    root = tk.Tk()
    Gui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
