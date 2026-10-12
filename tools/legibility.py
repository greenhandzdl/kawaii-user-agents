#!/usr/bin/env python3
"""正文可读性估算：从抽检图里挑出"平底色的一行字"，逐行量墨与纸的 WCAG 对比度。

为什么不是整块区域取中位数：真站截图里混着图片、代码块、卡片，
整块中位数会被大面积图色顶掉，量出来的其实是图片而不是字。
所以逐行先看这一行是不是"绝大多数像素都挤在同一个亮度附近"——
正文行正是这个形状（底占大头、字占小头），图行不是。
一行光够平不够：整行空白的同色比例是 1.0，比正文行还像平底色，
所以还得真有那么一撮离纸色很远的像素，才算它上面有字。

为什么配对必须逐行、不许跨行：上一版把"所有行纸色的中位"和"所有行墨色的中位"配成一对。
单一底色的站上两者几乎一样，那版本看着没问题；混合版式直接把它带偏。
当前这批图上重量的分歧（左＝全局配对，右＝逐行中位）：
  csstricks-article  裸 1.48/8.72　白天 2.42/7.97　夜晚 1.66/9.61
  mdn                夜晚全局把"纸"取到 L=0.01（自家深夜底），而它配对用的墨色里
                     混着浅底代码块的字，6.96 这个数既不是深夜底的成绩也不是代码块的成绩
那不是测量值，是在两个不同的底之间来回挑中位数。逐行配对没有这个自由度。

"这块底是谁涂的"靠重拍一张哨兵档来认，不靠颜色：把三档画布 token 扳成纯绿再拍同一页
（proxy.py 的 ?sentinel），同一坐标动了＝那块底是我们画的，没动＝站点自己的容器把底衬盖住
（kawaii-skin.user.css 第 2 节：底衬只画 html，站点容器不透明时它盖住我们）。
判定只看动了的那些行；落在站点自有底上的字算它自己的成绩，但每一跑都印出来——
它是 README 里那条"让路"约束的证据，不是脚注。
同一档还答第二问"这行字是谁涂的"：哨兵档把墨 token 一起扳绿（proxy.py 的 INK_TOKENS，
K18 那柄刀钉着它），于是"底没动、笔画芯动了"＝底是站家的、字是我们的。
让路讲的是底我们改不动；墨改得动，所以那一列是豁免区里唯一挂着账的部分。

为什么不在一张图上认颜色：连着两版都栽在"尺子是刀口"上，都是当前这批图上量到的——
  · 亮度带（±OURS_TOL）：站点近黑 (4,3,6)（L≈0.0004）落进我们深夜带 [-0.037,0.064]，
    GitHub 文档页自涂的深面板于是算进我们的成绩；站点近白 (255,253,254) 坐在浅带边外千分之几，
    一次取色抖动就能在"自家/站点底"之间来回跳。
  · 色相＋通道极差（绿最低且极差≥token 现推的 9）：吃掉了上面两个，却又把我们自己的画布
    踢出去——§3 那层 7% 叠色膜把 (255,246,250) 洗到 (255,247,250)（离 token 1 个通道、极差只剩 3），
    w3schools 白天档的接管行数随阈值在 34/7 之间跳；同时把 github-docs 白天档里
    (27,22,32) 这种**站点自己的深面板**算成我们的（白天档根本不会涂深色，判据里没有分支这一格）。
    我们自己的行离 token 最远 6 个通道，站家的深面板最近 8 个——任何绝对阈值都只是在刀口上挑一边。
颜色的差别是"差多少个通道"这种连续量，而"谁画的"是一个二值问题；二值问题要用会给出二值答案的
仪器问：改一个只影响我们自己的量，看谁跟着动。哨兵档就是这一问，它不给阈值留位置。

一行还得真"排成一排字"：光数"有多少像素离纸色够远"会把两块平色的交界当成一行字。
实测 css-tricks 那篇媒体查询指南的白天档，有 29 行对比度 1.10（其中 28 行算在皮肤接管的
底上），放大看是站点自己的米色提示框——圆角那一行里框内框外各占一片，被当作"墨"的
其实是页面白底，离纸色刚好过 GAP 那道线。字是一排孤立段，块边界是一整条连续段，
所以再加一条：离纸像素要排成至少 MIN_RUNS 段。这一刀在两个方向的假读数上都成立，
都是当前这批图上的数：同图剔掉那 29 行之后中位从 7.08 抬到 7.97；而 css-tricks 首页
"把卡片边当成字"的那 170 行剔掉之后从 1.73 掉到 1.21（那一页两档本来就都不及格，
剔掉假高行只是让它别把数字报得比实际好看）。真正文行几乎不受影响：
MDN 白天档 147 行里只有 1 行是单段，另有 14 行是两段（两张卡片并排的行）。

这道闸门有一处量不到的地方，写明白而不是藏起来：站点自己就 4.5 以下时整站豁免
（真实站的灰字我们改不动，不该记在皮肤头上），代价是这类站上皮肤造成的进一步退化也判不出来。
当前图上重量的实证：把 css-tricks 首页白天档整图向自身均值混 60%（字还在、正文行从 284
缩到 76、中位塌到 1.79），闸门仍然绿——因为该站裸页中位只有 1.20，豁免先开了火。
豁免行会在输出里点名"不计入闸门"，所以这不是静默放行，但确实是一块盲区。
破版、空页、注入失效三类不在此列，照判。

判据是"两档里至少有一档过线"，不是"每一档都得过"：皮肤带明暗开关，README 里那句
「撞上时切档」是要兑现的承诺，所以撞色的那一档不算红，但会被点名打印。
两档全塌才红——那才是"切档也救不回来"。
点名那句话必须说量到的数，而且要说的是它自己的那一档：上一版在这里写死"撞上站点自涂的
深底"，而那块底是浅的，描述反着说了一次——读数没错、判定也没错，但这句话是 README
那条约束的实例，说错了就等于把约束讲成了另一条。现在深浅是量出来的（站点底那几行的纸色中位），
一行都不在站点底上时就不编造归因。
"""
import os
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
SHOTS = HERE.parent / "shots"
X0, X1 = 0.22, 0.66          # 正文列的横向范围（避开侧栏与广告位）
Y0, Y1 = 0.10, 0.86
FLAT = 0.045                 # 与该行中位亮度差在这个范围内算"同色"
MIN_COVER = 0.60             # 一行至少有这么多比例的同色像素才当"有底色的一行"
GAP = 0.08                   # 离纸色亮度差过这个才算墨（抗锯齿的边缘带不算）
MIN_INK = 0.015              # 墨像素少于这个比例＝这行没字，是空白或纯色块
MAX_INK = 0.35               # 多于这个比例＝整行是图，不是正文
MIN_RUNS = 3                 # 离纸像素还要排成这么多段才算"上面有字"（见 measure）
MIN_ROWS = 40                # 凑不出这么多正文行就判定"采样不足"，不编数
INK_CORES = 12               # 每行取多少个"笔画芯"采样点来归因墨（见 ownership 的第三桶）
FACE_RATIO = 1.6             # 芯的亮度离本档画布 token 不到这个比＝那是我们自己涂的"面"，不是字
VARIANTS = ["bare", "day", "night"]
SKINNED = ("day", "night")   # 只有上了肤的档才有"谁涂的底"可问
FLOOR = 4.5

# 名单由 spot-check.sh 通过 KS_SITES 传进来（tag|url[|让路] 逐行），这里只消费不再抄一份：
# 报告必须点得出"这一格量的是哪个 URL"，否则换了样本而读数照旧绿，没人看得出来。
# 第三格"让路"是**样本自己声明**它是来量约束的、不是来量我们成绩的：
# 站点把正文列整片盖住时这一格根本量不到自家底（0 行），那是皮肤的真实边界、README 那条约束的
# 活证据，但留它在名单里当可读性样本就是拿量不到的格子凑绿。所以由名单而不是由闸门表态：
# 声明过才只报不判，没声明过就红，逼的是"要么换样本要么把这格说清楚"。
SITES, CONCED = {}, set()
for _ln in os.environ.get("KS_SITES", "").splitlines():
    _t, _sep, _rest = _ln.partition("|")
    _u, _s2, _f = _rest.partition("|")
    if _t.strip() and _sep:
        SITES[_t.strip()] = _u.strip()
        if "让路" in _f:
            CONCED.add(_t.strip())
if not SITES:
    sys.exit("LEGIBILITY ERROR: 名单没传进来（spot-check.sh 用 KS_SITES 逐行 tag|url 传）。"
             "报告点不出抓的是哪个 URL 的抽检没有意义，所以这里不猜默认值。")
TAGS = list(SITES)
# 列宽跟着最长的标签走：写死 16 的时候 csstricks-article（17 字）会把标签和 URL 黏成一行
W = max(len(t) for t in TAGS) + 1


def lum(rgb):
    def chan(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (chan(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a, b):
    hi, lo = sorted((a, b), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def pct(vals, p):
    v = sorted(vals)
    return v[min(len(v) - 1, int(p * len(v)))]


def canvas_face_lums():
    """每档自己的画布亮度，用来把"面"从"字"里摘出去（见 ownership 的第三桶）。

    取哪一支由 proxy.py 注入的 --kScheme 决定（day=light 支、night=dark 支），这里按同一套
    规则取；色值不抄第二份——解析器住在 check-contrast.py 的 load_tokens 里，
    legibility-controls.py 取画布色也是走这一本。

    没解析到就停，不设兜底色：那枚兜底值会流进"这是面还是字"的等值判定，把仪器断电
    印成"这一格没有我们的字"。
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("cc", str(HERE / "check-contrast.py"))
    cc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cc)
    tk = cc.load_tokens((HERE.parent / "preview" / "skin.css").read_text(encoding="utf-8"))
    out = {}
    for arm, branch in (("day", "light"), ("night", "dark")):
        lums = []
        for n in (1, 2, 3):
            key = f"canvas-{n}"
            if key not in tk:
                sys.exit(f"LEGIBILITY ERROR: preview/skin.css 里没按 light-dark() 解析到 "
                         f"--ks-{key}（{branch} 支）——'面/字'那一分没做成，"
                         f"站点底·我们的墨这一列会整列失真，不能靠兜底色继续印数")
            lums.append(lum(tk[key][branch]))
        out[arm] = lums
    return out


FACE_LUMS = canvas_face_lums()


def measure(img):
    """-> ([(纸色亮度, 该行对比度, 纸色像素坐标, 笔画芯坐标)], 有墨行数)，配对只在行内做。

    第二个数是这一趟新加的：**把 flat 那道闸摘掉之后**，还剩多少采样行"有排成段的墨"
    （墨带 + 段数两闸照旧，逐行的纸色仍取该行自己的中位）。
    它和第一个数用的是同一批采样点、同一个 MIN_ROWS 单位，唯一差别是不问"这行的底匀不匀"。

    为什么光数"有多少像素离纸色够远"不够：那会把两块平色的交界当成一行字。
    实测 css-tricks 那篇媒体查询指南的白天档，有 29 行算在皮肤接管的底上、对比度 1.10，
    放大看那几行是站点自己的米色提示框——圆角那一行里框内框外各占一片，
    被当作"墨"的其实是页面白底，离纸色刚好过 GAP 那道线。
    字是一排孤立段，块边界是一整条连续段，所以再加一条：离纸像素要排成至少 MIN_RUNS 段。
    这一刀在两个方向的假读数上都成立：同图剔掉那 29 行之后中位从 7.08 抬到 7.97，
    而 css-tricks 首页上"把卡片边当成字"的那批剔掉之后从 1.73 掉到 1.21。
    真正文行不受影响：MDN 的 146 行里只有 1 行是单段。

    坐标记的是"亮度最贴近该行中位的那个采样点"——归因要在哨兵档里回查同一个像素，
    只在中位那一格取，不取整行均值：均值会被墨拖走。

    被接受的那批行的定义一个字没改（三闸全过），只是把闸口的先后排成"墨带→段数→flat"：
    交集与顺序无关，所以第一趟和第二趟的 rows 逐字相同——这一点由"六站的中位数与行数
    改前改后一模一样"作证，不靠读代码。加 inked 计数器是因为下面那条塌版红需要一个
    **对纸的深浅不敏感**的行数（见 正文行不足 那一支）。
    """
    W, H = img.size
    px = img.load()
    xs = list(range(int(W * X0), int(W * X1), 2))
    rows = []
    inked = 0
    for y in range(int(H * Y0), int(H * Y1), 2):
        vals = [lum(px[x, y]) for x in xs]
        ls = sorted(vals)
        n = len(ls)
        paper = ls[n // 2]
        flat_ok = sum(1 for v in ls if abs(v - paper) <= FLAT) / n >= MIN_COVER
        lo = [v for v in ls if paper - v > GAP]     # 深墨：浅底站
        hi = [v for v in ls if v - paper > GAP]     # 亮墨：深底站
        side = lo if len(lo) >= len(hi) else hi
        if not (MIN_INK <= len(side) / n <= MAX_INK):
            continue
        runs = 0
        prev = False
        for v in vals:
            ink = abs(v - paper) > GAP
            if ink and not prev:
                runs += 1
            prev = ink
        if runs < MIN_RUNS:
            continue
        inked += 1                      # 字在这一行上（不问底匀不匀）
        if not flat_ok:
            continue
        paper_x = min(((abs(lum(px[x, y]) - paper), x) for x in xs))[1]
        # 取墨像素堆里靠极值那头的四分之一处：取中位会被抗锯齿边缘带拖向纸色
        ink_q = side[len(side) // 4]
        # 笔画芯＝过 GAP 的采样点里最贴近那枚墨色的前 INK_CORES 个 x 坐标。
        # 归"这行字是谁涂的"要在哨兵档回查它们：边缘带被纸色与墨色各拉一半，
        # 只有芯上的点解得开——它与 paper_x 那一问（"底动没动"）对称，问的是"墨动没动"。
        cand = [(abs(v - ink_q), x) for x, v in zip(xs, vals) if abs(v - paper) > GAP]
        cores = sorted(x for _, x in sorted(cand)[:INK_CORES])
        rows.append((paper, ratio(paper, ink_q), (paper_x, y), cores))
    return rows, inked


def ownership(img, sent, rows, face):
    """(自家底行, 站点底行, 站点底上墨也动了且不是面的行, 整格里动过的采样点数, 采样点总数)。
    同一坐标逐像素比，不看颜色。

    第二问「这行字是谁涂的」住在第三个返回值里：哨兵档把墨 token 一起扳绿（proxy.py 的
    INK_TOKENS 名单，K18 那柄刀钉着它），所以"底没动、笔画芯动了"＝底是站家的、字是我们的。
    这一桶是判定豁免区里唯一能归到我们头上的那部分——站点自涂的底我们改不动，
    可压在那片底上的墨是我们的 token，改得动就得改（README 那句"让路"讲的是底，不是墨）。
    混行按多数派归（一行里既有我们强制的链接墨又有站家自己写的字时记给占多数的那一边），
    所以它是普查数，不是逐行判定。

    第三桶只数**字**，不数"面"：动了的芯里，亮度落在本档画布三兄弟的 FACE_RATIO 以内的
    算我们自己涂的面（§99 的标题底板按出厂 α 就是实心 canvas-1，还有 §4c 那些把画布色
    垫到站点卡片上的规则），它压住的是站点底、不是把字洗掉——那一形由 ground-diff 与
    check-harmony 那两把尺管，不是"文字看不清"。
    实测这一分是必要的：六站首版普查里 github-docs 白天档 31 行「站点底·我们的墨」中位 1.78，
    逐枚放大看那批行的"墨"是 (255,237,245)／(255,207,229) 这一族＝canvas token，字本身三档都读得清；
    同批里 runoob 夜晚档那 8 行的芯是 (233,182,225)／(232,169,224)＝--ks-link 夜枝，压在站家
    浅灰 (238,236,238) 上 1.6 上下，放大看图确实糊——按亮度贴画布就把前者摘出去、把后者留下。
    这层排除只管画布族：其它面色（--ks-neutral/#4a4256 那一类）在这一列仍会被当墨，
    所以它是"少报"方向的近似，报出来的数按"至少这么多行"读。

    两趟之间唯一的差别是皮肤自己那套颜色 token（版式、圆角、时长、模糊、字体栈都不在哨兵档
    覆盖范围内，图片也没重取），所以"这个坐标的颜色变了"当得起"这块底是我们画的"；
    站点自涂的容器不读我们的 token，两张图里逐字节相同，"没变"当得起"不是我们涂的"。
    实测 mdn 白天档的分界是干净的：132 行里 117 行的纸色像素变成哨兵绿（(18,253,17) 这一族
    ——就是 #00ff00 隔着 §3 那层膜），剩下 15 行逐字节没动，它们的纸色是 (248,246,247)、
    (237,243,253)——MDN 自己的容器。

    这条等值判断怕的是另一种东西：两趟整版错位（哪怕差 1px）会让每个字的抗锯齿边缘都"变了"，
    于是噪声被读成归属。在 5 站 × 两档的这批图上按通道极差分桶量过：
    被判站点底的行偏移**恰好为 0**（393 行里 0 例外），被判自家的行 377/392 偏移 ≥8 通道、
    其余 15 行落在 3–7——没有整版位移，等值判断量到的是绘制归属而不是噪声。
    偏移 1–2 通道那种"抖一下"在这一批图上一格都没出现（出现的话分桶会显出第三个峰）。

    为什么哨兵档要扳整套颜色 token 而不只画布三档：皮肤还拿 --ks-sakura/--ks-petal/--ks-neutral/
    --ks-scrim 直接涂背景（mark 的底色、kbd 的面、遮罩、渐变面），这些不吃画布 token，
    只扳画布时它们在哨兵档里一动不动，就会被判成"站点自己涂的底"——归因朝"不怪我们"那一边错。
    名单由 proxy.py 从 skin.css 的声明形状现推，不抄第二份。

    最后那个计数只做诊断、不设红线（正文列本来就是我们的画布占大头，mdn 白天档 84% 是
    **正常读数**而不是两趟没对上，任何上限都会先把最健康的那一格判死）。两趟对不上的风险
    由出图那层挡（哨兵档和上肤档各自都要连续两张逐字节一致）加上尺寸必须相同；
    仪器失效的方向（哨兵没落地→整页一格都没变）走"动过 0 格"那条红，报得出来。
    """
    px, sx = img.load(), sent.load()
    if img.size != sent.size:
        return None, None, None, None, None
    W, H = img.size
    grid = [(x, y) for y in range(int(H * Y0), int(H * Y1), 2)
            for x in range(int(W * X0), int(W * X1), 2)]
    moved = sum(1 for x, y in grid if px[x, y] != sx[x, y])
    ours = [r for r in rows if px[r[2]] != sx[r[2]]]
    foreign = [r for r in rows if px[r[2]] == sx[r[2]]]
    # 站点底上的行里，笔画芯过半在哨兵档动了、且动了的那些芯里过半不是本档画布色
    # ＝字是我们的。芯按多数派归，混行（我们强制的链接与站家自己写的正文同在一行）
    # 会整行记给占多数的那一边。
    site_ink = []
    for r in foreign:
        y = r[2][1]
        moved_cores = [x for x in r[3] if px[x, y] != sx[x, y]]
        ink_cores = [x for x in moved_cores if min(
            ratio(lum(px[x, y]), f) for f in face) >= FACE_RATIO]
        if 2 * len(moved_cores) >= len(r[3]) and 2 * len(ink_cores) >= len(moved_cores):
            site_ink.append(r)
    return ours, foreign, site_ink, moved, len(grid)


def med(rows):
    return pct([r[1] for r in rows], 0.5) if rows else 0.0


def med_paper(rows):
    """这一档正文行的"纸"有多亮。用来把"站点自涂的底"是浅是深说清楚，
    而不是照着一个假设写死（见下面那条切档注释）。"""
    return pct([r[0] for r in rows], 0.5) if rows else None


def shown(rows):
    """行数 + 中位；空桶不印 0.00 —— med() 对空集返回 0.0 是给判定用的，
    落到输出里就成了"量到 0.00"这个压根没量过的读数。"""
    return f"{len(rows)}行 {med(rows):.2f}" if rows else "0行 —"


fails, missing = [], []
print(f"正文列 x∈[{X0},{X1}] 逐行配对；'自家底'＝该行纸色像素在哨兵档（皮肤整套颜色 token "
      f"扳成纯绿，非颜色 token 不动）里动了；"
      f"'站点底·我们的墨'＝站点底那一桶里笔画芯（该行最贴近墨色的 {INK_CORES} 个采样点）"
      f"过半动了、且动了的芯里过半亮度离本档画布三兄弟都 ≥{FACE_RATIO} 的行——"
      f"底是站家的、字是我们的，混行按多数派归，这一列也只报不判；"
      f"判定只看自家底上的行，站点底只报不判；上肤档凑不够 {MIN_ROWS} 行时先分两向——"
      f"有墨的行也不够才判「版面打散」，够则只报「底把行劈开了」不判（深浅档之间的行数比读不出塌版，见 measure），"
      f"两档尺寸不同判「归不了因」，动过比例恰为 0 判「仪器没读数」"
      f"（每档末尾印的'动过%'其余情况是这一格的诊断数，不设红线，理由见 ownership）")
for tag, url in SITES.items():
    print(f"  {tag:<{W}}{url}" + ("［名单声明：让路格，量不到自家成绩］" if tag in CONCED else ""))
for tag in TAGS:
    all_rows, buckets, moved, grid_n, inked = {}, {}, {}, 0, {}
    line = [f"{tag:<{W}}"]
    for v in VARIANTS:
        p = SHOTS / f"spot-{tag}-{v}.png"
        if not p.exists():
            line.append(f"{v:>5}=无图")
            missing.append(p.name)
            continue
        if v not in SKINNED:
            with Image.open(p) as im:
                all_rows[v], inked[v] = measure(im.convert("RGB"))
            continue
        sp = SHOTS / f"spot-{tag}-{v}-sent.png"
        if not sp.exists():
            line.append(f"{v:>5}=无哨兵图")
            missing.append(sp.name)
            continue
        with Image.open(p) as im, Image.open(sp) as sim:
            n_img, s_img = im.convert("RGB"), sim.convert("RGB")
            all_rows[v], inked[v] = measure(n_img)
            ours, foreign, site_ink, n_moved, n_grid = ownership(n_img, s_img, all_rows[v],
                                                                 FACE_LUMS[v])
        if n_moved is None:
            fails.append(f"{tag}/{v}：哨兵档尺寸 {tuple(s_img.size)} 和上肤档 {tuple(n_img.size)} 不同——"
                         f"两趟不是同一个版面，这张图归不了因")
            line.append(f"{v:>5}=尺寸不符")
            continue
        buckets[v] = (ours, foreign, site_ink)
        moved[v] = (n_moved, n_grid)
    # 归因分两头，混在一句话里就会把上游的账记到皮肤头上：
    # 裸页图压根没出＝出图环节挂了（反代没起来、上游超时、渲染没落盘），
    # 这一站的比对无从谈起，报红而不是静跳过——跳过的话名单就悄悄少了一站。
    if "bare" not in all_rows:
        fails.append(f"{tag}：裸页图没出（上游超时/渲染失败），这一站三档比对没做成")
        print("  ".join(line))
        continue
    # 裸页自己都凑不出正文行＝站点没给出可比对的正文：被反爬挡、?q= 被重定向回首页、
    # 版式不是长文，或者站点自己的样式表压根没落地。
    # "快门早于样式表"那种抖法已经由出图环节挡在外面（同一档要连续两张逐字节一致才收），
    # 所以走到这里还凑不够行，指的是"稳定地量不到正文"。
    # 这几种都跟皮肤无关，但照样报红——逼的是"重跑或换样本"，而不是换个说法把它讲没。
    if len(all_rows["bare"]) < MIN_ROWS:
        fails.append(f"{tag}：裸页凑不出 {MIN_ROWS} 行正文（站点侧：被挡/被重定向/非长文版式/"
                     f"站点自己的样式表没落地），这一站比对没做成；这一档出图时已确认过可复现，"
                     f"所以要不停在换样本，要么点名豁免")
        print("  ".join(line + [f"[{tag} 站点侧不可用]"]))
        continue

    bare = med(all_rows["bare"])
    line.append(f"bare={bare:.2f}({len(all_rows['bare'])}行)")
    verdicts, site_side, ours_by, site_by, site_ink_by = {}, {}, {}, {}, {}
    for v in SKINNED:
        if v not in all_rows:
            continue
        rows = all_rows[v]
        if len(rows) < MIN_ROWS:
            # 这一支原来只有一条出口：上肤行数比裸页少到不够 MIN_ROWS 就判"皮肤把版面打散了"。
            # 那条红拿的是**跨档的行数比**，而 flat 那道闸对纸的深浅敏感——2026-10-04 在
            # w3schools 夜晚档把掉行的成因按闸口拆开量过：flat 掉的行 night 218／day 66／bare 81，
            # 而"这一行压根没墨"掉的行 night 257 **少于** bare 309，两档被接受行的 y 跨度
            # 370..1238 里也没有成片的死窗口。也就是说深浅档之间的行数差读不出塌版，
            # 只读得出 flat 的口径差——那张图上的字一行都没丢，丢的是"这行的底匀不匀"。
            # 现在按闸口分两向，判据换成同档内的墨在不在（inked，来自 measure）：
            #   inked < MIN_ROWS ⇒ 正文列里连成片的字都数不出来 ⇒ 判红"打散"；
            #   inked >= MIN_ROWS 而被接受行不够 ⇒ 底把行劈开了，只报不判。
            # 阈值没为转绿动过：还是同一个 MIN_ROWS、同一个单位（采样行数），只是从
            # "被接受的行"换成"有墨的行"。塌版那一支照旧不进 verdicts——inked 只说字在不在，
            # 说不出对比度够不够。归因桶两种出口都登记（缺读数不许冒充结论，见 10-04 那一改）。
            note = ""
            if v in buckets:
                ours_by[v], site_by[v], site_ink_by[v] = buckets[v]
                site_side[v] = med(site_by[v]) if site_by[v] else None
                note = (f"｜自家{shown(ours_by[v])}｜站点底{shown(site_by[v])}"
                        f"｜站点底·我们的墨{shown(site_ink_by[v])}")
            if inked[v] < MIN_ROWS:
                fails.append(f"{tag}/{v}：正文列里只剩 {inked[v]} 行有墨（裸页 {inked['bare']} 行，"
                             f"要凑够 {MIN_ROWS} 行才算版面还在）——皮肤把版面打散了")
                line.append(f"{v:>5}=正文行不足({len(rows)})｜有墨{inked[v]}行{note}"
                            f"（判塌版：有墨的行也不够）")
            else:
                line.append(f"{v:>5}=正文行不足({len(rows)})｜有墨{inked[v]}行{note}"
                            f"（只报不判：底把行劈开了，见 measure 的 inked）")
            continue
        if v not in buckets:
            continue                      # 尺寸不符那支已经报过红，这里不再拿它的行做判定
        ours, foreign, site_ink = buckets[v]
        ours_by[v], site_by[v], site_ink_by[v] = ours, foreign, site_ink
        site_side[v] = med(foreign) if foreign else None
        if ours:
            verdicts[v] = med(ours)
        head = f"{verdicts[v]:4.2f}" if ours else "   —"
        line.append(f"{v:>5}={head}"
                    f"(正文{len(rows)}行｜自家{shown(ours)}｜站点底{shown(foreign)}"
                    f"｜站点底·我们的墨{shown(site_ink)}"
                    f"｜动过{moved[v][0] / moved[v][1]:.0%})")
    # 哨兵档一个点都没动＝这一页正文列从上到下都是站点自己涂的底，皮肤一行都没画到。
    # 这一格当不了可读性样本（绿的是站点自己的排版），所以默认红；名单里声明过"让路"的
    # 那一格例外——它是 README 那条约束的活证据，报数不判。0 不是阈值，是结构。
    # 但"量不到"有两种成因，先分开：整页一格都没动（动过比例恰为 0）是哨兵重拍没通电，
    # 那不是让路、是仪器没读数，任何名单声明都救不了它；整页动了、只有正文列没动才是让路。
    measured = [v for v in SKINNED if v in buckets]
    dead = [v for v in measured if not ours_by.get(v) and moved[v][0] == 0]
    yielded = [v for v in measured if not ours_by.get(v) and moved[v][0] > 0]
    if dead:
        fails.append(f"{tag}：{'、'.join(f'{v} 档整页 {moved[v][1]} 个采样点动过 0 个' for v in dead)}——"
                     f"哨兵重拍一格都没变，正文行里没有一行是皮肤涂的底。这是归因仪器没读数，"
                     f"不是让路（名单声明挡不住这条红）：重跑或查反代")
    elif measured and not verdicts:
        msg = (f"{tag}：{'、'.join(f'{v} {len(all_rows[v])}行' for v in measured)} "
               f"正文行里没有一行是皮肤涂的底（整格动过 "
               f"{'、'.join(f'{v} {moved[v][0]}/{moved[v][1]} 格' for v in measured)}）")
        if tag in CONCED:
            line.append(f"[{msg}——名单声明的让路格，站点底读数只报不判]")
        else:
            fails.append(msg + "——量不到皮肤自己的成绩：换样本，或在名单里把这格声明成让路格")
    # 判"这站本来可读、上了肤之后没有任何一档能读"。皮肤带一个明暗开关，
    # README 里那句「撞上时切档」是要兑现的承诺，所以两档各报各的数、有一档过线就不判红；
    # 没过的那一档照样点名打印——它是那条约束的实例，不是被抹平的读数。
    # "至少有一档过线"要成立的代价在这里：一档让路（正文列整片被站点容器盖住、我们一行都没涂到）
    # 时，判定只由另一档出，并当场点名"这一档在这一格没有成绩也没有惩罚"。
    # 上一版把这判红，理由是不许"拿另一档的缺席替它背书"——那句适用于**量到了却塌了**的档；
    # 0 行的档根本没有数可拿，替它背书的是站点自己的容器，不是我们。
    if yielded and verdicts and tag not in CONCED:
        other = "、".join(verdicts)
        line.append(f"[{tag}/{yielded[0]} 这一档在正文列一格自家底都没涂到"
                    f"（{len(all_rows[yielded[0]])} 行全落在站点自涂的底上，整格动过 "
                    f"{moved[yielded[0]][0]}/{moved[yielded[0]][1]} 格）——这一格只由 {other} 档出判定]")
    # 豁免的证据要落在"站点自己涂的底"上，不能只信参考档那一张。
    # 实测过的假绿：css-tricks 首页的裸页拍在了站点样式表落地之前（正文中位 1.81），
    # "站点本身不可读"于是先开火，把整站判定吞掉——而同两张上肤图里站点自有底上的行是 6.62/6.78，
    # 皮肤两档其实都过线。站点底那几行长在上了肤的图上，皮肤没接管它，它就是站点自己的成绩。
    proved = [m for m in site_side.values() if m is not None]
    if bare < FLOOR:
        if proved and max(proved) < FLOOR:
            line.append(f"[{tag} 站点自有底上只有 {'、'.join(f'{v} {m:.2f}' for v, m in site_side.items() if m is not None)}"
                        f"<{FLOOR}（裸页 {bare:.2f} 同向），不计入闸门]")
        elif proved:
            fails.append(f"{tag}：裸页参考档只有 {bare:.2f}，可上肤图里站点自有底上的行有 "
                         f"{'、'.join(f'{v} {m:.2f}' for v, m in site_side.items() if m is not None)}"
                         f"——两边对不上，参考档多半拍在了站点样式表落地之前，"
                         f"这一站的破版比对不成立，重跑或换样本")
        else:
            # 两档里没有一行落在站点自涂的底上：整页底都被接管，站点自己的成绩在这两张图上量不到，
            # 只能退回参考档。写明白这是"只有参考档作证"，而不是装作量过站点自有底。
            line.append(f"[{tag} 站点本身 {bare:.2f}<{FLOOR}，不计入闸门"
                        f"（两档无站点自有底的行，仅由参考档作证）]")
    elif verdicts and all(v < FLOOR for v in verdicts.values()):
        fails.append(f"{tag}：裸页 {bare:.2f} 可读，量到自家底的 {len(verdicts)} 档全塌（"
                     + "、".join(f"{k} {v:.2f}（{len(ours_by[k])}行）" for k, v in verdicts.items()) +
                     f"），切档也救不回来")
    elif len(verdicts) == 2 and min(verdicts.values()) < FLOOR:
        bad = min(verdicts, key=verdicts.get)
        good = [k for k, v in verdicts.items() if v >= FLOOR][0]
        # 这一句的归因必须由量到的数撑起：塌的那一档自家底上有几行、站点底有多亮。
        # 上一版在这里写死了"撞上站点自涂的深底"，而那一档实测纸色 L≈0.83——站点在自己的
        # 容器上涂的是浅底，我们的夜晚底衬被它盖住，于是"深底"反着说了一次。
        # 现在深浅是量出来的，站点底一行都没有时就不编造归因，只报数。
        fp = med_paper(site_by.get(bad) or [])
        side = "" if fp is None else f"；同一档站点自涂的底上 {len(site_by[bad])} 行" \
                                    f"（纸色 L≈{fp:.2f}，{'浅' if fp >= 0.5 else '深'}），那部分只报不判"
        line.append(f"[{tag}/{bad} 自家底上 {verdicts[bad]:.2f}<{FLOOR}"
                    f"（{len(ours_by[bad])}行）{side}，{good} 档 {verdicts[good]:.2f} 过线——切到{good}档读]")
    print("  ".join(line))

if missing:
    print(f"\n注意：缺图 {missing}，上面的判定没覆盖到这些变体")
if fails:
    print("\nLEGIBILITY FAIL")
    for f in fails:
        print("  - " + f)
    sys.exit(1)
judged = [t for t in TAGS if t not in CONCED]
print(f"\nLEGIBILITY PASS：{len(judged)} 站都至少有一档在自家底上取到了正文行"
      f"（另一档让路的格已逐格点名），且裸页可读的站上肤后量到的那一档仍过 4.5"
      f"（逐行估算，不是逐字形测量；'站点底'那一档是皮肤刻意让路的部分，"
      f"只报不判，它是 README 那条约束的证据）"
      + (f"；另有 {len(CONCED)} 格按名单声明只报让路读数" if CONCED else ""))
