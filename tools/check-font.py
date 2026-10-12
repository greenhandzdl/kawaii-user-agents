#!/usr/bin/env python3
"""计算样式闸门：用 headless Chrome 的 --dump-dom 读夹具里那段探针写下的结果。

判的是"层叠关系对不对"，两个方向都要成立：
- 该抢的抢到手：皮肤的字体栈压住站点自己的 Georgia，code/pre 的等宽没被扳圆；
- 该让的让到底：站点自己排过边框的表格、写过底色的字段必须原样赢回去
  （兜底那节刻意不加 !important，就是靠这条才成立）。
这几条换机器也成立；而"本机到底有没有圆体"取决于装了什么字体，所以只报数不判定。
"""
import html
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PAGE = ROOT / "preview" / "components.html"
CSS = ROOT / "kawaii-skin.user.css"

fails = []


def die(msg):
    print(f"FONT FAIL: {msg}")
    sys.exit(1)


if not Path(CHROME).exists():
    die(f"找不到 Chrome：{CHROME}")

dump = subprocess.run(
    [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
     "--virtual-time-budget=6000", "--allow-file-access-from-files",
     "--dump-dom", f"file://{PAGE}"],
    capture_output=True, text=True,
)
if dump.returncode != 0:
    die(f"dump-dom 退出码 {dump.returncode}：{dump.stderr.strip()[:200]}")

m = re.search(r'<output id="font-probe"[^>]*>(.*?)</output>', dump.stdout, re.S)
if not m:
    die("DOM 里没有 font-probe 的结果——探针没跑起来（或 --dump-dom 早于脚本执行）")
try:
    res = json.loads(html.unescape(m.group(1)))
except json.JSONDecodeError as e:
    die(f"探针输出不是合法 JSON：{e}；原文 {m.group(1)[:120]!r}")

css_stack = re.search(r"--ks-stack\s*:\s*([^;]+);", CSS.read_text(encoding="utf-8"))
if not css_stack:
    die("CSS 里没找到 --ks-stack")
want = [f.strip().strip("\"'") for f in css_stack.group(1).split(",")]
got = [f.strip().strip("\"'") for f in res["bodyStack"].split(",")]

print(f"实际生效栈  {got[:3]}…（CSS 期望 {want[:3]}…）")
if got != want:
    fails.append(f"生效的字体栈和 CSS 写的不是同一个：{got} vs {want}")
if res["siteFontLeakedThrough"]:
    fails.append("站点自己的 Georgia 漏了进来——html/body 的 !important 没压住")
if not res["codeKeepsMono"] or not res["preKeepsMono"]:
    fails.append("code/pre 被圆体扳走了，语法高亮那套等宽承诺不成立")
if not res["inputUntouched"]:
    fails.append(f"input 的字体被抢了（现为 {res['inputStack'][:40]}）——编辑器类控件不该动")
if not res["sentinelIsNoop"]:
    fails.append("哨兵 NOT-A-REAL-ZZZ 也改变了字宽，这套测量本身不可信")

# 层叠的另一头：兜底样式必须是"站点排过就让路"，谁给 4b 那节补 !important 就在这里红
for key, why in (
    ("siteTableKeepsOwnBorder", "站点自己画的 3px 虚线表格边框被我们盖掉了"),
    ("siteFieldKeepsOwnBg", "站点自己写的输入框底色被我们的底衬顶掉了"),
    ("bareTableGotOurRule", f"裸表格没拿到兜底边框（实测 {res['bareTableDetail']}）"),
    ("bareFieldGotOurBg", "裸输入框没拿到兜底底色，等于这节没生效"),
):
    if not res[key]:
        fails.append(why)

print(f"层叠让路    站点表格/字段守住自己的样式：{res['siteTableKeepsOwnBorder']}"
      f"/{res['siteFieldKeepsOwnBg']}；裸表格边框 {res['bareTableDetail']}，"
      f"站点字段边框 {res['ownFieldBorder']}")

print(f"本机圆体    首个家庭是否真的参与排版：{res['firstMatters']}"
      f"（取决于装机字体，只报数不判定）")

if fails:
    print("\nFONT FAIL")
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("\nFONT PASS：该抢的抢到手（站点字体被压住、等宽与表单字体没被牵连），"
      "该让的让到底（站点排过的表格边框与字段底色原样赢回）")
