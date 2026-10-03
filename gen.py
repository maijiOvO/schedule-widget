# -*- coding: utf-8 -*-
"""生成 课表.ics + 任务与考试.ics + 学期日程.md

数据全在 data.py。改完数据重跑本文件即可。
"""
import datetime as dt
import os
import sys

from data import *  # noqa: F401,F403 —— 日程数据（OUT_DIR / VAULT 也在里面）

# 库不在仓库旁边了，第一次跑（或换台机器）用 --vault 指一次，之后就记住了：
#     python gen.py --vault D:/Study
if "--vault" in sys.argv:
    VAULT = save_vault(sys.argv[sys.argv.index("--vault") + 1])
if not VAULT:
    sys.exit("找不到 Obsidian 库，学期日程.md 不知道该写去哪 —— 跑一次 "
             "python gen.py --vault <库的路径>，或设环境变量 STUDY_VAULT。")

# ---- ics 构造 -------------------------------------------------------------
lines_out = []


def esc(s):
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line):
    """ics 每行不超过 75 字节，按字节折行"""
    b = line.encode("utf-8")
    if len(b) <= 73:
        return [line]
    out, cur = [], b
    first = True
    while cur:
        limit = 73 if first else 72
        cut = limit
        while cut > 0 and (cur[cut] & 0xC0) == 0x80:  # 不切断 UTF-8 字符
            cut -= 1
        if cut <= 0:
            cut = limit
        piece = cur[:cut].decode("utf-8", "ignore")
        out.append(piece if first else " " + piece)
        cur = cur[cut:]
        first = False
        if len(cur) <= 72:
            if cur:
                out.append(" " + cur.decode("utf-8", "ignore"))
            break
    return out


_uid = [0]


def uid():
    _uid[0] += 1
    return f"study2026f-{_uid[0]:04d}@maiji.local"


def local(d, h, m):
    return f"{d.strftime('%Y%m%d')}T{h:02d}{m:02d}00"


def alarm(trigger, desc):
    return ["BEGIN:VALARM", "ACTION:DISPLAY", f"TRIGGER:{trigger}",
            f"DESCRIPTION:{esc(desc)}", "END:VALARM"]


def event(summary, dtstart, dtend, location="", desc="", alarms=(),
          rrule=None, exdates=(), allday=False, cats=""):
    e = ["BEGIN:VEVENT", f"UID:{uid()}",
         f"DTSTAMP:{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"]
    if allday:
        e.append(f"DTSTART;VALUE=DATE:{dtstart}")
        e.append(f"DTEND;VALUE=DATE:{dtend}")
    else:
        e.append(f"DTSTART;TZID={TZ}:{dtstart}")
        e.append(f"DTEND;TZID={TZ}:{dtend}")
    if rrule:
        e.append(f"RRULE:{rrule}")
    if exdates:
        if allday:
            e.append("EXDATE;VALUE=DATE:" + ",".join(exdates))
        else:
            e.append(f"EXDATE;TZID={TZ}:" + ",".join(exdates))
    e.append(f"SUMMARY:{esc(summary)}")
    if location:
        e.append(f"LOCATION:{esc(location)}")
    if desc:
        e.append(f"DESCRIPTION:{esc(desc)}")
    if cats:
        e.append(f"CATEGORIES:{cats}")
    for a in alarms:
        e.extend(a)
    e.append("END:VEVENT")
    return e


def calendar(name, body):
    head = ["BEGIN:VCALENDAR", "VERSION:2.0",
            "PRODID:-//maiji//2026Fall Study Schedule//CN",
            "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
            f"X-WR-CALNAME:{name}", f"X-WR-TIMEZONE:{TZ}"]
    head += VTIMEZONE.split("\n")
    out = head + body + ["END:VCALENDAR"]
    folded = []
    for ln in out:
        folded.extend(fold(ln))
    return "\r\n".join(folded) + "\r\n"


# =========================== 1. 课表.ics ===================================
body = []
until = "20261209T045959Z"  # Dec 8 23:59:59 EST → UTC

for (c, kind, wd, h1, m1, h2, m2, room, sec, start_from, extra_ex) in WEEKLY:
    start = first_on(wd, start_from or TERM_START)
    ex = []
    d = start
    while d <= TERM_END:
        if d in NO_CLASS or d in extra_ex:
            ex.append(local(d, h1, m1))
        d += dt.timedelta(days=7)
    body += event(
        f"{c} {KIND_CN[kind]} · {CN[c]}",
        local(start, h1, m1), local(start, h2, m2),
        room,
        f"{c} {sec}\n{CN[c]}\n{room}",
        rrule=f"FREQ=WEEKLY;UNTIL={until}",
        exdates=ex, cats="上课",
    )

# 隔周 PRA 时段（只在真的有 lab 的那周）
for n, d, _prep, _rep in ECE314_LABS:
    body += event(f"ECE314 Lab {n} · 电能", local(d, 10, 0), local(d, 13, 0),
                  "GB40", f"ECE314 PRA0105\nLab {n}\nGB40", cats="上课")
for n, d, _rep in ECE311_LABS:
    body += event(f"ECE311 Lab {n} · 控制", local(d, 15, 0), local(d, 18, 0),
                  "BA3114", f"ECE311 PRA0106\nLab {n}: {ECE311_LAB_TITLES[n]}\nBA3114",
                  cats="上课")
for n, d in ECE334_LABS:
    tag = " (PASS/FAIL)" if n == 0 else ""
    body += event(f"ECE334 Lab {n} · 数电{tag}", local(d, 9, 0), local(d, 12, 0),
                  "SF2206", f"ECE334 PRA0103\nLab {n}{tag}\nSF2206", cats="上课")

with open(f"{OUT_DIR}/课表.ics", "w", encoding="utf-8", newline="") as f:
    f.write(calendar("2026Fall 课表", body))
print("课表.ics ok")


# ====================== 2. 任务与考试.ics ==================================
body = []

# --- 提醒节奏（标准档） ---
# 截止类：提前 3 天早上 9 点 + 提前 1 天早上 9 点
# lab 当天：早 7:30
# 考试：提前 14 / 7 / 3 天 + 当天早 7:30


def before_at(anchor, days, hour):
    """相对事件开始时刻 anchor，提前 N 天当天 hour 点触发，返回 ics TRIGGER 值。
    注意基准必须是 VEVENT 的 DTSTART —— ics 的 TRIGGER 就是相对它算的。"""
    target = (anchor - dt.timedelta(days=days)).replace(hour=hour, minute=0)
    total = int((anchor - target).total_seconds())
    d, rem = divmod(total, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    s = "-P"
    if d:
        s += f"{d}D"
    if h or m:
        s += "T"
        if h:
            s += f"{h}H"
        if m:
            s += f"{m}M"
    return s if s != "-P" else "-PT5M"


def at(d, h, m):
    return dt.datetime.combine(d, dt.time(h, m))


# ---------- ECE314 lab prep（⚠️ 周一 12:00 全体统一死线） ----------
for n, lab_d, prep_d, rep_d in ECE314_LABS:
    dl = at(prep_d, 11, 30)   # = 本事件 DTSTART
    body += event(
        f"⚠️ 截止 ECE314 Lab {n} prep（12:00）",
        local(prep_d, 11, 30), local(prep_d, 12, 0),
        "Quercus 提交",
        f"ECE314 Lab {n} 的 lab prep 截止。\n\n"
        f"⚠️ 注意：你的 lab 在 {lab_d.strftime('%m月%d日')}（周三 10:00），"
        f"但 prep 是全体统一死线 —— syllabus 规定必须在该 lab 的第一个 section "
        f"（PRA0103，周一 12:00）开始前交，所以比你上 lab 早两天。\n\n"
        f"迟交每天扣 10%（向上取整）。",
        alarms=[
            alarm(before_at(dl, WORKLOAD["prep"][0], 9),
                  f"今天开始做 ECE314 Lab {n} prep —— 约 {WORKLOAD['prep'][1]:g} 小时，周一 12:00 截止"),
            alarm(before_at(dl, 1, 9), f"ECE314 Lab {n} prep 明天中午 12:00 截止 —— 今天必须做完"),
            alarm("-PT2H", f"ECE314 Lab {n} prep 2 小时后截止"),
        ],
        cats="截止",
    )
    # lab 当天早提醒
    body += event(
        f"ECE314 Lab {n} 今天（10:00 GB40）",
        local(lab_d, 7, 30), local(lab_d, 7, 45), "GB40",
        f"ECE314 Lab {n}，10:00-13:00 @ GB40。\n带：lab handout、prep、笔记本电脑。\n"
        f"报告截止 {rep_d.strftime('%m月%d日')}。",
        alarms=[alarm("-PT5M", f"今天 10:00 ECE314 Lab {n} @ GB40")],
        cats="实验",
    )
    # 报告截止
    warn = ""
    if rep_d in READING_WEEK:
        warn = "\n\n⚠️ 这个日期落在 Reading Week（Oct 26-30）里。syllabus 没写遇上休息周怎么办 —— 上完 Lab 3 当场问 TA 确认是否顺延。"
    dl = at(rep_d, 23, 0)     # = 本事件 DTSTART
    body += event(
        f"截止 ECE314 Lab {n} 报告",
        local(rep_d, 23, 0), local(rep_d, 23, 59), "Quercus 提交",
        f"ECE314 Lab {n} 实验报告截止（小组提交，lab 后一周）。\n迟交每天扣 10%。{warn}",
        alarms=[
            alarm(before_at(dl, WORKLOAD["report"][0], 9),
                  f"今天开始写 ECE314 Lab {n} 报告 —— 约 {WORKLOAD['report'][1]:g} 小时，小组的，先约时间"),
            alarm(before_at(dl, 0, 8), f"ECE314 Lab {n} 报告今晚截止"),
        ],
        cats="截止",
    )

# ---------- ECE311 lab prep + 报告 ----------
for n, lab_d, rep_d in ECE311_LABS:
    dl = at(lab_d, 14, 30)    # = 本事件 DTSTART
    body += event(
        f"⚠️ 截止 ECE311 Lab {n} prep（15:00 lab 开始前）",
        local(lab_d, 14, 30), local(lab_d, 15, 0), "BA3114",
        f"ECE311 Lab {n}: {ECE311_LAB_TITLES[n]}\n\n"
        f"prep 必须在 lab 开始前（周五 15:00）交，每人各交各的。\n\n"
        f"⚠️ ECE311 迟交政策是最严的：不接受任何迟交，不接受邮件提交，迟交直接 0 分。"
        f"如果确实赶不上，必须在截止前联系老师拿许可。",
        alarms=[
            alarm(before_at(dl, WORKLOAD["prep"][0], 9),
                  f"今天开始做 ECE311 Lab {n} prep —— 约 {WORKLOAD['prep'][1]:g} 小时，周五 15:00 截止，迟交 0 分"),
            alarm(before_at(dl, 2, 9), f"ECE311 Lab {n} prep 还有 2 天"),
            alarm("-PT3H", f"ECE311 Lab {n} prep 今天 15:00 前必须交（迟交 0 分）"),
        ],
        cats="截止",
    )
    dl = at(rep_d, 23, 0)     # = 本事件 DTSTART
    body += event(
        f"截止 ECE311 Lab {n} 报告",
        local(rep_d, 23, 0), local(rep_d, 23, 59), "Quercus 提交",
        f"ECE311 Lab {n}: {ECE311_LAB_TITLES[n]}\n实验报告截止（小组提交，lab 后一周）。\n"
        f"⚠️ 迟交 0 分，无例外。",
        alarms=[
            alarm(before_at(dl, WORKLOAD["report"][0], 9),
                  f"今天开始写 ECE311 Lab {n} 报告 —— 约 {WORKLOAD['report'][1]:g} 小时，迟交 0 分"),
            alarm(before_at(dl, 0, 8), f"ECE311 Lab {n} 报告今晚截止 —— 迟交 0 分"),
        ],
        cats="截止",
    )

# ---------- ECE334 lab ----------
for n, lab_d in ECE334_LABS:
    tag = "（PASS/FAIL，必须过）" if n == 0 else ""
    prep_d = lab_d - dt.timedelta(days=3)  # 前一个周一
    dl = at(prep_d, 19, 0)    # = 本事件 DTSTART
    body += event(
        f"准备 ECE334 Lab {n}（本周四 9:00）",
        local(prep_d, 19, 0), local(prep_d, 20, 0), "",
        f"ECE334 Lab {n}{tag} 在 {lab_d.strftime('%m月%d日')}（周四 9:00-12:00 @ SF2206）。\n\n"
        f"今晚过一遍 lab handout（Quercus 上），把要预先算的、要预先写的 Spice/仿真部分做完。\n\n"
        f"注：syllabus 没有明确写 ECE334 是否有独立评分的 prelab —— 第一次 lab 时向 TA 确认，"
        f"如果有，把这条提醒改成硬截止。\n\n"
        f"5 个 lab 共 20%。Lab 0 是 PASS/FAIL，过了之后只有后 4 个计分。\n"
        f"因病缺 lab 必须事先和 lab TA 约好补做时段。",
        alarms=[alarm("-PT5M", f"今晚过一遍 ECE334 Lab {n} handout，周四要用")],
        cats="准备",
    )
    body += event(
        f"ECE334 Lab {n} 今天（9:00 SF2206）{tag}",
        local(lab_d, 7, 30), local(lab_d, 7, 45), "SF2206",
        f"ECE334 Lab {n}{tag}，9:00-12:00 @ SF2206。",
        alarms=[alarm("-PT5M", f"今天 9:00 ECE334 Lab {n} @ SF2206")],
        cats="实验",
    )

# ---------- LIN200 quiz ----------
for n, close_d in LIN200_QUIZ:
    open_d = quiz_open(close_d)
    span = (close_d - open_d).days
    dl = at(close_d, 23, 0)   # = 本事件 DTSTART
    body += event(
        f"截止 LIN200 Quiz {n}（23:59）",
        local(close_d, 23, 0), local(close_d, 23, 59), "Quercus",
        f"LIN200 Quiz {n}，占 3%（9 个 quiz 共 27%）。\n\n"
        f"周四 {open_d.strftime('%m月%d日')} {QUIZ_OPEN_AT[0]}:{QUIZ_OPEN_AT[1]:02d} 放出，"
        f"周五 {close_d.strftime('%m月%d日')} 23:59 关闭，可做窗口 {span} 天。\n"
        f"开始后有 48 小时窗口，但不能超过关闭时间 —— 别拖到周五晚上才点开。\n\n"
        f"可以用讲义和课本，不能用其他网络资源或 AI，必须独立完成。\n"
        f"除特殊情况外没有补考机会（答案在截止后很快公布）。",
        alarms=[
            alarm(before_at(dl, span, QUIZ_OPEN_AT[0] + 1),
                  f"LIN200 Quiz {n} 已放出，从今晚起随时可做 —— 约 "
                  f"{WORKLOAD['quiz'][1]:g} 小时，{close_d.strftime('%m月%d日')} 23:59 关闭。"
                  f"点开之后 48 小时内必须交"),
            alarm(before_at(dl, 3, 18),
                  f"LIN200 Quiz {n} 还有 3 天关闭 —— 还没做就今晚做掉"),
            alarm(before_at(dl, 0, 18), f"LIN200 Quiz {n} 今晚 23:59 关闭 —— 还没做就现在做"),
        ],
        cats="截止",
    )

# ---------- 考试 ----------
for c, name, d, (h1, m1), (h2, m2), room, note in EXAMS:
    dl = at(d, h1, m1)        # = 本事件 DTSTART
    body += event(
        f"📝 {c} {name}",
        local(d, h1, m1), local(d, h2, m2), room or "教室待通知",
        f"{c}（{CN[c]}） {name}\n{d.strftime('%Y-%m-%d')} {h1:02d}:{m1:02d}-{h2:02d}:{m2:02d}\n\n{note}",
        alarms=[
            alarm(before_at(dl, WORKLOAD["exam"][0], 9),
                  f"今天开始复习 {c} {name} —— 还有 {WORKLOAD['exam'][0]} 天"),
            alarm(before_at(dl, 7, 9), f"{c} {name} 还有一周"),
            alarm(before_at(dl, 3, 9), f"{c} {name} 还有 3 天"),
            alarm(before_at(dl, 0, 7), f"今天 {h1:02d}:{m1:02d} {c} {name}"),
        ],
        cats="考试",
    )

# ---------- 校历 / 全天事件 ----------
def allday(d1, d2, summary, desc, alarms=()):
    return event(summary, d1.strftime("%Y%m%d"),
                 (d2 + dt.timedelta(days=1)).strftime("%Y%m%d"),
                 desc=desc, allday=True, alarms=alarms, cats="校历")


body += allday(dt.date(2026, 10, 12), dt.date(2026, 10, 12),
               "🍁 感恩节 · 不上课",
               "Thanksgiving Monday。全校停课。\n"
               "ECE302 的 Mon 9-11 tut 和 13-16 lec、ECE314 Mon 11-12 lec 都没有。")
body += allday(dt.date(2026, 10, 26), dt.date(2026, 10, 30),
               "📚 Reading Week · 全周停课",
               "Oct 26-30 全周无课、无 tutorial、无 lab、无 quiz、无 office hour。\n\n"
               "⚠️ 但 ECE314 Lab 3 的报告按「lab 后一周」算正好落在 Oct 28。"
               "上完 Lab 3（Oct 21）当场问 TA 是否顺延。",
               alarms=[alarm("-P6DT15H", "下周是 Reading Week —— 确认 ECE314 Lab 3 报告是否顺延")])
body += allday(dt.date(2026, 11, 17), dt.date(2026, 11, 17),
               "⚠️ 最后退课日 (Last day to drop)",
               "今天是本学期最后一天可以 drop 课而不留记录。\n\n"
               "到这一天为止你已经知道的成绩：ECE334 两次 term test（30%）、"
               "ECE311 Midterm 1（15%）、LIN200 期中（28%）+ 6 次 quiz、ECE314 Midterm 1（15%）、"
               "ECE302 两次期中（占比未知）。"
               "足够判断了。\n\n⚠️ 同一天晚上 18:30 还有 ECE311 Midterm 2。",
               alarms=[alarm("-P13DT15H", "两周后（11月17日）是最后退课日 —— 开始算各科成绩"),
                       alarm("-P2DT15H", "11月17日是最后退课日")])
body += allday(dt.date(2026, 12, 8), dt.date(2026, 12, 8),
               "🎓 最后上课日",
               "本学期最后一天上课。之后进入考试期。")
body += allday(dt.date(2026, 12, 10), dt.date(2026, 12, 22),
               "📝 期末考试期 (Dec 10-22)",
               "四门 ECE + LIN200 的 final 都在这个区间，具体日期学校统一公布。\n\n"
               "各科 final 权重：\n"
               "· ECE311 55%（且必须 ≥40% 才能及格，否则最高只给 49）\n"
               "· ECE314 55%（同样有 40% 及格线）\n"
               "· ECE334 50%（可带一张手写双面 aid sheet）\n"
               "· LIN200 35%（累积考 Week 1-12）\n"
               "· ECE302 未知（syllabus 还没拿到）\n\n"
               "⚠️ 考试表出来后回来把具体日期填上。",
               alarms=[alarm("-P20DT15H", "三周后进考试期 —— 查一下具体考试日期出来没有")])
body += allday(dt.date(2026, 9, 14), dt.date(2026, 9, 14),
               "❓ 补 ECE302 syllabus",
               "ECE302 是唯一一门没找到 syllabus 的课（Quercus 上也没有）。\n\n"
               "今天上课时问老师要，重点确认：\n"
               "· 两次期中的日期和时间\n"
               "· 评分权重（作业/期中/期末各占多少）\n"
               "· 有没有要交的作业，多久一次\n"
               "· 有没有 lab / project\n\n"
               "拿到后放进 G:\\我的云端硬盘\\GoodNotes\\2026fall\\ECE302\\，然后重跑 schedule-widget/gen.py。",
               alarms=[alarm("PT9H", "今天 ECE302 上课记得问 syllabus（期中日期、评分权重、作业安排）")])

with open(f"{OUT_DIR}/任务与考试.ics", "w", encoding="utf-8", newline="") as f:
    f.write(calendar("2026Fall 任务与考试", body))
print("任务与考试.ics ok")


# ====================== 3. 学期日程.md（Obsidian 总览） ====================
MD = []
W = "一二三四五六日"


def cn(d):
    return f"{d.month}月{d.day}日(周{W[d.weekday()]})"


# 汇总所有任务 → {date: [(排序键, 文本)]}
tasks = {}


def add(d, order, text):
    tasks.setdefault(d, []).append((order, text))


for n, lab_d, prep_d, rep_d in ECE314_LABS:
    add(prep_d, 0, f"**截止 12:00** ECE314 Lab {n} prep ⚠️比自己的 lab 早两天")
    add(lab_d, 1, f"ECE314 Lab {n} · 10:00-13:00 GB40")
    add(rep_d, 0, f"**截止** ECE314 Lab {n} 报告"
        + ("（⚠️落在 Reading Week，需向 TA 确认是否顺延）" if rep_d in READING_WEEK else ""))
for n, lab_d, rep_d in ECE311_LABS:
    add(lab_d, 0, f"**截止 15:00** ECE311 Lab {n} prep（迟交 0 分）")
    add(lab_d, 1, f"ECE311 Lab {n} · 15:00-18:00 BA3114 —— {ECE311_LAB_TITLES[n]}")
    add(rep_d, 0, f"**截止** ECE311 Lab {n} 报告（迟交 0 分）")
for n, lab_d in ECE334_LABS:
    add(lab_d - dt.timedelta(days=3), 2, f"过一遍 ECE334 Lab {n} handout（周四要用）")
    add(lab_d, 1, f"ECE334 Lab {n} · 9:00-12:00 SF2206"
        + ("（PASS/FAIL，必须过）" if n == 0 else ""))
for n, close_d in LIN200_QUIZ:
    add(close_d, 0, f"**截止 23:59** LIN200 Quiz {n}（3%）")
for c, name, d, (h1, m1), (h2, m2), room, _note in EXAMS:
    add(d, -1 + (h1 * 60 + m1) / 10000,
        f"> 📝 **{c} {name}** · {h1:02d}:{m1:02d}-{h2:02d}:{m2:02d}"
        + (f" {room}" if room else ""))
add(dt.date(2026, 10, 12), -2, "🍁 感恩节，全天停课")
add(dt.date(2026, 11, 17), -2, "⚠️ **最后退课日**")
add(dt.date(2026, 12, 8), -2, "🎓 最后上课日")

# 可做窗口一开就插一条 —— 材料到手了，翻到那一周就能提前把时间占上。
# 建议动手日跟开窗同一天的（quiz 就是这样）不重复插，下面那条已经说了。
for _it in upcoming(TERM_START, 400):
    if not _it.needs_work or not _it.opens or _it.opens >= _it.start:
        continue
    add(_it.opens, 0.4,
        f"🟢 **{_it.label}** 可以开始了"
        f"（窗口到 {_it.date.month}月{_it.date.day}日）")

# 建议动手日单独插一条 —— 翻到那一周就知道该起手了，不用自己倒推
for _it in upcoming(TERM_START, 400):
    if not _it.needs_work or _it.start == _it.date:
        continue
    _due = f"{_it.date.month}月{_it.date.day}日"
    if _it.kind == "exam":
        add(_it.start, 0.5, f"▶ **开始复习 {_it.text}**（{_due} 考）")
    else:
        # 开窗即动手的（quiz），把放出时刻也写上 —— 那天早上还没得做
        _open = (f"{_it.opens_at[0]}:{_it.opens_at[1]:02d} 放出，"
                 if _it.opens == _it.start and _it.opens_at != (0, 0) else "")
        add(_it.start, 0.5,
            f"▶ **开始做 {_it.label}**"
            f"（{_open}约 {_it.hours:g} 小时，{_due} 截止）")

MD.append("""# 2026 Fall 学期日程

> 由 `schedule-widget/gen.py` 从各科 syllabus 自动生成。改日期请改脚本再重跑，别直接改这个文件。
> 手机 / iPad / 电脑的推送提醒来自 `schedule-widget/任务与考试.ics`。

## 先看这几条

| | |
|---|---|
| ❓ **ECE302 没有 syllabus** | 两次期中已按 Quercus 公告补上（10月8日 EX200、11月5日 MS3154）。还缺：评分权重、作业安排、有无 lab。拿到后放进 `G:/我的云端硬盘/GoodNotes/2026fall/ECE302/` 再重跑脚本。 |
| ⚠️ **ECE314 的 lab prep 提前两天死线** | syllabus 规定 prep 必须在该 lab 的**第一个** section（PRA0103，周一 12:00）开始前交。你的 lab 在周三，但 prep 周一中午就截止。讲义 lecture 1 上写的是「lab 开始时交」，两者矛盾 —— 按早的算，第一次 lab 时找 TA 确认。 |
| ⚠️ **10月6日—8日连考三天** | 10月6日 12:00 ECE334 Term Test 1；10月7日 18:30 ECE311 Midterm 1（EX100，原定 10月6日，Quercus 9月29日公告改期）；10月8日 18:00 ECE302 Midterm 1（EX200）。10月7日白天还有 ECE314 Lab 2（10:00-13:00）。 |
| ⚠️ **ECE314 Lab 3 报告撞 Reading Week** | 按「lab 后一周」算是 10月28日，正在休息周里。10月21日上完 Lab 3 当场问 TA。 |
| ❓ **ECE334 有没有单独计分的 prelab** | syllabus 没写。第一次 lab（9月24日）时问 TA。如果有，把日程里的「过一遍 handout」改成硬截止。 |
| ❓ **五门课的 Final 日期全部 TBD** | 都在 12月10-22 考试期内，学校统一公布。出来后补进脚本。 |
| ❓ **ECE311 习题课教室** | syllabus 写 BA1200，你之前记的是 BA1220。第一次去之前在 ACORN 上确认一下。 |

## 任务要花多久

「▶ 开始做」的日子是从截止倒推的，倒推多少天、预计几小时写在 `schedule-widget/data.py`
的 `WORKLOAD` 里：

| 类型 | 提前动手 | 预计耗时 | 为什么这么定 |
|---|---|---|---|
| Lab prep | 4 天 | 2.5 小时 | 要预算、预仿真，得跨一个周末才够 |
| 实验报告 | 4 天 | 3.5 小时 | 小组交的，得先约上时间 |
| LIN200 Quiz | 开窗即动手 | 1 小时 | 周四 18:00 放出、下周五 23:59 关，窗口 8 天；点开后 48 小时内必须交 |
| 过 lab handout | 当天 | 1 小时 | 一晚上过完 |
| 期中复习 | 14 天 | — | 提前两周进状态 |

**这套数字是估的，不是实测。** 做完第一个 lab、写完第一份报告之后回来改成真实耗时
—— 改一次，ics 提醒、这个文件、桌面组件三处一起变。

## 每周

""")

# 按周输出
w = dt.date(2026, 9, 7)  # 第一个周一
wk = 0
while w <= dt.date(2026, 12, 12):
    days = [w + dt.timedelta(days=i) for i in range(7)]
    hits = [d for d in days if d in tasks]
    wk += 1
    label = f"第 {wk} 周 · {w.month}月{w.day}日 – {days[6].month}月{days[6].day}日"
    if w == dt.date(2026, 10, 26):
        label += " · 📚 READING WEEK"
    if w >= dt.date(2026, 12, 7):
        label += " · 考试期开始"
    if not hits:
        MD.append(f"### {label}\n\n无截止事项，正常上课。\n")
    else:
        MD.append(f"### {label}\n")
        for d in hits:
            items = sorted(tasks[d])
            MD.append(f"**{cn(d)}**\n")
            for _o, t in items:
                if t.startswith(">"):
                    MD.append(t)
                    MD.append("")   # 引用块后必须空行，否则和下面的列表粘连
                else:
                    MD.append(f"- {t}")
            MD.append("")
    w += dt.timedelta(days=7)

MD.append("""## 各科评分构成

| 课 | 平时/实验 | 期中 | 期末 | 硬性要求 |
|---|---|---|---|---|
| **ECE311** 控制 | Lab 15% | MT1 15% + MT2 15% | 55% | Final **必须 ≥40%**，否则最高只给 49 分。迟交一律 0 分，不接受邮件提交。 |
| **ECE314** 电能 | Lab 15% | MT1 15% + MT2 15% | 55% | Final **必须 ≥40%**。迟交每天扣 10%。 |
| **ECE334** 数电 | Lab 20%（5 个，Lab 0 是 PASS/FAIL，过了之后只算后 4 个） | TT1 15% + TT2 15% | 50% | 两次 term test 必须用钢笔作答才能申请复核。迟交每天扣 10%。 |
| **LIN200** 语言学 | Quiz 9×3% = 27% + 习题课出勤 10%（强制） | 28% | 35% | 习题课必须去，且光到场不给满分，要参与讨论。另有实验参与加分 1%。 |
| **ECE302** 概率 | — | MT1 + MT2（占比未知） | — | ❓ 等 syllabus |

## 不计分但要做的

- **ECE311 homework ×6**：隔周在 Quercus 发布，不计分。syllabus 明说「学生自己主动做是符合自身利益的」，且这门 55% 压在 final 上。
- **ECE314 homework**：不计分，但讲义原话是「和期末高度相关」。
- **LIN200 教材阅读**：每周对应 *Essentials of Linguistics* 一章，不是强制但期中期末都从里面出。Ch1→Ch2→Ch3(×2周)→Ch4(×2周)→Ch5→Ch6,7→Ch9→Ch10→Ch11-12。
- **ECE334 教材**：*CMOS VLSI Design* 4th ed.，`ece334_outline_2026.pdf` 里有 37 讲逐讲对应的章节号，跟着上课进度读。

## 校历

- 9月8日 开学
- 10月12日 感恩节，停课
- 10月26–30日 Reading Week，全周无课/无 lab/无 quiz/无 office hour
- **11月17日 最后退课日**（当晚 18:30 还有 ECE311 Midterm 2）
- 12月8日 最后上课日
- 12月10–22日 期末考试期

## 日历文件怎么用

`schedule-widget/` 下两个 ics：

| 文件 | 内容 | 导到哪 |
|---|---|---|
| `课表.ics` | 每周上课时段 + 隔周 lab 的实际时段 | **电脑、iPad**（手机上已经有课表了，别重复导） |
| `任务与考试.ics` | prelab / lab 提醒 / 报告截止 / quiz 截止 / 考试 / 校历，共 111 条提醒 | **三台都导** |

重新生成：

```
python schedule-widget/gen.py
```

重新导入前，先在日历 app 里删掉旧的那个日历（两个文件各自是独立日历，删除干净再导，否则会重复）。
""")

with open(os.path.join(VAULT, "学期日程.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(MD))
print("学期日程.md ok")
