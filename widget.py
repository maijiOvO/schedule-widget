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

鼠标操作：
    拖动           移动位置（自动记住）
    拖右下角       等比缩放整个组件（自动记住）
    双击顶部时间栏 折叠成一行 / 展开
    双击其他地方   打开 学期日程.md
    悬停           从半透明变清晰
    右键           菜单
"""
import ctypes
import datetime as dt
import json
import os
import sys
import tkinter as tk
import tkinter.font as tkfont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data import (NO_CLASS, READING_WEEK, TERM_END, TERM_START, classes_on,
                  next_exam, upcoming, urgency, week_no, when_cn)

FROZEN = getattr(sys, "frozen", False)   # 是否是 PyInstaller 打出来的 exe
# 打包后 __file__ 指向临时解压目录，位置要用 exe 自己所在的目录
HERE = os.path.dirname(sys.executable if FROZEN else os.path.abspath(__file__))
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


UI_SCALE = 1.0   # 默认大小。平时不用改这里 —— 拖组件右下角就能实时缩放，会记住

DPI_SCALE, DPI = dpi_scale()
try:    # 屏幕不高的机器（多是笔记本）默认小一档，否则组件占掉大半个屏
    _SMALL = 0.85 if ctypes.windll.user32.GetSystemMetrics(1) < 1200 else 1.0
except Exception:
    _SMALL = 1.0
DEFAULT_UI = UI_SCALE * _SMALL
UI_MIN, UI_MAX = 0.55, 1.8

WIDTH = 440          # 以下都是 ui=1 时的逻辑像素，
PAD = 20             # 画完之后整块按 self.scale 放大（见 _paint 末尾）
GRIP = 18            # 右下角缩放手柄的边长
TITLE_H = 58         # 顶部时间栏的高度 —— 双击这一块折叠
REFRESH_MS = 15_000
TODO_MAX = 4      # 「该动手了」最多列几条
REST_MAX = 6      # 「接下来」最多列几条
ALPHA_IDLE, ALPHA_HOVER = 0.92, 1.0

# 字号基准（ui=1 时的磅值），缩放时按 ui 等比调整
FONT_BASE = {"time": 19, "date": 10, "head": 8, "big": 12, "body": 10, "small": 9}

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
        self.ui = DEFAULT_UI
        self.collapsed = False
        self._mode = None
        self._drag = None
        self._resize0 = None

        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", ALPHA_IDLE)
        root.configure(bg=BG)
        root.tk.call("tk", "scaling", DPI / 72.0)   # 字体按真实 DPI 排版

        self.canvas = tk.Canvas(root, bg=BG, highlightthickness=1,
                                highlightbackground=LINE, bd=0)
        self.canvas.pack()

        self.fonts = {k: tkfont.Font(family="Microsoft YaHei", size=v,
                                     weight="bold" if k in ("time", "big") else "normal")
                      for k, v in FONT_BASE.items()}

        for w in (root, self.canvas):
            w.bind("<Button-1>", self.on_press)
            w.bind("<B1-Motion>", self.on_drag)
            w.bind("<ButtonRelease-1>", self.on_release)
            w.bind("<Double-Button-1>", self.on_double)
            w.bind("<Button-3>", self.on_menu)
            w.bind("<Enter>", lambda e: root.attributes("-alpha", ALPHA_HOVER))
            w.bind("<Leave>", lambda e: root.attributes("-alpha", ALPHA_IDLE))

        self.menu = tk.Menu(root, tearoff=0, bg="#1c2128", fg=FG,
                            activebackground="#30363d", activeforeground=FG,
                            bd=0, font=("Microsoft YaHei", 9))
        self.menu.add_command(label="折叠 / 展开", command=self.toggle_collapse)
        self.menu.add_separator()
        self.menu.add_command(label="大一点", command=lambda: self.bump(+0.1))
        self.menu.add_command(label="小一点", command=lambda: self.bump(-0.1))
        self.menu.add_command(label="恢复默认大小", command=self.reset_size)
        self.menu.add_separator()
        self.menu.add_command(label="打开学期日程.md", command=self.open_md)
        self.menu.add_command(label="立即刷新", command=self.render)
        self.topmost = tk.BooleanVar(value=True)
        self.menu.add_checkbutton(label="总在最前", variable=self.topmost,
                                  command=lambda: root.attributes("-topmost", self.topmost.get()))
        self.menu.add_command(label="回到右上角", command=self.reset_pos)
        self.menu.add_separator()
        self.menu.add_command(label="退出", command=root.destroy)

        self.restore_state()
        self.apply_fonts()
        self.render()
        self.tick()

    # ---- 缩放 ----
    @property
    def scale(self):
        """画布坐标的总缩放 = 系统 DPI × 用户缩放"""
        return DPI_SCALE * self.ui

    def apply_fonts(self):
        """字号只跟 ui 走 —— 系统 DPI 已经由 tk scaling 处理过了"""
        for k, base in FONT_BASE.items():
            self.fonts[k].configure(size=max(6, round(base * self.ui)))

    def set_ui(self, v, save=True):
        v = max(UI_MIN, min(UI_MAX, v))
        if abs(v - self.ui) < 0.005:
            return
        self.ui = v
        self.apply_fonts()
        self.render()
        if save:
            self.save_state()

    def bump(self, d):
        self.set_ui(self.ui + d)

    def reset_size(self):
        self.set_ui(DEFAULT_UI)

    # ---- 折叠 ----
    def toggle_collapse(self):
        self.collapsed = not self.collapsed
        self.render()
        self.save_state()

    # ---- 状态存取 ----
    def restore_state(self):
        """恢复位置和大小。换台机器（屏幕更小）时存的坐标可能已经在屏幕外，
        那样组件就永远看不见了 —— 越界就退回右上角。"""
        try:
            with open(POS_FILE, encoding="utf-8") as fh:
                p = json.load(fh)
            self.ui = max(UI_MIN, min(UI_MAX, float(p.get("ui", DEFAULT_UI))))
            self.collapsed = bool(p.get("collapsed", False))
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            x, y = int(p["x"]), int(p["y"])
            if not (-40 <= x <= sw - 120 and -10 <= y <= sh - 120):
                raise ValueError("上次的位置不在这块屏幕上")
            self.root.geometry(f"+{x}+{y}")
        except Exception:
            self.reset_pos()

    def reset_pos(self):
        sw = self.root.winfo_screenwidth()
        x, y = sw - int(WIDTH * self.scale) - 36, 48
        self.root.geometry(f"+{x}+{y}")
        self._write(x, y)   # 直接存算出来的值 —— 这时窗口还没布局，
                            # winfo_x() 只会返回 0，存进去下次就跑左上角了

    def _write(self, x, y):
        try:
            with open(POS_FILE, "w", encoding="utf-8") as fh:
                json.dump({"x": x, "y": y, "ui": round(self.ui, 3),
                           "collapsed": self.collapsed}, fh)
        except Exception:
            pass

    def save_state(self):
        self._write(self.root.winfo_x(), self.root.winfo_y())

    # ---- 鼠标 ----
    def _in_grip(self, e):
        """按在右下角那个缩放手柄上了吗"""
        g = int(GRIP * self.scale)
        lx = e.x_root - self.root.winfo_x()
        ly = e.y_root - self.root.winfo_y()
        return lx > self.root.winfo_width() - g and ly > self.root.winfo_height() - g

    def on_press(self, e):
        if self._in_grip(e):
            self._mode = "resize"
            self._resize0 = (e.x_root, e.y_root, self.ui)
        else:
            self._mode = "move"
            self._drag = (e.x_root - self.root.winfo_x(),
                          e.y_root - self.root.winfo_y())

    def on_drag(self, e):
        if self._mode == "resize" and self._resize0:
            x0, y0, ui0 = self._resize0
            # 往右下拖变大，往左上拖变小；两个方向都算，斜着拖手感自然
            d = ((e.x_root - x0) + (e.y_root - y0)) / 2
            self.set_ui(ui0 * (1 + d / (WIDTH * DPI_SCALE * 0.55)), save=False)
        elif self._mode == "move" and self._drag:
            self.root.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")
            self.save_state()

    def on_release(self, e):
        if self._mode == "resize":
            self.save_state()
        self._mode = None

    def on_double(self, e):
        """双击顶部时间栏 = 折叠/展开；双击别处 = 打开学期日程"""
        ly = e.y_root - self.root.winfo_y()
        if self.collapsed or ly < TITLE_H * self.scale:
            self.toggle_collapse()
        else:
            self.open_md()

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

    def _grip(self, w, h):
        """右下角画三道斜线，暗示这里能拖"""
        s = max(1, round(1.5 * self.scale))
        for off in (5, 10, 15):
            d = int(off * self.scale)
            self.canvas.create_line(w - d, h - 3, w - 3, h - d, fill=LINE, width=s)

    def _headline(self, today, nm):
        """折叠状态下只显示一句话：眼下最要紧的那件事"""
        cls = classes_on(today)
        cur = next((k for k in cls if mins(k[0]) <= nm < mins(k[1])), None)
        if cur:
            return f"{cur[2]}  还剩 {mins(cur[1]) - nm} 分", kind_color(cur[4])
        nxt = next((k for k in cls if mins(k[0]) > nm), None)
        if nxt:
            return (f"{nxt[0][0]:02d}:{nxt[0][1]:02d} {nxt[2]}  "
                    f"{human_gap(mins(nxt[0]) - nm)}"), kind_color(nxt[4])
        items = [it for it in upcoming(today, 21)
                 if it.date != today or mins(it.at) >= nm]
        todo = [it for it in items if it.started(today) and it.needs_work]
        if todo:
            it = todo[0]
            n = it.days_left(today)
            tail = ("今天 %02d:%02d" % it.at) if n == 0 else when_cn(n)
            return f"{it.label}  {tail}", URG[urgency(n)]
        nx = next_exam(today)
        if nx:
            n = (nx[0] - today).days
            return f"{nx[1]} {nx[2]}  {n} 天", PURPLE
        return "今天没安排", DIM

    def _paint_collapsed(self):
        """折叠成一行：时间 + 一句最要紧的事"""
        c = self.canvas
        c.delete("all")
        now = self.fixed_now or dt.datetime.now()
        today = self.fixed_today or now.date()
        nm = now.hour * 60 + now.minute

        y = 13
        self.txt(PAD, y, f"{now:%H:%M}", self.fonts["big"], FG)
        text, col = self._headline(today, nm)
        self.txt(PAD + 76, y + 2, text, self.fonts["body"], col,
                 maxw=(WIDTH - PAD - 26 - (PAD + 76)) * self.scale)
        self.txt(WIDTH - PAD + 2, y + 1, "▾", self.fonts["small"], DIM, "ne")
        y += 38
        if self.scale != 1.0:
            c.scale("all", 0, 0, self.scale, self.scale)
        return int(y * self.scale)

    def _paint(self, todo_max, rest_max):
        """按给定的条数上限画一遍，返回内容总高度（物理像素）"""
        c = self.canvas
        c.delete("all")
        F = self.fonts
        now = self.fixed_now or dt.datetime.now()
        today = self.fixed_today or now.date()
        nm = now.hour * 60 + now.minute
        y = 18

        # ── 时间 / 日期 ──
        self.txt(PAD, y, f"{now:%H:%M}", F["time"], FG)
        self.txt(WIDTH - PAD, y + 1, f"{today.month}月{today.day}日 周{WEEK_CN[today.weekday()]}",
                 F["date"], DIM, "ne")
        tag = f"第 {week_no(today)} 周"
        if today in READING_WEEK:
            tag += " · Reading Week"
        elif today in NO_CLASS:
            tag += " · 停课"
        elif not (TERM_START <= today <= TERM_END):
            tag = "学期外"
        self.txt(WIDTH - PAD, y + 30, tag, F["small"], FAINT, "ne")
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
            self.txt(PAD, y, "正在上", F["head"], DIM)
            self.txt(WIDTH - PAD, y, room, F["head"], DIM, "ne")
            self.txt(PAD, y + 18, title, F["big"], col)
            left = mins(cur[1]) - nm
            self.txt(WIDTH - PAD, y + 22, f"还剩 {left} 分", F["small"], DIM, "ne")
            # 进度条
            total = mins(cur[1]) - mins(cur[0])
            frac = 0 if total <= 0 else (nm - mins(cur[0])) / total
            bx0, bx1, by = PAD, WIDTH - PAD, y + 56
            c.create_line(bx0, by, bx1, by, fill=LINE, width=3)
            c.create_line(bx0, by, bx0 + (bx1 - bx0) * frac, by, fill=col, width=3)
            y += 84
        elif nxt:
            (h1, m1), _e, title, room, kind = nxt
            self.txt(PAD, y, "下一节", F["head"], DIM)
            self.txt(PAD, y + 18, f"{h1:02d}:{m1:02d}", F["big"], kind_color(kind))
            self.txt(PAD + 78, y + 20, title, F["body"], FG)
            self.txt(WIDTH - PAD, y + 20, room, F["small"], DIM, "ne")
            self.txt(PAD, y + 44, human_gap(mins(nxt[0]) - nm), F["small"], DIM)
            y += 68
        else:
            note = ("Reading Week" if today in READING_WEEK else
                    "今天放假" if today in NO_CLASS else
                    "今天没课" if not cls else "今天的课上完了")
            self.txt(PAD, y, note, F["body"], DIM)
            y += 32

        # ── 今天剩下 ──
        rest = [k for k in cls if mins(k[0]) > nm]
        if not cur and nxt and rest and rest[0] is nxt:
            rest = rest[1:]      # 只有真的画了「下一节」时才去重；正在上课时它没画
        if rest:
            self.rule(y)
            y += 14
            self.txt(PAD, y, "今天剩下", F["head"], DIM)
            y += 22
            for (h1, m1), _e, title, room, kind in rest[:5]:
                c.create_rectangle(PAD, y + 4, PAD + 3, y + 17,
                                   fill=kind_color(kind), outline="")
                self.txt(PAD + 12, y, f"{h1:02d}:{m1:02d}", F["small"], kind_color(kind))
                self.txt(PAD + 76, y, title, F["body"], FG,
                         maxw=(WIDTH - PAD - 60 - (PAD + 76)) * self.scale)
                self.txt(WIDTH - PAD, y + 1, room, F["small"], FAINT, "ne")
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
            self.txt(PAD, y, "该动手了", F["head"], DIM)
            y += 22
            for it in todo[:todo_max]:
                n = it.days_left(today)
                col = URG[urgency(n)] if it.hard or it.kind == "exam" else DIM
                is_exam = it.kind == "exam"
                c.create_oval(PAD, y + 7, PAD + 7, y + 14,
                              fill=PURPLE if is_exam else col, outline="")
                w = self.txt(PAD + 18, y, it.label, F["body"],
                             PURPLE if is_exam else FG,
                             maxw=(WIDTH - PAD - 88 - (PAD + 18)) * self.scale)
                # bbox 的左边是逻辑坐标，宽度却是字体渲染出来的物理像素 ——
                # 混着用会让工时标签在缩放后跑偏（放大时空一大截，缩小时压到字上）
                x1, _, x2, _ = self.canvas.bbox(w)
                bx = x1 + (x2 - x1) / self.scale
                self.txt(bx + 10, y + 2,
                         "复习" if it.hours is None else f"{it.hours:g}h",
                         F["small"], FAINT)
                tail = ("今天 %02d:%02d" % it.at) if n == 0 else when_cn(n)
                self.txt(WIDTH - PAD, y + 1, tail, F["small"], col, "ne")
                y += 26
            if len(todo) > todo_max:
                self.txt(PAD + 18, y, f"⋯ 还有 {len(todo) - todo_max} 件", F["small"], FAINT)
                y += 24
            y += 6

        if rest:
            self.rule(y)
            y += 14
            self.txt(PAD, y, "接下来", F["head"], DIM)
            y += 22
            last = None
            for it in rest[:rest_max]:
                n = it.days_left(today)
                col = URG[urgency(n)] if it.hard else DIM
                if it.date != last:
                    lab_col = URG[urgency(n)] if any(
                        x.hard for x in rest if x.date == it.date) else DIM
                    self.txt(PAD, y + 1, when_cn(n), F["small"], lab_col)
                    last = it.date
                if it.kind == "exam":
                    c.create_rectangle(PAD + 72, y + 6, PAD + 80, y + 15,
                                       fill=PURPLE, outline="")
                elif it.hard:
                    c.create_oval(PAD + 72, y + 7, PAD + 79, y + 14, fill=col, outline="")
                self.txt(WIDTH - PAD, y + 1, "%02d:%02d" % it.at,
                         F["small"], FAINT, "ne")
                self.txt(PAD + 92, y, it.text,
                         F["body"] if it.hard else F["small"],
                         PURPLE if it.kind == "exam" else (FG if it.hard else DIM),
                         maxw=(WIDTH - PAD - 52 - (PAD + 92)) * self.scale)
                y += 25
            if len(rest) > rest_max:
                self.txt(PAD + 92, y, f"⋯ 还有 {len(rest) - rest_max} 项", F["small"], FAINT)
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
            self.txt(PAD, y, "下一场考试", F["head"], DIM)
            self.txt(WIDTH - PAD, y, f"{ed.month}/{ed.day} {h1:02d}:{m1:02d}",
                     F["head"], FAINT, "ne")
            self.txt(PAD, y + 20, f"{course} {name}", F["body"], FG)
            cd = "就是今天" if n == 0 else "明天" if n == 1 else f"{n} 天"
            self.txt(WIDTH - PAD, y + 21, cd, F["small"], URG[urgency(n)], "ne")
            y += 50

        y += 12
        # 上面全程用逻辑坐标画，这里一次性缩放到物理像素 —— 字体已由 tk scaling 处理
        if self.scale != 1.0:
            c.scale("all", 0, 0, self.scale, self.scale)
        return int(y * self.scale)

    def render(self):
        """屏幕矮就少列几条 —— 高 DPI 的笔记本上按满额画会比屏幕还高"""
        if self.collapsed:
            h = self._paint_collapsed()
        else:
            limit = self.root.winfo_screenheight() - 140
            for tm, rm in ((TODO_MAX, REST_MAX), (3, 4), (2, 3), (1, 2)):
                h = self._paint(tm, rm)
                if h <= limit:
                    break
        w = int(WIDTH * self.scale)
        self._grip(w, h)
        self.canvas.configure(width=w, height=h)
        self.root.geometry(f"{w}x{h}")

    def tick(self):
        self.render()
        self.root.after(REFRESH_MS, self.tick)


# ---- 开机自启 -------------------------------------------------------------
def startup_path():
    return os.path.join(os.environ["APPDATA"], "Microsoft", "Windows",
                        "Start Menu", "Programs", "Startup", "Study日程组件.vbs")


def install_startup():
    if FROZEN:                       # exe 版：自启直接指向 exe
        target = f'"""{sys.executable}"""'
    else:                            # 脚本版：pythonw + widget.py，这样不弹黑框
        pyw = sys.executable.replace("python.exe", "pythonw.exe")
        if not os.path.exists(pyw):
            pyw = sys.executable
        target = f'"""{pyw}"" ""{os.path.join(HERE, "widget.py")}"""'
    # .vbs 必须按系统 ANSI 编码写、CRLF 换行：用 UTF-8 的话，路径里只要有中文
    # （比如 exe 叫「日程组件.exe」），WScript 读出来就是乱码，自启直接失效
    with open(startup_path(), "w", encoding="mbcs", errors="replace",
              newline="\r\n") as fh:
        fh.write('Set s = CreateObject("WScript.Shell")\n')
        fh.write(f"s.Run {target}, 0, False\n")
    print("已装进开机自启：", startup_path())


def remove_startup():
    p = startup_path()
    if os.path.exists(p):
        os.remove(p)
        print("已取消开机自启")
    else:
        print("本来就没装")


def already_running():
    """开机自启 + 手动双击 = 两个组件叠在一起看不出来。用命名互斥量拦住第二个。
    句柄不显式关闭，进程退出时系统自己回收。"""
    try:
        k32 = ctypes.windll.kernel32
        k32.CreateMutexW(None, False, "Study2026Fall_ScheduleWidget")
        return k32.GetLastError() == 183      # ERROR_ALREADY_EXISTS
    except Exception:
        return False


def main():
    if "--startup" in sys.argv:
        return install_startup()
    if "--unstartup" in sys.argv:
        return remove_startup()

    if "--shot" not in sys.argv and already_running():
        print("组件已经在运行了")
        return

    root = tk.Tk()
    today = now = None
    if "--at" in sys.argv:    # 调样式用：--at 2026-10-05T09:30
        now = dt.datetime.fromisoformat(sys.argv[sys.argv.index("--at") + 1])
        today = now.date()
    w = Widget(root, today, now)

    if "--shot" in sys.argv:
        out = sys.argv[sys.argv.index("--shot") + 1]
        if "--collapsed" in sys.argv:
            w.collapsed = True
            w.render()
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
