#!/usr/bin/env python3
"""像素级断言：证明明暗两档真的画出了不同的图、暗色站点默认不被涂成粉白、
撞色底上的字被光晕垫得读得动、模态遮罩压住了弹窗外面而没压住弹窗自己、
裸表的斑马纹在两档里都交替、1500 以下那三块页尾也跟着翻了档并且读得动、
浮层玻璃按 CSS 里那一成透出底下的内容且没把字吃掉。

只看字节数或"文件非空"都不算证据，这里直接采样像素；取样坐标一律来自
shoot.sh 里那趟几何探针（preview/.build/geometry.txt），不在脚本里猜 y。
"""
import importlib.util
import re
import sys
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "shots"
CSS = ROOT / "kawaii-skin.user.css"


def patch(img, box):
    """取一块区域的中位色，避开单点被文字/边缘污染。"""
    rgb = img.convert("RGB")
    blob = rgb.crop(box).tobytes()
    n = len(blob) // 3
    chans = [sorted(blob[i::3]) for i in range(3)]
    return tuple(ch[n // 2] for ch in chans)


def lum(rgb):
    def chan(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (chan(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    """WCAG 2.x 亮度比，1..21。"""
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def load(name):
    p = SHOTS / name
    if not p.exists():
        sys.exit(f"DIFF ERROR: 缺图 {name}")
    return Image.open(p)


NAV = (600, 6, 720, 26)          # 页首导航条空白处：吃到的是页面底衬
fails = []

day, night = load("01-components-day.png"), load("02-components-night.png")
c_day, c_night = patch(day, NAV), patch(night, NAV)
print(f"底衬采样  白天档 {c_day} (L={lum(c_day):.3f})   夜晚档 {c_night} (L={lum(c_night):.3f})")

if lum(c_day) < lum(c_night):
    fails.append(f"白天档比夜晚档还暗：{lum(c_day):.3f} < {lum(c_night):.3f}，light-dark() 没翻分支")
if abs(lum(c_day) - lum(c_night)) < 0.15:
    fails.append(f"明暗两档亮度差只有 {abs(lum(c_day)-lum(c_night)):.3f}，注入没生效")
if not (c_day[0] > c_day[1] and c_night[2] > c_night[0]):
    fails.append(f"色相不对：白天应偏粉(R>G) {c_day}，夜晚应偏紫(B>R) {c_night}")

diff = sum(abs(a - b) for a, b in zip(c_day, c_night))
print(f"两档采样差 {diff}（阈值 60）")
if diff < 60:
    fails.append("明暗档像素差过小，等于没换主题")

# 花瓣圆点：圆点画在 html::before 这层固定铺满视口的胶片上，位置完全由
# CSS 里的 `circle at X% Y%` 和 `background-size` 决定。所以这里不猜"哪块是空白"
# （那样采到的是文字），而是照着 CSS 算出每个圆点的圆心，去圆心取样，
# 再拿半周期处的对照点和整体平移 40px 的负控制点各比一次。
def film_layers():
    """从 CSS 里解出圆点层的 (圆心x%, 圆心y%, 周期px)，顺序不写死。"""
    src = CSS.read_text(encoding="utf-8")
    blocks = [b for b in re.findall(r"html::before \{([^}]*)\}", src, re.S)
              if 'content: ""' in b]
    if len(blocks) != 1:
        sys.exit(f"DIFF ERROR: 期望恰好 1 个画胶片的 html::before 块，实际 {len(blocks)}")
    film = blocks[0]
    if "position: fixed" not in film or "inset: 0" not in film:
        sys.exit("DIFF ERROR: 胶片不再是 fixed + inset:0，铺满视口的取样假设不成立")
    dots = [(float(a), float(b)) for a, b in
            re.findall(r"radial-gradient\(circle at ([\d.]+)% ([\d.]+)%", film)]
    sizes = re.search(r"background-size:\s*([^;]+);", film)
    if not sizes:
        sys.exit("DIFF ERROR: 胶片没有 background-size，圆心落点无从计算")
    entries = [e.strip() for e in sizes.group(1).split(",")]
    if entries[0] != "auto" or len(entries) - 1 != len(dots):
        sys.exit(f"DIFF ERROR: background-size {entries} 和 {len(dots)} 个 radial 对不上")
    periods = []
    for e in entries[1:]:
        nums = re.findall(r"([\d.]+)px", e)
        if len(nums) != 2 or nums[0] != nums[1]:
            sys.exit(f"DIFF ERROR: 圆点层尺寸 {e!r} 不是正方形的 px 周期，取样公式要重写")
        periods.append(float(nums[0]))
    return list(zip(dots, periods))


def sample(img, cx, cy, r=3):
    """一小块的中位 G 和中位 (R-G)；中位数让偶发的文字边不至于污染取样。"""
    W, H = img.size
    box = [img.getpixel((cx + dx, cy + dy))
           for dx in range(-r, r + 1) for dy in range(-r, r + 1)
           if 0 <= cx + dx < W and 0 <= cy + dy < H]
    g = sorted(c[1] for c in box)[len(box) // 2]
    rg = sorted(c[0] - c[1] for c in box)[len(box) // 2]
    return g, rg


def dot_stat(img, layers, ox=0, oy=0):
    """返回 (对数, 命中数, G 落差中位, R-G 抬升中位)。命中＝圆心比对照点暗 ≥6 级。"""
    W, H = img.size
    drops, lifts, hits, pairs = [], [], 0, 0
    for (fx, fy), per in layers:
        bx, by = round(fx / 100 * per) + ox, round(fy / 100 * per) + oy
        half = round(per / 2)
        m = 0
        while by + m * per + half < H:
            k = 0
            while bx + k * per + half < W:
                x, y = bx + k * per, by + m * per
                g0, r0 = sample(img, x, y)
                g1, r1 = sample(img, (x + half) % W, (y + half) % H)
                drops.append(g1 - g0)
                lifts.append(r0 - r1)
                pairs += 1
                if g1 - g0 >= 6:
                    hits += 1
                k += 1
            m += 1
    drops.sort()
    lifts.sort()
    return pairs, hits, drops[len(drops) // 2], lifts[len(lifts) // 2]


LAYERS = film_layers()
geom = "、".join(f"周期 {p:g}px 圆心 {fx:g}%/{fy:g}%" for (fx, fy), p in LAYERS)
print(f"圆点层    从 CSS 解出 {len(LAYERS)} 层：{geom}")
if len(LAYERS) < 2:
    fails.append("圆点层少于 2 层，取样面太窄，这个断言撑不起'花瓣画出来了'")

pairs, hits, drop, lift = dot_stat(day, LAYERS)
rate = hits / pairs if pairs else 0.0
print(f"花瓣圆点  圆心取样 {hits}/{pairs} 命中（{rate:.0%}），G 落差中位 {drop}，R-G 抬升中位 {lift}")
if pairs < 12:
    fails.append(f"圆心取样只有 {pairs} 对，视口/周期对不上，没法判定")
if rate < 0.75:
    fails.append(f"圆点几乎看不见：只有 {rate:.0%} 的预测圆心处 G 明显偏低")
if drop < 6:
    fails.append(f"圆点处 G 落差中位只有 {drop}，等于没画")

# 负控制：整张网点平移 40px 后就不该再踩着圆点，命中率必须掉下来越低越好。
# 这条是防"数到的其实是页面自带的纹理/边框"——真掉不下去说明取样本身在蒙。
cpairs, chits, cdrop, _ = dot_stat(day, LAYERS, ox=40, oy=40)
crate = chits / cpairs if cpairs else 0.0
print(f"负控制    平移 40px 后 {chits}/{cpairs} 命中（{crate:.0%}），G 落差中位 {cdrop}")
if crate > 0.25:
    fails.append(f"负控制没掉下去：平移后仍 {crate:.0%} 命中，测到的不是圆点网格")
if cdrop >= drop:
    fails.append(f"平移处的落差 {cdrop} ≥ 圆心处 {drop}，圆点位置算错了")

# 暗色站点：默认必须仍然是暗的
ds = patch(load("03-darksite-day.png"), NAV)
print(f"暗色站点默认  {ds} (L={lum(ds):.3f})")
if lum(ds) > 0.12:
    fails.append(f"暗色站点被顶成亮底了：L={lum(ds):.3f}，保守层失效")

# 打开强涂后：同一个位置必须变成粉白
pt = patch(load("04-darksite-paint-on.png"), NAV)
print(f"暗色站点强涂开 {pt} (L={lum(pt):.3f})")
if lum(pt) < 0.55:
    fails.append(f"强涂档没盖住站点底色：L={lum(pt):.3f}，--kPaint 是空转")

# 糖果滚动条那一格排在几何读数落定之后：它的期望长度要按"视口×视口/内容高"现推，
# 而内容高来自 geometry.txt（账写在下面那一节的开头，标题是"糖果滚动条"）。
# ---------- 撞色站点上的标题：光晕有没有把笔画垫出来 ----------
# 为什么只能靠光晕：白底要深字、深底要浅字，两个可行区间在亮度轴上不相交
# （对 L≈0.93 和 L≈0.02 各要 ≥4.5 倍，解出来 L≤0.168 与 L≥0.265 互相矛盾），
# 所以"一个颜色同时读得过两种底"在数学上不存在。样式表又读不到站点自己涂的块，
# 于是给标题描一圈"我们以为的底色"：同色时它落在底色上看不见，撞色时它把笔画垫出来。
# 两个方向都要判：站点自涂深底 + 我们白天档，和站点自涂白底 + 我们夜晚档
# （后者更常见——绝大多数站点默认白底，用户一强制粉紫就撞上）。
# 链接不吃这团模糊，那是量出来的不是猜的：16px 的中文笔画只有 1–2px 宽，光晕会渗进
# 笔画自己（同一行字的中位亮度 0.067→0.157，局部对比 1.75→1.40，越垫越糊）。链接要的
# 依托是另一形——零半径的四枚 1px 硬边；本闸门只判方向：链接行开档不许比关档差。
def candy_ink(img):
    """糖色笔画像素：返回 (集合, 按行归好的 x 列表)。

    谓词：G 是三通道里最小的那个，且够艳（max-min>60）。
    白天档我们的字是 #8c1f4d 这类品红、夜晚档是 #eab6ff 这类淡紫，两者都 G 最小；
    站点的黑字白字 R≈G≈B 不过，站点蓝链接 #0b5cad（最小的是 R）也不过。
    站点代码块自己写的淡紫（#c9f、#6b2fa0）会过谓词，但它们只占一行 16px 高的带，
    被下面"标题带 ≥24px"那条几何判据挡在外面——颜色分不开时用带高分。
    右缘 16px 不参与：01 那张的糖果滚动条也是糖色，会占掉一整条高带。
    """
    rgb = img.convert("RGB")
    W, H = rgb.size
    data = rgb.tobytes()
    ink, by_row = set(), {}
    for y in range(H):
        base = y * W * 3
        xs = []
        for x in range(0, W - 16):
            i = base + x * 3
            r, g, b = data[i], data[i + 1], data[i + 2]
            if g < r and g < b and max(r, g, b) - min(r, g, b) > 60:
                ink.add((x, y))
                xs.append(x)
        if xs:
            by_row[y] = xs
    return ink, by_row


def row_bands(by_row):
    """把有笔画的行切成带：连续行归一带，断 5 行以上算换带。"""
    ys = sorted(by_row)
    out, start = [], ys[0]
    for prev, y in zip(ys, ys[1:] + [ys[-1] + 99]):
        if y - prev > 5:
            out.append((start, prev))
            start = y
    return out


RING_HI = 2  # 贴着笔画的那一圈：光晕真正落点
FAR_LO, FAR_HI = 15, 26   # 离字 15px 开外才算站点没被我们碰到的底（最外一层模糊 18px）


def merge_iv(pairs):
    out = []
    for a, b in sorted(pairs):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def dilate(by_row, k, xcap, y0, y1):
    """带内笔画的切比雪夫 k 邻域，按行返回合并好的区间。

    两趟一维合并（先横后纵）。上一版对每一行重排三万多个区间，闸门从 2 秒跑到两分钟。
    """
    rows = {y: merge_iv([(max(0, x - k), min(xcap, x + k)) for x in xs])
            for y, xs in by_row.items() if y0 - k <= y <= y1 + k}
    return {y: merge_iv([iv for yy in range(max(0, y - k), min(y1 + k + 1, y + k + 1))
                         for iv in rows.get(yy, ())])
            for y in range(max(0, y0 - k), y1 + k + 1)}


def ring_pixels(by_row, ink, band, lo, hi, xcap, at):
    """离任何笔画恰好 lo..hi 像素、本身又不是笔画的取样。"""
    y0, y1 = band
    Dlo = dilate(by_row, lo - 1, xcap, y0, y1) if lo > 1 else {}
    out = []
    for y, ivs in dilate(by_row, hi, xcap, y0, y1).items():
        blocked = set()
        for a, b in Dlo.get(y, ()):
            blocked.update(range(a, b + 1))
        for a, b in ivs:
            for x in range(a, b + 1):
                if x not in blocked and (x, y) not in ink:
                    out.append(at(x, y))
    return out


def pct(vals, f):
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(len(vals) * f))]


def band_read(img, ink, by_row, band):
    """一行带的三块取样：笔画核心、贴边那一圈、远处的底，外加两个对比度和一个分离度。

    cr＝字对贴边，是人眼实际看到的"字压在哪块上"；cf＝字对站点的底，光晕不改这条，
    所以它一直在打印里露着，不拿 cr 冒充它。
    """
    rgb = img.convert("RGB")
    W, H = rgb.size
    data = rgb.tobytes()

    def at(x, y):
        i = (y * W + x) * 3
        return (data[i], data[i + 1], data[i + 2])

    y0, y1 = band
    xcap = W - 16
    core_px = [p for p in ink if y0 <= p[1] <= y1]
    ring = ring_pixels(by_row, ink, band, 1, RING_HI, xcap, at)
    far = ring_pixels(by_row, ink, band, FAR_LO, FAR_HI, xcap, at)
    if len(core_px) < 200 or len(ring) < 500 or len(far) < 500:
        sys.exit(f"DIFF ERROR: 带 {band} 取样不够（笔画 {len(core_px)}、"
                 f"贴边 {len(ring)}、远处 {len(far)}），这具夹具撑不起这条判据")
    core = pct([at(*p) for p in core_px], 0.10)
    rm = pct(ring, 0.50)
    box = pct(far, 0.50)
    return dict(n=len(core_px), core=core, ring=rm, box=box,
                cf=contrast(core, box), cr=contrast(core, rm), sep=sep(rm, box))


def sep(a, b):
    """两个色的亮度分离度，方向无关——白天档把贴边提亮、夜晚档压暗都算。"""
    la, lb = lum(a) + 0.005, lum(b) + 0.005
    return max(la, lb) / min(la, lb)


# ---------- 撞色站点上的标题：光晕有没有把笔画垫出来 ----------
# 为什么只能靠光晕：白底要深字、深底要浅字，两个可行区间在亮度轴上不相交
# （对 L≈0.93 和 L≈0.02 各要 ≥4.5 倍，解出来 L≤0.168 与 L≥0.265 互相矛盾），
# 所以"一个颜色同时读得过两种底"在数学上不存在。样式表又读不到站点自己涂的块，
# 于是给标题描一圈"我们以为的底色"：同色时它落在底色上看不见，撞色时它把笔画垫出来。
# 两个方向都要判：站点自涂深底 + 我们白天档，和站点自涂白底 + 我们夜晚档
# （后者更常见——绝大多数站点默认白底，用户一强制粉紫就撞上）。
# 判据全是成对的：同一具夹具、同一个量法，只差 --kHalo:0 一个变量。光晕若写成常开，
# 面板那一档就是装饰，所以"开档垫得起来、关档垫不起来"两条必须各自开火。
# 链接不吃这团模糊，那是量出来的不是猜的：16px 的中文笔画只有 1–2px 宽，光晕会渗进
# 笔画自己（同一行字的中位亮度 0.067→0.157，局部对比 1.75→1.40，越垫越糊）。链接要的
# 依托是零半径那四枚 1px 硬边（check-controls.py 钉着，K46/K47/K48 有刀）；这里只判方向。
CLASH = (("白天档×站点自涂深底", "03-darksite-day.png", "06-darksite-halo-off.png"),
         ("夜晚档×站点自涂白底", "07-lightsite-night.png", "08-lightsite-halo-off.png"))
for label, on_name, off_name in CLASH:
    on_img, off_img = load(on_name), load(off_name)
    on_ink, on_rows = candy_ink(on_img)
    off_ink, off_rows = candy_ink(off_img)
    heads = [b for b in row_bands(on_rows) if b[1] - b[0] + 1 >= 24]
    smalls = [b for b in row_bands(on_rows) if 10 <= b[1] - b[0] + 1 <= 18]
    off_heads = [b for b in row_bands(off_rows) if b[1] - b[0] + 1 >= 24]
    off_smalls = [b for b in row_bands(off_rows) if 10 <= b[1] - b[0] + 1 <= 18]
    if not (heads and smalls and off_heads and off_smalls):
        sys.exit(f"DIFF ERROR: {on_name}/{off_name} 切不出标题带或小字带，"
                 f"带高依次为 {[b[1] - b[0] + 1 for b in row_bands(on_rows)]}")
    # 带号不逐字相同：光晕会让边缘像素跨过颜色谓词，开档的带比关档宽两三个像素。
    # 配对按带中心对齐，容差 4px——再大就不是同一行字了。
    mid = lambda b: (b[0] + b[1]) / 2
    if abs(mid(heads[0]) - mid(off_heads[0])) > 4 or abs(mid(smalls[0]) - mid(off_smalls[0])) > 4:
        sys.exit(f"DIFF ERROR: {on_name} 与 {off_name} 行带对不上"
                 f"（标题 {heads[0]}/{off_heads[0]}，小字 {smalls[0]}/{off_smalls[0]}）")
    h_on = band_read(on_img, on_ink, on_rows, heads[0])
    h_off = band_read(off_img, off_ink, off_rows, off_heads[0])
    s_on = band_read(on_img, on_ink, on_rows, smalls[0])
    s_off = band_read(off_img, off_ink, off_rows, off_smalls[0])
    print(f"撞色 {label}｜标题带 y{heads[0]}（{h_on['n']} px 笔画，字 {h_on['core']}）")
    print(f"  关档  底 {h_off['box']}｜贴边 {h_off['ring']}｜贴边对底 {h_off['sep']:.1f}×｜"
          f"字对贴边 {h_off['cr']:.2f}:1、字对底 {h_off['cf']:.2f}:1  ← 原始读数")
    print(f"  开档  底 {h_on['box']}｜贴边 {h_on['ring']}｜贴边对底 {h_on['sep']:.1f}×｜"
          f"字对贴边 {h_on['cr']:.2f}:1、字对底 {h_on['cf']:.2f}:1")
    if h_off["sep"] > 1.4:
        fails.append(f"[{label}] 关档时贴边就已经和底分得开（{h_off['sep']:.1f}×），"
                     f"量法数到了别的东西，开档那条不算数")
    if h_on["sep"] < 2.5:
        fails.append(f"[{label}] 开档没在贴边垫出东西来：分离只有 {h_on['sep']:.1f}×（要 ≥2.5），"
                     f"光晕等于没加")
    if h_on["cr"] < 3.0:
        fails.append(f"[{label}] 撞色站点上标题读不动：字对贴边 {h_on['cr']:.2f}:1，"
                     f"连 WCAG 大字号那条 3:1 都不到")
    if h_on["cr"] < h_off["cr"] + 1.0:
        fails.append(f"[{label}] 光晕没把局部对比抬起来：{h_off['cr']:.2f} → {h_on['cr']:.2f}"
                     f"（要求至少 +1.0）")
    print(f"  链接行 y{smalls[0]}｜字对贴边 关档 {s_off['cr']:.2f}:1 → 开档 {s_on['cr']:.2f}:1"
          f"（链接吃的是 1px 硬边，不是这团模糊）")
    if s_on["cr"] < s_off["cr"] - 0.1:
        fails.append(f"[{label}] 链接行被垫糊了：开档 {s_on['cr']:.2f} < 关档 {s_off['cr']:.2f}，"
                     f"16px 中文笔画撑不住——那一圈描边退回模糊形了（硬边的半径必须是 0）")

# 负控制：自家页面上光晕不该把标题弄得读不动。这里刻意不要求"开关档读数相等"——
# 自家底是渐变（canvas-2→1→3），标题所在那一条的底色并不等于 --ks-canvas-1，
# 所以夜晚档的光晕（深紫）确实会比局部底更暗一点，量到 7.34→8.16 的真实抬升。
# 那条"同色时完全隐形"是 CSS 注释里的说法，只对底色正好等于 canvas-1 的地方成立；
# 这里判的是能站得住的那半句：不许变差，且两种情况都远在 AA 线之上。
NEG = (("白天档", "01-components-day.png", "09-components-halo-off-day.png"),
       ("夜晚档", "02-components-night.png", "10-components-halo-off-night.png"))
for neg_label, on_name, off_name in NEG:
    on_img, off_img = load(on_name), load(off_name)
    on_ink, on_rows = candy_ink(on_img)
    off_ink, off_rows = candy_ink(off_img)
    hb = [b for b in row_bands(on_rows) if b[1] - b[0] + 1 >= 24][0]
    ohb = [b for b in row_bands(off_rows) if b[1] - b[0] + 1 >= 24][0]
    n_on = band_read(on_img, on_ink, on_rows, hb)
    n_off = band_read(off_img, off_ink, off_rows, ohb)
    print(f"负控制 {neg_label} 自家底｜标题带 y{hb}｜字 {n_on['core']}｜底 {n_on['box']}"
          f"｜贴边 开 {n_on['ring']} / 关 {n_off['ring']}"
          f"｜字对贴边 开 {n_on['cr']:.2f}:1 / 关 {n_off['cr']:.2f}:1")
    if n_on["cr"] < n_off["cr"] - 0.2:
        fails.append(f"负控制不成立（{neg_label}）：自家底上开了光晕反而把标题读性拉低了 "
                     f"{n_off['cr']:.2f} → {n_on['cr']:.2f}")
    if min(n_on["cr"], n_off["cr"]) < 4.5:
        fails.append(f"自家底上标题不到 AA：开 {n_on['cr']:.2f}:1、关 {n_off['cr']:.2f}:1，"
                     f"不撞色的时候都不该掉到 4.5 以下")


SCRIM_DARK = 0.35    # 遮罩下白字也只到 L≈0.25，这条线把"被压暗"和"没被压暗"分开
ISLAND_MIN_ROWS = 40  # 弹窗面板实测 82 行亮区；低于此就是没找到成块的亮区
ISLAND_BRIGHT = 0.50
MIN_ROW_HITS = 100    # 一行里至少 100 个采样点亮着才算"面板的一行"，挡掉零散白点


def bright_island(img):
    """被遮罩留着没压暗的那块：返回 (bbox, 岛内底色中位, 岛内最深墨像素, 墨占比)。

    找不到返回 None。右缘 16px 不参与——糖果滚动条是一条从上到下的亮带，
    会把"孤岛"撑成整个视口。
    """
    rgb = img.convert("RGB")
    W, H = rgb.size
    px = rgb.load()
    rows = {}
    for y in range(0, H, 2):
        xs = [x for x in range(0, W - 16, 2) if lum(px[x, y]) > ISLAND_BRIGHT]
        if len(xs) >= MIN_ROW_HITS:
            rows[y] = xs
    if not rows:
        return None
    ys = sorted(rows)
    seg = [[ys[0]]]
    for a, b in zip(ys, ys[1:]):
        (seg[-1].append(b) if b - a <= 6 else seg.append([b]))
    band = max(seg, key=len)
    if len(band) < ISLAND_MIN_ROWS:
        return None
    x0 = min(min(rows[y]) for y in band)
    x1 = max(max(rows[y]) for y in band)
    box = (x0, band[0], x1, band[-1])
    inside = [px[x, y] for y in range(band[0], band[-1] + 1, 2)
              for x in range(x0, x1 + 1, 2)]
    lit = [p for p in inside if lum(p) > ISLAND_BRIGHT]
    ink = sorted((p for p in inside if lum(p) < SCRIM_DARK), key=lum)
    if not lit or not ink:
        what = "没底" if not lit else "没字"
        sys.exit(f"DIFF ERROR: 亮岛 {box} 里{what}，那块亮区不是弹窗")
    return box, med_rgb(lit), ink[len(ink) // 2], len(ink) / len(inside)


def med_rgb(ps):
    """逐通道中位，绕开 pct() 对元组排序时按 R 先比的老毛病。"""
    return tuple(sorted(p[i] for p in ps)[len(ps) // 2] for i in range(3))


def dark_rate(img):
    """整幅里被压到 L<SCRIM_DARK 的采样占比。"""
    rgb = img.convert("RGB")
    W, H = rgb.size
    px = rgb.load()
    n = d = 0
    for y in range(0, H, 4):
        for x in range(0, W, 4):
            n += 1
            d += lum(px[x, y]) < SCRIM_DARK
    return d / n


# ---------- 模态遮罩：弹窗外面压暗、弹窗自己不被压暗 ----------
# 这条原先只有计算样式断言（check-controls.py 读到 backdrop α=0.55），像素上没证过：
# 夹具里那个 <dialog open> 是非模态的，非模态压根不画 ::backdrop，
# 所以前面十张图里没有任何一格能回答"遮罩到底画没画出来"。
# 11/12 出自同一份构建，只差末尾那段 showModal()——两档的暗区占比就是这对的读数。
mo, no = load("11-components-modal.png"), load("12-components-nomodal.png")
mo_dark, no_dark = dark_rate(mo), dark_rate(no)
isl = bright_island(mo)
if isl is None:
    sys.exit("DIFF ERROR: 11 里找不到成块的亮区（连续亮行 < 40），弹窗或遮罩没画出来")
box, bg, ink_mid, ink_share = isl
W, H = mo.size
share = ((box[2] - box[0] + 1) * (box[3] - box[1] + 1)) / ((W - 16) * H)
print(f"模态遮罩  挂 showModal 后暗区 {mo_dark:.1%}｜不挂的负控制 {no_dark:.1%}"
      f"（阈值 {SCRIM_DARK}）")
print(f"  亮岛 {box} 占视口 {share:.1%}｜岛内底 {bg} (L={lum(bg):.3f})"
      f"｜岛内墨 {ink_share:.1%}｜最深那档字对底 {contrast(ink_mid, bg):.2f}:1")
if mo_dark < 0.80:
    fails.append(f"遮罩没把弹窗外面压暗：只有 {mo_dark:.1%} 的像素掉到 L<{SCRIM_DARK}")
if no_dark > 0.20:
    fails.append(f"负控制不成立：不挂 showModal 的同一份构建已经 {no_dark:.1%} 是暗的，"
                 f"上面那条'压暗'不是遮罩带来的")
if share > 0.30:
    fails.append(f"亮岛占了视口 {share:.1%}，那不是一块孤岛而是整页没被压暗")
if lum(bg) < 0.55:
    fails.append(f"弹窗自己被压在遮罩底下：岛内底 L={lum(bg):.3f}")
if ink_share < 0.02:
    fails.append(f"亮岛里只有 {ink_share:.1%} 是墨，那块亮区里没有字——它不是弹窗，"
                 f"或者夹具的弹窗被挪走了")
# 岛内"字对底"只打印不设阈值：判墨用的是 L<0.35 这一刀，中间调的墨（比如 #ff7ab0，
# L≈0.36）两头都不落，实测把弹窗字色换成它就整条静默通过。弹窗文字的对比度
# 由 check-contrast.py 在 token 层判，这里只保证"岛里有字、岛没被遮罩盖住"。

# 负控制档本该"整页都亮、没有孤岛"：亮区铺满视口才对得上。
no_isl = bright_island(no)
if no_isl is None:
    fails.append(f"负控制档（12）里也找不到亮区，说明压暗不是 showModal 这一处带来的")
else:
    nb = no_isl[0]
    no_share = ((nb[2] - nb[0] + 1) * (nb[3] - nb[1] + 1)) / ((W - 16) * H)
    print(f"  负控制档亮区占视口 {no_share:.1%}（该铺满整页，弹窗只是其中一块）")
    if no_share < 0.60:
        fails.append(f"负控制档的亮区只占 {no_share:.1%}：不挂 showModal 时页面也不该有孤岛")

# ---------- 几何：取样坐标由 shoot.sh 的探针量回来，不在这里猜 ----------
# 两趟读数的存在是因为滚动条会吃掉内容宽度：短窗口那趟（有滚动条）配 01/02，
# 整页那趟（没有滚动条）配 13/14。拿一趟的坐标去采另一趟就是上一轮那次错位 140px。
GEOM = ROOT / "preview" / ".build" / "geometry.txt"


def geometry():
    if not GEOM.exists():
        sys.exit(f"DIFF ERROR: 缺 {GEOM.relative_to(ROOT)}——坐标探针没落盘，"
                 f"斑马纹和页尾那几格没有落脚处")
    out = {}
    for line in GEOM.read_text(encoding="utf-8").splitlines():
        m = re.match(r"win=([\d,]+) GEOM (\d+) (.*)", line.strip())
        if not m:
            sys.exit(f"DIFF ERROR: geometry.txt 这一行形状不对：{line[:70]!r}")
        win, doc_h, body = m.groups()
        rects = {"_doc": int(doc_h)}
        for e in body.split(";"):
            sel, _, nums = e.rpartition("@")
            v = nums.split(",")
            if not sel or len(v) != 4 or not all(n.isdigit() for n in v):
                sys.exit(f"DIFF ERROR: geometry.txt 里这一条目形状不对：{e!r}")
            rects[sel] = tuple(int(n) for n in v)
        out[win] = rects
    if len(out) != 2:
        sys.exit(f"DIFF ERROR: geometry.txt 该有短窗口和整页两趟读数，实际 {sorted(out)}")
    return out


GEO = geometry()
SHORT = "1280,1500"
if SHORT not in GEO:
    sys.exit(f"DIFF ERROR: 没有 {SHORT} 那一趟几何读数，实际 {sorted(GEO)}")
FULL = next((w for w in GEO if w != SHORT), "")
if not FULL or int(FULL.split(",")[1]) <= 1500:
    sys.exit(f"DIFF ERROR: 整页那一趟 {FULL or '（缺）'} 不比 1500 高，页尾取不到东西")

# ---------- 糖果滚动条：判据是"画出了一条 CSS 声明的那块滑块"，不是"数到多少粉点" ----------
# 为什么这一格要接在几何读数后面：滑块该占多长是算得出来的——thumb 长 = 视口高×视口高/内容高
# （Chrome 按可见比例画），内容高由探针量到、视口高是出图窗口那 1500。
# 上一版没有这个期望值，它卡的是"右缘糖段至少占视口 25%"：夹具从 2100 长到 3444 那一次，
# 滑块从 90% 掉到 44%，同一把尺子下次量到的还是夹具的高度而不是滚动条。
# 芯宽也从 CSS 现推（::-webkit-scrollbar 的 width 减掉 thumb 那圈 border 的两倍），
# 判"一行是糖"要求整条芯宽都命中，而不是这一行里有一个糖点。
# 负控制跟着升级成同宽的镜像带，不再依赖"左缘恰好没东西"：量过，01 那张的糖芯落在
# x1271–1277 恰好 7 列（与 11−2×2 对上），而左缘那 40 行连续的粉只有 1 列命中
# （引用左线，落在 x=8）——按点谓词它和滑块同格（旧版就是这么误红了一整次），
# 按带谓词它是 0 行。
# 容差给 ±8 行（24px，约 1.5% 的视口）：采样每 3px 取一行、滑块两端各有 2px 描边、
# 圆角还会削掉首尾几行，这三样都是量化而不是"画错了"。
# 为什么不去关 overlay：实测 headless 下 --enable/--disable-features=OverlayScrollbar
# 两种取值的右缘粉点一模一样（3463/3463），这个开关在无头里是空转；
# 真浏览器上能不能看见取决于系统"始终显示滚动条"——这条写进 README，不假称已验证。


def scroll_core(src):
    """从 CSS 里解出滚动条的 (轨道宽, 描边宽)；糖芯宽度由这两个数现推，脚本不抄像素。"""
    w = re.search(r"::-webkit-scrollbar\s*\{\s*width:\s*(\d+)px", src)
    b = re.search(r"::-webkit-scrollbar-thumb\s*\{[^{}]*?border:\s*(\d+)px\s+solid", src)
    if not w or not b:
        sys.exit("DIFF ERROR: 没能从 CSS 里解出 ::-webkit-scrollbar 的 width 和 thumb 的 "
                 "border，芯宽无从算起，这一格也就没有判定对象")
    return int(w.group(1)), int(b.group(1))


SB_W, SB_EDGE = scroll_core(CSS.read_text(encoding="utf-8"))
SB_CORE = SB_W - 2 * SB_EDGE
if SB_CORE < 2:
    sys.exit(f"DIFF ERROR: 糖芯宽解成 {SB_W}−2×{SB_EDGE}，不是一条能采样的带")

bar = day
BW, BH = bar.size
ROWS = range(0, BH, 3)
# 右缘那条芯按 CSS 的几何落在 [BW−轨道宽+描边, BW−描边)；负控制取左缘的镜像同宽带
CORE_X = range(BW - SB_W + SB_EDGE, BW - SB_EDGE)
LEFT_X = range(SB_EDGE, SB_EDGE + SB_CORE)


def candy_run(img, xs):
    """返回 (整条带都命中的最长连续行数, 命中行的中位 R-G)。用 min 不用 max：
    一个糖点不足以让一行过关，必须整条芯宽都是糖——这正是把滑块和内容分开的那一格。"""
    px = img.load()
    best = cur = 0
    gaps = []
    for y in ROWS:
        hit = min(px[x, y][0] - px[x, y][1] for x in xs)
        cur = cur + 1 if hit > 40 else 0
        best = max(best, cur)
        if hit > 40:
            gaps.append(hit)
    gaps.sort()
    return best, (gaps[len(gaps) // 2] if gaps else 0)


n_rows = len(ROWS)
right_run, right_gap = candy_run(bar, CORE_X)
left_run, left_gap = candy_run(bar, LEFT_X)
DOC_H = GEO[SHORT]["_doc"]
want_rows = round(BH * BH / DOC_H / 3)
print(f"滚动条    糖芯 {SB_CORE} 列（CSS 声明轨道 {SB_W} 减两侧描边 {SB_EDGE}），"
      f"右缘最长连续段 {right_run}/{n_rows} 行（中位 R-G {right_gap}）；"
      f"按几何该是 {want_rows} 行（内容高 {DOC_H}），左缘同宽镜像带 {left_run} 行")
if abs(right_run - want_rows) > 8:
    fails.append(f"右缘糖段的长度对不上几何：量到 {right_run} 行，按 视口×视口/内容高 "
                 f"该是 {want_rows} 行——滑块要么没画满，要么内容高与图不是同一趟")
if left_run * 6 > right_run:
    fails.append(f"负控制不成立：左缘同宽那条带 {left_run} 行已到右缘 {right_run} 行的 "
                 f"1/6 以内，数到的可能不是滚动条")


def check_size(img, win, name):
    w, h = (int(v) for v in win.split(","))
    if img.size != (w, h):
        sys.exit(f"DIFF ERROR: {name} 是 {img.size[0]}×{img.size[1]}，和几何那一趟的窗口 "
                 f"{win} 对不上——图或 geometry.txt 是陈旧的，重跑 shoot.sh")


def rect(img, win, sel, ix=0, iy=0):
    """按探针坐标取这块的取样盒，往里收 (ix, iy) 躲开自己的边框；越界就是读数陈旧。"""
    if sel not in GEO[win]:
        sys.exit(f"DIFF ERROR: {win} 那趟几何读数里没有 {sel}")
    x, y, w, h = GEO[win][sel]
    W, H = img.size
    if x + w > W or y + h > H:
        sys.exit(f"DIFF ERROR: {sel} 在 {win} 量到 x{x} y{y} {w}×{h}，超出这张图的 "
                 f"{W}×{H}——geometry.txt 和图对不上，重跑 shoot.sh")
    if w <= 2 * (ix + 4) or h <= 2 * (iy + 4):
        sys.exit(f"DIFF ERROR: {sel} 只有 {w}×{h}，收不进 ix={ix} iy={iy} 的取样盒")
    return (x + ix, y + iy, x + w - ix, y + h - iy)


def sampled(img, box, step=2):
    """盒内每 step 个像素取一点。三个判据（纸中位、墨那头、纹理带宽）共用同一批点，
    免得各写一遍取样而量到不同的东西。"""
    rgb = img.convert("RGB").crop(box)
    W, H = rgb.size
    data = rgb.tobytes()
    return [(data[(y * W + x) * 3], data[(y * W + x) * 3 + 1], data[(y * W + x) * 3 + 2])
            for y in range(0, H, step) for x in range(0, W, step)]


def ink_read(img, box, name):
    """一块区域内的纸（逐通道中位）、墨（离纸最远的那一头）和过 4.5 线的取样占比。"""
    pts = sampled(img, box)
    if len(pts) < 200:
        sys.exit(f"DIFF ERROR: {name} 的取样盒 {box} 只有 {len(pts)} 个点，撑不起判据")
    pairs = sorted((lum(p), p) for p in pts)
    ls = [l for l, _ in pairs]
    paper_l = ls[len(ls) // 2]
    lo_l, hi_l = ls[2], ls[-3]

    def wr(l):
        return (max(l, paper_l) + 0.05) / (min(l, paper_l) + 0.05)

    # 墨在哪一头是档位决定的：白天档墨比纸暗，夜晚档底 L≈0.01、墨反而比纸亮。
    # 写死"取最暗"会在夜晚档把纸当墨——同一轮里量竖分隔线就是这么假没的。
    side, ink = ("亮", pairs[-3][1]) if hi_l - paper_l > paper_l - lo_l else ("暗", pairs[2][1])
    return dict(paper=med_rgb([p for _, p in pairs]), ink=ink, side=side,
                ratio=wr(lum(ink)), share=sum(1 for l, _ in pairs if wr(l) >= 4.5) / len(pairs),
                dist=abs(lum(ink) - paper_l), n=len(pairs))


fd, fn = load("13-components-full-day.png"), load("14-components-full-night.png")
for img, name in ((day, "01"), (night, "02")):
    check_size(img, SHORT, name)
for img, name in ((fd, "13"), (fn, "14")):
    check_size(img, FULL, name)

# ---------- 斑马纹：裸表相邻两行必须交替，而不是往下渐变 ----------
# 坐标来自 shoot.sh 的几何探针（那一趟跑在 1280×1500 窗口里，和 01/02 同宽同滚动条），
# 不在这里猜 y——上一轮手工取样把带子取错了 140px，差点把"画出来了"报成"没画"。
# 判"交替"而不是判"第二行不一样"：偶/奇两行（1 与 3）该几乎相等，相邻两行（1 与 2）该分开。
# 底衬本身是个往下走的渐变，只看 1↔2 会把渐变数成斑马纹，所以 1↔3 是这条的负控制。
ZEB = tuple(f"table:not(.own) tbody tr:nth-child({i})" for i in (1, 2, 3))
ZEB_ALT_MIN = 1.05    # 相邻两行至少要到这个分离度（实测白天 1.112×、夜晚 1.375×；删掉斑马纹就是 1.00×）
ZEB_GAP_MIN = 0.05    # 且要比同奇偶两行的残留高出至少这么多——拿渐变自己当基线，不写死魔数
# 为什么用"差"而不是"倍数"：亮度接近白的时候比值这根尺本身分辨率很差，
# 9% 的糖洗在白天档底衬上只把 L 从 0.934 拉到 0.840，倍数为 1.11×——
# 再要求"至少是残留的 1.2 倍"就成了一条永远开不了火的判据（白天档的倍数就是它自己）。
# 差值形式对两档都留得下余量：白天 0.112、夜晚 0.350，而漂移那一路实测 ≤0.025。

for arm, img in (("白天档", day), ("夜晚档", night)):
    rows = [patch(img, rect(img, SHORT, s, 6, 3)) for s in ZEB]
    alt, drift = sep(rows[0], rows[1]), sep(rows[0], rows[2])
    print(f"斑马纹 {arm}｜行1 {rows[0]} (L={lum(rows[0]):.4f}) 行2 {rows[1]} "
          f"(L={lum(rows[1]):.4f}) 行3 {rows[2]}｜1↔2 {alt:.3f}×｜1↔3 {drift:.3f}×"
          f"｜交替减漂移 {alt - drift:+.3f}")
    if alt < ZEB_ALT_MIN:
        fails.append(f"斑马纹看不出来（{arm}）：相邻两行只分离 {alt:.3f}×，"
                     f"`tbody tr:nth-child(even)` 那条等于没落地")
    if alt - drift < ZEB_GAP_MIN:
        fails.append(f"数到的不是斑马纹（{arm}）：相邻两行 {alt:.3f}× 只比同奇偶两行的 "
                     f"{drift:.3f}× 高 {alt - drift:+.3f}，分不出交替和底衬往下走的渐变")

# ---------- 页尾那一格：六、卡片与图 / dialog / footer ----------
# 出图窗口原先写死 1280×1500，而这份夹具的内容长到 y≈1972，也就是说 1500 以下那三块
# 从来没有一张闸门图覆盖过 —— 上一轮逐块看图时它是靠临时手出的整页图才发现的，
# 闸门本身对页尾是瞎的。13/14 按量出来的真实内容高出图，这里逐块判两件事：
# 跟着档位真的翻了色（不是卡死在某档），以及这块里有字读得动（不是拿空底冒充"复检过"）。
TAIL = (("卡片与图", ".cards"), ("弹窗", "dialog"), ("页脚", "footer"))
TAIL_Y = 1500
TAIL_FLIP_MIN = 0.15    # 同一块在两档之间的亮度落差
TAIL_INK_MIN = 0.004    # 过 4.5 线的取样点占比下限（实测文字带是这个的十倍量级）
TAIL_INK_DIST = 0.03    # 墨那头离纸至少这么远，否则"墨"只是噪点
boxes = {}

for label, sel in TAIL:
    boxes[label] = rect(fd, FULL, sel)
    if boxes[label][3] <= TAIL_Y:
        sys.exit(f"DIFF ERROR: {label} 整块都在 y{TAIL_Y} 以上（只到 y{boxes[label][3]}），"
                 f"旧的那两张 1500 高的图早就盖住了它，页尾这一格失去了取证对象")
if not any(b[1] >= TAIL_Y for b in boxes.values()):
    sys.exit(f"DIFF ERROR: 三块页尾都跨在 y{TAIL_Y} 上、没有一块整个落在下面 —— "
             f"夹具短到旧图就盖得住，这一格是空转")

for label, sel in TAIL:
    bd = boxes[label]
    t_day = ink_read(fd, rect(fd, FULL, sel, 4, 4), f"13/{label}·白天档")
    t_night = ink_read(fn, rect(fn, FULL, sel, 4, 4), f"14/{label}·夜晚档")
    dl, nl = lum(t_day["paper"]), lum(t_night["paper"])
    print(f"页尾 {label}｜x{bd[0]}–{bd[2]} y{bd[1]}–{bd[3]}"
          f"{'（整块都在旧图之外）' if bd[1] >= TAIL_Y else '（跨 y1500）'}")
    for lab, t in (("白天档", t_day), ("夜晚档", t_night)):
        print(f"  {lab} 纸 {t['paper']} (L={dl if lab == '白天档' else nl:.3f})｜"
              f"墨在{t['side']}那头 {t['ink']}｜墨对纸 {t['ratio']:.2f}:1｜"
              f"过线墨点 {t['share']:.2%}")
    if dl < nl:
        fails.append(f"页尾{label}白天档比夜晚档还暗（{dl:.3f} < {nl:.3f}），"
                     f"这块没跟着 light-dark() 翻档")
    if abs(dl - nl) < TAIL_FLIP_MIN:
        fails.append(f"页尾{label}两档亮度差只有 {abs(dl - nl):.3f}，"
                     f"页首翻了不代表页尾也翻——它卡在同一档了")
    for lab, t in (("白天档", t_day), ("夜晚档", t_night)):
        if t["dist"] < TAIL_INK_DIST:
            fails.append(f"页尾{label}取不到墨：离纸最远的那头也只差 {t['dist']:.3f}，"
                         f"那块是空底不是内容")
        elif t["share"] < TAIL_INK_MIN:
            fails.append(f"页尾{label}几乎没有字：过 4.5 线的取样点只占 {t['share']:.2%}，"
                         f"这块撑不起'逐块复检'")
        elif t["ratio"] < 4.5:
            fails.append(f"页尾{label}字读不动：墨对纸 {t['ratio']:.2f}:1，不到 AA 的 4.5")

# ---------- 第十项：浮层玻璃——透多少写在 CSS 里，透过以后还读不读得动只能量像素 ----------
# 计算样式那一本（check-controls）已经逐条对账过 §4c：bg 的 α、backdrop-filter 里的虚焦
# 半径、面与后代各自的字色。那些只证明"样式表这么写、Chrome 这么算"，答不了三件事：
# ①那 14% 真透上来了没有、把纸面弄成了什么色；②透上来的底噪有没有把字吃掉；
# ③玻璃有没有溢出浮层、动到底下那块不属于它的内容。三条都只有像素能回答。
#
# 两格浮层是配对存在的，不是为了好看——"透出多少"这一问只在纸与底不同色时才有读数：
#   七：深底菜单压在站点白底正文上 → 夜晚档的纸（深紫）被白底提亮（ΔL +0.027）开火，
#       白天档的纸（粉白）与白底几乎同色（ΔL −0.006），在这一档这一格是瞎的。
#   八：浅色提示条压在深色代码块上 → 白天档 ΔL −0.214 开火，夜晚档 −0.000 瞎。
# 于是每一档各有一格开火、另一格天然是"透不出东西时读数不许动"的负控制；两把尺子
# 在白天档还各自落在不同的那格上（均值靠第八格、纹理靠第七格）。所以那两条"每档至少
# 有一格分辨得出"的下限是必须立的：调色板改天把两格都弄成同色时，它炸，而不是让整项
# 静默退化成"两张图各印了一行读数"。
#
# 已知不对称，写在这儿不遮掩：纹理上限那条（GLASS_BLEED_MAX）只在白天档开得火——
# 把虚焦在页面上覆写成 0px 出的对照图，实测白天档的菜单那格纸半带 0.096（越线），
# 夜晚档同一格 0.032（不越线）。所以"虚焦在场"这件事的通用判定归 check-controls 的
# blur(16px) 那一行，像素这本只是给它补了一道白天的兜底，不冒充两档都证过。
# 同样不归像素这本的是"面那条 color"：第八格每一行文字都挂在被后代点名的元素上
# （这是为了让后代那条有东西可管而刻意排的），所以面自己那条字色在这一格是等价变异，
# 它由计算样式那本判。
GLASS = (("菜单×白底正文", ".site-menu", ".site-doc"),
         ("提示条×深色代码块", ".site-toast", ".site-code"),
         # 第九格那四块：A/B 是逐字摘自 GitHub 服务端 HTML 的类名值（靠 modal／popover
         # 这两个词根命中），D/E 除了语义属性没有任何别的钩子——族里那两个新属性
         # 在像素上到底生没生效，只有这两块能回答。
         ("GitHub 弹窗面×站点正文", ".gh-a", ".gh-ground"),
         ("GitHub 悬停卡×站点正文", ".gh-b", ".gh-ground"),
         ("aria-modal 面板×站点正文", ".gh-d", ".gh-ground"),
         ("alertdialog 面板×站点正文", ".gh-e", ".gh-ground"),
         # 第十格那四块：常驻浮动条（侧栏／吸顶条／文档次级栏／悬浮钮外壳）。
         # 它们和上面那五块的区别是"一直浮着"，底下永远有字在滚，
         # 所以这一格才是"浮动的东西也要统一成玻璃"那句话说的事。
         # B 的站点墨是 #fff（w3schools 那条深蓝吸顶条的白字），面被扳成浅粉底之后，
         # 只有后代那条 color 换走了墨才读得动——这一格是那条规则在像素上唯一的证人。
         ("站点侧栏×常驻浮动条底", ".ch-a", ".ch-ground"),
         ("站点吸顶条×常驻浮动条底", ".ch-b", ".ch-ground"),
         ("文档次级栏×常驻浮动条底", ".ch-c", ".ch-ground"),
         ("悬浮钮外壳×常驻浮动条底", ".ch-d", ".ch-ground"),
         # 2026-10-03 用户改判「接管常驻条」：navbar／header 两截从否决转正，
         # 于是这两格从下面的负控制搬进这一族——它们从此必须在开关两趟之间挪动，
         # 而且透底以后仍要读得动（GLASS 这一圈每条都过 4.5 那道 AA 线）。
         ("导航条×常驻条接管", ".ch-e", ".ch-ground"),
         ("吸顶容器×常驻条接管", ".ch-f", ".ch-ground"))
# 追不到的那四格：站点只给了哈希类名（Primer 的 ActionMenu 面），或者它压根不是浮层
# 而是被词根子串误伤的控件/图标（GitHub 侧栏那对 NavDropdown 按钮与箭头），
# 又或者它是挂了新词根的 <button>（被末尾的 :not 排在外面）。
# 开关两趟它们必须一字节都不动——--kGlass 只调制族点名的那一面。
# 这四条不是"顺手记个限制"：它们是 P06/P07 那两把刀的靶子，往 C 的类名里塞一个 modal 词根、
# 或把族末尾的 :not(button) 摘掉，对应那格立刻红。
# navbar／header 两格从前在这里（那是普查判过「不追」的否决，红过就代表词根被加了进来），
# 改判之后它们进了上面那一族，这一格里再没有它们的证人。
GLASS_UNREACHED = (("哈希类名面板", ".gh-c", ".gh-ground",
                    "站点只用哈希类名宣告自己是浮层、族追不上它"),
                   ("侧栏折叠钮", ".gh-f", ".gh-ground",
                    "它是按钮不是浮层，族末尾的 :not(button, svg) 把它排在外面"),
                   ("按钮里的箭头图标", ".gh-g", ".gh-ground",
                    "它是 svg 图标不是浮层，同上"),
                   ("挂 fixed-btn 的真按钮", ".ch-g", ".ch-ground",
                    "词根追到了类名但它是 <button>，族末尾的 :not(button, svg) 排在外面"))
# 每一块底上压着的全部浮层：算"底下的平均色"和比"浮层以外不许动"都要一次挖干净，
# 漏挖兄弟面板等于把别人家的玻璃算成这块的底。够不着的那几格也要挖：它们今天确实两趟相同，
# 但"它们被刀割到、词根追上了"正是这几格要报的红——那种红该只有一本报，
# 让别的格跟着报"浮层以外动了"就是把一个判据的失败摊成六本。
GLASS_PANELS = {}
for _l, _p, _u, *_ in GLASS + GLASS_UNREACHED:
    GLASS_PANELS.setdefault(_u, []).append(_p)
GLASS_PRED_TOL = 6      # 实测纸面中位 vs 按 CSS 缺口混出来的预测，逐通道
GLASS_CR_MIN = 4.5      # 透过玻璃以后墨对纸
GLASS_SOLID_MAX = 0.020  # 关档那面板的纸半带：必须是一面不透明的板子
GLASS_BLEED_MIN = 0.010  # 开档至少要比关档多出这么多底噪（实测 白天+0.021／夜晚+0.015）
GLASS_BLEED_MAX = 0.060  # 上限：纹理要被虚焦抹开（无虚焦的对照实测 0.096）
GLASS_SHIFT_MIN = 0.020  # 每档至少一格纸面中位真的被挪动（实测 白天 0.214／夜晚 0.027）
PAPER_HALF = 0.25        # 离纸中位这么远以内的点算"纸那一半"，把笔画剔出带宽


def load_gate(name):
    """按路径导入闸门模块：期望值的算式只住一本，两本共用（和 check-controls 里那条同一条路）。"""
    path = ROOT / "tools" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def glass_deficit():
    """玻璃"透出去"的那一成不在这里再解释一遍 CSS：交给 check-controls 的 MIX_RE 现推，
    两本闸门读到的 α 因而是同一个数。解不出来就炸，不能让预测拿 0% 蒙过这一格。"""
    cc = load_gate("check-controls.py")
    gate = cc.load_gate("check-contrast.py")
    src = CSS.read_text(encoding="utf-8")
    try:
        d = cc.glass_deficit(cc.css_expect(src, gate.load_tokens(src),
                                           gate.load_sakura(src), gate))
    except (ValueError, SystemExit):
        sys.exit("DIFF ERROR: §4c 的透明度缺口从 CSS 里解不出来——第十项没有预测值可比，"
                 "先修 tools/check-controls.py 报出来的那一处")
    if not 0 < d < 1:
        sys.exit(f"DIFF ERROR: 解出的玻璃缺口 {d} 不在 (0,1)，预测公式要重写")
    return d


def paper_band(img, box, who):
    """纸那一半的亮度带宽（p90−p10）。剔掉墨是有原因的：笔画在两档都是零点几个单位
    的落差，把它算进带里量到的就是"这块有没有字"，而这一格要问的是底噪透上来多少。"""
    ls = [lum(p) for p in sampled(img, box)]
    med = pct(ls, 0.50)
    paper = [l for l in ls if abs(l - med) <= PAPER_HALF]
    if len(paper) < 200:
        sys.exit(f"DIFF ERROR: {who} 的取样盒 {box} 里纸那一半只有 {len(paper)} 点，"
                 f"这块不是浮层")
    return pct(paper, 0.90) - pct(paper, 0.10)


def _grow(boxes, by=2):
    """整批往外扩 by 个像素（挖洞用，不是取样用）。"""
    return [(x0 - by, y0 - by, x1 + by, y1 + by) for x0, y0, x1, y1 in boxes]


def box_minus(outer, holes):
    """从 outer 里挖掉一整批浮层，返回剩下的互不重叠小盒：按各面板的上下边界切横带，
    每一带再按压在这一行上的那些面板挖掉 x 段。

    挖的必须是"这一格底上的全部浮层"而不是被测的那一块——只挖自己那块，兄弟面板会被
    当成"底"算进均值，而开关两趟兄弟面板自己也在翻（它们同样是玻璃），
    于是"浮层以外不许动"这一条对每一格都红（六格浮层第一跑就是四格红在这里）。"""
    ox0, oy0, ox1, oy1 = outer
    edges = {oy0, oy1 + 1}
    for _, hy0, _, hy1 in holes:
        if hy1 < oy0 or hy0 > oy1:
            continue
        edges.add(max(hy0, oy0))
        edges.add(min(hy1, oy1) + 1)
    ys = sorted(v for v in edges if oy0 <= v <= oy1 + 1)
    out = []
    for a, b in zip(ys, ys[1:]):
        if b <= a:
            continue
        mid = (a + b) // 2
        xs = sorted((max(ox0, hx0), min(ox1, hx1))
                    for hx0, hy0, hx1, hy1 in holes if hy0 <= mid <= hy1)
        cur = ox0
        for x0, x1 in xs:
            if x1 < cur:
                continue
            if x0 > cur:
                out.append((cur, a, x0 - 1, b - 1))
            cur = max(cur, x1 + 1)
        if cur <= ox1:
            out.append((cur, a, ox1, b - 1))
    return [r for r in out if r[2] >= r[0] and r[3] >= r[1]]


DEF = glass_deficit()
gd, gn = load("15-components-glass-off-day.png"), load("16-components-glass-off-night.png")
for img, name in ((gd, "15"), (gn, "16")):
    check_size(img, FULL, name)
print(f"玻璃缺口  §4c 按 CSS 透出 {DEF:.0%}，{len(GLASS)} 格浮层 × 两档一起对账，"
      f"另加 {len(GLASS_UNREACHED)} 格族不该管的形状当负控制")

for arm, on_img, off_img, on_n, off_n in (
        ("白天档", fd, gd, "13", "15"), ("夜晚档", fn, gn, "14", "16")):
    shifts, bleeds = [], []
    for label, p_sel, u_sel in GLASS:
        pbox = rect(on_img, FULL, p_sel, 6, 6)
        if rect(off_img, FULL, p_sel, 6, 6) != pbox:
            sys.exit(f"DIFF ERROR: {label} 在 {on_n}/{off_n} 两张图里位置不同，"
                     f"这一对不是只差 --kGlass 一个变量")
        r_on = ink_read(on_img, pbox, f"{on_n}/{label}·{arm}")
        r_off = ink_read(off_img, pbox, f"{off_n}/{label}·{arm}")
        # 往外多挖 2px：面板自己的边线反锯齿在开关两趟会差一级，那是板子的边界不是底
        gboxes = box_minus(rect(on_img, FULL, u_sel),
                           _grow([rect(on_img, FULL, s) for s in GLASS_PANELS[u_sel]]))
        gpts = [p for b in gboxes for p in sampled(on_img, b)]
        if len(gpts) < 2000:
            sys.exit(f"DIFF ERROR: {label}（{arm}）底下那块挖掉浮层后只剩 {len(gpts)} 个取样点，"
                     f"浮层几乎把底全盖住了——预测用的'底下的平均色'取不到")
        gmean = tuple(sum(p[c] for p in gpts) / len(gpts) for c in range(3))
        # 混色在观察值上是线性的，所以可以直接拿"关档那面实心板 + 底下平均色"按缺口混出预测；
        # 两层都被同一张叠色膜洗过，公式里不用再乘别的项（实测最大偏差 1 级）
        pred = tuple(round((1 - DEF) * r_off["paper"][c] + DEF * gmean[c]) for c in range(3))
        dev = max(abs(pred[c] - r_on["paper"][c]) for c in range(3))
        b_on, b_off = paper_band(on_img, pbox, f"{label}·{arm}·开档"), \
            paper_band(off_img, pbox, f"{label}·{arm}·关档")
        worst = 0
        for b in gboxes:
            d = ImageChops.difference(on_img.convert("RGB").crop(b), off_img.convert("RGB").crop(b))
            if d.getbbox():
                worst = max(worst, max(v[1] for v in d.getextrema()))
        dl = lum(r_on["paper"]) - lum(r_off["paper"])
        shifts.append(abs(dl))
        bleeds.append(b_on - b_off)
        print(f"浮层 {arm} {label}｜x{pbox[0]}–{pbox[2]} y{pbox[1]}–{pbox[3]}｜"
              f"底 {len(gpts)} 点均值 ({gmean[0]:.0f},{gmean[1]:.0f},{gmean[2]:.0f})")
        print(f"  关档 纸 {r_off['paper']} (L={lum(r_off['paper']):.3f})｜纸半带 {b_off:.3f}"
              f"｜墨对纸 {r_off['ratio']:.2f}:1")
        print(f"  开档 纸 {r_on['paper']} (L={lum(r_on['paper']):.3f})｜纸半带 {b_on:.3f}"
              f"｜墨对纸 {r_on['ratio']:.2f}:1｜墨{r_on['ink']}（在{r_on['side']}那头）")
        print(f"  按缺口 {DEF:.0%} 预测 {pred}（实测差 {dev}）｜纸面中位挪动 {dl:+.3f}"
              f"｜底噪比关档多 {b_on - b_off:+.3f}｜浮层以外那块两趟最大差 {worst}")
        if dev > GLASS_PRED_TOL:
            fails.append(f"浮层{label}（{arm}）画出来的不止 CSS 里那一成：实测纸 {r_on['paper']}、"
                         f"按缺口 {DEF:.0%} 混出来该是 {pred}，差 {dev}")
        if r_on["ratio"] < GLASS_CR_MIN:
            fails.append(f"浮层{label}（{arm}）透过玻璃读不动：墨对纸 {r_on['ratio']:.2f}:1，"
                         f"不到 AA 的 4.5——透出底噪的代价把字吃了")
        if b_off > GLASS_SOLID_MAX:
            fails.append(f"浮层{label}（{arm}）关档那面并不实心：纸半带 {b_off:.3f} > "
                         f"{GLASS_SOLID_MAX}，--kGlass:0 没退回一面不透明的板子")
        if b_on > GLASS_BLEED_MAX:
            fails.append(f"浮层{label}（{arm}）开档透出的是渣不是一片：纸半带 {b_on:.3f} > "
                         f"{GLASS_BLEED_MAX}，虚焦没把底噪抹开")
        if worst > 0:
            fails.append(f"浮层{label}（{arm}）动到了浮层以外的底：开关两趟在底下那块有 "
                         f"{worst} 级像素差，玻璃只该画在自己那面之内")
    # 够不着的那几格：先证明它们有字（空底的话"两趟相同"是白捡的），再要求开关两趟逐字节相同
    for ulabel, u_sel, _u_ground, ureason in GLASS_UNREACHED:
        ubox = rect(on_img, FULL, u_sel, 6, 6)
        if rect(off_img, FULL, u_sel, 6, 6) != ubox:
            sys.exit(f"DIFF ERROR: {ulabel} 在 {on_n}/{off_n} 两张图里位置不同，比对对象没对齐")
        u_ink = ink_read(on_img, ubox, f"{on_n}/{ulabel}·{arm}")
        ud = ImageChops.difference(on_img.convert("RGB").crop(ubox),
                                   off_img.convert("RGB").crop(ubox))
        uux = 0 if not ud.getbbox() else max(v[1] for v in ud.getextrema())
        print(f"够不着 {arm} {ulabel}｜x{ubox[0]}–{ubox[2]} y{ubox[1]}–{ubox[3]}｜"
              f"墨对纸 {u_ink['ratio']:.2f}:1｜开关两趟最大差 {uux}")
        if u_ink["dist"] < TAIL_INK_DIST:
            fails.append(f"够不着{ulabel}（{arm}）取不到墨：离纸最远的那头也只差 "
                         f"{u_ink['dist']:.3f}，那块是空底，'两趟相同'是白捡的")
        elif uux > 0:
            fails.append(f"够不着{ulabel}（{arm}）被开关动到了：{ureason}，"
                         f"开关两趟却有 {uux} 级差——玻璃溢到了不该管的那一块")
    if max(shifts) < GLASS_SHIFT_MIN:
        fails.append(f"浮层{arm}两格都分辨不出'透没透'：纸面中位最多只挪动 {max(shifts):.3f}"
                     f"（下限 {GLASS_SHIFT_MIN}）——这一档的纸和两格的底撞色了，均值这把尺失效")
    if max(bleeds) < GLASS_BLEED_MIN:
        fails.append(f"浮层{arm}两格都没有底噪透上来：纹理最多只多 {max(bleeds):.3f}"
                     f"（下限 {GLASS_BLEED_MIN}），backdrop-filter 那一格在这具夹具上量不到东西")

if fails:
    print("\nDIFF FAIL")
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("\nDIFF PASS：明暗翻档、暗色站保持暗、强涂档保持可翻、糖果滚动条、花瓣圆点、"
      "撞色站点光晕（含关档对照与自家底负控制）、模态遮罩（含不挂脚本的负控制）、"
      "裸表斑马纹（含同奇偶两行的渐变负控制）、页尾逐块（卡片与图/弹窗/页脚翻档且读得动）、"
      f"浮层玻璃（{len(GLASS)} 格配对，含逐字摘自 GitHub 的类名值与只挂语义属性那两块：按 CSS 缺口预测纸面、"
      "透底以后仍读得动、关档退回实心板、含浮层以外那块未被改动的负控制，"
      f"另加族不该管的 {len(GLASS_UNREACHED)} 格（{'、'.join(l for l, *_ in GLASS_UNREACHED)}）"
      "开关两趟逐字节相同），十项都落到像素上且各带负控制")
