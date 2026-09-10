# -*- coding: utf-8 -*-
"""常驻桌面的日程组件。

一个无边框半透明小窗，钉在桌面角落，一直显示：现在在上什么课（带进度条）、
下一件事还有多久、今天剩下什么、接下来的截止、下一场考试倒计时。
每 15 秒自己刷新，不用点任何东西。

数据来自 data.py，和 ics、学期日程.md、壁纸同源。

    pythonw schedule-widget/widget.py              # 启动（不带控制台窗口）
    python  schedule-widget/widget.py --startup    # 装进开机自启
    python  schedule-widget/widget.py --unstartup  # 取消开机自启
    python  schedule-widget/widget.py --shot out.png   # 截一张当前样子，用来调样式

鼠标：
    右上角三个按钮   折叠/展开 · 恢复默认大小 · 立即刷新
    滚轮            放大 / 缩小
    拖边缘          朝那条边缩放
    拖角            固定对角自由形变
    拖别处          移动位置
    双击            打开 学期日程.md
    右键            其余低频操作
"""
import ctypes
import datetime as dt
import math
import json
import os
import sys
import tkinter as tk
import tkinter.font as tkfont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data import (NO_CLASS, READING_WEEK, TERM_END, TERM_START, VAULT,
                  classes_on, next_exam, save_vault, upcoming, urgency,
                  week_no, when_cn)

FROZEN = getattr(sys, "frozen", False)   # 是否是 PyInstaller 打出来的 exe
# 打包后 __file__ 指向临时解压目录，位置要用 exe 自己所在的目录
HERE = os.path.dirname(sys.executable if FROZEN else os.path.abspath(__file__))
POS_FILE = os.path.join(HERE, ".widget_pos.json")
if "--at" in sys.argv:      # 调样式/跑测试时别动真实的位置文件
    POS_FILE = os.path.join(HERE, ".widget_pos.test.json")
# 库没配过就是 None —— 双击打开日程这一项静默失效，其余功能照常
SCHEDULE_MD = os.path.join(VAULT, "学期日程.md") if VAULT else None

# 单实例判断靠它认人，别改（改了等于放两个组件进来）
WINDOW_TITLE = "Study2026Fall_ScheduleWidget"


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


UI_SCALE = 1.0   # 默认大小。平时不用改这里 —— 滚轮或者拖边缘就能实时调，会记住

DPI_SCALE, DPI = dpi_scale()
try:    # 屏幕不高的机器（多是笔记本）默认小一档，否则组件占掉大半个屏
    _SMALL = 0.85 if ctypes.windll.user32.GetSystemMetrics(1) < 1200 else 1.0
except Exception:
    _SMALL = 1.0
DEFAULT_UI = UI_SCALE * _SMALL
UI_MIN, UI_MAX = 0.55, 1.8

W_DEFAULT = 440      # 卡片默认逻辑宽度；拖左右边会改 self.W
W_MIN, W_MAX = 300, 900
PAD = 20             # 布局全用逻辑像素，画完整块按 self.scale 放大
EDGE = 7             # 边缘判定带宽度：拖这一圈是缩放，拖里面是移动
CORNER = 18          # 四角判定方块的边长
MIN_H = 110          # 拖到最矮也不能低于这个（逻辑像素）
BTN, BTN_GAP = 15, 11    # 右上角按钮的边长和间距
TITLE_H = 58         # 顶部时间栏高度
REFRESH_MS = 15_000
# 放得下就全列出来，放不下才一档档削。先削「接下来」—— 它比「该动手了」次要。
# 每一档是 (该动手了最多几条, 接下来最多几条)，99 = 不限制。
FIT_LADDER = [(99, 99), (99, 14), (99, 10), (99, 7), (6, 6), (5, 5),
              (4, 5), (4, 4), (3, 4), (3, 3), (2, 3), (2, 2), (1, 2), (1, 1)]
ALPHA_IDLE, ALPHA_HOVER = 0.92, 1.0
WHEEL_STEP = 1.07    # 滚一格缩放多少

# 字号基准（ui=1 时的磅值），缩放时按 ui 等比调整
FONT_BASE = {"time": 19, "date": 10, "head": 8, "big": 12, "body": 10, "small": 9}

BG      = "#12161c"
FG      = "#e6edf3"
DIM     = "#7d8590"
FAINT   = "#4a525c"
LINE    = "#262c34"
BTN_FG  = "#8b949e"
BTN_HI  = "#e6edf3"
BTN_BG  = "#242c37"
BLUE    = "#79c0ff"
GREEN   = "#56d364"
PURPLE  = "#c6a0f6"
URG     = ["#ff7b72", "#ffa657", "#d2b464", "#7d8590"]   # data.urgency() 四级
NOW_BG  = "#1b2430"

WEEK_CN = "一二三四五六日"

# 八个方向的鼠标指针。必须用 size_* 这套 —— 实测只有它们映射到 Windows 系统
# 光标（IDC_SIZENWSE 等），会跟随系统光标主题；X11 那套名字（top_left_corner
# 之类）Tk 是用自带的黑白位图画的，又糙又老。
CURSORS = {"nw": "size_nw_se", "se": "size_nw_se",
           "ne": "size_ne_sw", "sw": "size_ne_sw",
           "n": "size_ns", "s": "size_ns",
           "w": "size_we", "e": "size_we"}


def mins(t):
    return t[0] * 60 + t[1]


def kind_color(k):
    return {"lab": GREEN, "exam": PURPLE}.get(k, BLUE)


def when_full(d, n, weekday=True):
    """「9/18 周五 · 8 天后」。只说「8 天后」的话，没人知道那天到底落在哪。"""
    day = f"{d.month}/{d.day}"
    if weekday:
        day += f" 周{WEEK_CN[d.weekday()]}"
    return f"{day} · {when_cn(n)}"


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
        self.ui = DEFAULT_UI    # 字号缩放，只由滚轮改
        self.W = W_DEFAULT      # 卡片逻辑宽度，只由拖左右边/角改
        self.win_h = None       # 用户拖出来的高度（物理像素）；None = 跟着内容走
        self.collapsed = False
        self._mode = None       # None / move / resize / button
        self._drag = None
        self._rz = None         # resize 起始快照
        self._rz_job = None     # 节流用的 after id
        self._pending = None    # 最后一次鼠标位置
        self._wheel_job = None  # 滚轮也按帧合并
        self._wheel_to = None   # 累加出来的目标字号
        self._wheel_at = None
        self._btns = []         # [(x1, y1, x2, y2, 回调, 名字)]，物理坐标
        self._hot = None        # 鼠标正悬在哪个按钮上
        self._fit = 0           # 上次用的 FIT_LADDER 档位，下次从这里接着找

        root.title(WINDOW_TITLE)     # 无边框窗口也有标题，单实例判断认的就是它
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", ALPHA_IDLE)
        root.configure(bg=BG)
        root.tk.call("tk", "scaling", DPI / 72.0)   # 字体按真实 DPI 排版

        # 撑满窗口：尺寸只由 root.geometry 决定一次，canvas 自己跟上。
        # 边框改成自己画（highlightthickness 会让内容整体偏移 1px）
        self.canvas = tk.Canvas(root, bg=BG, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        self.fonts = {k: tkfont.Font(family="Microsoft YaHei", size=v,
                                     weight="bold" if k in ("time", "big") else "normal")
                      for k, v in FONT_BASE.items()}

        for w in (root, self.canvas):
            w.bind("<Button-1>", self.on_press)
            w.bind("<B1-Motion>", self.on_drag)
            w.bind("<ButtonRelease-1>", self.on_release)
            w.bind("<Double-Button-1>", self.on_double)
            w.bind("<Button-3>", self.on_menu)
            w.bind("<Motion>", self.on_motion)
            w.bind("<MouseWheel>", self.on_wheel)
            w.bind("<Enter>", lambda e: (root.attributes("-alpha", ALPHA_HOVER), "break")[1])
            w.bind("<Leave>", self.on_leave)

        self.menu = tk.Menu(root, tearoff=0, bg="#1c2128", fg=FG,
                            activebackground="#30363d", activeforeground=FG,
                            bd=0, font=("Microsoft YaHei", 9))
        self.menu.add_command(label="打开学期日程.md", command=self.open_md)
        self.menu.add_command(label="回到右上角", command=self.reset_pos)
        self.topmost = tk.BooleanVar(value=True)
        self.menu.add_checkbutton(label="总在最前", variable=self.topmost,
                                  command=lambda: root.attributes("-topmost", self.topmost.get()))
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

    def set_ui(self, v, save=True, redraw=True):
        """只改字号（连带间距）。卡片宽度是 self.W，跟这个无关。"""
        v = max(UI_MIN, min(UI_MAX, v))
        if abs(v - self.ui) < 0.004:
            return False
        if self.win_h:              # 手动定过高度的话，让它跟着一起缩放
            self.win_h = int(self.win_h * v / self.ui)
        self.ui = v
        self.apply_fonts()
        if redraw:
            self.render()
        if save:
            self.save_state()
        return True

    def reset_size(self):
        self.win_h = None
        self.W = W_DEFAULT
        self.collapsed = False
        if not self.set_ui(DEFAULT_UI):
            self.render()
            self.save_state()

    def on_wheel(self, e):
        """以鼠标为锚点缩放 —— 鼠标底下那个点保持不动，而不是钉住左上角。
        滚轮事件比屏幕刷新密，所以把连续几格累成一次画，否则整块字会闪。"""
        x0, y0 = self.root.winfo_x(), self.root.winfo_y()
        w0, h0 = max(1, self.root.winfo_width()), max(1, self.root.winfo_height())
        fx = (e.x_root - x0) / w0        # 鼠标在卡片里的相对位置
        fy = (e.y_root - y0) / h0
        base = self._wheel_to if self._wheel_to else self.ui
        self._wheel_to = max(UI_MIN, min(UI_MAX,
                                         base * (WHEEL_STEP if e.delta > 0
                                                 else 1 / WHEEL_STEP)))
        self._wheel_at = (e.x_root, e.y_root, fx, fy)
        if self._wheel_job is None:
            self._wheel_job = self.root.after(12, self._flush_wheel)
        return "break"

    def _flush_wheel(self):
        self._wheel_job = None
        target, anchor = self._wheel_to, self._wheel_at
        self._wheel_to = None
        if target and self.set_ui(target, save=False, redraw=False):
            self.render(anchor=anchor)
            self.save_state()

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
            self.W = max(W_MIN, min(W_MAX, float(p.get("w", W_DEFAULT))))
            self.collapsed = bool(p.get("collapsed", False))
            h = p.get("h")
            self.win_h = int(h) if h else None
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            x, y = int(p["x"]), int(p["y"])
            if not (-40 <= x <= sw - 120 and -10 <= y <= sh - 120):
                raise ValueError("上次的位置不在这块屏幕上")
            self.root.geometry(f"+{x}+{y}")
        except Exception:
            self.reset_pos()

    def reset_pos(self):
        sw = self.root.winfo_screenwidth()
        x, y = sw - int(self.W * self.scale) - 36, 48
        self.root.geometry(f"+{x}+{y}")
        self._write(x, y)   # 直接存算出来的值 —— 这时窗口还没布局，
                            # winfo_x() 只会返回 0，存进去下次就跑左上角了

    def _write(self, x, y):
        try:
            with open(POS_FILE, "w", encoding="utf-8") as fh:
                json.dump({"x": x, "y": y, "ui": round(self.ui, 3),
                           "w": round(self.W, 1), "h": self.win_h,
                           "collapsed": self.collapsed}, fh)
        except Exception:
            pass

    def save_state(self):
        self._write(self.root.winfo_x(), self.root.winfo_y())

    # ---- 命中判定 ----
    def _local(self, e):
        return e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y()

    def _zone(self, lx, ly):
        """鼠标在哪条边/哪个角上？不在边缘就返回 None（那是移动区）"""
        w, h = self.root.winfo_width(), self.root.winfo_height()
        edge = max(4, int(EDGE * self.scale))
        corner = max(10, int(CORNER * self.scale))
        left, right = lx < edge, lx > w - edge
        top, bottom = ly < edge, ly > h - edge
        # 角的判定范围比边宽一些，不然很难点中
        cl, cr = lx < corner, lx > w - corner
        ct, cb = ly < corner, ly > h - corner
        if (top or bottom or left or right):
            if (ct or top) and (cl or left) and (top or left):
                return "nw"
            if (ct or top) and (cr or right) and (top or right):
                return "ne"
            if (cb or bottom) and (cl or left) and (bottom or left):
                return "sw"
            if (cb or bottom) and (cr or right) and (bottom or right):
                return "se"
            return "n" if top else "s" if bottom else "w" if left else "e"
        return None

    def _button_at(self, lx, ly):
        for x1, y1, x2, y2, fn, name in self._btns:
            if x1 <= lx <= x2 and y1 <= ly <= y2:
                return fn, name
        return None, None

    # ---- 鼠标 ----
    def on_motion(self, e):
        # 注意：这些 handler 都要 return "break"。事件绑在 root 和 canvas 两处，
        # 不截断的话 canvas 上的事件会冒泡到 root 再触发一次 —— 按钮会被点两下。
        if self._mode:
            return "break"
        lx, ly = self._local(e)
        _fn, name = self._button_at(lx, ly)
        if name != self._hot:          # 按钮高亮跟着鼠标走
            self._hot = name
            self.render()
        z = None if name else self._zone(lx, ly)
        self.canvas.configure(cursor=CURSORS.get(z, "") if z else "")
        return "break"

    def on_leave(self, e):
        self.root.attributes("-alpha", ALPHA_IDLE)
        if self._hot:
            self._hot = None
            self.render()
        return "break"

    def on_press(self, e):
        lx, ly = self._local(e)
        fn, _name = self._button_at(lx, ly)
        if fn:
            self._mode = "button"
            fn()
            return "break"
        z = self._zone(lx, ly)
        if z:
            self._mode = "resize"
            self._rz = (z, e.x_root, e.y_root,
                        self.root.winfo_x(), self.root.winfo_y(),
                        self.root.winfo_width(), self.root.winfo_height(), self.W)
        else:
            self._mode = "move"
            self._drag = (lx, ly)
        return "break"

    def on_drag(self, e):
        if self._mode == "resize" and self._rz:
            # 按帧合并：鼠标事件比屏幕刷新密得多，每来一个就重画会闪
            self._pending = (e.x_root, e.y_root)
            if self._rz_job is None:
                self._rz_job = self.root.after(12, self._flush_resize)
        elif self._mode == "move" and self._drag:
            self.root.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")
            self.save_state()
        return "break"

    def _flush_resize(self):
        self._rz_job = None
        if self._pending and self._rz:
            self._do_resize(*self._pending)

    def _do_resize(self, mx, my):
        """拖边 = 只朝那个方向拉；拖角 = 钉住对角，宽高各自变。
        全程不动字号 —— 字号是滚轮的事。"""
        z, mx0, my0, x0, y0, w0, h0, W0 = self._rz
        dx, dy = mx - mx0, my - my0

        w = w0
        if "e" in z:
            w = w0 + dx
        elif "w" in z:
            w = w0 - dx
        newW = max(W_MIN, min(W_MAX, w / self.scale))   # 卡片宽度按逻辑像素存
        w = int(newW * self.scale)                      # 夹紧后回推，免得越界时漂移

        h = h0
        if "s" in z:
            h = h0 + dy
        elif "n" in z:
            h = h0 - dy
        h = max(int(MIN_H * self.scale),
                min(self.root.winfo_screenheight(), int(h)))

        # 钉住对边/对角：动左边就右边不动，动上边就下边不动
        x = x0 + (w0 - w) if "w" in z else x0
        y = y0 + (h0 - h) if "n" in z else y0

        self.collapsed = False
        self.W = newW
        if "n" in z or "s" in z:      # 只有真的拖了上下方向才锁高度
            self.win_h = h
        self.render(move_to=(x, y))

    def on_release(self, e):
        if self._rz_job is not None:      # 节流可能还压着最后一帧，补画
            self.root.after_cancel(self._rz_job)
            self._rz_job = None
            if self._pending and self._rz:
                self._do_resize(*self._pending)
        self._pending = None
        if self._mode in ("resize", "button"):
            self.save_state()
        self._mode = None
        self._rz = None
        return "break"

    def on_double(self, e):
        lx, ly = self._local(e)
        if self._button_at(lx, ly)[0] or self._zone(lx, ly):
            return "break"
        self.open_md()
        return "break"

    def on_menu(self, e):
        self.menu.tk_popup(e.x_root, e.y_root)

    def open_md(self):
        if not SCHEDULE_MD:
            return
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
        self.canvas.create_line(PAD, y, self.W - PAD, y, fill=LINE)

    def _draw_buttons(self, w):
        """右上角三个按钮，用画的不用字符 —— 不依赖字体里有没有那些符号。
        坐标全是物理像素，在整体缩放之后画。"""
        c = self.canvas
        self._btns = []
        s = self.scale
        b = int(BTN * s)
        gap = int(BTN_GAP * s)
        top = int(14 * s)
        right = w - int(PAD * s)
        lw = max(1, round(1.4 * s))

        specs = [("collapse", self.toggle_collapse),
                 ("reset", self.reset_size),
                 ("refresh", self.render)]
        for i, (name, fn) in enumerate(specs):
            x2 = right - i * (b + gap)
            x1, y1, y2 = x2 - b, top, top + b
            hot = self._hot == name
            if hot:
                pad = int(4 * s)
                c.create_rectangle(x1 - pad, y1 - pad, x2 + pad, y2 + pad,
                                   fill=BTN_BG, outline="")
            col = BTN_HI if hot else BTN_FG
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            if name == "collapse":
                if self.collapsed:      # 折叠状态画个方框：点了会还原
                    c.create_rectangle(x1 + b * .15, y1 + b * .2, x2 - b * .15, y2 - b * .2,
                                       outline=col, width=lw)
                else:                   # 展开状态画条横线：像最小化
                    c.create_line(x1 + b * .12, cy + b * .22, x2 - b * .12, cy + b * .22,
                                  fill=col, width=lw)
            elif name == "reset":       # 方框 + 左上角实心块 = 回到标准大小和位置
                c.create_rectangle(x1 + b * .12, y1 + b * .12, x2 - b * .12, y2 - b * .12,
                                   outline=col, width=lw)
                c.create_rectangle(x1 + b * .12, y1 + b * .12, cx, cy, fill=col, outline="")
            else:                       # 转一圈的箭头 = 刷新
                r = b * .40
                th = 55                 # 弧的缺口留在右上，箭头就画在这个端点
                c.create_arc(cx - r, cy - r, cx + r, cy + r,
                             start=th, extent=285, style="arc", outline=col, width=lw)
                rad = math.radians(th)
                ex, ey = cx + r * math.cos(rad), cy - r * math.sin(rad)
                tx, ty = -math.sin(rad), -math.cos(rad)      # 端点处的切线方向
                nx, ny = -ty, tx                             # 法线，用来撑开底边
                a = max(2, 2.6 * s)
                c.create_polygon(ex + tx * a * 1.7, ey + ty * a * 1.7,
                                 ex + nx * a, ey + ny * a,
                                 ex - nx * a, ey - ny * a, fill=col, outline="")
            pad = int(6 * s)            # 点击热区比图标本身大一圈，好点
            self._btns.append((x1 - pad, y1 - pad, x2 + pad, y2 + pad, fn, name))

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
        btn_zone = BTN * 3 + BTN_GAP * 2 + 16
        self.txt(PAD + 76, y + 2, text, self.fonts["body"], col,
                 maxw=(self.W - PAD - btn_zone - (PAD + 76)) * self.scale)
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

        # ── 时间 / 日期（右上角留给按钮） ──
        self.txt(PAD, y, f"{now:%H:%M}", F["time"], FG)
        tag = f"第 {week_no(today)} 周"
        if today in READING_WEEK:
            tag += " · Reading Week"
        elif today in NO_CLASS:
            tag += " · 停课"
        elif not (TERM_START <= today <= TERM_END):
            tag = "学期外"
        self.txt(PAD, y + 32, f"{today.month}月{today.day}日 周{WEEK_CN[today.weekday()]}"
                 f"  ·  {tag}", F["small"], DIM)
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
            c.create_rectangle(PAD - 8, y - 6, self.W - PAD + 8, y + 68,
                               fill=NOW_BG, outline="")
            self.txt(PAD, y, "正在上", F["head"], DIM)
            self.txt(self.W - PAD, y, room, F["head"], DIM, "ne")
            self.txt(PAD, y + 18, title, F["big"], col)
            left = mins(cur[1]) - nm
            self.txt(self.W - PAD, y + 22, f"还剩 {left} 分", F["small"], DIM, "ne")
            # 进度条
            total = mins(cur[1]) - mins(cur[0])
            frac = 0 if total <= 0 else (nm - mins(cur[0])) / total
            bx0, bx1, by = PAD, self.W - PAD, y + 56
            c.create_line(bx0, by, bx1, by, fill=LINE, width=3)
            c.create_line(bx0, by, bx0 + (bx1 - bx0) * frac, by, fill=col, width=3)
            y += 84
        elif nxt:
            (h1, m1), _e, title, room, kind = nxt
            self.txt(PAD, y, "下一节", F["head"], DIM)
            self.txt(PAD, y + 18, f"{h1:02d}:{m1:02d}", F["big"], kind_color(kind))
            self.txt(PAD + 78, y + 20, title, F["body"], FG)
            self.txt(self.W - PAD, y + 20, room, F["small"], DIM, "ne")
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
            for (h1, m1), _e, title, room, kind in rest:
                c.create_rectangle(PAD, y + 4, PAD + 3, y + 17,
                                   fill=kind_color(kind), outline="")
                self.txt(PAD + 12, y, f"{h1:02d}:{m1:02d}", F["small"], kind_color(kind))
                self.txt(PAD + 76, y, title, F["body"], FG,
                         maxw=(self.W - PAD - 60 - (PAD + 76)) * self.scale)
                self.txt(self.W - PAD, y + 1, room, F["small"], FAINT, "ne")
                y += 26
            y += 6

        # ── 该动手了 / 接下来 ──
        for span in (14, 21, 28, 45):
            items = [it for it in upcoming(today, span)
                     if it.date != today or mins(it.at) >= nm]   # 今天已过点的不再显示
            if len(items) >= 5:
                break

        # 已经到该动手的日子、还没过截止的，单独拎出来放最上面。
        # 材料已经放出、可以动手，但还没到建议动手日的，紧跟在后面暗一档列 ——
        # 这一档是用来提前占时间的，不是催你现在就做。
        todo = [it for it in items if it.started(today, nm) and it.needs_work]
        soon = [it for it in items if it.needs_work and it.available(today, nm)
                and not it.started(today, nm)]
        rest = [it for it in items if it not in todo and it not in soon]

        # 日期写法：宽的时候连星期几一起写，窄卡片挤不下就只留月/日。
        # 量的是渲染出来的物理宽度，除以 scale 换回布局用的逻辑像素。
        def lab_w(txt):
            return F["small"].measure(txt) / self.scale
        wide = self.W - 2 * PAD - 52 - lab_w(when_full(today, 28)) - 32 >= 150

        if todo or soon:
            hot = todo[:todo_max]
            # 空间不够时先削「可以做」这一档 —— 它比真的该动手了次要
            warm = soon[:max(0, todo_max - len(hot))]
            self.rule(y)
            y += 14
            self.txt(PAD, y, "该动手了" if hot else "可以做了", F["head"], DIM)
            y += 22
            tails = {it: ("今天 %02d:%02d" % it.at) if it.days_left(today) == 0
                         else when_full(it.date, it.days_left(today), wide)
                     for it in hot + warm}
            tail_w = max(88, max(lab_w(t) for t in tails.values()) + 12)
            for it in hot + warm:
                open_only = it in warm      # 窗口开了，但还不到建议动手的日子
                n = it.days_left(today)
                col = URG[urgency(n)] if it.hard or it.kind == "exam" else DIM
                is_exam = it.kind == "exam"
                if open_only:
                    # 空心点 = 可以做了；实心点 = 该做了
                    c.create_oval(PAD, y + 7, PAD + 7, y + 14, outline=col)
                else:
                    c.create_oval(PAD, y + 7, PAD + 7, y + 14,
                                  fill=PURPLE if is_exam else col, outline="")
                w = self.txt(PAD + 18, y, it.label, F["body"],
                             PURPLE if is_exam else (DIM if open_only else FG),
                             maxw=(self.W - PAD - tail_w - (PAD + 18)) * self.scale)
                # bbox 的左边是逻辑坐标，宽度却是字体渲染出来的物理像素 ——
                # 混着用会让工时标签在缩放后跑偏（放大时空一大截，缩小时压到字上）
                x1, _, x2, _ = self.canvas.bbox(w)
                bx = x1 + (x2 - x1) / self.scale
                tag = "复习" if it.hours is None else f"{it.hours:g}h"
                self.txt(bx + 10, y + 2, "可做 · " + tag if open_only else tag,
                         F["small"], FAINT)
                self.txt(self.W - PAD, y + 1, tails[it], F["small"],
                         FAINT if open_only else col, "ne")
                y += 26
            more = (len(todo) - len(hot)) + (len(soon) - len(warm))
            if more:
                self.txt(PAD + 18, y, f"⋯ 还有 {more} 件", F["small"], FAINT)
                y += 24
            y += 6

        if rest:
            self.rule(y)
            y += 14
            self.txt(PAD, y, "接下来", F["head"], DIM)
            y += 22
            last = None
            shown = rest[:rest_max]
            labs = {it.date: when_full(it.date, it.days_left(today), wide)
                    for it in shown}
            bx = PAD + max(72, max(lab_w(s) for s in labs.values()) + 12)
            for it in shown:
                n = it.days_left(today)
                col = URG[urgency(n)] if it.hard else DIM
                if it.date != last:
                    lab_col = URG[urgency(n)] if any(
                        x.hard for x in rest if x.date == it.date) else DIM
                    self.txt(PAD, y + 1, labs[it.date], F["small"], lab_col)
                    last = it.date
                if it.kind == "exam":
                    c.create_rectangle(bx, y + 6, bx + 8, y + 15,
                                       fill=PURPLE, outline="")
                elif it.hard:
                    c.create_oval(bx, y + 7, bx + 7, y + 14, fill=col, outline="")
                self.txt(self.W - PAD, y + 1, "%02d:%02d" % it.at,
                         F["small"], FAINT, "ne")
                self.txt(bx + 20, y, it.text,
                         F["body"] if it.hard else F["small"],
                         PURPLE if it.kind == "exam" else (FG if it.hard else DIM),
                         maxw=(self.W - PAD - 52 - (bx + 20)) * self.scale)
                y += 25
            if len(rest) > rest_max:
                self.txt(bx + 20, y, f"⋯ 还有 {len(rest) - rest_max} 项", F["small"], FAINT)
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
            self.txt(self.W - PAD, y, f"{ed.month}/{ed.day} {h1:02d}:{m1:02d}",
                     F["head"], FAINT, "ne")
            self.txt(PAD, y + 20, f"{course} {name}", F["body"], FG)
            cd = "就是今天" if n == 0 else "明天" if n == 1 else f"{n} 天"
            self.txt(self.W - PAD, y + 21, cd, F["small"], URG[urgency(n)], "ne")
            y += 50

        y += 12
        # 上面全程用逻辑坐标画，这里一次性缩放到物理像素 —— 字体已由 tk scaling 处理
        if self.scale != 1.0:
            c.scale("all", 0, 0, self.scale, self.scale)
        return int(y * self.scale)

    def render(self, move_to=None, anchor=None):
        """尺寸和位置在同一次 geometry 里改完 —— 分开改会让 Windows 多走一轮
        重绘，拖动和缩放时看着就是在闪。
        anchor=(鼠标x, 鼠标y, fx, fy)：画完之后把卡片挪到让相对点 (fx,fy)
        正好落在鼠标底下，滚轮缩放靠它做到「鼠标底下那个点不动」。"""
        w = int(self.W * self.scale)
        if self.collapsed:
            h = self._paint_collapsed()
        else:
            # 有拖出来的高度就照着填，否则以屏幕高度为上限
            target = self.win_h or (self.root.winfo_screenheight() - 140)
            # 从上次那一档开始爬，别每次都从头扫 —— 拖拽时每动一下都会重画
            i = self._fit
            h = self._paint(*FIT_LADDER[i])
            if h <= target:
                while i > 0:                 # 还有余量，试试能不能列得更全
                    h2 = self._paint(*FIT_LADDER[i - 1])
                    if h2 > target:
                        h = self._paint(*FIT_LADDER[i])   # 退回上一档
                        break
                    i, h = i - 1, h2
            else:
                while i < len(FIT_LADDER) - 1:
                    i += 1
                    h = self._paint(*FIT_LADDER[i])
                    if h <= target:
                        break
            self._fit = i
            if self.win_h:      # 用户定了高度：内容短就留白，长就裁掉
                h = self.win_h
        self._draw_buttons(w)
        self.canvas.create_rectangle(0, 0, w - 1, h - 1, outline=LINE)
        if anchor:
            mx, my, fx, fy = anchor
            move_to = (round(mx - fx * w), round(my - fy * h))
        g = f"{w}x{h}"
        if move_to:
            g += f"+{move_to[0]}+{move_to[1]}"
        self.root.geometry(g)

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
    """开机自启 + 手动双击 = 两个组件叠在一起看不出来，得拦住第二个。

    判断的依据是「屏幕上有没有那个窗口」，不是「有没有别的进程活着」。
    原先用命名互斥量：进程一起来就占住，谁占到谁是唯一的一个。问题是互斥量
    的寿命是进程的寿命 —— 窗口没了进程还在（2026-09-09 就留下这么一个：
    没有任何窗口，光占着互斥量），后来的实例全被它挡在门外，双击 exe 毫无
    反应，因为 exe 是无控制台的，连那句「组件已经在运行了」都没地方打。
    改成找窗口之后，这种僵尸进程自然就不碍事了。"""
    try:
        hwnd = ctypes.windll.user32.FindWindowW(None, WINDOW_TITLE)
        return bool(hwnd)
    except Exception:
        return False


def main():
    if "--startup" in sys.argv:
        return install_startup()
    if "--unstartup" in sys.argv:
        return remove_startup()

    if "--vault" in sys.argv:
        save_vault(sys.argv[sys.argv.index("--vault") + 1])
        return print("Obsidian 库记下了，重启组件生效")

    if "--shot" not in sys.argv and already_running():
        # exe 版没有控制台，print 出去没人看得见，弹个框说明白
        if FROZEN:
            ctypes.windll.user32.MessageBoxW(
                None, "组件已经在屏幕上了（右上角），不用再开一个。",
                "日程组件", 0x40)
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
        if "--hot" in sys.argv:      # 高亮某个按钮，用来看悬停效果
            w._hot = sys.argv[sys.argv.index("--hot") + 1]
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
