#!/usr/bin/env python3
"""本地反代：把真站搬到 127.0.0.1 下面，顺手剥掉 CSP 并挂上皮肤，好让抽检能脚本化。

为什么绕这一圈：真站的 CSP 会拦掉"页面里 JS 注入样式/请求本地端口"，
在 https 页面上用 devtools 注入既不稳定也测不出东西。搬到同源之后，
注入的就是普通 <style>，和装 Stylus 时的差别只剩"没有扩展"这一条。
只监听 127.0.0.1，只用来出抽检图，不当公开服务用。

用法：/s/<完整站点 URL>，加 ?night 走夜晚档，加 ?bare 出同一条链路的裸页，
加 ?sentinel 出归因档（**整套颜色 token** 扳成纯绿，含 --ks-ink-*/--ks-link/--ks-head-ink，
所以"这块底是谁涂的"和"这行字是谁涂的"两问都由同一档答），加 ?glassprobe 让页面自己报"哪些浮面穿上了玻璃"。
"""
import hashlib
import html as htmllib
import http.server
import json
import os
import re
import socketserver
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOST = "127.0.0.1"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8748
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36")
MIN_BYTES = 1500
# 单条子资源的上游等待上限。必须显著小于 Chrome 的 --timeout：
# 实测 css-tricks 那篇媒体查询指南挂着两条死链（一条写成 //themes/smoothness/ 的
# jquery-ui.min.css、一张 2020 年贴在 dropbox 上的图），每条都要等满 25s 才失败，
# 于是 load 永远不触发、快门每次撞在不同的一秒——四张连拍给出两种像素。
# 10s 之内没回来的就当它死了：三档同样缺，比"每次都抖"更可比对。
UPSTREAM_TIMEOUT = int(os.environ.get("KS_PROXY_TIMEOUT", "10"))
# 失败也进缓存，但只记 60 秒。原先"只缓存成功的那次"是怕一次抖动把整站锁死 6 小时；
# 短到一分钟之后，锁不死了，而"每张图重等一遍死链"这一条也不会再来一遍。
FAIL_TTL = int(os.environ.get("KS_PROXY_FAIL_TTL", "60"))
CACHE = Path(os.environ.get("KS_PROXY_CACHE_DIR", "/tmp/ks-proxy-cache"))
SKIN = (ROOT / "preview" / "skin.css").read_text(encoding="utf-8")

# 哨兵档要把皮肤的**整个调色板**扳成纯绿，不只是 canvas 那三档。
# 皮肤还会拿 --ks-sakura/--ks-petal/--ks-neutral/--ks-scrim 直接涂背景（mark、kbd、遮罩、
# 渐变面），只扳 canvas 时那些格在哨兵档里一动不动，就会被判成"站点自己涂的底"——
# 归因朝"不怪我们"那一边错，而这条闸门要的恰好是"这块底是谁涂的"。
# 哪些 token 是颜色，按 skin.css 里声明值的形状现认，不抄第二份名单：
# 皮肤新加一个颜色 token，哨兵档自动覆盖到它；圆角/时长/模糊/字体栈/百分比不在里面，
# 把长度扳成颜色会让那条声明在计算值阶段失效（初值 0px、无阴影），
# 那才是真会把两趟版面拉开、把归因染脏的做法。
SENT_COLOR = re.compile(r"^(light-dark\(|#|color-mix\(|(linear|radial|conic)-gradient\(|"
                        r"var\(--[A-Za-z][\w-]*,\s*#|rgb[a]?\(|hsl[a]?\(|lab\(|oklab\(|lch\(|"
                        r"oklch\(|color\()")


def sentinel_decls(css):
    """-> 该页要注入的哨兵声明列表。渐变 token 用两层纯绿渐变顶替（background-image 收不下色值）。"""
    out = []
    for name, raw in re.findall(r"(--ks-[\w-]+)\s*:\s*([^;{}]+)", css):
        val = " ".join(raw.split())
        if not SENT_COLOR.match(val):
            continue
        rep = ("linear-gradient(#00ff00, #00ff00)"
               if re.match(r"(linear|radial|conic)-gradient\(", val) else "#00ff00")
        out.append(f"{name}: {rep} !important")
    return out


SENTINELS = sentinel_decls(SKIN)
if not any("--ks-canvas-1" in d for d in SENTINELS):
    sys.exit("preview/skin.css 里没认出 --ks-canvas-1 这个颜色 token："
             "哨兵档认不出画布就等于一个像素都不动，归因会整批判成"
             "「站点自己涂的底」——先修 token 的形状，别拿假读数当结论")

# 墨 token 也必须在名单里。legibility.py 的 ownership 拿"同一坐标动没动"做**二值**归因，
# 而它答的题有两问：这块底是谁涂的、这行字是谁涂的。只扳画布时第二问答不出来，
# 且答错的方向是"整批判成站家的字"——我们强制的浅字压在站家浅底上那类撞色
# （真站名单里量到过 21 行，最坏一枚 w3schools 夜晚档标题芯对纸 1.71）会从读数里消失。
# 名单按声明形状现推（哪些 token 被**文字颜色**那一类属性吃走），不抄第二份名字：
# 皮肤新加一个墨 token，这条守卫自动覆盖到它；抄名字则会先漂后红，归因归不到刀上。
INK_TOKENS = set(re.findall(
    r"(?<![\w-])(?:color|-webkit-text-fill-color|fill)\s*:\s*var\(\s*(--ks-[\w-]+)\s*\)", SKIN))
if not INK_TOKENS:
    sys.exit("PROXY ERROR: preview/skin.css 里没认出任何「文字颜色走 var(--ks-*)」的声明："
             "下面那条墨守卫就此哑掉（0 个对象的判据永远不会红）——"
             "要么声明的形状变了，要么皮肤真的不接管字色了，两种都得先说清楚再跑")
_missed = sorted(t for t in INK_TOKENS if not any(t + ":" in d for d in SENTINELS))
if _missed:
    sys.exit(f"PROXY ERROR: 哨兵档没扳这些文字颜色 token：{_missed}——归因答不了「这行字是谁涂的」，"
             f"而 legibility.py 的 ownership 主张写的是「整套颜色 token」。"
             f"要么把墨 token 扳回来，要么把那句话改成「只归因底、字不归因」")

# ?glassprobe 要跑的普查脚本。写成常量而不是内联在 proxy 里，是为了让
# tools/glass-census.py 能把它整段读出来贴进报告——读数说不通时得能看见量它的尺原文。
# 判"穿上玻璃"按**涂到的效果**认：backdrop-filter 里有 blur，且 background-color
# 解成我们那一形 color(srgb … / α)。不按"族的选择器能不能匹上这块"认，因为那要在
# JS 里再抄一份族名单，抄本迟早和族分家（§4c 那族在 CSS 里本来就有四份逐字副本）。
GLASS_PROBE = r"""
(function () {
  function run() {
    var faces = [];
    var all = document.body ? document.body.querySelectorAll('*') : [];
    for (var el of all) {
      var s = getComputedStyle(el);
      if (s.position !== 'fixed' && s.position !== 'sticky') continue;
      var r = el.getBoundingClientRect();
      if (r.width < 40 || r.height < 16 || r.width * r.height <= 400) continue;
      if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') continue;
      if (r.bottom <= 0 || r.top >= innerHeight || r.right <= 0 || r.left >= innerWidth) continue;
      var bf = s.backdropFilter || s.webkitBackdropFilter || 'none';
      var bg = s.backgroundColor;
      // 这块面被"自己涂了底的子孙"压住多少（面积百分数，交集按面的矩形裁，重叠会重复计，
      // 所以能 >100）。它问的不是"这块该不该上玻璃"，而是"上了玻璃肉眼看不看得见"——
      // 盖到 100 的那一块，玻璃换成实心也读不出差别，扳它没有收益。
      // 只认 background-color 不认 background-image：图是站点的画，不是它的底色。
      var cover = 0, area = r.width * r.height;
      for (var d of el.querySelectorAll('*')) {
        var ds = getComputedStyle(d);
        if (ds.display === 'none' || ds.visibility === 'hidden') continue;
        if (ds.backgroundImage !== 'none') continue;
        var db = ds.backgroundColor;
        if (db === 'transparent' || /^rgba\(\s*0,\s*0,\s*0,\s*0\s*\)$/.test(db)) continue;
        var dr = d.getBoundingClientRect();
        var ow = Math.min(r.right, dr.right) - Math.max(r.left, dr.left);
        var oh = Math.min(r.bottom, dr.bottom) - Math.max(r.top, dr.top);
        if (ow > 0 && oh > 0) cover += ow * oh;
      }
      // 玻璃**底下**是谁：从最近的上层祖先起，往下数涂了底的三层（一路到 html／body）。
      // 这块面的透孔（背景 α 的那一小半）就是落在这一串上，所以「下面衬的是不是我们的粉」
      // 这一问只能在页里量——CSS 知道谁透，不知道透出来的是什么。
      // 只收 background-color，但 background-image 那一层要标 `img:` 记下来：图是站点画的，
      // 拿它当纯色合成会造出一个不存在的底，所以宁可让读表的人看见"这一格算不出"。
      var und = [], q = el.parentElement;
      while (q && und.length < 3) {
        var qs = getComputedStyle(q);
        var qb = qs.backgroundColor;
        var op = qs.backgroundImage !== 'none';
        if (op || (qb && qb !== 'transparent' &&
                   !/^rgba\(\s*0,\s*0,\s*0,\s*0\s*\)$/.test(qb))) {
          und.push({
            t: q.tagName.toLowerCase(), i: q.id || '',
            c: (q.getAttribute('class') || '').replace(/\s+/g, ' ').slice(0, 60),
            b: (op ? 'img:' : '') + qb,
            own: q === document.body || q === document.documentElement
          });
        }
        q = q.parentElement;
      }
      faces.push({
        tag: el.tagName.toLowerCase(),
        id: el.id || '',
        cls: (el.getAttribute('class') || '').replace(/\s+/g, ' ').slice(0, 90),
        pos: s.position, w: Math.round(r.width), h: Math.round(r.height),
        x: Math.round(r.left), y: Math.round(r.top),
        // 这块面上落在其内的可见文字数：判"它是不是常驻内容条"用，不是判据
        txt: (el.innerText || '').replace(/\s+/g, '').length,
        glass: bf.indexOf('blur') >= 0 && /^color\(srgb/.test(bg),
        cover: area > 0 ? Math.round(cover * 100 / area) : 0,
        // 64 不是随手取的：α 正是面板玻璃开关要调制的那一位，截短了读数就不自证
        bf: bf.slice(0, 40), bg: bg.slice(0, 64),
        // 这块面上真在生效的墨色（计算值，不是我们 token 的原文）：族给 color 用的不是
        // !important，站点更具体的规则顶得掉它——所以判可读性要读这一格，不能读 token。
        ink: s.color, und: und
      });
    }
    faces.sort(function (a, b) { return (b.glass - a.glass) || (a.y - b.y); });
    var o = document.getElementById('ks-glass');
    if (!o) {
      o = document.createElement('output');
      o.id = 'ks-glass';
      o.hidden = true;
      document.documentElement.appendChild(o);
    }
    o.textContent = JSON.stringify({
      vw: innerWidth, vh: innerHeight, dpr: devicePixelRatio,
      // 皮肤到底上没上：直接读我们自己的 token 有没有解出来。缺了它，"这站一个浮面都没有"
      // 就是假读数（没样式的页面全站 static，判据一条都进不来）。
      tok: (getComputedStyle(document.documentElement)
              .getPropertyValue('--ks-canvas-1') || '').trim(),
      // 分支到底解成了哪一支：tok 那枚是未解算的 light-dark(…) 原文，day 与 night 读出来
      // 一模一样，所以它证不了档。colorScheme 才是解算结果——html 那一格管 §3 的膜
      // （膜涂在 html::before 上），body 那一格管 §2 的画布（:where(body) 让路）。
      htmlScheme: getComputedStyle(document.documentElement).colorScheme,
      bodyScheme: document.body ? getComputedStyle(document.body).colorScheme : '',
      n: faces.length, g: faces.filter(function (f) { return f.glass; }).length,
      faces: faces
    });
  }
  if (document.readyState === 'complete') run();
  else window.addEventListener('load', run);
})();
""".strip()


# ?rootprobe 的候选词根名册。这一格是唯一的定义：注入时替换进 ROOT_PROBE 的 __TOKENS__，
# 驱动 tools/root-census.py 也 import 它，两边都不抄第二份。
# 为什么要有这张表：族名单里「navbar／header 这两截不追」是按真站普查定的，而 CSS 选择器
# 表达不了 computed position——「这一截词根命中的元素里到底有几个真浮着」只能在页面里量。
# 加一截候选就加一行；它今天追到什么，由 root-census 的读数说，不由这里的注释说。
# overlay／popup／flyout 这三截是族里今天**完全没有**的通用词根（族认 modal/dropdown/
# popover/toast/tooltip/sidebar/secondarybar/topnav/fixed-btn）。进名册的理由不是"别人家有"，
# 是夹具里那块逐字摘自真站的 GitHub 浮层：类名串 `Box Box--overlay … hx_rsm-dialog hx_rsm-modal`
# 今天是被 `modal` 那一截子串接住的，`overlay` 自己一行都没出力。要问的是——
# 真站上那些**类名里只有 Overlay/popup/flyout、不带 modal 字样**的浮层有多少，
# 它们现在是站家的底还是根本没浮着；这正好是这张表的两形计数能答的。
# backdrop：2026-10-03 由 tools/overlay-probe.mjs 量出来的候选——GitHub 的搜索面板穿上了玻璃，
# 它背后那层铺满大半页的遮罩（div.prc-Dialog-Backdrop，fixed 1440×813，站家 rgba(200,209,218,.4)）
# 没穿，home 与 features 两站各量到一次。定夺＝**不收进玻璃族**：族那条给的是 86% 不透明的粉底，
# 铺在整页遮罩上会把弹窗底下洗掉；该谈的是 --ks-scrim 那一档，而那层只在点开时存在——静息普查
# 结构上量不到它（这一截在职六站静息命中 0，不构成"没有误伤"的证据）。
# pagetop：2026-10-03 「接管常驻条」转正的那两截 id 形里的一截（w3schools 的 `#pagetop`），
# 族按 id 子串追它，但普查名册里没有它就一直量不到"还有谁挂着这个 id"。加进来只为补这一格
# 读数，不代表名单里的其它 id 形也被量过。
ROOT_TOKENS = ["navbar", "nav", "header", "sticky", "fixed", "topbar",
               "toolbar", "banner", "drawer", "menu", "dropdown",
               "overlay", "popup", "flyout", "backdrop", "pagetop"]

# 第三形：不靠类名的**结构形**。上面这些截全是类名／id 的子串或词边界，而没穿上玻璃那 6 块
# 浮面里最响的两块（mdn 1280×98 的常驻页头、github-features 的 AnchorNav）类名串里没有通用词。
# 但它们都长得像"整页最外层的一个 header／nav"。CSS 表达得了"最外层"（:not(:is(header,nav) *)），
# 表达不了 position，所以浮着／文档流两侧还得在这一档现量——这一格问的就是结构代理能不能替词根。
# 最后一条带上 :not(button, svg)：那是族今天已有的排除，要采纳就得连它一起量，不然读数对不上规则。
ROOT_RAW = [
    {"s": "header", "label": "header 标签（全部）"},
    {"s": "nav", "label": "nav 标签（全部）"},
    {"s": "body > :is(header, nav)", "label": "body 直属的页头／导航"},
    {"s": ":is(header, nav):not(:is(header, nav) *)", "label": "最外层 header／nav"},
    {"s": ":is(header, nav):not(:is(header, nav) *):not(button, svg)",
     "label": "最外层·带族排除的可采纳形"},
]

# ?rootprobe 要跑的脚本。它问的不是"这块面穿上玻璃没有"（那是 ?glassprobe 那一档，
# 它只看 fixed/sticky），而是"如果把这截词根加进族，会追到什么"：
# 按类名／id 子串命中的元素里，几个是 fixed/sticky（加了才看得见）、
# 几个是文档流里的 static／relative（加了就是误伤），以及误伤里最大那块的面积。
# 每截词根数两形，因为族里现存的两种形追到的集合不一样大：
# 子串形 = [class*=X i] 或 [id*=X i]（族里 modal/dropdown/sidebar 那一组用的形），
# 词边界形 = 只作用在 class 上的六条形（~= 整词、^= 前缀、*- 与 *_ 与 - 与 _ 黏合，
# 族里 topnav 那一组用的形）。再单报"只靠 id 命中"的个数：族不匹配 id，
# 那一格说的是"要不要把 id 也拉进匹配面"，不是已经追到的东西。
# 顺带报全站一条别的尺子看不见的：穿上了玻璃、位置却不是 fixed/sticky 的元素——
# ?glassprobe 按位置先筛过，这一格它结构上读不到。
ROOT_PROBE = r"""
(function () {
  var TOKENS = __TOKENS__;
  var RAW = __RAW__;
  function isGlass(s) {
    var bf = s.backdropFilter || s.webkitBackdropFilter || 'none';
    return bf.indexOf('blur') >= 0 && /^color\(srgb/.test(s.backgroundColor);
  }
  function sig(el) {
    // 祖先链要比的是"同一个签名能不能对上"，所以两边共用一个算法：tag + id + 第一个类名。
    // 只取第一个类名是刻意的：哈希站的整串类名各自唯一，对不上"族追的是哪一截"这个问题，
    // 而链上每一跳只要能认出"是不是那一块"就够了。
    var c = (el.getAttribute('class') || '').trim().split(/\s+/)[0] || '';
    return el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (c ? '.' + c : '');
  }
  function info(el, s) {
    var r = el.getBoundingClientRect();
    var up = [], a = el.parentElement, hop = 0;
    while (a && hop < 5) { up.push(sig(a)); a = a.parentElement; hop++; }
    return {tag: el.tagName.toLowerCase(), id: (el.id || '').slice(0, 40),
            cls: (el.getAttribute('class') || '').replace(/\s+/g, ' ').slice(0, 110),
            pos: s.position, w: Math.round(r.width), h: Math.round(r.height),
            area: Math.round(r.width * r.height),
            txt: (el.innerText || '').replace(/\s+/g, '').length,
            glass: isGlass(s),
            x: Math.round(r.left), y: Math.round(r.top),
            // bg/bf 是"这块玻璃是谁给的"唯一的直接证人：orphan 行从前只有形状没有这两个值，
            // 于是"尺子的洞"和"站点本来就透"在这张表上长得一模一样。
            bg: s.backgroundColor,
            bf: s.backdropFilter || s.webkitBackdropFilter || 'none',
            up: up};
  }
  function wbClass(v, t) {
    // 只作用在 class 属性上，镜像族里 topnav 那一组的六种形（全带 i）：
    // [class~=] 空格分词的整词、[class^=] 前缀、以及 *- 与 *_ 的左右黏合。
    // 为什么要有第二形：族今天对 topnav 用的就是这个形，而子串形（[class*=X i]）
    // 追到的元素集合更大——「只许上词边界形」那条判据要能算，就得把这一形单独数一遍。
    if (!v) return false;
    return (' ' + v.replace(/[\s]+/g, ' ').trim() + ' ').indexOf(' ' + t + ' ') >= 0
        || v.indexOf(t) === 0
        || v.indexOf(t + '-') >= 0 || v.indexOf(t + '_') >= 0
        || v.indexOf('-' + t) >= 0 || v.indexOf('_' + t) >= 0;
  }
  function splitTop(sel) {
    // 顶层逗号切分：:is(...) 与 [class*="a, b"] 里的逗号不是分隔符。
    var out = [], depth = 0, cur = '', q = null;
    for (var i = 0; i < sel.length; i++) {
      var c = sel[i];
      if (q) { cur += c; if (c === q) q = null; continue; }
      if (c === '"' || c === "'") { q = c; cur += c; continue; }
      if (c === '(') depth++;
      if (c === ')') depth--;
      if (c === ',' && depth === 0) { out.push(cur.trim()); cur = ''; continue; }
      cur += c;
    }
    if (cur.trim()) out.push(cur.trim());
    return out;
  }
  function famParts() {
    // 族内实形：不看我拼的近似形状，直接问「这一页真在生效的样式表里，
    // 哪几条选择器把元素刷成了玻璃」。含 ks- 的选择器整条跳过并进 skipped——
    // 自家工具条是 fixed，不排掉就会把「浮」那一列顶高；代价反着写在这里：
    // 某站真类名里带 ks- 会被我少算，所以 skipped 要逐条读，不是只看条数。
    var parts = [], skipped = [], inner = {}, shs = document.styleSheets || [];
    for (var i = 0; i < shs.length; i++) {
      var rs = null;
      try { rs = shs[i].cssRules; } catch (e) { continue; }
      for (var j = 0; j < rs.length; j++) {
        var r = rs[j];
        if (!r.selectorText || !r.style) continue;
        var bf = (r.style.getPropertyValue('backdrop-filter') ||
                  r.style.getPropertyValue('-webkit-backdrop-filter') || '');
        if (bf.indexOf('blur') < 0) continue;
        if ((r.style.getPropertyValue('background-color') || '').indexOf('color-mix') < 0) continue;
        var ps = splitTop(r.selectorText);
        for (var k = 0; k < ps.length; k++) {
          if (ps[k].indexOf('ks-') >= 0) { skipped.push(ps[k]); continue; }
          if (parts.indexOf(ps[k]) >= 0) continue;
          parts.push(ps[k]);
          inner[ps[k]] = innerOf(ps[k]);
        }
      }
    }
    return {parts: parts, skipped: skipped, inner: inner};
  }
  function innerOf(p) {
    // 族的两份副本都写成 :is(…一整串词根…)[:not/:is(…)]——顶层逗号在括号里，
    // 所以「按选择器归因」只会给出一条整族，答不了「是哪一截词根追的」。
    // 这里取第一层 :is() 花括号内的每一项当词根标签；不以 :is( 开头的选择器
    // （站家自己的玻璃规则、我们的单条规则）就整条当标签，原样印出来。
    if (p.slice(0, 4) !== ':is(') return [p];
    var depth = 0, q = null;
    for (var i = 3; i < p.length; i++) {
      var c = p[i];
      if (q) { if (c === q) q = null; continue; }
      if (c === '"' || c === "'") { q = c; continue; }
      if (c === '(') depth++;
      else if (c === ')') { depth--; if (depth === 0) return splitTop(p.slice(4, i)); }
    }
    return [p];
  }
  function run() {
    var tokens = [], stray = [], orphan = [], total = 0, glassN = 0, glassFloat = 0;
    var all = document.body ? document.body.querySelectorAll('*') : [];
    var fp = famParts();
    function who(el) {
      var hit = [];
      for (var k of fp.parts) {
        var ok = false;
        try { ok = el.matches(k); } catch (e) { continue; }
        if (!ok) continue;
        var ins = fp.inner[k] || [];
        for (var r0 of ins) {
          var ok2 = false;
          try { ok2 = el.matches(r0); } catch (e) { ok2 = false; }
          if (ok2 && hit.indexOf(r0) < 0) hit.push(r0);
        }
      }
      return hit;
    }
    var pmap = {};
    for (var el of all) {
      var s = getComputedStyle(el);
      if (s.display === 'none' || s.visibility === 'hidden') continue;
      if (s.position !== 'fixed' && s.position !== 'sticky' && !isGlass(s)) continue;
      var r = el.getBoundingClientRect();
      if (r.width < 40 || r.height < 16 || r.width * r.height <= 400) continue;
      if (isGlass(s)) {
        var i0 = info(el, s);
        i0.by = who(el);
        glassN++;
        if (s.position === 'fixed' || s.position === 'sticky') glassFloat++;
        if (!i0.by.length) orphan.push(i0);
        if (s.position !== 'fixed' && s.position !== 'sticky') stray.push(i0);
        for (var b of i0.by) {
          var a = pmap[b] || (pmap[b] = {p: b, n: 0, pos: {}, float: [], still: []});
          a.n++;
          a.pos[i0.pos] = (a.pos[i0.pos] || 0) + 1;
          if (i0.pos === 'fixed' || i0.pos === 'sticky') a.float.push(i0);
          else a.still.push(i0);
        }
      }
    }
    var parts = [];
    for (var key in pmap) {
      var e = pmap[key];
      e.still.sort(function (x, y) { return y.area - x.area; });
      e.float.sort(function (x, y) { return y.area - x.area; });
      parts.push({p: e.p, n: e.n, pos: e.pos,
                  // 上限从 2 抬到 6：收窄定价要的是"换成精确词之后这块还剩不剩"，
                  // 只有类名/签名答得出来，而 2 份会在浮面≥3 的那一截上悄悄少报。
                  float: e.float.slice(0, 6), still: e.still.slice(0, 6)});
    }
    parts.sort(function (x, y) { return y.n - x.n; });
    for (var t of TOKENS) {
      var sel = '[class*="' + t + '" i], [id*="' + t + '" i]';
      var hits = document.body ? document.body.querySelectorAll(sel) : [];
      var pos = {}, float = [], still = [], n = 0;
      var tl = t.toLowerCase();
      var wpos = {}, wfloat = [], wstill = [], wn = 0, idonly = 0;
      // idonly 从前只是一个总数，答不了"族要不要吃 id"：id 命中的那些面浮着还是躺在文档流上、
      // 最大的一块多大，是这一格唯一还缺的价。
      var idpos = {}, idmax = 0, idtop = null, idfloat = [], idstill = [];
      for (var el2 of hits) {
        var s2 = getComputedStyle(el2);
        if (s2.display === 'none' || s2.visibility === 'hidden') continue;
        var i2 = info(el2, s2);
        if (i2.area <= 0) continue;
        n++;
        pos[i2.pos] = (pos[i2.pos] || 0) + 1;
        if (i2.pos === 'fixed' || i2.pos === 'sticky') float.push(i2);
        else still.push(i2);
        var cv = (el2.getAttribute('class') || '').toLowerCase();
        var iv = (el2.id || '').toLowerCase();
        if (cv.indexOf(tl) < 0 && iv.indexOf(tl) >= 0) {
          idonly++;
          idpos[i2.pos] = (idpos[i2.pos] || 0) + 1;
          if (i2.pos === 'fixed' || i2.pos === 'sticky') idfloat.push(i2);
          else idstill.push(i2);
          if (i2.area > idmax) { idmax = i2.area; idtop = i2; }
        }
        if (wbClass(cv, tl)) {
          wn++;
          wpos[i2.pos] = (wpos[i2.pos] || 0) + 1;
          if (i2.pos === 'fixed' || i2.pos === 'sticky') wfloat.push(i2);
          else wstill.push(i2);
        }
      }
      still.sort(function (a, b) { return b.area - a.area; });
      float.sort(function (a, b) { return b.area - a.area; });
      wstill.sort(function (a, b) { return b.area - a.area; });
      wfloat.sort(function (a, b) { return b.area - a.area; });
      idstill.sort(function (a, b) { return b.area - a.area; });
      idfloat.sort(function (a, b) { return b.area - a.area; });
      total += n;
      tokens.push({t: t, n: n, pos: pos,
                   float: float.slice(0, 3), still: still.slice(0, 3),
                   wb: {n: wn, pos: wpos,
                        float: wfloat.slice(0, 3), still: wstill.slice(0, 3)},
                   idonly: idonly, idpos: idpos, idmax: idmax, idtop: idtop,
                   idfloat: idfloat.slice(0, 3), idstill: idstill.slice(0, 3)});
    }
    // 结构形那一档：和词根同一套计数（可见、面积>0、按 computed position 分浮/静止），
    // 但多带一个 glass 标记——净新增要看"这块浮面今天穿没穿上玻璃"，
    // 只数命中会把族里已经接住的那几块算成新收益。
    var raws = [];
    for (var rw of RAW) {
      var rhits = [];
      try { rhits = document.body ? document.body.querySelectorAll(rw.s) : []; }
      catch (e) { raws.push({s: rw.s, label: rw.label, err: String(e.name), n: 0,
                             pos: {}, float: [], still: []}); continue; }
      var rpos = {}, rfloat = [], rstill = [], rn = 0;
      for (var el4 of rhits) {
        var s4 = getComputedStyle(el4);
        if (s4.display === 'none' || s4.visibility === 'hidden') continue;
        var i4 = info(el4, s4);
        if (i4.area <= 0) continue;
        rn++;
        rpos[i4.pos] = (rpos[i4.pos] || 0) + 1;
        if (i4.pos === 'fixed' || i4.pos === 'sticky') rfloat.push(i4);
        else rstill.push(i4);
      }
      rfloat.sort(function (a, b) { return b.area - a.area; });
      rstill.sort(function (a, b) { return b.area - a.area; });
      raws.push({s: rw.s, label: rw.label, n: rn, pos: rpos,
                 float: rfloat.slice(0, 6), still: rstill.slice(0, 6)});
    }
    var o = document.getElementById('ks-root');
    if (!o) {
      o = document.createElement('output');
      o.id = 'ks-root';
      o.hidden = true;
      document.documentElement.appendChild(o);
    }
    o.textContent = JSON.stringify({
      vw: innerWidth, vh: innerHeight,
      tok: (getComputedStyle(document.documentElement)
              .getPropertyValue('--ks-canvas-1') || '').trim(),
      htmlScheme: getComputedStyle(document.documentElement).colorScheme,
      n: total, tokens: tokens, raws: raws, stray: stray.slice(0, 12), strayN: stray.length,
      parts: parts, partsN: fp.parts.length, skipped: fp.skipped.slice(0, 8),
      glassN: glassN, glassFloat: glassFloat,
      orphan: orphan.slice(0, 4), orphanN: orphan.length
    });
  }
  if (document.readyState === 'complete') run();
  else window.addEventListener('load', run);
})();
""".strip()


def _atomic_write(path, data):
    """先写临时文件再 rename，而不是直接 write_bytes。
    线程池里两个请求同时未命中同一子资源时，write_bytes 会先截断再写，
    另一头就读到半截正文——2MB 正文、一路写线程对八路读线程实测：
    960 次读里 465 次读到的长度不等于全文（出现过 26 种长度），换成 rename 是 0 次。
    冷缓存那一跑量到的"裸页只有 72KB 而重拍是 285KB"和这个窗口一致
    （一致性不是证明：那一场的图已经被复拍覆盖掉了，没能当场看到是哪份子资源残缺）。
    页面照样出图，只是可能缺样式——而缺样式的参考档会把整条比对带偏。"""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".part")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def fetch_cached(url):
    """带 /tmp 缓存的 fetch：样式、脚本、图都过这一层，一页实测要抓十几个子资源。
    不缓存时单张抽检图约 100 秒，命中后几秒——同一份名单要能反复重跑才谈得上是道闸门。
    KS_PROXY_CACHE=0 强制重抓，KS_PROXY_TTL 改成功那次的到期秒数（默认 6 小时），
    KS_PROXY_FAIL_TTL 改失败那次的（默认 60 秒）。"""
    key = hashlib.sha1(url.encode()).hexdigest()
    body_p, meta_p, bad_p = CACHE / f"{key}.bin", CACHE / f"{key}.meta", CACHE / f"{key}.bad"
    ttl = int(os.environ.get("KS_PROXY_TTL", str(6 * 3600)))
    use_cache = os.environ.get("KS_PROXY_CACHE", "1") != "0"
    if use_cache and body_p.exists() and meta_p.exists() \
            and time.time() - body_p.stat().st_mtime < ttl:
        code, _, ctype = meta_p.read_text(encoding="utf-8").partition("\t")
        return int(code), ctype, body_p.read_bytes()
    if use_cache and bad_p.exists() and time.time() - bad_p.stat().st_mtime < FAIL_TTL:
        # 一分钟之内对同一条死链重试没有意义：把它原样抛回去，让调用方拿到同一个 504
        raise RuntimeError(bad_p.read_text(encoding="utf-8"))
    try:
        code, ctype, body = fetch(url)
    except Exception as e:
        CACHE.mkdir(parents=True, exist_ok=True)
        # 只记一句（代理会把它带到 504 正文里），且失败不落 body：
        # 读取侧仍然先查 body 再读 meta，半成品那条顺序不变
        _atomic_write(bad_p, str(e).encode("utf-8"))
        raise
    if code == 200 and not body:
        # 空正文原样转给调用方（回 200、Content-Length: 0），但**不进缓存**。
        # 为什么不再按失败处理：实测 css-tricks 的
        # wp-content/plugins/gravityforms/assets/css/dist/gravity-forms-orbital-theme.min.css
        # 直连真站就是 200 + 0 字节——那是站点的答复，不是这一跳的故障，
        # 上一版把它 raise 成 504，于是预热闸门把站点自己的空样式表算成了我的错。
        # 为什么不落盘：缓存里一份空 .bin 会让之后 6 小时每一拍都拿到空样式表，
        # 而"每次都重新问一遍"只花 0.98 秒——贵的那一侧才是该防的。
        # （上一轮曾把一次全站失效归到"缓存里躺着 0 字节的样式表"，那次归因没被复现证明过，
        #  这里不再引用它当理由。）
        return code, ctype, body
    if code == 200:
        CACHE.mkdir(parents=True, exist_ok=True)
        _atomic_write(body_p, body)
        # meta 落在 body 之后：读取侧先查 body 再读 meta，反过来会读到"有 meta 没 body"的半成品
        _atomic_write(meta_p, f"{code}\t{ctype}".encode("utf-8"))
        if bad_p.exists():
            bad_p.unlink()
    return code, ctype, body


def fetch(url):
    """返回 (状态码, 内容类型, 正文字节)。走 curl 而不是 urllib：同一批 URL 实测
    urllib 拿回 0~140 字节的反爬占位，curl 是 81580/290570/95683 字节——
    拿到壳子照样能出图，出的是一张空身子的肤，所以这层必须换。"""
    fd, tmp = tempfile.mkstemp(suffix=".bin")
    os.close(fd)
    try:
        p = subprocess.run(
            ["curl", "-sL", "--compressed", "--max-time", str(UPSTREAM_TIMEOUT),
             "-A", UA,
             "-H", "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
             "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
             "-w", "%{http_code}\t%{content_type}", "-o", tmp, url],
            capture_output=True, text=True, timeout=40,
        )
        meta = p.stdout.split("\t")
        code = int(meta[0]) if meta and meta[0].isdigit() else 0
        ctype = meta[1].strip() if len(meta) > 1 else ""
        if p.returncode != 0:
            # 000/HTTP 0 只说"没拿到"，光靠它分不清超时还是被挡，所以把 curl 的退出码带上
            raise RuntimeError(f"curl 退出码 {p.returncode}（HTTP {code}）{p.stderr.strip()[:80]}")
        with open(tmp, "rb") as fh:
            body = fh.read()
        return code, ctype, body
    finally:
        os.unlink(tmp)


def _resolve(page_url, raw):
    """把 HTML 属性里的地址解成站点上的完整 URL。非 http(s) 的地址原样留着，返回 None。"""
    v = htmllib.unescape(raw).strip()
    if not v or v.startswith("#"):
        return None
    m = re.match(r"(https?)://([^/]+)(/[^?#]*)?", page_url)
    if not m:
        return None
    scheme, origin, path = m.group(1), f"{m.group(1)}://{m.group(2)}", m.group(3) or "/"
    if v.startswith("//"):
        return f"{scheme}:{v}"
    if re.match(r"https?://", v):
        return v
    # 其余带协议的形态（about:、chrome://、filesystem:、mailto: 的漏网写法）不能当相对地址拼：
    # 拼出来的 "…/css-random-function-polyfill/about:blank" 是一条实测出现过的假请求。
    if re.match(r"[a-z][a-z0-9+.-]*:", v, re.I):
        return None
    if v.startswith("/"):
        return origin + v
    return f"{origin}{path.rsplit('/', 1)[0]}/{v}"


def route_home(page_url, page):
    """把子资源（样式表、脚本、图、字体引用）改成"过本机反代"的形状：/s/<站点完整 URL>。

    为什么要绕这一层：原先只把根文档搬进反代，<base href="https://站点/"> 让相对地址
    仍旧直连真站——于是每张图都要重新跑一遍真站网络，快门撞在加载中的哪一秒纯看运气，
    同一个 URL 连拍四张可以是四个大小（实测 373964→540567→647433→650196）。
    抽检比的是"只差注入与否"，两边却各自追着一条会抖的网络链路跑，那条比对就是假的。
    搬进反代之后第二次起全部命中本机缓存，出图不再等运气。

    /s/<完整 URL> 这个形状对 CSS 内部的相对地址同样成立：
    样式表挂在 /s/https://站点/a/b.css，它里面的 url(fonts/x.woff2) 拼出来是
    /s/https://站点/a/fonts/x.woff2，正是本代理认得的形态。

    第三方源照抓不误（图、CDN 上的核心样式表都是页面正文的一部分），
    会抖的那一层由 drop_scripts() 处理，不按域名一刀切。
    """
    root = f"http://{HOST}:{PORT}/s/"

    def one(m):
        attr, q, raw = m.group(1), m.group(2), m.group(3)
        u = _resolve(page_url, raw)
        if not u or u.startswith(root):
            return m.group(0)
        return f'{attr}={q}{root}{htmllib.escape(u, quote=True)}{q}'

    def many(m):
        attr, q, raw = m.group(1), m.group(2), m.group(3)
        out = []
        for part in raw.split(","):
            bits = part.strip().split()
            if not bits:
                out.append(part)
                continue
            u = _resolve(page_url, bits[0])
            bits[0] = f"{root}{htmllib.escape(u, quote=True)}" if u else bits[0]
            out.append(" " + " ".join(bits))
        return f'{attr}={q}{",".join(out)}{q}'

    # <base> 要躲开改写：它指回站点源，我漏掉的相对地址（内联 style 里的 url()、
    # JS 拼的路径）还能顺着它落到真站上；把它也搬进反代的话 "/x" 这一形会变成
    # http://127.0.0.1:端口/x —— 从"迟到"变成"整个 404"，那是更坏的结果。
    held = []

    def hold(m):
        held.append(m.group(0))
        return f"\x00HELD{len(held) - 1}\x00"

    page = re.sub(r"<base\b[^>]*>", hold, page, flags=re.I)
    page = re.sub(r'(?<![\w-])(data-src|poster|src|href)\s*=\s*("|\')(.*?)\2',
                  one, page, flags=re.I)
    page = re.sub(r'(?<![\w-])(srcset)\s*=\s*("|\')(.*?)\2', many, page, flags=re.I)
    return re.sub(r"\x00HELD(\d+)\x00", lambda m: held[int(m.group(1))], page)


def drop_scripts(page):
    """把 <script> 整段摘掉，返回 (正文, 摘掉的段数)。

    抽检的判据是"同一档连拍两张要逐字节一致"，也就是"页面不再往版画东西"。
    脚本活着的时候这条判据基本没有兑现的机会：实测 css-tricks 一篇文章（正是讲
    CSS random() 的那篇）三张连拍三个大小，400911/405122/362098，而它自己的示例
    每次解析都会重新摇一遍——那种页面本来就不该拿来当比对对象。
    广告、统计、嵌入用的 iframe 也都是脚本在 load 之后现塞进来的，快门撞在哪一秒纯看运气。

    摘掉之后"加载完成"重新等于"最终状态"：图、字体、样式表仍按原样抓（它们是正文的一部分），
    只是不再有人在读完后继续改版面。三档走同一条改写路径，比对两边差的仍然只有注入与否。
    """
    n = len(re.findall(r"<script[\s>]", page, re.I))
    page = re.sub(r"<script\b[^>]*>.*?</script\s*>", "", page, flags=re.I | re.S)
    return re.sub(r"<script\b[^>]*/?>", "", page, flags=re.I), n


class H(http.server.BaseHTTPRequestHandler):
    # 默认值是 HTTP/1.0：一问一答就断线。Chrome 对同一主机只开 6 条 socket，
    # 而这一页有 16 个子资源（全搬进反代之后它们同源），于是排在队尾的那几张图
    # 在快门落下时还没被请求过——坏图占位就这么来的。改 HTTP/1.1 复用连接之后
    # 同一档连拍四张逐字节一致（585617 四张），改之前是 585617/585617/585201/585617。
    # 每条响应都带 Content-Length（见 _send），这是 1.1 复用连接的前提。
    # 起作用的是这一行而不是"把 <img> 钉成 decoding=sync"：对照实例（同一条链路、
    # 共用同一份缓存、只做这一处回退）量到的也是四张一致，那一步因此没有留下。
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _trace(self, line):
        """KS_PROXY_LOG 指一个路径就记一行请求流水，专门用来看"这一页到底在等什么"。
        默认关：闸门跑的时候不需要有人等它写盘。"""
        p = os.environ.get("KS_PROXY_LOG")
        if p:
            with open(p, "a", encoding="utf-8") as fh:
                fh.write(f"{time.strftime('%H:%M:%S')} {line}\n")

    def _send(self, code, body, ctype, extra=()):
        # 中文错误文案按字符数算 Content-Length、按字节写盘，两者不等长时 Chrome 会
        # 把截断的响应当加载失败——所以先编码，再用同一份字节既报长度又写。
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def page_via_proxy(self, url):
        """按出图时 Chrome 真正看到的那份 HTML 取这一页（剥脚本、补 <base>、外链改写成走反代）。
        css_list / img_list 都从这里出发：清单必须是"Chrome 会请求的那些地址"，
        自己再解析一遍原始 HTML 就会量到另一棵树——改写前后各一份名单，点了个空。"""
        try:
            code, ctype, raw = fetch_cached(url)
        except Exception:
            return None
        if code != 200 or "html" not in ctype:
            return None
        return route_home(url, drop_scripts(raw.decode("utf-8", "replace"))[0])

    def css_list(self, url):
        """这一页会抓的样式表地址，逐条列成"走反代"的形式，给 spot-check.sh 预热用。
        快门不该撞在"站点自己的 CSS 还在路上"的那一秒——预先把它们拖进本机缓存之后，
        每一拍都是从本机取 CSS。

        它同时是"这一格拍的是不是上了样式的页面"那道闸门的落点：上游等待上限压到 10 秒、
        失败又进 60 秒负缓存之后，一张慢的站点主样式表会被判死，于是整页塌成无样式——
        实测 css-tricks 的 grid 指南在 497154（有样式）和 193271（无样式，黑字标占满整屏）
        两种状态之间来回，而**无样式那一态自己也是逐字节可复现的**：连拍两张一致这条判据
        根本拦不住它。可复现不等于上了样式，所以这一层要在出图之前把样式表点齐。
        解析放在代理这一侧：只有它知道改写后的形状长什么样。"""
        page = self.page_via_proxy(url)
        if page is None:
            return []
        out = []
        for tag in re.findall(r"<link\b[^>]*>", page, flags=re.I):
            if not re.search(r"""rel\s*=\s*["'][^"']*stylesheet""", tag, flags=re.I):
                continue
            m = re.search(r'href\s*=\s*("|\')(.*?)\1', tag, flags=re.I)
            if m and m.group(2).startswith(f"http://{HOST}:{PORT}/s/"):
                out.append(m.group(2))
        return out

    def img_list(self, url):
        """这一页 <img> 的 src，同样列成走反代的形式。和样式表同一层理由：
        没预热时每一拍都在重新等图，等到的画上、没等到的留破图占位——版面因此整页漂移。
        实测 css-tricks 首页 49 个 <img>（28 个不同 src）里 24 个请求失败：
        坏链进 60 秒负缓存，过期那一次又要等满上游上限，于是同一档连拍六张给出四个大小
        （653189 / 343011 / 454176 / 653461），裸页档也定不下来。
        先把 src 逐个点一遍之后，同一档六连拍塌到 3 个状态且出现相邻两张逐字节一致
        （653185 连中两次）——抖动从"整页重排"降到解码边缘的几个像素。
        只点 src 不点 srcset：dpr=1 下 Chrome 取的就是这一支，实测够了，
        而把 28 个 srcset 的候选全拖进缓存会让"就位"这个数不再等于 Chrome 请求过的东西。"""
        page = self.page_via_proxy(url)
        if page is None:
            return []
        srcs = []
        for tag in re.findall(r"<img\b[^>]*>", page, flags=re.I):
            m = re.search(r'<img\b[^>]*?\ssrc\s*=\s*("|\')(.*?)\1', tag, flags=re.I)
            if m and m.group(2).startswith(f"http://{HOST}:{PORT}/s/"):
                srcs.append(m.group(2))
        # 去重保序：css-tricks 首页 49 个 <img> 只有 28 个不同的 src（同一张头像在卡片流里
        # 被引了三四次）。不去重就是把同一个 URL 等三遍，而失败的那些每次都要重新等满
        # 上游上限——实测这一格光预热就烧掉两分钟。清单也不该重复点同一条名。
        return list(dict.fromkeys(srcs))

    def do_GET(self):
        if self.path.startswith("/s/"):
            query = self.path[3:].partition("?")[2]
            # 与出图同一条 URL 形状，只是要的是清单而不是页面：省掉再编码一层。
            # 样式表和图片走同一支：两条链路必须一模一样，否则"点齐"这件事在两边各说一遍
            for kind, lister in (("csslist", self.css_list), ("imglist", self.img_list)):
                if kind in query:
                    body = "\n".join(lister(self.path[3:].partition("?")[0]))
                    return self._send(200, body.encode("utf-8"), "text/plain; charset=utf-8")
            return self.proxy()
        if self.path == "/healthz":
            return self._send(200, b"ok", "text/plain; charset=utf-8")
        return self._send(404, b"not found", "text/plain; charset=utf-8")

    def proxy(self):
        url, _, query = self.path[3:].partition("?")
        theme = "dark" if "night" in query else "light"
        # ?bare：同一条抓取与改写路径，只是不注入皮肤。
        # 裸页原先直接开真站，于是比对两边隔着两条链路——反代有缓存、剥了 CSP、补了 <base>，
        # 裸页没有。实测这一格就是这么塌的：同一个 MDN，裸页 8.7KB 空白而挂肤页 916KB，
        # 报出来的却是"站点侧不可用"。让两边只差皮肤这一处，红才归得到皮肤头上。
        bare = "bare" in query
        # ?noskin：探针照塞、皮肤与面板档都不塞。这一档是为"这块玻璃是谁给的"设立的——
        # isGlass 是视觉谓词（计算值 blur ＋ color(srgb），站点自涂的半透会被算进「穿上玻璃 N」。
        # 同一页两趟一比，掉了的那些才是族净增的。与 ?bare 只差一处：bare 连探针都不塞
        # （抽检的裸页档用它，两边隔着的是同一条链路），noskin 要读探针带回的数。
        noskin = "noskin" in query
        # ?glassprobe：在上了肤的页面上跑普查脚本，把"哪些可见的 fixed/sticky 面真的穿上了玻璃"
        # 写进 <output id="ks-glass">，供 tools/glass-census.py 用 --dump-dom 取回。
        # 判据与用途都写在 GLASS_PROBE 那一格，这里不复述（复述迟早和实现分家）。
        # 判据与用途、以及它只出哪一条判定，都写在 tools/glass-census.py 抬头，这里不复述
        # （复述迟早和实现分家）。
        probe = "glassprobe" in query
        root = "rootprobe" in query
        # ?keepjs：不摘站点的 <script>，让页面自己把下拉／弹层／遮罩造出来。
        # 默认那条链路摘脚本有两个正当理由（见 drop_scripts 那一段）：内联脚本里的
        # document.write("</head>") 会污染"注入点唯一"的判断，也会让缩水闸门虚报。
        # 代价是站点用 JS 现造的浮层在这一档里根本不存在——README 已把这条盲区登记。
        # 这一档就是为那一格开的：留着脚本就得接受那两处风险，所以它不碰出图与哨兵两档
        # （出图要逐字节稳定），表头里那格填 -1 而不是 0（0 的意思是"这页本来没脚本"）。
        keepjs = "keepjs" in query
        if keepjs and bare:
            return self._send(400, "?bare&keepjs 没意义：bare 那一档不注入任何东西，"
                                   "摘不摘脚本都不改变它量的是什么",
                              "text/plain; charset=utf-8")
        if keepjs and "sentinel" in query:
            return self._send(400, "?keepjs&sentinel 没意义：哨兵档要逐字节可比的两张图，"
                                   "开着脚本的页面自己就会动",
                              "text/plain; charset=utf-8")
        if probe and bare:
            return self._send(400, "?bare&glassprobe 没意义：裸页没有玻璃可普查",
                              "text/plain; charset=utf-8")
        if root and bare:
            return self._send(400, "?bare&rootprobe 没意义：裸页没有玻璃可认，"
                                   "候选词根追到的位置倒是能量，但那不是这张表问的",
                              "text/plain; charset=utf-8")
        if probe and root:
            return self._send(400, "一次只跑一档探针：?glassprobe 与 ?rootprobe 各写各的 "
                                   "<output>，同页跑会把两档的 load 时机绑在一起",
                              "text/plain; charset=utf-8")
        # ?sentinel：把三档画布 token 换成纯绿，出一张"只改颜色不改版式"的同页图。
        # 用途是可读性闸门的归因：同一个像素坐标在两张图里比对，动了＝那块底是我们画的，
        # 没动＝站家自己的容器把底衬盖住了（README 里"让路"那一层）。
        # 为什么不在一张图上认颜色：§3 那层 7% 叠色膜把我们的画布洗到离 token 差 1–6 个通道，
        # 而站点自涂的深面板离 token 只差 8——两头挤在同一条尺的两侧，任何绝对阈值都是刀口，
        # 实测的接管行数会随阈值在 7/22/29/34 之间跳（详见 legibility.py 注释）。
        sent = "sentinel" in query
        if sent and bare:
            return self._send(400, "?bare&sentinel 没意义：裸页档没有皮肤可标记",
                              "text/plain; charset=utf-8")
        m = re.match(r"(https?)://([^/]+)", url)
        if not m:
            return self._send(400, "路径要长成 /s/https://site/path", "text/plain; charset=utf-8")
        t0 = time.monotonic()
        try:
            code, ctype, raw = fetch_cached(url)
        except Exception as e:
            # 504＝"我这一跳没走到头"（超时、连不上、curl 非零退出、200 但零字节）。
            # 和下面那个 502 分开是有用的：抽检的预热闸门要区分"站点自己的外链就是坏的"
            # 和"我这台机器没取到"，前者三档一样缺、比对照样成立，后者不能拿来当比对对象。
            self._trace(f"FAIL {round(time.monotonic()-t0,1)}s {url} ({e})")
            return self._send(504, f"本机这一跳没取到: {e}".encode(), "text/plain; charset=utf-8")
        self._trace(f"{code} {round(time.monotonic()-t0,1)}s {len(raw)}B {ctype[:24]} {url}")
        if code != 200:
            # 502＝站点答了，答的是 404/403 之类：它自己的外链就是这么坏的
            return self._send(502, f"上游 HTTP {code}（站点自己给的就是这个码）".encode(),
                              "text/plain; charset=utf-8")
        if "html" not in ctype:
            # 子资源原样转发，不注入。短正文那道闸门在这里之后：它是防"反爬壳子"的，
            # 只对该看正文的 HTML 成立——一张 300 字节的 favicon 或一段小 CSS 本来就没那么大，
            # 拿 1500 去卡它会把好端端的子资源 502 掉，版面塌得比缺样式还早。
            return self._send(200, raw, ctype)
        if len(raw) < MIN_BYTES:
            # 短正文＝被反爬挡了。宁可 502 也不要给出一张"皮肤上了、身子是空的"的图
            return self._send(502, f"上游正文只有 {len(raw)} 字节（<{MIN_BYTES}），判定为被挡".encode(),
                              "text/plain; charset=utf-8")

        page = raw.decode("utf-8", "replace")
        page = re.sub(r"<meta[^>]+Content-Security-Policy[^>]*>", "", page, flags=re.I)
        # 摘脚本要赶在补 <base> 和找注入点之前：内联脚本里常写 document.write("</head>")
        # 这类字符串，它们会污染"注入点唯一"的判断，也会让下面的缩水闸门虚报。
        # ?keepjs 那一档反过来：它要的就是站点自己把 JS 现造的浮层建出来，所以这里不摘，
        # 表头那格填 -1（"这一档没摘"），和 0（"这页本来没脚本"）分开说。
        if keepjs:
            n_scripts = -1
        else:
            page, n_scripts = drop_scripts(page)
        # <base> 得赶在站点自己的 <link> 之前落位：它只对"从它往后解析"的 URL 生效。
        # 跟皮肤一起塞在 </head> 前，MDN 那 18 个 /static/client/*.css 仍按 127.0.0.1 的源去取，
        # 集体 404，版面塌成单列——抽检量到的就不是"上了肤的真页"而是"被扒了 CSS 的裸 HTML"，
        # 而这张图照样能出、看着还挺像换了配色，只有正文行数那类检查会露馅。
        # 站点自己写了 <base> 就不动它：相对地址跟着它的源走，本来就是要的效果。
        if not re.search(r"<base[\s>]", page, re.I):
            for pat in (r"<head(?=[\s>])[^>]*>", r"<html(?=[\s>])[^>]*>"):
                hits = list(re.finditer(pat, page, re.I))
                if len(hits) == 1:
                    page = (page[:hits[0].end()]
                            + f'<base href="{m.group(1)}://{m.group(2)}/">\n'
                            + page[hits[0].end():])
                    break
        page = route_home(url, page)
        before_inject = len(page.encode("utf-8"))   # 和产出同量纲（字节）：中文页上字符数会把它放宽
        inject = ("" if noskin else
                  f'<style id="ks-skin">\n{SKIN}\n</style>\n'
                  f'<style id="ks-panel">:root{{--kScheme:{theme}; --kEmoji:"";}}</style>\n')
        if sent:
            # 排在皮肤之后、带 !important：注入点只在 </head> 之前挪位置，谁后面谁赢，
            # 而"谁后面"不该由站点或皮肤的声明顺序决定——这一档的唯一用途就是把皮肤的调色板扳成绿色。
            inject += ('<style id="ks-sent">:root{' + ";".join(SENTINELS) + "}</style>\n")
        if probe:
            # 站点的 <script> 已经在上面被摘掉了，这一段是我们自己塞的，所以它必须在摘之后注入。
            # 带 id 是为了让"探针落没落位"有一条能查的证据，而不是靠 <output> 出没出现去反推
            # （探针没跑起来时 output 根本不存在，两种失败在页面上长得一样）。
            inject += f'<script id="ks-glass-probe">{GLASS_PROBE}</script>\n'
        if root:
            inject += ('<script id="ks-root-probe">'
                       + ROOT_PROBE.replace("__TOKENS__", json.dumps(ROOT_TOKENS)).replace("__RAW__", json.dumps(ROOT_RAW))
                       + '</script>\n')
        if not bare:
            # 注入点按"唯一性"依次退让：站点的 </head> 可能大写、也可能整个省掉（合法 HTML），
            # 猜错位置等于悄悄没注入，所以每一档都要求只命中一次，全落空就报错而不是硬塞。
            for pat, where in ((r"</head\s*>", "before"),
                               (r"<head(?=[\s>])[^>]*>", "after"),
                               (r"<body(?=[\s>])[^>]*>", "before")):
                hits = list(re.finditer(pat, page, re.I))
                if len(hits) == 1:
                    at = hits[0].start() if where == "before" else hits[0].end()
                    page = page[:at] + inject + page[at:]
                    break
            else:
                return self._send(500, "找不到唯一注入点（</head>、<head>、<body> 都不唯一或都不在）",
                                  "text/plain; charset=utf-8")
        # 缩水闸门比的是"摘完脚本之后"的长度：脚本本来就该被摘掉，拿它当基准会让 JS 重的站
        # 集体虚报；而拼接写错时标记照样留着、正文整篇消失（就是这么产出一批空图的）那种事
        # 仍会撞线——正文没被摘掉过。
        out = page.encode("utf-8")
        if len(out) < before_inject * 0.5:
            return self._send(500, f"改写后正文缩水：摘脚本后 {before_inject} 字节，"
                                   f"产出 {len(out)} 字节", "text/plain; charset=utf-8")
        if not bare and not noskin and "ks-skin" not in page:
            # 光查"有没有产出"不够：注入没落位时页面照样能出图，出的是一张没上肤的图
            return self._send(500, "注入没落位：产出里没有 ks-skin", "text/plain; charset=utf-8")
        if (bare or noskin) and "ks-skin" in page:
            # 裸页里混进皮肤＝这一档和上肤档隔着同一条链路比同一件东西，比对整个失去意义
            return self._send(500, "?bare 的产出里出现了 ks-skin", "text/plain; charset=utf-8")
        if sent and "ks-sent" not in page:
            # 标记没落位就出一张"以为标了绿"的图：归因那张图上没有一个像素会动，
            # 于是整档被读成"皮肤一行都没涂到"，红会报在错的因上。
            return self._send(500, "哨兵档没落位：产出里没有 ks-sent", "text/plain; charset=utf-8")
        if probe and "ks-glass-probe" not in page:
            # 同理：探针段没落位时 Chrome 照样能出 DOM，普查读到的是"这站一个浮面都没有"，
            # 而那句话会被当成站点改版面的证据。
            return self._send(500, "普查档没落位：产出里没有 ks-glass-probe",
                              "text/plain; charset=utf-8")
        if root and "ks-root-probe" not in page:
            # 同理：这一段没落位时 Chrome 照样出 DOM，候选词根普查会读到"这截一个都没命中"，
            # 而那句话会被当成"这截词根安全"的证据——正好是这张表要防的那种假绿。
            return self._send(500, "候选词根档没落位：产出里没有 ks-root-probe",
                              "text/plain; charset=utf-8")
        # 摘了几段脚本写进表头：抽检脚本从 HTTP/1.1 表头里数它，"这一格隔着什么"才不用猜。
        # 0 也是合法值（纯静态页），它要说的是"这一页本来没脚本"，不是"忘了摘"。
        return self._send(200, out, "text/html; charset=utf-8",
                          [("X-KS-No-Scripts", str(n_scripts))])


if not SKIN.strip():
    sys.exit("preview/skin.css 是空的，先跑 tools/strip.py")

# 开机那段收进 __main__：上面那几条守卫（画布认得出、墨 token 扳得到）是**判据**，
# 而这一本原来模块级直接 serve——于是任何想"只把判据跑一遍"的消费者（电池那柄 K18）
# exec 到这里就把反代开起来了，守卫的 rc 永远读不到。收进来之后 `python3 tools/proxy.py`
# 照旧开机（spot-check.sh 走的就是这条路），exec_module 只走判据、不占端口。
if __name__ == "__main__":
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer((HOST, PORT), H) as srv:
        srv.daemon_threads = True
        print(f"抽检反代就位 http://{HOST}:{PORT}/s/<站点完整URL>"
              f"（只监听本机，加 ?night 出夜晚档、?bare 出同链路裸页）", flush=True)
        srv.serve_forever()
