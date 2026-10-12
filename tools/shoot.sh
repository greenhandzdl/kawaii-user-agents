#!/bin/bash
# 出图取证。
#
# 为什么不用 --force-prefers-color-scheme：实测 Chrome 154 的 headless=new 不认它
# （light/dark/bogus 三种取值下 matchMedia 一律返回 LIGHT），拿它出图等于只出白天档。
# 这里改成注入面板变量 --kScheme，等价于在 Stylus 面板里选"粉紫（强制夜晚）"，
# 它会翻 color-scheme 从而翻所有 light-dark()。"跟随系统"那条路由 CDP 仿真单独验。
set -euo pipefail
cd "$(dirname "$0")/.."

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
[ -x "$CHROME" ] || { echo "找不到 Chrome：$CHROME"; exit 1; }

python3 tools/strip.py
# 变异电池要问的是"像素这一本会不会红"。前面两道计算样式闸门排在前头，一刀割在
# 共用的那条声明上就先把整条流水线拦下——出图根本没跑，报出来的名字全是计算样式的，
# 归因不到像素那本上。SKIP_PRE=1 时跳过这两道，出图与像素/字体判定照旧。
if [ -z "${SKIP_PRE:-}" ]; then
  echo "=== 对比度闸门：色值只住在 CSS 里，这里解析出来实算 ==="
  python3 tools/check-contrast.py | tail -1
  echo "=== 控件闸门：逐个控件问它到底算出了什么样式 ==="
  python3 tools/check-controls.py
fi
mkdir -p preview/.build shots

build() { # build <out.html> <in.html> <注入的 CSS> [插在 </body> 前的 HTML]
  python3 - "$2" "$1" "$3" "${4:-}" <<'PY'
import sys
src, out, css, extra = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
html = open(src, encoding="utf-8").read()
anchor = '<link rel="stylesheet" href="skin.css">'
assert html.count(anchor) == 1, f"{src} 里的锚点不是恰好 1 处"
if extra:
    assert html.count("</body>") == 1, f"{src} 里的 </body> 不是恰好 1 处"
    html = html.replace("</body>", extra + "\n</body>")
# 变体页落在 preview/.build/ 下，相对路径必须往回一级，否则 skin.css 直接 404，
# 出来的就是一张裸页（曾经采到纯白/站点原色就是这样露馅的）
fixed = '<link rel="stylesheet" href="../skin.css">'
inject = fixed + f'\n<style>/* 模拟 Stylus 面板 */ {css}</style>'
open(out, "w", encoding="utf-8").write(html.replace(anchor, inject))
PY
  grep -q '../skin.css' "$1" && grep -q '模拟 Stylus 面板' "$1" || { echo "注入失败：$1"; exit 1; }
}

# 白天那几张必须显式钉住 --kScheme:light。皮肤默认值是 light dark（跟随系统），
# 而 headless Chrome 的 prefers-color-scheme 跟着 macOS 外观走：实测同一张
# preview/components.html 在 18:03 出图是粉白 (255,235,244)、18:40 再出就变成
# 粉紫 (38,25,56)——日落前后系统自动切了深色。不钉住的话，"白天档"这张图
# 到底是不是白天，取决于几点跑脚本。
#
# 出厂默认值（含 --kEmoji 那朵花）现在由 strip.py 注进 preview/skin.css，
# 所以这里只写"和默认不同"的那几项。以前 NIGHT 里硬写过 --kEmoji:"🌸 "，
# 结果是白天档没花、夜晚档有花——两档差的不是明暗一个变量。
DAY=':root{--kScheme:light;}'
NIGHT=':root{--kScheme:dark;}'
PAINT=':root{--kPaint:1;--kScheme:light;}'
HALOOFF=':root{--kHalo:0;--kScheme:light;}'
# 撞色/光晕那几对（03/06、07/08）必须显式关掉标题前缀：🌸 的花瓣是粉叠在白底上，
# 缝隙里每个像素都离笔画 1–2px，会把"贴边中位"整个顶成花瓣色——实测关档读出
# (244,186,227)、对底分离 1.5×，等于在没垫任何东西的页面上量出"垫过了"。
# 默认值进了 skin.css 之后，"不要花"从"不写"变成了"必须写 none"。
NOFLOWER='--kEmoji:none;'
DARKDAY=":root{${NOFLOWER}--kScheme:light;}"
DARKPAINT=":root{--kPaint:1;${NOFLOWER}--kScheme:light;}"
DARKHALOOFF=":root{--kHalo:0;${NOFLOWER}--kScheme:light;}"
NIGHTPLAIN=":root{${NOFLOWER}--kScheme:dark;}"
NIGHTHALOOFF=":root{--kHalo:0;${NOFLOWER}--kScheme:dark;}"
# 浮层玻璃那一对（15/16）：和 13/14 出自同一份夹具，只差 --kGlass:0 这一个变量。
# 开关在 CSS 里同时调制透明度与虚焦半径，所以"关掉"是原地降级成实心面，
# 不需要第二条规则——也正好让像素这一本能拿"透与不透"做配对测量。
GLASS_OFF_DAY=':root{--kGlass:0;--kScheme:light;}'
GLASS_OFF_NIGHT=':root{--kGlass:0;--kScheme:dark;}'

build preview/.build/components-day.html      preview/components.html "$DAY"
build preview/.build/components-night.html    preview/components.html "$NIGHT"
build preview/.build/darksite-day.html        preview/dark-site.html  "$DARKDAY"
build preview/.build/darksite-paint.html      preview/dark-site.html  "$DARKPAINT"
build preview/.build/components-paint.html    preview/components.html "$PAINT"
build preview/.build/darksite-nohalo.html     preview/dark-site.html  "$DARKHALOOFF"
build preview/.build/lightsite-night.html     preview/light-site.html "$NIGHTPLAIN"
build preview/.build/lightsite-nohalo.html    preview/light-site.html "$NIGHTHALOOFF"
# 负控制也要成对：自家粉白/粉紫底上光晕应当完全隐形，所以 01/02 各配一张只差
# --kHalo:0 的同页对照。拿"开档 vs 站点底"当负控制量不出"隐形"这件事。
build preview/.build/components-nohalo.html      preview/components.html "$HALOOFF"
build preview/.build/components-night-nohalo.html preview/components.html "$NIGHTHALOOFF"
build preview/.build/components-glass-off-day.html    preview/components.html "$GLASS_OFF_DAY"
build preview/.build/components-glass-off-night.html  preview/components.html "$GLASS_OFF_NIGHT"

# 模态遮罩那一对。为什么单独出：夹具里的 <dialog open> 是**非模态**的，
# 非模态压根不画 ::backdrop，所以前面十张图里没有任何一格能回答"遮罩画没画出来"——
# 原先这条只有 check-controls.py 的计算样式断言（α=0.55），像素上从没证过。
# 两张图出自同一份构建、同一个 $DAY，只差末尾那段脚本。
# removeAttribute("open") 不能省：showModal() 对已经 open 的 dialog 抛
# InvalidStateError，抛完页面照旧、出图照旧——第一版探针就是这么"两张图一模一样"的。
MODAL='<script>var d=document.querySelector("dialog");d.removeAttribute("open");d.showModal();</script>'
build preview/.build/components-modal.html    preview/components.html "$DAY" "$MODAL"
build preview/.build/components-nomodal.html  preview/components.html "$DAY"
if ! grep -q 'showModal' preview/.build/components-modal.html; then
  echo "模态变体没落位：这一对量不到遮罩"; exit 1; fi
if grep -q 'showModal' preview/.build/components-nomodal.html; then
  echo "负控制变体里混进了 showModal：这一对不再是只差一个变量"; exit 1; fi

shoot() { # shoot <file> <out.png> [窗口高，默认 1500]
  local winh="${3:-1280,1500}"
  rm -f "shots/$2"   # 先删旧图，否则上一轮留下的文件会让失败这次看起来成功
  for try in 1 2; do
    "$CHROME" --headless=new --disable-gpu --no-sandbox \
      --window-size="$winh" --virtual-time-budget=6000 \
      --allow-file-access-from-files \
      --screenshot="shots/$2" "file://$PWD/$1" >/dev/null 2>&1 && break
    echo "  第 $try 次出图失败，重试：$2"
  done
  [ -s "shots/$2" ] || { echo "出图失败（空文件）：shots/$2"; exit 1; }
  echo "  $2  $(wc -c < "shots/$2") bytes"
}

# 页尾那三块（卡片与图 / dialog / 页脚）以前从没进过任何像素闸门：出图窗口写死
# 1280×1500，而这份夹具的内容长到 y≈1972。先量一次真实内容高，再按它出一对整页图，
# 页尾那格由 diff-shots.py 逐块判"翻没翻档、字读不读得动"。
# 01/02 仍留 1500 高：窗口一旦不短于内容，文档滚动条就不画了，滚动条那一格会失去取证对象。
#
# 坐标为什么要量两趟：窗口 1500 高时文档带滚动条（内容宽 1265），整页窗口里没有滚动条
# （内容宽 1280），同一份夹具两趟的落点差出一整个滚动条宽。上一轮手工量斑马纹就是把
# 带子取错了 140px，差点把"画出来了"报成"没画"——所以短窗口那格归短窗口那趟。
SEL='["table:not(.own)","table:not(.own) tbody tr:nth-child(1)","table:not(.own) tbody tr:nth-child(2)","table:not(.own) tbody tr:nth-child(3)",".cards","dialog","footer",".site-doc",".site-menu",".site-code",".site-toast",".gh-ground",".gh-a",".gh-b",".gh-c",".gh-d",".gh-e",".gh-f",".gh-g",".ch-ground",".ch-a",".ch-b",".ch-c",".ch-d",".ch-e",".ch-f",".ch-g"]'
# 拼一条而不是三段：bash 里 'a' 'b' 是两个词，第二词会被当成命令（第一版就是这么挂的）。
GEOM='<script>var o=document.getElementById("font-probe");o.hidden=false;'
GEOM+='function R(s){var e=document.querySelector(s);if(!e)return "MISS:"+s;'
GEOM+='var b=e.getBoundingClientRect();'
GEOM+='return s+"@"+Math.round(b.x)+","+Math.round(b.y+scrollY)+","+Math.round(b.width)+","+Math.round(b.height);}'
GEOM+="o.textContent=\"GEOM \"+document.documentElement.scrollHeight+\" \"+$SEL.map(R).join(\";\");"
GEOM+='</script>'
build preview/.build/probe-geometry.html preview/components.html "$DAY" "$GEOM"
if ! grep -q 'GEOM ' preview/.build/probe-geometry.html; then
  echo "几何探针没落位：这一跑取不到坐标"; exit 1; fi

: > preview/.build/geometry.txt
geom() { # geom <变体页> <窗口尺寸> → 打印该窗口下的文档内容高，并追加一行几何读数
  local line
  line=$("$CHROME" --headless=new --disable-gpu --no-sandbox --window-size="$2" \
         --virtual-time-budget=6000 --allow-file-access-from-files --dump-dom \
         "file://$PWD/$1" 2>/dev/null | grep -o 'GEOM [^<]*' | head -1 || true)
  [ -n "$line" ] || { echo "几何探针在窗口 $2 下没回话（脚本没跑起来？）"; exit 1; }
  case "$line" in *MISS*) echo "几何探针取不到选择器：$line"; exit 1;; esac
  printf 'win=%s %s\n' "$2" "$line" >> preview/.build/geometry.txt
  printf '%s\n' "$line" | awk '{print $2}'
}
DOC_H=$(geom preview/.build/probe-geometry.html 1280,1500)
case "$DOC_H" in ''|*[!0-9]*) echo "内容高不是个数：$DOC_H"; exit 1;; esac
FULL_WIN="1280,$((DOC_H + 24))"
geom preview/.build/probe-geometry.html "$FULL_WIN" >/dev/null
echo "夹具内容高 ${DOC_H}px → 整页图窗口 ${FULL_WIN}"
[ "$DOC_H" -gt 1500 ] || echo "  注意：夹具已不超 1500，页尾那一格将量不到东西"

echo "=== 出图 ==="
shoot preview/.build/components-day.html      01-components-day.png
shoot preview/.build/components-night.html    02-components-night.png
shoot preview/.build/darksite-day.html        03-darksite-day.png
shoot preview/.build/darksite-paint.html    04-darksite-paint-on.png
shoot preview/.build/components-paint.html  05-components-paint-on.png
shoot preview/.build/darksite-nohalo.html   06-darksite-halo-off.png
shoot preview/.build/lightsite-night.html   07-lightsite-night.png
shoot preview/.build/lightsite-nohalo.html  08-lightsite-halo-off.png
shoot preview/.build/components-nohalo.html      09-components-halo-off-day.png
shoot preview/.build/components-night-nohalo.html 10-components-halo-off-night.png
shoot preview/.build/components-modal.html       11-components-modal.png
shoot preview/.build/components-nomodal.html     12-components-nomodal.png
shoot preview/.build/components-day.html         13-components-full-day.png    "$FULL_WIN"
shoot preview/.build/components-night.html       14-components-full-night.png  "$FULL_WIN"
shoot preview/.build/components-glass-off-day.html   15-components-glass-off-day.png   "$FULL_WIN"
shoot preview/.build/components-glass-off-night.html 16-components-glass-off-night.png "$FULL_WIN"

# 滚动条不再单独出一张：headless 一律按经典滚动条画（--enable/--disable-features=
# OverlayScrollbar 两种取值出的图一模一样），所以 01 这张右缘就带着滚动条，直接采它。
# 真机上覆盖式滚动条不画样式滚动条，这条限制写进 README，不在此假称已验证。

echo "=== 像素断言：明暗两档必须真的画出了不同的图 ==="
python3 tools/diff-shots.py

echo "=== 字体断言：皮肤的栈压住站点字体，等宽和表单控件不被牵连 ==="
python3 tools/check-font.py
