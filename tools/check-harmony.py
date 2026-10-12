#!/usr/bin/env python3
"""风格统一闸门：上肤以后，不许有一块**我们的**颜色孤零零立在别人的底中间。

这一格是 2026-10-05 用户指着 github.com/features 页头那一横说的「这个粉看起来与整体不搭了」：
站点把那一块排成深色，而我们先把分支钉在了常驻条上，于是两条黑底中间孤零零一条粉。
CSS 那一侧已经改了契约（§4c：钉档只钉浮层，常驻条跟着所在区域翻），夹具也有直判与两把反面刀；
这个文件补的是**真站这一侧的常驻读数线**——出图每次重出，判据第一次落在这儿。

两本各判一个方向（同一页的两张图配对，第二张是哨兵档）：
  · 白天档 `spot-X-day.png` + `spot-X-day-sent.png`：找「我们的浅粉段」被**站家深底**夹着。
  · 夜晚档 `spot-X-night.png` + `spot-X-night-sent.png`：找「我们的深李段」被**站家浅底**夹着。
形状判据（两本同一条，只是方向相反）：按 8px 横带逐行、每 3px 取一列——
  本段（连续 ≥2 带）里"我们那一族"的格 ≥20%，段外上下各两带都 <5%，且那两带的**衬底**
  （深色那一族／浅色那一族）各自 ≥50%。粉红一片或深李一片时邻居同族，永远不火。

为什么要配哨兵那一趟：不配就只能按调色板形状认，站点自己用 magenta／紫渐变会一起算进来
（GitHub 的 hero 渐变 rgb(43, 30, 76) 与我们的深李 rgb(36, 22, 52) 在同一条尺的同一侧）。
哨兵档把**我们整套颜色 token** 扳成纯绿、非颜色 token 不动，所以同一坐标在哨兵图里发绿＝那块是我们画的；
站点自己涂的一律不发绿。剩下的代价按方向登记：坐标要对齐，两档尺寸不同就整对不判（见下）。

两条没判的格子，按形状登记在这里（不是"应当判而漏了"，是这条尺子主张到哪为止）：
  · 贴边的段不判红也不判绿，但逐段点名报出来。段一路延伸到画面外，画面里看不见它的另一侧：
    可能是页尾往下接着铺我们自己的画布（不孤零零），也可能是贴窗口顶的一条常驻板（孤零零）。
    2026-10-05 六站 12 对现量：11 段贴边，其中 9 段的段内一侧仍然是我们那一族（84–100%，
    也就是段其实往里长，画面外那侧无从判起）；只有两段的段外一侧真是站家的底——
    runoob 夜晚档 y=0–16（下两带 12%/0% 我们族、88%/100% 浅底）与 w3schools 夜晚档 y=0–88
    （下两带 12%/0%、88%/98%）。这两条都是"夜晚档在浅底站点顶上的常驻条"，看图复核过：
    条上自己的字是浅墨压深李、对比够，缺的是它下面整页站家自涂的白（那格归 #79 那条让路记账），
    不是"两条别家底中间夹一条我们的"，所以不立尺子——立了会把画面外那一侧的两种可能一起判死。
  · 反面控制（把分支声明加回 §4c 面块，＝电池 K32 那一刀的现场形状）现量只让**白天那一本**开火：
    y=56–104、段内峰值 99%、rc=1，与不配哨兵的上一版读数逐字相同；夜晚那一本同一次落刀 0 段，
    因为那一横在夜晚档解成深李、上下两条站家底也是深色——反衬那一格不成立。
    所以这一格的真站证据是单向的，夜晚方向的牙只有 selftest 那两格（正/反各一）举着。

跑法：python3 tools/check-harmony.py [图路径…]（默认扫 shots/spot-* 的 day/night 两对；
      点名时那一档按图名里的 -night 认，写死白天判据会让夜晚那张永远不火）
      python3 tools/check-harmony.py --selftest   # 不开浏览器：四格控制，两正两负
"""
import glob
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BAND, XSTEP, YSTEP = 8, 3, 1
FIRE, NEIGH, CONTEXT = 0.20, 0.05, 0.50
MIN_RUN = 2

# 四条谓词都是"形状"而不是贴色：要抓的正是 α 叠在别家底上的**合成色**。
# 实测过的那几个值：白天粉面压近黑 rgb(222, 203, 232)（离 token #ffeaf3 差 33 个色阶）、
# 夜晚李面压近黑 rgb(34, 21, 47)、我们的画布 #ffeaf3 / #3a1b2c、夜晚墨 rgb(244, 234, 255)。
# 所以墨不算粉（244-234=10 < 12）、白不算粉（r-g=0）、紫渐变不是绿（哨兵那一趟它不动）。
def pinkish(p):
    r, g, b = p
    return min(r, g, b) >= 120 and r - g >= 12 and b - g >= 6


def plumish(p):
    r, g, b = p
    return max(r, g, b) <= 140 and b - g >= 12 and r - g >= 8


def darkish(p):
    return max(p[0], p[1], p[2]) < 80


def lightish(p):
    return min(p[0], p[1], p[2]) >= 150


def greenish(p):
    r, g, b = p
    return g >= 90 and g >= r + 20 and g >= b + 20


def ours(p, sent, want):
    """这一格是「我们画的那一族」：本档里落在粉／李那一族，且哨兵档同一坐标发绿。"""
    return (pinkish(p) if want == "pink" else plumish(p)) and greenish(sent)


def bands(path, sent_path, want):
    """返回 [(带起点 y, 我们那族份额, 反衬份额)]：反衬＝深那一族（want=pink 时）
    或浅那一族（want=plum 时），只数**哨兵档里不发绿**的格，也就是站家自己的底。"""
    from PIL import Image
    im = Image.open(path).convert("RGB")
    sm = Image.open(sent_path).convert("RGB")
    if im.size != sm.size:
        return None, f"两档尺寸不同（{im.size} vs {sm.size}）——坐标对不上，这一整对不判"
    w, h = im.size
    px, sx = im.load(), sm.load()
    ctx = darkish if want == "pink" else lightish
    out = []
    for y in range(0, h, BAND):
        hit = ctx_n = tot = 0
        for yy in range(y, min(h, y + BAND), YSTEP):
            for x in range(0, w, XSTEP):
                p, s = px[x, yy], sx[x, yy]
                tot += 1
                if ours(p, s, want):
                    hit += 1
                elif ctx(p) and not greenish(s):
                    ctx_n += 1
        if tot:
            out.append((y, hit / tot, ctx_n / tot))
    return out, None


def isolated(rows):
    """极大连续段（按"我们那族"的份额）＋两端的反衬够不够。
    返回 (孤立段 [(y起, y止, 最高份额)], 贴边没法判的段 [(同上三元组)])。
    贴边那一截不判红也不判绿：段一直延伸到画面外，画面里看不见它的另一侧是什么——
    可能是页尾往下接着铺我们自己的画布（不孤零零），也可能是贴着窗口顶的一条常驻板（孤零零）。
    这一格分不出来，所以点名报出来让人看，而不是悄悄记成一个数。"""
    runs, edge, i = [], [], 0
    while i < len(rows):
        if rows[i][1] < FIRE:
            i += 1
            continue
        j = i
        while j + 1 < len(rows) and rows[j + 1][1] >= FIRE:
            j += 1
        span = (rows[i][0], rows[j][0] + BAND,
                round(max(rows[q][1] for q in range(i, j + 1)), 3))
        if i < 2 or j > len(rows) - 3:
            edge.append(span)
        else:
            nb = [rows[q][1] for q in (i - 2, i - 1, j + 1, j + 2)]
            ct = [rows[q][2] for q in (i - 2, i - 1, j + 1, j + 2)]
            if (all(v < NEIGH for v in nb) and all(c >= CONTEXT for c in ct)
                    and j - i + 1 >= MIN_RUN):
                runs.append(span)
        i = j + 1
    return runs, edge


def fake_pair(tmp, tmp_sent, mid, sent_mid, dark_ctx=True):
    """120x120：上下 40 行是站家的底，中间 40 行是 `mid`（我们的那一族）。
    哨兵图同一坐标在中间那段发 `sent_mid`，其余按底原样。"""
    from PIL import Image
    base = (18, 16, 17) if dark_ctx else (250, 250, 250)
    im = Image.new("RGB", (120, 120), base)
    sm = Image.new("RGB", (120, 120), base)
    for y in range(40, 80):
        for x in range(120):
            im.putpixel((x, y), mid)
            sm.putpixel((x, y), sent_mid)
    im.save(tmp)
    sm.save(tmp_sent)


def selftest():
    GREEN = (0, 255, 0)
    cases = [
        ("白天正控制：暗底中间一条玻璃粉面（是我们的）",
         (222, 203, 232), GREEN, "pink", True),
        ("白天反面控制：同一条带换成站点自己涂的同族粉（哨兵里不发绿）",
         (222, 203, 232), (222, 203, 232), "pink", False),
        ("夜晚正控制：白底中间一条深李面（是我们的）",
         (67, 55, 80), GREEN, "plum", True),
        ("夜晚反面控制：同一条带换成站家的紫（哨兵里不动）",
         (43, 30, 76), (43, 30, 76), "plum", False),
    ]
    ok = True
    for i, (name, mid, sent_mid, want, should) in enumerate(cases):
        d, s = Path(f"/tmp/ks-hm-t{i}.png"), Path(f"/tmp/ks-hm-t{i}-sent.png")
        fake_pair(d, s, mid, sent_mid, dark_ctx=(want == "pink"))
        rows, err = bands(d, s, want)
        got = bool(isolated(rows)[0]) if rows else False
        ok = ok and got == should and err is None
        print(f"  {'√' if got == should else '×'} {name}：{'着火' if got else '不火'}"
              f"（要 {'着火' if should else '不火'}）")
    print("  读法：正控制不开火＝这条闸门永远绿，而它本该拦住的就是 2026-10-05 那一横；"
          "反面控制着火＝把站家自己涂的同族色也算成了我们的，哨兵那一趟没起作用")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    pairs = []
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    for f in sorted(glob.glob(str(ROOT / "shots" / "spot-*-day.png"))):
        pairs.append((Path(f), "pink"))
    for f in sorted(glob.glob(str(ROOT / "shots" / "spot-*-night.png"))):
        pairs.append((Path(f), "plum"))
    if args:
        # 点名要按图名的那一档来：写死 pink 会让夜晚档那张按白天的判据扫，
        # 深李那一族在粉判据下永远不火——这一把就成了假绿。
        pairs = [(Path(a), ("plum" if "-night" in Path(a).name else "pink")) for a in args]
    if not pairs:
        sys.exit("HARMONY ERROR: 一张图都没有——先跑 tools/spot-check.sh 出图。"
                 "「没对象」不许读成「没有不搭的色」")
    print(f"带 {BAND}px、纵向每 {YSTEP}px、横向每 {XSTEP}px；点火线 本段 ≥{FIRE:.0%}"
          f"（我们那一族）且段外两带各 <{NEIGH:.0%}、那两带的衬底 ≥{CONTEXT:.0%}、连续 ≥{MIN_RUN} 带；"
          "归属靠哨兵那一趟（发绿＝我们画的）")
    bad, skipped, edges = [], [], []
    for path, want in pairs:
        sent = Path(str(path).replace("-day.png", "-day-sent.png")
                    .replace("-night.png", "-night-sent.png"))
        if not sent.exists():
            skipped.append(f"{path.name}：没有 {sent.name}，这一对归不了因")
            continue
        rows, err = bands(path, sent, want)
        if err:
            skipped.append(f"{path.name}：{err}")
            continue
        runs, edge = isolated(rows)
        share = sum(r[1] for r in rows) / len(rows)
        ctx = sum(r[2] for r in rows) / len(rows)
        print(f"  {path.name:38} {len(rows):4} 带  我们那一族 {share:>4.0%} "
              f"｜反衬 {ctx:>4.0%}｜孤立段 {len(runs)}"
              + (f"  ⚠ {runs}" if runs else "")
              + (f"\n      贴边不判（画面里看不见另一侧）{len(edge)} 段：{edge}" if edge else ""))
        bad += [(path.name, r) for r in runs]
        # 贴边那几段也要进总数：PASS 那一行只说"不判的 0 对"会让人以为什么都没绕过去，
        # 而"对"（整对图没归成因）和"段"（一对图里贴边的那一截）是两个不同的单位——
        # 2026-10-05 实跑就撞在这个缝上：汇总印 0，图行下面却印着 1 段贴边不判。
        edges += [(path.name, e) for e in edge]
    for line in skipped:
        print(f"  ⚠ 不判：{line}")
    if edges:
        print("  贴边不判的段逐段点名（每段=(起行, 止行, 段内占比)）：" +
              "；".join(f"{n} {list(e)}" for n, e in edges))
    if bad:
        print(f"\nHARMONY FAIL：{len(bad)} 段「我们那一族孤零零立在站家的底中间」——"
              "这就是用户指着说「与整体不搭」的那一格")
        sys.exit(1)
    print(f"\nHARMONY PASS：{len(pairs) - len(skipped)} 对（白天＋夜晚各扫一遍）里"
          f"没有孤立段；整对不判的 {len(skipped)} 对已逐对点名，"
          f"段级贴边不判的 {len(edges)} 段已点名（单位不同：对＝一整对图，段＝一对图里贴那一屏边的那一截）")


main()
