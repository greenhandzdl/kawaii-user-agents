#!/usr/bin/env python3
"""从 kawaii-skin.user.css 解析色 token 与叠色膜参数，实算 WCAG 对比度闸门。

色值只住在 CSS 里：本脚本不复制任何 hex，解析不到就报错退出。
面板里每一档叠色强度都要过线——用户不该能选出一个不可读的档。
"""
import re
import sys
from pathlib import Path

CSS = Path(__file__).resolve().parent.parent / "kawaii-skin.user.css"

REQUIRED = {
    "ink-1": 4.5, "ink-3": 3.0,
    "link": 4.5, "head": 4.5,
}
BACKGROUNDS = ["canvas-1", "canvas-2", "canvas-3"]
# 混色型底：浓度由面板某一档决定，所以判定必须扫过面板的每一个档——
# 用户能选出来的最差那一档才是"能不能读"的那一问，出厂档只是其中一格。
# 第二列是这一格里"谁把档拧浓"的面量名，只用来打标。
# 每一支混色型底只配**一门**文字：配哪门由 BTN_INK 点名，理由写在那里。
MIXED = [("btn", "kBtn")]
BTN_INK = {"btn": "ink-1"}


def die(msg):
    print(f"GATE ERROR: {msg}")
    sys.exit(2)


def parse_hex(text):
    m = re.fullmatch(r"#([0-9a-fA-F]{6})", text.strip())
    return None if not m else tuple(int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4))


def rel_lum(rgb):
    def chan(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (chan(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    l1, l2 = sorted((rel_lum(a), rel_lum(b)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def wash(page, veil_rgb, alpha):
    """膜以 alpha 盖在页面色之上后的合成色。"""
    return tuple(v * alpha + p * (1 - alpha) for p, v in zip(page, veil_rgb))


# "两个色是不是同一个色"的带宽只住这一格：check-controls.py 的 close() 拿它比探针读数，
# 这里拿它判"按钮面有没有和页面撞色"。两本各写一个数，就会有一本先漂。
EQ_TOL = 2


def close(a, b, tol=None):
    t = EQ_TOL if tol is None else tol
    return a is not None and b is not None and all(abs(x - y) <= t for x, y in zip(a, b))


# color-mix() 的形状只在这里解释一遍：check-controls.py 的期望值折叠和这里的 token
# 表折叠用同一条正则（它通过 gate.MIX_RE 取），两本各写一条就会有一本先漂。
MIX_RE = re.compile(
    r"color-mix\(in srgb,\s*var\(--ks-([\w-]+)\)\s*"
    r"(?:([0-9.]+)%|calc\(var\(--k[\w-]+,\s*1\)\s*\*\s*([0-9.]+)%\)"
    r"|calc\(100%\s*-\s*var\(--k[\w-]+,\s*1\)\s*\*\s*([0-9.]+)%\))\s*,\s*"
    r"(transparent|var\(--ks-([\w-]+)\))\s*\)")

# 面板档挂在 calc 的那个变量名不在 MIX_RE 的捕获里（加一组会把 check-controls 用的
# 组号全挪位），所以单独按名字取。
KNOB_RE = re.compile(r"calc\(\s*var\(--([\w-]+),")

# token 定义那一侧的形：light-dark(color-mix(...), color-mix(...))。
# 两支各是一个配平的 color-mix，用 [^)]* 截会断在 calc( 里面那个 var() 的括号上；
# color-mix 里最深的嵌套是 calc(var(--kX, 1) * N%)，两层，所以括号配平写两遍。
_PAREN2 = r"(?:[^()]|\((?:[^()]|\([^()]*\))*\))*"
MIX_TOKEN_RE = re.compile(
    r"--ks-([a-z0-9-]+)\s*:\s*light-dark\(\s*"
    r"(color-mix\(" + _PAREN2 + r"\))\s*,\s*"
    r"(color-mix\(" + _PAREN2 + r"\))\s*\)", re.S)


def mix_parts(text, who):
    """light-dark 的一支 color-mix → (混入的 token, 回退档下的比例, 打底的 token, 面板档名)。

    token 表只收实色：transparent 打底那一形是"透出多少"那一格，不归这里折叠。
    """
    mm = MIX_RE.search(text)
    if not mm:
        die(f"--ks-{who} 里那一支 color-mix 形状解不开：{text.strip()[:70]!r}")
    if mm.group(5) == "transparent" or not mm.group(6):
        die(f"--ks-{who} 那一支以 transparent 打底，token 表算不出实色（它属于玻璃那一格）")
    if mm.group(4) is not None:
        die(f"--ks-{who} 用的是 calc(100% - 档 * N%) 那一形，token 表只折叠"
            f"「档越大越浓」这一形，折叠方向要另立判据")
    knob = KNOB_RE.search(text)
    pct = (float(mm.group(2)) if mm.group(2) is not None
           else float(mm.group(3))) / 100.0
    return {"over": mm.group(1), "pct": pct, "base": mm.group(6),
            "knob": knob.group(1) if knob else None}


def load_mix_token(src, name):
    """按名字取 light-dark(color-mix, color-mix) 型 token 的两支结构。"""
    for tok, day, night in MIX_TOKEN_RE.findall(src):
        if tok == name:
            return {b: mix_parts(t, name) for b, t in (("light", day), ("dark", night))}
    die(f"CSS 里 --ks-{name} 不是 light-dark(color-mix(...), color-mix(...)) 那一形")


def mix_at(tokens, part, branch, knob, who):
    """把一支 color-mix 折成实色：knob 是面板档的乘数（无档位名的固定比例不乘）。"""
    if part["knob"] is None:
        knob = 1.0
    over = tokens.get(part["over"])
    base = tokens.get(part["base"])
    if over is None or base is None:
        die(f"--ks-{who} 混色引用的 token 表里没有（over={part['over']} "
            f"base={part['base']}）——引用顺序或名字错了")
    return wash(base[branch], over[branch], part["pct"] * knob)


def load_tokens(src):
    """解析所有 light-dark(白天, 夜晚) 形式的 --ks-* token。

    第二个消费者是 check-controls.py：色值只住在 CSS 里这条规矩，
    一旦两个脚本各抄一份解析器就会漂移，所以解析器本身也只住一处。
    """
    tokens = {}
    for name, day, night in re.findall(
        r"--ks-([a-z0-9-]+)\s*:\s*light-dark\(\s*(#[0-9a-fA-F]{6})\s*,\s*(#[0-9a-fA-F]{6})\s*\)",
        src,
    ):
        tokens[name] = {"light": parse_hex(day), "dark": parse_hex(night)}
    # 混色型 token 折叠在面板回退档上（calc(var(--kX, 1) * N%) 的那个 1）：
    # 探针页加载的正是 strip.py 注进 preview/skin.css 的出厂默认值，两边同一档。
    for name, _day, _night in MIX_TOKEN_RE.findall(src):
        parts = load_mix_token(src, name)
        tokens[name] = {b: mix_at(tokens, parts[b], b, 1.0, name)
                        for b in ("light", "dark")}
    return tokens


def load_sakura(src):
    """强调色的回退值。第二个消费者是 check-controls.py，理由同 load_tokens。"""
    acc = re.search(r"--ks-sakura\s*:\s*var\(--kAccent,\s*(#[0-9a-fA-F]{6})\)", src)
    if not acc:
        die("没解析到 --ks-sakura 的回退色")
    return parse_hex(acc.group(1))


def main():
    src = CSS.read_text(encoding="utf-8")
    if not src.strip():
        die("样式表是空的")

    tokens = load_tokens(src)
    missing = [t for t in list(REQUIRED) + BACKGROUNDS + [n for n, _ in MIXED] + ["petal"]
               if t not in tokens]
    if missing:
        die(f"CSS 里没解析到这些 token: {missing}")

    # 叠色强度：面板里的每一档都进判定
    sel = re.search(r"@var\s+select\s+kVeil.*?\n\s*}\n", src, re.S)
    if not sel:
        die("没找到 @var select kVeil 块")
    opts = [(lbl.replace("*", ""), float(pct)) for lbl, pct in
            re.findall(r'"([^"]+)"\s*:\s*"([0-9.]+)%"', sel.group(0))]
    if not opts:
        die("kVeil 块里没解析到任何档位")
    starred = [(l, p) for l, p in
               re.findall(r'"([^"]+\*)"\s*:\s*"([0-9.]+)%"', sel.group(0))]
    if len(starred) != 1:
        die(f"kVeil 块里带 * 的默认项应有且仅有一个，实际 {len(starred)} 个")

    fb = re.search(r"--ks-veil-a\s*:\s*var\(--kVeil,\s*([0-9.]+)%\)", src)
    if not fb:
        die("没找到 --ks-veil-a 的回退值")
    if abs(float(fb.group(1)) - float(starred[0][1])) > 1e-9:
        die(f"kVeil 面板默认 {starred[0][1]} ≠ CSS 回退 {fb.group(1)}%")

    # 按钮饱满度：面板里的每一档都进判定（形状同 kVeil，值不带 %）
    bsel = re.search(r"@var\s+select\s+kBtn.*?\n\s*}\n", src, re.S)
    if not bsel:
        die("没找到 @var select kBtn 块")
    barns = sorted({float(v) for v in re.findall(r'"[^"]+"\s*:\s*"([0-9.]+)"', bsel.group(0))})
    if not barns:
        die("kBtn 块里没解析到任何档位")
    bstar = [float(v) for _l, v in
             re.findall(r'"([^"]+\*)"\s*:\s*"([0-9.]+)"', bsel.group(0))]
    if len(bstar) != 1:
        die(f"kBtn 带 * 的默认档应有且仅有一个，实际 {len(bstar)} 个")
    bfb = re.findall(r"calc\(\s*var\(--kBtn,\s*([0-9.]+)\)", src)
    if not bfb:
        die("没找到 --ks-btn 里 calc(var(--kBtn, …)) 的回退档")
    if {float(x) for x in bfb} != {bstar[0]}:
        die(f"kBtn 面板默认 {bstar[0]} 与 CSS 回退 {sorted({float(x) for x in bfb})} 不一致")

    mults = set(re.findall(r"calc\(\s*var\(--ks-veil-a\)\s*\*\s*([0-9.]+)\s*\)", src))
    if not mults:
        die("没找到圆点层的强度倍数")
    if len(mults) > 1:
        die(f"两层圆点倍数不一致 {sorted(mults)}，闸门只按第一层算会低估")
    dot_mult = float(mults.pop())

    blk = re.search(r"html::before\s*\{(.*?)\n  \}", src, re.S)
    if not blk:
        die("没定位到 html::before 规则块")
    stops = {}
    for branch, i in (("light", 0), ("dark", 1)):
        stops[branch] = [parse_hex(c[i]) for c in re.findall(
            r"light-dark\(\s*(#[0-9a-fA-F]{6})\s*,\s*(#[0-9a-fA-F]{6})\s*\)", blk.group(1))]
        if not stops[branch]:
            die(f"膜里没有 {branch} 分支的渐变停色")

    # 选中态：::selection 底色 = 强调色按 kSparkle 百分比混进来
    sp = re.search(r"::selection\s*\{[^}]*?var\(--ks-sakura\)\s*"
                   r"calc\(var\(--kSparkle, 1\)\s*\*\s*([0-9.]+)%\)", src, re.S)
    if not sp:
        die("没解析到 ::selection 的混色比例")
    sel_pct = float(sp.group(1)) / 100.0
    sakura = load_sakura(src)

    # 字体档：面板默认档和 CSS 里的 --ks-stack 是同一个清单写了两遍，
    # 漂移了没人发现，所以在这儿钉住；同时要求"站点原字体"那档必须是 revert。
    fblk = re.search(r"@var\s+select\s+kFont.*?\n\s*}\n", src, re.S)
    if not fblk:
        die("没找到 @var select kFont 块")
    fopts = re.findall(r'"([^"]+)"\s*:\s*"([^"]*)"', fblk.group(0))
    fstar = [v for lbl, v in fopts if lbl.endswith("*")]
    if len(fstar) != 1:
        die(f"kFont 带 * 的默认档应有且仅有一个，实际 {len(fstar)} 个")
    if "revert" not in [v.strip() for _, v in fopts]:
        die("kFont 里没有 value=revert 的档位，字体方面就没有逃生阀")
    css_stack = re.search(r"--ks-stack\s*:\s*([^;]+);", src)
    if not css_stack:
        die("没找到 --ks-stack")
    if not re.search(r"font-family:\s*var\(--kFont,\s*var\(--ks-stack\)\)\s*!important", src):
        die("font-family 没走 var(--kFont, var(--ks-stack))，面板选不到栈")

    def fams(text):
        return [re.sub(r"\s+", " ", f).strip().strip("\"'") for f in text.split(",")]

    if fams(fstar[0]) != fams(css_stack.group(1)):
        die(f"面板默认字体档与 --ks-stack 漂移：{fams(fstar[0])} vs {fams(css_stack.group(1))}")
    print(f"字体      面板默认 {len(fams(fstar[0]))} 个家庭，与 --ks-stack 逐项一致；"
          f"逃生阀 revert 在档")

    def veiled(ink_rgb, bg_rgb, branch, pct):
        """最坏情况：整屏叠一层渐变停色，再叠一层圆点。"""
        petal = tokens["petal"][branch]
        a_lin, a_dot = pct / 100.0, pct / 100.0 * dot_mult
        best = None
        for lin in stops[branch]:
            cur = tuple(wash(wash(c, lin, a_lin), petal, a_dot) for c in (ink_rgb, bg_rgb))
            r = contrast(*cur)
            if best is None or r < best:
                best = r
        return best

    print(f"解析到 {len(tokens)} 个色 token；叠色档位 {len(opts)} 档："
          f"{', '.join(f'{l} {p}%' for l, p in opts)}；圆点 ×{dot_mult}")
    print(f"选中态底色 = 强调色 {sakura} 混入 {sel_pct * 100:.0f}%\n")

    failures = []
    btn_parts = {n: load_mix_token(src, n) for n, _ in MIXED}
    for branch in ("light", "dark"):
        label = "白天 粉白" if branch == "light" else "夜晚 粉紫"
        print(f"=== {label} ===")
        print(f"{'文字':<8}{'底色':<12}{'要求':>6}{'裸':>7}{'最差档':>9}  判定")

        # 每个底色带一组候选面：常规 canvas 只有一格，混色型底要把面板的每一档都摆上来
        cases = [(ink, bg, [(tokens[bg][branch], "")])
                 for ink in REQUIRED for bg in BACKGROUNDS]
        # ::selection 在 CSS 里是 color-mix(sakura X%, transparent)，落到页面即
        # "sakura 以 X% 盖在底色上"，所以 page=底色、veil=sakura，方向不能颠倒
        cases += [("ink-1", "::selection",
                   [(wash(tokens["canvas-1"][branch], sakura, sel_pct), "")])]
        for name, knob in MIXED:
            # 出厂档排第一（表里"裸"那一列印的就是它），其余档按面板值排进来
            order = [bstar[0]] + [a for a in barns if a != bstar[0]]
            variants = [(mix_at(tokens, btn_parts[name][branch], branch, k, name),
                         "" if k == bstar[0] else f"{knob}={k:g}") for k in order]
            # 只配 BTN_INK 点名的那一门墨：§4b 那条 button 规则往按钮面上写的 color 就是
            # ink-1，四门全配会提一个皮肤不画的组合（标题色/链接色不会出现在 <button> 上），
            # 红线落在"假如把标题压成浓粉底"而不是"这一档能不能读"。
            # 曾经没覆盖的组合：<button> 里嵌 del/s —— `del, s { color: var(--ks-ink-3) }` 直接命中
            # 子元素，按钮面上的 ink-1 只是被继承的那一层压不过它，所以 ink-3 确实能落到混色面上，
            # 而同口径上限只有白天 10.0%／夜晚 14.2%（出厂 34%/24%）——配进本闸门就会红。
            # 收法不是调阈值：§4b 补了面级的 `button :is(del, s)` → ink-1，§4c 后代元素表补了 del, s，
            # 于是"ink-3 落在我们涂的面上"变成皮肤不画的组合，本闸门因此仍只判 BTN_INK 点名的那一门墨。
            # 那三行的尺子在 tools/check-controls.py（按钮面／玻璃面／画布淡划字色）＋ knives.py 的 M07。
            cases += [(BTN_INK[name], name, variants)]
        for ink, bg_name, bgs in cases:
            need = 4.5 if ink != "ink-3" else 3.0
            raw = contrast(tokens[ink][branch], bgs[0][0])
            worst, worst_pct = raw, "裸"
            for bg_rgb, bg_lbl in bgs:
                v0 = contrast(tokens[ink][branch], bg_rgb)
                if v0 < worst:
                    worst, worst_pct = v0, bg_lbl or "裸"
                for lbl, pct in opts:
                    v = veiled(tokens[ink][branch], bg_rgb, branch, pct)
                    if v < worst:
                        worst, worst_pct = v, f"{(bg_lbl + ' ') if bg_lbl else ''}膜 {pct:g}%"
            ok = worst >= need
            if not ok:
                failures.append(f"{branch}: {ink}/{bg_name} = {worst:.2f} < {need}（档 {worst_pct}）")
            print(f"{ink:<8}{bg_name:<12}{need:>6}{raw:>7.2f}{worst:>9.2f}"
                  f"  {'PASS' if ok else 'FAIL'}"
                  f"{'' if ok else f'  <- {worst_pct} 档'}")
        print()

    # ---- 正控制：三道，逐层证明判定逻辑与膜都真的开火 ----
    white = (255, 255, 255)
    if contrast(white, tokens["canvas-1"]["light"]) >= 4.5:
        die("正控制 1 没开火：白字对粉白底竟然达标，contrast() 坏了")
    good = tokens["ink-1"]["light"]
    base = contrast(good, tokens["canvas-1"]["light"])
    top_pct = max(p for _, p in opts)
    if veiled(good, tokens["canvas-1"]["light"], "light", top_pct) >= base:
        die("正控制 2 没开火：加膜后对比度没下降，veiled() 是空转")
    if abs(veiled(good, tokens["canvas-1"]["light"], "light", 0) - base) > 1e-9:
        die("正控制 3 没开火：0% 膜没退化成裸值，最坏档搜索被污染")
    # 混色方向哨兵：强调色混得越多，深墨对底的对比度必须越低。反了就说明 wash 实参颠倒
    c1 = tokens["canvas-1"]["light"]
    if not (contrast(good, wash(c1, sakura, 0.60)) < contrast(good, wash(c1, sakura, 0.10))):
        die("正控制 4 没开火：选中态混色方向反了（wash 的 page/veil 实参颠倒）")
    print(f"正控制：白字/粉白底 {contrast(white, tokens['canvas-1']['light']):.2f} 会被拒；"
          f"ink-1 裸 {base:.2f} → {top_pct:g}% 档 {veiled(good, tokens['canvas-1']['light'], 'light', top_pct):.2f}；"
          f"0% 档 {veiled(good, tokens['canvas-1']['light'], 'light', 0):.2f}")

    # 面板档哨兵：kBtn 从出厂档拧到最浓档，折出来的底必须真的变。
    # 旋钮没接进混色时两格会算出同一个数，扫档判定就退化成把出厂值重复三遍。
    rich = max(barns)
    if rich == bstar[0]:
        die(f"kBtn 面板里没有比出厂档 {bstar[0]} 更浓的档，扫档判定只是在重复出厂值")
    for b in ("light", "dark"):
        f1 = mix_at(tokens, btn_parts["btn"][b], b, bstar[0], "btn")
        f2 = mix_at(tokens, btn_parts["btn"][b], b, rich, "btn")
        if max(abs(x - y) for x, y in zip(f1, f2)) < 1.0:
            die(f"kBtn {bstar[0]}→{rich} 折出的 --ks-btn {b} 分支几乎没动"
                f"（{tuple(round(v) for v in f1)} vs {tuple(round(v) for v in f2)}）：档位没接进混色")
    print(f"按钮档    kBtn 扫 {len(barns)} 档 {barns}，最浓 {rich:g}× 折出的底两分支都在动")

    # 混色型底的可辨识性：面板每一档折出来的按钮面，都不能和页面三档里的任何一档撞在
    # close() 的带宽里。撞上了对比度判据管不到——墨与面的对比还在，没的是控件边界本身
    # （浮层靠 backdrop 出边界，按钮面只能靠底色）。这一格不是假想：白天旧值 20% 的
    # 最淡档折出 (255, 231, 242)，对 --ks-canvas-3 三通道差 (0, 2, 1)，正落在带宽里。
    margins = {}
    for b in ("light", "dark"):
        for k in barns:
            face = mix_at(tokens, btn_parts["btn"][b], b, k, "btn")
            for cg in BACKGROUNDS:
                if close(face, tokens[cg][b]):
                    die(f"kBtn={k:g} 的 {b} 分支折出按钮面 {tuple(round(v) for v in face)}，"
                        f"与 --ks-{cg} 撞色（带宽 {EQ_TOL}）：这一档把按钮还原成「和页面同色」")
        margins[b] = min(max(abs(x - y) for x, y in zip(
            mix_at(tokens, btn_parts["btn"][b], b, k, "btn"), tokens[cg][b]))
            for k in barns for cg in BACKGROUNDS)
    print(f"按钮面    离最近页面档的最小间距 白天 {margins['light']:.1f} / "
          f"夜晚 {margins['dark']:.1f}（带宽 {EQ_TOL}，每一档都要在带外）")

    if failures:
        print(f"\nGATE FAIL：{len(failures)} 组不达标")
        for f in failures:
            print("  - " + f)
        sys.exit(1)
    print("\nGATE PASS：全部文字/底色配对在最浓叠色档下仍达标")


if __name__ == "__main__":
    main()
