#!/usr/bin/env python3
"""变异电池：一柄一柄割在新写的判据上，要求红的那一本正是被割的那一本。

为什么要有这一本：这一轮加的东西全是新尺子——20 条计算样式对账、斑马纹的"差值"判据、
页尾逐块、以及把取样坐标从手工猜测换成实测的三道守卫。新写的尺子最常见的失效方式
不是量错，而是根本没量：锚点匹配不到、探针取空、坐标过期被沿用，都会绿得毫无声音。
所以每柄刀先量一次 pristine 基线（同一条命令、同一棵树）确认它今天绿，落刀后先读回文件
确认改动真在盘上，再跑闸门，最后核对报出来的名字。

刀的清单不是手抄的：那 20 柄直接由 check-controls.py 里的 SPECS 表生成（同一个定义，
两头的名字不会漂）。每柄割完还顺手跑一遍"另一道闸门看不看得到这一刀"，
那条用来回答"像素这本格是不是多余"——只有计算样式能看见的刀，就该由计算样式去红。
"""
import hashlib
import importlib.util
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = {"css": ROOT / "kawaii-skin.user.css",
         "fixture": ROOT / "preview" / "components.html",
         "geom": ROOT / "preview" / ".build" / "geometry.txt",
         # P05 割的是"配对构建"这件事本身，而它写在出图脚本里，所以这一趟要把脚本也纳入
         # 还原面：电池跑完之后盘上的 shoot.sh 必须是干净那一份，否则下一跑就是在混树上跑。
         "shoot": ROOT / "tools" / "shoot.sh",
         # K18 割的是哨兵档的 token 名单，那份名单住在反代里。proxy.py 的尾部已收进
         # `if __name__ == "__main__":`，所以下面那条 SENT 闸门 exec 它只跑判据、不开机。
         "proxy": ROOT / "tools" / "proxy.py",
         # K37/K38 割的是普查自己那一栏的划分（tools/glass-census.py 的 buckets）。
         # 仪器侧的刀以前没有目标文件：CSS 侧的刀量"皮肤改坏了会红吗"，
         # 而尺子 own 的那一格（族外那一栏收不收面）只有它自己能被割。
         "census": ROOT / "tools" / "glass-census.py"}
GATES = {"CTRL": (["python3", "tools/check-controls.py"], None),
         "PIX": (["./tools/shoot.sh"], {"SKIP_PRE": "1"}),
         "DIFF": (["python3", "tools/diff-shots.py"], None),
         # 普查的正控制：不开浏览器、不起代理，只喂合成人面＋分区断言，秒级。
         "SELF": (["python3", "tools/glass-census.py", "--selftest"], None),
         "SENT": (["python3", "-c",
                   "import importlib.util as u;"
                   "s=u.spec_from_file_location('ks_proxy','tools/proxy.py');"
                   "m=u.module_from_spec(s);s.loader.exec_module(m);"
                   "print('SENT OK 哨兵名单 %d 条，其中墨 token %d 枚' % (len(m.SENTINELS), len(m.INK_TOKENS)))"],
                  None)}
TIMEOUT = {"CTRL": 240, "PIX": 900, "DIFF": 120, "SENT": 60, "SELF": 60}


def sha(t):
    return hashlib.sha256(t.encode()).hexdigest()[:12]


def load_specs():
    """从闸门模块里取 SPECS 与面规则锚点：刀的名册必须由判据本身生成。"""
    spec = importlib.util.spec_from_file_location("_cc", ROOT / "tools" / "check-controls.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PRISTINE = {k: p.read_text(encoding="utf-8") for k, p in FILES.items()}
HASH0 = {k: sha(t) for k, t in PRISTINE.items()}


def restore_all():
    for k, p in FILES.items():
        p.write_text(PRISTINE[k], encoding="utf-8")
    bad = [k for k, p in FILES.items() if sha(p.read_text(encoding="utf-8")) != HASH0[k]]
    if bad:
        sys.exit(f"KNIFE ABORT: 还原后哈希对不上 {bad}——后面的判定都不可信")


def run(gate):
    cmd, extra = GATES[gate]
    env = dict(os.environ, **(extra or {}))
    t0 = time.time()
    r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True,
                       timeout=TIMEOUT[gate])
    return r.returncode, (r.stdout + r.stderr), time.time() - t0


def reds(out):
    return [l for l in out.splitlines()
            if l.startswith("  - ") or "FAIL" in l or "ERROR" in l]


def apply_cut(key, old, new, who, n_want=1):
    """落刀并读回：只证明"文件变成这样"，不证明"闸门跑过这棵树"——后者由 run 负责。

    n_want 默认 1（一柄刀只动一格）。族那四份副本要一起动时才显式给 4：
    逐处 replace(old, new, 1) 在"锚点本来就有 N 处"的树上只会改到第一处，
    那种半具刀被红起来的判据根本归不到它想割的那一格。
    """
    txt = PRISTINE[key]
    n = txt.count(old)
    if n != n_want:
        return f"{who}: 锚点命中 {n} 处，应当恰好 {n_want} 处（刀还没落，不测了）"
    want = txt.replace(old, new)
    if want == txt:
        return f"{who}: 这一刀是 no-op（替换前后一模一样）"
    FILES[key].write_text(want, encoding="utf-8")
    back = FILES[key].read_text(encoding="utf-8")
    if sha(back) != sha(want):
        return f"{who}: 写盘后读回哈希不符（{sha(back)} vs {sha(want)}）"
    return None


def css_spec_cut(name, anchor, prop):
    """把 SPECS 那一行的声明整条摘掉：锚点还在，判据因此只能报"对不上"而不是"找不到"。

    刀以"整个规则块"为单位替换，不以声明文本为单位：`color: var(--ks-ink-1);` 这种声明
    在全文件出现 7 次，按声明切要么切错地方、要么被下面的 count==1 拦成 LANDING-FAIL
    （第一版就是 11 柄刀卡在这里）。块本身带选择器，整块是唯一的。
    """
    txt = PRISTINE["css"]
    hits = list(re.finditer(r"(?<![-\w])" + anchor + r"([^}]*)\}", txt, re.S))
    if len(hits) != 1:
        return None, None, f"规则块命中 {len(hits)} 处"
    block = hits[0].group(0)
    d = re.search(r"(?<![-\w])" + re.escape(prop) + r"\s*:\s*[^;]+;", hits[0].group(1))
    if not d:
        return None, None, f"块里没有 {prop} 声明"
    return block, block.replace(d.group(0), "", 1), None


CC = load_specs()

# 族被抄了几份，是 CSS 自己的事实，不是名册里的一个数。
# 2026-10-10 之前它写成字面量：每往 §4c 添一份逐字副本（#110 那一份、本轮 #135 那一份），
# 21+5 柄刀就一起报「锚点命中 N+1 处，应当恰好 N 处」——同一格失败成批出现，说明钉错的
# 是锚点层次而不是那 26 个数。现在按 CC.load_family() 现数，副本守卫（≥2 份且逐字相同）
# 才是"份数漂了"那一格的判定处。+2 那两支是常驻条分支（给 <a> 上墨、给控件撤面），
# 它们各自重复了 topnav／navbar／页头那几截词根，割族时一起割。
NCOPY = CC.load_family(PRISTINE["css"])
CUT = []
# 三条"反档"线的判定对象是「钉档」那一格撑着的，不是它们各自读的那条声明。
# 2026-10-04 契约分裂后那一格住在浮动面专属的一条规则里（CC.PIN），不在面块：
# 面块现在只画面（底／虚焦／墨），钉档只钉浮动面，常驻条跟着所在区域翻。
# 玻璃面/后代那两条声明由整个族共用一个规则块，割它先打红块里排在最前的那行（玻璃面底色／
# 玻璃后代字色），CTRL 在解析 CSS 那一步就 die，本轮想点的名字进不了红名单——
# 实测 S23/S41 同病（MISSED，报的都是"玻璃面底色：那条规则块里没有 background-color 声明"）。
# 割 color-scheme 没有任何 SPECS 行按它解期望值，判据因此走"实测与声明不符"那条收集路径，
# 被这格撑着的三行一起点名（白天两格、夜晚一格）。后代那行的规则块里根本没有 color-scheme
# （第一版就报 CANNOT-CUT），所以它的锚点也要一起换到钉档那一条。
CUT_TARGET = {n: (CC.PIN, "color-scheme") for n in
              ("反档祖先玻璃面(祖先dark)", "反档祖先玻璃面(祖先light)", "反档祖先玻璃后代")}
for i, (name, anchor, prop, key, field) in enumerate(CC.SPECS):
    anchor, prop = CUT_TARGET.get(name, (anchor, prop))
    CUT.append({"id": f"S{i:02d}", "gate": "CTRL", "what": f"摘除 {name} 的声明",
                "expect": [name], "kind": "css_spec",
                "args": (name, anchor, prop),
                "note": f"{key}·{field}"})

# 族成员名单那 16 行（八截词根 × 面/后代）在 CSS 侧的真实依赖是"词根本身在族里"，
# 不是那条共享声明——所以它们各配一柄割词根的刀：副本一起动，副本相等守卫不红，
# 红的只能是被摘出族的那一类成员。锚点都带上邻接的逗号，
# 否则选择器列表断成 `, ,` 会让整条族规则被解析器丢掉，那是"全族都红"而不是定位。
# 逗号在哪一侧是量出来的（fixed-btn 在族末尾，前面是换行＋六空格，不是逗号）。
# 替换文本按每截单独给：fixed-btn 那一截的锚点尾巴上挂着 `:is(` 的闭合括号，
# 删空它就把括号也吞了——实测第一版就这么死在"§4c 那族在偏移 23600 处没有配平的 )"，
# 判据结构性 die（不会假绿），但那一刀什么也没测到。
# n 现在是逐截给的：族那四份逐字副本之外还有两支常驻条分支——给 <a> 上墨那一条、
# 给控件撤面那一条（2026-10-04 为用户指着页头说"强调太突兀"而加）——它们各自重复了
# topnav／navbar／页头三截词根，所以这三截的锚点在文件里有 6 处而不是 4 处。
# 割的时候一起割——那两支问的是同一句「这截词根在不在族里」，留它在后面几处等于割完还红着别的。
# 2026-10-04 契约分裂后又多出**第五处**：浮动面专属的那条钉档规则逐字抄了族的末尾四截 :not()
# 与浮层那几截词根（常驻条那五截它刻意不抄）。所以带面板词根或带末尾排除式的锚点从 4 处变 5 处，
# 而带常驻条词根的锚点仍是 4/6 处——这一差本身就是被钉范围那一格的形，由下面 K31 举住。
# 2026-10-07 #110 又多出**第六处**：面内控件的钉档规则（把面族的原文再抄一遍、末尾加 :is(input, textarea, select)），
# 所以浮层那几截词根与末尾排除式的锚点从 5 处变 6 处；常驻条那三截不受影响。
SEL_CUT = []
for _rid, (_label, _old, _new, _rows, _n) in enumerate([
        ("aria-modal", ', [aria-modal="true"]', "",
         ("玻璃面 aria-modal", "后代字色 aria-modal"), NCOPY + 2),
        ("alertdialog", ', [role="alertdialog"]', "",
         ("玻璃面 alertdialog", "后代字色 alertdialog"), NCOPY + 2),
        ("sidebar", ' [class*="sidebar" i]:not(:has([class*="sidebar" i])), ', "",
         ("玻璃面 sidebar", "后代字色 sidebar", "玻璃面 嵌套内层"), NCOPY),
        ("secondarybar", ' [class*="secondarybar" i],', "",
         ("玻璃面 secondarybar", "后代字色 secondarybar"), NCOPY),
        ("topnav^", ' [class^="topnav" i],', "",
         ("玻璃面 topnav", "后代字色 topnav"), NCOPY + 2),
        ("fixed-btn", ',\n      [class*="fixed-btn" i])', ")",
         ("玻璃面 fixedbtn", "后代字色 fixedbtn"), NCOPY + 2),
        # 2026-10-03 转正的两根各配一柄摘出刀：它们从否决转正之后，"这两截在不在族里"
        # 就成了会漂移的一格，而 FLOATROOTS 那两行的正控制只说"在族里时是玻璃"，
        # 反向那一格（词根被删掉时该红在这一行）要由这两柄钉。
        ("navbar", ' [class*="navbar" i],', "",
         ("玻璃面 navbar", "后代字色 navbar"), NCOPY + 2),
        # 页头那一截带着「挂在 main／article 之下就让路」那道排除（普查量到它扳上的
        # 24 块里 22 块不浮着，最大的两块 452658px²／395296px² 坐在正文容器里），
        # 所以锚点是整截连同排除一起割——只割词根留着排除，剩下的是半具刀。
        ("header", ' [class*="navbar" i], [class*="header" i]'
                   ':not(:is(main, article) [class*="header" i])',
         ' [class*="navbar" i]',
         ("玻璃面 header", "后代字色 header"), NCOPY + 2),
], start=1):
    SEL_CUT.append({"id": f"M{_rid:02d}", "gate": "CTRL",
                    "what": f"把 {_label} 摘出玻璃族", "kind": "text",
                    "args": ("css", _old, _new), "n": _n, "expect": list(_rows),
                    "note": "族成员名单漂移：这条词根被删掉/改名时该红在自己这两行上"})

# 淡划墨落进面里那一格（#39）要有自己的刀，不能靠 S44：S44 割的是后代块那条**共享**的
# `color: var(--ks-ink-1) !important`，块里还有 div/span/li/… 十几类读者，一刀下去红的是
# 整族而不是这一行——和 M01–M06 当年"12 行全是哑刀"是同一类失败，按同类办法补：割元素表本身。
# 元素表只在后代块出现 1 次（四份副本重复的是**族选择器**那一段，不含这里），所以 n=1。
SEL_CUT.append({"id": "M09", "gate": "CTRL", "what": "把 del, s 摘出玻璃后代元素表",
                "kind": "text", "args": ("css", "dd, del, s,", "dd,"), "n": 1,
                "expect": ["玻璃面淡划字色"],
                "note": "面上淡划字退回 §4b 那条画布级 ink-3 时该红在这一行，不该带红整族"})

# 两截按 id 命中的词根（#78 补的夹具证人）。编号写死而不是接着 SEL_CUT 那个 enumerate 排：
# 插进那张表会把 header 那一柄的编号顶到 M10，和下面手写的 M09 撞名。
# 摘出刀落 6 处：族那四份逐字副本（§4c 两份 + 打印档两份）之外，常驻条那两支分支
# （给 <a> 上墨、给控件撤面）各自也带着同一截 id 形。
# id-topnav 这一柄连排除式一起摘，所以红的除了自己那两行还有 belowTopnavId 那块整页容器
# ——一条选择器一次摘掉，两格一起红是它本来的形状。
SEL_CUT.append({"id": "M10", "gate": "CTRL", "what": "把 id 形 topnav 那一截摘出玻璃族",
                "kind": "text", "n": NCOPY + 2,
                "args": ("css", '\n      [id*="topnav" i]:not([id*="below" i]),', ""),
                "expect": ["玻璃面 id-topnav", "后代字色 id-topnav"],
                "note": "族成员名单漂移：这一截被删掉/改名时该红在自己那两行上。"
                        "反证块 belowTopnavId 在这一柄上**不**红——整截被摘走时它同时失去了"
                        "被匹配的机会，让路那一格由 K23 单独举住（写这条期望时我先按「两格"
                        "一起红」猜过，M10 落刀实测只红两行，猜错了，按读数改期望而不是按期望改刀）"}),
SEL_CUT.append({"id": "M11", "gate": "CTRL", "what": "把 id 形 pagetop 那一截摘出玻璃族",
                "kind": "text", "n": NCOPY + 2, "args": ("css", ', [id*="pagetop" i]', ""),
                "expect": ["玻璃面 id-pagetop", "后代字色 id-pagetop"],
                "note": "同上，管的是 w3schools 页头第一行那一截"})

def geom_line(win):
    """按整行取那一趟几何读数：条目在两行里各出现一次，只按条目切会命中 2 处。"""
    for l in PRISTINE["geom"].splitlines():
        if l.startswith(f"win={win} "):
            return l
    sys.exit(f"geometry.txt 里没有 win={win} 那一趟，刀无处可落")


# 整页那一趟的窗口不写死：夹具长一寸，它就不是那个数了（上一版把 2022 抄在刀柄里，
# 夹具一长 G01/G02 就落不了刀）。按"不是短窗口的那一趟"现推。
WINS = [l.split()[0].removeprefix("win=") for l in PRISTINE["geom"].splitlines() if l.strip()]
if "1280,1500" not in WINS:
    sys.exit(f"geometry.txt 里没有短窗口那一趟，实际 {WINS}")
FULL_WIN = next((w for w in WINS if w != "1280,1500"), None)
if not FULL_WIN:
    sys.exit(f"geometry.txt 只有一趟读数 {WINS}，整页那一趟的刀无处可落")
SHORT_LINE, FULL_LINE = geom_line("1280,1500"), geom_line(FULL_WIN)


def geom_entry(line, sel):
    """从那一趟读数里取某个选择器的条目原文（刀要照着现在的坐标改，不能抄旧坐标）。"""
    m = re.search(r"(?:^|;)" + re.escape(sel) + r"@[\d,]+", line)
    if not m:
        sys.exit(f"geometry.txt 那一趟里没有 {sel}，刀无处可落：{line[:80]}")
    return m.group(0).lstrip(";")


FOOTER = geom_entry(FULL_LINE, "footer")
ROW1 = geom_entry(SHORT_LINE, "table:not(.own) tbody tr:nth-child(1)")
_fx, _fy, _fw, _fh = (int(v) for v in FOOTER.split("@")[1].split(","))
_rx, _ry, _rw, _rh = (int(v) for v in ROW1.split("@")[1].split(","))

# 顺序是定的：PIX 那几柄会重出 16 张图，跑完之后盘上的图就来自被割过的那棵树；
# 只读旧图的 DIFF 柄必须排在它们前面，否则那几柄的基线量的是一棵混树。
DIFF_CUT = [
    {"id": "G01", "gate": "DIFF", "what": "geometry.txt 的窗口和图对不上",
     "expect": ["对不上"], "kind": "text",
     "args": ("geom", f"win={FULL_WIN}", "win=1280,1600"),
     "note": f"整页那一趟被改成 1600，图却还是 {FULL_WIN} 高——陈旧坐标被沿用的那一形"},
    {"id": "G02", "gate": "DIFF", "what": "页脚被挪回 y1500 以上",
     "expect": ["页脚 整块都在"], "kind": "text",
     "args": ("geom", FULL_LINE,
              FULL_LINE.replace(FOOTER, f"footer@{_fx},1440,{_fw},{_fh}")),
     "note": "页尾这一格失去取证对象时必须自己说"},
    {"id": "G03", "gate": "DIFF", "what": "斑马纹取样盒比行还宽",
     "expect": ["收不进"], "kind": "text",
     "args": ("geom", SHORT_LINE,
              SHORT_LINE.replace(ROW1, f"table:not(.own) tbody tr:nth-child(1)"
                                       f"@{_rx},{_ry},10,{_rh}")),
     "note": "取样盒装不进那一行"},
]

PIX_CUT = [
    {"id": "P01", "gate": "PIX", "what": "斑马纹洗到看不见",
     "expect": ["斑马纹看不出来（白天档）", "斑马纹看不出来（夜晚档）"],
     "kind": "text", "args": ("css",
                              "background-color: color-mix(in srgb, var(--ks-sakura) 9%, transparent);",
                              "background-color: color-mix(in srgb, var(--ks-sakura) 0.4%, transparent);"),
     "note": "9%→0.4%：声明还在、计算样式仍解得开，只是像素上分不出行"},
    {"id": "P02", "gate": "PIX", "what": "页尾三块的字涂成纸色",
     "expect": ["页尾页脚"],
     # 锚点取 </style> 本身而不是"上一条规则的收尾两行"：夹具末尾加一条一行式规则就会把
     # 那种锚点打成 0 命中（上一版就是这么哑的），而 </style> 在这份文件里恰好 1 处。
     "kind": "text", "args": ("fixture", "</style>",
                              "  footer, .cards, dialog { color: var(--ks-canvas-1); }\n"
                              "  footer a { -webkit-text-fill-color: var(--ks-canvas-1); }\n</style>"),
     "note": "皮肤不碰正文色，所以这一刀落在夹具上：footer a 那条走 -webkit-text-fill-color，"
             "因为 a 的 color 被用户源 !important 占着，作者源普通声明抢不动"},
    {"id": "P03", "gate": "PIX", "what": "关掉浮层的虚焦（留 α）",
     "expect": ["虚焦没把底噪抹开"],
     "kind": "text", "args": ("css",
                              "    backdrop-filter: var(--ks-glass-blur) !important;\n", ""),
     "note": "半透还在、底噪直接以锐边透上来：实测白天档菜单那格纸半带 0.021→0.096，"
             "越过上限。计算样式那本同时也看得见（它盯 blur(16px)），这一格是像素侧的兜底"},
    {"id": "P04", "gate": "PIX", "what": "族把底下的正文也当浮层（站点类名撞 string 匹配）",
     "expect": ["动到了浮层以外的底"], "kind": "text",
     "args": ("fixture", '<div class="site-doc">', '<div class="site-doc modal">'),
     "note": "[class*=\"modal\" i] 这类子串匹配的现实失效方式就是站点自己的类名撞上它。"
             "玻璃改到浮层以外那块底，只有像素这本看得见：check-controls 的探针是它自己拼的 HTML"},
    {"id": "P05", "gate": "PIX", "what": "关档那两张其实没关（--kGlass:0 被摘掉）",
     "expect": ["画出来的不止 CSS 里那一成"], "kind": "text",
     "args": ("shoot", "GLASS_OFF_DAY=':root{--kGlass:0;--kScheme:light;}'",
                           "GLASS_OFF_DAY=':root{--kScheme:light;}'"),
     "note": "配对构建的卫生：两张图若只差一个变量名而变量没落地，第十项就等于拿开档比开档。"
             "位置守卫看不出这一形（两处坐标一模一样），是纸面中位与预测的那 28 级差把它揭出来的"},
    {"id": "P06", "gate": "PIX", "what": "够不着那一格的哈希类名里出现了 modal 词根",
     "expect": ["够不着哈希类名面板（白天档）被开关动到了",
                "够不着哈希类名面板（夜晚档）被开关动到了"],
     "kind": "text",
     "args": ("fixture", 'gh-c Primer_Brand__ActionMenu-module__ActionMenu___xLxGU"',
                        'gh-c Primer_Brand__ActionMenu-module__ActionMenu___xLxGU modal"'),
     "note": "这一格量的是「玻璃管不到哪儿」，而「管不到」最容易是白捡的：那块若是空底、"
             "或者压根不在开关覆盖面上，两趟相同都不用验。往它的类名里塞一个词根，族立刻追得上它，"
             "两趟就有了差 → 这一条必须红。它同时证明这一格的判定来自开关自己：同一块底上其余六格"
             "（四格真浮层加另两块族不该管的形状）的两趟差仍然是 0——量过，落刀后 DIFF 报出的红"
             "只有这两本，白天档 6 级差、夜晚档 28 级差"},
    {"id": "P07", "gate": "PIX", "what": "四份副本一起丢掉 :not(button) 那一支",
     "expect": ["够不着侧栏折叠钮（白天档）被开关动到了",
                "够不着侧栏折叠钮（夜晚档）被开关动到了"],
     "kind": "text", "n": NCOPY + 2,
     "args": ("css", "):not(button, svg)", "):not(svg)"),
     "note": "K07 的像素侧同刀：计算样式那本读的是 check-controls 自己拼的探针 HTML，"
             "这一格读的是夹具里那块真按 Primer 排的按钮（站点只给 color/font/padding，"
             "底是空的）。它红了才说明排除式少一项时**页面上真的会多出一块毛面**，"
             "而不只是计算值对不上。button 这一支现在红在两本上：.gh-f（dropdown 词根追上的"
             "侧栏折叠钮）与 .ch-g（fixed-btn 词根追上的真按钮）——夹具里有两块 button 形状各挂"
             "一种词根，这是应当的差，不是溢出；svg 那一支（P08）仍只红在箭头那一本"},
    {"id": "P08", "gate": "PIX", "what": "四份副本一起丢掉 :not(svg) 那一支",
     "expect": ["够不着按钮里的箭头图标（白天档）被开关动到了",
                "够不着按钮里的箭头图标（夜晚档）被开关动到了"],
     "kind": "text", "n": NCOPY + 2,
     "args": ("css", "):not(button, svg)", "):not(button)"),
     "note": "箭头那一支的像素侧：svg 吃底色在计算样式上是同一个读数，但用户看得见的是"
             "三角形后面多了一块粉——P07/P08 各点自己那一格，两格的差互不背书"},
    # P09（"四份副本一起把「不追」的 navbar 词根加进族"，gate=PIX）2026-10-03 退役。
    # 它那笔否决被用户改判成「接管常驻条」：navbar/header 两截现在就在族里，这把"加进去"
    # 的刀落的是一把 no-op（等价变异），而 MISSED 会被读成"断言太松"。它的账改由两处担：
    # 正面是 diff-shots.py 的 GLASS 里新增的 .ch-e/.ch-f 两格（导航条×常驻条接管／
    # 吸顶容器×常驻条接管——开关两趟必须挪动，且透底以后墨对纸仍要 ≥4.5），
    # 反面是上面 M 系列新加的 navbar／header 两柄摘出刀（红在 玻璃面/后代字色 那四行）。
]

# §4c 的判据里有三样东西是"从 CSS 现推"的：虚焦半径配方、缺口比例、族选择器的多份副本。
# 它们各自的失效方式都是"漂了但没人说"，所以每样配一把专割那一格的刀。
# 副本漂移那两柄刀（K03/K06）必须落在"族列表末位之后"那一格，而列表本身会长——
# sidebar／secondarybar／topnav／fixed-btn 这四截就是后来接上去的。锚点从前把末位两截
# 抄死在刀柄里，四截一接，抄死的那串命中 0 处，这两柄连着若干轮全量都是 LANDING-FAIL
# （今天全量重跑才看见：`锚点命中 0 处，应当恰好 1 处（刀还没落，不测了）`）。
# 所以这里从当前文本现推落点，不再抄词根名。落点仍选后代那一格：它是四份副本里唯一在
# `):not(...)` 之后接 `:is(` 的一格，而面那一格的行尾正是 check-controls.py 的块锚点，
# 往那儿追加会先把锚点打断，红就归因不到副本守卫头上。
# 连接点按形状现推，不抄 `:not(button, svg)` 那一串字面：族末尾后来又接了一道
# 结构排除 `:not(:has(> button))`，抄死的串当场命中 0 处，K03/K06 又回到 LANDING-FAIL。
# 取的是"行末那个右括号一路到下一行的 :is("，:is( 后面不接 dialog（那才是后代元素表）。
_JOIN = None
for _m in re.finditer(r"\)[^\n]*\n {4}:is\((?!dialog)", PRISTINE["css"]):
    if _JOIN is not None:
        sys.exit("KNIFE ABORT: 后代的 `):not(...)`→`:is(` 连接点命中不止一处，"
                 "落点会切错地方（K03/K06 各份副本的相对位置要重新想）")
    _JOIN = _m.group(0)
if _JOIN is None:
    sys.exit("KNIFE ABORT: 找不到后代的 `):not(...)`→`:is(` 连接点——"
             "族末尾和后代元素表之间不再是这一形，落点要跟着 CSS 的形状改")
_tailstr = PRISTINE["css"][:PRISTINE["css"].index(_JOIN)].splitlines()[-1]
_br = re.findall(r"\[[^\[\]]+\]", _tailstr)
if not _br:
    sys.exit("KNIFE ABORT: 连接点那一行的行尾没有方括号选择器，认不出族列表末位")
TAIL_LAST = _br[-1]
TAIL = TAIL_LAST + _JOIN
if " i]" not in TAIL:
    sys.exit(f"KNIFE ABORT: 族列表末位 {TAIL_LAST!r} 没有 i 标志，"
             "K03 的「只有后代那份丢了 i」落不了刀（要么换落点，要么改这一柄问的问题）")
TAIL_NOI = TAIL.replace(" i]", "]", 1)
TAIL_DRIFT = TAIL.replace(TAIL_LAST, TAIL_LAST + ", [data-ks-drift]", 1)

GLASS_CUT = [
    {"id": "K01", "gate": "CTRL", "what": "摘掉玻璃面的 backdrop-filter",
     "expect": ["玻璃面没拿到"], "kind": "text",
     "args": ("css", "    backdrop-filter: var(--ks-glass-blur) !important;\n", ""),
     "note": "半径那条断言（blur(16px) 自 §1 token 现推）必须炸在这里"},
    {"id": "K02", "gate": "CTRL", "what": "后代那条去掉 !important",
     "expect": ["玻璃后代字色"], "kind": "text",
     "args": ("css", "h5, h6) {\n    color: var(--ks-ink-1) !important;",
              "h5, h6) {\n    color: var(--ks-ink-1);"),
     "note": "用户源普通声明排在作者源普通声明之下（Cascade 4），探针里那条 #dlg .it{color:#fff}"
             "就该赢回来——这一刀验的正是'字归我们'靠的是 !important 而不是选择器写得好"},
    {"id": "K03", "gate": "CTRL", "what": "族的一份副本漂了（只有后代那份丢了 i）",
     "expect": ["副本漂成"], "kind": "text",
     "args": ("css", TAIL, TAIL_NOI),
     "note": "四份副本（面、后代、打印那两格）只认逐字相等；漂一份不会报错、只会让"
             "同一族在两个地方是两套东西，所以必须让它在这儿炸而不是悄悄少盖一类。"
             "落点由 TAIL 现推（族列表末位＋后代连接点），不抄词根名——抄死过一次，"
             "四截新词根接上列表后锚点命中 0 处，这柄连着若干轮全量都是 LANDING-FAIL"},
    {"id": "K04", "gate": "CTRL", "what": "打印档里又写了一份虚焦配方",
     "expect": ["虚焦半径应恰好有 1 处"], "kind": "text",
     "args": ("css", "--ks-glass-blur: none; }\n    :is(dialog",
              "--ks-glass-blur: blur(calc(var(--kGlass, 1) * 16px)); }\n    :is(dialog"),
     "note": "同一个量有两个定义时，期望值就不知道该照着谁算——load_glass 按恰好 1 处钉"},
    {"id": "K05", "gate": "CTRL", "what": "缺口从 14% 拧到 0%",
     "expect": ["玻璃面透明度缺口"], "kind": "text",
     "args": ("css", "calc(100% - var(--kGlass, 1) * 14%)",
              "calc(100% - var(--kGlass, 1) * 0%)"),
     "note": "α=1 时「透没透」在计算样式上是同一个读数：这一行会退化成普通的底色对账而仍显绿，"
             "所以辨识力下限必须自己开火（像素那本的同形刀是 P05，两边各自有尺）"},
    {"id": "K06", "gate": "CTRL", "what": "族的一份副本在列表末尾追加了一个选择器",
     "expect": ["副本漂成"], "kind": "text",
     "args": ("css", TAIL, TAIL_DRIFT),
     "note": "这一刀是 load_family 换算法的理由：列表末位之后追加（给一类新浮层开口子"
             "最常见的写法）在旧判据那种『按末位那个词收尾截段』的取法里截出来是同样的字节，"
             "四份副本看着逐字相等却少盖一类。配对量过（旧落点那棵树、同一把刀）："
             "旧判据 4 份 1 种写法（绿，静默放过），新的配平扫描 4 份 2 种写法（红）。"
             "落点选后代那一格而不是面那一格：面那格的行尾（现在是 `):not(button, svg) {`）"
             "正是 SPECS 的块锚点，追加在那里会先把锚点打断，红就归因不到副本守卫头上。"
             "落点同样由 TAIL 现推，不抄词根名（理由见 K03）"},
    {"id": "K07", "gate": "CTRL", "what": "四份副本一起丢掉 :not(button) 那一支",
     "expect": [f"白天 {CC.OVERFLOW}：btn{CC.WHY['yield']}",
                f"夜晚 {CC.OVERFLOW}：btn{CC.WHY['yield']}"], "kind": "text", "n": NCOPY + 2,
     "args": ("css", "):not(button, svg)", "):not(svg)"),
     "note": "「n: 4」是这具刀的关键：逐处只改第一处（旧 apply_cut 的写法）会让其余三份仍带排除式，"
             "四份副本先漂成两套，红落在「副本漂成」上而不是这一格——那是把两件事混成一件。"
             "摘掉 button 这一支，探针里那个类名带 dropdown 词根的按钮就被族涂上了玻璃底，"
             "而真站 GitHub 首页量到的正是 5 块这样的 NavDropdown 按钮（Primer 给它写的是 "
             "background:0 0 加 border:0——底色那一格站点明确留空，逐字取自 /tmp/ghcss 里那条规则；"
             "裸页两趟读到的是 UA 的 ButtonFace 灰，不是站点排的色）。"
             "实测红：白天档按钮底 #ffeaf3、夜晚档 #3a1b2c（夹具里替站点排的那块底是 #2f81f7，"
             "取自 GitHub 的品牌蓝），虚焦一起挂上了 blur(16px) saturate(1.3)"},
    {"id": "K08", "gate": "CTRL", "what": "四份副本一起丢掉 :not(svg) 那一支",
     "expect": [f"白天 {CC.OVERFLOW}：icon{CC.WHY['yield']}",
                f"夜晚 {CC.OVERFLOW}：icon{CC.WHY['yield']}"], "kind": "text", "n": NCOPY + 2,
     "args": ("css", "):not(button, svg)", "):not(button)"),
     "note": "和 K07 是同一族的另一半：svg 那一支管的是按钮里那颗箭头（首页量到 5 个 "
             "…buttonIcon… 的 svg）。两条各点自己那一本（这一柄的红线里只有 icon；K07 的红线里"
             "除 btn 还捎上 fixedBtn——夹具那个元素本身就是 <button>，摘掉 button 这一支它跟着漏；"
             "两柄各自的名字都进得了红线，量过），所以 :not() 里的两项都有尺子盯着，"
             "少任何一项都会红，而不是「少一项看不出来」"},
    {"id": "K17", "gate": "CTRL", "what": "四份副本一起丢掉那道结构排除 :not(:has(> button))",
     "expect": ["浮层族少了那道结构排除"], "kind": "text", "n": NCOPY + 2,
     "args": ("css", ":not(h1, h2, h3, h4, h5, h6):not(:has(> button))",
              ":not(h1, h2, h3, h4, h5, h6)"),
     "note": "这一格是页头那 5 块导航壳之修法唯一的尺子：整族外面那道「直接子元素里有按钮就不上玻璃」"
             "的排除，四份一起删掉时副本照样逐字相同，「漂成 N 种写法」那条守卫对它天然看不见，"
             "所以「在不在」要单独钉一次。锚点换过形（2026-10-06 现量）：#96 把 "
             ":not(h1, h2, h3, h4, h5, h6) 插进了 :not(button, svg) 与 :not(:has(> button)) 之间，"
             "旧锚点 `):not(button, svg):not(:has(> button))` 当场 0 命中，全量电池报的是 "
             "LANDING-FAIL（/tmp/final-battery.log 第 242 行）而不是「浅字压粉底」那一本红——"
             "刀没落，判据就没说话。新锚点取「标题形那一截＋被割那一截」，命中 5 处，"
             "与 n 同源；族上方注释里那串裸字样不再取进锚点（它会把注释那一处也算进去）。"
             "真站那一侧的证人：root-census 的「玻璃在文档流上」29 行 → 23 行，掉下那 6 行逐行点名"
             "＝GitHub 页头 5 块 NavDropdown 导航壳（relative，104/109/116/118/137×40）"
             "＋ github-docs 一块 53×44 的侧栏开关位；浮着的 9 块一块没少"},
    {"id": "K19", "gate": "CTRL", "what": "四份副本一起丢掉那道孙辈结构排除 :not(:has(> * > button))",
     "expect": ["浮层族少了那道孙辈结构排除"], "kind": "text", "n": NCOPY + 2,
     "args": ("css", ":not(:has(> button)):not(:has(> * > button))", ":not(:has(> button))"),
     "note": "K17 那一道的第二形：GitHub 页头那块 ActionMenu 的 container 只有一个直接子节点（div），"
             "button 挂在 div 里，所以带 > button 的那道按构造够不着它——这一格唯一的尺子就是这一截。"
             "锚点换过形（2026-10-06 现量）：#96 把 :not(h1, h2, h3, h4, h5, h6) 插进了 "
             ":not(button, svg) 与 :not(:has(> button)) 之间，旧锚点 "
             "`):not(button, svg):not(:has(> button)):not(:has(> * > button))` 当场 0 命中，"
             "全量电池报 LANDING-FAIL（/tmp/final-battery.log 第 243 行）而不是「浮层族少了那道孙辈"
             "结构排除」那一本红。新锚点取「被留着那一截＋被割那一截」相邻的两串：命中 5 处、"
             "与 n 同源；而裸的 :not(:has(> * > button)) 是 6 处——族上方第 717 行那条注释也写了它的"
             "字样，取锚点时不能把注释那一处算进副本数（先量过再落笔）。"
             "真站那一侧的证人：root-census 的【族内实形】同日配对重拍（只换这一处）"
             "＝dropdown 那一行整体归零、secondarybar 面2/静止1 → 面1/静止0，"
             "浮着的面 9→9 一块没少、其余各行一字不差"},
    {"id": "K09", "gate": "CTRL", "what": "系统「少用透明」那一档路由到半透而不是实心",
     "expect": ["reduced-transparency 路由到 --kGlass"], "kind": "text",
     "args": ("css", "--kGlass: 0 !important", "--kGlass: 0.35 !important"),
     "note": "§7 那一格管的是可达性偏好，而它没有自己的浏览器通道（无头 Chrome 不认 "
             "--force-prefers-reduced-transparency：两趟 matchMedia 都是 false）。所以它只能靠"
             "「接到已量过的值」这条链成立——把 0 改成 0.35，链子断在数字上，红必须落在这一本"},
    {"id": "K10", "gate": "CTRL", "what": "那一格整个不再动 --kGlass（退回旧写法）",
     "expect": ["只撤了虚焦、没动 --kGlass"], "kind": "text",
     "args": ("css", ":root { --ks-glass-blur: none; --kGlass: 0 !important; }",
              ":root { --ks-glass-blur: none; }"),
     "note": "这一刀割的是「改回上一版」：上一版只写 blur，面板在减透明偏好下仍透 14% 的粉。"
             "旧写法在当时没有任何尺子会说红——这一格就是那条历史"},
    {"id": "K11", "gate": "CTRL", "what": "像素闸门的关档值从 0 挪到 0.5（拆证人）",
     "expect": ["shoot.sh 的关档串不是 --kGlass:0"], "kind": "text", "n": 2,
     "args": ("shoot", "':root{--kGlass:0", "':root{--kGlass:0.5"),
     "note": "跨文件那一半的刀：割的是证人那一边，不是主张那一边。落点取带引号的那一截，"
             "因为 --kGlass:0 在 shoot.sh 里出现 3 次——两条 GLASS_OFF_* 赋值加一行注释，"
             "n=2 只切赋值那两条（守卫也只认 GLASS_OFF_*，注释漂了不会假红）。"
             "没有这具，那条跨文件对账可以只靠 CSS 一侧自证"},
    {"id": "K12", "gate": "CTRL", "what": "那一格撤掉虚焦那一半",
     "expect": ["没把 --ks-glass-blur 置 none"], "kind": "text",
     "args": ("css", ":root { --ks-glass-blur: none; --kGlass: 0 !important; }",
              ":root { --kGlass: 0 !important; }"),
     "note": "--kGlass:0 让 blur 算成 blur(0px)，但 blur(0px) 仍是一层 backdrop-filter："
             "所以「实心」和「虚焦撤掉」是两格，各要一把刀（K10 割透明度那一半、K12 割 blur 那一半）"},
    # 新加的四根浮动条词根各自一把：割法不是删整行（四份副本的换行/缩进抄不准），
    # 而是把词根本身改一个字母——族还在、语法还合法，只是追不上任何元素。
    # 落点选 sidebar 和 fixed-btn 两根：一根是最典型的"整条侧栏"，一根是和 :not(button)
    # 共用同一截类名的新根。topnav/secondarybar 两根由自动生成的 S 系列（按 SPECS 逐条摘声明）
    # 与这两把同形，不再各加一把同义刀。
    {"id": "K24", "gate": "CTRL", "what": "摘掉页头那一截的 main/article 让路",
     "expect": [f"白天 {CC.OVERFLOW}：inMainHeader",
                f"夜晚 {CC.OVERFLOW}：inMainHeader"],
     "kind": "text", "n": NCOPY + 2,
     "args": ("css", ':not(:is(main, article) [class*="header" i])', ''),
     "note": "问的是让路在不在，不是词根在不在（词根那一条由 M08 举）。夹具里那块"
             "div.page-header-content 坐在 main 里，摘掉排除它就穿上玻璃——红在这一格。"
             "落 6 处是刻意的：族那四份逐字副本之外，常驻条那两支分支（给 <a> 上墨、给控件撤面）"
             "也带着同一道排除。"},
    {"id": "K23", "gate": "CTRL", "what": "摘掉 id 形那截的 below 排除",
     "expect": [f"白天 {CC.OVERFLOW}：belowTopnavId",
                f"夜晚 {CC.OVERFLOW}：belowTopnavId"],
     "kind": "text", "n": NCOPY + 2,
     "args": ("css", ':not([id*="below" i])', ''),
     "note": "和 K22 同一问法、不同的截：这条管 id 形那一截上那道让路在不在。夹具里那块反证"
             "块（id 拼法照 w3schools 服务端 HTML 的 belowtopnavcontainer）必须原样留着站家的"
             "底。落 6 处是刻意的——族那四份逐字副本之外，常驻条那两支分支也带着这一截，"
             "摘掉排除时各处一起放宽，红只由反证块举。"},
    {"id": "K22", "gate": "CTRL", "what": "摘掉 sidebar 那一截的嵌套排除",
     "expect": [f"白天 {CC.OVERFLOW}：outerRail", f"夜晚 {CC.OVERFLOW}：outerRail"],
     "kind": "text", "n": NCOPY,
     "args": ("css", ':not(:has([class*="sidebar" i]))', ''),
     "note": "问的不是词根在不在，是收窄在不在。2026-10-04 七站复量：整根匹配 43 块面、其中 38 块"
             "坐在文档流，最大那一块是 MDN 的整页版式壳 div.layout__2-sidebars-inline 1280×3157"
             "（4,040,960 px²），它里面还套着两块 sidebar 类名的栏——玻璃套玻璃，把那两块各自的 "
             "86% 粉底再乘一遍（就是「浮层里再套一层浮层会比一层更透」那笔代价的实物）。收成「最里层"
             "才穿玻璃」后用同一把尺复跑：面 43→22、静止 38→19、最大误伤 4,040,960→600,690 px²；"
             "浮着的 5→3，少的那两块（MDN 那一横、docs.github 那一竖）改穿在各自的内容块上，面还在，"
             "只是穿到了更里层。夹具那对父子照 runoob 父链列量到的那一形抄（"
             "div.sidebar-box gallery-list 套 div.sidebar-box re-box），摘掉排除后外层被扳成玻璃、"
             "两档各红一次；反方向由「玻璃面 嵌套内层」"
             "那一行守着（收得太狠时它红）。"},
    {"id": "K13", "gate": "CTRL", "what": "四份副本一起把 sidebar 词根改错一个字母",
     "expect": ["玻璃面 sidebar", "后代字色 sidebar", "玻璃面 嵌套内层"], "kind": "text", "n": NCOPY,
     "args": ("css", '[class*="sidebar" i]:not(:has([class*="sidebar" i]))',
              '[class*="sidebr" i]:not(:has([class*="sidebr" i]))'),
     "note": "站点白侧栏（w3-sidebar）必须退回站点那块 #fff 实心底、白字面板里的墨也得换回来。"
             "四份副本逐字相等所以副本守卫不红——红必须落在计算样式那本点名的两根断言上。"
             "夹具里那块面板的白底是站点自己写的，没有这条作者声明，摘掉词根在计算样式上是"
             "等价变异（透明玻璃画在透明地上）"},
    {"id": "K14", "gate": "CTRL", "what": "四份副本一起把 fixed-btn 词根改错一个字母",
     "expect": ["玻璃面 fixedbtn", "后代字色 fixedbtn"], "kind": "text", "n": NCOPY + 2,
     "args": ("css", '[class*="fixed-btn" i]', '[class*="fixedbtn" i]'),
     "note": "runoob 那种悬浮小钮：和 K13 是同一个形状的第二根，割它是因为它和 :not(button) "
             "挤在同一截类名里——新加的根最容易漂的就是这一带。"
             "这一柄曾经 MISSED 过：探针钩子当时叫 ksChromeFixedBtn，去掉连字符的错拼 "
             "fixedbtn 按子串匹配先把钩子自己命中了，面板照样是玻璃、闸门全绿。钩子名改成不含"
             "词根字面后，同一把刀的红落在 玻璃面/后代字色 那两本上（量过：只改钩子名这一步"
             "就把 rc=0 翻成 rc=1，实测站点底 rgb(239,241,243) 顶掉了期望的玻璃色）"},
    {"id": "K15", "gate": "CTRL", "what": "把 topnav 的一截词边界形式改成 bar（钩子名自撞守卫）",
     "expect": ["探针钩子名被族里的词根吃到了"], "kind": "text", "n": NCOPY + 2,
     "args": ("css", '[class~="topnav" i]', '[class~="bar" i]'),
     "note": "K14 那笔账的守卫要有自己的刀，否则「钩子名不含词根」只是一句散文。"
             "bar 是真实会写的错（想多抓几块带 Bar 的容器），而它同时满足三块面板的站点类名和"
             "ksChromeDocAside 那类钩子名——面板仍全是玻璃，K13/K14 那种「退回站点底」的红"
             "一个都不会出现，所以这一柄只能由守卫报，报的是名字而不是着色值。"
             "topnav 收成词边界六形式之后锚点跟着换了写法，守卫的取根正则也从只认 [class*= "
             "扩到 [class~=／^=／*=] 并把两侧的词边界符号剥掉——不扩的话它抽不出 topnav，"
             "这一柄会静默 MISSED（量过：只扩形式不改正则时 roots 名册里没有 topnav）"},
    {"id": "K16", "gate": "CTRL", "what": "把 topnav 的六截词边界形式退回子串匹配",
     "expect": [f"白天 {CC.OVERFLOW}：belowTopnav",
                f"夜晚 {CC.OVERFLOW}：belowTopnav"],
     "kind": "text", "n": NCOPY,
     "args": ("css", '      [class~="topnav" i], [class^="topnav" i], [class*="topnav-" i],\n'
                     '      [class*="topnav_" i], [class*="-topnav" i], [class*="_topnav" i],',
              '      [class*="topnav" i],'),
     "note": "这一柄问的是收窄本身：子串形式会把 w3schools 那个 position: static、实测 "
             "5,895,110 px² 的整页容器 belowtopnavcontainer 当浮动条扳成玻璃，它里面站点自己"
             "涂白的卡片仍是白底，后代那条把夜色墨压上去——真站同一坐标逐行配对的 17 行从 "
             "OFF 中位 16.85:1 掉到 ON 1.16:1。夹具那块面板的类名逐字取自真站、站点底写 "
             "#ebf1f8，退回子串后两档都被扳（实测白天 #ffeaf3、夜晚 #3a1b2c），所以红点名 "
             "belowTopnav 两次。判据不是副本守卫（四份一起改，守卫不红），也不是像素闸门——"
             "这一格的失效方向是选择器形态，计算样式才看得见。射程要说清：它只认「在类名任何"
             "位置都算命中」这种写法，若有人只补回 [class*=\"-topnav\"] 那一截，这一格不红 "
             "（belowtopnavcontainer 里没有 -topnav），那是另一条决定，不在本柄账上"},
]

# 哨兵档的 token 名单：legibility.py 的 ownership 拿"同一坐标动没动"做二值归因，
# 而它答的题有两问——这块底是谁涂的、这行字是谁涂的。第二问全靠名单里有墨 token，
# 而"有没有"这一格今天既没人抄表也没人钉，所以单独一柄，割的是 proxy.py 的取色那一支。
# K20：§1 遮罩那条规则现在接 backdrop 两形 + mask 两形。
# 这一格除了"摘出选择器"没有别的刀可配——摘声明会让两形一起红（S 那一条已经管着底色），
# 定位不到"只有 class 形没接上"这一格。
# 2026-10-04 两次改动把这一柄带着一起重排：assertion 的措辞从"class 形遮罩"改成
# "backdrop 那形遮罩／遮罩各形不同档"（因为形数从 2 变成 4，"两形"那句已经不成立），
# 而出厂那块的选择器列表末尾从 `…modal" i] {` 变成了逗号——旧锚点按 `{` 收尾，现在命中 0 次。
# 期望串与锚点都是从判定文本现抄的，改措辞不改语义时必须同步这里，否则这柄刀静默变成 MISSED。
GLASS_CUT.append(
    {"id": "K20", "gate": "CTRL", "what": "把 backdrop 那两截 class 形摘出那条遮罩规则，只留 ::backdrop 与 mask 形",
     "expect": ["白天 backdrop 那形遮罩完全不遮挡", "夜晚 backdrop 那形遮罩完全不遮挡",
                "白天 遮罩各形不同档", "夜晚 遮罩各形不同档"],
     "kind": "text",
     "args": ("css",
              '  dialog::backdrop,\n'
              '  [class*="backdrop" i][class*="dialog" i],\n'
              '  [class*="backdrop" i][class*="modal" i],\n',
              '  dialog::backdrop,\n'),
     "note": "证人：真站 2026-10-03 量到 GitHub 的搜索面板穿上了玻璃，它背后铺满大半页的遮罩 "
             "（div.prc-Dialog-Backdrop-5Nt2U，fixed 1440x813，bg rgba(200,209,218,.4)，bf=none）"
             "仍是站家灰蓝——::backdrop 结构上够不着那一形。摘掉这两截后 ::backdrop 那格仍全绿"
             "（α=0.55、blur 都在），红只能来自 class 形那几行判定。锚点带两空格缩进：减透明 "
             "那一档的同形列表缩进是四空格，裸串会命中 2 处、这一刀要先落在出厂那一块上。"
             "减透明那一档的选择器列表不在射程里：无头 Chrome 不认那条媒体查询，与 K09 同一笔账"},
)

# K25：遮罩的 mask 词根两形（Vue .vui_dialog--mask、京东 .jd_pc_dou_popup_mask，#77 的 B 档）。
# 与 K20 同一格道理：只有摘选择器这一把刀能定位"mask 那两形没接上"，摘声明会连 backdrop 形一起红。
# 反面那三枚（裸 mask／裸 overlay／.Overlay）由 check-controls 的裸词根那一格看着：
# 它们出厂就是 α=0，所以这柄刀不会把它们误判进去——刀只让"该遮的没遮"开火。
GLASS_CUT.append(
    {"id": "K26", "gate": "CTRL", "what": "往遮罩那条里加回裸 mask 词根（这一形在真站多半是面板本体）",
     "expect": ["白天 裸词根那形被当遮罩压暗了", "夜晚 裸词根那形被当遮罩压暗了"],
     "kind": "text",
     # 反面那三枚断言（check-controls.py 的 csn_*）此前没有刀：K20/K25 割的是"收进来的形会掉"，
     # 没人割过"多收一枚会红"。这一柄补的就是那一向。
     # 锚点必须带**前置换行**：不带的话 `  [class*=…]` 这串在盘上命中 2 次——减透那一本写的是
     # 四空格缩进，而四空格里头含着一个两空格前缀的子串。带换行后命中 1 次（\n 后紧跟两空格再跟 `[`
     # 才成立），这一刀才真的只落在出厂那一本上。
     "args": ("css",
              '\n  [class*="mask" i][class*="dialog" i],\n',
              '\n  [class*="mask" i],\n'
              '  [class*="mask" i][class*="dialog" i],\n')})
# K26 单独一次 append：这一族里 K25 的写法就是 GLASS_CUT.append({...}) 一柄一包，
# 把两柄塞进同一个 append 会在 import 阶段就炸（list.append() takes exactly one argument）。

GLASS_CUT.append(
    {"id": "K25", "gate": "CTRL", "what": "把 mask 那两截词根对摘出遮罩规则，只留 ::backdrop 与 backdrop 形",
     "expect": ["白天 mask×dialog 那形遮罩完全不遮挡", "夜晚 mask×dialog 那形遮罩完全不遮挡",
                "白天 遮罩各形不同档", "夜晚 遮罩各形不同档"],
     "kind": "text",
     "args": ("css",
              '  [class*="backdrop" i][class*="modal" i],\n'
              '  [class*="mask" i][class*="dialog" i],\n'
              '  [class*="mask" i][class*="popup" i] {\n',
              '  [class*="backdrop" i][class*="modal" i] {\n'),
     "note": "证人：夹具里那两枚类名是真站原文（.vui_dialog--mask、.jd_pc_dou_popup_mask），"
             "摘掉这两截后 ::backdrop 与 backdrop 形仍同档（α、blur 都在），"
             "红只能来自 mask 那两形的判定。×modal 那两形不配刀也不写：玻璃族带 "
             "[class*=\"modal\"] 且声明是 !important，遮罩这条不是，测它只能测出规则次序"},
)

# K21：链接形按钮那条面规则。它要解决的正是"站点把自己的底写成带 !important 的类名规则"
# 那一格，所以刀割在 !important 上而不是整块删掉——整块删掉的话站点的白底仍在、我们的面
# 也没了，红答的是"没上色"而不是"上不过站点那条 !important"，这一格就答不出规则在管什么。
CUT.append(
    {"id": "K21", "gate": "CTRL", "what": "摘掉链接形按钮那条底色的 !important",
     "expect": ["白天 站点写 !important 的链接按钮没拿到统一的面",
                "夜晚 站点写 !important 的链接按钮没拿到统一的面"],
     "kind": "text",
     "args": ("css",
              '  a[href][role="button"], a[href].btn, a[href][class*="btn" i],'
              ' a[href][class*="button" i] {\n'
              '    background-color: var(--ks-btn) !important;',
              '  a[href][role="button"], a[href].btn, a[href][class*="btn" i],'
              ' a[href][class*="button" i] {\n'
              '    background-color: var(--ks-btn);'),
     "note": "夹具里的 skin.css 是 <link> 进来的作者源，和这条作者规则同层，所以这一格量"
             "到的是两种通道里较弱的那一种（同层时作者的 !important 一定压过普通声明）；"
             "产品那一格若落在用户源只会更强，而挂载通道在哪一层没量到（#53 记的就是文档"
             "推断：profile 被 TCC 挡住，扩展内部不可自证）。摘掉之后那颗钮拿到站点的"
             "rgb(255,255,255)，元素形那"
             "颗真按钮仍是我们的面——红只可能来自这一条对比，两档各一次。射程要说清：它量"
             "不到特异度那一半（站点若用三截类名写底，带 !important 也压不过，那一格已知"
             "留白），因为夹具那条作者规则就摆在 0,1,1。选择器那两截列表合起来在文件里只有"
             "一处（§7 减透明那一档不收链接形按钮），锚点因此不需要别的区分"},
)

# 常驻条那两支（2026-10-04「这个按钮的元素强调还是太突兀了」落的那两格）各配刀：
# 两支的字由自动生成的 S 系列管（SPECS 末尾新追加的两行，摘声明即红在行名上），
# 下面这三柄补的是 S 系列够不着的那三格——一柄管面那一半的声明，两柄管各自的排除式。
CUT += [
    {"id": "K27", "gate": "CTRL", "what": "摘掉常驻条控件那一支的 background-color 声明",
     "expect": ["常驻条上的控件没让回透明面"],
     "kind": "text",
     # 锚点取那一支独有的两行声明**成对**的那一截：`color: var(--ks-ink-1) !important;` 单行
     # 在全文件出现多次（族的面/后代、a[href] 那一支都在这里），按单行切先被拦成 LANDING-FAIL；
     # 而成对串量过是 1 处。这一刀留字删面，正是"强调过头"那一格被修掉的反面。
     "args": ("css",
              '    color: var(--ks-ink-1) !important;\n'
              '    background-color: transparent !important;',
              '    color: var(--ks-ink-1) !important;'),
     "note": "证人是一对，不是一枚：条下那枚（.ksChromeBarButton，类名逐字取自真站量到的 "
             ".NavDropdown-module__button__PEHWX）读 rgba(0,0,0,0)，条外那枚同类名同底的 "
             ".ksBarOutside 读作者的 #2f81f7——作者底没加载时两块一起红，所以条下那个 0 "
             "不会被读成「站点本来就没涂」。摘掉声明后 §4b 的元素形粉底重新压回自家粉条上，"
             "红的那本点名的就是这一格"},
    {"id": "K28", "gate": "CTRL", "what": "摘掉 <a> 那一支末尾的 :not(body, html)",
     "expect": ["条外那枚正文链接被条那一支上墨了"],
     "kind": "text",
     # 锚点带上 ` a[href] {`：`:not(body, html)` 这个串在盘上有 9 处（族四份副本、两支分支、
     # 还有三处在注释里），只有连着选择器尾巴落下来才是这一支。带两空格前缀是量过的：
     # 去掉它命中 3 处（族里 `):not(body, html):not(button, svg)` 那四处含着一个无前缀子串）。
     "args": ("css", '  ):not(body, html) a[href] {', '  ) a[href] {'),
     "note": "这一支把词根抄了第二遍，族开头那道排除管不到它。夹具的 <body> 挂着真站原文的 "
             "header-dark，摘掉它「常驻条之下」就成了「整页之下」：证人 a.ksBodyLink（条外的"
             "正文链接，站点自涂 #1a7f37 带 !important）当场被换成自家墨。这一格是 2026-10-04 "
             "新加证人时现量到的——当时没有这道排除，夹具里 btn／fixedBtn／btn_face 三本一起"
             "读成 rgba(0,0,0,0) 而它们都不在任何条下"},
    {"id": "K29", "gate": "CTRL", "what": "摘掉常驻条控件那一支的 :not(body, html)",
     "expect": ["按钮底色 实测"],
     "kind": "text",
     # 与 K28 同一条排除、不同的支：这一分管的是 background-color，漏掉的代价是**全站**控件
     # 的面被拍平。锚点带换行＋六空格＋`:is(button,`，量过命中 1 处（那一截换行缩进刻意是六：
     # 四空格起头的 :is( 是本文件里后代那一格的唯一定位点，见上面 K03/K06 那段账）。
     "args": ("css", '  ):not(body, html)\n      :is(button,', '  )\n      :is(button,'),
     "note": "证人不是新加的那两枚，是早就在职的两本：form 里那颗裸钮（btn_face，§4b 的粉底）"
             "和站点自涂绿的 fixedBtn。摘掉排除后它们被这一支拍成透明，红的名字是「按钮底色」"
             "——这一格当初就是被这两本报出来的，不是被新证人报出来的"},
]

# 族开头那道 body 排除（同一格的第四份副本）：K28/K29 割的是分支自己抄的那两遍，
# 这一柄割族四份副本一起丢——四份逐字相同那条守卫不会红，而夹具的 <body> 也读不出行为
# （现量：body 有直接 button 子节点，族末尾 :not(:has(> button)) 按构造先把它排掉了），
# 所以红的只能是 check-controls.py 里第三格「在不在」守卫。失效方向写在那条守卫的注释里。
CUT += [
    {"id": "K30", "gate": "CTRL", "what": "四份副本一起丢掉族开头那道 :not(body, html)",
     "expect": ["浮层族少了那道整页排除"],
     "kind": "text", "n": NCOPY + 2,
     # 锚点必须带 `:not(button, svg)` 后缀：族上方那条注释也写了 `:not(body, html)` 的字样，
     # 裸串 9 处、带后缀 4 处（先量过再落笔）。n=4 让四份副本一起动，否则半具刀割出来的
     # 是「副本漂成两样」那条守卫，而不是这一格。
     "args": ("css", '):not(body, html):not(button, svg)', '):not(button, svg)'),
     "note": "这一柄的证人不是行为读数，是「在不在」守卫：夹具 <body class=\"ksBodyHost "
             "header-dark\"> 底下直接铺着 <button>，所以族末尾那道 :not(:has(> button)) 按构造"
             "先把 body 排在外面——2026-10-04 现量 body_cut=false、后代那格两跑同为 14/46，"
             "摘掉整页排除在夹具里读不出任何变化。承重的那一读在真站：同一族串在无头之外量 "
             "github.com/features 渲染后的 DOM，body 的 class 末截就是 header-dark（header 那截"
             "词根按子串命中），而 btn_child／btn_grand 都是 false、depth≤2 的 button 数 0，"
             "去掉这一截后 body 当场匹配族（body_cut=true）。留下的时候它读 §2 的画布 "
             "rgb(255, 246, 250) 与 backdrop-filter: none；摘掉就是整页披粉底玻璃＋一层"
             "白烧的合成层。夹具之所以量不到，是因为它把控件全铺在 body 底下，而真站埋得深"},
]

# 「钉档只钉浮动面、常驻条跟着区域翻」这一分法要有两把刀，各割一边的范围：
# K31 往钉档那条的词根表里塞一截常驻条词根（页头那截），K32 把 color-scheme 声明加回面块
# （= 退回 2026-10-04 之前的形状，全族连条一起钉）。两柄点的都是 check-controls 里那句
# 「常驻条跟着区域翻」——它读的是深色区域里那根条的面与墨，条被钉上档就会在白天档解成粉。
# 为什么只有白天档红：钉的是 var(--kScheme, light dark)，夜晚档里它解出的仍是夜晚那一支，
# 与区域声明一致，读数和期望相同。这是量出来的，不是推的（两柄刀的 rc 都只在白天那两本上）。
CUT += [
    {"id": "K31", "gate": "CTRL", "what": "把页头那一截词根也钉进浮动面的档",
     "expect": ["白天 常驻条跟着区域翻：面实测", "白天 常驻条跟着区域翻：墨实测"],
     "kind": "text",
     # 锚点取钉档那条自己的开头 `:where(:is(` 加头两截词根：族那四份副本都是顶格 :is( 起手，
     # 没有 :where( 前缀，所以这一串在文件里只有一处（先量过再落笔）。
     "args": ("css", ':where(:is(dialog, [popover]',
              ':where(:is(dialog, [popover], [class*="header" i]'),
     "note": "钉档的范围是「浮动面」，不是「玻璃族」——这两句现在不等价，差的就是常驻条那五截词根。"
             "往词根表里补一截 header，夹具里那根 .anti-dark-bar（类名逐字取自 github.com/features "
             "页头那一横，被同一截词根按子串追上）当场被钉上面板档：深色区域里披上白天那层粉，"
             "而它下面那块 dark 树里的整页仍是站点自己的深色——正是用户指着截图说「这个粉看起来"
             "与整体不搭了」的那一格。白天档两本各红一次"},
    {"id": "K32", "gate": "CTRL", "what": "把 color-scheme 声明加回 §4c 的面块",
     "expect": ["白天 常驻条跟着区域翻：面实测", "白天 常驻条跟着区域翻：墨实测"],
     "kind": "text",
     # 落点取面块里那行虚焦声明之前：同一串在文件里也是 1 处（K01/P03 割的就是这一行）。
     "args": ("css", "    backdrop-filter: var(--ks-glass-blur) !important;\n",
              "    color-scheme: var(--kScheme, light dark) !important;\n"
              "    backdrop-filter: var(--ks-glass-blur) !important;\n"),
     "note": "K31 割的是钉档那条「少列了谁」，这一柄割的是「上色的地方顺手把档也钉了」——"
             "同一个分法的两个漂移方向，各配一把。这一刀等于退回 2026-10-04 分裂之前的形状："
             "面块里既有底也有 color-scheme，族里的每一格（含常驻条）都按面板解。"
             "浮动面板那几格不会红（它们本来就该钉），所以这一柄唯一的证人就是深色区域里那根条"},
]

# 族末尾那道标题排除（:not(h1…h6)，2026-10-05 runoob 的 <h2 class="tutheader">）两向各一柄：
# K33 割"删掉"，K34 割"写宽了"。两柄红的不是同一本——删掉时先红的是"在不在"那句守卫
# （四份副本一起删，逐字相同那条看不见），写宽时守卫照样绿（它按子串认，多一项还在），
# 红的是正控制那一本：同一枚 tutheader 挂在 div 上必须吃到面。
CUT += [
    {"id": "K33", "gate": "CTRL", "what": "整族删掉那道标题排除 :not(h1…h6)",
     "expect": ["浮层族少了那道标题排除"], "kind": "text", "n": NCOPY + 2,
     "args": ("css", "):not(button, svg):not(h1, h2, h3, h4, h5, h6)",
              "):not(button, svg)"),
     "note": "这一格量的是「类名撞上词根的标题」要不要被画上整幅面。删掉之后夹具里那枚 "
             "h2.tutheader 当场吃面（真站同一形：2026-10-05 配对重拍在 runoob 的 1280×1500 框里 "
             "量到四块这样的带，白天档摘掉那一截前 rgb(254,234,243)、摘后 rgb(250,247,246) "
             "是站家自己的浅底，站点根本没给这块排过底）。"
             "红在守卫那一句上，不红在行为那一句上——因为守卫走在浏览器取数之前，"
             "行为那本（标题形那一格判的是「不穿玻璃＋吃上 §4 圆角底」）在同一趟里轮不到说话"},
    {"id": "K34", "gate": "CTRL", "what": "把标题排除写宽到连 div 一起排掉",
     "expect": ["玻璃面 标题形对照"], "kind": "text", "n": NCOPY + 2,
     "args": ("css", ":not(button, svg):not(h1, h2, h3, h4, h5, h6)",
              ":not(button, svg):not(h1, h2, h3, h4, h5, h6, div)"),
     "note": "反面那一格（标题让路）单独看永远可以是「把整族收得死死的」骗过去的——"
             "所以这一柄往排除里加一项 div。第一版让它红在了守卫上（整串相等那条按 :not(h1…h6) "
             "带闭括号认，多一项就把那一串打断），行为那本轮不到说话，刀判 MISSED；"
             "守卫改成「六个标题形都在同一组 :not() 里」后它绿在这一柄上，"
             "红的其中一本是正控制：同一枚 tutheader 挂在 div 上不再吃面，实测 rgba(0, 0, 0, 0)。"
             "两柄合起来才把这一截钉成「不能删、也不能加」两向都有牙"},
]

# §4 标题圆角底（2026-10-06 换机制：从"给字描一圈我们以为的底色"改成"给字自己造一块底"）。
# K35 割的是这一块唯一的上色声明；宽度那一形（width:fit-content）没刀，理由写在设计记录末尾。
CUT += [
    {"id": "K35", "gate": "CTRL", "what": "摘掉标题圆角底那条 background-color 声明",
     "expect": ["headingRootClass", "标题形这一格判的是"], "kind": "text",
     "args": ("css",
              '    background-color: color-mix(in srgb, var(--ks-plate) calc(var(--kHalo, 1) * 100%),\n'
              '                                         transparent) !important;\n',
              ""),
     "note": "这一格换掉的是旧判据的前提：标题那块底从 2026-10-06 起由 §4 的圆角底上色，"
             "所以 headingRootClass 那一格不再判「留着站家的底」，改判「不穿玻璃＋吃上 §4 的圆角底」"
             "（check-controls.py 的 HEADEXCL 分支）。摘掉声明后站家的 #f6f8fa 原样赢回，红在行为那一句上"
             "而不是红在守卫上——K33 割选择器时红的是「在不在」，这一柄走的是取数以后那一步。"
             "同一刀也动真站的地面普查？——没量过，别当成这柄刀的读数：垫底前后那对数"
             "（26 块／81,610 格 → 54 块／304,336 格）是两版 CSS 之间的对照，那一版把旧的四层光晕"
             "一起换掉了；这一刀只摘上色、留着 2/5px 两层，它落在普查上的数没人读过。"
             "普查那把尺（tools/ground-diff.py）报的是分布不是判定，给它配刀得先立一条"
             "不靠产物反推的阈值——那一格还欠着"},
    {"id": "K36", "gate": "CTRL", "what": "摘掉链接形按钮那条 -webkit-text-fill-color",
     "expect": ["链接形按钮孙节点", "没上自家墨"], "kind": "text",
     "args": ("css",
              '    -webkit-text-fill-color: var(--ks-ink-1) !important;\n',
              ""),
     "note": "割的是 2026-10-06 那颗 docs.github.com \"Quickstart\" 的因：站点把字色排在**孙节点**"
             "的类名上（.Button--label-primary{color:…}，0,1,0 无 !important），我们写在 <a> 上的"
             "color 只能靠继承过去，而继承值在任何直接命中的声明面前都输——面我们的、字站家的，"
             "真站量到 1.36:1（白天）／1.38:1（夜晚）。夹具那枚证人 a.ksPrimerBtn span span 读的是"
             "tf（-webkit-text-fill-color 的计算值）而不是 color：拿 color 读数改前改后都一样，"
             "这一格就成了空话。改法落盘前这一行实测 rgb(255,255,255)、我们的墨 rgb(58,43,62)／"
             "rgb(244,234,255)，两档各红一次；摘掉声明应当红回同一本"},
]

# 普查【衬底】那一栏的"族外"半边（2026-10-06 补的盲区：一块浮着、没被词根收进玻璃族的面，
# 底下一样是我们的粉地面，旧代码在 `if not f["glass"]` 就整块跳过，GitHub 仓库页现读到
# 一块 74 字的粘滞面却印「判 0 块」）。两柄刀一头一尾：K37 摘空族外栏（漏判方向），
# K38 把全部面灌进族外栏（过收方向）——只证"摘掉会红"对"收多了"是沉默的。
CUT += [    {"id": "K41", "gate": "CTRL", "what": "面内搜索壳那一支的 :has 里把 input 换成 textarea",
     "expect": ["面内搜索壳底"], "kind": "text", "n": 1,
     "args": ("css", ':has(:is(input, textarea, [role="textbox"]',
                       ':has(:is(textarea, [role="textbox"]'),
     "note": "正面证人：真站上那枚壳里住的是 <input>，把结构条件里的 input 换掉，"
             "壳就该退回站点那块白——红在「面内搜索壳底」这一行上。"},
    {"id": "K42", "gate": "CTRL", "what": "面内搜索壳那一支的 :has 多收一枚 span（过界方向）",
     "expect": ["面内搜索壳反面(没控件)"], "kind": "text", "n": 1,
     "args": ("css", ':is(input, textarea, [role="textbox"], [role="searchbox"], [role="combobox"])',
                       ':is(span, input, textarea, [role="textbox"], [role="searchbox"], [role="combobox"])'),
     "note": "反面证人：结构条件多收一枚 span 之后，面里那枚「类名带 search、里面只有 span」的壳也会被垫上底，"
             "而它按契约不该被画。这一柄割的是「收得太多」那个方向——K41 只证「割少了会红」，对收多是沉默的。"
             "原先这柄是把整截 :has(...) 摘掉，那会让尾巴落成 :not(:is(input, textarea, select)) { 那一形，"
             "正好与「玻璃面底色」那行的 FACE 锚点同形（命中 2 处），闸门先死在选择器歧义上、走不到反面证人那一格，"
             "故按锚点中性改成往 :is 里添一枚 span。"},

    {"id": "K37", "gate": "SELF", "what": "把普查的族外那一栏摘空",
     "expect": ["两栏划分不成立"], "kind": "text",
     "args": ("census",
              '    return ([f for f in faces if f["glass"]],'
              ' [f for f in faces if not f["glass"]])',
              '    return ([f for f in faces if f["glass"]], [])'),
     "note": "割的是 buckets 那一格（划分只住这一处：逐块打印、汇总两栏、selftest 的分区断言"
             "都读它）。摘空族外栏后合成人面 E 仍判 low——judge() 本来就不认玻璃与否，它一直"
             "判得动——所以红的必须是分区那一句：这一格的主张是「族外那些面收没收进表」，"
             "不是「那一栏的算术会不会算」"},
    {"id": "K38", "gate": "SELF", "what": "把全部浮面灌进普查的族外那一栏",
     "expect": ["两栏划分不成立"], "kind": "text",
     "args": ("census",
              '    return ([f for f in faces if f["glass"]],'
              ' [f for f in faces if not f["glass"]])',
              '    return ([f for f in faces if f["glass"]], [f for f in faces])'),
     "note": "反面那具：族外栏过收（同一块面进两栏）。两栏互斥是这一栏唯一的口径主张，"
             "过收会让「底下衬着我们自己的面 = N 块」两栏加起来大于真数，也把玻璃面的归因"
             "重复计进「没穿玻璃的浮面」——所以两头都得有牙"},
]

# 衬底归因那一支：`own` 只等于"这一格住在 html/body"，不等于"那是我们的粉地面"。
# 站点把实心底涂在 body 上、再压一条全透明的图（docs.github.com 现读：body 的
# background-color rgb(0,0,0) ＋ linear-gradient(transparent,transparent)），旧代码看见
# 图就把停靠换成我们那三个值 ⇒ 把"底下是站家黑"印成"底下衬我们的粉"，比值跟着算错。
# 两柄刀一头一尾：K39 摘掉新守卫（漏，回到旧错归因），K40 让新守卫过收（把我们的粉也判成站家）。
CUT += [
    {"id": "K39", "gate": "SELF", "what": "摘掉「body 自涂实心底」那支归因守卫",
     "expect": ["衬底归因两向不成立"], "kind": "text",
     "args": ("census", "if solid[3] >= 1.0 and not any(",
              "if False and solid[3] >= 1.0 and not any("),
     "note": "割回补洞前的那条支路：`own and img` 一律换成我们的 token 停靠。"
             "合成人面 F（body 实心黑＋一条全透的图）必须红在「黑实心底那格读到 我们的粉地面」；"
             "它不红＝这一格的证人只是摆设，普查那句「底下衬着我们自己的面 = N 块」还是不能读"},
    {"id": "K40", "gate": "SELF", "what": "让「body 自涂实心底」那支守卫过收（连我们的粉也判掉）",
     "expect": ["衬底归因两向不成立"], "kind": "text",
     "args": ("census", "if solid[3] >= 1.0 and not any(",
              "if solid[3] >= 1.0 and any("),
     "note": "反面那具：把 not 摘掉，守卫会把我们真涂的那面粉（合成人面 C：html 的粉渐变）"
             "也判成「站点自涂」——归因表从 5 块粉掉回 0 块，而它是"
             "「玻璃底下衬的是我们的粉」这一整条主张的读数来源，过收和漏判一样致命"},
]

# #135：面里的控件不再自己垫一块底。这一支有两条主张，方向相反，所以两头各一柄：
# 摘掉声明（控件重新垫底，站家排在控件**底下**的镜像被盖住）与补上 !important
# （我们的透明顶掉站家自己写的底，墨压在站家的底上＝#112 那一形由我们亲手造出来）。
CUT += [
    {"id": "K43", "gate": "CTRL", "what": "摘掉「面里的控件不再垫底」那一支的声明",
     "expect": ["面里的控件自己垫了底"], "kind": "text", "n": 1,
     "args": ("css", "    background-color: transparent;\n",
              "    --ks-k43: transparent;\n"),
     "note": "正证人：夹具里那枚住在面里的裸 <input> 该读到 α=0。把声明换成一条空的自定义属性，"
             "控件就退回 UA 那块实心白——2026-10-10 登录态 github.com 快搜那一格读到的正是这块白："
             "夜档 0 格墨／最大 1.66，站点把可见的字排在 input **下面**，底一垫整框空。"
             "刻意不整行删除而是同形替换：这一支下面的行号被别的锚点引用，删行会把它们一起顶红，"
             "那把刀就在替我普查谁钉着行号，而不是割这一格"},
    {"id": "K44", "gate": "CTRL", "what": "给「面里的控件不再垫底」那一支的声明补 !important",
     "expect": ["站点自己写的底"], "kind": "text", "n": 1,
     "args": ("css", "    background-color: transparent;\n",
              "    background-color: transparent !important;\n"),
     "note": "反面那具：夹具里那枚自己写了底的控件必须留着站点那块 #1a7f37。带上 !important 后我们的"
             "透明顶掉站家的底，框里只剩我们的墨压在玻璃上——w3schools 顶栏那枚搜索框夜档量到 1.16，"
             "就是这一形在真站的样子（#112）。这一柄割的是「刻意不带 !important」那条决定：K43 只证"
             "摘掉会红，对加上是沉默的"},
]


# 关系形证人（#140 补的那格）的刀。锚点必须带上注释开头那一段：
# 文件里 `background-color: var(--ks-canvas-1) !important;` 后面紧跟换行的那一处是**第 123 行**，
# 不是这一支（这一支的分号后面是两个空格加注释）。取截断形会割到别人身上。
_SHELL_DECL = '    background-color: var(--ks-canvas-1) !important;  /* 两档同一支'
CUT += [
    {"id": "K45", "gate": "CTRL", "what": "把面内搜索壳的底换成面自己那支 token（垫了等于没垫）",
     "expect": ["面内搜索壳跟它衬的面看不见分开"], "kind": "text", "n": 1,
     "args": ("css", _SHELL_DECL,
              '    background-color: var(--ks-canvas-2) !important;  /* 两档同一支'),
     "note": "这一柄割的是**当天真的落过的那一档**：夜枝当时写的就是 canvas-2，与面同一支 token。"
             "壳 α=1 时两个端点都塌回面 token 自己，关系形证人当场读 0.0/255，两档各红一行；"
             "而计算样式那一格对这一形同样沉默：它只问「这行落没落上」，不问「落上的这行看不看得出来」。"
             "本来还有一柄同族的「改回 rgba(0,0,0,0)」，现读作废：那一形根本走不到关系断言——"
             "SPECS 那格对 `rgba(...)` 这个形状算不出期望值，先在那里报错红掉，"
             "而那一带的住户本来就是 S58（摘除声明）。留一柄能真开火的，比留两柄数数一样的高"},
]


# 链接那一圈描边（2026-10-11，「文字看不清」那一族的修法）。判据把三条关系分开钉，
# 所以三个方向各一柄：摘掉自定义属性（描边整个没了）、白天那一支也画上边（过画）、
# 把 1px 硬边换回 §99 那种模糊半径（机制退回去）。三柄都只动 a{} 这一块内部，
# 且行数中性——删行会把别处按行号钉着的锚点一起顶红，那把刀就在替我普查谁钉着行号。
CUT += [
    {"id": "K46", "gate": "CTRL", "what": "把四枚 1px 偏移换成 none（描边整个没了）",
     "expect": ["链接描边整条没了"], "kind": "text", "n": 1,
     "args": ("css",
              "    text-shadow: 1px 0 0 var(--ks-edge), -1px 0 0 var(--ks-edge),\n"
              "                 0 1px 0 var(--ks-edge), 0 -1px 0 var(--ks-edge);\n",
              "    text-shadow: none;\n"
              "    /* k46 割形：四枚偏移换成 none，等价于这条声明没落上 */\n"),
     "note": "两行换两行，行数中性（删行会把按行号钉着的别处锚点一起顶红，K43 同病同治）。"
             "原先这柄割的是上一行的自定义属性名——试跑证明那形割不动：属性一改名，"
             "text-shadow 里的 var(--ks-edge) 就成了「用了没定义」，被 strip.py 的守卫当场拦下"
             "（STRIP ERROR，整条流水线退出），红的是投递层的报错而不是这一格断言，"
             "expect 里那句名字根本到不了。所以改割偏移本身：none 是合法值，投递层放行，"
             "计算样式读到 none，两档各红一行。"},
    {"id": "K47", "gate": "CTRL", "what": "把 light-dark 的第一支从 transparent 换成实色（白天过画）",
     "expect": ["白天那一支不该有边"], "kind": "text", "n": 1,
     "args": ("css", "light-dark(transparent, var(--ks-canvas-1))",
              "light-dark(var(--ks-canvas-1), var(--ks-canvas-1))"),
     "note": "这一柄钉的是「白天整幅 0 格改动」那条出图 A/B 读数（runoob 白天档候选 vs 认证档，"
             "1,920,000 格里改动 0 格）：改成两支都画之后白天那一支读到 rgb(255, 246, 250) α=1，"
             "红的正是这一行。夜档不受影响——K46 只证「摘掉会红」，对「多画一支」是沉默的。"},
    {"id": "K48", "gate": "CTRL", "what": "把四枚 1px 硬边换成 §99 那种 2/5px 模糊（机制退回去）",
     "expect": ["链接描边的半径不是 0"], "kind": "text", "n": 1,
     "args": ("css",
              "    text-shadow: 1px 0 0 var(--ks-edge), -1px 0 0 var(--ks-edge),\n"
              "                 0 1px 0 var(--ks-edge), 0 -1px 0 var(--ks-edge);\n",
              "    text-shadow: 0 0 2px var(--ks-edge), 0 0 5px var(--ks-edge),\n"
              "                 0 0 2px var(--ks-edge), 0 0 5px var(--ks-edge);\n"),
     "note": "保持四枚一层、颜色与档都不动，只把偏移挪进半径：这样红只能来自「半径必须是 0」那一句，"
             "不会被层数或颜色那两格抢先点名。§99 换机制的原因就在这儿——模糊半径一起吃掉 1–2px 宽的"
             "中文笔画，2× 看图那一行字外一圈发虚，legibility 还多出一行 1.1；描边之所以成立，"
             "是它把半径收成了 0"},
]


SENT_CUT = [
    {"id": "K18", "gate": "SENT", "what": "把哨兵档收窄成只扳画布 token（墨 token 不扳）",
     "expect": ["哨兵档没扳这些文字颜色 token"], "kind": "text",
     "args": ("proxy", '        val = " ".join(raw.split())\n',
              '        val = " ".join(raw.split())\n'
              '        if "canvas" not in name:\n'
              '            continue\n'),
     "note": "这一柄要的不是「玻璃没了」那种红，而是「归因答不出字是谁涂的」这一格会说话："
             "只扳画布时页面仍会上肤、版式仍逐字不动、底仍归因得出来，"
             "所有像素与计算样式闸门全绿——只有真站名单里那 21 行"
             "（我们的浅字压在站家浅底上，最坏一枚 w3schools 夜晚档标题芯对纸 1.71）"
             "会从读数里静默消失。INK_TOKENS 按 skin.css 的声明形状现推，"
             "所以这柄刀割的是取色那一支而不是某枚 token 的名字：抄名字的话，"
             "皮肤改天换个墨 token 名，刀就先落在错的地方"},
]

# 「这一格由谁定位」不该要人翻 300 行注释去认。M 系列每柄刀自己声明了它点名哪几行
# （expect 就是 SPECS 里的行名），所以代管关系由 SEL_CUT 现推，不另立名册：
# 那 13 行 S 号割的是整个族共用的一块声明，判据在解析 CSS 那一步就 die（报
# "那条规则块里没有 … 声明"），被割那一行的名字进不了红名单——这不是尺子瞎了，
# 是那一行在 CSS 侧的真实依赖根本不在它自己那条声明上（见 SEL_CUT 上面那段）。
# 入代管要同时满足三条，所以这层豁免烂不掉：行名在 M 系列声明过的名单里、这一柄 MISSED、
# 且红的是那句结构性 die。换成别的死法、或哪天它自己能定位了，都不影响；
# 但如果它 MISSED 而红的不是那句——它掉回 MISSED，把 rc 顶成 1。
LOCALIZED_BY = {row: k["id"] for k in SEL_CUT for row in k["expect"]}
# 「玻璃面 标题形对照」那一行是 2026-10-05 追加进 SPECS 的（check-controls.py 末尾，
# 标题让路那对判据的正控制：同一枚 tutheader 挂在 div 上必须吃到面）。它的自动刀（S57）
# 割的是整族共用的那条 background-color，与 S23/S41 同病：CTRL 在解析那一步就 die，
# 被割那行的名字进不了红名单——全量电池里它 MISSED（/tmp/final-battery.log 第 123/407 行）。
# 这一格在 CSS 侧没有自己那条声明，能定位它的只有 K34（往排除式里多塞一项 div：
# 别的行都照旧绿，红的正好是这一行）。代管的三条闸门照旧都要满足（名字在这张表里、
# 这一柄 MISSED、红的是那句结构性 die），所以它烂不掉：哪天 K34 不再点名这一行，
# 它自己就掉回 MISSED 把 rc 顶成 1。
LOCALIZED_BY["玻璃面 标题形对照"] = "K34"
STRUCT_DIE = "那条规则块里没有"
# S 号是按 SPECS 位置生成的（追加行会顶号，所以归属只能现推，不抄编号）
_BY = {s["id"]: s["args"][0] for s in CUT if s["kind"] == "css_spec"}

# 全量名册只枚举一次：下面那个"点空了必须死"的守卫原先自己又抄了一遍
# （`_all = CUT + SEL_CUT + GLASS_CUT + DIFF_CUT + PIX_CUT`），于是新加一柄只进 STAGES 的话，
# 守卫会报"这把刀不存在"而它其实就在跑的那张表里——同一本文件里的两份名册自己打了架。
ALL_KNIVES = CUT + SEL_CUT + GLASS_CUT + SENT_CUT + DIFF_CUT + PIX_CUT
STAGES = ALL_KNIVES
if len(sys.argv) > 1:  # 只跑点名的那几柄（按编号前缀），调试用
    _pats = [p for p in sys.argv[1].split(",") if p]
    STAGES = [s for s in STAGES if any(s["id"].startswith(p) for p in _pats)]
    # 点空了必须死：0 柄刀时末尾那句"0/0 柄刀红在了被割的那一本上"会配着 rc=0 一起出去，
    # 读起来像"全过"。实测 `--help` 就是这么绿着退的。
    _all = ALL_KNIVES
    _none = [p for p in _pats if not any(s["id"].startswith(p) for s in _all)]
    if _none:
        sys.exit(f"KNIFE ABORT: 点名的前缀 {_none} 一把刀都没对上（现有编号："
                 f"{_all[0]['id']}…{_all[-1]['id']}，共 {len(_all)} 柄）")
if not STAGES:
    sys.exit("KNIFE ABORT: 名单为空——没有一把刀被跑到，这不等于全过")

print(f"变异电池：{len(STAGES)} 柄刀，每柄先量一次自己的基线（pristine：{HASH0}）\n")

# KNIVES_DRY=1：只量"锚点还落不落得下去"，不跑闸门、不出图。
# 为什么要这一格：2026-10-06 那一跑全量电池（115 柄、约一小时）里，K17/K19 两柄的
# 判据根本没说话——它们死在 apply_cut 的锚点命中数上（#96 往族末尾插了 :not(h1…h6)，
# 把带 `:not(button, svg)` 前缀的旧锚点顶成 0 命中）。那一类失效不需要浏览器就能发现，
# 所以把它单拆成一趟秒级的过筛，换词根／改注释之后先跑它，再决定要不要付一小时的账。
# 它不作证"割了会红"（那是 CAUGHT，只有跑闸门才知道），只作证"刀还落得下去"。
if os.environ.get("KNIVES_DRY") == "1":
    def _land(st):
        if st["kind"] == "text":
            key, old, new = st["args"][0], st["args"][1], st["args"][2]
        else:
            old, new, why = css_spec_cut(*st["args"])
            if old is None:
                return f"CANNOT-CUT：{why}"
            key = "css"
        err = apply_cut(key, old, new, st["id"], st.get("n", 1))
        return f"LANDING-FAIL：{err}" if err else None
    bad = []
    for st in STAGES:
        msg = _land(st)
        restore_all()
        if msg:
            bad.append(f"{st['id']} {msg}")
    # 正控制自带：一把注定落不下去的探针必须被这一趟抓到，否则"0 柄落不下去"是空的。
    probe = {"id": "_PROBE", "kind": "text", "gate": "CTRL", "what": "DRY 自检探针",
             "expect": [], "n": 1,
             "args": ("css", "「这串字样不可能出现在这份文件里」", "")}
    if _land(probe) is None:
        restore_all()
        sys.exit("KNIVES_DRY 自检失效：探针锚点本应 0 命中却没被抓到，这一趟的\"全部落得下去\"不作数")
    restore_all()
    print(f"KNIVES_DRY：{len(STAGES)} 柄里 {len(bad)} 柄落不下去"
          f"（正控制探针被抓到，判定与逐柄同源）")
    for b in bad:
        print("  " + b)
    sys.exit(1 if bad else 0)

rows = []
try:
    for st in STAGES:
        restore_all()
        gate = st["gate"]
        rb, ob, tb = run(gate)
        if rb != 0:
            rows.append((st["id"], "BASELINE-RED", st["what"], "基线就是红的，这一刀无法归因"))
            print(f"[{st['id']}] 基线红（{tb:.0f}s）—— 不做判定：\n" + "\n".join(reds(ob)[:4]))
            continue
        if st["kind"] == "text":
            key, old, new = st["args"][0], st["args"][1], st["args"][2]
        else:
            old, new, why = css_spec_cut(*st["args"])
            if old is None:
                rows.append((st["id"], "CANNOT-CUT", st["what"], why))
                print(f"[{st['id']}] 落不了刀：{why}")
                continue
            key = "css"
        err = apply_cut(key, old, new, st["id"], st.get("n", 1))
        if err:
            rows.append((st["id"], "LANDING-FAIL", st["what"], err))
            print(f"[{st['id']}] 刀没落盘：{err}")
            continue
        rk, ok, tk = run(gate)
        cross = None
        if gate == "PIX":
            rc_x, ox, _ = run("CTRL")
            cross = f"计算样式闸门{'也看见' if rc_x else '看不见'}"
        expect = "；".join(reds(ok))
        hits = [e for e in st["expect"] if e in expect]
        caught = rk != 0 and len(hits) == len(st["expect"])
        who = LOCALIZED_BY.get(_BY.get(st["id"], ""))
        by_design = not caught and who is not None and STRUCT_DIE in expect
        verdict = "CAUGHT" if caught else "BY-DESIGN" if by_design else "MISSED"
        rows.append((st["id"], verdict, st["what"],
                     (f"rc={rk} 基线绿；点名 {'/'.join(hits)}" if caught else
                      f"rc={rk} 结构性 die，这一格由 {who} 定位" if by_design else
                      f"rc={rk}，期望的名字 {st['expect']} 里只出现 {hits}") +
                     (f"；{cross}" if cross else "")))
        print(f"[{st['id']}] {st['what']}｜基线绿 {tb:.0f}s → 落刀 {tk:.0f}s｜{verdict}"
              f"{'（' + cross + '）' if cross else ''}")
        for l in reds(ok)[:6]:
            print(f"    {l.strip()}")
finally:
    restore_all()
    # 每柄刀的 CTRL/PIX 那两跑现在都会自己重生成 preview/skin.css（探针引它，不引源文件），
    # 所以电池跑完时那份副本来自**最后一柄刀**那棵树。还原了源文件还得还原副本，
    # 否则下一跑的第一格读到的是一份混着刀印的生成物。
    r = subprocess.run([sys.executable, "tools/strip.py"], cwd=ROOT,
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("KNIFE WARN: 还原后重生成 preview/skin.css 失败：\n"
              + (r.stdout + r.stderr).strip())
    # 同一笔账的像素侧：PIX 那一族刀每跑一次就用当前那棵树重写 shots/*.png，
    # 所以电池收尾时盘上那 16 张图来自**最后一柄刀**——下一跑读图的那本闸门会把刀印
    # 当成皮肤的红。量过：P09（把 navbar 词根加进族）跑完不重出图，紧接着单跑
    # tools/diff-shots.py 报「navbar 词根的导航条 开关两趟有 4/31 级差」，
    # 而 .ch-e 的计算样式在两趟里逐字节相同（bg rgb(239,239,241)）——红在图上不在皮肤上。
    s = subprocess.run(["./tools/shoot.sh"], cwd=ROOT, capture_output=True,
                       text=True, env={**os.environ, "SKIP_PRE": "1"},
                       timeout=TIMEOUT["PIX"])
    if s.returncode != 0:
        print("KNIFE WARN: 还原后重出 shots/ 失败，像素闸门的下一跑读的是刀印那批图：\n"
              + (s.stdout + s.stderr).strip()[-800:])

print(f"\n{'='*72}\n{'编号':<5}{'判定':<14}{'这一刀割的是什么':<26}细节")
for rid, verdict, what, detail in rows:
    print(f"{rid:<5}{verdict:<14}{what:<26}{detail}")
miss = [r for r in rows if r[1] == "MISSED"]
bd = [r for r in rows if r[1] == "BY-DESIGN"]
# 这三类都没走到"落刀—看谁红"那一步，既不是红的功劳也不是哑刀：把它们算进
# "红在了被割的那一本上"会让汇总行替没发生的事说话（量过：4 柄基线红被记成 68/81）。
untested = [r for r in rows if r[1] in ("BASELINE-RED", "LANDING-FAIL", "CANNOT-CUT")]
caught = [r for r in rows if r[1] == "CAUGHT"]
print(f"\n{len(caught)}/{len(rows)} 柄刀红在了被割的那一本上"
      + (f"；{len(bd)} 柄割的是族共用那条声明、判据结构性 die，"
         f"那一格由 {sorted({LOCALIZED_BY[_BY[r[0]]] for r in bd})} 定位" if bd else "")
      + (f"；{len(untested)} 柄根本没判定（基线就是红的或刀没落盘）："
         f"{[(r[0], r[1]) for r in untested]}" if untested else "")
      + (f"；没红的：{[r[0] for r in miss]}" if miss else
         "，无一把哑刀" if not bd and not untested else ""))
sys.exit(1 if miss or untested else 0)
