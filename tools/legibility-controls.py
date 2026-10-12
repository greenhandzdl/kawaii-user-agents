#!/usr/bin/env python3
"""legibility.py 的刀架：每具只改一个变量，看输出里那句主张动不动。

为什么单独一个文件而不塞进闸门：这几具要把闸门**判红**，而真跑那一趟必须是绿的；
混在一起就成了"为了自测而故意红一次"，读数不再等于结论。
所以这里跑的是沙箱里的一份拷贝（临时目录 + 复制 spot-check.sh 名单上每一站的五张图：
裸页、白天、夜晚，再加白天/夜晚两张哨兵档），真站的图一个字节都不动。

主张住在注释里，判据住在代码里，两边都要有人证：
  C0 基线              没动过图，rc=0 且至少一格两档自家底都量到了数
  C1 MIN_RUNS 退回 1    块边界又被当成一行字：证人落在"同一张图上正文行数变多"（那正是这个
                       常量管的那一格）。判定数不当证人——同一具刀在三格上给出三种符号，
                       挑任何一种当机制就是把上一版读数钉成期望值（详见 C1 那段注释）
  C2 哨兵档＝上肤档的拷贝  仪器断电：整格动过 0 格 ⇒ 判红"没有一行是皮肤涂的底"，
                       而且这条红不归名单声明管（C6a 用的就是同一格声明，走的是另一支）
  C3 尺寸不符           两趟不是同一个版面 ⇒ 判红"这张图归不了因"
  C4 只压白天档          自家底塌一档、另一档过线 ⇒ 点名"切到另一档读"（README 那句承诺的实例）
  C5 两档一起压          「量到自家底的两档全塌，切档也救不回来」
  C6a/b 让路声明一对     同一张"整格动了、正文列一格没动"的哨兵图（自家 0 行、动过 >0 格，
                       runoob/night 实测的形状）：声明了"让路"就只报不判、摘掉声明就判红，
                       证明那两个真字真的在挡红，而不是句装饰注释
  C7 让路声明 + 两档都压塌  声明挡不住塌档——往名单里加一行不能把红点抹白
 C8a 抹掉正文列的墨      真塌版：逐采样行把正文列填成该行自己的纸色 ⇒ 判红"只剩 N 行有墨"
 C8b 底把行劈开、墨还在   真站 w3schools/night 现图（2026-10-04 量到 有墨 66 行 ≥ 裸页 65 行、
                        被接受只有 34 行）⇒ 只报不判，输出里不许出现"打散"那三个字
 C9  块边界当字（另一格） 同一把 MIN_RUNS=1 的刀只喂 github-docs：站点底被拖到 1.36 而参考档 4.20
                        ⇒ 那条「两边对不上」的比对红开火（它此前没有任何控制；反面见 C1）

压图是全图编辑，它顺带把归因放宽了：哨兵档不跟着压，于是站点自涂的纸也被拉离哨兵值、
挤进"自家"那一桶。所以 C4/C5 证明的是"自家底的中位掉到 4.5 以下 ⇒ 塌档与切档那两条红开火"，
不证明归因本身的宽窄——归因由 C2/C3/C6 那几具管。
压强选"向该档自己的画布 token 混"而不是"向整图均值混"：向均值混在旧一批图上实测过会把正文行
从 284 缩到 76（行检测先受伤，FLAT/MIN_COVER 认不出糊成一片的纸；那一站 csstricks-home 已出名单，
这个数不再由现在的图供养，留在这里只说明为什么不走那条路）。向画布混只吃墨的对比度、
纸还是那一档的粉紫，量到的才是"墨被纸吃掉"这件事。
每一档用多大的压强不是拍的：first_alpha_to_press 现探，要求压完那一档仍然 自家>0 行且读数 <4.5，
探不到就停下来报错——不许拿"压到 0.8 总该塌"当假设。
"""
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
GATE_SRC = ROOT / "tools" / "legibility.py"
SPOT = ROOT / "tools" / "spot-check.sh"
# 这几具的读数写在具体那一本上（mdn 的两档、csstricks-article 的 MIN_RUNS 刀、
# 让路声明那一格），所以它们必须在册。不在册不是"少测一个站"，是那几具根本没有对象可压。
NEED = ("mdn", "csstricks-article")
ARMS = ("bare", "day", "night", "day-sent", "night-sent")


def extract_sites():
    """取 spot-check.sh 的 SITES 原文（`tag|url[|让路]` 逐行），不抄第二份。

    抄了一份就变成测副本：真名单加一站（github-docs 就是这么进来的），刀架却还在跑四个，
    于是"抽检图不齐"那道守卫只按旧名册挡人，新那一格的漏判没人量——而它的图就躺在同一个
    shots/ 里，看着像是被覆盖了。
    """
    src = SPOT.read_text(encoding="utf-8")
    m = re.search(r'^SITES="\n(.*?)"$', src, re.S | re.M)
    if not m:
        sys.exit(f"CONTROL ERROR: 没按 `^SITES=\"` … `^\"` 从 {SPOT.name} 取出名单——"
                 f"它的形状变了，这一趟没有站点可跑")
    lines = [l for l in m.group(1).splitlines() if l.strip()]
    for l in lines:
        tag, sep, rest = l.partition("|")
        url = rest.partition("|")[0]
        if not sep or not tag.strip() or not url.startswith("http"):
            sys.exit(f"CONTROL ERROR: {SPOT.name} 的名单里这一行不像 `tag|http…[|声明]`：{l[:80]}")
    have = {l.partition("|")[0].strip() for l in lines}
    if sorted(set(NEED) - have):
        sys.exit(f"CONTROL ERROR: 名单里没有 {sorted(set(NEED) - have)}——"
                 f"这几具的读数是写在那几本上的，换样本得连读数一起换，不能少测")
    return "\n".join(lines)


KS = extract_sites()
TAGS = {l.partition("|")[0].strip() for l in KS.splitlines()}


def sandbox():
    """把闸门、它的输入（preview/skin.css 由 check-contrast.py 解析）和抽检图搬进临时目录：
    legibility.py 按 __file__ 的上级找 shots/，所以必须整棵树一起搬。"""
    d = Path(tempfile.mkdtemp(prefix="ks-legctl-"))
    for sub in ("tools", "preview", "shots"):
        (d / sub).mkdir()
    for f in ("legibility.py", "check-contrast.py"):
        shutil.copy2(ROOT / "tools" / f, d / "tools" / f)
    shutil.copy2(ROOT / "preview" / "skin.css", d / "preview" / "skin.css")
    missing = [f"spot-{t}-{v}.png" for t in sorted(TAGS) for v in ARMS
               if not (ROOT / "shots" / f"spot-{t}-{v}.png").exists()]
    if missing:
        sys.exit(f"CONTROL ERROR: 抽检图不齐（名单 {len(TAGS)} 站 × {len(ARMS)} 档，"
                 f"缺 {sorted(set(missing))}）——先跑 ./tools/spot-check.sh 出图，再来量它自己的刀")
    for p in sorted((ROOT / "shots").glob("spot-*.png")):
        shutil.copy2(p, d / "shots" / p.name)
    return d


def canvas(branch):
    """该档自己的画布 token（压图的目标色）。色值不抄第二份，从 skin.css 现推。"""
    spec = importlib.util.spec_from_file_location("cc", str(ROOT / "tools" / "check-contrast.py"))
    cc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cc)
    return cc.load_tokens((ROOT / "preview" / "skin.css").read_text(encoding="utf-8"))[f"canvas-1"][branch]


def press(path, rgb, alpha):
    """把整图向 rgb 混：墨被纸吃掉，纸还是那张纸（颜色级别不变，归因不掉）。"""
    with Image.open(path) as im:
        im = im.convert("RGB")
        Image.blend(im, Image.new("RGB", im.size, rgb), alpha).save(path)


def pristine(d):
    for p in (ROOT / "shots").glob("spot-*.png"):
        shutil.copy2(p, d / "shots" / p.name)


def gate(d, knife=None, edits=(), sites=None):
    """跑一趟真闸门，返回 (rc, 输出)。knife＝改 legibility.py 的一个常量；
    edits＝对图做二次处理（函数，在 pristine 之后按序执行）；sites＝换传进去的名单。"""
    gate_p = d / "tools" / "legibility.py"
    src = GATE_SRC.read_text(encoding="utf-8")
    if knife:
        old, new = knife
        n = src.count(old)
        if n != 1:
            sys.exit(f"CONTROL ERROR: 锚点 {old!r} 在 {GATE_SRC.name} 里命中 {n} 次，"
                     f"不唯一——这把刀会打到别处，先修锚点再谈结论")
        gate_p.write_text(src.replace(old, new), encoding="utf-8")
    else:
        gate_p.write_text(src, encoding="utf-8")
    # 每具刀都从原图起步：上一具的处理留在沙箱里，下一具就是在处理过的图上再处理一次
    pristine(d)
    for fn in edits:
        fn(d)
    r = subprocess.run([sys.executable, str(gate_p)],
                       env=dict(os.environ, KS_SITES=sites or KS),
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def reading(out, tag, arm):
    """从输出里取那一格那一档的判定数（行首 `tag  …  arm=6.91(…`）。取不到就停，不猜。

    名单段也按 `tag  http…` 打印，首词同样是那个 tag，所以只认带"正文"的那一行；
    按首词取第一行会取到名单行，然后在这具根本没打印过的格上报"没量到"。
    """
    line = next((l for l in out.splitlines()
                 if l.split() and l.split()[0] == tag and "正文" in l), None)
    if line is None:
        sys.exit(f"CONTROL ERROR: 输出里没有 {tag} 那一行——它被摘出名单了还是换了形状")
    m = re.search(rf"{arm}=(\d+\.\d\d|   —)", line)
    if not m:
        # "这一档没有判定数"有四种真形状，都是报告本该说得出话的格子：正文行不足（采样不足
        # 那一支根本不打中位数）、尺寸不符（归不了因）、无图／无哨兵图（缺输入）。
        # 基线转绿之后 judged_sites() 会对每一格每一档都调这里，把它们当 CONTROL ERROR
        # 就等于"这台仪器一绿，刀架反而跑不起来"——读不到数是读数的一种，不是输出坏了。
        if re.search(rf"{arm}=(?:正文行不足|尺寸不符|无图|无哨兵图)", line):
            return None
        sys.exit(f"CONTROL ERROR: {tag} 那一行没量到 {arm} 档的数：{line[:90]}")
    v = m.group(1)
    return None if v.strip() == "—" else float(v)


def rows(out, tag, arm):
    """那一格那一档的 (正文, 自家, 站点底) 行数。判定数住在"自家"那一格里，
    所以归因塌没塌只能从这里量，不能光看判定数（"   —" 和 0.00 是两件事）。
    每桶形状由 legibility.py 的 shown() 定：非空 `N行 中位`、空桶 `0行 —`。"""
    line = next((l for l in out.splitlines()
                 if l.split() and l.split()[0] == tag and "正文" in l), None)
    if line is None:
        sys.exit(f"CONTROL ERROR: 输出里没有 {tag} 那一行——它被摘出名单了还是换了形状")
    m = re.search(rf"{arm}=[^()]*\(正文(\d+)行｜自家(\d+)行 (?:[\d.]+|—)｜站点底(\d+)行", line)
    if not m:
        sys.exit(f"CONTROL ERROR: {tag} 那一行的三桶行数形状对不上：{line[:120]}")
    return tuple(int(g) for g in m.groups())


def judged_sites(out):
    """两档自家底都量到了读数的格数——判定住在这些格上，所以基线至少要有 1 格。"""
    n = 0
    for tag in TAGS:
        if any(l.split() and l.split()[0] == tag and "正文" in l for l in out.splitlines()):
            if all(reading(out, tag, v) is not None for v in ("day", "night")):
                n += 1
    return n


def run(d, label, want_rc, want, check=None, knife=None, edits=(), sites=None):
    """check(输出) -> (是否成立, 印出来的依据)。方向性断言走 check，不走 want：
    把上一版量到的数写进 want 就成了钉历史，换一次样本、改一次图都得先改刀。"""
    rc, out = gate(d, knife=knife, edits=edits, sites=sites)
    miss = [w for w in want if not re.search(w, out, re.S)]
    ok_check, note = ((True, "") if check is None else check(out))
    ok = rc == want_rc and not miss and ok_check
    print(f"{'OK  ' if ok else 'FAIL'} {label}: rc={rc}(要 {want_rc})"
          f"{'，缺 ' + '、'.join(miss) if miss else ''}"
          f"{'，' + note if note else ''}")
    for l in out.splitlines():
        first = l.split(maxsplit=1)[0] if l.split() else ""
        if first in TAGS or l.startswith("  - ") or "FAIL" in l or "PASS" in l:
            print("     " + l[:200])
    return ok


def zero_sentinel(dd, tag):
    """把某一格的哨兵档换成它的上肤档拷贝＝仪器断电：颜色一个字节没改，归因却全塌。"""
    for v in ("day", "night"):
        shutil.copy2(dd / "shots" / f"spot-{tag}-{v}.png",
                     dd / "shots" / f"spot-{tag}-{v}-sent.png")


def sample_grid():
    """归因采样网格的范围，从 legibility.py 现读（X0, X1 = … / Y0, Y1 = …）——抄第二份就会有两处定义。"""
    src = GATE_SRC.read_text(encoding="utf-8")
    m = re.search(r"^X0, X1 = ([\d.]+), ([\d.]+)", src, re.M)
    n = re.search(r"^Y0, Y1 = ([\d.]+), ([\d.]+)", src, re.M)
    if not (m and n):
        sys.exit("CONTROL ERROR: 没在 legibility.py 里按 `^X0, X1 = 数, 数` 和 `^Y0, Y1 = 数, 数` "
                 "取到采样网格——那两行换了形状，这一具的落点就没有依据了")
    return float(m.group(1)), float(m.group(2)), float(n.group(1)), float(n.group(2))


def concede_text_column(dd, tag):
    """把"正文列整片由站点自己涂的底盖住"做成图，并且只在这件事之上加一格"别处仍在动"。

    两步，缺一不可：
    1) 把 bare 档的正文列同时盖进上肤档和哨兵档——列内两档逐字相同，于是每一行的纸色都
       "没动"，自家 0 行、站点底那一桶就是裸页的真实纸色（runoob/night 的真形状）。
    2) 但归因的采样网格**只覆盖正文列**（legibility.py 的 ownership()：x∈[X0,X1]、y∈[Y0,Y1]、步长 2），
       第 1 步顺带把整格的动过读数抹成 0——那正是 C2"仪器没读数"那一支，名单声明挡不住它。
       所以再挑若干个**纹理格**（八邻域与中心逐通道差都 ≥8，因而绝不可能是某行"平底色"的纸色采样点）
       在哨兵档上挪一下：动过 >0 而没有任何一行被判成自家。
    """
    x0, x1, y0, y1 = sample_grid()
    for v in ("day", "night"):
        ba_p = dd / "shots" / f"spot-{tag}-bare.png"
        sk_p = dd / "shots" / f"spot-{tag}-{v}.png"
        sn_p = dd / "shots" / f"spot-{tag}-{v}-sent.png"
        with Image.open(ba_p) as bare, Image.open(sk_p) as a, Image.open(sn_p) as b:
            if not (bare.size == a.size == b.size):
                sys.exit(f"CONTROL ERROR: {tag} 的 bare/{v}/哨兵三张尺寸不齐，切不出这一具")
            bare, a, b = bare.convert("RGB"), a.convert("RGB"), b.convert("RGB")
            W, H = a.size
            left, right = int(W * x0), int(W * x1)
            band = bare.crop((left, 0, right, H))
            a.paste(band, (left, 0))
            b.paste(band, (left, 0))
            px = b.load()
            picked = []
            for y in range(int(H * y0), int(H * y1), 2):
                for x in range(left, right, 2):
                    if len(picked) >= 400:
                        break
                    c = px[x, y]
                    nb = [(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                          if (dx or dy) and 0 <= x + dx < W and 0 <= y + dy < H]
                    if len(nb) == 8 and all(max(abs(i - j) for i, j in zip(c, px[nx, ny])) >= 8
                                           for nx, ny in nb):
                        picked.append((x, y))
                if len(picked) >= 400:
                    break
            if not picked:
                sys.exit(f"CONTROL ERROR: {tag}/{v} 的正文列里挑不出一格纹理点——"
                         f"这一具需要'列内没被涂到、但整格仍在动'，挑不出就切不出那个形状")
            for x, y in picked:
                cur = px[x, y]
                b.putpixel((x, y), tuple((c + 7) % 256 for c in cur))
            a.save(sk_p)
            b.save(sn_p)
            grid_pts = [(x, y) for y in range(int(H * y0), int(H * y1), 2)
                        for x in range(left, right, 2)]
            moved = sum(1 for x, y in grid_pts if a.getpixel((x, y)) != b.getpixel((x, y)))
            if moved != len(picked) or moved == 0:
                sys.exit(f"CONTROL ERROR: {tag}/{v} 网格上动了 {moved} 格、挑中 {len(picked)} 格——"
                         f"两者必须相等且不为 0，否则落点没切准（列内应当只剩挑中那几格在动）")


def const_val(name):
    """从 legibility.py 现读一个整数常量（MIN_ROWS 这类），不抄第二份：抄了就变成
    刀架钉着自己手里那份数，真闸门改了常量还得人来记得同步这里。"""
    m = re.search(rf"^{name} = (\d+)", GATE_SRC.read_text(encoding="utf-8"), re.M)
    if not m:
        sys.exit(f"CONTROL ERROR: 没在 {GATE_SRC.name} 里按 `^{name} = 数` 读到它——"
                 f"那一行换了形状，这一具的判据没依据了")
    return int(m.group(1))


def inked_rows(out, tag, arm):
    """采样不足那一支打的两个行数 (被接受, 有墨)。取不到就停：C8 两具的证人正落在这两格上。"""
    line = next((l for l in out.splitlines()
                 if l.split() and l.split()[0] == tag and "正文" in l), None)
    if line is None:
        sys.exit(f"CONTROL ERROR: 输出里没有 {tag} 那一行")
    m = re.search(rf"{arm}=正文行不足\((\d+)\)｜有墨(\d+)行", line)
    if not m:
        sys.exit(f"CONTROL ERROR: {tag} 的 {arm} 档没打「正文行不足(N)｜有墨M行」这一格："
                 f"{line[:120]}——采样不足那两支换了形状，C8 的证人就没了")
    return int(m.group(1)), int(m.group(2))


def erase_text(dd, tag, arm):
    """把某一格上肤档正文列里的**墨**抹掉、纸留着＝真塌版。

    逐采样行取该行自己的中位色，把整段列宽（含采样点之间那一列）连同下一行一起填过去：
    墨一行都不剩，而底还是它自己的底——所以 flat 那道闸照过、墨带全不过。
    不"整块填一个纯色"：那会把底也一起改掉，量到的就不是"字没了"而是"底没了"，
    那一具证的就不是这一格。
    """
    x0, x1, y0, y1 = sample_grid()
    p = dd / "shots" / f"spot-{tag}-{arm}.png"
    with Image.open(p) as im:
        im = im.convert("RGB")
        W, H = im.size
        px = im.load()
        left, right = int(W * x0), int(W * x1)
        xs = range(left, right, 2)
        for y in range(int(H * y0), int(H * y1), 2):
            line = sorted(px[x, y] for x in xs)
            paper = line[len(line) // 2]
            for yy in (y, y + 1):
                if yy < H:
                    for x in range(left, right):
                        px[x, yy] = paper
        im.save(p)


def only_site(sites_txt, tag):
    """把名单缩到一站。用在"主张只落在某一格的那一列读数上"的具上（C1）。

    这一具原来跑的是整张名单，于是 rc 由**别格**的判定决定：2026-10-04 实测
    MIN_RUNS=1 把 github-docs 白天档的站点底读数从 3.28 拖到 1.36、裸页参考档 4.20，
    那条「参考档和站点自有底两边对不上」的红就替这具刀说了话——而那根本不是 C1 的主张
    （C1 要说的是"块边界又被当成一行字"，证人只有"同一张图上正文行数变多"）。
    注意这里缩的只是**传给闸门的名字**，不是判定的宽窄：C1 从头到尾都在比同一格的同一列，
    和 glass-census 那条"缩过的名册不许出整体失效"（#83）不冲突——那一条换的是判定作用域，
    这一具换的是采样面，判定还是那一格的行数比。
    """
    keep = [l for l in sites_txt.splitlines() if l.partition("|")[0].strip() == tag]
    if len(keep) != 1:
        sys.exit(f"CONTROL ERROR: 名单里 {tag} 出现 {len(keep)} 次，缩不出一站")
    return "\n".join(keep)


def declare(sites_txt, tag):
    """把名单里某一格声明成让路格（补第三格），其余行一字不动。"""
    out, hit = [], 0
    for ln in sites_txt.splitlines():
        if ln.partition("|")[0].strip() == tag:
            hit += 1
            out.append(ln + "|让路")
        else:
            out.append(ln)
    if hit != 1:
        sys.exit(f"CONTROL ERROR: 名单里 {tag} 出现 {hit} 次，声明不了让路格")
    return "\n".join(out)


def first_alpha_to_press(d, arm, tag):
    """把 spot-<tag>-<arm>.png 单档压到 4.5 以下所需的最小压强，并且归因必须还在（自家 >0 行）。
    两档各探各的：只探一个"够压塌白天档"的强度，两档一起压那一具就会出现
    "压了两档、只有一档塌"的假失败。

    压图必须走 gate(edits=…) 那一扇门：gate() 自己先 pristine() 再跑，
    在外面先压再叫 gate 等于把这一压覆盖掉（实测过：α 从 0.3 扫到 0.8 读数逐字不动）。
    这也让探出来的 α 和 C4/C5 用的是同一条落盘路径。"""
    branch = "light" if arm == "day" else "dark"
    for a in (0.30, 0.40, 0.50, 0.60, 0.70, 0.80):
        rc, out = gate(d, edits=[lambda dd, a=a: press(
            dd / "shots" / f"spot-{tag}-{arm}.png", canvas(branch), a)])
        v = reading(out, tag, arm)
        n_ours = rows(out, tag, arm)[1]
        print(f"     探强度 {tag}/{arm} alpha={a}: 读数={v if v is None else f'{v:.2f}'} "
              f"自家{n_ours}行 rc={rc}")
        if v is not None and v < 4.5 and n_ours:
            return a
    sys.exit(f"CONTROL ERROR: 压到 0.8 都没能让 {tag} 的 {arm} 档塌下去——"
             f"那一具刀没有基线可切，别当成'判据够用'")


def collapse_fired(out):
    """C8a 的方向性判据：那条红开了火，并且它自己报的读数确实低于那道线。
    不钉具体数（抹光墨该读出 0 行，可那是这一具刀的形状，不是判据的主张）。"""
    m = re.search(r"正文列里只剩 (\d+) 行有墨（裸页 (\d+) 行", out)
    if not m:
        return False, "这条红没开火——墨抹光了还不判，版面真塌了就没人报"
    n, bare_n = int(m.group(1)), int(m.group(2))
    lim = const_val("MIN_ROWS")
    return n < lim, f"判红读数 有墨 {n} 行 < {lim}（裸页同一把尺 {bare_n} 行）"


def caliber_not_red(out):
    """C8b 的方向性判据：现成的 w3schools/night（底把行劈开、墨还在）不许被判成塌版。
    两个条件都要：那句指控不在输出里，且它自己报的有墨行数在 MIN_ROWS 之上——
    只有前半，"这一格整趟没量到"也能冒充成绿。"""
    n_rows, n_inked = inked_rows(out, "w3schools", "night")
    lim = const_val("MIN_ROWS")
    bad = "皮肤把版面打散" in out
    return (not bad and n_inked >= lim), (
        f"w3schools/night 被接受 {n_rows} 行、有墨 {n_inked} 行（阈值 {lim}），"
        f"塌版指控{'还开着火' if bad else '没开火'}")


def main():
    d = sandbox()
    base_rc, base_out = gate(d)
    try:
        if base_rc != 0:
            print("FAIL 基线自己就是红的——先修真闸门，再来量它的刀（下面每一具都会把红记在自己头上）")
            for l in base_out.splitlines():
                if l.startswith("  - ") or "FAIL" in l:
                    print("     " + l[:200])
            return 1
        a_day = first_alpha_to_press(d, "day", "mdn")
        a_night = first_alpha_to_press(d, "night", "mdn")
        b_day = reading(base_out, "csstricks-article", "day")
        if b_day is None:
            sys.exit("CONTROL ERROR: 基线里 csstricks-article 的白天档自家底 0 行（判定数是 '—'）——"
                     "C1 这具要在它的读数上量方向，没有基线数就别跑")
        results = [
            run(d, "C0 基线（没动过图）", 0, [],
                check=lambda o: (judged_sites(o) >= 1,
                                 f"{judged_sites(o)}/{len(TAGS)} 格两档自家底都量到（基线同数）")),
            # C1：MIN_RUNS 退回 1 ⇒ 块边界那一整条连续段又被当成"上面有字"。
            # 证人只能落在"正文行数变多"上——那正是这个常量管的那一格。
            # 不断言判定数（中位）的方向，也不断言它必须动：现图上三格给出三种结果
            # csstricks/day 7.08→7.08（行 91→120，中位恰好没挪）、github-docs/day 9.73→15.42、
            # w3schools/night 9.19→1.40。拿其中任何一格的符号当机制，就是把上一版读数钉成期望值。
            run(d, "C1 MIN_RUNS=1（块边界当字）", 0, [r"csstricks-article"],
                check=lambda o: (
                    rows(o, "csstricks-article", "day")[0] > rows(base_out, "csstricks-article", "day")[0],
                    f"基线正文 {rows(base_out, 'csstricks-article', 'day')[0]} 行（判定 {b_day:.2f}）"
                    f" → 这具 {rows(o, 'csstricks-article', 'day')[0]} 行"
                    "（只认行数；判定数方向见上面那三格）"),
                knife=("MIN_RUNS = 3", "MIN_RUNS = 1"),
                sites=only_site(KS, "csstricks-article")),
            # C2：把哨兵档换成上肤档的拷贝＝仪器断电（一个像素都不会变）。
            # 这一具证明"这块底是谁涂的"真的由那张重拍决定：颜色一个字节没改，归因却全塌。
            # 也是"名单声明挡不住仪器断电"那条分界的正控制（C6a 声明了让路，走的却是另一支）。
            run(d, "C2 哨兵档＝上肤档拷贝（仪器断电）", 1,
                [r"动过 0 个", r"没有一行是皮肤涂的底", r"LEGIBILITY FAIL"],
                edits=[lambda dd: zero_sentinel(dd, "mdn")]),
            run(d, "C3 哨兵档尺寸不符（两趟不是同一版面）", 1,
                [r"尺寸.*不同|归不了因", r"LEGIBILITY FAIL"],
                edits=[lambda dd: Image.open(dd / "shots" / "spot-mdn-day-sent.png")
                       .crop((0, 0, 1200, 1500)).save(dd / "shots" / "spot-mdn-day-sent.png")]),
            run(d, "C4 只压 mdn 白天档（塌一档、切档能救）", 0,
                [r"mdn/day 自家底上 \d\.\d\d<4\.5", r"切到 ?night ?档读|切到night档读"],
                edits=[lambda dd: press(dd / "shots" / "spot-mdn-day.png", canvas("light"), a_day)]),
            run(d, "C5 mdn 两档一起压", 1, [r"量到自家底的 2 档全塌", r"LEGIBILITY FAIL"],
                # arm/br/al 必须用默认参数绑死：列表推导里的循环变量是同一个作用域格子，
                # 两枚 lambda 都闭到最后一枚上，实测就是"压了 night 两次、day 一字未动"。
                edits=[lambda dd, arm=arm, br=br, al=al:
                       press(dd / "shots" / f"spot-mdn-{arm}.png", canvas(br), al)
                       for arm, br, al in (("day", "light", a_day), ("night", "dark", a_night))]),
            # C6 是一对：同一张"动了正文列以外那一格"的哨兵图（自家底 0 行、动过 >0 格），
            # 唯一的差别是名单里那一格声明没声明"让路"。只跑声明的那一半会假绿——
            # 它可能本来就因为别的原因不判红；摘掉声明必须红，才证明那两个真字真的在挡红，
            # 而不是句装饰注释。
            run(d, "C6a 让路声明 + 正文列没涂到 → 只报不判", 0,
                [r"另有 \d+ 格按名单声明只报让路读数"],
                edits=[lambda dd: concede_text_column(dd, "mdn")],
                sites=declare(KS, "mdn")),
            run(d, "C6b 同一张图，摘掉让路声明 → 判红", 1,
                [r"量不到皮肤自己的成绩", r"LEGIBILITY FAIL"],
                edits=[lambda dd: concede_text_column(dd, "mdn")],
                sites=KS),
            # C7：让路只该挡"没涂到"，不该挡"涂到了还塌"。把白天档压塌、同时把那一格声明成让路：
            # 声明不该把这具刀也一并豁免掉（否则名单里加一行就能把红点抹白）。
            run(d, "C7 让路声明挡不住塌档", 1,
                [r"量到自家底的 2 档全塌", r"LEGIBILITY FAIL"],
                edits=[lambda dd: press(dd / "shots" / "spot-mdn-day.png", canvas("light"), a_day),
                       lambda dd: press(dd / "shots" / "spot-mdn-night.png", canvas("dark"), a_night)],
                sites=declare(KS, "mdn")),
            # C8 是一对，证的同一把尺（"正文列里还剩几行字"）在两种失效上的两种形状：
            # C8a 墨没了＝真塌版，必须判红；C8b 底把行劈开而墨还在＝口径差，必须不判红。
            # 原来那条红只看"裸页几行 vs 上肤几行"，这两种形状在它眼里一模一样，于是把
            # 仪器口径指控成了"皮肤把版面打散"。2026-10-04 拆开闸口量过 w3schools/night：
            # flat 掉的行 night 218／day 66／bare 81，而"压根没墨"掉的行 night 257 少于 bare 309，
            # 被接受 34 行却有墨 66 行（裸页同档尺只有 65 行）——字一行没丢。
            # 只判方向不钉历史数：C8b 读的是"有墨 ≥ MIN_ROWS 且输出里没有那三个字"，
            # C8a 读的是"红开了火且它自己报的有墨行数确实低于那道线"。
            run(d, "C8a 抹掉 csstricks-article 夜晚档正文列的墨（真塌版）→ 判红", 1,
                [r"正文列里只剩 \d+ 行有墨", r"皮肤把版面打散", r"LEGIBILITY FAIL"],
                edits=[lambda dd: erase_text(dd, "csstricks-article", "night")],
                check=collapse_fired),
            run(d, "C8b 底把行劈开而墨还在（真站 w3schools/night）→ 只报不判", 0, [],
                check=caliber_not_red),
            # C9 是这一轮把架跑通之后才露出来的：C1 原来喂的是整张名单，顺带把另一格判红了，
            # 而那条红（「裸页参考档 vs 上肤图里站点自有底 两边对不上」）在此之前**没有一具控制**——
            # 它开不开火、什么时候该开火，一直没人证过。现在单独钉住：同一把刀 MIN_RUNS=1、
            # 只喂 github-docs 一站，块边界把站点底那一桶从 3.28 拖到 1.36（参考档 4.20），
            # 这条红必须开火。反面就是 C1：同一把刀在 csstricks-article 那一格不开这条红（rc 0）。
            run(d, "C9 块边界当字 → 站点底被拖离参考档，那条比对红开火", 1,
                [r"两边对不上", r"LEGIBILITY FAIL"],
                knife=("MIN_RUNS = 3", "MIN_RUNS = 1"),
                sites=only_site(KS, "github-docs")),
        ]
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print(f"\n{sum(results)}/{len(results)} 具动了")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
