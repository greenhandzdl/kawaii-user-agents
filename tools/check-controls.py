#!/usr/bin/env python3
"""控件计算样式闸门：逐个问"这个控件到底拿到了什么"，而不是从截图上猜。

为什么要有这一本：像素闸门看的是"图变了没有"，字体闸门看的是"层叠方向对不对"，
两者都拦不住"按钮带着 UA 的 2px 黑描边"和"粉底漏给全站每个复选框"——
前者是缺一行声明，后者是多一类选择器，两张图上都只是"有点粉/有点深"。
实测这两处都是先在这里红出来的。

后来补的第二批尺子是"线和面"那一类：表格边框、竖分隔线、斑马纹、表头、表题、图例、
折角标记、横线、高亮、引用面、选中色、聚焦环、遮罩。它们各有 CSS、一把尺子都没有，
而像素闸门天生量不到：它取一块区域的中位色，1px 的分隔线、::marker 那个三角、
没人拿鼠标去划的 ::selection、要键盘才亮的聚焦环，都够不着把中位数顶过去。

色值仍然只住在 CSS 里：期望值从 token 和 color-mix 的比例现推，脚本不抄 hex、也不抄百分比。
"""
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BUILD = ROOT / "preview" / ".build" / "probe-controls.html"
CSS = ROOT / "kawaii-skin.user.css"

# readonly 属性在 HTML 规范里只对下面这些类型有意义
TEXT_TYPES = ["text", "search", "url", "tel", "email", "password", "number",
              "date", "month", "week", "time", "datetime-local"]
# 其余类型 Chrome 一律算作 :read-only —— 所以兜底必须逐个排除，
# 写 input:read-only 就等于给这一整列刷上"只读"粉底
EXCLUDED_TYPES = ["range", "color", "checkbox", "radio", "file",
                  "button", "submit", "reset", "image", "hidden"]

BOX_CONTROLS = {
    "button": "button",
    "input-submit": 'input[type="submit"]',
    "input-reset": 'input[type="reset"]',
    "input-text": 'input[type="text"]',
    "input-date": 'input[type="date"]',
    "select": "select",
    "textarea": "textarea",
    "file": 'input[type="file"]',
}
ACCENTED = {
    "checkbox": 'input[type="checkbox"]',
    "radio": 'input[type="radio"]',
    "range": 'input[type="range"]',
    "progress": "progress",
    "meter": "meter",
}
DISABLEABLE = {
    "button": "button:disabled",
    "input": 'input[type="text"]:disabled',
    "select": "select:disabled",
    "textarea": "textarea:disabled",
}

# 表格线、图例、表题、折角、横线、高亮、引用、选中、聚焦环这一类：以前只有 CSS、
# 一把尺子都没有。像素闸门看得见"图变了没"，看不见"表题到底拿到 ink-3 没有"，
# 所以这里逐条把声明解出来再问计算样式。
STYLE_PROBE = {
    "table": ("table", None),
    "caption": ("caption", None),
    "td": ("tbody td:nth-child(1)", None),
    "sep": ("tbody td:nth-child(2)", None),
    "thead_th": ("thead th", None),
    "zebra_even": ("tbody tr:nth-child(2)", None),
    "zebra_odd": ("tbody tr:nth-child(1)", None),
    "quote": ("blockquote", None),
    "hr": ("hr", None),
    "mark": ("mark", None),
    "legend": ("legend", None),
    "marker": ("summary", "::marker"),
    "summary": ("summary", None),
    "selection": ("#selp", "::selection"),
    "fieldset": ("fieldset", None),
    "dialog": ("dialog", None),
    "glass_child": ("dialog .it", None),
    # class 形遮罩：真站（GitHub/Primer 那类）上遮罩不是 ::backdrop 而是一个 div，
    # 类名这枚是 2026-10-03 在真页上量到的原文，它排在面板外面、不在 dialog 子树里
    "csb": ("div.prc-Dialog-Backdrop-5Nt2U", None),
    # #77 的 B 档：遮罩词根是 mask 而不是 backdrop 的那两形，类名同样是真站原文
    # （Vue 套件 .vui_dialog--mask、京东 .jd_pc_dou_popup_mask）。
    "csc": ("div.vui_dialog--mask", None),
    "csd": ("div.jd_pc_dou_popup_mask", None),
    # 反面三枚：裸词根不该被当遮罩压暗。GitHub 的 .Overlay 是面板本体、
    # 京东的 .wechat_overlay 是 α0.4 的白底，裸 mask 那一枚钉的是"只有一截词根时不收"。
    "csn_overlay": ("div.Overlay", None),
    "csn_wechat": ("div.wechat_overlay", None),
    "csn_mask": ("div.sketch-mask", None),
    # 站点把按钮底写成作者 !important 的那颗白钮（2026-10-03 用户指的那一格）：
    # 它是链接形——§4b 的形状那条本来就给到了它，面却留白，形状是我们的、底色是人家的
    "linkbtn": ("a.ksWhiteBtn", None),
    # GitHub 文档页那一形唯一的正面证人：墨排在**孙节点**的类名上，取的是真正上色的
    # 那个属性（tf = -webkit-text-fill-color），不是 color——站点那条只写 color，
    # 拿 color 读数会永远"对"，这一格就成了一句空话。
    "primer_label": ("a.ksPrimerBtn span span", None),
    # 常驻条里的那枚控件（2026-10-04）：真站类名逐字取自 github.com/features 页头
    # 量到的 .NavDropdown-module__button__PEHWX，它坐在 navbar 词根命中的壳里，
    # 站点给它排了实心蓝底白字。这一枚是"条上的控件让面、上墨"那一条唯一的正面证人。
    "chrome_bar_btn": ("button.ksChromeBarButton", None),
    "chrome_bar_out_btn": ("button.ksBarOutside", None),
    # 常驻条那一支（裸链接那一形）的正面证人：坐在这条里的 <a href> 必须拿到自家墨。
    # 族的后代那一形只列 div/span/li/… 不含 a，§4 那条全局 a{} 排的是 --ks-link，
    # 所以这一格删掉 a[href] 那一支时红的只有这一行。
    "chrome_bar_link": ("a.ksChromeBarLink", None),
    # 同一条的反面：一枚不在任何条下的正文链接，站点自己排了绿字带 !important。
    # 这一支的选择器把词根抄了第二遍，族开头那道 :not(body, html) 管不到它；
    # 而夹具的 <body> 挂着 header-dark（真站原文），漏掉那道排除时「常驻条之下」
    # 就是「整页之下」——这一枚会跟着被上墨，绿字读不到。
    "body_link": ("a.ksBodyLink", None),
    # 第九格那两个只靠语义属性当钩子的面板：族里新加的 [aria-modal="true"] 与
    # [role="alertdialog"] 唯一的用武之地就在这里，探针必须点着它们自己
    "am_panel": ('[aria-modal="true"]', None),
    "ad_panel": ('[role="alertdialog"]', None),
    "am_child": ('[aria-modal="true"] span', None),
    "ad_child": ('[role="alertdialog"] span', None),
    # 分支对抗那两块：祖先在自己身上声明与面板相反的 color-scheme（真站上 docs.github 在
    # 页面 wrapper 上声明 light、github 首页在 main/react-app 上声明 dark）。**浮动面**必须按
    # 面板档解，不跟着祖先翻——这一格在补尺子之前六站两档里翻过 15/15 与 18/21。
    # 2026-10-04 契约分裂：钉档只钉在浮动面上，常驻条不钉，跟着所在区域翻，
    # 所以同一棵 dark 树下另挂一根条（下面那两枚探针），它要的读数与上面两块相反。
    "anti_dark": (".anti-dark-panel", None),
    "anti_light": (".anti-light-panel", None),
    "anti_dark_child": (".anti-dark-panel .it", None),
    "anti_dark_bar": (".anti-dark-bar", None),
    "anti_dark_bar_child": (".anti-dark-bar .it", None),
    "kbd": ("kbd", None),
    # 按钮面：box 那一族只量边框（bw/bs/bc），底色和面上的字这两格此前没有尺子——
    # 而这一轮改的正是"白天混 34%、夜晚混 24%"这个浓度，它落在 background-color 上。
    # querySelector("button") 取到的是探针页里第一个未禁用的 <button>。
    "btn_face": ("button", None),
    # 面上的淡墨（#39）：CSS 里 `del, s { color: var(--ks-ink-3) }` 直接命中子元素，
    # 会落进我们涂的面上。三条线各盯一格：按钮面里、玻璃面里、画布上——
    # 画布那一条是"别把淡墨整条抹掉"的反面证人，少了它就分不清"面上不让淡"和"全站没淡墨"。
    "btn_del": ("button .kd", None),
    "glass_del": ("#dlg .gd", None),
    "plain_del": ("#selp .pd", None),
    "filebtn": ('input[type="file"]', "::file-selector-button"),
}
# focus 和 backdrop 这两个必须挑时机取（一个要刚聚焦、一个要已经 showModal），
# 由探针脚本单独写进 out.focus / out.backdrop
SPECIAL = ("focus", "backdrop")

# 族末尾那截 :not(button, svg) 的尺子：造一个"类名里带词根、但它是按钮／图标"的元素，
# 站点自己排过底色，然后问计算样式这层底还在不在、虚焦有没有落上去。
# 形状是量出来的，不是猜的：GitHub 首页服务端 HTML 里词根命中的 31 个元素有 5 个
# <button class="NavDropdown-module__button__PEHWX">、5 个 <svg class="…buttonIcon…">。
# 底色只写在这张表里一次：探针页那条作者 <style> 由它生成，期望值和喂给页面的值是同一份
YIELD = {"btn": ("button", "ksYieldDrop", "dropdown-toggle", (0x2F, 0x81, 0xF7)),
         "icon": ("svg", "ksYieldIcon", "popover-icon", (0x0F, 0x9D, 0x58))}

# 这一族"常驻条"词根（sidebar / topnav / secondarybar / fixed-btn，外加 2026-10-03
# 改判「接管常驻条」转正的 navbar / header）：
# 每根一块面板，面板自己涂底、里面的 span 自己写白字——这两条站点声明是判据的地基。
# 没有它们，"这一根在不在族里"在计算样式上量不出来：面板不画底就是透明，
# 子元素从父级继承墨，把词根整根删掉照样一位不差（那就是等价变异）。
# 类名逐字取自真站服务端 HTML：w3schools 的 w3-sidebar 与 topnavcontainer、
# docs.github.com 的 DocsSecondaryBar_bar、runoob 的 Tutorial_fixed-btn。
# 每个元素只挂一根新词根：两根挂同一块上，删掉其中一根它还是玻璃，红就报不出来。
# 钩子名刻意不含任何词根的字面：[class*="…" i] 是**不区分大小写的子串**匹配，钩子里留着
# 词根的字面时，词根只要被改成另一个仍能匹配钩子的拼法，面板照样是玻璃——刀落了，而词根
# 那一格量不到任何东西。这条不是推测：K14（fixed-btn→fixedbtn）第一跑 MISSED，撞的是
# ksChromeFixedBtn；四个面板钩子改名后它又被 ksYieldFixedBtn 撞了一次（"ksyieldfixedbtn"
# 里含 "fixedbtn"）；两批改完，同一把刀才红在 玻璃面/后代字色 那两本上（实测站点底
# rgb(239,241,243) 顶掉期望的玻璃色）。守卫住在 load_family 末尾，第一次跑就抓到改名者
# 自己（AsideBar 里含 sidebar）；它的刀是 K15——topnav→bar 同时命中钩子名和三块站点类名，
# 所以只能由守卫报，报的是名字而不是着色值。
FLOATROOTS = {"sidebar": ("ksChromeRail", "w3-sidebar SiteSidebar", (0xFF, 0xFF, 0xFF)),
          "topnav": ("ksChromeBarTop", "topnavcontainer SiteTopNav", (0x28, 0x2A, 0x35)),
          "secondarybar": ("ksChromeDocAside", "DocsSecondaryBar_bar",
                           (0xFF, 0xFF, 0xFF)),
          "fixedbtn": ("ksChromeFloatBtn", "Tutorial_fixed-btn", (0xEF, 0xF1, 0xF3)),
          # 2026-10-03 改判「接管常驻条」转正的两根：站点类名逐字取自真站
          # （docs.github.com 的 SiteNavbar／GitHub 页头 Header_stickyContainer header），
          # 站点底沿用从前当否决时量到的那两个值，正控制换方向——这两块必须是我们的面。
          "navbar": ("ksChromeSiteNav", "SiteNavbar navbar", (0xEF, 0xF1, 0xF3)),
          "header": ("ksChromeStickTop", "Header_stickyContainer header",
                     (0xF6, 0xF8, 0xFA))}
# 坐在正文容器里的那一格（#80）：页头那一截带着「挂在 main／article 之下就让路」那道排除，
# 普查量到它扳上的 24 块里 22 块不浮着、最大的两块坐在正文容器里，所以这条让路是有账的。
# 从前它只有真站读数、没有夹具证人——这一格在夹具里怎么漂都没人报。钩子名刻意不含词根，
# 站点类名要含 header：让路判的正是"类名撞上词根、但它坐在正文里"这一格。
# 作者底沿用 FLOATROOTS 里 navbar／header 那两行已经量过的 #f6f8fa，不是对新块的重测。
MAINYIELD = {"inMainHeader": ("div", "ksYieldDoc", "page-header-content", (0xF6, 0xF8, 0xFA))}
# 标题形被词根子串撞上那一格（2026-10-05 runoob）：<h2 class="tutheader"> 被 header 那截按
# 子串追上，站点一处纯文字标题被画上整幅面（配对重拍现量：1280×1500 的框里四块带
# y=496–539、1263–1306、1361–1404、1459–1499，每块 x=232–1069；白天档摘掉那一截前
# rgb(254,234,243)、摘后 rgb(250,247,246)＝站家那块浅底）。族末尾因此多了一道 :not(h1…h6)。
# 这一对是同一条类名的正反两形：h2 那枚必须留着站家的底，div 那枚必须吃到面——
# 两块同红才是这一截写坏了（只有反面那枚的话，"整根 header 词根被摘掉"也会绿给它看）。
# 作者底沿用上面 MAINYIELD／FLOATROOTS 已经量过的 #f6f8fa，不是对新块的重测。
HEADEXCL = {"headingRootClass": ("h2", "ksYieldHeading", "tutheader", (0xF6, 0xF8, 0xFA))}
HEADCARRY = ("div", "ksTakeHeading", "tutheader")
# <body> 挂着 header-dark 那一格（2026-10-04）：header 词根是按子串认的，GitHub 把 body 写成
# class="logged-out env-production page-responsive header-dark"，族开头那道 :not(body, html)
# 不在的话整页会被玻璃糊上——站点排在 body 上的底会被顶掉、backdrop-filter 会挂在 <body> 上
# 白烧一层合成层。这一枚是那道排除唯一的反面证人（正面那一格由 chrome_header 那根举着）。
BODYROOTS = {"bodyHeaderClass": ("body", "ksBodyHost", "header-dark", (0x1F, 0x6F, 0xEB))}
# 常驻条上那一枚控件的正面证人（2026-10-04 用户说"这个按钮的元素强调还是太突兀了"）：
# 壳与钮的类名逐字取自 github.com/features 页头现量到的两块，站点给钮排了实心蓝底白字。
# 壳刻意留一个直接子节点 button——真站那 5 块正是这个形状，它因此被族末尾的
# :not(:has(> button)) 排在玻璃之外，而"条上的控件"那一支照旧管得到它。
BARBTN_HOST = ("div", "ksChromeBarBtnHost", "navbar")
BARBTN = ("button", "ksChromeBarButton", "NavDropdown-module__button__PEHWX")
BARBTN_SITE = (0x2F, 0x81, 0xF7)
# 条那一支（裸链接形）的两枚证人（2026-10-04）。钩子名刻意不含 btn／button 的字面：
# §4b 的链接形和"条上的控件"那一支都按这两截子串匹配，钩子含了就没有一问是它们之外的。
# 壳的站点类名用 navbar 那一截（真站形状由上面 BARBTN_HOST 举着）——这一格要的是
# "链接坐在条下"这个形状，不是又一份原文类名。
# 反面那枚的绿字是喂给页面的声明与断言里的期望值同一份，按 BODYLINK_SITE 现拼。
BARLINK_HOST = ("div", "ksChromeBarLinkHost", "navbar")
BARLINK = ("a", "ksChromeBarLink")
BODYLINK = ("a", "ksBodyLink")
BODYLINK_SITE = (0x1A, 0x7F, 0x37)
# 两截按 id 命中的词根（2026-10-04 补证人）：族里 [id*="topnav" i]:not([id*="below" i]) 与
# [id*="pagetop" i] 这两截从前只有真站读数、没有夹具证人——FLOATROOTS 的面板按 class 生成，
# 而这两截只看 id 属性，所以它们在族里怎么漂都没人报。id 形照 w3schools 服务端 HTML 的拼法：
# 第三条深蓝导航条 id="subtopnav"、页头第一行 id="pagetop"。钩子名刻意不含词根子串：下面的
# 钩子守卫把「钩子名里含词根」当成词的等价拼法直接判死，含了就是自己撞自己。
# 作者底沿用本文件里已经量过的那两个值，不是对这两块的新测量——正控制只要求"我们的面"和
# "站家的底"可分。
IDROOTS = {"id-topnav": ("ksChromeIdBar", "subtopnav", (0x28, 0x2A, 0x35)),
           "id-pagetop": ("ksChromeIdHead", "pagetop", (0xFF, 0xFF, 0xFF))}
# id 形那一截的排除式反证：站家把"顶部导航条下面那一整片"命名成 id="belowtopnavcontainer"，
# :not([id*="below" i]) 把它排在外面。这块和 MIDTOKEN 那一格问的是同一条让路，但走的是 id
# 属性而不是 class 词边界——两截各有自己的证人，红起来点的是不同的名。
IDEXCL = {"belowTopnavId": ("div", "ksYieldIdBelow", "belowtopnavcontainer",
                            (0xEB, 0xF1, 0xF8))}
# 族决定**不去追**的那一截词根：追得上类名、但形状是 <button> 的。
# 判据和 YIELD 同一条（站点那块底必须原样留着、不许糊上虚焦），归因不同：
# YIELD 红等于 :not() 少了项，这一块红等于词根被加了进来。
# navbar / header 那笔否决在 2026-10-03 被用户改判成「接管常驻条」：docs.github.com 上
# navbar 命中 23 个元素（浮动面 0 个）、header 命中 7 个（浮动 1 个、文档流 5 个）——
# 页头那三条带各自涂底、彼此不谐，改判要的就是这一块被统一。这两截于是进 FLOATROOTS。
NOTROOTS = {"fixedBtn": ("button", "ksYieldFloatBtn", "Tutorial_fixed-btn",
                         (0x2E, 0xA4, 0x63))}
# 第三种"不该管"：词根本身确实在族里，但这一块上的词根只出现在类名**中间**、没落在词边界上。
# w3schools 用 belowtopnavcontainer 命名"顶部导航条下面那一整片"——实测它 position: static、
# 1280 视口下占 5,895,110 px²，是整页容器而不是浮动条。子串形式 [class*="topnav" i] 把它的
# 底扳成玻璃，而它里面站点自己涂白的卡片仍是白底，后代那条把夜色墨压上去：真站同一坐标逐行
# 配对量到正文列 17 行从 OFF 中位 16.85:1 掉到 ON 1.16:1（左栏那一列两档 202/202 行逐行相同，
# 所以这笔损害精确归这一格，不归 sidebar 那根）。topnav 收成词边界形式之后它必须原样留着
# 站点的底；判据与 NOTROOTS 同一条，归因不同——这一格红等于"词边界被退回子串匹配"。
MIDTOKEN = {"belowTopnav": ("div", "ksYieldPageWrap", "belowtopnavcontainer",
                            (0xEB, 0xF1, 0xF8))}
# 侧栏套侧栏那一格（2026-10-04 收窄）：[class*="sidebar" i] 整根匹配会连整页版式壳一起扳，
# 所以族里那一截收成「最里层才穿玻璃」——:not(:has([class*="sidebar" i]))。这条排除只看形状
# 不看位置，夹具要给一对嵌套块：外层留给站点（下面的反证），内层仍穿玻璃（正面在 SPECS 那行
# 「玻璃面 嵌套内层」）。只有反证的话，"收得太狠一块都不给"这一种错法没人管。
# 两块类名逐字取自 runoob 服务端 HTML：2026-10-04 普查那一张表的父链列量到
# div.sidebar-box>div.sidebar-box>div.fivecol 这样的父子同名嵌套，同一枚类名挂两层。
# 作者底按 ".<钩子名>" 拼（和上面四张表同一格），所以站点类名那一栏可以照真站写整串。
NESTED_OUTER = ("div", "ksYieldNestedRail", "sidebar-box gallery-list", (0xFF, 0xFF, 0xFF))
NESTED_INNER = ("div", "ksChromeNestedInner", "sidebar-box re-box", (0xFF, 0xFF, 0xFF))
NESTED = {"outerRail": NESTED_OUTER}
# 站点自己的声明（底色，以及浮动条面板上那行白字）由这几张表生成，
# 期望值和喂给页面的值是同一份——写在两处就会有一处先烂
AUTHOR_PAINT = ([(cls, site) for (_tag, cls, _s, site) in YIELD.values()] +
                [(cls, site) for (_tag, cls, _s, site) in NOTROOTS.values()] +
                [(cls, site) for (_tag, cls, _s, site) in MIDTOKEN.values()] +
                [(cls, site) for (cls, _s, site) in FLOATROOTS.values()] +
                [(NESTED_OUTER[1], NESTED_OUTER[3]), (NESTED_INNER[1], NESTED_INNER[3])] +
                [(h, bg) for (h, _i, bg) in IDROOTS.values()] +
                [(cls, site) for (_tag, cls, _s, site) in IDEXCL.values()] +
                [(cls, site) for (_tag, cls, _s, site) in MAINYIELD.values()] +
                [(cls, site) for (_tag, cls, _s, site) in HEADEXCL.values()] +
                # HEADCARRY（正控制那枚 div.tutheader）刻意不给作者底：期望值由 FACE 那块现推，
                # 站点声明加不加都不改它；少了这格反而有牙——一旦它不再吃面，计算样式回到
                # rgba(0,0,0,0)，那一本就红。喂了站家底的话"摘掉整族上色"会被站家的底盖过去。
                [(cls, site) for (_tag, cls, _s, site) in BODYROOTS.values()] +
                [(BARBTN[1], (0x2F, 0x81, 0xF7))])
# 站点写在那枚条上控件字上的白（真站形状：GitHub 的导航触发钮 color: rgb(255,255,255)）
BARBTN_INK = "#fff"
SITE_CHILD_INK = "#fff"

# 面那一条规则的锚点按"形状"匹配而不是按内容：族末尾的排除式正是会被增删的那一格，
# 把它的项抄进锚点，割掉一项的刀会先把锚点打断，闸门死在"解不出期望值"那一行上，
# 于是这一格真正要报的红（玻璃溢到了非浮层控件）永远轮不到说话。
# 量过：锚点写成排除式的内容时，K07/K08/P07/P08 四柄刀全哑在这一行上（都是 MISSED，
# 报的是"锚点命中 0 处"而不是被割的那一本）。
FACE = r':not\((?:[^()]|\([^()]*\))*\)\s*\{'

# 浮动面钉档那一条（§4c 面块下面那条 :where(:is(…)…)）的锚点。面块自己不再声明
# color-scheme（2026-10-04 契约分裂：常驻条跟着区域翻），所以"摘掉钉档会怎样"那三柄刀
# （tools/knives.py 的 CUT_TARGET）从面块改指到这里。这条只有一格声明，SPECS 里没有
# 任何一行按 color-scheme 解期望值，判据走"实测与声明不符"那条收集路径。
PIN = r':where\(:is\(dialog'

# 这一句和下面三个"为什么没让路"的尾巴，是 tools/knives.py 里 K07/K08/K16 三柄刀的期望名，
# 所以住在闸门这一侧由两边共读：措辞在这里改掉而刀柄里没跟着改，那三柄会静默变成 MISSED
# ——判据照样红，红的却不是被点名的那一本，读起来像"尺子瞎了"。（已经踩过一次：
# 这一句从前写"溢到了非浮层控件"，K07/K08 的期望名留在那个旧措辞上，全量重跑才看见。）
OVERFLOW = "玻璃溢到了不该管的那一块"
WHY = {"yield": "(族末尾的 :not)",
       "roots": "(词根本族没追或形状是控件)",
       "mid": "(词根没落在词边界上)",
       "nested": "(侧栏套侧栏，外层按收窄让路)",
       "id": "(id 形那截让给 :not([id*=below]))",
       "main": "(坐在 main／article 里，按让路)",
       "body": "(挂在 <body> 上，按 :not(body, html) 让路)",
       "heading": "(标题形，按 :not(h1…h6) 让路)"}

# 名字、CSS 里那条规则的锚点、属性、探针键、从计算样式里取哪个字段
SPECS = [
    ("裸表外框",   r"table\s*\{",                        "border",              "table",     "bc"),
    ("组框",       r"fieldset\s*\{",                     "border",              "fieldset",  "bc"),
    ("表题字色",   r"caption\s*\{",                      "color",               "caption",   "fg"),
    ("单元格底线", r"th, td\s*\{",                       "border-block-end",    "td",        "bbc"),
    ("竖分隔线",   r"\+\s*:is\(th, td\)\s*\{",           "border-inline-start", "sep",       "bic"),
    ("表头字色",   r"thead th\s*\{",                     "color",               "thead_th",  "fg"),
    ("表头淡底",   r"thead th\s*\{",                     "background-color",    "thead_th",  "bg"),
    ("表头底线",   r"thead th\s*\{",                     "border-block-end",    "thead_th",  "bbc"),
    ("斑马偶行",   r"tbody tr:nth-child\(even\)\s*\{",   "background-color",    "zebra_even", "bg"),
    ("引用左线",   r"blockquote\s*\{",                   "border-inline-start", "quote",     "bic"),
    ("引用淡面",   r"blockquote\s*\{",                   "background-color",    "quote",     "bg"),
    ("横线色",     r"hr\s*\{",                           "border-color",        "hr",        "bc"),
    ("高亮底色",   r"mark\s*\{",                         "background-color",    "mark",      "bg"),
    ("图例字色",   r"legend\s*\{",                       "color",               "legend",    "fg"),
    ("折角标记",   r"summary::marker[^{]*\{",            "color",               "marker",    "fg"),
    ("折叠开关",   r"summary\s*\{",                      "color",               "summary",   "fg"),
    ("选中底色",   r"::selection\s*\{",                  "background-color",    "selection", "bg"),
    ("选中字色",   r"::selection\s*\{",                  "color",               "selection", "fg"),
    ("聚焦环",     r":focus-visible\s*\{",               "outline-color",       "focus",     "ol"),
    ("遮罩底色",   r"dialog::backdrop[^{]*\{(?=[^}]*background-color)",
                                                       "background-color",    "backdrop",  "bg"),
    # §4c 那族浮层：面和后代各一条，锚点都取族选择器的收尾形状（FACE 与 `h6) {`），
    # 这两个形状各自在全文件恰好 1 处，所以面与后代两格分得出来。
    # FACE 为什么按形状匹配，见它自己那一段的账。
    ("玻璃面底色",   FACE, "background-color",    "dialog",      "bg"),
    ("玻璃面字色",   FACE, "color",               "dialog",      "fg"),
    ("玻璃后代字色", r"h6\)\s*\{",                      "color",               "glass_child", "fg"),
    # 第九格那两块：除了语义属性没有任何别的钩子能把它们扳成玻璃。少了这四行，
    # "[aria-modal] 到底吃没吃到"就只剩 CSS 里那句话自己说。
    ("玻璃面 aria-modal",   FACE, "background-color", "am_panel", "bg"),
    ("玻璃面 alertdialog",  FACE, "background-color", "ad_panel", "bg"),
    ("后代字色 aria-modal", r"h6\)\s*\{",                      "color",       "am_child", "fg"),
    ("后代字色 alertdialog", r"h6\)\s*\{",                     "color",       "ad_child", "fg"),
    # 分支对抗那三行：期望值与「玻璃面底色」同一条（都由 FACE 那块现推），差别只在被测元素
    # 站在一格声明了相反档的祖先里。白天档里 dark 那格是反着来的，夜晚档里换 light 那格反着来，
    # 所以两档各有一格在盯着"分支到底谁说了算"；少了这三行，翻档这件事只有 CSS 那句话自己说。
    ("反档祖先玻璃面(祖先dark)",  FACE, "background-color", "anti_dark",      "bg"),
    ("反档祖先玻璃面(祖先light)", FACE, "background-color", "anti_light",     "bg"),
    ("反档祖先玻璃后代",       r"h6\)\s*\{",                   "color",         "anti_dark_child", "fg"),
    # kbd 的锚点要带前瞻：§4 那条 `pre, code, samp, kbd {` 也以 "kbd {" 收尾，
    # 只按 "kbd {" 切会命中两处，而那两处的意图正好相反（一处只借圆角、一处给面）
    ("键帽底色",   r"kbd\s*\{(?=[^}]*background-color)", "background-color",    "kbd",       "bg"),
    ("键帽边框",   r"kbd\s*\{(?=[^}]*background-color)", "border",              "kbd",       "bc"),
    # 按钮那三格：锚点取整条选择器列表（不是 :not() 排除式，也不含被测的那行声明），
    # 割掉 background-color / color 的刀会红在"那条规则块里没有 X 声明"上，
    # 而不是红在"锚点命中 0 处"——后者报不出被割的是哪一本。
    # §4b 那条只给圆角和投影的 `button, [type="button"], [type="submit"], [type="reset"], [type="file"]`
    # 与打印那条 `... [role="button"], .btn ...` 都在同一个文件里，所以列表要写到 [type="reset"] 才分得开。
    ("按钮底色",   r"button,\s*\[type=\"button\"\],\s*\[type=\"submit\"\],"
                   r"\s*\[type=\"reset\"\]\s*\{",         "background-color",    "btn_face",  "bg"),
    ("按钮字色",   r"button,\s*\[type=\"button\"\],\s*\[type=\"submit\"\],"
                   r"\s*\[type=\"reset\"\]\s*\{",         "color",               "btn_face",  "fg"),
    # 文件钮那条前面有顶格两空格、打印块里那条缩进四空格：靠缩进分，不靠声明内容分
    ("文件钮底色", r"\n  ::file-selector-button\s*\{",    "background-color",    "filebtn",   "bg"),
]

# 四根新词根各两条：面那一格判"站点那块底有没有被换成玻璃"，后代那一格判
# "站点写死的白字有没有被换走"。锚点与 dialog／am／ad 那几行同形（FACE 与 h6) {），
# 期望值从同两条规则现推，脚本里不另抄颜色。
# 名字用词根本身，不用面板号：删掉 CSS 里那一根，红的名字就点着那根词根。
for _root, (_cls, _site_cls, _site_bg) in FLOATROOTS.items():
    STYLE_PROBE[f"chrome_{_root}"] = (f"div.{_cls}", None)
    STYLE_PROBE[f"chrome_{_root}_child"] = (f"div.{_cls} span", None)
    SPECS.append((f"玻璃面 {_root}", FACE, "background-color", f"chrome_{_root}", "bg"))
    SPECS.append((f"后代字色 {_root}", r"h6\)\s*\{", "color",
                  f"chrome_{_root}_child", "fg"))

# 收窄的正面：内层那一块仍然必须是玻璃。名字点着这一格而不是接着编号，因为它的失效方向
# 是「排除写得太宽」，和 M 段那几柄问的「词根在不在族里」不是同一条。
# 两截 id 形各两条，和 FLOATROOTS 那个循环同形：面判"站家的底有没有被换成玻璃"，
# 后代判"站点写死的白字有没有被换走"。名字点着 id 那一截，摘掉词根时红的就是这一行。
for _name, (_hook, _id, _bg) in IDROOTS.items():
    STYLE_PROBE[f"chrome_{_name}"] = (f"div.{_hook}", None)
    STYLE_PROBE[f"chrome_{_name}_child"] = (f"div.{_hook} span", None)
    SPECS.append((f"玻璃面 {_name}", FACE, "background-color", f"chrome_{_name}", "bg"))
    SPECS.append((f"后代字色 {_name}", r"h6\)\s*\{", "color",
                  f"chrome_{_name}_child", "fg"))

STYLE_PROBE["nested_inner"] = ("div." + NESTED_INNER[1], None)
SPECS.append(("玻璃面 嵌套内层", FACE, "background-color", "nested_inner", "bg"))

# 淡墨落进面里那三格（#39）。追加在末尾而不是插进上面的字面表：knives.py 的 S 号按
# SPECS 顺序现推，往中间插会把已有刀的编号顶掉，而 M 段和若干散文按号点名。
# 「按钮面淡划字色」的锚点是本轮新写那条规则的形状，全文件只有它有 `[type="reset"] :is(del, s) {`。
SPECS.append(("按钮面淡划字色", r"\[type=\"reset\"\]\s+:is\(del, s\)\s*\{",
              "color", "btn_del", "fg"))
SPECS.append(("玻璃面淡划字色", r"h6\)\s*\{", "color", "glass_del", "fg"))
SPECS.append(("画布淡划字色", r"del, s \{", "color", "plain_del", "fg"))
# 常驻条那两支（2026-10-04）各一行，同样追加在末尾而不是插进上面的字面表——理由与 #39
# 那三行一样：S 号按 SPECS 顺序现推，往中间插会把已有刀的编号顶掉，而 knives.py 的散文
# 按号点名（本轮第一版就插在了中间，S23/S41/S44 三处号因此漂了 1，改回来才发现）。
# 「常驻条控件上墨」的锚点取那一支独有的那一截 a[href][class*="btn" i]) {，全文件恰 1 处。
# 它的面那一格不在这里——CSS 写的是字面量 transparent，期望值解析器只认 var(--ks-*) 与
# color-mix(...) 两形，所以那格由 check() 里"站点那块蓝底必须不见"直判，
# 并由配对的那枚条外控件举着作者底确实加载了。
SPECS.append(("常驻条控件上墨", r'a\[href\]\[class\*="btn" i\]\)\s*\{',
              "color", "chrome_bar_btn", "fg"))
# 「常驻条链接上墨」是那一支的裸链接形：锚点取 `a[href] {`，全文件恰 1 处，
# 且不含那道 :not(body, html)——割掉排除式的刀要红在"条外那枚也被上墨"上，
# 不能先把锚点打断（锚点断了闸门死在解析那一步，想点的名字进不了红名单）。
SPECS.append(("常驻条链接上墨", r"a\[href\]\s*\{", "color", "chrome_bar_link", "fg"))
# 标题形那一对的正控制（同一枚 tutheader 挂在 div 上必须吃到面）：追加在末尾，理由与上面
# 那几行相同——S 号按 SPECS 顺序现推，往中间插会把已有刀的编号顶掉。
STYLE_PROBE["chrome_heading_div"] = ("div." + HEADCARRY[1], None)
SPECS.append(("玻璃面 标题形对照", FACE, "background-color", "chrome_heading_div", "bg"))

# 面内搜索壳那三格（#132）。追加在末尾，理由与上面那几行相同：S 号按 SPECS 顺序现推，
# 往中间插会把已有刀的编号顶掉。锚点取那一支独有的收尾 `combobox))) {`，全文件恰 1 处。
# 反面那两格不进 SPECS：它们的期望值是**站点自己那行白**，不来自我们的声明，
# 而期望值解析器只读我们的声明——和「常驻条控件上墨」同一类处置。
SHELL_ANCHOR = r'combobox"\]\)\)\s*\{' 
SHELL_SITE = (0xFF, 0xFF, 0xFF)
# 壳与面的最坏分离度地板（#140）。白天 8 是从"改回 transparent 就读 0"那一端反推的：
# 现读 10.3，留 2.3 的余量给解析与渲染口径差（同一枚 token 246 现读会渲成 244，量过）。
# 夜档 2026-10-10 先钉在 3 是因为那时夜枝用的就是面那支 token，关系形证人当场读出 **0.0**
# （不是先前估的 4.5：壳不透明时压不出任何一端，α_壳=1 ⇒ 两个端点都塌回面 token 自己）。
# #141 把夜枝换成 canvas-1 后现读 27.5，两档因此共用同一个地板。
SHELL_SEP_MIN = {"light": 8, "dark": 8}
STYLE_PROBE["shell_in_face"] = ("div.quick-search-input-module__searchContain__X1", None)
STYLE_PROBE["shell_no_ctrl"] = ("div.quick-search-input-module__searchContain__X2", None)
STYLE_PROBE["shell_out_face"] = ("div.quick-search-input-module__searchContain__X3", None)
SPECS.append(("面内搜索壳底", SHELL_ANCHOR, "background-color", "shell_in_face", "bg"))
# 环与边那两格（#157）：#111 往壳上落的这两条声明当时只有 DOM 侧与像素侧证人，
# 计算样式那本没问「这两行落没落在壳上」。同一枚锚点、同一支探针，各再问一句；
# 刀不用手写——knives.py 按 SPECS 自动生成 S59/S60（摘声明 → 本行点名 die）。
SPECS.append(("面内搜索壳环色", SHELL_ANCHOR, "outline-color", "shell_in_face", "ol"))
SPECS.append(("面内搜索壳边色", SHELL_ANCHOR, "border-color", "shell_in_face", "bc"))

# 面里控件底那两枚（#135）：期望值一个是字面量 transparent、一个是站点那行绿，
# 都不来自我们的 var(--ks-*) 声明，所以不进 SPECS，由 check() 里直判——
# 与「常驻条控件上墨」「面内搜索壳反面」同一类处置。
STYLE_PROBE["face_in"] = ("input.ksFaceIn", None)
STYLE_PROBE["face_in_site"] = ("input.ksFaceSiteIn", None)
FACE_IN_SITE = (0x1A, 0x7F, 0x37)

fails = []


def die(msg):
    print(f"CTRL FAIL: {msg}")
    sys.exit(1)


def load_gate(name):
    """按路径导入 check-contrast.py：解析器只住一本，两本闸门共用。"""
    path = ROOT / "tools" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# 模块级就绑定：close() 和 MIX_RE 要在各自的定义点取这一本里的单一定义，
# 等 main() 再导入就晚了（这两处都在模块级）。check-contrast.py 有 __main__ 守卫，
# 导入它只是拿解析函数，不会把对比度闸门跑一遍。
GATE = load_gate("check-contrast.py")


def rgb(text):
    """把 Chrome 计算出来的三种颜色写法归成一个可比的三元组。"""
    text = text.strip()
    m = re.fullmatch(r"rgba?\(\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\s*\)", text)
    if m:
        a = 1.0 if m.group(4) is None else float(m.group(4))
        return tuple(round(float(m.group(i))) for i in (1, 2, 3)), a
    m = re.fullmatch(r"color\(srgb\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)(?:\s+/\s*([\d.]+))?\)", text)
    if m:
        a = 1.0 if m.group(4) is None else float(m.group(4))
        return tuple(round(float(m.group(i)) * 255) for i in (1, 2, 3)), a
    return None, None


def close(a, b, tol=None):
    """带宽只住在 gate 那一本：这里比探针读数，那里比"这档跟页面撞不撞色"，
    两条判据必须认同一个"同一个颜色"。"""
    return GATE.close(a, b, tol)


def alpha_of(text, what, label):
    """取不透明度。解析不出来时必须炸，不能让"量不到"顺着 == 0.0 那一条溜成假绿。"""
    a = rgb(text)[1]
    if a is None:
        die(f"{label} {what} 的颜色读不出（实测 {text!r}）——伪元素没被支持还是探针没跑？")
    return a


def build(branch):
    h = ['<!doctype html><html lang="zh"><head><meta charset="utf-8">',
         '<link rel="stylesheet" href="../skin.css">',
         f'<style>:root{{--kScheme:{branch};}}</style>',
         # 站点自己写在浮层子项上的白字：权重比 §4c 后代那条高（id+class vs 两个类型选择器），
         # 只有 !important 才压得住。没有这一条竞争，子元素是从弹窗继承到同一份墨色，
         # 把后代规则整条删掉也不会红——那这一行判的就不是后代规则。
         '<style>#dlg .it{color:#fff}</style>',
         # 站点自己排在按钮/图标/导航条/吸顶容器上的底色，和浮动条面板自己写的那行白字：
         # 类名带词根（或被词根的子串误伤），正是族会吃到的那几块。
         # 有这一条作者声明，"排除式没漏"和"词根确实追上了那一面"才量得出来——
         # 没有它，删掉 :not 里的 button、或整根删掉 sidebar，都只是把透明玻璃画在透明地上，
         # 计算样式读不出任何区别
         "<style>" + "".join(
             f".{cls}{{background:#{r:02x}{g:02x}{b:02x}}}"
             for cls, (r, g, b) in AUTHOR_PAINT) +
             "".join(f".{cls} span{{color:{SITE_CHILD_INK}}}"
                     for cls, _s, _bg in FLOATROOTS.values()) +
             "".join(f".{h} span{{color:{SITE_CHILD_INK}}}"
                     for h, _i, _bg in IDROOTS.values()) +
             f".{BARBTN[1]}{{color:{BARBTN_INK}}}" + "</style>",
         # 站点自己用 !important 写的白底链接钮。没有这条竞争，把皮肤里那条新规则整块
         # 删掉也不会红，判据就是空的。夹具里 skin.css 是 <link> 进来的作者源，和这条
         # 作者规则同层，所以量到的是两种通道里较弱的那一种（同层比 !important，两条都
         # 带时比特异度：我们的 a[href][class*=…] 是 0,2,1，站点这条 a.ksWhiteBtn 是 0,1,1）；
         # 产品那一格若落在用户源只会更强，而挂载通道在哪一层没量到（#53 记的是文档推断）。
         '<style>a.ksWhiteBtn{background-color:#fff !important;color:#222 !important}'
         # GitHub 文档页那颗 "Quickstart" 的形状（2026-10-06 从缓存文档现读）：站点把字色排在
         # **孙节点**的类名上（.Button--label-primary{color:var(--brand-button-primary-fgColor-rest)}，
         # 0,1,0、不带 !important）。我们把面扳成粉、把墨写在 <a> 上，孙节点那条直接命中声明
         # 照样赢——继承值在任何直接命中面前都输，与 !important 无关。量到的就是 1.36:1。
         '.ksPrimerLabel{color:#fff}</style>',
         # 条那一支（裸链接形）那两枚证人各自的站点声明：条下那枚排白字——真站上导航字就是
         # 站点写死的白（w3schools 第三条深蓝条、GitHub 锚点导航条同一形），正控制要的正是
         # "白字被换成自家墨"；条外那枚排带 !important 的绿字——反面证人要量的是"这一支没
         # 越到条外面来"，它必须原样留着站家的绿。两条都不带 !important 时，全局 a{} 那条
         # 用户声明会先把它们盖掉，那就成了替 a[href] 这一支作证。
         f'<style>a.{BARLINK[1]}{{color:{SITE_CHILD_INK}}}'
         f'a.{BODYLINK[1]}{{color:#{BODYLINK_SITE[0]:02x}'
         f'{BODYLINK_SITE[1]:02x}{BODYLINK_SITE[2]:02x} !important}}</style>',
         # <body> 上那枚 header-dark 是真站原文（GitHub features 页头 class 属性里的最后一截），
         # 站点自己排在 body 上的底由 AUTHOR_PAINT 生成——族开头那道 :not(body, html) 的证人
         f'</head><body class="{BODYROOTS["bodyHeaderClass"][1]}'
         f' {BODYROOTS["bodyHeaderClass"][2]}">']
    for t in TEXT_TYPES + EXCLUDED_TYPES:
        h.append(f'<input type="{t}" value="x">'
                 f'<input type="{t}" value="x" readonly>')
    h.append('<input value="x"><input value="x" readonly>')
    h.append('<form><button>提交<del class="kd">旧</del></button><input type="submit" value="s">'
             '<input type="reset" value="r"><input type="text" value="t">'
             '<input type="date" value="2026-01-01">'
             '<select><optgroup label="暖色"><option selected>甲</option>'
             '<option>乙</option></optgroup></select>'
             '<textarea>x</textarea><input type="file">'
             '<input type="checkbox"><input type="radio" name="q">'
             '<input type="range"><input type="color" value="#d4508f">'
             '<progress value="0.6" max="1"></progress>'
             '<meter min="0" max="100" low="30" high="70" value="86">86%</meter>'
             '<fieldset><legend>组</legend><input type="text"></fieldset>'
             '<details open><summary>折</summary>内</details>'
             '<button disabled>禁</button><input type="text" value="d" disabled>'
             '<select disabled><option>甲</option></select>'
             '<textarea disabled>d</textarea>'
             '<dialog id="dlg">框<div class="it">项</div><del class="gd">旧</del></dialog>'
             '<div class="prc-Dialog-Backdrop-5Nt2U">遮</div>'
             # 遮罩的 mask 词根两形（真站原文）＋裸词根三枚反面（收成遮罩就会涂黑一块面板）
             '<div class="vui_dialog--mask">遮</div>'
             '<div class="jd_pc_dou_popup_mask">遮</div>'
             '<div class="Overlay">面板</div>'
             '<div class="wechat_overlay">白</div>'
             '<div class="sketch-mask">纸</div>'
             # 用户指的那颗白底钮：站点把它写成作者 !important 的链接形按钮
             '<a href="#x" class="ksWhiteBtn" role="button">白钮</a>'
             '<a href="#y" class="ksPrimerBtn" role="button"><span class="ksPrimerBtn__text">'
             '<span class="ksPrimerLabel">孙白</span></span></a>'
             # 第九格那两个"只挂语义属性"的面板：类名里没有任何族认得的词根，
             # 计算样式能取到玻璃，才说明 [aria-modal] 与 [role="alertdialog"] 真的在管事
             '<div class="amP" aria-modal="true"><span>甲</span></div>'
             '<div class="adP" role="alertdialog"><span>乙</span></div></form>')
    # 表格线/表题/引用/横线/高亮/选中/键帽这几类的探针：夹具里没这些元素就一条也判不了，
    # 所以这一串是尺子的地基，不是装饰
    h.append('<blockquote>引</blockquote><hr><mark>亮</mark><kbd>⌘</kbd><p id="selp">可选中<del class="pd">旧</del></p>'
             '<table><caption>题</caption>'
             '<thead><tr><th>甲</th><th>乙</th></tr></thead>'
             '<tbody><tr><td>一</td><td>二</td></tr><tr><td>三</td><td>四</td></tr></tbody>'
             '</table>')
    # 族的反面：这几块都是"类名里确实有词根、但它不该被扳"的形状，形状照真站抄。
    # YIELD 那两块是被末尾的 :not() 排在外面（按钮/图标），NOTROOTS 那一块是词根追到了
    # 类名但形状是 <button>（挂 fixed-btn 的那个），
    # MIDTOKEN 那一块是词根在族里、但在这个类名里没落在词边界上（belowtopnavcontainer）。
    for tag, cls, site_cls, _ in (list(YIELD.values()) + list(NOTROOTS.values())
                                  + list(MIDTOKEN.values())):
        h.append(f'<{tag} class="{cls} {site_cls}">'
                 f'{"" if tag == "svg" else "浮"}</{tag}>')
    # 族的新正面：四根浮动条词根各一块面板，里面一行站点白字（后代那条的取证对象）。
    # 站点类名要写在属性值**开头**、钩子名排在它后面：topnav 那根现在是词边界形式，其中
    # [class^="topnav" i] 只看属性值的起始，钩子名顶在前面就会让正控制自己先掉——实测反过来
    # 写时 CTRL 报"玻璃面 topnav 实测 rgb(40,42,53)"，即整根词根从这个探针上消失了。
    # 真站的形状也是这样：w3schools 服务端 HTML 里就是 class="topnavcontainer "。
    for cls, site_cls, _ in FLOATROOTS.values():
        h.append(f'<div class="{site_cls} {cls}"><span>条</span></div>')
    # 常驻条里那枚控件：壳带着 navbar 词根、钮是站点自己排过底色的那一形（真站原文类名）。
    # 它同时举两格——"条上的控件让面、上墨"的正面，和"这条不越到条外面去"的反面
    # （反面由 btn_face 举：form 里那颗裸钮照旧拿 §4b 的粉底）。
    h.append(f'<{BARBTN_HOST[0]} class="{BARBTN_HOST[2]} {BARBTN_HOST[1]}">'
             f'<{BARBTN[0]} class="{BARBTN[2]} {BARBTN[1]}">钮</{BARBTN[0]}></{BARBTN_HOST[0]}>')
    # 同一份作者底、同一枚类名，只是不坐在条下：这一枚举的是"那一支不越到条外面去"，
    # 同时也是上面那枚的配对正控制——作者底没加载上时两块会一起红，不会只留一个假透明。
    h.append(f'<{BARBTN[0]} class="{BARBTN[2]} {BARBTN[1]} ksBarOutside">钮</{BARBTN[0]}>')
    # 条那一支（裸链接形）的正反面一对：同一份白字，一枚坐在 navbar 词根命中的壳里、
    # 一枚直接挂在 <body> 下。条下那枚必须换成自家墨，条外那枚必须留着站家的绿——
    # 两块同红才是"这一支越到了条外面来"，只有正控制的话这一支写成 body 全局没代价。
    h.append(f'<{BARLINK_HOST[0]} class="{BARLINK_HOST[2]} {BARLINK_HOST[1]}">'
             f'<{BARLINK[0]} class="{BARLINK[1]}" href="#bar">条</{BARLINK[0]}>'
             f'</{BARLINK_HOST[0]}>')
    h.append(f'<{BODYLINK[0]} class="{BODYLINK[1]}" href="#body">正文链接</{BODYLINK[0]}>')
    # id 形那两截的正控制：属性走 id，钩子留在 class 上（ grabbing 用 tag.class 这一形）。
    # class 值刻意不含任何词根，免得这两块同时被 class 形那几截撞上——那样子就分不清
    # 红的是 id 那截还是 class 那截。
    # 让路的反面：一块 div.page-header-content 坐在 <main> 里，类名确实撞上 header 词根，
    # 但按那道排除它必须原样留着站家的底。放进 <main> 而不是并列——:is(main, article) 看的是祖先。
    for tag_, cls_, site_cls_, _ in MAINYIELD.values():
        h.append(f'<main><{tag_} class="{site_cls_} {cls_}">正文里的页头</{tag_}></main>')
    # 标题形那一对放在顶层：放进 <main> 就同时被 main 那道让路盖住，红起来说不清是哪一截。
    for tag_, cls_, site_cls_, _ in HEADEXCL.values():
        h.append(f'<{tag_} class="{site_cls_} {cls_}">标题里的词根</{tag_}>')
    h.append(f'<{HEADCARRY[0]} class="{HEADCARRY[2]} {HEADCARRY[1]}"><span>条</span>'
             f'</{HEADCARRY[0]}>')
    for _name, (hook, _id, _bg) in IDROOTS.items():
        h.append(f'<div id="{_id}" class="{hook}"><span>条</span></div>')
    for tag, cls, site_cls, _ in list(IDEXCL.values()):
        h.append(f'<{tag} id="{site_cls}" class="{cls}">{"" if tag == "svg" else "整页"}'
                 f'</{tag}>')
    # 那一对写成父子而不是并列：:not(:has(…)) 只看后代，并列会让外层自己也是叶子，
    # 排除生没生效就量不出来了
    h.append(f'<{NESTED_OUTER[0]} class="{NESTED_OUTER[2]} {NESTED_OUTER[1]}">'
             f'<{NESTED_INNER[0]} class="{NESTED_INNER[2]} {NESTED_INNER[1]}"><span>条</span></{NESTED_INNER[0]}></{NESTED_OUTER[0]}>')
    # 分支对抗两块：真站上站点把 color-scheme 写在自己的 wrapper 上（docs.github 写在页面
    # 容器上是 light、github 首页写在 main/react-app 上是 dark），而面板档只钉在 :root，
    # 够不到那两层子树——2026-10-01 六站两档现量到族里的面整批跟着翻（夜晚档 15/15 块解成
    # 白天枝、白天档 18/21 块解成夜晚枝）。这一族是"我们接管面与墨"的那一层，档必须由面板定，
    # 所以这里各挂一个唱反调的祖先；两档跑下来每档恰有一格在对抗。
    h.append('<div style="color-scheme:dark"><div role="dialog" class="anti-dark-panel">'
             '<span class="it">祖先声明 dark</span></div></div>'
             '<div style="color-scheme:light"><div role="dialog" class="anti-light-panel">'
             '<span class="it">祖先声明 light</span></div></div>')
    # 同一棵 dark 树下的常驻条（2026-10-04 分支契约分裂的另一半）：类名逐字取自
    # github.com/features 页头那一横（div.MarketingHeader-module__bar__mBSyE，40px 高，
    # 被 header 那截词根按子串追上），它的祖先 <header> 与外面那层 div 都带着
    # data-color-mode="dark"，primer-*.css 里 [data-color-mode="dark"][data-dark-theme*="dark"]
    # 把这两处都写成 color-scheme: dark。条不钉档，所以它必须跟着这一棵树翻成夜晚那套，
    # 而上面那块 anti-dark-panel 必须顶住不翻——两格读数是反的，一把尺量不到另一把。
    h.append('<div style="color-scheme:dark"><div class="anti-dark-bar '
             'MarketingHeader-module__bar__mBSyE"><span class="it">深色区域里的条</span>'
             '</div></div>')
    # 面内搜索壳那三枚（#132 的计算样式证人）：探针页是 check-controls.py 自己拼的 HTML，
    # 不是 preview/components.html（那本归像素闸门用），所以证人往这里加。
    # 外面那层 div 用 role="dialog" 落进玻璃族；里面两枚壳一枚真住控件、一枚只住 span；
    # 第三枚同样类名但不在任何面里。input 刻意 type="search"：聚焦环那一格按
    # input[type="text"] 抓文档里第一个，别把它抢走。
    h.append('<div role="dialog" class="ks-shell-face Box--overlay">'
             '<div class="quick-search-input-module__searchContain__X1" style="background:#ffffff">>'
             '<input type="search" placeholder="面内·有控件"></div>'
             '<div class="quick-search-input-module__searchContain__X2" style="background:#ffffff">>'
             '<span>面内·没有控件</span></div>'
             '</div>'
             '<div class="quick-search-input-module__searchContain__X3" style="background:#ffffff">>'
             '<input type="search" placeholder="面外·有控件"></div>')
    # 面里的控件底那一格（#135）的三枚证人，挂在同一块面上：
    # 正＝面里的裸控件，底必须是透明（透出自家面，站点排在控件底下的镜像才看得见）；
    # 反 A＝面里、控件自己写了作者底的一枚，必须留着站点那块绿——这一支刻意不带 !important，
    #   按 Cascade 4 站点普通声明排在我们的普通声明之上，补上 !important 就是把 #112 亲手造出来；
    # 反 B＝面外的控件照旧吃 §4 的画布底，那一格由 RO 表里 input[type="text"] 那几行举着
    #   （选择器摘掉面祖先时红的就是它们）。
    h.append('<div role="dialog" class="ks-inface"><input class="ksFaceIn" type="search">'
             '<input class="ksFaceSiteIn" type="search" style="background:#1a7f37"></div>')

    h.append('<pre id="out"></pre><script>(function(){'
             'function grab(sel,pe){var e=(typeof sel==="object")?sel:document.querySelector(sel);'
             'if(!e) return null; var s=getComputedStyle(e,pe||null); return {'
             'bw:s.borderTopWidth,bs:s.borderTopStyle,bc:s.borderTopColor,'
             'bb:s.borderBlockEndWidth,bbc:s.borderBlockEndColor,'
             'bi:s.borderInlineStartWidth,bis:s.borderInlineStartStyle,bic:s.borderInlineStartColor,'
             'ol:s.outlineColor,bf:s.backdropFilter,'
             'bg:s.backgroundColor,fg:s.color,tf:s.webkitTextFillColor,'
             'sh:s.textShadow,'
             'ac:s.accentColor,op:s.opacity,'
             'cu:s.cursor,w:s.width,h:s.height};}'
             'var RO=[];')
    for t in TEXT_TYPES + EXCLUDED_TYPES:
        h.append(f'RO.push(["{t}",grab(\'input[type="{t}"]:not([readonly])\'),'
                 f'grab(\'input[type="{t}"][readonly]\')]);')
    h.append('RO.push(["(no type)",grab("input:not([type]):not([readonly])"),'
             'grab("input:not([type])[readonly]")]);')
    h.append('var out={ro:RO, box:{}, acc:{}, dis:{}};')
    for name, sel in BOX_CONTROLS.items():
        h.append(f'out.box[{json.dumps(name)}]=grab({json.dumps(sel)});')
    h.append('out.box["file-btn"]=grab(\'input[type="file"]\', "::file-selector-button");')
    for name, sel in ACCENTED.items():
        h.append(f'out.acc[{json.dumps(name)}]=(grab({json.dumps(sel)})||{{}}).ac||"";')
    for name, sel in DISABLEABLE.items():
        h.append(f'out.dis[{json.dumps(name)}]=grab({json.dumps(sel)});')
    h.append('out.style={};')
    for key, (sel, pe) in STYLE_PROBE.items():
        h.append(f'out.style[{json.dumps(key)}]=grab({json.dumps(sel)},'
                 f'{json.dumps(pe or "")});')
    h.append('out.ksyield={};')
    for name, (tag, cls, _, _) in (list(YIELD.items()) + list(NOTROOTS.items())
                                   + list(MIDTOKEN.items()) + list(NESTED.items())
                                   + list(IDEXCL.items()) + list(MAINYIELD.items())
                                   + list(BODYROOTS.items()) + list(HEADEXCL.items())):
        h.append(f'out.ksyield[{json.dumps(name)}]=grab({json.dumps(f"{tag}.{cls}")});')
    # 聚焦环要在"刚聚焦"那一刻取；showModal 会把焦点抢走，所以它排在地表探测之前。
    # 计算样式按元素直取，不按 input:focus 取：那一截伪类要等一次样式更新才匹配得上，
    # 而"环亮没亮"已经由 out.mfv／out.act 各自断言，多一层伪类匹配只会多一种假红。
    h.append('var inp=document.querySelector(\'input[type="text"]\');'
             'inp.focus();out.focus=grab(inp);'
             'out.mfv=inp.matches(":focus-visible");'
             'out.act=(document.activeElement===inp);'
             'out.sel=!!document.querySelector("input:focus");inp.blur();')
    h.append('out.option=grab("option:not(:checked)");'
             'out.optionChecked=grab("option:checked");'
             'out.optgroup=grab("optgroup");'
             'out.html=grab("html");'
             'var d=document.getElementById("dlg"); d.showModal();'
             'out.backdrop=grab("dialog", "::backdrop");'
             'document.getElementById("out").textContent="CTRL "+JSON.stringify(out);'
             '})();</script></body></html>')
    BUILD.parent.mkdir(exist_ok=True)
    BUILD.write_text("".join(h), encoding="utf-8")
    return BUILD


def run(page):
    r = subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
         "--window-size=1280,900", "--virtual-time-budget=6000",
         "--allow-file-access-from-files", "--dump-dom", f"file://{page}"],
        capture_output=True, text=True)
    m = re.search(r"CTRL (\{.*?\})</pre>", r.stdout, re.S)
    if not m:
        die(f"探针没跑起来（或 --dump-dom 早于脚本执行）；退出码 {r.returncode}："
            f"{r.stderr.strip()[:200]}")
    # 退出码在这里不是判据：量过，共驻负载高时（load 131、可用内存 85 MB 那一档）同一条命令
    # 六跑里有一跑 rc=2，而 stdout 里那串 CTRL JSON 是完整的。JSON 由页尾脚本在**所有** grab
    # 之后才写，它在了就证明探针跑到了底；反过来按 rc 判死，会把"读到了"报成"读不到"，
    # 而 knives.py 那边会把它记成 BASELINE-RED——归因就此落到没跑过的刀上。
    if r.returncode != 0:
        # 刻意不回抄 stderr 首行：那一句含 "ERROR:" 字样，而 knives.py 的 reds() 把带
        # ERROR 的行当红线收——把机器的噪音印进判定输出，等于给期望串多造一种撞上的可能。
        print(f"CTRL WARN: dump-dom 退出码 {r.returncode}，读数完整——收尾崩，不是探针崩"
              f"（stderr 另有 {len(r.stderr.splitlines())} 行，未打印）", file=sys.stderr)
    return json.loads(m.group(1))


# color-mix() 的形状只在 check-contrast.py 里解释一遍（两本闸门共用同一条正则）
MIX_RE = GATE.MIX_RE
VAR_RE = re.compile(r"var\(--ks-([\w-]+)\)")


def token_val(tokens, sakura, name, branch, who):
    if name == "sakura":
        return sakura
    if name not in tokens:
        die(f"{who} 引用了 --ks-{name}，token 表里没有这一档，期望值算不出来")
    return tokens[name][branch]


def ld_two(decl, who):
    """light-dark(A, B) → (A, B)；按顶层逗号切，括号内的逗号不算。"""
    inner = decl.strip()
    inner = re.sub(r"\s*!\s*important\s*$", "", inner)
    if not inner.startswith("light-dark(") or not inner.endswith(")"):
        die(f"{who}：{inner!r} 不是 light-dark(...) 那一形")
    depth, parts, cur = 0, [], ""
    for ch in inner[len("light-dark("):-1]:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    parts.append(cur.strip())
    if len(parts) != 2:
        die(f"{who}：light-dark 的参数不是恰好两支（解出 {len(parts)} 支）")
    return parts


def edge_layers(txt):
    """计算样式里的 text-shadow → [(颜色串, [x, y, 半径]…)，…]；"none" 给空表，读不出给 None。

    按顶层逗号切层（rgba(...) 里的逗号不算层边界），每层剥出颜色前缀和剩下的 px 长度。
    层的顺序由浏览器序列化决定，不假设颜色在左还是在右：只认「一段颜色 + 三个长度」，
    形状对不上就返回 None 让调用方 die——这一列静默跳过比红掉更贵。
    """
    t = (txt or "").strip()
    if t == "none":
        return []
    depth, cur, raw = 0, "", []
    for ch in t:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            raw.append(cur)
            cur = ""
        else:
            cur += ch
    raw.append(cur)
    out = []
    for layer in raw:
        # 颜色前缀不能按「不含数字」认：这版 Chrome 把 light-dark() 解出来的透明写成
        # color(srgb 0 0 0 / 0)，里面全是数字。改成从右锚定认三枚 px 长度，剩下的整段算颜色。
        m = re.match(r"\s*(.+?)\s+-?[\d.]+px\s+-?[\d.]+px\s+-?[\d.]+px\s*$", layer)
        if not m:
            return None
        lens = [float(x[:-2]) for x in re.findall(r"-?[\d.]+px", layer)]
        out.append((m.group(1).strip(), lens))
    return out


def css_expect(src, tokens, sakura, gate):
    """把 SPECS 每一条"该画成什么色"从 CSS 里解出来 → {(档, 名字): ((r,g,b), α)}。

    混色比例和参与混色的 token 名都只住在 CSS 里：换配色不用改脚本，
    脚本也不会替 CSS 撒谎（期望值由声明现推，抄来的 hex 会跟着 CSS 一起烂）。
    """
    want = {}
    for name, anchor, prop, key, field in SPECS:
        full = r"(?<![-\w])" + anchor + r"([^}]*)\}"
        blocks = re.findall(full, src, re.S)
        if len(blocks) != 1:
            die(f"{name}：CSS 里锚点 {anchor!r} 命中 {len(blocks)} 处，应当恰好 1 处，"
                f"不知道照着哪一条算期望值")
        val = re.search(r"(?<![-\w])" + re.escape(prop) + r"\s*:\s*([^;]+);", blocks[0])
        if not val:
            die(f"{name}：那条规则块里没有 {prop} 声明，判据跟 CSS 对不上")
        decl = val.group(1)
        mm = MIX_RE.search(decl)
        if mm:
            if mm.group(2) is not None:
                pct = float(mm.group(2)) / 100.0
            elif mm.group(3) is not None:
                pct = float(mm.group(3)) / 100.0
            else:
                # calc(100% - 开关 * N%)：玻璃那两格。闸门跑的是默认档（开关=1），
                # 所以这一格的 alpha 就是 1-N%；写反了会量到一个"哪儿都不差"的假值
                pct = 1.0 - float(mm.group(4)) / 100.0
            base = mm.group(6) or "transparent"
            for b in ("light", "dark"):
                c = token_val(tokens, sakura, mm.group(1), b, name)
                if base == "transparent":
                    want[(b, name)] = (c, pct)
                else:
                    want[(b, name)] = (gate.wash(
                        token_val(tokens, sakura, base, b, name), c, pct), 1.0)
            continue
        if decl.strip().startswith("light-dark("):
            for b, arg in zip(("light", "dark"), ld_two(decl, name)):
                mv2 = VAR_RE.search(arg)
                if mv2:
                    want[(b, name)] = (token_val(tokens, sakura, mv2.group(1), b, name), 1.0)
                    continue
                rr, aa = rgb(arg)
                if rr is None:
                    die(f"{name}：light-dark 的 {b} 支 {arg!r} 既不是 var(--ks-*) "
                        f"也不是解得开的颜色，期望值算不出来——判据要跟着改")
                want[(b, name)] = (rr, aa)
            continue
        mv = VAR_RE.search(decl)
        if not mv:
            die(f"{name}：{prop} 的值 {decl.strip()!r} 既不是 var(--ks-*) 也不是 "
                f"color-mix(...) 这个形状，期望值算不出来——判据要跟着改")
        for b in ("light", "dark"):
            want[(b, name)] = (token_val(tokens, sakura, mv.group(1), b, name), 1.0)
    return want


def check_styles(res, want, branch, label):
    """逐条比对：CSS 说该画成什么，计算样式就得是什么。"""
    missing, wrong = [], []
    for name, anchor, prop, key, field in SPECS:
        got = (res.get(key) if key in SPECIAL else res["style"].get(key)) or {}
        txt = got.get(field)
        if not txt:
            missing.append(f"{name}（{key}·{field}）")
            continue
        gr, ga = rgb(txt)
        if gr is None:
            missing.append(f"{name} 的颜色读不出（实测 {txt!r}）")
            continue
        wr, wa = want[(branch, name)]
        if not close(gr, wr) or abs(ga - wa) > 0.02:
            # 期望值那三个分量从 token 现推，light-dark()/color-mix 解出来是浮点，
            # '%02x' 只收整数——红的时候在这里抛 TypeError，等于把要报的那一句吞掉
            # （2026-10-04 新加的那行第一次红就撞上了，闸门死在打印上而不是死在判定上）
            wrong.append(f"{name} 实测 {txt}，期望 "
                         f"#{'%02x%02x%02x' % tuple(int(round(c)) for c in wr)} α={wa:.2f}")
    if missing:
        die(f"{label} 探针取不到这些判定对象 {missing}——夹具少了元素，"
            f"这些条会静默跳过")
    if wrong:
        fails.append(f"{label} 着色与声明不符：" + "；".join(wrong))


def check(branch, res, tokens, tint, tint_pct, want, glass_px):
    label = "白天" if branch == "light" else "夜晚"
    want_border = tokens["border"][branch]

    # 皮肤到底加载了没：html 的底色是 !important 的 token，裸页上是透明的
    html_bg, _ = rgb(res["html"]["bg"])
    if not close(html_bg, tokens["canvas-1"][branch]):
        die(f"{label}：html 底色不是 canvas-1 token（实测 {res['html']['bg']}）——"
            f"探针页的 skin.css 没加载，下面全部判定都是空的")

    bad = [n for n, v in res["box"].items() if v is None]
    if bad:
        die(f"{label}：夹具里找不到这些控件 {bad}，判定会静默跳过")
    off_border = []
    for n, v in res["box"].items():
        if v["bw"] != "1px" or "solid" not in v["bs"]:
            off_border.append(f"{n} 边框 {v['bw']}/{v['bs']}")
        elif not close(rgb(v["bc"])[0], want_border):
            off_border.append(f"{n} 边框色 {v['bc']}")
    if off_border:
        fails.append(f"{label} 盒控件边框不统一：" + "；".join(off_border))

    # 按钮面和文件钮面必须是同一个色。CSS 里两处都引用 --ks-btn，所以上面那两条 SPECS
    # 都跟着 CSS 重新折期望值——单独动了其中一处时两行各自仍绿，只有这条对账会红。
    # （同一排里 <input type=file> 那个"选择文件"比别的按钮淡一档，就是这一格。）
    fb_bg = rgb(res["style"]["filebtn"]["bg"])[0]
    bt_bg = rgb(res["style"]["btn_face"]["bg"])[0]
    if not close(fb_bg, bt_bg):
        fails.append(f"{label} 文件钮底 {res['style']['filebtn']['bg']} 与按钮底 "
                     f"{res['style']['btn_face']['bg']} 不是同一色")

    tinted, leaked = [], []
    want_tint = tint[branch]
    for t, plain, ro in res["ro"]:
        if plain is None or ro is None:
            die(f"{label}：type={t} 的只读/非只读配对缺一个，判据不成立")
        is_text = t in TEXT_TYPES or t == "(no type)"
        if close(rgb(ro["bg"])[0], want_tint):
            (tinted if is_text else leaked).append(t)
    if leaked:
        fails.append(f"{label} 只读粉底漏给了非文本类型 {leaked}——"
                     f"Chrome 让 :read-only 匹配所有 input，排除列表少了项")
    missing_tint = [t for t in TEXT_TYPES + ["(no type)"] if t not in tinted]
    if missing_tint:
        fails.append(f"{label} 文本类只读字段没拿到底色 {missing_tint}——只读档没生效")

    accs = {k: v for k, v in res["acc"].items()}
    auto = [k for k, v in accs.items() if v in ("auto", "normal", "")]
    if auto:
        fails.append(f"{label} 这些控件没拿到 accent-color：{auto}（会是系统蓝）")
    if len(set(accs.values())) > 1:
        fails.append(f"{label} accent-color 不一致：{sorted(set(accs.values()))}——"
                     f"应当由同一个强调色驱动")

    miss = [k for k, v in res["dis"].items() if v is None]
    if miss:
        die(f"{label} 夹具里没找到禁用态控件 {miss}，这一项判不了")
    weak = [k for k, v in res["dis"].items()
            if float(v["op"]) >= 1.0 or v["cu"] != "not-allowed"]
    if weak:
        fails.append(f"{label} 禁用态缺信号：{weak}（应同时有降透明度和 not-allowed 光标）")

    for key, what in (("option", "选项"), ("optionChecked", "选中项"),
                      ("optgroup", "分组标题"), ("backdrop", "弹窗遮罩")):
        if res[key] is None:
            die(f"{label} 夹具里没有{what}（{key}），这一项判不了")

    if alpha_of(res["option"]["bg"], "option 底色", label) == 0.0:
        fails.append(f"{label} option 底色透明——下拉面板会退回系统白底")
    if rgb(res["option"]["bg"])[0] == rgb(res["option"]["fg"])[0]:
        fails.append(f"{label} option 字色与底色同值，面板里的选项读不出来")
    if res["optionChecked"]["bg"] == res["option"]["bg"]:
        fails.append(f"{label} 面板里选中项和未选中项同色，高亮那档没生效")
    if alpha_of(res["optgroup"]["fg"], "optgroup 标题色", label) == 0.0:
        fails.append(f"{label} optgroup 标题色透明")
    backdrop_a = alpha_of(res["backdrop"]["bg"], "dialog::backdrop 底色", label)
    if backdrop_a == 0.0:
        fails.append(f"{label} dialog::backdrop 完全不遮挡——弹窗会和页面糊在一起")

    # 族的反面：类名带词根（或被词根子串撞上）的控件、导航条、吸顶容器，
    # 必须原样留着站点那块底、且没被糊上虚焦
    noyield = []
    for why, table in ((WHY["yield"], YIELD),
                       (WHY["roots"], NOTROOTS),
                       (WHY["mid"], MIDTOKEN),
                       (WHY["nested"], NESTED),
                       (WHY["id"], IDEXCL),
                       (WHY["main"], MAINYIELD),
                       (WHY["body"], BODYROOTS),
                       (WHY["heading"], HEADEXCL)):
        for name, (_, _, _, site) in table.items():
            v = res["ksyield"].get(name)
            if v is None:
                die(f"{label} 探针里没有 {name}（类名带词根的控件/导航条），"
                    f"排除式与词根名册那一条判不了")
            got_bg = rgb(v["bg"])[0]
            bf = (v["bf"] or "none").strip()
            if table is HEADEXCL:
                # 标题形那一块自 2026-10-06 起由 §4 的圆角底上色：这一格的判据换成
                # 「不穿玻璃 + 底色不再是站家排的那块」，两向各有证人——圆角底被摘则底退回
                # #f6f8fa，族末尾那道 :not(h1…h6) 被割掉则虚焦不再是 none。
                if bf != "none" or close(got_bg, site):
                    noyield.append(f'{name}{why} 实测底 '
                                   f'#{"%02x%02x%02x" % got_bg if got_bg else "??????"}'
                                   f'（站点排的是 #{"%02x%02x%02x" % site}）、虚焦 {bf}'
                                   f'——标题形这一格判的是「不穿玻璃、且吃上 §4 的圆角底」：'
                                   f'虚焦非 none＝玻璃族溢到标题上，底等于站家那块＝圆角底被摘')
                continue
            if not close(got_bg, site) or bf != "none":
                noyield.append(f'{name}{why} 实测底 '
                               f'#{"%02x%02x%02x" % got_bg if got_bg else "??????"}'
                               f'（站点排的是 #{"%02x%02x%02x" % site}）、虚焦 {bf}')
    if noyield:
        fails.append(f"{label} {OVERFLOW}：" + "；".join(noyield) +
                     "——要么族末尾的 :not() 少了项，要么 navbar/header 这两截"
                     "被普查判过「不追」的词根被加了进来，要么 topnav 那几截词边界形式"
                     "被退回了对类名中间的子串也认的匹配，要么族开头那道 body 排除被摘掉")

    # 常驻条下那枚控件的面：CSS 里写的是字面量 transparent，期望值解析器只认
    # var(--ks-*) 与 color-mix(...) 两形，所以这一格按"站点那块蓝底必须不见"直判，
    # 并由条外那枚同类名控件配对证明蓝底确实排上了（作者底没加载时两块一起红，
    # 不会只剩一个假透明把这一格举绿）。
    for _k, _where in (("chrome_bar_btn", "条下"), ("chrome_bar_out_btn", "条外")):
        if res["style"].get(_k) is None:
            die(f"{label} 探针里没有 {_k}（常驻条那枚控件·{_where}），让面那一格判不了")
    _in_bg = res["style"]["chrome_bar_btn"]["bg"]
    _out_rgb = rgb(res["style"]["chrome_bar_out_btn"]["bg"])[0]
    if _out_rgb is None:
        die(f"{label} 条外那枚控件的底色读不出（实测 "
            f'{res["style"]["chrome_bar_out_btn"]["bg"]!r}）——探针没落进文档？')
    if not close(_out_rgb, BARBTN_SITE):
        fails.append(f"{label} 条外那枚控件没拿到站点排的蓝底（实测 "
                     f'{res["style"]["chrome_bar_out_btn"]["bg"]}，作者声明是 '
                     f'#{"%02x%02x%02x" % BARBTN_SITE}）——配对断了，条下那格的透明读数不算数')
    elif alpha_of(_in_bg, "常驻条上的控件底色", label) != 0.0:
        fails.append(f"{label} 常驻条上的控件没让回透明面：实测底 {_in_bg}——"
                     f"条那一支的 background-color 声明被摘掉了，"
                     f"站点那块实心底会压在自家粉条上")

    # 条那一支（裸链接形）越没越到条外面去：那一支把词根抄了第二遍，族开头那道
    # :not(body, html) 管不到它，而夹具的 <body> 挂着真站原文的 header-dark。
    # 期望值是站点自己那行带 !important 的绿——它不来自 CSS，所以这一格只能直判，
    # 不进 SPECS（进了就得替一个"期望值从被试规则现推"的解析器编第三种形状）。
    if res["style"].get("body_link") is None:
        die(f"{label} 探针里没有 body_link（条外的正文链接），"
            f"条那一支的 body 排除那一格判不了")
    _link_fg = res["style"]["body_link"]["fg"]
    _link_rgb = rgb(_link_fg)[0]
    if _link_rgb is None:
        die(f"{label} 条外那枚正文链接的字色读不出（实测 {_link_fg!r}）——"
            f"{BODYLINK[1]} 探针没落进文档还是被 display:none 收了？")
    if not close(_link_rgb, BODYLINK_SITE):
        fails.append(f"{label} 条外那枚正文链接被条那一支上墨了：实测字色 {_link_fg}，"
                     f'站点排的是 #{"%02x%02x%02x" % BODYLINK_SITE}——'
                     f"a[href] 那一支末尾的 :not(body, html) 被摘掉了，"
                     f"<body> 挂着 header-dark 时「常驻条之下」就成了「整页之下」")

    # 链接那一圈描边（2026-10-11 修「文字看不清」那一族落的那一刀）。三条关系各有各的方向，
    # 少一条就会放走一种错法：
    #   ① 白天那一支必须是透明的：撞色那 5 行全在夜档（浅墨压站家浅底），白天这一边没量到
    #      读者；而白档描边取的是画布那支浅色，等于吃掉深色字的外沿一圈——没有证人不画。
    #      出图 A/B 量到白天整幅 0 格改动，这一格把它从一次性对照升级成常驻断言。
    #   ② 夜档那一圈的颜色必须等于 canvas-1：这圈的意义是「让底下那块画布透过来」，
    #      换成别的亮度就是凭空多一枚颜色，会重演 §99 那条「强调太突兀」的旧账。
    #      期望值走 tokens 表（解的是 --ks-canvas-1 那一行），不读 a{} 这一块 ⇒ 割块里的声明
    #      只会动实测、不动期望，这一格才归得清。
    #   ③ 半径必须是 0、偏移必须恰好是上下左右各 1px 的四枚：模糊那形（§99 换掉的旧机制）
    #      会把 1–2px 宽的中文笔画一起吃掉，2× 看图发虚，legibility 还多出一行 1.1。
    _edge_txt = res["style"]["body_link"].get("sh")
    if _edge_txt is None:
        die(f"{label} 探针里没有链接的 text-shadow（grab 少了 sh 那一列），"
            f"描边这一格会静默跳过")
    _lay = edge_layers(_edge_txt)
    if _lay is None:
        die(f"{label} 链接描边读不出（实测 {_edge_txt!r}）——"
            f"浏览器序列化形状跟判据假设不符，判据要跟着改")
    if len(_lay) == 0:
        fails.append(f"{label} 链接描边整条没了：实测 text-shadow={_edge_txt!r}，"
                     f"应当是四枚硬边——a{{}} 里那条 --ks-edge 或 text-shadow 被摘掉了")
    elif any(len(l) != 3 or l[2] != 0.0 for _, l in _lay):
        fails.append(f"{label} 链接描边的半径不是 0：实测 {_edge_txt!r}——"
                     f"模糊那形会把 1–2px 宽的中文笔画一起吃掉，§99 已经否过一次")
    elif len(_lay) != 4 or sorted(tuple(l[:2]) for _, l in _lay) != [(-1.0, 0.0),
                                                                     (0.0, -1.0),
                                                                     (0.0, 1.0),
                                                                     (1.0, 0.0)]:
        fails.append(f"{label} 链接描边不是「上下左右各 1px」的四枚硬边：实测 {_edge_txt!r}——"
                     f"少一枚方向就有一侧没有衬底，多一枚会把字挤粗")
    _want_edge = tokens["canvas-1"][branch]
    _bad_edge = []
    for _col, _ in _lay:
        _cr, _ca = rgb(_col)
        if _cr is None:
            die(f"{label} 链接描边的颜色读不出（实测 {_col!r}）——"
                f"序列化里出现了不认识的形状，判据要跟着改")
        if branch == "light":
            if _ca != 0.0:
                _bad_edge.append(f"{_col}（α={_ca:.2f}）")
        elif not close(_cr, _want_edge) or abs(_ca - 1.0) > 0.02:
            _we = '%02x%02x%02x' % tuple(int(round(c)) for c in _want_edge)
            _bad_edge.append(f"{_col}，期望 #{_we}")
    if _bad_edge:
        if branch == "light":
            fails.append(f"{label} 链接描边的白天那一支不该有边：实测 "
                         f"{'；'.join(_bad_edge)}——"
                         f"light-dark 的第一支被换成了实色，整页链接会多画一层"
                         f"（出图 A/B 量到的「白天 0 格改动」就是这一格）")
        else:
            fails.append(f"{label} 链接描边夜档那一圈不是 canvas-1：实测 "
                         f"{'；'.join(_bad_edge)}——"
                         f"这圈的意义是让底下的画布透过来，换亮度就成了凭空多一枚颜色")

    # 深色区域里那根常驻条跟着区域翻（2026-10-04 分支契约分裂的另一半）。
    # 期望值不另抄颜色：取 FACE 那条现推出来的**暗档**读数，两档跑的都是同一个期望——
    # 这正是这一格要问的：面板档在白天，条也得是夜晚那套面与墨，因为它坐在一棵声明了
    # dark 的树下。反面证人就是上面那两块 anti-*-panel（同一棵树下的浮动面必须顶住不翻），
    # 而"站点没表过态时条跟着面板档"那一格由 玻璃面 navbar／header 那两行举着。
    for _k, _field, _wkey, _what in (
            ("anti_dark_bar", "bg", ("dark", "玻璃面底色"), "面"),
            ("anti_dark_bar_child", "fg", ("dark", "玻璃后代字色"), "墨")):
        got = (res["style"].get(_k) or {}).get(_field)
        if not got:
            die(f"{label} 探针里没有 {got!r}（深色区域里那根常驻条的{_what}），"
                f"条跟着区域翻那一格判不了")
        gr, ga = rgb(got)
        wr, wa = want[_wkey]
        if gr is None or not close(gr, wr) or abs(ga - wa) > 0.02:
            fails.append(f"{label} 常驻条跟着区域翻：{_what}实测 {got}，期望 "
                         f"#{'%02x%02x%02x' % tuple(int(round(c)) for c in wr)} α={wa:.2f}"
                         f"——钉档那条的范围又扩到了常驻条的词根上，或者面块被重新加回了 "
                         f"color-scheme，条在深色区域里会披上白天那层粉")


    # 面内搜索壳那两枚反面证人（#132）：一枚在面里但里面没有控件（:has 落空），
    # 一枚有控件但不在任何面里（面祖先落空）。两枚都必须原样留着站家那块白——
    # 摘掉 :has 或摘掉面那一截时，红的就是这里，而不是正面那一格（正面照样被画上）。
    for _k, _where in (("shell_no_ctrl", "面内搜索壳反面(没控件)"),
                       ("shell_out_face", "面外搜索壳反面")):
        got = (res["style"].get(_k) or {}).get("bg")
        if not got:
            die(f"{label} 探针里没有 {got!r}（{_where}），夹具少了那一块还是被 display:none 收了？")
        gr, _ga = rgb(got)
        if gr is None or not close(gr, SHELL_SITE):
            fails.append(f"{label} {_where}被画上面了：实测 {got}，站点排的是 "
                         f"#{'%02x%02x%02x' % SHELL_SITE}——那一支的 :has(...) 结构条件"
                         f"或面祖先被摘掉了，凡是带 search/input 类名的壳都会被垫一块底")

    # 关系形证人（#140）：壳跟它衬的那块面必须**看得见地**分开。
    # 上面那格 shell_in_face 是计算样式对账，期望值和实测值从同一句 CSS 现推 ⇒
    # 把白天枝改回 rgba(0,0,0,0) 时两边一起变成 transparent，那一格照样绿，
    # 可渲染出来是"壳＝面"（2026-10-10 落地前那张夹具图就是这个状态：分离 1.000:1）。
    # 这里不比色值，比的是"壳压出来的底"与"壳底下那块面压出来的底"逐通道差多少。
    # 面是半透明的，它真正衬的页面底没被这一格量过 ⇒ 只取两个端点当最坏情况：
    # 面叠在自家纸上一遍（就近那一端）与面 token 自己（叠到无穷深那一端），
    # 合成沿层单调 ⇒ 最小值必落在端点上，不需要知道嵌套了几层（#142 因此不欠）。
    _frgb, _fa = want[(branch, "玻璃面底色")]
    _srgb, _sa = want[(branch, "面内搜索壳底")]
    _base = tokens["canvas-1"][branch]

    def _flat(top, top_a, under):
        return tuple(top_a * t + (1 - top_a) * u for t, u in zip(top, under))

    def _sep(gnd):
        return max(abs(a - b) for a, b in zip(_flat(_srgb, _sa, gnd), gnd))

    _near = tuple(_fa * f + (1 - _fa) * b for f, b in zip(_frgb, _base))
    _worst = min(_sep(_near), _sep(_frgb))
    _floor = SHELL_SEP_MIN[branch]
    print(f"  {label} 壳/面 最坏分离 {_worst:.1f}/255（地板 {_floor}，α_面={_fa:.2f} "
          f"α_壳={_sa:.2f} 就近底 {tuple(round(v, 1) for v in _near)}）")
    if _worst < _floor:
        fails.append(f"{label} 面内搜索壳跟它衬的面看不见分开：最坏分离 {_worst:.1f}/255 < {_floor}。"
                     f"壳底被改回透明（或与面同一支 token）时，落在玻璃面里的输入框就没有边界了——"
                     f"计算样式那一格对这一形是沉默的，因为它两边的值出自同一句 CSS")

    # 面里的控件底那一格（#135）：正证人必须**透**（α=0），反面证人必须留着站点那块绿。
    # 两柄刀一头一尾——K43 摘声明（正证人红）、K44 补 !important（反证人红）。
    _fin = (res["style"].get("face_in") or {}).get("bg")
    if _fin is None:
        die(f"{label} 探针里没有 face_in 的读数（面里的裸控件），夹具少了 .ks-inface 那块？")
    _gr, _ga = rgb(_fin)
    if _ga != 0:
        fails.append(f"{label} 面里的控件自己垫了底：实测 {_fin}，期望透明（α=0）——"
                     f"这一块底会把站点排在控件**底下**的镜像整个盖住，框里一个字都不剩"
                     f"（2026-10-10 登录态 github.com 快搜那一格就是这么读的：夜 0 格墨／最大 1.66）")
    _site = (res["style"].get("face_in_site") or {}).get("bg")
    if _site is None:
        die(f"{label} 探针里没有 face_in_site 的读数（面里、控件自己写了底的反面证人）")
    _sr, _sa = rgb(_site)
    if _sr is None or not close(_sr, FACE_IN_SITE) or _sa != 1:
        fails.append(f"{label} 面里控件的「站点自己写的底」被我们扳掉了：实测 {_site}，"
                     f"站点排的是 #{'%02x%02x%02x' % FACE_IN_SITE}——那一支一旦带上 "
                     f"!important，我们的墨就会压在站家的底上（w3schools 顶栏那枚搜索框"
                     f"夜档量到 1.16），也就是 #112 那一形由我们亲手造出来")

    check_styles(res, want, branch, label)

    # 虚焦那一格不是颜色，check_styles 够不着：半径从 §1 的 token 现推，
    # 于是"改了 token 忘了改这里"和"token 被某档媒体查询整个顶掉"两种漂法都看得见
    bf = (res["style"]["dialog"] or {}).get("bf") or ""
    if f"blur({glass_px})" not in bf:
        fails.append(f"{label} 玻璃面没拿到 §1 声明的那档虚焦：backdrop-filter 实测 "
                     f"{bf!r}，期望含 blur({glass_px})")

    # :focus-visible 在无头里到底亮没亮，必须先确认，否则聚焦环那条是在拿 :focus 冒充它
    if not res.get("mfv") or not res.get("act"):
        die(f"{label} 程序化 focus 没点亮 :focus-visible，聚焦环这一项判不了"
            f"（mfv={res.get('mfv')} activeElement 命中那块输入={res.get('act')}）")
    if res.get("sel") is False:
        # 只在旧写法会假红的那一格留一行：伪类这一拍没匹配上，而环是亮的、读数是按元素取的
        print(f"{label} 记录：那一次 input:focus 伪类没匹配上（环亮，读数直取元素）")
    if alpha_of(res["style"]["zebra_odd"]["bg"], "斑马奇行底色", label) != 0.0:
        fails.append(f"{label} 斑马纹的奇行也有底色（{res['style']['zebra_odd']['bg']}）——"
                     f"那是整张表被涂了一遍，不是分行交替")
    if "blur" not in (res["backdrop"].get("bf") or ""):
        fails.append(f"{label} 遮罩没挂上虚焦（backdrop-filter 实测 "
                     f"{res['backdrop'].get('bf')!r}）")

    # 遮罩的各形必须同档。真站上遮罩的类名词根不止 backdrop 一种：GitHub/Primer 写作
    # backdrop×dialog，Vue 套件写作 dialog--mask，京东写作 popup_mask（2026-10-03 在反代
    # 缓存的四份样式表里量到的原文）。::backdrop 结构上够不着它们，所以每一形都要自己
    # 接到同一份底色与虚焦上——这一格比的是"各形拿到的是不是同一份底"，两形各写一档也会红。
    # ×modal 那两形不在这里出现：玻璃族带 [class*="modal"] 且声明是 !important，遮罩这条不是，
    # 同一元素上玻璃会赢，测它只能测出规则次序、测不出遮罩接没接到。
    # 反面那三枚钉的是"裸词根不收"：收了就把面板当遮罩涂黑。
    for key, name in (("csb", "backdrop 那形"), ("csc", "mask×dialog 那形"),
                      ("csd", "mask×popup 那形")):
        el = res["style"].get(key)
        if el is None:
            die(f"{label} 夹具里没有 {name}遮罩（{key}），这一项判不了")
        a = alpha_of(el["bg"], f"{name}遮罩底色", label)
        if a == 0.0:
            fails.append(f"{label} {name}遮罩完全不遮挡——弹窗会和页面糊在一起")
        if not close(rgb(el["bg"])[0], rgb(res["backdrop"]["bg"])[0]) or abs(a - backdrop_a) > 0.02:
            fails.append(f"{label} 遮罩各形不同档：::backdrop 实测 {res['backdrop']['bg']}、"
                         f"{name}实测 {el['bg']}")
        if "blur" not in (el.get("bf") or ""):
            fails.append(f"{label} {name}遮罩没挂上虚焦（backdrop-filter 实测 {el.get('bf')!r}）")
    for key, name in (("csn_overlay", "GitHub 形 .Overlay 面板"),
                      ("csn_wechat", "京东形 .wechat_overlay 白底"),
                      ("csn_mask", "裸 mask 词根")):
        el = res["style"].get(key)
        if el is None:
            die(f"{label} 夹具里没有 {name}那枚反面（{key}），裸词根收不收这一项判不了")
        if alpha_of(el["bg"], f"{name}底色", label) != 0.0 or (el.get("bf") or "none") != "none":
            fails.append(f"{label} 裸词根那形被当遮罩压暗了（底色 {el['bg']}、"
                         f"虚焦 {el.get('bf')!r}）——那一形多半是面板本体或站家的浅底，"
                         f"收进遮罩就是涂黑一块能读的东西")

    lb = res["style"].get("linkbtn")
    if lb is None:
        die(f"{label} 夹具里没有那颗站点自涂白的链接按钮（linkbtn），这一项判不了")
    if not close(rgb(lb["bg"])[0], rgb(res["style"]["btn_face"]["bg"])[0]):
        fails.append(f"{label} 站点写 !important 的链接按钮没拿到统一的面："
                     f"实测 {lb['bg']}，那颗真按钮是 {res['style']['btn_face']['bg']}")
    pl = res["style"].get("primer_label")
    if pl is None:
        die(f"{label} 夹具里没有那颗「墨排在孙节点」的链接按钮（primer_label），这一项判不了")
    if not close(rgb(pl["tf"])[0], rgb(res["style"]["btn_face"]["fg"])[0]):
        fails.append(f"{label} 链接形按钮孙节点的字没上自家墨（站点把字色排在了后代类名上）："
                     f"上色属性实测 {pl['tf']}，我们的墨是 {res['style']['btn_face']['fg']}")

    print(f"{label}  边框 {len(res['box'])} 个盒控件统一 1px solid "
          f"{'#%02x%02x%02x' % want_border}；"
          f"只读粉底({tint_pct:.0%}) {len(tinted)} 中 / {len(leaked)} 漏；"
          f"accent {len(accs)} 个同为 {sorted(set(accs.values()))[:1]}；"
          f"禁用态 {len(DISABLEABLE)} 个双信号；backdrop α={backdrop_a:.2f}；"
          f"玻璃面虚焦 blur({glass_px})；新词根 {len(FLOATROOTS)} 根各自吃到面与后代、"
          f"类名带词根却不该管的 {len(YIELD) + len(NOTROOTS) + len(MIDTOKEN) + len(NESTED) + len(IDEXCL) + len(MAINYIELD) + len(BODYROOTS) + len(HEADEXCL)} 块里 "
          f"{len(YIELD) + len(NOTROOTS) + len(MIDTOKEN) + len(NESTED) + len(IDEXCL) + len(MAINYIELD) + len(BODYROOTS)} 块原样留给站点、"
          f"标题那 {len(HEADEXCL)} 块判「不穿玻璃＋吃上 §4 圆角底」；"
          f"{len(SPECS)} 条线/面/标记逐条对账")


def load_tint(src):
    """从 CSS 里把"只读粉底"这一格的实际配方读出来：混色比例住在声明里，脚本不抄。"""
    blk = re.search(r"\):read-only[^{]*\{(.*?)\}", src, re.S)
    if not blk:
        die("没定位到 :read-only 那条规则块，粉底配方无从算起")
    mix = re.search(r"color-mix\(in srgb,\s*var\(--ks-sakura\)\s+([0-9.]+)%,"
                    r"\s*var\(--ks-canvas-1\)\)", blk.group(1))
    if not mix:
        die(":read-only 块里没解析到 color-mix(强调色 X%, canvas-1) 的配方")
    return float(mix.group(1)) / 100.0


def load_glass(src):
    """玻璃面的虚焦半径住在 §1 的 token 里，面板开关只调制它、不另写一份配方。
    降级档里那两处 `--ks-glass-blur: none` 是刻意的第二档，所以这里只认 blur() 那一格。"""
    got = re.findall(r"--ks-glass-blur:\s*blur\(calc\(var\(--kGlass,\s*1\)\s*\*\s*"
                     r"([0-9.]+)px\)\)", src)
    if len(got) != 1:
        die(f"玻璃虚焦半径应恰好有 1 处 blur(calc(var(--kGlass, 1) * Npx)) 配方，"
            f"实际 {len(got)} 处：{got}——期望值无从算起")
    return f"{got[0]}px"


def glass_deficit(want):
    """玻璃"透出去"的那一成 = 1 − §4c 那面的 α。单一定义：color-mix 的形状只在
    check-contrast.py 里解释一遍（MIX_RE 从那里取），像素闸门（diff-shots 第十项）
    拿同一个数预测纸面该画成什么色。
    两本各写一条正则，就会有一本先漂，然后两本一起绿。"""
    key = ("light", "玻璃面底色")
    if key not in want:
        raise ValueError("SPECS 表里没有「玻璃面底色」这一行，缺口比例无从算起")
    return 1.0 - want[key][1]


def load_family(src):
    """§4c 那族浮层选择器在文件里被抄了不止一遍（面、后代、打印那两格）。
    副本各走各的等于"玻璃面"和"玻璃面上的字"不是一套，纸上还会透着粉——
    所以按整段字节相等钉住，漂了就不是判据跟 CSS 对不上，而是 CSS 自己前后不一致。

    取整段靠的是括号深度，不是"从 :is(dialog 一路匹配到某个词"：
    上一版拿 `[class*="tooltip" i]` 当匹配收尾，而它在族里只是列表中段的一个词——
    往某一份副本的那一格**之后**追加选择器（给一类新浮层开口子最常见的写法），
    两份截出来的字节照样相同，漂移就这么静默过去了。改成扫到与自己配平的那个 )
    为止，整段（含列表末尾）才进了比对。"""
    fams = []

    def balanced(s, i):
        """从 s[i]（开括号的下一位）扫到配平的那个 ) 之后一位，返回 (位置, 剩余深度)。"""
        depth = 1
        while i < len(s) and depth:
            if s[i] == "(":
                depth += 1
            elif s[i] == ")":
                depth -= 1
            i += 1
        return i, depth

    for mm in re.finditer(r"^ {2,4}(:is\(dialog)", src, re.M):
        # 取段的起点是选择器本身，不含缩进：面与后代顶格两空格，打印档那两格在
        # @media print 里面、顶格四空格——把缩进算进字节，副本守卫会红在空格数上。
        # 为什么按"行首 + 词根表"而不是全文扫 :is(：§4c 还有一条只给浮动面钉分支的
        # 规则（:where( 套着词根表，项比族少五截），它不是副本，逐字相同那条不该管它。
        start, head = mm.start(1), mm.end(1)
        i, depth = balanced(src, head)
        if depth:
            die(f"§4c 那族在偏移 {start} 处没有配平的 )，整段取不出来")
        # 紧跟族的每一截 :not( 都算同一段（不是一截）：少了它们，"往排除式里加一项"
        # 或"整族外面再套一道结构排除"这种改动只落在一份副本里时没人说话，
        # 而它们正是"按钮／控件壳到底归不归我们"那一条。
        for _ in range(8):
            if not src.startswith(":not(", i):
                break
            i, depth = balanced(src, i + 5)
            if depth:
                die(f"§4c 那族的 :not( 在偏移 {i} 处没有配平的 )")
        else:
            die(f"§4c 那族在偏移 {i} 处连着 8 截 :not(，取段逻辑走不通——先看是不是括号没配平")
        fams.append(src[start:i])
    if len(fams) < 2:
        die(f"浮层族选择器应有 ≥2 份逐字相同的副本（面 + 后代），实际 {len(fams)} 份——"
            f"少一份说明族在某一处被单独改过，另一处的墨色没跟着走")
    uniq = set(fams)
    if len(uniq) != 1:
        die(f"浮层族的 {len(fams)} 份副本漂成了 {len(uniq)} 种写法："
            + "；".join(sorted(repr(f.splitlines()[-1].strip()) for f in uniq)))
    # 结构排除那一截由"逐字相同"钉不住：四份一起删掉它，副本照样彼此相同、闸门照样绿，
    # 而它正是把 GitHub 页头那 5 块文档流导航壳摘出玻璃的那一道（浅字压粉底的坏）。
    # 所以"在不在"这一格单独钉一次——失效方向是"被整族删掉"，不是"被单独改过"。
    if not all(":not(:has(> button))" in f for f in fams):
        die(f"浮层族少了那道结构排除 :not(:has(> button))（{sum(1 for f in fams if ':not(:has(> button))' in f)}/{len(fams)} 份还在）——"
            f"直接子元素里有按钮的面是站点的控件壳，不是浮层；摘掉这道排除，"
            f"GitHub 页头那几块导航壳会重新穿上玻璃，站家的浅色字压在粉底上")
    # 同一格的第二形：触发钮坐在孙节点上时上面那道按构造够不着（2026-10-03 现量 GitHub 页头
    # ActionMenu 的 container 只有一个直接子节点 div，button 在 div 里）。
    # 它同样钉在"在不在"上——四份副本一起删这一截时逐字相同那条守卫看不见。
    if not all(":not(:has(> * > button))" in f for f in fams):
        die(f"浮层族少了那道孙辈结构排除 :not(:has(> * > button))（{sum(1 for f in fams if ':not(:has(> * > button))' in f)}/{len(fams)} 份还在）——"
            f"这一截管的是按钮挂在孙节点上的那层控件壳；摘掉它，GitHub 页头那块 ActionMenu 容器"
            f"和 secondarybar 那块文档流面会重新穿上玻璃（浮着的那 9 块不受影响）")
    # 同一族的第三格"在不在"：整页排除 :not(body, html)。这一截**只能**钉在在不在上，
    # 夹具里量不到行为——2026-10-04 现读：夹具的 <body class="ksBodyHost header-dark"> 有
    # 直接的 <button> 子节点（body_btn_child=true），所以族末尾那道 :not(:has(> button))
    # 按构造先把 body 排掉了；把整页排除摘掉再量，body 依旧不匹配族（body_cut=false），
    # 后代那一格够到的元素数也一动不动（两跑都是 14/46）。这不是判据空转，是夹具的
    # 形状决定的：它把控件全铺在 body 底下，而真站的按钮埋得更深。
    # 承重读数在真站上（同一族串、无头之外现量 github.com/features 渲染后的 DOM）：
    # body 的 class 是 "logged-out env-production page-responsive header-dark"，
    # header 那截词根按子串命中 body；而 body 既没有按钮子节点也没有按钮孙节点
    # （btn_child=false、btn_grand=false，depth≤2 的 button 数 0），所以两道结构排除都
    # 盖不住它——去掉整页排除后 body 当场匹配族（body_cut=true）。留着它，body 读到的
    # 是 §2 的画布 rgb(255, 246, 250) 与 backdrop-filter: none。
    if not all(":not(body, html)" in f for f in fams):
        die(f"浮层族少了那道整页排除 :not(body, html)"
            f"（{sum(1 for f in fams if ':not(body, html)' in f)}/{len(fams)} 份还在）——"
            f"词根是按子串认的，GitHub 把 body 写成 class=\"… header-dark\"，header 那一截"
            f"当场命中 <body>；这一截是整页唯一一道盖得住它的排除（族末尾的两道结构排除"
            f"只排有按钮子孙的面，真站那页 body 底下没有 ≤2 层的按钮）。摘掉它，整页会披上"
            f"粉底玻璃加一层虚焦合成层，而 <body> 背后什么都没有可虚焦")
    # 同一族的第四格"在不在"：标题排除 :not(h1…h6)。夹具给得出行为证人（同一枚 tutheader 的
    # 正反两形），但四份副本一起删这一截时逐字相同那条看不见它——所以照旧单独钉一次。
    # 这一截按「六个标题形都在同一组 :not() 里」认，不按整串逐字节认：量出来的——K34 第一跑
    # 把排除写成 :not(h1, h2, h3, h4, h5, h6, div)，整串相等那条当场被打断，于是"写宽了"这一向
    # 红在守卫上、正控制那一本（div.tutheader 必须吃到面）轮不到说话，刀被判 MISSED。
    # 放宽后的分工才是两句各管一向：守卫管删，正控制管过收。
    _headgrp = re.compile(r":not\((?=[^()]*\bh1\b)(?=[^()]*\bh2\b)(?=[^()]*\bh3\b)"
                          r"(?=[^()]*\bh4\b)(?=[^()]*\bh5\b)(?=[^()]*\bh6\b)[^()]*\)")
    if not all(_headgrp.search(f) for f in fams):
        die(f"浮层族少了那道标题排除 :not(h1, h2, h3, h4, h5, h6)"
            f"（{sum(1 for f in fams if _headgrp.search(f))}/{len(fams)} 份还在）——"
            f"词根按子串认，runoob 的 <h2 class=\"tutheader\"> 当场被 header 那截追上，"
            f"站点一处纯文字标题被画上整幅面（2026-10-05 配对重拍：白天档那四块摘掉这一截前 "
            f"rgb(254,234,243)、摘后 rgb(250,247,246) 是站家自己的浅底）。页面 chrome 不会是一个 <h*>")
    # 钩子名 vs 词根：探针靠"站点类名里有词根"才成立，而钩子名自己若含词根的字面，
    # 词根被改写成一个仍能匹配钩子的拼法时，探针照样是玻璃——刀落了闸门却绿。
    # 这里按不区分大小写的子串比一遍，撞了就死在名字上，不留静默等价这条路。
    hooks = ([v[1] for v in YIELD.values()] + [v[1] for v in NOTROOTS.values()]
             + [v[1] for v in MIDTOKEN.values()] + [v[1] for v in NESTED.values()]
             + [NESTED_INNER[1]] + [v[0] for v in FLOATROOTS.values()]
             + [v[1] for v in IDEXCL.values()] + [v[0] for v in IDROOTS.values()]
             + [BARBTN_HOST[1], BARBTN[1], BARLINK_HOST[1], BARLINK[1],
                BODYLINK[1], BODYROOTS["bodyHeaderClass"][1]])
    # 取根的正则要跟着族的形式走：topnav 那几截写成 [class~=]/[class^=]/[class*="-topnav"]
    # 之后，只认 [class*= 的旧正则一根都抽不到，守卫就此哑掉而闸门全绿——所以三种属性运算符
    # 一起抽，再把两侧的词边界符号剥掉还原成词根本身（fixed-btn 中间的连字符不在两侧，不动）。
    roots = {t.strip('-_') for fam in fams
             for t in re.findall(r'\[class[~^*]?="([^"]*)"', fam)}
    hit = sorted({h for h in hooks for r in roots if r and r.lower() in h.lower()})
    if hit:
        die("探针钩子名被族里的词根吃到了：" + "、".join(hit)
            + f"（族里的词根：{sorted(roots)}；[class*=／^=／~=\"…\" i] 都是不区分大小写的匹配，"
              "钩子自己满足词根时，词根无论怎么写这块面板都是玻璃，那一格的判定量不到东西）")
    return len(fams)


def brace_block(src, open_at, who):
    """从 src[open_at]（必须是 '{'）扫到配平的 '}'，返回整块（含两端）。
    按花括号数深度不看字符串：量过，本文件里带引号的字面量没有一个含 { 或 }，
    而 CSS 注释里的花括号只出现在这一族自己的说明文字里、都成对。"""
    depth, i = 0, open_at
    while i < len(src):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if not depth:
                return src[open_at:i + 1]
        i += 1
    die(f"{who} 的花括号在偏移 {open_at} 处没配平，整块取不出来")


def load_reduced(src, shoot_src):
    """§7「系统要求少用透明」那一格必须把浮层路由到像素闸门已经量过的那一档。

    为什么这一本要跨文件对：关玻璃那趟拍的「实心板 + 墨还读得动」住在 shoot.sh 的
    GLASS_OFF_* 那两串里，量的是 --kGlass:0。§7 若写成别的数（或干脆只撤虚焦、
    留着那 14% 的缺口），「系统偏好接到了已量过的值」就只剩一句散文在说——
    所以这里比的是两边的数字，不比注释。
    口径：无头 Chrome 没有模拟 prefers-reduced-transparency 的通道（量过：
    加 --force-prefers-reduced-transparency 那一趟 matchMedia 仍为 false、虚焦没撤），
    媒体查询本身生不生效只能拿真装了系统偏好的浏览器复检；这一本管的是它路由到哪一档。"""
    mm = re.search(r"@media\s*\(\s*prefers-reduced-transparency\s*:\s*reduce\s*\)\s*\{", src)
    if not mm:
        die("CSS 里找不到 @media (prefers-reduced-transparency: reduce) 那一格——"
            "系统的「少用透明」偏好没接到任何东西")
    body = brace_block(src, mm.end() - 1, "reduced-transparency 那一格")
    glass = re.findall(r"--kGlass\s*:\s*([0-9.]+)", body)
    if not glass:
        die("reduced-transparency 那一格只撤了虚焦、没动 --kGlass："
            "面板还透着 14% 的粉，系统偏好等于没生效")
    if set(glass) != {"0"}:
        die(f"reduced-transparency 路由到 --kGlass:{'/'.join(sorted(set(glass)))}，"
            f"而像素闸门关档量的是 --kGlass:0——两边不是同一档，「已量过」那句话不成立")
    off = re.findall(r"GLASS_OFF_\w+\s*=\s*'[^']*?--kGlass:([0-9.]+)", shoot_src)
    if len(off) != 2:
        die(f"shoot.sh 里解出的 GLASS_OFF_* 关档串是 {len(off)} 条（应为白天/夜晚 2 条），"
            f"§7 的路由声明没有完整的证人")
    if sorted(set(off)) != ["0"]:
        die(f"shoot.sh 的关档串不是 --kGlass:0（读到 {sorted(set(off))}），"
            f"§7 的路由声明失去了证人——先修哪一边要看谁才是被量的那个")
    if not re.search(r"--ks-glass-blur\s*:\s*none", body):
        die("reduced-transparency 那一格没把 --ks-glass-blur 置 none："
            "底下的内容还糊成一片，这一档只剩透明度那一半")
    return glass[0]


def regenerate():
    """探针引的是 preview/skin.css，而它是从 kawaii-skin.user.css 剥壳生成的。
    这一本必须自己生成它：留下的副本会替**上一版**源文件说话——把源文件里的声明摘掉，
    计算样式照旧绿，那几十条对账就没在看真正要装进浏览器的那一份
    （K01/K02 两柄刀割在 backdrop-filter 和后代 !important 上都是这么哑掉的）。"""
    r = subprocess.run([sys.executable, "tools/strip.py"], cwd=ROOT,
                       capture_output=True, text=True)
    if r.returncode != 0:
        die("剥壳生成 preview/skin.css 失败，探针没有可加载的样式：\n"
            + (r.stdout + r.stderr).strip())


def main():
    if not Path(CHROME).exists():
        die(f"找不到 Chrome：{CHROME}")
    src = CSS.read_text(encoding="utf-8")
    regenerate()
    gate = GATE
    tokens = gate.load_tokens(src)
    for t in ("border", "canvas-1", "canvas-2"):
        if t not in tokens:
            die(f"CSS 里没解析到 --ks-{t}，期望值无从算起")
    sakura = gate.load_sakura(src)
    tint_pct = load_tint(src)
    tint = {b: gate.wash(tokens["canvas-1"][b], sakura, tint_pct)
            for b in ("light", "dark")}
    want = css_expect(src, tokens, sakura, gate)
    glass_px = load_glass(src)
    n_fam = load_family(src)
    print(f"浮层族    {n_fam} 份选择器副本逐字相同；虚焦半径自 §1 token：blur({glass_px})")
    rt = load_reduced(src, (ROOT / "tools" / "shoot.sh").read_text(encoding="utf-8"))
    print(f"少透明档  §7 把浮层路由到 --kGlass:{rt}，与 shoot.sh 关档同一个值"
          f"（实心板那一档由像素闸门量）")
    # 判据可辨识性：粉底若和某个兜底底色撞在容差内，"漏没漏"这一问就答不出来，
    # 调色板改天撞色时必须在这里炸，而不是让 leaked 静默变成空列表
    for b in ("light", "dark"):
        for t in ("canvas-1", "canvas-2", "canvas-3"):
            if t in tokens and close(tint[b], tokens[t][b]):
                die(f"{b} 档只读粉底与 {t} 撞色，判据失去辨识力（比例 {tint_pct:.0%}）")
    # 玻璃那一格同理：透出多少住在 α 上，缺口小过容差量级时"透"和"不透"是同一个读数
    try:
        deficit = glass_deficit(want)
    except ValueError as e:
        die(str(e))
    if deficit < 0.04:
        die(f"玻璃面透明度缺口只有 {deficit:.2f}，和 α 容差（0.02）同一个量级——"
            f"这一行退化成普通的底色对账，「透没透」在这儿分不出来")
    print(f"玻璃缺口  §4c 那面透出 {deficit:.0%}（像素闸门第十项照着同一个数预测纸面）")

    got = {b: run(build(b)) for b in ("light", "dark")}

    # 正控制：两档的边框色必须真的不同。相同 = --kScheme 没生效，
    # 那"夜晚档全绿"只是把白天量了两遍（shoot.sh 里那条历史坑的同一形）
    same = [n for n in BOX_CONTROLS
            if got["light"]["box"][n]["bc"] == got["dark"]["box"][n]["bc"]]
    if len(same) == len(BOX_CONTROLS):
        die("正控制没开火：明暗两档边框色一模一样，--kScheme 注入没生效，"
            "这一趟等于把白天量了两遍")

    for b in ("light", "dark"):
        check(b, got[b], tokens, tint, tint_pct, want, glass_px)

    if fails:
        print(f"\nCTRL FAIL：{len(fails)} 项")
        for f in fails:
            print("  - " + f)
        sys.exit(1)
    print("\nCTRL PASS：每个控件都拿到了该拿的，且只拿该拿的那一份")


if __name__ == "__main__":
    main()
