# -*- coding: utf-8 -*-
"""把「今天的课 + 接下来两周的截止」画成桌面壁纸。

数据全部来自 data.py（和 ics、学期日程.md 同源）。
内容画在屏幕右侧，左边留给桌面图标。

    python _schedule/wallpaper.py          # 只生成图片
    python _schedule/wallpaper.py --set    # 生成并设为桌面壁纸
    python _schedule/wallpaper.py --set --date 2026-10-05   # 预览某一天的效果
"""
import ctypes
import datetime as dt
import os
import sys

from PIL import Image, ImageDraw, ImageFont

from data import (OUT_DIR, VAULT, LOOKAHEAD, NO_CLASS, READING_WEEK, classes_on, next_exam,
                  upcoming, urgency, week_no, when_cn)

OUT = os.path.join(OUT_DIR, "桌面日程.png")
def screen_size():
    """跟着这台机器的主屏走，不写死 2560x1440"""
    try:
        u = ctypes.windll.user32
        u.SetProcessDPIAware()
        return u.GetSystemMetrics(0), u.GetSystemMetrics(1)
    except Exception:
        return 2560, 1440


W, H = screen_size()
PANEL_W = min(1010, int(W * 0.40))     # 右侧面板宽度
PANEL_X = W - PANEL_W - 100            # 左边全部留给桌面图标

BG        = (13, 17, 23)
BG2       = (22, 27, 34)
FG        = (230, 237, 243)
DIM       = (125, 133, 144)
LINE      = (48, 54, 61)
BLUE      = (121, 192, 255)        # 上课
GREEN     = (86, 211, 100)         # 实验
RED       = (255, 123, 114)        # 今天/明天截止
ORANGE    = (255, 166, 87)         # 2-3 天
YELLOW    = (210, 180, 100)        # 4-7 天
PURPLE    = (198, 160, 246)        # 考试
URG       = [RED, ORANGE, YELLOW, DIM]   # data.urgency() 的 4 个等级

_FONTS = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")
REG   = os.path.join(_FONTS, "msyh.ttc")
BOLD  = os.path.join(_FONTS, "msyhbd.ttc")
LIGHT = os.path.join(_FONTS, "msyhl.ttc")
F = {}


def f(size, weight="reg"):
    key = (size, weight)
    if key not in F:
        path = {"reg": REG, "bold": BOLD, "light": LIGHT}[weight]
        F[key] = ImageFont.truetype(path, size)
    return F[key]


WEEK_CN = "一二三四五六日"


# ---- 画 -------------------------------------------------------------------
def draw(today):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # 面板底：比桌面稍亮一点，右侧到底
    d.rectangle([PANEL_X - 40, 0, W, H], fill=BG2)
    d.line([PANEL_X - 40, 0, PANEL_X - 40, H], fill=LINE, width=2)

    x = PANEL_X
    y = 90

    # ---- 今天 ----
    d.text((x, y), f"{today.month}月{today.day}日", font=f(76, "bold"), fill=FG)
    w = d.textlength(f"{today.month}月{today.day}日", font=f(76, "bold"))
    d.text((x + w + 22, y + 30), f"周{WEEK_CN[today.weekday()]}", font=f(36), fill=DIM)

    tag = f"第 {week_no(today)} 周"
    if today in READING_WEEK:
        tag += " · Reading Week"
    elif today in NO_CLASS:
        tag += " · 停课"
    d.text((x, y + 108), tag, font=f(28), fill=DIM)
    y += 175

    # ---- 今日课表 ----
    cls = classes_on(today)
    if cls:
        for (h1, m1), (h2, m2), title, room, kind in cls:
            color = {'lab': GREEN, 'exam': PURPLE}.get(kind, BLUE)
            d.rectangle([x, y + 6, x + 6, y + 40], fill=color)
            d.text((x + 24, y), f"{h1:02d}:{m1:02d}", font=f(32, "bold"), fill=color)
            d.text((x + 132, y + 2), title, font=f(31), fill=FG)
            d.text((x + 132 + d.textlength(title, font=f(31)) + 20, y + 8), room,
                   font=f(25), fill=DIM)
            y += 56
    else:
        note = "Reading Week" if today in READING_WEEK else (
            "假期" if today in NO_CLASS else "周末" if today.weekday() >= 5 else "今天没课")
        d.text((x + 24, y), note, font=f(31), fill=DIM)
        y += 56

    y += 34
    d.line([x, y, x + PANEL_W - 60, y], fill=LINE, width=2)
    y += 34

    # ---- 接下来 ----

    # 空档期就往后多看，别留一大片空白
    for span in (LOOKAHEAD, 21, 28, 40):
        items = upcoming(today, span)
        if len(items) >= 7:
            break
    d.text((x, y), f"接下来 {span} 天", font=f(27, "bold"), fill=DIM)
    y += 52
    if not items:
        d.text((x + 24, y), "没有截止事项", font=f(29), fill=DIM)
        y += 50
    last_day = None
    for it in items:
        if y > H - 190:
            d.text((x + 24, y), f"⋯ 还有 {len([i for i in items if i.date >= it.date])} 项",
                   font=f(25), fill=DIM)
            break
        day, hard, kind = it.date, it.hard, it.kind
        n = it.days_left(today)
        color = URG[urgency(n)] if hard else DIM
        if day != last_day:
            lab = URG[urgency(n)] if any(o.hard for o in items if o.date == day) else DIM
            d.text((x, y + 3), when_cn(n), font=f(26, "bold"), fill=lab)
            last_day = day
        if hard:
            d.ellipse([x + 118, y + 13, x + 130, y + 25], fill=color)
        if it.started(today) and it.needs_work:      # 已经该动手的，左侧竖条标出来
            d.rectangle([x - 18, y + 4, x - 13, y + 36], fill=color)
        d.text((x + 148, y), ("📝 " if kind == "exam" else "") + it.text,
               font=f(28 if hard else 26),
               fill=PURPLE if kind == "exam" else (FG if hard else DIM))
        tail = "%02d:%02d" % it.at
        if it.hours and not it.started(today):
            tail = f"{it.start.month}/{it.start.day} 动手 · " + tail
        d.text((x + PANEL_W - 60, y + 4), tail, font=f(24), fill=(70, 78, 88), anchor="ra")
        y += 46

    # ---- 底部：下一场考试 ----
    nx = next_exam(today)
    if nx:
        ed, c, name, (h1, m1) = nx
        n = (ed - today).days
        by = H - 150
        d.line([x, by - 34, x + PANEL_W - 60, by - 34], fill=LINE, width=2)
        d.text((x, by), "下一场考试", font=f(24), fill=DIM)
        label = f"{c} {name}"
        d.text((x, by + 38), label, font=f(34, "bold"), fill=FG)
        cd = "就是今天" if n == 0 else ("明天" if n == 1 else f"还有 {n} 天")
        d.text((x + d.textlength(label, font=f(34, "bold")) + 26, by + 44), cd,
               font=f(28), fill=URG[urgency(n)])
        d.text((x + PANEL_W - 60, by + 42),
               f"{ed.month}/{ed.day} {h1:02d}:{m1:02d}", font=f(26), fill=DIM,
               anchor="ra")

    d.text((x, H - 42), f"更新于 {dt.datetime.now():%m-%d %H:%M}  ·  {os.path.join(VAULT, chr(23398)+chr(26399)+chr(26085)+chr(31243))}.md",
           font=f(20), fill=(70, 78, 88))
    return img


def set_wallpaper(path):
    # SPI_SETDESKWALLPAPER=20, SPIF_UPDATEINIFILE|SPIF_SENDCHANGE=3
    ok = ctypes.windll.user32.SystemParametersInfoW(20, 0, path.replace("/", "\\"), 3)
    return bool(ok)


if __name__ == "__main__":
    today = dt.date.today()
    if "--date" in sys.argv:
        today = dt.date.fromisoformat(sys.argv[sys.argv.index("--date") + 1])
    draw(today).save(OUT)
    print("已生成", OUT)
    if "--set" in sys.argv:
        print("已设为桌面壁纸" if set_wallpaper(OUT) else "设置壁纸失败")
