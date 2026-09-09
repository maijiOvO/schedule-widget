# -*- coding: utf-8 -*-
"""常驻桌面的日程组件。

一个无边框半透明小窗，钉在桌面角落，一直显示：现在在上什么课（带进度条）、
下一件事还有多久、今天剩下什么、接下来的截止、下一场考试倒计时。
每 15 秒自己刷新，不用点任何东西。

数据来自 data.py，和 ics、学期日程.md、壁纸同源。

    pythonw _schedule/widget.py              # 启动（不带控制台窗口）
    python  _schedule/widget.py --startup    # 装进开机自启
    python  _schedule/widget.py --unstartup  # 取消开机自启
    python  _schedule/widget.py --shot out.png   # 截一张当前样子，用来调样式

鼠标操作：拖动移动位置（自动记住）· 悬停变清晰 · 右键菜单 · 双击打开学期日程.md
"""
import ctypes
import datetime as dt
import json
import os
import subprocess
import sys
import tkinter as tk
import tkinter.font as tkfont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data import (NO_CLASS, READING_WEEK, TERM_END, TERM_START, classes_on,
                  next_exam, upcoming, urgency, week_no, when_cn)

HERE = os.path.dirname(os.path.abspath(__file__))
POS_FILE = os.path.join(HERE, ".widget_pos.json")
SCHEDULE_MD = os.path.join(HERE, "..", "学期日程.md")

def dpi_scale():
    """这台机器的显示缩放：96 DPI = 100% = 1.0，144 DPI = 150% = 1.5。
    笔记本多半不是 100%，尺寸和字号都得跟着走，否则组件会缩成一小块。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)   # 必须在建窗口前
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            return 1.0, 96
    try:
        dpi = ctypes.windll.user32.GetDpiForSystem()
    except Exception:
        dpi = 96
    return dpi / 96.0, dpi


UI_SCALE = 1.0   # 嫌大就调小（0.85 之类），嫌小就调大。1.0 = 完全跟随系统缩放

_sys_scale, DPI = dpi_scale()
SCALE = _sys_scale * UI_SCALE

WIDTH = 440          # 以下都是 100% 缩放下的逻辑像素，
PAD = 20             # 画完之后整块按 SCALE 放大（见 render 末尾）
REFRESH_MS = 15_000
TODO_MAX = 4      # 「该动手了」最多列几条
REST_MAX = 6      # 「接下来」最多列几条
ALPHA_IDLE, ALPHA_HOVER = 0.92, 1.0

BG      = "#12161c"
FG      = "#e6edf3"
DIM     = "#7d8590"
FAINT   = "#4a525c"
LINE    = "#262c34"
BLUE    = "#79c0ff"
GREEN   = "#56d364"
PURPLE  = "#c6a0f6"
URG     = ["#ff7b72", "#ffa657", "#d2b464", "#7d8590"]   # data.urgency() 四级
NOW_BG  = "#1b2430"

WEEK_CN = "一二三四五六日"


def mins(t):
    return t[0] * 60 + t[1]


def kind_color(k):
    return {"lab": GREEN, "exam": PURPLE}.get(k, BLUE)


def human_gap(m):
    """把分钟数说成人话"""
    if m < 1:
        return "马上"
    if m < 60:
        return f"{m} 分钟后"
    h, r = divmod(m, 60)
    if h < 24:
        return f"{h} 小时后" if r == 0 else f"{h} 小时 {r} 分后"
    return f"{h // 24} 天后"


class Widget:
    def __init__(self, root, today=None, now=None):
        self.root = root
        self.fixed_today, self.fixed_now = today, now
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", ALPHA_IDLE)
        root.configure(bg=BG)

        root.tk.call("tk", "scaling", DPI / 72.0)   # 字体按真实 DPI 排版
        self.canvas = tk.Canvas(root, width=int(WIDTH * SCALE), bg=BG,
                                highlightthickness=1, highlightbackground=LINE, bd=0)
        self.canvas.pack()

        self.f_time  = tkfont.Font(family="Microsoft YaHei", size=19, weight="bold")
        self.f_date  = tkfont.Font(family="Microsoft YaHei", size=10)
        self.f_head  = tkfont.Font(family="Microsoft YaHei", size=8)
        self.f_big   = tkfont.Font(family="Microsoft YaHei", size=12, weight="bold")
        self.f_body  = tkfont.Font(family="Microsoft YaHei", size=10)
        self.f_small = tkfont.Font(family="Microsoft YaHei", size=9)

        self._drag = None
        for w in (root, self.canvas):
            w.bind("<Button-1>", self.on_press)
            w.bind("<B1-Motion>", self.on_drag)
            w.bind("<Double-Button-1>", lambda e: self.open_md())
            w.bind("<Button-3>", self.on_menu)
            w.bind("<Enter>", lambda e: root.attributes("-alpha", ALPHA_HOVER))
            w.bind("<Leave>", lambda e: root.attributes("-alpha", ALPHA_IDLE))

        self.menu = tk.Menu(root, tearoff=0, bg="#1c2128", fg=FG,
                            activebackground="#30363d", activeforeground=FG,
                            bd=0, font=("Microsoft YaHei", 9))
        self.menu.add_command(label="打开学期日程.md", command=self.open_md)
        self.menu.add_command(label="立即刷新", command=self.render)
        self.menu.add_separator()
        self.topmost = tk.BooleanVar(value=True)
        self.menu.add_checkbutton(label="总在最前", variable=self.topmost,
                                  command=lambda: root.attributes("-topmost", self.topmost.get()))
        self.menu.add_command(label="回到右上角", command=self.reset_pos)
        self.menu.add_separator()
        self.menu.add_command(label="退出", command=root.destroy)

        self.restore_pos()
        self.render()
        self.tick()

    # ---- 位置 ----
    def restore_pos(self):
        """恢复上次的位置。换台机器（屏幕更小）时存的坐标可能已经在屏幕外，
        那样组件就永远看不见了 —— 越界就退回右上角。"""
        try:
            with open(POS_FILE, encoding="utf-8") as fh:
                p = json.load(fh)
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            x, y = int(p["x"]), int(p["y"])
            if not (-40 <= x <= sw - 120 and -10 <= y <= sh - 120):
                raise ValueError("上次的位置不在这块屏幕上")
            self.root.geometry(f"+{x}+{y}")
        except Exception:
            self.reset_pos()

    def reset_pos(self):
        sw = self.root.winfo_screenwidth()
        self.root.geometry(f"+{sw - int(WIDTH * SCALE) - 36}+{48}")
        self.save_pos()

    def save_pos(self):
        try:
            with open(POS_FILE, "w", encoding="utf-8") as fh:
                json.dump({"x": self.root.winfo_x(), "y": self.root.winfo_y()}, fh)
        except Exception:
            pass

    def on_press(self, e):
        self._drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def on_drag(self, e):
        if self._drag:
            self.root.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")
            self.save_pos()

    def on_menu(self, e):
        self.menu.tk_popup(e.x_root, e.y_root)

    def open_md(self):
        try:
            os.startfile(os.path.abspath(SCHEDULE_MD))
        except Exception:
            pass

    # ---- 画 ----
    def txt(self, x, y, s, font, fill, anchor="nw", maxw=None):
        if maxw and font.measure(s) > maxw:      # 放不下就截断，别画出边框
            while s and font.measure(s + "…") > maxw:
                s = s[:-1]
            s += "…"
        return self.canvas.create_text(x, y, text=s, font=font, fill=fill, anchor=anchor)

    def rule(self, y):
        self.canvas.create_line(PAD, y, WIDTH - PAD, y, fill=LINE)

    def render(self):
        c = self.canvas
        c.delete("all")
        now = self.fixed_now or dt.datetime.now()
        today = self.fixed_today or now.date()
        nm = now.hour * 60 + now.minute
        y = 18

        # ── 时间 / 日期 ──
        self.txt(PAD, y, f"{now:%H:%M}", self.f_time, FG)
        self.txt(WIDTH - PAD, y + 1, f"{today.month}月{today.day}日 周{WEEK_CN[today.weekday()]}",
                 self.f_date, DIM, "ne")
        tag = f"第 {week_no(today)} 周"
        if today in READING_WEEK:
            tag += " · Reading Week"
        elif today in NO_CLASS:
            tag += " · 停课"
        elif not (TERM_START <= today <= TERM_END):
            tag = "学期外"
        self.txt(WIDTH - PAD, y + 30, tag, self.f_small, FAINT, "ne")
        y += 58
        self.rule(y)
        y += 14

        # ── 现在 / 下一节 ──
        cls = classes_on(today)
        cur = next((k for k in cls if mins(k[0]) <= nm < mins(k[1])), None)
        nxt = next((k for k in cls if mins(k[0]) > nm), None)

        if cur:
            (h1, m1), (h2, m2), title, room, kind = cur
            col = kind_color(kind)
            c.create_rectangle(PAD - 8, y - 6, WIDTH - PAD + 8, y + 68,
                               fill=NOW_BG, outline="")
            self.txt(PAD, y, "正在上", self.f_head, DIM)
            self.txt(WIDTH - PAD, y, room, self.f_head, DIM, "ne")
            self.txt(PAD, y + 18, title, self.f_big, col)
            left = mins(cur[1]) - nm
            self.txt(WIDTH - PAD, y + 22, f"还剩 {left} 分", self.f_small, DIM, "ne")
            # 进度条
            total = mins(cur[1]) - mins(cur[0])
            frac = 0 if total <= 0 else (nm - mins(cur[0])) / total
            bx0, bx1, by = PAD, WIDTH - PAD, y + 56
            c.create_line(bx0, by, bx1, by, fill=LINE, width=3)
            c.create_line(bx0, by, bx0 + (bx1 - bx0) * frac, by, fill=col, width=3)
            y += 84
        elif nxt:
            (h1, m1), _e, title, room, kind = nxt
            self.txt(PAD, y, "下一节", self.f_head, DIM)
            self.txt(PAD, y + 18, f"{h1:02d}:{m1:02d}", self.f_big, kind_color(kind))
            self.txt(PAD + 78, y + 20, title, self.f_body, FG)
            self.txt(WIDTH - PAD, y + 20, room, self.f_small, DIM, "ne")
            self.txt(PAD, y + 44, human_gap(mins(nxt[0]) - nm), self.f_small, DIM)
            y += 68
        else:
            note = ("Reading Week" if today in READING_WEEK else
                    "今天放假" if today in NO_CLASS else
                    "今天没课" if not cls else "今天的课上完了")
            self.txt(PAD, y, note, self.f_body, DIM)
            y += 32

        # ── 今天剩下 ──
        rest = [k for k in cls if mins(k[0]) > nm]
        if not cur and nxt and rest and rest[0] is nxt:
            rest = rest[1:]      # 只有真的画了「下一节」时才去重；正在上课时它没画
        if rest:
            self.rule(y)
            y += 14
            self.txt(PAD, y, "今天剩下", self.f_head, DIM)
            y += 22
            for (h1, m1), _e, title, room, kind in rest[:5]:
                c.create_rectangle(PAD, y + 4, PAD + 3, y + 17,
                                   fill=kind_color(kind), outline="")
                self.txt(PAD + 12, y, f"{h1:02d}:{m1:02d}", self.f_small, kind_color(kind))
                self.txt(PAD + 76, y, title, self.f_body, FG,
                         maxw=(WIDTH - PAD - 60 - (PAD + 76)) * SCALE)
                self.txt(WIDTH - PAD, y + 1, room, self.f_small, FAINT, "ne")
                y += 26
            y += 6

        # ── 该动手了 / 接下来 ──
        for span in (14, 21, 28, 45):
            items = [it for it in upcoming(today, span)
                     if it.date != today or mins(it.at) >= nm]   # 今天已过点的不再显示
            if len(items) >= 5:
                break

        # 已经到该动手的日子、还没过截止的，单独拎出来放最上面
        todo = [it for it in items if it.started(today) and it.needs_work]
        rest = [it for it in items if it not in todo]

        if todo:
            self.rule(y)
            y += 14
            self.txt(PAD, y, "该动手了", self.f_head, DIM)
            y += 22
            for it in todo[:TODO_MAX]:
                n = it.days_left(today)
                col = URG[urgency(n)] if it.hard or it.kind == "exam" else DIM
                is_exam = it.kind == "exam"
                c.create_oval(PAD, y + 7, PAD + 7, y + 14,
                              fill=PURPLE if is_exam else col, outline="")
                label = it.label
                w = self.txt(PAD + 18, y, label, self.f_body,
                             PURPLE if is_exam else FG,
                             maxw=(WIDTH - PAD - 88 - (PAD + 18)) * SCALE)
                bx = self.canvas.bbox(w)[2]
                self.txt(bx + 10, y + 2,
                         "复习" if it.hours is None else f"{it.hours:g}h",
                         self.f_small, FAINT)
                tail = ("今天 %02d:%02d" % it.at) if n == 0 else when_cn(n)
                self.txt(WIDTH - PAD, y + 1, tail, self.f_small, col, "ne")
                y += 26
            if len(todo) > TODO_MAX:
                self.txt(PAD + 18, y, f"⋯ 还有 {len(todo) - TODO_MAX} 件", self.f_small, FAINT)
                y += 24
            y += 6

        if rest:
            self.rule(y)
            y += 14
            self.txt(PAD, y, "接下来", self.f_head, DIM)
            y += 22
            last = None
            for it in rest[:REST_MAX]:
                n = it.days_left(today)
                col = URG[urgency(n)] if it.hard else DIM
                if it.date != last:
                    lab_col = URG[urgency(n)] if any(
                        x.hard for x in rest if x.date == it.date) else DIM
                    self.txt(PAD, y + 1, when_cn(n), self.f_small, lab_col)
                    last = it.date
                if it.kind == "exam":
                    c.create_rectangle(PAD + 72, y + 6, PAD + 80, y + 15,
                                       fill=PURPLE, outline="")
                elif it.hard:
                    c.create_oval(PAD + 72, y + 7, PAD + 79, y + 14, fill=col, outline="")
                self.txt(WIDTH - PAD, y + 1, "%02d:%02d" % it.at,
                         self.f_small, FAINT, "ne")
                self.txt(PAD + 92, y, it.text,
                         self.f_body if it.hard else self.f_small,
                         PURPLE if it.kind == "exam" else (FG if it.hard else DIM),
                         maxw=(WIDTH - PAD - 52 - (PAD + 92)) * SCALE)
                y += 25
            if len(rest) > REST_MAX:
                self.txt(PAD + 92, y, f"⋯ 还有 {len(rest) - REST_MAX} 项", self.f_small, FAINT)
                y += 25
            y += 6

        # ── 下一场考试 ──
        nx = next_exam(today)
        # 上面「接下来」已经列出来的考试就不再重复一遍
        shown = {it.date for it in items if it.kind == "exam"}
        if nx and nx[0] not in shown:
            ed, course, name, (h1, m1) = nx
            n = (ed - today).days
            self.rule(y)
            y += 14
            self.txt(PAD, y, "下一场考试", self.f_head, DIM)
            self.txt(WIDTH - PAD, y, f"{ed.month}/{ed.day} {h1:02d}:{m1:02d}",
                     self.f_head, FAINT, "ne")
            self.txt(PAD, y + 20, f"{course} {name}", self.f_body, FG)
            cd = "就是今天" if n == 0 else "明天" if n == 1 else f"{n} 天"
            self.txt(WIDTH - PAD, y + 21, cd, self.f_small, URG[urgency(n)], "ne")
            y += 50

        y += 12
        # 上面全程用逻辑坐标画，这里一次性缩放到物理像素 —— 字体已由 tk scaling 处理
        if SCALE != 1.0:
            c.scale("all", 0, 0, SCALE, SCALE)
        h = int(y * SCALE)
        c.configure(width=int(WIDTH * SCALE), height=h)
        self.root.geometry(f"{int(WIDTH * SCALE)}x{h}")

    def tick(self):
        self.render()
        self.root.after(REFRESH_MS, self.tick)


# ---- 开机自启 -------------------------------------------------------------
def startup_path():
    return os.path.join(os.environ["APPDATA"], "Microsoft", "Windows",
                        "Start Menu", "Programs", "Startup", "Study日程组件.vbs")


def install_startup():
    pyw = sys.executable.replace("python.exe", "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = sys.executable
    script = os.path.join(HERE, "widget.py")
    vbs = ('Set s = CreateObject("WScript.Shell")\r\n'
           f's.Run """{pyw}"" ""{script}""", 0, False\r\n')
    with open(startup_path(), "w", encoding="utf-8") as fh:
        fh.write(vbs)
    print("已装进开机自启：", startup_path())


def remove_startup():
    p = startup_path()
    if os.path.exists(p):
        os.remove(p)
        print("已取消开机自启")
    else:
        print("本来就没装")


def main():
    if "--startup" in sys.argv:
        return install_startup()
    if "--unstartup" in sys.argv:
        return remove_startup()

    root = tk.Tk()
    today = now = None
    if "--at" in sys.argv:    # 调样式用：--at 2026-10-05T09:30
        now = dt.datetime.fromisoformat(sys.argv[sys.argv.index("--at") + 1])
        today = now.date()
    w = Widget(root, today, now)

    if "--shot" in sys.argv:
        out = sys.argv[sys.argv.index("--shot") + 1]
        root.attributes("-alpha", 1.0)   # 截图要看清样式，不要透出桌面
        root.update()
        root.update_idletasks()
        from PIL import ImageGrab
        x, y = root.winfo_rootx(), root.winfo_rooty()
        img = ImageGrab.grab((x, y, x + root.winfo_width(), y + root.winfo_height()))
        img.save(out)
        print("截图", out, img.size)
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    main()
