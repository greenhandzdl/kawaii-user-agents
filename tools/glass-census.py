#!/usr/bin/env python3
"""浮面普查：六站各自有多少个可见的 fixed/sticky 面真的穿上了 §4c 的玻璃。

只出一条判定（全名单玻璃归零＝族在真站整体失效），其余全出数——今天先要的是
"这一格现在长什么样"，不是又一道 PASS/FAIL。
它要补的那一格空白是：玻璃族靠类名词根认成员，站点把类名一改，玻璃就静默少一块，
而现场没有任何尺子在看这件事（M01–M06 那六柄刀割的是 CSS 里的词根本身，
夹具里那块面照样在——它们量不到真站）。

名单从 tools/spot-check.sh 的 SITES 取，不抄第二份（和 legibility-controls.py 同一条规矩）。
判"穿上玻璃"在页面里按**涂到的效果**认，不按"族的选择器匹不匹得上"认——
后者要在这里再抄一份族名单，抄本迟早和 §4c 那四份逐字副本分家。判据原文在
tools/proxy.py 的 GLASS_PROBE。

够不着的四条（都量过或点名过，不是"也许"）：
  1. 脚本被代理摘掉 —— 站点用 JS 现造的浮层在这一档里根本不存在。证据：runoob 的
     `runoob-nav-drawer`/`bm-panel` 在缓存的原始正文里出现 0 次，而上一轮开着脚本的
     MCP 普查数到它们（那站 4 块 vs 这里 1 块）。所有下拉、弹层、遮罩同理不在场内，
     所以"GitHub 首页 0/2"说的是它**静息版面**，不是用户点开菜单后看到的那一块。
  2. shadow root 里的元素拿不到（querySelectorAll 不下钻，--dump-dom 也不展开）。
  3. 视口比名义窗口矮 87px：--window-size=1280,1500 时 innerHeight 读 1413，
     1280,1000 时读 913（两点都实测）。而 spot-check.sh 出的 PNG 是 1280×1500 ——
     所以这一档看到的版面比抽检图矮一截，只活在底部那 87px 里的面会漏。
  4. 加载时还藏着的块不算：w3schools 的 `#scroll_right_btn` 在原始正文里有 7 处，
     这次判据没数到它 —— **它为什么没进名单这一轮没量**，别当成"它是 JS 造的"。

【衬底】这一格是后加的，判据先落在字上再跑（写法在下面，跑之前没有任何数）：
「下面衬托粉色」这句话到今天只有**上肤后画布被我们接管了几成**那一格（哨兵档量的），
没有一句话说清**每一块玻璃底下第一层涂底的是谁**。探针因此多带两格：`und`（往上数
三层涂了底的祖先，标记哪一层是 html／body）和 `ink`（这块面上真在生效的计算墨色，
不是 token 原文——族给 color 没写 !important，站点顶得掉）。
读法，三条，都不许在看完数之后改：
  · 把 `bg`（我们的玻璃层）按 α 依次合成在 `und` 第一、第二、第三层上，最底仍带透的
    合成到浏览器默认白底。得出「合成面底色」。
  · 判据只有一个：**这块面的计算墨色对合成面底色 ≥ 4.5**。4.5 不是新钉的数，
    它就是 tools/check-contrast.py 里 `"ink-1"` 那一格（AA 正文线），这里引用不重抄。
    只判**面上有可见文字**的那几块（`txt > 0`）：这一问是"读不读得动"，一块没字的面上
    那个 `color` 没有读者，拿它报红是把仪器读成产品；没字的块单独计数并印出来。
  · `und` 里出现 `img:` 前缀的那一块**不判**（图没法当纯色合成，硬合成等于造一个不存在
    的底），单独计数并点名；`und` 为空（一路到根没人涂底）的按白底判。
    这一条**跑第一趟就改过**，改在还没有任何被判过的数之前（day 档那一跑判了 0 块，
    没有读数被它污染），改的理由是它把要问的那一格筛掉了：我们自己的皮肤把粉地面
    （`--ks-ground` 那一条 160° 渐变）画在 `html`（带 `!important`）和 `:where(body)` 上，
    所以 `own` 那一层带 `img:` 恰恰就是「下面衬着粉」本人，不是站点的图。
    现在的形状：涂了底的**第一层**若是 `own` 且带图，就按我们那三条渐变停靠
    （canvas-2 → canvas-1 → canvas-3）各合成一次、**取最低那一格**报（渐变是整面覆盖的实心色，
    所以取三档里最差的就是保守界）；若是**站点容器**画的图，仍然不判并点名。
    值域：三条停靠不抄第二份，从探针页真加载的 `preview/skin.css` 用 check-contrast 的
    `load_tokens` 解，档由这一跑的 `bodyScheme` 选。
  · 只有**挡住下面那层的不透明底**解不开时才整块不判；它之上的半透明层照旧逐层合成。
    `?noskin` 对照档**整格不判**：那一跑里满足玻璃谓词的块是站家自己涂的，墨色也是它的，
    判它等于用我们的 AA 去量别人的设计。
  · §3 那层 7% 叠色膜**不在这份模型里**：它整页同强度、对分子分母同乘，
    这一格又是它已被单独量过的那一层（#28/#29），混进来只会让两个数互相遮掩。
这一格填的是 #35 结账时点名的仪器债：让路边界的依据（最坏可达底仍 8.35/9.54）当时是
一次性手算，落在这儿才有常驻尺子。rc 的语义因此加了一条：原来 1 只表示"族整体归零"，
现在"任一块合成后墨色不到 AA"同样让 rc=1，两句话各印各的、不合并成一句。

用法：python3 tools/glass-census.py [--window=1280x1500] [--theme=day|night]
                                     [--only=tag[,tag]] [--json] [--noskin]
                                     [--extra=tag|https://url[,tag|https://url]]
--extra 只给**这一跑**临时加站，不动 tools/spot-check.sh 那份名单——那份是抽检、
        暖机、计算样式、两条普查共用的单一来源，为一次探索改它会牵动五把尺子
        （上一轮换名单就是在那一处动的，抓到 5 处仪器自身的坏）。
        后果要读对：extra 进来的站与名单站**同进一条判定的分母**（名册＝名单∪extra），
        表头逐站点名哪几枚是 extra。JS 现造版面的站（这一档看不见 JS 造的浮层，见抬头
        够不着那条第 1 点）会在这一档读成"0 块浮面"，那是仪器的边界不是皮肤失效——
        所以 extra 那几站的读数只用于**看形状**（有没有浮面、底下衬的是谁、穿上玻璃几块），
        不进 README 的结论，也不单独当"族失效"的证据。
--selftest 只跑【衬底】那格的正控制（四份合成人面，不开浏览器、不起代理）：
        A 空底配我们的墨＝必须 ok；B 站点白字顶掉我们那一门＝必须 low；
        C 底下是我们自己那面粉地面（带渐变图）＝必须进判定，不许被 img: 筛掉；
        D 站点容器画的图＝必须不判。四支里任何一支走错，rc=1。
        它管的是"绿能不能变红"，与真站读数无关。
--noskin 是**对照档**：同一页同一条链路，皮肤与面板档都不注入，只留探针。
        它量的是"关掉我们还剩几块玻璃"＝站点自涂的那一成；「穿上玻璃 N」减去它才是族净增。
        这一档不出"族落到了地"那条判定（0 块族玻璃在这里是设计如此，不是失效）。
环境变量：KS_CENSUS_PORT（默认 8748）、KS_CENSUS_TIMEOUT（默认 45000ms）
"""
import hashlib
import html
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPOT = ROOT / "tools" / "spot-check.sh"
PROXY = ROOT / "tools" / "proxy.py"
# AA 线不抄第二份：那条 4.5 住在 check-contrast.py 的 REQUIRED["ink-1"]，
# 这里 import 来引用。用 spec_from_file_location 是因为文件名带连字符，不是包内模块。
_spec = importlib.util.spec_from_file_location("_cc", ROOT / "tools" / "check-contrast.py")
cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cc)
# 加载的必须是那个模块本身：check-contrast 有 __main__ 守卫，所以 import 不会顺手跑一遍
# 可读性闸门；万一它哪天没了守卫，这一行会先炸而不是让普查安静地多跑一道闸门。
assert callable(cc.rel_lum) and callable(cc.contrast)
AA = cc.REQUIRED["ink-1"]
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = int(os.environ.get("KS_CENSUS_PORT", "8748"))
BASE = f"http://127.0.0.1:{PORT}/s/"
# ?noskin 对照档在**模块层**读一次：逐站那一格和收尾那条判定都要看它，
# 两处各读各的 argv 迟早分家（判定和读数不一致时，报出来的那句就替另一句作保了）。
NOSKIN = "--noskin" in sys.argv
# 出图那边的 20s 是给"同一张图连拍要逐字节一致"用的；这一档不比像素，把上限抬高
# 只花墙钟。照抄 20000 时 css-tricks 那格四跑里两跑读不到探针输出。2026-10-01 做过
# 单变量对照（同一格、同一份缓存、每跑之前先等过 60s 的失败负缓存）：
# 上限 45s 那跑读到了数（浮面 0），上限 20s 那跑读不到探针输出，两跑 DOM 都是 212756 字符
# ——只差那个 <output>，所以是 load 落在 20s 与 45s 之间。为什么落在那儿没单独证：代理注释里
# 记着那篇挂着两条死链、每条等满 10s 上游上限，撞线跟这个假设相符，但这一跑没把它隔离出来。
DUMP_TIMEOUT_MS = int(os.environ.get("KS_CENSUS_TIMEOUT", "45000"))


def sites():
    """[(tag, url)]，逐字取 spot-check.sh 的 SITES 段。"""
    src = SPOT.read_text(encoding="utf-8")
    m = re.search(r'^SITES="\n(.*?)"$', src, re.S | re.M)
    if not m:
        sys.exit(f"CENSUS ERROR: 没按 `^SITES=\"` … `^\"` 从 {SPOT.name} 取出名单——"
                 "名单的写法变了要同时改这里，别退回抄第二份")
    out = []
    for line in m.group(1).splitlines():
        if "|" not in line:
            continue
        tag, url = line.split("|")[0], line.split("|")[1].strip()
        out.append((tag, url))
    if len(out) < 2:
        sys.exit(f"CENSUS ERROR: 只取出 {len(out)} 站，名单不可能这么短")
    return out


def parse_extra(extra_src, roster, err="CENSUS ERROR"):
    """把 --extra=tag|url[,tag|url] 解成 [(tag, url)]。两档普查共用这一份定义。

    加进来的形状要当场验，因为 tag 和名单重名时 report() 打的行、以及"哪一站是借来的"
    这件事都会分不开（读数会串成一站）。roster 由调用方传进来（root-census 用的也是
    sites()，但它那侧的名字是 gc.sites()，这里不现取第二趟）。
    """
    out, seen = [], []
    for item in [x for x in extra_src.split(",") if x.strip()]:
        if "|" not in item:
            sys.exit(f"{err}: --extra 要写成 tag|https://… 这一形，收到 {item!r}")
        t, u = [x.strip() for x in item.split("|", 1)]
        if not t:
            sys.exit(f"{err}: --extra 的 {item!r} 缺 tag")
        if not re.match(r"^https?://[^/]", u):
            sys.exit(f"{err}: --extra 的 {t} 那枚 URL 不是 http(s) 绝对地址：{u!r}")
        if t in {s[0] for s in roster} or t in seen:
            sys.exit(f"{err}: --extra 的 tag {t} 与名单或另一枚 extra 重名，"
                     "两行的读数会分不开")
        seen.append(t)
        out.append((t, u))
    return out


def start_proxy():
    """已经在跑就借它的（spot-check.sh 自己会留一个在 8748）；没跑就现起一个，走人时关掉。

    借不借都记一笔：普查读数要能归到"它读的是哪一份 skin.css"，
    而代理在启动那一刻把 preview/skin.css 读进内存（SKIN 是模块级常量），
    借来的那只可能带着上一代 CSS 在跑。所以借之前先比对它起得来不来得。
    """
    if reachable():
        return None
    p = subprocess.Popen([sys.executable, str(PROXY), str(PORT)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    for _ in range(40):
        if reachable():
            return p
        time.sleep(0.25)
    p.terminate()
    sys.exit(f"CENSUS ERROR: 反代在 :{PORT} 起不来")


def reachable():
    return subprocess.run(["curl", "-sf", "-m", "2", f"http://127.0.0.1:{PORT}/healthz"],
                          capture_output=True).returncode == 0


def dump(url, window, oid="ks-glass"):
    """跑一次 headless Chrome 的 --dump-dom，取回 <output id="ks-glass"> 里的 JSON。

    `oid` 由 ?rootprobe 那一档共用（同一套出图参数、同一条"没落位"的报错形状），
    默认值就是普查自己那档，所以两档不会各自漂出一份取数逻辑。
    不带 --virtual-time-budget：spot-check.sh 里那条测量已经写明虚拟时钟遇到吊着的
    第三方请求就不往前走（同一 URL 实测 70s 没吐出文件，去掉它 4s 出图）。
    """
    r = subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
         f"--window-size={window}", f"--timeout={DUMP_TIMEOUT_MS}", "--hide-scrollbars",
         "--allow-file-access-from-files", "--dump-dom", url],
        capture_output=True, text=True,
    )
    m = re.search(rf'<output id="{re.escape(oid)}"[^>]*>(.*?)</output>', r.stdout, re.S)
    if not m:
        # 不带 stderr：rc=0 且正文几十万字符时，那几行 CVDisplayLink 噪声跟"探针没跑起来"
        # 没有因果关系，把它打进读数里就等于给一个没证过的因。
        if len(r.stdout) < 4000:
            # 正文只有这么点＝这一页根本没画出来，"load 没触发"是错的因。现量过一轮：
            # 这种形状对应的都是上游那一跳（zh.wikipedia 与 old.reddit 是 504 本机取不到，
            # stackoverflow 是 502 站点自己答 403），跟探针挂在 load 上无关。
            return None, (f"dump-dom rc=0，正文只有 {len(r.stdout)} 字符——这一页根本没画出来，"
                          f"里面自然没有 {oid}。不是「load 没触发」：先用 curl 走同一条反代跳看是"
                          "504（本机这一跳没走到头）还是 502（站点答的就是 404/403 之类）")
        return None, (f"dump-dom rc={r.returncode}，DOM {len(r.stdout)} 字符已吐出，"
                      f"但里面没有 {oid} —— load 在 "
                      f"{DUMP_TIMEOUT_MS // 1000}s 内没触发，探针挂在 load 上")
    try:
        return json.loads(html.unescape(m.group(1))), None
    except Exception as e:
        return None, f"{oid} 里的 JSON 解不开：{e}"


def _nums(body, hi):
    """按 hi 的值域解三个通道＋可选 α：hi=255 给 rgb()，hi=1 给 color(srgb)。
    带 % 的按百分比走，不带的小数/整数按该形的原生值域。解不出返回 None。"""
    p = [x for x in re.split(r"[,\s/]+", body.strip()) if x]
    if len(p) < 3:
        return None
    try:
        v = [float(t[:-1]) / 100 * 255 if t.endswith("%")
             else (float(t) if hi == 255 else float(t) * 255) for t in p[:3]]
        a = 1.0
        if len(p) > 3:
            a = float(p[3][:-1]) / 100 if p[3].endswith("%") else float(p[3])
    except ValueError:
        return None
    return (v[0], v[1], v[2], min(1.0, max(0.0, a)))


def parse_c(text):
    """计算色 → (r,g,b,a)，通道 0–255、α 0–1。只认 rgb()/rgba() 与 color(srgb …) 两形；
    解不出返回 None——宁可少判一块，也不拿猜出来的色去合成。"""
    if not text:
        return None
    t = " ".join(str(text).split())
    for pat, hi in ((r"rgba?\(([^)]*)\)", 255), (r"color\(srgb\s+([^)]*)\)", 1)):
        m = re.fullmatch(pat, t)
        if m:
            return _nums(m.group(1), hi)
    return None


WHITE = (255.0, 255.0, 255.0)


def stack(layers):
    """layers[0] 是最上面那一层，依次往下，最底垫浏览器默认白。累加器始终是实心色，
    所以每一层就是 `l*a + 下*(1-a)`——这就是"那 14% 的透孔里透上来的到底是什么"。"""
    out = WHITE
    for c in reversed(layers):
        r, g, b, a = c
        out = (r * a + out[0] * (1 - a), g * a + out[1] * (1 - a),
               b * a + out[2] * (1 - a))
    return tuple(round(x) for x in out)


def sig_of(f):
    return f"{f['tag']}{'#' + f['id'] if f['id'] else ''}" \
           f"{('.' + f['cls']) if f['cls'] else ''}"


_TOKS = None
GARDEN = ("canvas-2", "canvas-1", "canvas-3")   # --ks-ground 的三条停靠，按渐变里的顺序


def canvas_colors():
    """我们那面粉到底是哪三个值。不抄第二份：从探针页真加载的 preview/skin.css 里用
    check-contrast 的 load_tokens 解。惰性——root-census import 本模块时不该顺手解一遍 CSS，
    而 load_tokens 解不出是要 die() 退出的，放在模块层会把那条 import 变成一道闸门。"""
    global _TOKS
    if _TOKS is None:
        src = (ROOT / "preview" / "skin.css").read_text(encoding="utf-8")
        _TOKS = cc.load_tokens(src)
        for k in ("canvas-1", "canvas-2", "canvas-3"):
            if k not in _TOKS:
                sys.exit(f"CENSUS ERROR: preview/skin.css 里解不出 --ks-{k}，"
                         "衬底那一格归不了因（渐变停靠的候选值没了）")
    return _TOKS


def resolve_backdrop(f, branch):
    """找"挡住玻璃那 14% 透孔的第一层"。返回 (候选链列表, 归因文字, 不可判的原因)。
    候选链 >1 条时只发生在 our-own 那一格：我们的粉地面是一条整面覆盖的渐变，
    取值域内的最差停靠当保守界（抬头那条读法）。"""
    toks = canvas_colors()
    prefix = []
    for u in f.get("und") or []:
        raw = str(u.get("b", ""))
        img = raw.startswith("img:")
        solid = parse_c(raw[4:] if img else raw)
        own = bool(u.get("own"))
        if solid is None:
            return None, None, f"底解不开：{raw[:36]!r}"
        if own and img:
            # `own` 只等于"这一格住在 html/body"，**不等于**"这一格是我们的粉地面"。
            # 站点常把实心底涂在 body 上、再压一条全透明的图（docs.github.com：
            # body{background-color:rgb(0,0,0)} ＋ linear-gradient(transparent,transparent)）——
            # 那条图什么也没画，透上来的是它自己的实心色。拿我们的 token 停靠替换它，
            # 就会把"底下衬的是站家黑"印成"底下衬我们的粉"，比值跟着算错。
            if solid[3] >= 1.0 and not any(cc.close(solid[:3], tuple(toks[k][branch]))
                                           for k in GARDEN):
                return [prefix + [solid]], (f"站点自涂的 {u['t']}（实心底压在它自己那条图上，"
                                            "透不出我们那面粉）"), None
            who = ("我们的粉地面（" + ("html" if u["t"] == "html" else "body") + "）")
            return ([prefix + [tuple(c for c in toks[k][branch]) + (1.0,)] for k in GARDEN],
                    who, None)
        if img:
            return None, None, (f"底下是站点画的图 <{u['t']}"
                                f"{'#' + u['i'] if u['i'] else ''}.{u['c'][:34]}>")
        if own:
            ours = any(cc.close(solid[:3], tuple(toks[k][branch])) for k in GARDEN)
            who = (("我们的画布（" + ("html" if u["t"] == "html" else "body") + "）")
                   if ours else f"站点自涂的 {u['t']}（值不是我们那三个之一）")
        else:
            who = (f"站点容器 <{u['t']}{'#' + u['i'] if u['i'] else ''}"
                   f".{u['c'][:34]}>")
        if solid[3] >= 1.0:
            return [prefix + [solid]], who, None
        prefix.append(solid)
    return [prefix + [(255.0, 255.0, 255.0, 1.0)]], "一路没人涂底（按默认白判）", None


def attr_of(f, branch):
    """只问"底下第一层是谁"，不算比值——面上没字的那几块也要进这张归因表，
    它们证不了"读得动"，但完全答得了「衬的是不是我们的粉」。"""
    cands, who, err = resolve_backdrop(f, branch)
    return who if cands else err


def branch_of(data):
    return "dark" if "dark" in str(data.get("bodyScheme") or "") else "light"


def judge(f, branch):
    """按抬头那条预注册读法算一块玻璃面的合成底色与墨色对比。
    返回 (状态, 文字, 比值或 None)：状态在 ok / low / img / noink / parser 里取一个，
    只有 ok 与 low 带可信比值。"""
    if f.get("und") is None or f.get("ink") is None:
        return "parser", "探针没带 und/ink 那一格（旧形状）", None
    ink = parse_c(f.get("ink"))
    if ink is None:
        return "noink", f"墨色解不开：{f.get('ink')!r}", None
    top = parse_c(f["bg"])
    if top is None:
        return "parser", f"面底解不开：{f['bg']!r}", None
    cands, who, err = resolve_backdrop(f, branch)
    if not cands:
        return "img", err, None
    rs = [(cc.contrast(ink[:3], stack([top] + ch)), ch) for ch in cands]
    r, worst = min(rs, key=lambda x: x[0])
    extra = "" if len(cands) == 1 else f"（三档停靠里取最低那格，另两档 " \
        f"{'、'.join(f'{x[0]:.2f}' for x in sorted(rs, key=lambda y: y[0])[1:])}）"
    face = stack([top] + worst)
    return ("ok" if r >= AA else "low"), \
        (f"合成 #{face[0]:02x}{face[1]:02x}{face[2]:02x} 墨 {f['ink'][:22]} → "
         f"{r:.2f}:1｜第一层={who}{extra}"), r


def buckets(faces):
    """衬底那张表分两栏，**划分只住这一格**：逐块打印、汇总两栏、selftest 的分区断言
    判的是同一份定义（判据双写，"防呆"用例就变成自我测试）。
    族外那一栏是 2026-10-06 补的盲区：旧代码在 `if not f["glass"]` 就整块跳过，一块浮着
    而没被词根收进玻璃族的面，底下一样是我们的粉地面、字一样要读得动，却两把尺都不管
    （GitHub 仓库页现读到一块 74 字的粘滞面，那一跑印的是「判 0 块」）。"""
    return ([f for f in faces if f["glass"]], [f for f in faces if not f["glass"]])


def ground_tally(rows, which):
    """对一栏面跑同一份衬底归因＋合成判读，返回 (归因直方图, 判到的, 面上 0 字, 算不出)。
    which 取 buckets() 的第几栏——两栏共用这条代码，所以"族外有没有被漏判"这类错
    只可能出在 buckets 那一格，不会出在这里抄漏一支。"""
    hist, res, notext, skipped = {}, [], [], []
    for r in rows:
        br = branch_of(r)
        for f in buckets(r["faces"])[which]:
            who = attr_of(f, br)
            key = ("我们的粉地面" if "粉地面" in who else
                   "我们的画布" if "我们的画布" in who else
                   "站点自涂的根" if "站点自涂" in who else
                   "站点容器" if "站点容器" in who else
                   "没人涂底" if "没人涂底" in who else "不可判")
            hist[key] = hist.get(key, 0) + 1
            if f["txt"] <= 0:
                notext.append((r["tag"], f))
                continue
            st, msg, ratio = judge(f, br)
            if st in ("ok", "low"):
                res.append((r["tag"], f, st, msg, ratio))
            else:
                skipped.append((r["tag"], f, st, msg, ratio))
    return hist, res, notext, skipped


def report(tag, data, err):
    if err:
        print(f"  {tag:18} ⚠ 量不到：{err}")
        return None
    if not data.get("tok") and not NOSKIN:
        # 皮肤 token 没解出来＝这一页没上肤，"0 个浮面"是这条链路的故障不是站点的事实
        print(f"  {tag:18} ⚠ 皮肤没上（--ks-canvas-1 空），这次的数不算")
        return None
    if data.get("tok") and NOSKIN:
        # 对照档的反面：--noskin 这一跑的皮肤 token 必须是空。它非空＝代理没按 ?noskin 办事
        # （多半是借到了补丁前的代理，那一版根本不认这一档），读数会混进自家的玻璃。
        print(f"  {tag:18} ⚠ 对照档里皮肤却上了（--ks-canvas-1 非空），这一站的数不算"
              "——代理大概是补丁前的那一代")
        return None
    faces = data["faces"]
    if any("und" not in f or "ink" not in f for f in faces):
        # 旧代理（补丁前那一份）不带这两格。缺格按链路断处理，不按读数处理：
        # 让 judge() 把它判成 parser 也能印一排字，但那一排字和"这站真的没涂底"在表上长一样。
        print(f"  {tag:18} ⚠ 探针是旧形状（面记录里没有 und/ink 那一格），这一站的数不算"
              "——多半是借到了补丁前的代理")
        return None
    g, _of = buckets(faces)
    br = branch_of(data)
    print(f"  {tag:18} 浮面 {len(faces):2}／穿上玻璃 {len(g):2}"
          f"   ({data['vw']}×{data['vh']}，解档 html={data.get('htmlScheme')}"
          f" body={data.get('bodyScheme')}→取 {br} 支)")
    for f in faces:
        mark = "玻璃" if f["glass"] else "  — "
        print(f"      {mark} {f['pos']:6} {f['w']:4}×{f['h']:<4} y={f['y']:<5}"
              f"字{f['txt']:5} <{sig_of(f)}>")
        print(f"           bg={f['bg']}  bf={f['bf']}  盖{f['cover']}%")
        if NOSKIN:
            # 对照档那一跑没有我们的粉地面可衬，族外那一栏同样不判——整跑形状与补洞前逐字相同
            if not f["glass"]:
                continue
            print("           衬底：对照档整格不判（那一跑满足谓词的玻璃是站家自己涂的）")
            continue
        lbl = "" if f["glass"] else "·族外"
        if f["txt"] <= 0:
            print(f"           衬底{lbl}：面上 0 字，不判比值｜第一层={attr_of(f, br)}")
        else:
            st, msg, _ = judge(f, br)
            print(f"           衬底{lbl}[{st}] {msg}")
    return {"tag": tag, **data}


def verdict(rows_n, gl, noskin, full_n, picked_n):
    """这一条判定抽成纯函数：main 打印它，selftest 也判同一份定义——判据只住一处。

    为什么要抽：2026-10-04 github-home 单站那一跑（浮面 2／穿上玻璃 0）印出了
    「族在名单圈到的站内整体失效」，可它的名册被 --extra 缩到 1 站，而"整体失效"说的是
    全名单那六站。拿缩过的名册出全名单的结论是口径错：那一跑那两块面一块是站点自己
    常驻的营销页头（盖 165%，子孙把面涂满了，上了玻璃也看不见），一块是 fixed 的正文
    hero（不是浮层 chrome）——两块都够不着这条判定要说的事。
    现在缩过名册就不出这条判定，和 ?noskin 对照档、"一站都没量到"那两支同一个理由：
    仪器读不到对象时不许替产品说话。全名单那支一个字没动，selftest 的 V1/V2 那一对
    除名册宽窄之外没有第二个变量。
    """
    if rows_n == 0:
        # 一站都没量到＝这条链路自己坏了，不是"皮肤没落地"。报 2 而不是 1，
        # 免得读 rc 的人把链路故障读成判定；这一支必须不出判定，
        # 否则"没量到"会同时印出 OK 和 ERROR（实测踩过）。
        return 2, "CENSUS ERROR：一站都没量到（链路问题，不是族失效），这一跑不出判定"
    if noskin:
        # 对照档**不出**"族落到了地"那条判定：这一跑压根没挂皮肤，"族玻璃 0 块"是设计如此，
        # 拿它报"整体失效"就是把仪器读成产品。它唯一的读数是 gl——皮肤摘掉后仍然满足
        # 玻璃谓词的块数＝站点自涂的那一成，上肤档那句「穿上玻璃 N」减去它才是族净增。
        return 0, (f"CENSUS 对照档（?noskin）：{rows_n} 站浮面里皮肤摘掉后仍带玻璃谓词的 {gl} 块"
                   "＝站点自涂，不计给族；『族在真站上落到了地』这一条在本档不适用")
    if gl == 0 and picked_n < full_n:
        return 0, (f"CENSUS ⚠ 不适用：这一跑名册被缩到 {picked_n} 站（全名单 {full_n} 站），"
                   "而「整体失效」要说的是全名单——缩过的名册不出这条判定；"
                   "要看这一站自己有没有浮层，读上面那张逐站表")
    if gl == 0:
        # 措辞按"这一跑的名单"说，不按"真站"说；能走到这一支说明名册没被缩过（上一支挡着）。
        return 1, (f"CENSUS ⚠：这一跑的 {rows_n} 站浮面上一块玻璃都没落上"
                   "——族在名单圈到的站内整体失效")
    return 0, ("CENSUS OK：族在真站上落到了地（这条只拦整体归零；某站少一块不报，"
               "要盯每站块数得先有金样本——见抬头）")


def selftest():
    """【衬底】那格的正控制：不开浏览器、不碰网络，喂 judge() 两份合成人面，
    一份必须判 ok、一份必须判 low。为什么要有这一格：玻璃自己那层是 86% 不透明的画布色，
    墨又是我们那一门，合成下来比值几乎不可能掉到 4.5 以下——所以这一格的绿**天生可疑**，
    它可能只是"判据结构性开不了火"。这两份人面证明算术那条支路是通的，
    掉下来的那一格（站点的 color 顶掉我们没写 !important 的那一门）真会让它报红。
    返回 0/1，不跑普查、不起代理。
    """
    glass = "color(srgb 1 0.9176 0.9529 / 0.86)"
    t = canvas_colors()
    stops = "/".join(f"{'#%02x%02x%02x' % tuple(round(x) for x in t[k]['light'])}"
                     for k in GARDEN)
    cases = [
        ("合成人面 A（我们的墨，底下空到默认白）",
         {"bg": glass, "ink": "rgb(58, 43, 62)", "txt": 40, "und": [],
          "tag": "DIV", "id": "", "cls": "a"}, "ok"),
        ("合成人面 B（站点的白字顶掉了我们那一门）",
         {"bg": glass, "ink": "rgb(255, 255, 255)", "txt": 40, "und": [],
          "tag": "DIV", "id": "", "cls": "b"}, "low"),
        # C 是第一趟真站的形状（我们自己的粉地面带 background-image）：它必须进判定，
        # 不许再被 img: 那一格筛掉——第一趟就是被这条筛空的，判了 0 块还印了 OK。
        ("合成人面 C（底下是我们那面粉地面，带渐变图）",
         {"bg": glass, "ink": "rgb(58, 43, 62)", "txt": 40, "und":
             [{"t": "html", "i": "", "c": "", "b": f"img:rgb(255, 246, 250)", "own": True}],
          "tag": "DIV", "id": "", "cls": "c"}, "ok"),
        ("合成人面 D（站点容器画的图，真不可判）",
         {"bg": glass, "ink": "rgb(58, 43, 62)", "txt": 40, "und":
             [{"t": "div", "i": "", "c": "hero", "b": "img:rgba(0, 0, 0, 0)", "own": False}],
          "tag": "DIV", "id": "", "cls": "d"}, "img"),
        # E 是族外那一栏的正控制：一块**没穿我们玻璃**的浮面，自己没涂底（透明），
        # 字是站点自己的浅色，底下直接是我们的粉地面。它必须判 low——那一栏的绿
        # 从补洞那天起就该可疑（它可能只是"结构性开不了火"），这一具就是它的证人。
        ("合成人面 E（族外浮面：透明底＋站点浅字压在我们的粉地面上）",
         {"bg": "rgba(0, 0, 0, 0)", "ink": "rgb(255, 255, 255)", "txt": 74, "glass": False,
          "und": [{"t": "html", "i": "", "c": "", "b": "img:rgb(255, 246, 250)", "own": True}],
          "tag": "DIV", "id": "", "cls": "e"}, "low"),
    ]
    bad = 0
    for name, f, want in cases:
        st, msg, r = judge(f, "light")
        mark = "√" if st == want else "×"
        if st != want:
            bad += 1
        print(f"  {mark} {name}：判 {st}（要 {want}）｜{msg}")
    print(f"  读法：A 支不开火＝合成或对比度那条路断了；B 支不开火＝这一格只会永远绿，"
          f"它的绿不能当证据（线 {AA} 来自 check-contrast 的 ink-1 那一格）；"
          f"C 支不判＝「衬粉」那一格又被筛空（停靠 {stops}）；D 支开了火＝拿图当纯色合成了；"
          f"E 支不开火＝族外那一栏是空壳，它的绿不能当「那些面都读得动」")

    # 归因那一支的两向控制：body 上涂着**实心**底色、上面压一条全透明的图（站点常见写法），
    # 不许当成"我们的粉地面"；反过来，body 涂的确实是我们那三个停靠之一时仍然要认粉。
    # 只测 F 一具＝摘掉新守卫会红，但它过收（把我们的粉也判成站家的）却没人管。
    fbody = {"bg": glass, "ink": "rgb(58, 43, 62)", "txt": 40, "glass": False,
             "und": [{"t": "body", "i": "", "c": "", "b": "img:rgb(0, 0, 0)", "own": True}],
             "tag": "DIV", "id": "", "cls": "f"}
    who_f = attr_of(fbody, "light")
    who_c = attr_of(cases[2][1], "light")
    if "站点自涂" not in who_f or "粉地面" not in who_c:
        bad += 1
        print(f"  - SELF FAIL：衬底归因两向不成立｜黑实心底那格读到 {who_f!r}（要「站点自涂」）"
              f"｜我们那面粉那格读到 {who_c!r}（要「粉地面」）")
    else:
        print(f"  √ 归因两向：body 实心黑＋一条全透的图 ⇒ {who_f}；"
              f"body 涂我们的停靠 ⇒ {who_c}")

    # 分区断言：两块栏的划分本身（双向）。摘空族外栏会红在这里，把族外栏灌成"全都算族外"
    # 也会红在这里——一具刀要两头都有牙，只证"摘掉会红"对"收多了"是沉默的。
    pfaces = [{"k": "G", "glass": True}, {"k": "O1", "glass": False},
              {"k": "O2", "glass": False}]
    gb, ob = buckets(pfaces)
    p_ok = ([f["k"] for f in gb] == ["G"]
            and sorted(f["k"] for f in ob) == ["O1", "O2"]
            and len(gb) + len(ob) == len(pfaces))
    if not p_ok:
        bad += 1
        print(f"  - SELF FAIL：两栏划分不成立｜玻璃栏 {[f['k'] for f in gb]}"
              f"／族外栏 {[f['k'] for f in ob]}（要 G ／ O1、O2，且两块栏互斥并覆盖）")
    else:
        print(f"  √ 分区：{len(pfaces)} 块面各归一栏（玻璃 {[f['k'] for f in gb]}"
              f"／族外 {[f['k'] for f in ob]}）")

    # 第二组：判定那条支路本身（verdict，纯函数，不起浏览器）。V1/V2 是同一份 gl==0，
    # 只有名册宽窄不同——这一对证明"缩过名册"是唯一变量，而不是我把失效那支改哑了。
    vcases = [
        ("V1 全名单六站、玻璃归零（旧行为必须原样保留）",
         (6, 0, False, 6, 6), 1, "整体失效"),
        ("V2 同一读数但名册缩到一站（不适用，不报失效）",
         (1, 0, False, 6, 1), 0, "不适用："),
        ("V3 全名单、玻璃落了地（这条只拦整体归零）",
         (6, 9, False, 6, 6), 0, "落到了地"),
        ("V4 一站都没量到（链路支：rc 必须是 2，不能被读成判定）",
         (0, 0, False, 6, 6), 2, "都没量到"),
        ("V5 对照档 ?noskin（本档不出那条判定）",
         (6, 0, True, 6, 6), 0, "本档不适用"),
    ]
    vbad = 0
    for name, vargs, want_rc, want_tok in vcases:
        got_rc, msg = verdict(*vargs)
        ok = got_rc == want_rc and want_tok in msg
        if not ok:
            vbad += 1
        print(f"  {'√' if ok else '×'} {name}：rc={got_rc}（要 {want_rc}）"
              f"｜话里{'有' if want_tok in msg else '没有'}「{want_tok}」")
    print("  读法：V1 不红＝整体归零那条判定被改哑了（这才是真缺陷）；V2 红＝缩过的名册"
          "还在替全名单作保；V4 报成 1＝链路故障会被读成皮肤失效；V5 出判定＝仪器读成产品")
    return 1 if (bad or vbad) else 0


def main():
    argv = sys.argv[1:]
    if "--selftest" in argv:
        sys.exit(selftest())
    bad = [a for a in argv if not re.match(r"^--(window|theme|json|only|noskin|extra)(=|$)", a)]
    if bad:
        sys.exit(f"CENSUS ERROR: 不认得参数 {bad}"
                 "（可用：--window=WxH --theme=day|night --only=tag[,tag] --json --noskin"
                 " --extra=tag|https://url）")
    window = next((a.split("=", 1)[1].lower().replace("x", ",")
                   for a in argv if a.startswith("--window=")), "1280,1500")
    if not re.match(r"^\d+,\d+$", window):
        sys.exit(f"CENSUS ERROR: --window 要写成 1280x1500 这种形状，收到 {window!r}")
    theme = next((a.split("=", 1)[1] for a in argv if a.startswith("--theme=")), "day")
    if theme not in ("day", "night"):
        sys.exit(f"CENSUS ERROR: --theme 只认 day/night，收到 {theme!r}")
    only = next((a.split("=", 1)[1].split(",")
                 for a in argv if a.startswith("--only=")), None)
    extra_src = next((a.split("=", 1)[1]
                      for a in argv if a.startswith("--extra=")), "")
    as_json = "--json" in argv
    # --noskin：同一页、同一条反代链路、同一份探针，只是不挂皮肤也不挂面板档（proxy 的 ?noskin）。
    # 用途只有一个——isGlass 是视觉谓词，站点自涂的半透会被算进「穿上玻璃 N」，
    # 所以那一列要分家成"族净增"和"本来就透"。谓词本身一个字符没动。
    noskin = NOSKIN

    roster = sites()
    picked = [s for s in roster if not only or s[0] in only]
    if not picked and not extra_src:
        sys.exit(f"CENSUS ERROR: --only {only} 一站都没对上（名单：{[s[0] for s in roster]}）")
    # --extra：只给这一跑加站，定义在 parse_extra（root-census 共用同一份校验）
    extras = parse_extra(extra_src, roster, "CENSUS ERROR")
    picked += extras

    skin = ROOT / "preview" / "skin.css"
    body = skin.read_bytes()
    proxy = start_proxy()
    try:
        q = (f"?glassprobe{'&night' if theme == 'night' else ''}"
             f"{'&noskin' if noskin else ''}")
        rows = []
        rc = 0
        scope = "" if not only else f"，只跑 {only}"
        print(f"浮面普查（{theme} 档{'＋对照档 ?noskin：皮肤与面板档都不注入' if noskin else ''}，"
              f"窗口 {window.replace(',', '×')}，"
              f"上限 {DUMP_TIMEOUT_MS // 1000}s，skin.css {len(body)} 字节，"
              f"sha {hashlib.sha1(body).hexdigest()[:12]}{scope}）")
        print("  注：代理把 preview/skin.css 读在启动那一刻——上面这枚 sha 是文件的，"
              "借来的代理可能在跑上一代。判定前先看 tools/spot-check.sh 那一跑。\n")
        if extras:
            print(f"  注：extra 站 {len(extras)} 枚（{[t for t, _ in extras]}）与名单同进分母，"
                  "但它们的读数只用于看形状（有没有浮面、底下衬的是谁、几块穿上玻璃），"
                  "不进 README 的结论；量不到的那几枚会让 rc=1，那是可达性不是失效\n")
        for tag, url in picked:
            data, err = dump(f"{BASE}{url}{q}", window)
            r = report(tag, data, err)
            if r:
                rows.append(r)
        tot = sum(r["n"] for r in rows)
        gl = sum(r["g"] for r in rows)
        with_g = sum(1 for r in rows if r["g"])
        print(f"\n  合计：{len(rows)}/{len(picked)} 站量到，浮面 {tot}／穿上玻璃 {gl}"
              f"，其中 {with_g} 站各至少落上一块")
        # 玻璃落上去 ≠ 肉眼看得见玻璃：子孙自己涂了底的那一格由"盖%"说明，
        # 这里只给分布不判好坏——阈值一进来就成了第二条判定，而它没有金样本可钉。
        # 94 这类数会在下一版版面里漂，所以报中位与范围（范围由现跑的名册算出）。
        def _dist(lst):
            if not lst:
                return "无"
            c = sorted(f["cover"] for f in lst)
            mid = c[len(c) // 2] if len(c) % 2 else (c[len(c) // 2 - 1] + c[len(c) // 2]) // 2
            return f"中位 {mid}，范围 {c[0]}–{c[-1]}"
        gf = [f for r in rows for f in r["faces"] if f["glass"]]
        of = [f for r in rows for f in r["faces"] if not f["glass"]]
        print(f"  盖%（子孙自己涂底的面积占比，嵌套会重复计所以能 >100；0＝面上全空，"
              f"越大说明这块上了玻璃也看不见）：族内 {len(gf)} 块 {_dist(gf)}｜"
              f"族外 {len(of)} 块 {_dist(of)}")
        # 【衬底】那张表：抬头预注册的那几条读法在这里落地，判据的 4.5 从 check-contrast
        # 的 REQUIRED["ink-1"] 引用而来（AA 线只住那一格，这里不抄第二份）。
        if rows and not noskin:
            hist, res, notext, skipped = ground_tally(rows, 0)
            ours = hist.get("我们的粉地面", 0) + hist.get("我们的画布", 0)
            print(f"  【衬底】玻璃面 {len(res) + len(notext) + len(skipped)} 块的第一层归因："
                  + "｜".join(f"{k} {v}" for k, v in sorted(hist.items(), key=lambda kv: -kv[1]))
                  + f"　⇒ 底下衬着我们自己的面的 = {ours} 块")
            if res:
                mn = min(res, key=lambda x: x[4])
                print(f"      判 {len(res)} 块（线 {AA}，引用 check-contrast 的 ink-1 那一格）："
                      f"最低 {mn[4]:.2f}:1 在 {mn[0]} <{sig_of(mn[1])[:56]}>")
                for t, f, st, msg, ratio in sorted(res, key=lambda x: x[4])[:4]:
                    print(f"      {t:18} {ratio:5.2f}:1 字{f['txt']:5} <{sig_of(f)[:52]}>｜{msg}")
            else:
                print(f"      判 0 块（线 {AA}）——这一格的绿不能当证据，见下面那句")
            if skipped or notext:
                by = {}
                for t, f, st, msg, _ in skipped:
                    by.setdefault(st, []).append((t, msg))
                print(f"      不判比值：面上 0 字 {len(notext)}（那格 color 没有读者）"
                      f"｜算不出 {len(skipped)} "
                      + "｜".join(f"{k} {len(v)} 块：{v[0][0]} {v[0][1]}"
                                  for k, v in sorted(by.items())))
            low = [x for x in res if x[2] == "low"]
            if low:
                print(f"  衬底 ⚠：{len(low)} 块玻璃面合成后墨色不到 {AA}（AA 正文线）")
                for t, f, st, msg, ratio in low:
                    print(f"      {t:18} {ratio:5.2f}:1 <{sig_of(f)[:64]}>｜{msg}")
                rc = 1
            elif not res:
                # 我自己第一趟就踩在这里：判 0 块时打印 "衬底 OK" 就是一道空壳绿。
                print("  衬底 ⚠：一块都没判到（全被「面上没字」或「底下是站点画的图」筛掉了）——"
                      "这一跑这条判据没有对象，它既没通过也没失败")
            else:
                print(f"  衬底 OK：判到的 {len(res)} 块合成后墨色都不低于 {AA}"
                      "——这一格只判「我们的玻璃＋我们的墨」配真站的底，不判站点自己的面")
            # 第二栏：浮着但**没**被词根收进玻璃族的那些面。同一份合成判据，分母互斥
            # （划分只住在 buckets 那一格）。这一栏只摆数不出判定、不翻 rc——
            # 那些面上的墨多半是站点自己的，上面那条 AA 线的主张是"我们的玻璃＋我们的墨"，
            # 管不到它；读数拿去给"这块该不该收进名单"定价（预注册读法见 root-census 抬头）。
            hist2, res2, notext2, skipped2 = ground_tally(rows, 1)
            n2 = len(res2) + len(notext2) + len(skipped2)
            ours2 = hist2.get("我们的粉地面", 0) + hist2.get("我们的画布", 0)
            print(f"  【衬底·族外】没穿玻璃的浮面 {n2} 块（与上面那栏互斥）："
                  + ("｜".join(f"{k} {v}" for k, v in
                               sorted(hist2.items(), key=lambda kv: -kv[1])) or "一块都没有")
                  + f"　⇒ 底下衬着我们自己的面的 = {ours2} 块")
            if res2:
                mn2 = min(res2, key=lambda x: x[4])
                print(f"      判 {len(res2)} 块：最低 {mn2[4]:.2f}:1 在 {mn2[0]}"
                      f" <{sig_of(mn2[1])[:56]}>")
                for t, f, st, msg, ratio in sorted(res2, key=lambda x: x[4])[:4]:
                    print(f"      {t:18} {ratio:5.2f}:1 字{f['txt']:5} <{sig_of(f)[:52]}>｜{msg}")
            else:
                print(f"      判 0 块（族外那 {n2} 块全被「面上没字」或「算不出」筛掉了）"
                      "——这一栏这一跑没有对象，它既没通过也没失败")
            low2 = [x for x in res2 if x[2] == "low"]
            if low2:
                print(f"      ⚠ 族外 {len(low2)} 块合成后不到 {AA}"
                      "（摆出来定价，不算缺陷计数：墨是谁涂的读上一行的归因）")
        # 唯一一条判定，而且是别的尺子都看不见的那一格：族在真站上到底落没落地。
        # 不钉每站块数——那要一份金样本，而金样本会把"站点改版面"和"我们的名单漂移"
        # 混成同一个红；也不钉总和（今天 9），只钉"别整体掉到 0"。
        # M01–M06 那六柄刀割的是 CSS 里的词根，夹具里那块面照样在，它们量不到真站。
        # 分支本身住在 verdict()（纯函数；selftest 判的是同一份定义），这里只打印与取 rc。
        v_rc, v_msg = verdict(len(rows), gl, noskin, len(roster), len(picked))
        print("  " + v_msg)
        if v_rc in (1, 2):
            rc = v_rc
        if as_json:
            Path("/tmp/ks-glass-census.json").write_text(
                json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
            print("  逐块明细 → /tmp/ks-glass-census.json")
    finally:
        if proxy:
            proxy.terminate()
            proxy.wait(timeout=10)
    sys.exit(rc)


if __name__ == "__main__":
    main()
