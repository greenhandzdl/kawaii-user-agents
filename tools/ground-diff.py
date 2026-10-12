#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""无中生有的底：我们在一格"站点自己没涂底"的地方画上了面，这有多少平方像素？
（#97，2026-10-05）

为什么要这一本：runoob 的 <h2 class="tutheader"> 那一格是**肉眼看图**发现的（正文列里四块
838×44 的粉带，站点在那儿只写了字没排底）。现有尺子没人管这一形：
  - check-harmony 判的是「我们那一族孤零零立在**深色上下文**中间」，浅色页面上整页都浅，
    那条判据按构造不火——2026-10-05 用出厂图和摘掉标题排除那一版的配对图都跑过，两边各 0 段。
  - check-controls 的夹具只覆盖类名形状（词根命中哪一类元素），覆盖不到"这块底站点排没排过"。
  - glass-census 按 position 取对象，文档流里的标题块结构上读不到。
所以这一本问的是一个和上面三条都不重叠的问题：**把站点没涂底的地方算成我们的面积**。

读法（三档配对＋一张哨兵档归因，全是现成的产物）：
  候选 = 哨兵档发绿（那一格是我们画的）**且** 上肤档与裸页档在这格不同（我们动了它）。
  候选块按裸页档分成三堆，各印一个数：
    压在**整页纸底**上（块内 ≥FLAT_SHARE 的格落在裸页众数即纸底色 ±FLAT_TOL 内）＝无中生有
    平但不是纸底＝站点自己涂的一条实心带 → 我们的面压在别家东西上，那是另一格（衬底归因）
    不平＝那块本来有站点的图／渐变
  为什么判据钉的是「对纸底的份额」而不是「块内自己平不平」：写 --selftest 那一格手工图时才
  看清——站点自涂的一条纯灰带**同样**是平的，按份额判会把它算成无中生有，正好把这一本最该
  分开的两格并成一格。纸底由裸页档全图粗采样（每 4 格取 1）的众数给，块内只比它。
  贴字那一格：候选块里会有字的笔画（块内不平），所以量的是份额不是极值。

第一版自审抓到三处坏（都改了，也都由 --selftest 钉住方向）：逐通道取差误用 darker（给的是
最小值，「只有 g 通道差 21」那一形整片被读成没动过——正是我们的粉压在白纸上最常见的形状）；
块合并拿**起行**比相邻（一块起于 y=0 就能一路吃到页尾，坐标读数失真）；众数用 list.count
（大块是 O(唯一色×像素)，六站跑不动）。

这一本**只报不判**。2026-10-06 第一跑（出厂档六站 × 白天＋夜晚）的分布与三处污染，
阈值必须等这三处分得开之后再定，否则判红会打在已经定夺过的特性上：
  分布：孤岛份额 mdn 白天 0 格／夜晚 749 格，github-docs 夜晚 5,121 格（0.53%），
        github-features 两档各 ~26,500 格（2.8%），runoob 白天 4,451（0.46%）／夜晚 36,483（3.80%），
        w3schools 白天 30,942（3.22%）／夜晚 67,186（7.00%）。
  真站正控制拿到了：/tmp/ks-keep/shots-prefix（摘掉标题排除那一版，缺陷在场）里
        y=496–539 x=236–1068 那条 833×44 的带白天夜晚都判成孤岛（候选 10,698／18,400 格），
        出厂档里同一坐标一块都不剩——runoob 白天孤岛从 37,687 格掉到 4,451 格（8.5×）。
        这一格独立于 2026-10-05 那趟配对重出图，把 #96 的收成又量了一遍。
  污染一（墨 vs 面）：我们强制的那份墨本身也发绿、也压在纸底上，所以一处**文字**会被当成一块面
        ——runoob 白天 y=1095–1115、y=1476–1494 两块的上肤众数是 rgb(148,45,89)（我们的墨），
        不是面。分得开的那把尺是候选格在 bbox 里的密度，但密度在"面里有字"时不干净。
  污染二（已定夺的接管条）：页头那一条按形状就是孤岛（上下都是站家的底），github-features
        两档 y=61–100 整幅宽、25,600 格，就是 #94/#66 定夺过的那次接管；w3schools y=112–147 同理。
        画布接管那一格由 E 那条自证格钉住不判，**接管条那一格还没有对应的自证格**。
  污染三（发丝线）：1–3px 宽的线也会成为孤岛——runoob y=198–1331 x=208–210（3×1134，2,268 格）
        是一根竖线，不是一块面。
夜晚档系统性比白天档报得多（runoob 8×、w3schools 2×）：我们的深李压在这些浅站纸底上，
逐通道差更容易越过 DIFF_MIN，这是量出来的差别，不是两处都坏了。
"""
import sys
from collections import Counter
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
XSTEP, YSTEP = 2, 1
DIFF_MIN = 12          # 上肤档与裸页档逐通道最大差 ≥ 这个数才算"我们动了这格"
SENT_MIN_G = 90        # 哨兵发绿的三条判据（与 check-harmony 同一套值）
FLAT_TOL = 6           # 裸页那块算"平"的容差：众数色 ±FLAT_TOL 内算同一档
FLAT_SHARE = 0.6       # 块内 ≥ 这个比例的格落在整页纸底色上，才把这块算「压在纸底上」
RING = 6               # 孤岛判据：块外几像素那一圈
ISLAND_SHARE = 0.7     # 一圈里 ≥ 这个比例的格不是我们画的，才算孤岛（四周是站家的底）
MIN_BLOCK = 200        # 小于这个格数的碎块不印（一行里的字距、抗锯齿边）
MIN_THICK = 8          # 短边不到这个像素不算一块面：那是线（边框、分隔线）不是底
RUN_SHARE = 0.6        # 行内最长连续候选段／块宽的中位数：一整片面≈1，只有字的笔画≈0.02–0.4
TAKEOVER_W = 0.9       # 横向铺到画面两边（≥这个份额）…
TAKEOVER_H = 8         # …且高度不超过画面高的 1/8 → 页头接管条那一形（#94/#66 已定夺，不判）


def green_mask(im):
    """哨兵档里发绿的格＝那一格的色来自我们的 token（面、底或墨，都算我们画的）。"""
    r, g, b = im.split()
    ok_g = g.point(lambda v: 255 if v >= SENT_MIN_G else 0)
    ge_r = ImageChops.subtract(g, r).point(lambda v: 255 if v >= 20 else 0)
    ge_b = ImageChops.subtract(g, b).point(lambda v: 255 if v >= 20 else 0)
    return ImageChops.darker(ImageChops.darker(ok_g, ge_r), ge_b).convert("1")


def changed_mask(a, b, lo):
    """两档逐通道最大差 ≥ lo 的格。"""
    # 取的是逐通道绝对差的**最大值**，所以三通道要 lighter（逐位取大）而不是 darker：
    # 踩过的坑是这里误用 darker，它给的是最小值，于是"只有 g 通道差 13、r/b 差 3–4"
    # 那一形——正是我们的粉面压在白纸上最常见的形状——整片被算成"没动过"，普查会假绿。
    ra, ga, ba = ImageChops.difference(a.convert("RGB"), b.convert("RGB")).split()
    m = ImageChops.lighter(ImageChops.lighter(ra, ga), ba)
    return m.point(lambda v: 255 if v >= lo else 0).convert("1")


def blocks(cand, w, h):
    """把候选掩膜按行合并成块：相邻行且 x 区间重叠过半算同一块。返回 [(y0,y1,x0,x1,格数)]。"""
    # 必须先 convert("L")：mode "1" 的 tobytes() 是**按位打包**的，一行 w 个像素只占 w/8 字节，
    # 拿 x 当字节索引读的是隔壁行的位。真站 1280 宽时它不报错、只静默给一张错的掩膜——
    # 是 200×100 的手工图把它崩出来的（IndexError），所以这本的自证格走在真站读数之前。
    dat = cand.convert("L").tobytes()
    rows = []
    for y in range(0, h, YSTEP):
        base = y * w
        xs = [x for x in range(0, w, XSTEP) if dat[base + x]]
        if not xs:
            continue
        # 同一行里断开的段拆成多条（列与列之间隔着别家底时不该并成一块）
        start = xs[0]
        prev = xs[0]
        for x in xs[1:]:
            if x - prev > XSTEP * 3:
                rows.append((y, start, prev))
                start = x
            prev = x
        rows.append((y, start, prev))
    out = []
    # 块记录＝[起行, 末行, x0, x1, 格数]。合并只认「末行的下一行」：第一版拿**起行**比，
    # 一个块一旦起于 y=0 就永远匹配得上下面的行，整页并成一块、坐标读数为零。
    for y, x0, x1 in rows:
        span = 1 + (x1 - x0) // XSTEP
        for b in out:
            if b[1] == y - YSTEP and min(b[3], x1) - max(b[2], x0) >= 0.5 * (x1 - x0):
                b[1] = y
                b[2] = min(b[2], x0)
                b[3] = max(b[3], x1)
                b[4] += span
                break
        else:
            out.append([y, y, x0, x1, span])
    return [(b[0], b[1], b[2], b[3], b[4]) for b in out if b[4] >= MIN_BLOCK]


def classify(blk, bare, day, sent, canvas):
    """块内：候选格数、裸页众数色与其邻域份额、对**整页纸底**的份额、上肤档的众数色、哨兵发绿份额。"""
    y0, y1, x0, x1, _n = blk
    crop_b = bare.convert("RGB").crop((x0, y0, x1 + 1, y1 + 1))
    crop_d = day.convert("RGB").crop((x0, y0, x1 + 1, y1 + 1))
    crop_s = sent.convert("RGB").crop((x0, y0, x1 + 1, y1 + 1))
    bd, dd, sd = list(crop_b.getdata()), list(crop_d.getdata()), list(crop_s.getdata())
    tot = len(bd)
    cb = Counter(bd)
    mode_b, _n_b = cb.most_common(1)[0]
    flat = sum(n for p, n in cb.items()
               if all(abs(p[i] - mode_b[i]) <= FLAT_TOL for i in range(3)))
    on_canvas = sum(n for p, n in cb.items()
                    if all(abs(p[i] - canvas[i]) <= FLAT_TOL for i in range(3)))
    mode_d = Counter(dd).most_common(1)[0][0]
    green = sum(1 for p in sd if p[1] >= SENT_MIN_G and p[1] >= p[0] + 20 and p[1] >= p[2] + 20)
    return {"bare_mode": mode_b, "bare_flat": flat / tot, "on_canvas": on_canvas / tot,
            "day_mode": mode_d, "sent_green": green / tot, "px": tot}


def canvas_color(bare, w, h):
    """整页纸底＝裸页档里最粗采样那一趟的众数色（站点没排底的地方就是它）。"""
    px = bare.convert("RGB").load()
    c = Counter(px[x, y] for y in range(0, h, 4) for x in range(0, w, 4))
    return c.most_common(1)[0][0]


def island_share(cand_px, blk, w, h):
    """块外一圈里「不是我们画的」占多少。孤岛＝我们在一块站家底中间画了一小块（runoob 那一格）。
    整幅被我们接管（画布那一格，已定夺的特性）时这一圈也全是我们的，份额低 → 不判孤岛。
    为什么非加这一列不可：只比「块内裸页＝纸底」时，六站第一跑把 mdn 读成 111%、
    github-docs 读成 36%——那两处量的其实是画布接管和「站点自己那块黑／深底就是众数纸底」，
    不是我们无中生有画的那一块。加上四周的归属，两格才分得开。"""
    y0, y1, x0, x1, _n = blk
    ring = []
    for y in ({max(0, y0 - RING), min(h - 1, y1 + RING)}):
        ring += [(x, y) for x in range(x0, x1 + 1, XSTEP)]
    for x in ({max(0, x0 - RING), min(w - 1, x1 + RING)}):
        ring += [(x, y) for y in range(y0, y1 + 1, YSTEP)]
    return sum(1 for p in ring if not cand_px[p]) / len(ring)


def run_share(cand_px, blk, w):
    """行内最长连续候选段／块宽，取有候选那些行的中位数。一整片面≈1（面自己连续）；
    只有字的笔画时那一行的最长段就是一个字宽 → 很小。为什么不看候选格密度：面里也常有字，
    密度那把尺把"面＋字"和"只有字"混在一起（runoob 那两处墨的密度 39%，同批一条真面 58%）。"""
    y0, y1, x0, x1, _n = blk
    cells_w = (x1 - x0) // XSTEP + 1
    best_rows = []
    for y in range(y0, y1 + 1):
        cur = top = 0
        for x in range(x0, x1 + 1, XSTEP):
            if cand_px[x, y]:
                cur += 1
                top = max(top, cur)
            else:
                cur = 0
        if top:
            best_rows.append(top)
    if not best_rows:
        return 0.0
    best_rows.sort()
    return best_rows[len(best_rows) // 2] / cells_w


def shape_of(blk, cls, isl, run, w, h):
    """这一块像什么。只有一支是缺陷候选，其余每一支都点名为什么不判——
    判错的代价比不判大：把已定夺的接管、把我们的墨、把一根边框线算成"无中生有的一块底"，
    红就红在错的地方，行为那一轮根本没说话。"""
    y0, y1, x0, x1, _n = blk
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    if cls["on_canvas"] < FLAT_SHARE:
        return "站家底", "裸页那块不是整页纸底（我们的面压在站点自己涂的底上，那是衬底那一格）"
    if isl < ISLAND_SHARE:
        return "自家片", f"四周 {1 - isl:.0%} 还是我们自己的面（画布接管那一格）"
    if bw >= TAKEOVER_W * w and bh <= h // TAKEOVER_H:
        return "接管条", f"横铺 {bw}px＝整幅的 {bw / w:.0%}、竖 {bh}px：页头接管条那一形（#94/#66 定夺过）"
    if min(bw, bh) < MIN_THICK:
        return "线", f"短边 {min(bw, bh)}px：那是一根线（边框／分隔线），不是一块底"
    if run < RUN_SHARE:
        return "墨", f"行内最长连续段只占块宽 {run:.0%}：那是字的笔画，不是一整片面"
    return "面", f"{bw}×{bh} 的一整片压在站家的纸底上，四周是站家的底"


def analyze(day, sent, bare, w, h):
    """三档配对 → (纸底色, [(块, 分类, 孤岛份额, 行连续份额, 形状, 为什么不判)])。"""
    g = green_mask(sent)
    ch = changed_mask(day, bare, DIFF_MIN)
    cand = ImageChops.darker(g.convert("L"), ch.convert("L")).convert("1")
    px = cand.convert("L").load()
    cvs = canvas_color(bare, w, h)
    out = []
    for b in blocks(cand, w, h):
        cls = classify(b, bare, day, sent, cvs)
        isl = island_share(px, b, w, h)
        run = run_share(px, b, w)
        kind, why = shape_of(b, cls, isl, run, w, h)
        out.append((b, cls, isl, run, kind, why))
    return cvs, out


def report(tag, band, shot):
    p_day = shot / f"spot-{tag}-{band}.png"
    p_sent = shot / f"spot-{tag}-{band}-sent.png"
    p_bare = shot / f"spot-{tag}-bare.png"
    for p in (p_day, p_sent, p_bare):
        if not p.exists():
            print(f"  跳过 {tag}/{band}：缺 {p.name}")
            return 0, 0, 0
    day, sent, bare = (Image.open(p_day), Image.open(p_sent), Image.open(p_bare))
    if not (day.size == sent.size == bare.size):
        print(f"  跳过 {tag}/{band}：三档尺寸不同（{day.size}／{sent.size}／{bare.size}），坐标对不上")
        return 0, 0, 0
    w, h = day.size
    cvs, rows = analyze(day, sent, bare, w, h)
    by = {}
    for r in rows:
        by.setdefault(r[4], []).append(r)
    cells_all = len(range(0, w, XSTEP)) * len(range(0, h, YSTEP))
    face = by.get("面", [])
    n_face = sum(r[0][4] for r in face)
    print(f"  {tag:20} {band:5} 纸底 rgb{cvs}｜候选 {len(rows):3} 块"
          f"｜**面形（缺陷候选）{len(face):2} 块 / {n_face:7,} 格 = 整幅 {n_face / cells_all:5.2%}**"
          f"｜不判的：站家底 {len(by.get('站家底', [])):2}、自家片 {len(by.get('自家片', [])):2}、"
          f"接管条 {len(by.get('接管条', [])):2}、线 {len(by.get('线', [])):2}、墨 {len(by.get('墨', [])):2}")
    for b, c, i, rn, _k, _why in face[:5]:
        y0, y1, x0, x1, n = b
        print(f"      面 y={y0}–{y1} x={x0}–{x1}（{x1 - x0 + 1}×{y1 - y0 + 1}，候选 {n:,} 格）"
              f" 裸页 rgb{c['bare_mode']}｜上肤 rgb{c['day_mode']}｜哨兵绿 {c['sent_green']:.0%}"
              f"｜四周非我们 {i:.0%}｜行连续 {rn:.0%}")
    if len(face) > 5:
        print(f"      …另有 {len(face) - 5} 块面形（放宽 MIN_BLOCK 可全列）")
    for kind in ("站家底", "自家片", "接管条", "线", "墨"):
        if by.get(kind):
            b, c, i, rn, _k, why = max(by[kind], key=lambda r: r[0][4])
            print(f"      不判[{kind}] 最大一块 y={b[0]}–{b[1]} x={b[2]}–{b[3]}"
                  f"（候选 {b[4]:,} 格，上肤 rgb{c['day_mode']}）：{why}")
    return len(face), n_face, len(rows)


def selftest():
    """手工定七条形，每形一条自证格，不开浏览器：量的是这把尺子把「面」从
    「墨／线／接管条／自家片／站家底」里分得开开不了。每一形都点名它为什么不判成缺陷——
    判错的代价比不判大：把已定夺的接管、把我们的墨、把一根边框线算成"无中生有的一块底"，
    红就红在错的地方，行为那一轮根本没说话。第一版自审抓到的三处坏（逐通道取小、
    块合并比起行、mode "1" 按位打包）也分别由 A、A2、候选块数这三条举住。"""
    W, H = 200, 300
    WHITE, GREEN = (255, 255, 255), (39, 240, 43)
    bare = Image.new("RGB", (W, H), WHITE)
    skin = Image.new("RGB", (W, H), WHITE)
    sent = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(bare)
    d.rectangle((20, 50, 180, 59), fill=(240, 240, 240))    # 站家自涂的一条平底
    d.rectangle((20, 70, 180, 79), fill=(200, 200, 200))    # 站家自己变的灰（不是我们画的）
    ds = ImageDraw.Draw(skin)
    dn = ImageDraw.Draw(sent)
    for y0 in (10, 30):     # A、A2：一整片粉压在纸底上，四周是站家的纸底，与裸页只差 g/b 通道
        ds.rectangle((20, y0, 180, y0 + 9), fill=(254, 234, 243))
        dn.rectangle((20, y0, 180, y0 + 9), fill=GREEN)
    ds.rectangle((20, 50, 180, 59), fill=(251, 225, 238))   # B：压在站家平底上的粉
    dn.rectangle((20, 50, 180, 59), fill=GREEN)
    ds.rectangle((20, 70, 180, 79), fill=(120, 120, 120))   # D：变了但哨兵不发绿
    for bx in range(20, 181, 6):    # F：只有字的笔画——一道一道竖笔，行内不连续
        ds.rectangle((bx, 110, bx + 1, 124), fill=(148, 45, 89))
        dn.rectangle((bx, 110, bx + 1, 124), fill=GREEN)
    ds.rectangle((0, 150, W - 1, 159), fill=(51, 35, 65))   # T：横铺整幅的一条＝页头接管条那一形
    dn.rectangle((0, 150, W - 1, 159), fill=GREEN)
    ds.rectangle((20, 200, 26, 283), fill=(252, 233, 243))  # L：7px 宽的一根竖线
    dn.rectangle((20, 200, 26, 283), fill=GREEN)
    ds.rectangle((0, 284, W - 1, H - 1), fill=(254, 234, 243))   # E：铺到画面底边、四周仍是我们自己
    dn.rectangle((0, 284, W - 1, H - 1), fill=GREEN)
    cvs, rows = analyze(skin, sent, bare, W, H)
    kinds = {}
    for r in rows:
        kinds[r[4]] = kinds.get(r[4], 0) + 1
    faces = [(r[0][0], r[0][1]) for r in rows if r[4] == "面"]
    why = {r[4]: r[5] for r in rows}
    checks = [
        ("纸底读成白", cvs == WHITE),
        ("候选块＝7（A A2 B F T L E；站家自己变灰那条 D 没进来）", len(rows) == 7),
        ("七形各归各的：面2 站家底1 墨1 接管条1 线1 自家片1",
         kinds == {"面": 2, "站家底": 1, "墨": 1, "接管条": 1, "线": 1, "自家片": 1}),
        ("判成缺陷候选的就是 A、A2 那两条，别的形式都不算", faces == [(10, 19), (30, 39)]),
        ("A 与 A2 没被并成一个（块合并拿末行比相邻，不是起行）", len(faces) == 2),
        ("墨那一形点名「字的笔画」", "字的笔画" in why.get("墨", "")),
        ("线那一形点名「短边」", "短边" in why.get("线", "")),
        ("接管条那一形点名「页头接管条」", "页头接管条" in why.get("接管条", "")),
        ("自家片那一形点名「画布接管」", "画布接管" in why.get("自家片", "")),
        ("站家底那一形点名「站点自己涂的底」", "站点自己涂的底" in why.get("站家底", "")),
    ]
    bad = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'√' if ok else '×'} {name}")
    if bad:
        print(f"\nGROUND SELFTEST FAIL：{len(bad)}/{len(checks)} 格坏——尺子本身不可信，"
              f"真站读数先别用（坏的格：{'；'.join(bad)}）")
        return 1
    print(f"\nGROUND SELFTEST PASS：{len(checks)}/{len(checks)} 格各钉住一形的分派"
          f"（正控制＝A 那条只差 g/b 通道、四周是纸底、行内连续的一整片；"
          f"负控制＝D 站家自己变灰、B 站家平底、F 墨、L 线、T 接管条、E 自家片）")
    return 0


def main():
    argv = sys.argv[1:]
    if "--selftest" in argv:
        sys.exit(selftest())
    shot = ROOT / "shots"
    if "--shots" in argv:
        i = argv.index("--shots")
        if i + 1 >= len(argv):
            sys.exit("GROUND ERROR: --shots 后面要跟一个目录")
        shot = Path(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    tags = argv
    if not tags:
        tags = sorted({p.name[len("spot-"):-len("-day.png")]
                       for p in shot.glob("spot-*-day.png")})
    if not tags:
        sys.exit(f"GROUND ERROR: {shot} 里一张白天档都没有——先跑 tools/spot-check.sh")
    print(f"读法：候选＝哨兵发绿 ∧ 与裸页逐通道最大差 ≥{DIFF_MIN}（碎块线 {MIN_BLOCK} 格）；"
          f"「面形＝缺陷候选」要四把尺同时过——①块内 ≥{FLAT_SHARE:.0%} 的格落在整页纸底色 ±{FLAT_TOL} "
          f"（我们的面压在站家纸底上，不是压在站点自己涂的底上）；②块外 {RING}px 一圈 ≥{ISLAND_SHARE:.0%} "
          f"的格不是我们画的（不是画布接管那一格）；③短边 ≥{MIN_THICK}px 且行内最长连续 ≥{RUN_SHARE:.0%} "
          f"块宽（不是线、不是字的笔画）；④不是通宽 ≥{TAKEOVER_W:.0%} 的窄条（页头接管条那一形）。"
          f"其余各形只报不判（{shot}）")
    tot_face = tot_cells = tot_cand = 0
    pairs_ok, missing = 0, []
    for tag in tags:
        for band in ("day", "night"):
            need = (shot / f"spot-{tag}-bare.png", shot / f"spot-{tag}-{band}.png",
                    shot / f"spot-{tag}-{band}-sent.png")
            gone = [p.name for p in need if not p.exists()]
            if gone:
                missing.append(f"{tag}-{band} 缺 {'、'.join(gone)}")
                continue
            a, b, c = report(tag, band, shot)
            pairs_ok += 1
            tot_face += a
            tot_cells += b
            tot_cand += c
    print(f"\n合计 面形（缺陷候选）{tot_face} 块 / {tot_cells:,} 格｜全部候选 {tot_cand:,} 块"
          f"｜覆盖 {pairs_ok}/{len(tags) * 2} 档（{len(tags)} 站 × 白天＋夜晚）——这是分布，不是判定")
    # 覆盖那一格必须自己报：tags 是从 spot-*-day.png 反解出来的，所以一站只有白天档时它照样数进
    # "N 站"。2026-10-06 就是这么读的——mdn 与 w3schools 夜晚档连拍六张定不下来，spot-check 回了
    # rc=1，而这一把尺子把 4/6 站的名册报成 "6 站 × 白天＋夜晚" 的 17 块/30,868 格，还回了 rc=0。
    # 缺档不是"没有缺陷"，是没量，所以退出码非零，且合计行不再声称扫了各一遍。
    if missing:
        print(f"GROUND INCOMPLETE：{len(missing)} 档没配上图，合计里没数它们，"
              f"别拿这一行去和全档基线比：{'；'.join(missing)}")
        return 1
    return 0


sys.exit(main())
