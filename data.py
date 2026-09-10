# -*- coding: utf-8 -*-
"""2026 Fall 全部日程数据 —— 唯一数据源。

全部逐条核对自 GoodNotes/2026fall/ 下各科 syllabus。
日期要改就改这里，然后重跑 gen.py（出 ics 和 md）和 wallpaper.py（出壁纸）。
"""
import datetime as dt
import os
from dataclasses import dataclass

# 路径都相对本文件，别写死盘符 —— 换台机器/换个盘符照样跑
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = HERE

# 学期日程.md 要写进 Obsidian 库，而库和这个仓库现在是两个地方（仓库在桌面，
# 库在 D:/Study），所以库的位置得显式记下来。
CONFIG_DIR = os.path.join(os.environ.get("APPDATA", HERE), "schedule-widget")
VAULT_FILE = os.path.join(CONFIG_DIR, "vault.txt")


def save_vault(path):
    """记住 Obsidian 库在哪。存进 %APPDATA% 而不是仓库里或 exe 旁边 —— exe 会被
    拷到任何地方，仓库又归 git 管，两处都不适合放这种一台机器一个样的配置。"""
    path = os.path.abspath(path)
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(VAULT_FILE, "w", encoding="utf-8") as fh:
        fh.write(path)
    return path


def find_vault():
    """按 环境变量 → 配置文件 → 老布局 的顺序找，都没有就返回 None，
    由调用方决定是报错（gen.py 必须要有）还是安静跳过（组件只是少个双击）。"""
    cand = [os.environ.get("STUDY_VAULT")]
    if os.path.exists(VAULT_FILE):
        with open(VAULT_FILE, encoding="utf-8") as fh:
            cand.append(fh.read().strip())
    legacy = os.path.dirname(HERE)      # 老布局：代码放在库里的 schedule-widget/ 下
    if os.path.isdir(os.path.join(legacy, ".obsidian")):
        cand.append(legacy)
    for c in cand:
        if c and os.path.isdir(c):
            return os.path.abspath(c)
    return None


VAULT = find_vault()
TZ = "America/Toronto"

# ---- 学期骨架 -------------------------------------------------------------
TERM_START = dt.date(2026, 9, 8)    # 开学（周二）
TERM_END   = dt.date(2026, 12, 8)   # 最后上课日（周二）
HOLIDAYS = [dt.date(2026, 10, 12)]  # 感恩节
READING_WEEK = [dt.date(2026, 10, d) for d in range(26, 31)]  # Oct 26-30
NO_CLASS = HOLIDAYS + READING_WEEK

VTIMEZONE = """BEGIN:VTIMEZONE
TZID:America/Toronto
X-LIC-LOCATION:America/Toronto
BEGIN:DAYLIGHT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
TZNAME:EDT
DTSTART:19700308T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
TZNAME:EST
DTSTART:19701101T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
END:STANDARD
END:VTIMEZONE"""

WD = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4}


def first_on(weekday, not_before):
    """not_before 当天或之后的第一个 weekday"""
    d = not_before
    while d.weekday() != WD[weekday]:
        d += dt.timedelta(days=1)
    return d


# ---- 每周固定上课 ---------------------------------------------------------
# (课号, 类型, 星期, 开始时, 结束时, 地点, section, 学期内起始日, 额外排除日)
WEEKLY = [
    # ECE302 —— 无 syllabus，只有课表
    ("ECE302", "TUT", "Mon", 9, 0, 11, 0, "BA1200", "TUT0101", None, []),
    ("ECE302", "LEC", "Mon", 13, 0, 16, 0, "BA1170", "LEC0102", None, []),
    # ECE314
    ("ECE314", "LEC", "Mon", 11, 0, 12, 0, "GB244", "LEC0101", None, []),
    ("ECE314", "LEC", "Tue", 14, 0, 15, 0, "GB244", "LEC0101", None, []),
    ("ECE314", "TUT", "Tue", 16, 0, 17, 0, "HA410", "TUT0101", None, []),
    ("ECE314", "LEC", "Fri", 13, 0, 14, 0, "GB120", "LEC0101",
     None, [dt.date(2026, 10, 23), dt.date(2026, 11, 20)]),  # 两次期中占用
    # ECE334 —— TUT 从第 2 周 Sep 15 起
    ("ECE334", "TUT", "Tue", 9, 0, 10, 0, "WB130", "TUT0101", dt.date(2026, 9, 15), []),
    ("ECE334", "LEC", "Tue", 12, 0, 13, 0, "MP103", "LEC0101",
     None, [dt.date(2026, 10, 6), dt.date(2026, 11, 10)]),   # 两次 term test 占用
    ("ECE334", "LEC", "Thu", 12, 0, 13, 0, "BA1130", "LEC0101", None, []),
    ("ECE334", "LEC", "Fri", 12, 0, 13, 0, "WB116", "LEC0101", None, []),
    # ECE311 —— 第 1 周无 tutorial
    ("ECE311", "LEC", "Tue", 13, 0, 14, 0, "SF1105", "LEC0101", None, []),
    ("ECE311", "LEC", "Wed", 9, 0, 10, 0, "SF1101", "LEC0101", None, []),
    ("ECE311", "TUT", "Wed", 17, 0, 18, 0, "BA1200", "TUT0102", dt.date(2026, 9, 16), []),
    ("ECE311", "LEC", "Fri", 14, 0, 15, 0, "BA1160", "LEC0101", None, []),
    # LIN200 —— Week 6 (Oct 15) 无 tutorial；Oct 13 lecture 被期中占用
    ("LIN200", "LEC", "Tue", 17, 0, 19, 0, "KP108", "LEC2501",
     None, [dt.date(2026, 10, 13)]),
    ("LIN200", "TUT", "Thu", 16, 0, 17, 0, "BF215", "TUT0301",
     None, [dt.date(2026, 10, 15)]),
]

CN = {"ECE302": "概率", "ECE311": "控制", "ECE314": "电能", "ECE334": "数电", "LIN200": "语言学"}
KIND_CN = {"LEC": "课", "TUT": "习题课", "PRA": "实验"}

# ---- Lab 排期（已对到我自己的 section） -----------------------------------
# ECE314 PRA0105 Wed 10:00-13:00 GB40
ECE314_LABS = [
    (1, dt.date(2026, 9, 23),  dt.date(2026, 9, 21),  dt.date(2026, 9, 30)),
    (2, dt.date(2026, 10, 7),  dt.date(2026, 10, 5),  dt.date(2026, 10, 14)),
    (3, dt.date(2026, 10, 21), dt.date(2026, 10, 19), dt.date(2026, 10, 28)),
    (4, dt.date(2026, 11, 11), dt.date(2026, 11, 9),  dt.date(2026, 11, 18)),
    (5, dt.date(2026, 11, 25), dt.date(2026, 11, 23), dt.date(2026, 12, 2)),
]
# ECE311 PRA0106 Fri 15:00-18:00 BA3114 —— prep 在 lab 开始前交，report 一周后
ECE311_LABS = [
    (1, dt.date(2026, 10, 16), dt.date(2026, 10, 23)),
    (2, dt.date(2026, 11, 6),  dt.date(2026, 11, 13)),
    (3, dt.date(2026, 11, 20), dt.date(2026, 11, 27)),
    (4, dt.date(2026, 12, 4),  dt.date(2026, 12, 11)),
]
ECE311_LAB_TITLES = {
    1: "Introduction to LTI Systems in Matlab and Simulink",
    2: "Control of a Magnetically Levitated Ball",
    3: "Speed Control of a Simplified Car Model",
    4: "Position Control of a Simplified Cart Model",
}
# ECE334 PRA0103 Thu 9:00-12:00 SF2206
ECE334_LABS = [
    (0, dt.date(2026, 9, 24)),
    (1, dt.date(2026, 10, 8)),
    (2, dt.date(2026, 10, 22)),
    (3, dt.date(2026, 11, 19)),
    (4, dt.date(2026, 12, 3)),
]
# LIN200 quiz —— 周四 18:00 放出，下一周的周五 23:59 关闭，窗口 8 天。
# syllabus 只说 "made available by end-of-day Thursdays ... close on the following
# Fridays"、"the quiz will be open for a week"，18:00 这个点是实际观察到的
# （2026-09-10 Quiz 1 就是当天 18:00 开）。放出是哪个周四由 quiz_open() 按课表算。
QUIZ_OPEN_AT = (18, 0)
LIN200_QUIZ = [
    (1, dt.date(2026, 9, 18)),  (2, dt.date(2026, 9, 25)),
    (3, dt.date(2026, 10, 2)),  (4, dt.date(2026, 10, 9)),
    (5, dt.date(2026, 11, 6)),  (6, dt.date(2026, 11, 13)),
    (7, dt.date(2026, 11, 20)), (8, dt.date(2026, 11, 27)),
    (9, dt.date(2026, 12, 4)),
]
# 考试 (课号, 名称, 日期, 起, 止, 备注)
EXAMS = [
    ("ECE334", "Term Test 1", dt.date(2026, 10, 6), (12, 0), (13, 0),
     "闭卷。允许一张手写单面 8.5x11 aid sheet。必须用钢笔/圆珠笔作答，否则不能申请复核。占 15%。日期 tentative，考前确认。"),
    ("ECE311", "Midterm 1", dt.date(2026, 10, 6), (18, 30), (20, 0),
     "1.5 小时。占 15%。⚠️ 同一天 12:00 还有 ECE334 Term Test 1。"),
    ("LIN200", "Midterm", dt.date(2026, 10, 13), (17, 0), (19, 0),
     "在 lecture 时段线下进行，110 分钟，覆盖 Week 1-5。占 28%。补考仅限特殊情况：Oct 16 (Fri) 17:10-19:00，须在期中后 24 小时内联系老师。"),
    ("ECE314", "Midterm 1", dt.date(2026, 10, 23), (13, 0), (14, 0),
     "1 小时，占 15%。教室另行通知（不一定是 GB120）。"),
    ("ECE334", "Term Test 2", dt.date(2026, 11, 10), (12, 0), (13, 0),
     "闭卷。一张手写单面 aid sheet。占 15%。日期 tentative。"),
    ("ECE311", "Midterm 2", dt.date(2026, 11, 17), (18, 30), (20, 0),
     "1.5 小时。占 15%。⚠️ 同一天是最后退课日。"),
    ("ECE314", "Midterm 2", dt.date(2026, 11, 20), (13, 0), (14, 0),
     "1 小时，占 15%。教室另行通知。⚠️ 同一天 15:00 ECE311 Lab 3。"),
]


LOOKAHEAD = 14   # 「接下来」默认往前看多少天

# 每类任务：建议提前几天动手 + 大概要几小时。
# 提前天数只是「建议什么时候起手」，跟「什么时候才可以起手」是两回事 ——
# 后者是 Item.opens（材料放出/前置做完），见 OPEN_LEAD 和 quiz_open()。
# 这套数字是按「syllabus 说了什么 + 截止窗口有多长」估的，不是实测。
# 做完第一次就回来改成自己的真实耗时 —— 这里改一次，ics 提醒、学期日程.md、
# 桌面组件三处一起变。
WORKLOAD = {
    # 类型      提前天数  小时   说明
    "prep":    (4, 2.5),   # lab prep：要预算/预仿真，跨一个周末才够
    "report":  (4, 3.5),   # 实验报告：小组的，得先约上时间
    "quiz":    (8, 1.0),   # 开窗即动手：放出那天就该做，别攒到最后（见 START_AT_OPEN）
    "read":    (0, 1.0),   # 过 lab handout：当晚一次过完
    "exam":    (14, None),  # 期中：提前两周进复习
    "lab":     (0, None),   # lab 本身是去上，不用提前做
}


# 「可做窗口」的起点：材料放出、或者前置做完的那一刻。到这天才谈得上开始做。
# lab 类的 handout 三门 syllabus 都没写什么时候上 Quercus（ECE334 只说
# "Lab handouts are/will be available on the course website"），所以按提前一周估；
# 看到真实发布日就改这里。报告的起点是确定的 —— lab 做完才写得了。
OPEN_LEAD = {"prep": 7, "read": 7}   # 相对 lab 当天往前几天，报告/quiz 另行计算

# 这些类型「开窗即动手」：窗口一开就该做，不再另算提前天数
START_AT_OPEN = {"quiz"}


@dataclass(frozen=True)
class Item:
    """一件要做的事。date/at 是截止(或发生)时刻，start 是建议动手的日子。"""
    date: dt.date
    hard: bool          # 硬截止（错过有代价） vs 只是日程上的一件事
    text: str
    kind: str           # prep / report / quiz / read / exam / lab
    at: tuple           # (时, 分)
    opens: dt.date = None   # 可做窗口的起点；None = 没这个概念（课、考试）
    opens_at: tuple = (0, 0)   # 那天几点才算开窗（quiz 是 18:00 才放出来）

    @property
    def label(self):
        """去掉「截止」后缀的干净名字，用在「开始做 X」这种句子里"""
        return self.text.removesuffix("截止").strip()

    @property
    def lead(self):
        return WORKLOAD.get(self.kind, (0, None))[0]

    @property
    def hours(self):
        return WORKLOAD.get(self.kind, (0, None))[1]

    @property
    def start(self):
        """建议哪天动手。不会早于可做窗口 —— 材料还没放出，催也没用。"""
        if self.opens and self.kind in START_AT_OPEN:
            return self.opens
        d = self.date - dt.timedelta(days=self.lead)
        return max(d, self.opens) if self.opens else d

    @property
    def needs_work(self):
        """是要自己花时间做的事（考试复习也算），还是只是去上一节课"""
        return self.hours is not None or self.kind == "exam"

    def _open_yet(self, today, now_min):
        """开窗当天还得过了放出时刻才算数 —— 周四早上 quiz 还没出来呢。
        now_min 不给就按一整天算完，日历/月历那种只论天的地方用得上。"""
        return not (self.opens and today == self.opens
                    and now_min < self.opens_at[0] * 60 + self.opens_at[1])

    def started(self, today, now_min=1440):
        return (self.start <= today <= self.date
                and (self.start != self.opens or self._open_yet(today, now_min)))

    def available(self, today, now_min=1440):
        """材料已经放出、还没过截止 —— 这段时间里随时可以做。
        没标 opens 的项退回「到了建议动手日才算」，跟以前一个样。"""
        return ((self.opens or self.start) <= today <= self.date
                and self._open_yet(today, now_min))

    def window(self, today):
        """(窗口共几天, 还剩几天)。没有窗口概念的返回 None。"""
        if not self.opens:
            return None
        return (self.date - self.opens).days, (self.date - today).days

    def days_left(self, today):
        return (self.date - today).days


# ---- 推算某天有什么 -------------------------------------------
def classes_on(d):
    """当天的课，返回 [((开始h,m), (结束h,m), 标题, 地点, 类型)]，按时间排好。
    类型: lec / tut / lab / exam —— 配色由调用方决定。"""
    out = []
    if d in NO_CLASS or not (TERM_START <= d <= TERM_END):
        return out
    for (c, kind, wd, h1, m1, h2, m2, room, _sec, start_from, extra_ex) in WEEKLY:
        if d.weekday() != WD[wd] or d in extra_ex:
            continue
        if d < first_on(wd, start_from or TERM_START):
            continue
        out.append(((h1, m1), (h2, m2), f"{c} {KIND_CN[kind]}", room, kind.lower()))
    for n, lab_d, _p, _r in ECE314_LABS:
        if d == lab_d:
            out.append(((10, 0), (13, 0), f"ECE314 Lab {n}", "GB40", "lab"))
    for n, lab_d, _r in ECE311_LABS:
        if d == lab_d:
            out.append(((15, 0), (18, 0), f"ECE311 Lab {n}", "BA3114", "lab"))
    for n, lab_d in ECE334_LABS:
        if d == lab_d:
            tail = " (P/F)" if n == 0 else ""
            out.append(((9, 0), (12, 0), f"ECE334 Lab {n}{tail}", "SF2206", "lab"))
    for c, name, ed, (h1, m1), (h2, m2), _note in EXAMS:
        if d == ed:
            out.append(((h1, m1), (h2, m2), f"{c} {name}", "考试", "exam"))
    return sorted(out)


def has_class(d, course, kind):
    """那天有没有某门课的某种课时。用来判断 quiz 覆盖的那次 tutorial 到底开没开。"""
    return any(t[2].startswith(course) and t[4] == kind for t in classes_on(d))


def quiz_open(close_d):
    """LIN200 quiz 的放出日：关闭日（周五）往前 8 天的那个周四。

    那天要是没 tutorial 就再退一周 —— 全学期只有 Quiz 5 会走到这一步：往前 8 天
    落在 Reading Week 的 10/29，于是退到 10/22 Tutorial 6 之后放出，跨整个
    Reading Week 一直开到 11/6。这跟 syllabus 周历里 Quiz 5 排在 Week 8 行、
    考的却是 Week 7 内容是对得上的。"""
    d = close_d - dt.timedelta(days=8)
    for _ in range(3):
        if has_class(d, "LIN200", "tut"):
            return d
        d -= dt.timedelta(days=7)
    return close_d - dt.timedelta(days=8)


def upcoming(today, days=LOOKAHEAD):
    """今天起 days 天内的所有截止/实验/考试，按时间排好，返回 [Item]。

    每项都带「建议哪天动手」和「大概要几小时」—— 见 WORKLOAD。
    同一天里硬截止排在前面。"""
    out = []
    for n, lab_d, prep_d, rep_d in ECE314_LABS:
        out.append(Item(prep_d, True, f"ECE314 Lab {n} prep 截止", "prep", (12, 0),
                        lab_d - dt.timedelta(days=OPEN_LEAD["prep"])))
        out.append(Item(lab_d, False, f"ECE314 Lab {n}  GB40", "lab", (10, 0)))
        out.append(Item(rep_d, True, f"ECE314 Lab {n} 报告截止", "report", (23, 59),
                        lab_d))          # 做完 lab 才写得了报告
    for n, lab_d, rep_d in ECE311_LABS:
        out.append(Item(lab_d, True, f"ECE311 Lab {n} prep 截止", "prep", (15, 0),
                        lab_d - dt.timedelta(days=OPEN_LEAD["prep"])))
        out.append(Item(lab_d, False, f"ECE311 Lab {n}  BA3114", "lab", (15, 0)))
        out.append(Item(rep_d, True, f"ECE311 Lab {n} 报告截止", "report", (23, 59),
                        lab_d))
    for n, lab_d in ECE334_LABS:
        out.append(Item(lab_d - dt.timedelta(days=3), False,
                        f"过 ECE334 Lab {n} handout", "read", (19, 0),
                        lab_d - dt.timedelta(days=OPEN_LEAD["read"])))
        out.append(Item(lab_d, False, f"ECE334 Lab {n}  SF2206", "lab", (9, 0)))
    for n, close_d in LIN200_QUIZ:
        out.append(Item(close_d, True, f"LIN200 Quiz {n} 截止", "quiz", (23, 59),
                        quiz_open(close_d), QUIZ_OPEN_AT))
    for c, name, ed, (h1, m1), _e, _note in EXAMS:
        out.append(Item(ed, True, f"{c} {name}", "exam", (h1, m1)))
    lo, hi = today, today + dt.timedelta(days=days)
    return sorted((x for x in out if lo <= x.date <= hi),
                  key=lambda x: (x.date, not x.hard, x.text))


def todo_now(today, days=LOOKAHEAD, now_min=1440):
    """已经到了该动手的时候、但还没过截止的事。这就是「我现在该做什么」。"""
    return [it for it in upcoming(today, days)
            if it.started(today, now_min) and it.needs_work]


def can_start_now(today, days=LOOKAHEAD, now_min=1440):
    """材料已经放出、可以动手，但还没到建议动手日的事。用来提前占好时间。"""
    return [it for it in upcoming(today, days) if it.needs_work
            and it.available(today, now_min) and not it.started(today, now_min)]


def next_exam(today):
    fut = sorted(((d, h, c, n) for c, n, d, h, _e, _x in EXAMS if d >= today))
    if not fut:
        return None
    d_, h_, c_, n_ = fut[0]
    return d_, c_, n_, h_


def week_no(d):
    return (d - dt.date(2026, 9, 7)).days // 7 + 1


def urgency(days):
    """紧急度等级 0=最急(今明天) 1=2~3天 2=4~7天 3=更远。配色由调用方决定。"""
    if days <= 1:
        return 0
    if days <= 3:
        return 1
    if days <= 7:
        return 2
    return 3


def when_cn(days):
    return {0: "今天", 1: "明天", 2: "后天"}.get(days, f"{days} 天后")
