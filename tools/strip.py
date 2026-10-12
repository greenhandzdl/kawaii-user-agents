#!/usr/bin/env python3
"""把 @-moz-document 外壳剥掉，产出可被 <link> 直接引用的 preview/skin.css。

外壳只有头尾两处，所以还原必须是机械的：本脚本会守住"删掉的正好是一开一合"。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "kawaii-skin.user.css"
OUT = ROOT / "preview" / "skin.css"

src = SRC.read_text(encoding="utf-8")
if not src.strip():
    sys.exit("STRIP ERROR: 样式表是空的")

openers = re.findall(r"^@-moz-document[^\n]*\{\s*$", src, re.M)
if len(openers) != 1:
    sys.exit(f"STRIP ERROR: @-moz-document 开壳应有 1 处，实际 {len(openers)}：{openers}")

lines = src.splitlines()
first = next(i for i, l in enumerate(lines) if l.startswith("@-moz-document"))
last = max(i for i, l in enumerate(lines) if l.rstrip() == "}")
if lines[last].rstrip() != "}":
    sys.exit("STRIP ERROR: 收尾的 } 定位失败")
if last - first < 10:
    sys.exit(f"STRIP ERROR: 壳内只有 {last - first} 行，不像完整样式表")

body = "\n".join(lines[first + 1:last]).strip() + "\n"
if body.count("{") != body.count("}"):
    sys.exit(f"STRIP ERROR: 剥壳后花括号不平衡 {body.count('{')} vs {body.count('}')}")
for leak in ("@-moz-document", "==UserStyle=="):
    if leak in body:
        sys.exit(f"STRIP ERROR: 壳残留 {leak!r} 进了预览文件")


def strip_comments(text):
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


# 壳外（头尾）只准有注释和空白：@import、顶层规则写在这儿会被这次剥壳静默吞掉，
# 预览就变成"少了一层样式但依然全绿"的假象 —— 实测过一次，圆体 webfont 就是这么没的。
for label, chunk in (("壳前", "\n".join(lines[:first])), ("壳后", "\n".join(lines[last + 1:]))):
    leftovers = strip_comments(chunk).strip()
    if leftovers:
        sys.exit(f"STRIP ERROR: {label}有会被静默丢掉的实内容：{leftovers[:80]!r}")

# 自包含：用户样式表里任何远程引用都会替每个访问过的站点发一次外部请求，
# 而远程字体在 Stylus 面板里根本无法验证，所以一发现就拦下来。
# 只扫去了注释的正文：注释里会提到 "@import" 这个词本身（下面那条注释就是），
# 拿原文扫等于把说明文字当成违规，闸门会红得莫名其妙。
code = strip_comments(src)
if "@import" in code:
    sys.exit("STRIP ERROR: 出现了 @import —— 这份皮肤必须自包含，不发网络请求")
for remote in re.findall(r"url\(\s*['\"]?(https?:)[^)]*\)", code, re.I):
    sys.exit(f"STRIP ERROR: url() 指向外部（{remote}），这份皮肤不许联网")

# 令牌卫生：var(--x) 既没兜底值又从没定义过，浏览器会静默丢掉整条声明——页面照常渲染、
# 截图照常出、对比度闸门照常绿，只有肉眼看才发现少了一层。实测踩过：--ks-ink-2 这个
# 名字根本不存在（色板从 ink-1 直接跳到 ink-3），写错的那条 :read-only 上色就是这么溜过去的。
panel = {"--" + n for n in re.findall(r"@var\s+\w+\s+([\w-]+)", src)}   # Stylus 面板变量
defined = set(re.findall(r"(--[\w-]+)\s*:", code)) | panel
undef = sorted({n for n, sep in re.findall(r"var\(\s*(--[\w-]+)\s*([,)])", code)
                if sep != "," and n not in defined})
if undef:
    sys.exit(f"STRIP ERROR: 这些 var() 没有兜底值且从未定义，整条声明会被丢掉：{undef}")

# 同一个选择器的同一个属性写两遍：后一条静默顶掉前一条，前一条连同它引用的 token
# 一起变成死码，而页面看起来完全正常。实测 --ks-scrim 就是这么被上面那条
# dialog::backdrop 顶掉的——把被顶掉那行改坏，计算样式闸门一点反应都没有。
def depth1_rules(text):
    """扫出壳内第一层的 (选择器, 声明串)。@ 开头的块整块跳过：
    媒体查询里的覆盖（打印、减动效、强制对比）是故意的，不该算重复。"""
    out, i, n = [], 0, len(text)
    while True:
        j = text.find("{", i)
        if j < 0:
            return out
        sel = " ".join(text[i:j].split())
        k, depth = j + 1, 1
        while k < n and depth:
            depth += {"{": 1, "}": -1}.get(text[k], 0)
            k += 1
        if not sel.startswith("@"):
            out.append((sel, text[j + 1:k - 1]))
        i = k


flat = strip_comments(body)
rules = depth1_rules(flat)
counts = {}
for sel, decls in rules:
    for prop in re.findall(r"(?:^|;)\s*([a-z-]+)\s*:", decls):
        counts[(sel, prop)] = counts.get((sel, prop), 0) + 1
dups = sorted(k for k, n in counts.items() if n > 1)
if dups:
    sys.exit(f"STRIP ERROR: 同一选择器的同一属性写了两遍，后一条会静默顶掉前一条：{dups}")
print(f"结构      壳内第一层 {len(rules)} 个规则块（{len({s for s, _ in rules})} 个选择器）、"
      f"{len(counts)} 个 (选择器, 属性) 配对，无互相遮蔽")

def panel_defaults(src, code):
    """从 ==UserStyle== 头里取每个 @var 的出厂默认值，拼成一条 :root 声明。

    Stylus 在真机上是把这些值以自定义属性写到 :root 上的，预览构建不带就等于
    夹具跑的从来不是用户拿到的那一套。实测漏的是 --kEmoji：content 没法用 1/0 调制，
    样式表里的兜底只能写 none，于是白天档的截图一直没有那朵花——
    而夜晚档有，只因为出图脚本替它硬写了一遍。
    """
    got = {}
    for name, val in re.findall(r'@var\s+checkbox\s+([\w-]+)\s+"[^"]*"\s+([01])', src):
        got[name] = val
    for name, val in re.findall(r'@var\s+color\s+([\w-]+)\s+"[^"]*"\s+(#[0-9a-fA-F]{3,8})', src):
        got[name] = val
    for name, val in re.findall(r'@var\s+text\s+([\w-]+)\s+"[^"]*"\s+"([^"]*)"', src):
        got[name] = f'"{val}"'
    for name, body, in re.findall(r'@var\s+select\s+([\w-]+)\s+"[^"]*"\s*\{([^}]*)\}', src):
        star = re.findall(r'"[^"]*\*"\s*:\s*"([^"]*)"', body)
        if len(star) != 1:
            sys.exit(f"STRIP ERROR: 面板项 {name} 的默认档（带 * 的那个）应有 1 个，"
                     f"实际 {len(star)}——不猜该拿哪个值")
        got[name] = star[0]
    missing = sorted({n for n in re.findall(r"@var\s+\w+\s+([\w-]+)", code) if n not in got})
    if missing:
        sys.exit(f"STRIP ERROR: 这些面板开关解析不出默认值，预览会跑成非默认配置：{missing}")
    return ":root{" + ";".join(f"--{k}:{v}" for k, v in got.items()) + "}"


defaults = panel_defaults(src, code)
OUT.parent.mkdir(exist_ok=True)
OUT.write_text(defaults + "\n\n" + body, encoding="utf-8")
print(f"面板默认  注入 {len(defaults.split(';'))} 项出厂值（含 --kEmoji），夹具跑的即用户拿到的那套")
print(f"已剥壳：{SRC.name} {len(lines)} 行 → {OUT.relative_to(ROOT)} "
      f"{len((defaults + chr(10) + body).splitlines())} 行，"
      f"花括号 {body.count('{') + 1}/{body.count('}') + 1} 平衡")
