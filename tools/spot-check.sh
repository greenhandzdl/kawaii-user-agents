#!/bin/bash
# 真站抽检：同一个页面拍"裸"和"上肤（白天/夜晚）"三张，然后量正文可读性。
#
# 为什么走本地反代而不是直接开真站：真站的 CSP 会在页面里拦住注入，
# devtools 手工注入既不稳定也没法进流水线。反代只监听 127.0.0.1，
# 抓 HTML 时顺手剥掉 CSP meta，把 preview/skin.css 当 <style> 塞进 </head> 前。
# 抽检对象是版式类别（长文、卡片流、参考文档），不是全站保证。
set -uo pipefail
cd "$(dirname "$0")/.."

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT=8748
BASE="http://127.0.0.1:$PORT/s/"
mkdir -p shots
# --only=tag[,tag…]：只重拍名单里这几站，其余站的 spot-* 原样留着。
# 为什么要这一格：原先开头无条件 rm -f shots/spot-*.png，一站定不下来就把六站的图一起清掉——
# 2026-10-06 那一跑有三档定不下来，普查只能按 4/6 站读，而"哪几站是这一跑新拍的"没人报得出。
# 单站复量也是配对重拍（改前／改后各一遍）要用的通道：换一截词根不该重付六站的账。
ONLY=""
for a in "$@"; do
  case "$a" in
    --only=*) ONLY="${a#--only=}" ;;
    *) echo "SPOT ERROR: 不认得参数 $a（可用 --only=tag[,tag]）"; exit 2 ;;
  esac
done
_want=()
if [ -n "$ONLY" ]; then
  IFS=',' read -r -a _want <<< "$ONLY"
  for t in "${_want[@]}"; do rm -f "shots/spot-$t-"*.png; done
  echo "只重拍：$ONLY（其余站的图是上一跑留下的，跨跑比较前先核被摄对象那一枚 sha）"
else
  rm -f shots/spot-*.png   # 清掉上一轮的：换了站点名单，glob 会把旧图算进"跨站重复"那道检查
fi
rm -f shots/tmp-*.png

python3 tools/strip.py >/dev/null || { echo "剥壳失败"; exit 1; }
pkill -f "tools/proxy.py" 2>/dev/null
nohup python3 tools/proxy.py "$PORT" >/tmp/ks-proxy.log 2>&1 &
PROXY=$!
trap 'kill "$PROXY" 2>/dev/null' EXIT
for i in {1..20}; do
  curl -sf -m 1 "http://127.0.0.1:$PORT/healthz" >/dev/null && break
  sleep 0.25
done
curl -sf -m 2 "http://127.0.0.1:$PORT/healthz" >/dev/null || {
  echo "反代没起来：/tmp/ks-proxy.log"; cat /tmp/ks-proxy.log; exit 1; }

# 每行：<标签>|<裸页 URL>。版式类别：入门长文（正文+代码块）、卡片流（图+短条目）、
# 参考文档（表格+代码+侧栏）。抽检对象是版式类别，不是这几个域名本身。
# 可达性是按"这一格能不能当比对对象"量的，不是随手试的：Bing 的 ?q= 直接被重定向回首页
# （裸页全白、上肤页只有搜索框），当不了对象。GitHub 早前那一跑是 blob 页整站超时，
# 所以卡片流那格当时换成了 css-tricks；今天复量首页与一个 repo 页都回 200
# （0.55s / 0.88s，117KB / 44KB），就把首页加成新的一格——css-tricks 那格不动，
# 两格是两种版面，不互相替代。
# css-tricks 出两格：首页自称深色（它是 README 那条「撞上时切档」约束的活证据），
# 同站的文章页则是另一套底色——只留首页会把"整站"和"这一张版面"混为一谈。
# 文章格原先用的是讲 CSS random() 的那篇，换掉了：它自己的示例每次解析都重新摇一遍
# （正文里 66 处 random()），三张连拍给出三个大小 400911/405122/362098——
# 这种页面天生定不下来，加拍只是把墙钟烧光，按"该由人来换样本"那条办。
# 换成媒体查询指南：10 张表格（表格正是 README 里点名要保可读的那类容器），
# 且摘掉脚本之后三张连拍逐字节一致。
# 2026-09-29 再换两格（都是量出来的，不是嫌它们不好看）：
#  · css-tricks 首页：图片预热之后能定下来了，但它是卡片流，正文列凑不出 40 行——
#    量不到就不判，所以换成同站的参考目录页（almanac）：day 接管25行 7.08／night 19行 9.61，两张一致。
#  · GitHub 首页：2026-09-29 记的是"裸页六张连拍没有相邻一致，差的 11 个像素在注册框圆角与页眉，
#    预热救不了"——2026-10-01 按这条链路的原样（同一个 proxy、同样的窗口与 --timeout、出图前
#    csslist/imglist 各点一遍）重测不复现：bare/day/night/sentinel 四档连拍六张，相邻逐字节一致
#    的对数分别是 3/3/5/3（夜晚档六张两两相同）。抖的那些坐标固定在 x[1093,1162] y[22,51]，
#    六张之间最大差 3/765（R+G+B 之和，单通道 1 个色阶）且 A→B→A 翻回原位——是页眉一小块的
#    亚像素栅格化，不是页面还在画。正文列凑得出行：裸页 44／白天 43／夜晚 45（MIN_ROWS=40），
#    所以这一格按"能不能量到"放回名单。
#    当初并进来的那句"任何一档都必然判红"说的是 docs.github 那格（站点自己的墨纸坐在 4.51，
#    而 §3 那面膜实测要收 0.42：同档关膜重拍 4.51→4.09；自家紫底同样一档 7.58→6.81），
#    首页白天档自家底的中位是 9.92（43 行里 19 行判自家），不在那条上。
#    膜这笔代价按"谁涂的底"分开记账的尺子已经落地：?sentinel 把整套颜色 token 扳成纯绿重拍，
#    同一坐标动了＝我们画的（见 legibility.py 的 ownership）。
# 2026-10-02 首页这一格换出去（同上：量出来的，不是嫌它不好看）：
#  · 整跑两次都在**白天哨兵档**红（/tmp/ks-sp-recheck.log:105、/tmp/ks-sp-full2.log:84），
#    六张给的是 372024／189934／372025／372024／376207／372024——多数态出现三次但不相邻，
#    五个相邻对全不达标；两跑之间根文档 sha 从 b27119f95620 换成 761c2baa5d7a（题目自己换过）。
#  · 单站副本三连跑（同一 proxy、同样的窗口与 --timeout、warm 各点一遍）3/3 全 rc=0，
#    判定逐字复现 day=9.92(自家 19 行)／night=9.90(自家 26 行)；其中一次白天哨兵档
#    拍到第 6 张才与第 5 张一致——也就是说这一格对上取样窗口的余量是 0，整跑必然撞空。
#  · 替进来的是同一版式类别（营销首页：hero＋卡片流）的 https://github.com/features：
#    同一条链路五档全定、样式表 27/27、图片 8/8，bare=14.20／day=9.17(自家 39 行)／
#    night=9.73(自家 42 行)、动过 16%。判据（相邻两张逐字节一致）一个字没改，
#    改的是"这一格能不能当比对对象"——按上面那枚 0 余量办，不是靠加拍糊过去。
#  · 另一个候选 github.com/microsoft/vscode 当场否掉：0 档定下来、图片 2/3，仓库页天生画不完。
#  · 换出去的是**可读性闸门**这一侧；首页在玻璃侧的读数不因此作废（六站·昼夜那张普查里
#    github-home 那一列是 2026-10-02 现量的，7 块玻璃／0 块浮面穿上玻璃，记在项目记忆里）。
SITES="
runoob|https://www.runoob.com/html/html-tutorial.html
csstricks-article|https://css-tricks.com/a-complete-guide-to-css-media-queries/
mdn|https://developer.mozilla.org/zh-CN/docs/Web/CSS
github-docs|https://docs.github.com/en/get-started
github-features|https://github.com/features
w3schools|https://www.w3schools.com/css/
"
TAGS=$(while IFS='|' read -r t u; do [ -n "${t:-}" ] && printf '%s ' "$t"; done <<< "$SITES")
NSITES=$(grep -c '|' <<< "$SITES")

grab() { # grab <url> <out.png>
  rm -f "shots/$2"
  # 不再带 --virtual-time-budget：虚拟时钟遇到吊着的第三方请求就不往前走。
  # 实测同一个代理 URL：带虚拟时钟那一跑 70s 没吐出文件（上一轮加的 --timeout=45000
  # 也没拦住它——那条"墙钟上限"的注释是错的，这里按量到的事实改写），
  # 去掉它、只留 --timeout=20000 则 4s 出图。皮肤是内联 <style>，不吃虚拟时钟。
  # 外面还要再套一道墙钟杀手：--timeout 到底兜不兜得住没被这次测量证明
  # （4s 那跑本来就远没到 20s），不能把"不卡死"押在一个没验证的开关上。
  "$CHROME" --headless=new --disable-gpu --no-sandbox \
    --window-size=1280,1500 --timeout=20000 --hide-scrollbars \
    --allow-file-access-from-files --screenshot="shots/$2" "$1" >/dev/null 2>&1 &
  local pid=$! rc t0
  # 看门狗用轮询，不用"睡满 75 秒再被杀掉"：给那个子壳发信号时 SIGTERM 会挂到它的 sleep
  # 结束才执行，日志里因此每次出图都多一行 "Terminated: 15"（上一跑 27 行，混在"定下来"
  # 旁边看着像失败）。轮询版一个信号都不发：chrome 一退它半秒内自己收工，
  # 只有真的满 75 秒还活着才动手。
  t0=$(date +%s)
  ( while kill -0 "$pid" 2>/dev/null; do
      if [ "$(( $(date +%s) - t0 ))" -ge 75 ]; then kill -TERM "$pid" 2>/dev/null; break; fi
      sleep 0.5
    done ) &
  local killer=$!
  wait "$pid"; rc=$?
  wait "$killer" 2>/dev/null
  [ -s "shots/$2" ] || {
    # css-tricks 实测会间歇性"退出码 0 但没落盘"（同一 URL 上一跑 1.0MB、下一跑没文件）。
    # 只重试一次、且用环境变量钉住深度：整站从比对里悄悄消失是最坏的结果，
    # 而重试两次以上只会把一跑的墙钟翻倍。
    if [ -z "${KS_GRAB_RETRY:-}" ]; then
      echo "  （第一次没出图，重试一次：$1）"
      KS_GRAB_RETRY=1 grab "$1" "$2" && return 0
    fi
    echo "  （出图失败 rc=${rc}，$1）"; return 1
  }
  echo "  $2  $(wc -c < "shots/$2") bytes"
}

# warm <页 URL> <css|img>：出图之前先把这一页的外链（样式表 / 图片）逐条拖进本机缓存，并点齐。
# 为什么这是道闸门而不是优化：上游等待上限 10 秒 + 失败进 60 秒负缓存之后，
# 一张慢的主样式表会被判死，整页塌成无样式——而实测无样式那一态自己也是可复现的
# （css-tricks grid 指南在 497154 有样式 / 193271 无样式之间来回，两边都能连拍相同）。
# "连拍两张逐字节一致"拦不住它，只有出图之前把样式表逐条点一遍拦得住。
# 样式表那一支缺一张就红：三档是从同一条链路取的，缺了就是拿一张被扒了 CSS 的页面做比对对象。
# 但"缺"要分开算：502＝站点答了、答的是 404/403（它自己的外链本来就是坏的）；
# 504＝这一跳没走到头，还要再切一刀——绕开代理直连真站也拿不到 200 的，是"这台机器到不了它"；
# 直连能拿到 200 的，才是"我的代理把外链弄丢了"。只有最后这一种红（图片那一支例外，见下）。
# 理由：三档走同一条链路，一起缺的东西不影响"上肤前后"的比对；而"这一页到底上没上样式"
# 仍然被点齐的那个数钉住（实测 css-tricks 两格的样式表各 20 张：18 张就位、2 张点名放行；
# 图片是另一次独立的点名，两支各印各的数，不合并成一个"齐了"）。
# 把站点自己的坏链算到皮肤头上，或者反过来把自己没取到说成"站点就这样"，都是假归因。
# 图片那一支（?imglist）是后加的，理由和样式表那支不同：不是"上了没上图"，而是
# **同一档连拍定不下来**。实测 css-tricks 首页 49 个 <img> 逐条请求里 24 次失败
# （按 src 去重后是 28 个里 8 个回 504），坏链每过期一次就要重新等满上游上限，
# 于是快门有时撞上图已画上、有时撞上破图占位——整页跟着重排，
# 裸页档六连拍给出四个大小（653189 / 343011 / 454176 / 653461）。
# 点齐之后同一档六连拍塌到三个状态、并出现相邻两张逐字节一致（653185 连中两次）。
# 两支共用同一段取清单/判缺的码，但**严重性刻意不同**：样式表少一张红，图片少一张只报。
# 差别住在调用方那两行里，各有一具刀钉着（W1 样式表判红、W4 图片只报不拦），
# 所以"共用一套归因"不等于"两支同生共死"——把图片也改成判红，W4 就会红给它看。
warm() { # warm <页 URL> <css|img>
  # 下面几条 echo 里的 ${var} 都刻意带花括号：紧跟变量名的中文标点会被算进名字本身
  # （`v=1; echo "$v，"` 在 bash 3.2 和 5.3 上都报 "v\ufffd: 未绑定的变量"，换 LANG 也没用），
  # 而 `set -u` 会让这一行直接死掉——偏偏它只在出问题时才执行。warm-controls.py 量到过。
  local list u ok=0 total=0 sitebad="" mybad="" code direct kind="${2:-css}" noun q
  case "$kind" in
    css) q=csslist; noun=样式表 ;;
    img) q=imglist; noun=图片 ;;
    *) echo "    warm：不认的清单种类「$kind」——新加一类要在这里点名，不能默认当样式表"; return 1 ;;
  esac
  list=$(curl -s -m 90 "${BASE}${1}?${q}") || { echo "    ${noun}清单没取到"; return 1; }
  while IFS= read -r u; do
    [ -n "$u" ] || continue
    total=$((total + 1))   # 清单条数：汇总行要印 N/M，光印 N 会把"缺了几张"藏进上一段
    u=${u//&amp;/&}   # 清单是 HTML 属性值：浏览器解析时会把 &amp; 还原成 &，curl 不会
    code=$(curl -s -m 60 -o /dev/null -w '%{http_code}' "$u")
    case "$code" in
      200) ok=$((ok + 1)) ;;
      502) sitebad="$sitebad
      $u" ;;
      *)   # 504 之类＝这一跳没走到头。再量一次"绕开我的代理直连真站"把它分开：
           # 直连也拿不到 200＝这台机器到不了它（实测 ajax.googleapis.com 那条：直连 30s 超时、
           # 0 字节，而它本身就是条写坏的链接 jqueryui//themes/），三档一样缺，点名放行；
           # 直连回 200＝我的代理把它弄丢了，这一格不能拿来比对。
           direct=$(curl -sL --compressed -m 25 -o /dev/null -w '%{http_code}' "${u#"$BASE"}")
           if [ "$direct" = "200" ]; then
             mybad="$mybad
      (回 ${code}，直连真站却回 200) $u"
           else
             sitebad="$sitebad
      (回 ${code}，直连真站同样回 ${direct}) $u"
           fi ;;
    esac
  done <<< "$list"
  if [ -n "$sitebad" ]; then
    echo "    站点自己的外链就是坏的（上游答了非 200，三档一样缺）：$sitebad"
  fi
  if [ -n "$mybad" ]; then
    if [ "$kind" = css ]; then
      echo "    FAIL ${noun} ${ok}/${total} 张就位，但这些本机这一跳没取到：$mybad"
      return 1
    fi
    # 图片这一支只报不拦。分档的理由不是"图不重要"，而是两支的失效方向不同：
    # 少一张样式表会改变"这一页是什么"（无样式那一态自己可复现，能伪装成 settled 的比对对象），
    # 而少一张图在三档里是同一张缺图——上肤前后比对两边差的仍然只有注入与否，
    # 可读性那一层量的又是正文行。这一支要的是"每一拍都从本机取，别再撞在等图的那一秒"，
    # 而那是"点齐"这个动作给的，和红不红无关。
    # 还有一层量到的不对称：把"我这跳失败"判红的探针本身不可信。实测 css-tricks 首页
    # 28 个不同 src 里 19 张 200、8 张回 504（都是 gravatar / i0.wp.com 的头像尺寸端点），
    # 而那 504 只花 0.003 秒＝反代的 60 秒负缓存在答，不是重新等满上游上限；
    # 直连那一探却每次都现走网络，同一张图连探三次给出 000 / 200 / 200。
    # 两边量的不是同一个东西，"我这跳 504 而直连 200"因此可以只是缓存时序，
    # 拿它当"这一格不能比对"的依据不够硬。（样式表那一支照旧判红：那里少一张是真塌版。）
    echo "    ${noun} ${ok}/${total} 张就位，另有这些这一跳没取到（三档一样缺，只报不拦）：$mybad"
  fi
  if [ "$kind" = img ] && [ "${ok:-0}" = "0" ]; then
    # 空清单单独说一句：这一页真没有 <img>（mdn 那一格现量：清单 0 行，页面里 <img> 一个没有、
    # 图标是 12 个内联 <svg>），还是我这支解析没认出来——两种情况都印在这里，不让它安静地像个绿。
    # 解析错不会静默过去：warm-controls.py 的 W5 钉的是"图片 1/2 张就位"，
    # img_list 认不出 src 时那里会印 0/0 而红。
    echo "    ${noun}清单是空的（这一页没有 <img>，或清单没解析出来——出图那层自己会抖）"
  fi
  # 汇总行只印 N/M，不写"全部就位"：站点自己的坏链在上面那一段已经点名过，
  # 这一格本来就不是"全部"（css-tricks 首页的 28 个 src 现量：19 张回 200、8 张回 504）。
  echo "    ${noun} ${ok}/${total} 张就位"
  return 0
}

# settle <url> <名>-<档>：同一档拍到"有两张逐字节一致"才算页面定下来，落盘成 spot-<...>.png。
# 为什么每档都要拍两遍而不只是参考档：比对的全部效力来自"三张图只差注入与否"，
# 而实测任何一档都可能撞上页面还没定下来（上一跑塌的就是参考档）。
# 一张会变脸的图撑不起"上肤前后"这种说法，所以这一层就把它挡下来。
# 上限六张。原先这里写的是"CDN 边缘要前几张才热起来"——那个猜测是错的。
# 按请求流水量到过的抖源有四个，最后一个才是主因：子资源没走反代（每张图重新跑一遍真站网络）、
# 死链每次都等满上游上限、页面自带的脚本在 load 之后继续往版画东西（strip.py 因此剥脚本），
# 以及反代按 HTTP/1.0 一问一答断线——Chrome 对同一主机只开 6 条 socket，
# 而 runoob 一页有 16 个子资源全搬进反代之后就同源，排在队尾的那几张图在快门落下时还没被请求过，
# 于是坏图占位。改成 HTTP/1.1 复用连接之后同一档连拍逐字节一致（见 proxy.py 里 protocol_version
# 那段）。
# 判据 2026-10-06 从"相邻两张一致"改成"六张里出现两次以上的同一枚"，改的是**相邻**这一条、
# 不是"两张一致"这一条：动机是现量的覆盖率——按相邻判据六站 12 档里三档定不下来
# （github-features 裸页、mdn 夜、w3schools 夜），而 w3schools 夜档那六张的字节数是
# 777727／777722／497769／777727…——第 1 张与第 4 张逐字节相同。也就是说页面确实回到了
# 同一个状态，只是中间被某个周期重绘的元素岔开了一次；按相邻判据这种"回得来"的页面和
# 真·自带随机数、永远回不来的页面读起来是同一个 FAIL，于是每次复量都有 2/6 站静默缺席。
# 取众数而不是取"任意一对"：出现两次以上才算复现，只出现一次的坏图（497769 那一枚）不当定档。
# 真定不下来的页面（六张里没有任何一枚重过）照旧 FAIL——那还是"该由人来换样本"那一格，
# 不是靠加拍糊过去。
settle() { # settle <url> <stem>
  local shots=() i best="" bestn=0 n=0
  for i in 1 2 3 4 5 6; do
    local f="tmp-$2-$i.png"
    grab "$1" "$f" || { rm -f shots/tmp-"$2"-*.png; return 1; }
    shots+=("$f")
    n=${#shots[@]}
    local c=$(md5 -q "shots/$f") hit=0
    for j in "${shots[@]}"; do
      [ "$(md5 -q "shots/$j")" = "$c" ] && hit=$((hit + 1))
    done
    if [ "$hit" -gt "$bestn" ]; then bestn=$hit; best="$f"; fi
    [ "$bestn" -ge 2 ] && break
  done
  if [ "$bestn" -lt 2 ]; then
    echo "    定不下来：$n 张里没有任何两张逐字节相同"
    rm -f shots/tmp-"$2"-*.png
    return 1
  fi
  echo "    定下来：$n 张里同一枚出现 $bestn 次（取那一枚落盘）"
  mv "shots/$best" "shots/spot-$2.png"
  rm -f shots/tmp-"$2"-*.png
  return 0
}

fails=0
echo "=== 真站抽检出图 ==="
while IFS='|' read -r tag url; do
  [ -n "${tag:-}" ] || continue
  # --only 那一支：名单外的站整段跳过（不预热、不拍、不判），否则它会拿上一跑的图冒充本轮
  if [ "${#_want[@]}" -gt 0 ]; then
    _hit=0
    for t in "${_want[@]}"; do [ "$t" = "$tag" ] && _hit=1; done
    [ "$_hit" = 1 ] || continue
  fi
  # --hide-scrollbars：各站写各的滚动条，把它排除掉才只比正文
  # 三档都走反代这一条链路，只差注入与否：裸页原先直连真站，于是比对两边隔着两条链路
  # （缓存、CSP、<base> 都只在一边），MDN 就是这么从"能比对"掉成"裸页 8.7KB 空白"的。
  warm "$url" css || { echo "  FAIL $tag 样式表没齐，这一格不比对"; fails=1; continue; }
  # 图片那一支的 rc 只有"清单没取到"会非 0（缺图只报不拦，理由在 warm() 里）。
  # 这一格照旧 continue：清单取不到＝反代或根文档已经不行，样式表那一支也一样会红。
  warm "$url" img || { echo "  FAIL $tag 图片清单没取到，这一格不比对"; fails=1; continue; }
  # 被摄对象指纹：这份名单的读数只有在上游给的是同一份根文档时，才谈得上跨跑比较。
  # 反代缓存 6 小时一到就重抓，实测 2026-10-01 两跑之间 mdn 与 docs.github 的根文档各换了
  # 一份，于是连"根本没注入皮肤"的裸页档也一起动了（mdn 7.76→18.10、docs.github 4.51→6.08）。
  # 那一笔不能记到修色头上，但当时的日志里没有任何东西说出这件事。这一行只登记、不改判定：
  # 跨跑比读数前先比这一枚，对不上就是换了题目，得现比重拍两遍（改前/改后各一遍）才作数。
  subj=$(curl -s -m 90 "${BASE}${url}?bare" | shasum -a 1 | cut -c1-12)
  echo "    被摄对象 ${tag}：根文档 sha=${subj}（跨跑比较前先核这一枚）"
  settle "${BASE}${url}?bare"  "$tag-bare"  || { echo "  FAIL $tag 裸页档定不下来（连拍六张，没有任何两张逐字节相同）"; fails=1; continue; }
  settle "${BASE}${url}"       "$tag-day"   || { echo "  FAIL $tag 白天档定不下来（连拍六张，没有任何两张逐字节相同）"; fails=1; continue; }
  settle "${BASE}${url}?night" "$tag-night" || { echo "  FAIL $tag 夜晚档定不下来（连拍六张，没有任何两张逐字节相同）"; fails=1; continue; }
  # 哨兵档：整套颜色 token 扳成纯绿（含 --ks-ink-*/--ks-link/--ks-head-ink，名单由 proxy.py
  # 按声明形状现推，并有 INK_TOKENS 那条守卫钉着），版式应当逐字不动。legibility.py 拿它做
  # "这块底是谁涂的"与"这行字是谁涂的"的二值归因（同一坐标动过＝我们画的），所以它和上肤档之间不能有第二种差别——
  # 判据和上肤档同一支（连续两张逐字节一致），因为一张会抖的哨兵图会把站家的行算到我们头上。
  # 裸页档没有皮肤可扳，所以只有两档出哨兵图。
  settle "${BASE}${url}?sentinel"       "$tag-day-sent"   || { echo "  FAIL $tag 白天哨兵档定不下来（连拍六张，没有任何两张逐字节相同）"; fails=1; continue; }
  settle "${BASE}${url}?night&sentinel" "$tag-night-sent" || { echo "  FAIL $tag 夜晚哨兵档定不下来（连拍六张，没有任何两张逐字节相同）"; fails=1; continue; }
done <<< "$SITES"

echo "=== 抽检图自身的两道检查 ==="
# 1) 跨站裸页图一模一样＝上游只拿到反爬壳子，页面是空的（这种图照样能出，所以必须显式拦）
dup=$(md5 -q shots/spot-*-bare.png 2>/dev/null | sort | uniq -d)
if [ -n "$dup" ]; then
  echo "  FAIL 裸页截图跨站重复（${dup}）：上游被挡，不是版式问题"; fails=1
else
  echo "  OK  ${NSITES} 站裸页图各不相同$( [ -n "$ONLY" ] && echo "（本轮只重拍 $ONLY，其余是上一跑的图，这一道按整目录读）" )"
fi
# 2) 上肤图和裸页图逐字节相同＝<style> 根本没进页面，注入被静默丢掉
for tag in $TAGS; do
  if [ -s "shots/spot-$tag-bare.png" ] && cmp -s "shots/spot-$tag-bare.png" "shots/spot-$tag-day.png"; then
    echo "  FAIL ${tag}：白天档与裸页逐字节相同，皮肤没生效"; fails=1
  fi
done

echo "=== 风格统一（孤立粉带）==="
# 这一本问的是「上肤以后有没有哪一块粉是孤零零立在别家的底中间」——判据、两条盲区与
# 两头都试过的色值都写在 tools/check-harmony.py 抬头，这里不复述（复述迟早和实现分家）。
# 它有没有牙是现量的：把分支声明加回 §4c 面块（＝电池里 K32 那一刀的现场形状）之后重出
# github-features 白天档，同一张链路读出 y=56–104 一段 99% 的孤立粉带并判红（rc=1）；
# 出厂文件下六站各 0 段。2026-10-05 量的这两趟都记在 check-harmony.py 那一段里。
# selftest 走在图之前：它不开浏览器、只喂四格手工定的色带（两正两负），量的是这把尺子自己
# 还认不认得"孤立的一段粉"——尺子坏了而这一跑六站恰好都没有孤立带，是两个不同的坏消息，
# 少了这一格就只能报"没红"，报不出"没坏"。
python3 tools/check-harmony.py --selftest || fails=1
python3 tools/check-harmony.py || fails=1

echo "=== 正文可读性估算 ==="
# 名单交给 legibility.py：报告要点得出"这一格量的是哪个 URL"，两处各抄一份迟早会分家
export KS_SITES="$SITES"
python3 tools/legibility.py || fails=1
exit "$fails"
