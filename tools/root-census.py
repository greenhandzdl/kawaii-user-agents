#!/usr/bin/env python3
"""候选词根普查：把「这一截词根加进玻璃族会追到什么」量成一张表。

为什么要有这一张表：§4c 的族名单里「navbar／header 这两截不追」是按真站普查定的，
而那次普查（tools/glass-census.py）按 computed position 先筛过 fixed/sticky，
所以它结构上答不了「一截词根命中的元素里有几个真浮着、几个躺在文档流里」。
CSS 选择器也表达不了 position——于是「加进去会不会误伤」这一格一直没有尺子。

这张表问的就是这一格：对每一截候选词根，在同一个窗口、同一份 skin.css 下数
命中的可见元素里 fixed／sticky 有几个（加了才看得见玻璃）、static／relative 有几个
（加了就是把玻璃涂到正文条上），并给出误伤那一侧最大的一块面积和它的类名。

它**不出判定**：阈值一进来就是第二条判据，而这一格没有金样本可钉。
读数是给「要不要往族里加一截词根」这个决定用的输入，加与不加写在 CSS 的注释里。

跑法（和 glass-census 同一套：本机反代 + headless Chrome 的 --dump-dom）：
    ./tools/root-census.py                      # 全站名单，白天档
    ./tools/root-census.py --theme=night --only=github-docs,w3
    ./tools/root-census.py --only= --extra=tag|https://url   # 只跑临时加进来的那一站
候选词根的名册只有一个定义，在 tools/proxy.py 的 ROOT_TOKENS（按类名／id 的两形）与
ROOT_RAW（不靠类名的结构形），注入时替换进探针脚本，这里不抄第二份（抄本迟早和名册分家）。
"""
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("_gc", ROOT / "tools" / "glass-census.py")
gc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gc)
# 加载的必须是那个模块本身：glass-census 有 __main__ 守卫，所以 import 不会顺手跑一遍普查；
# 万一它哪天没了守卫，这一行会先炸而不是让这张表安静地多跑一轮网络。
assert callable(gc.dump) and callable(gc.sites) and callable(gc.start_proxy)


def pos_of(rec):
    p = rec.get("pos") or {}
    return {k: int(p.get(k, 0) or 0)
            for k in ("fixed", "sticky", "static", "relative", "absolute")}


def main():
    argv = sys.argv[1:]
    bad = [a for a in argv if not re.match(r"^--(window|theme|only|keepjs|extra)(=|$)", a)]
    if bad:
        sys.exit(f"ROOT ERROR: 不认得参数 {bad}（可用：--window=WxH --theme=day|night "
                 "--only=tag[,tag] --keepjs --extra=tag|https://url，与 glass-census 同一套）")
    window = next((a.split("=", 1)[1].lower().replace("x", ",")
                   for a in argv if a.startswith("--window=")), "1280,1500")
    if not re.match(r"^\d+,\d+$", window):
        sys.exit(f"ROOT ERROR: --window 要写成 1280x1500 这种形状，收到 {window!r}")
    theme = next((a.split("=", 1)[1] for a in argv if a.startswith("--theme=")), "day")
    if theme not in ("day", "night"):
        sys.exit(f"ROOT ERROR: --theme 只认 day/night，收到 {theme!r}")
    only = next((a.split("=", 1)[1].split(",")
                 for a in argv if a.startswith("--only=")), None)
    extra_src = next((a.split("=", 1)[1]
                      for a in argv if a.startswith("--extra=")), "")

    roster = gc.sites()
    picked = [s for s in roster if not only or s[0] in only]
    # --extra 只给这一跑加站，不动 tools/spot-check.sh 那份名单（校验与 glass-census
    # 同一份定义，在 gc.parse_extra 里）。要读形状而不改名册的场合就是这一格：
    # 仓库页那一类样本天生画不完（spot-check.sh 抬头量过：6 张裸页没相邻两张一致），
    # 进不了抽检名单，但这一张表数的是**位置**，一页读一次就够。
    extras = gc.parse_extra(extra_src, roster, "ROOT ERROR")
    picked += extras
    if not picked:
        sys.exit(f"ROOT ERROR: --only {only} 一站都没对上（名单：{[s[0] for s in roster]}）")

    proxy = gc.start_proxy()
    rows, rc = [], 0
    try:
        q = f"?rootprobe{'&night' if theme == 'night' else ''}{'&keepjs' if '--keepjs' in argv else ''}"
        print(f"候选词根普查（{theme} 档{'，?keepjs：站点 JS 现造的浮层才在这一档存在' if '--keepjs' in argv else '，代理摘脚本'}，"
              f"窗口 {window.replace(',', '×')}，上限 {gc.DUMP_TIMEOUT_MS // 1000}s，名单 {len(picked)} 站）")
        print("  注：代理把 preview/skin.css 读在启动那一刻，借来的那只可能在跑上一代；"
              "这一张表数的是**位置**，跟皮肤上没上都无关，但 stray 那一列要读皮肤。\n")
        for tag, url in picked:
            data, err = gc.dump(f"{gc.BASE}{url}{q}", window, oid="ks-root")
            if err:
                print(f"  {tag:18} ⚠ 量不到：{err}")
                rc = 1
                continue
            if not data.get("tokens"):
                # 空名册＝注入落位了但 __TOKENS__ 那一格没替换上，读出来会是"每截词根都安全"
                print(f"  {tag:18} ⚠ 探针没返回词根名册（tokens 空），这次的数不算")
                rc = 1
                continue
            if "parts" not in data or "partsN" not in data:
                # 缺这一格＝借到了没有 famParts 的旧代理；读出来会是"族里一条都没落地"
                print(f"  {tag:18} ⚠ 探针是旧形状（没有 parts/partsN 那一格），这一站的数不算"
                      "——多半是借到了补丁前的代理")
                rc = 1
                continue
            if any("wb" not in t or "idonly" not in t or "idpos" not in t
                   for t in data["tokens"]):
                # 这条守卫是干跑逼出来的：喂它一份**没有 wb 格**的老形状载荷时，原来那版
                # 会安静地把词边界形印成一排 0——而那一排 0 和"这一截词根真的什么都没追到"
                # 在表上长得一模一样。最现实的触发方式是借到了旧代理（它在启动那一刻读进
                # 补丁前的 proxy.py），所以缺格按链路断处理，不按读数处理。
                # idpos 一起进来是同一笔账：新加的那一格缺了也会印成 0。
                print(f"  {tag:18} ⚠ 探针是旧形状（词根记录里没有 wb/idonly/idpos 那一格），"
                      "这一站的数不算——多半是借到了补丁前的代理")
                rc = 1
                continue
            if "raws" not in data:
                # 和 wb/idpos 同一笔账：缺这一格时下面那张【结构形】表会印成一排空的通过，
                # 看起来像"结构形一个都没命中"，实际是借到了补丁前的代理。按链路断处理。
                print(f"  {tag:18} ⚠ 探针是旧形状（没有 raws 那一格），这一站的数不算"
                      "——多半是借到了补丁前的代理")
                rc = 1
                continue
            rows.append((tag, data))
            tot_f = sum(t["pos"].get("fixed", 0) + t["pos"].get("sticky", 0)
                        for t in data["tokens"])
            tot_s = sum(t["n"] for t in data["tokens"]) - tot_f
            wb = [t.get("wb", {}) for t in data["tokens"]]
            w_f = sum(x.get("pos", {}).get("fixed", 0) + x.get("pos", {}).get("sticky", 0)
                      for x in wb)
            w_n = sum(x.get("n", 0) for x in wb)
            print(f"  {tag:18} 子串形命中 {tot_s + tot_f:4}｜浮着 {tot_f:3}｜文档流 {tot_s:4}"
                  f"｜词边界形 {w_n:4}（浮 {w_f:3}）"
                  f"｜穿上玻璃却不在浮层位置 {data.get('strayN', 0)}"
                  f"   ({data['vw']}×{data['vh']}，解档 html={data.get('htmlScheme')}"
                  f"，皮肤 {'上了' if data.get('tok') else '没上 ← stray 那一列不算'})")
            for t in data["tokens"]:
                if not t["n"]:
                    continue
                w = t.get("wb", {})
                for shape, rec in (("子串  ", t), ("词边界", w)):
                    if not rec.get("n"):
                        continue
                    p = rec["pos"]
                    fl = p.get("fixed", 0) + p.get("sticky", 0)
                    top = (rec["still"][0] if rec["still"] else None)
                    print(f"      {t['t']:9} {shape} 命中 {rec['n']:3}  浮 {fl:2}  "
                          f"static/relative {p.get('static', 0) + p.get('relative', 0):3}"
                          f"  abs {p.get('absolute', 0):2}"
                          + (f"  最大误伤 {top['area']}px² <{top['tag']}."
                             f"{top['cls'][:44]}>" if top else ""))
                if t.get("idonly"):
                    # 族今天不匹配 id：这一格是"把 id 也拉进匹配面才会多出来的量"，
                    # 不是这一截词根已经追到的东西，所以单独一行、不混进上面两形。
                    ipos = t.get("idpos", {})
                    ifl = ipos.get("fixed", 0) + ipos.get("sticky", 0)
                    itop = t.get("idtop")
                    print(f"      {t['t']:9} 只靠 id 命中 {t['idonly']}（族不匹配 id，上面两形都没算它）"
                          f"｜浮 {ifl}｜文档流 {t['idonly'] - ifl}"
                          f"｜最大单面 {t.get('idmax', 0)}px²"
                          + (f" <{itop['tag']}{'#' + itop['id'] if itop['id'] else ''}"
                             f".{itop['cls'][:40]}>"
                             f" 父链{'>'.join(itop.get('up', [])[:3]) or '—'}"
                             if itop else ""))
            for r in data.get("raws", []):
                # 结构形那一档多带一格「浮里没穿玻璃」：净新增要看的是这块浮面今天穿没穿上，
                # 只数命中会把族里已经接住的那几块算成新收益（预注册规则 T2）。
                rp = r.get("pos", {})
                rfl = rp.get("fixed", 0) + rp.get("sticky", 0)
                ungl = [x for x in r.get("float", []) if not x.get("glass")]
                print(f"      结构形 {r['label'][:24]:26} 命中 {r['n']:3}｜浮 {rfl:2}｜"
                      f"静止 {rp.get('static', 0) + rp.get('relative', 0):3}｜"
                      f"浮里没穿玻璃 {len(ungl):2}"
                      + (f"｜选择器抛 {r['err']}" if r.get("err") else ""))
                if rfl > len(r.get("float", [])):
                    print(f"        （浮侧点名上限 6，另有 {rfl - len(r.get('float', []))} 块没签名）")
                top = (r.get("still") or [None])[0]
                for x in ungl[:3]:
                    print(f"        未穿 {x['pos']:6} {x['w']}×{x['h']} "
                          f"<{x['tag']}{'#' + x['id'] if x['id'] else ''}.{x['cls'][:56]}>"
                          f" 父链{'>'.join(x.get('up', [])[:3]) or '—'}"
                          + (f"｜最大误伤 {top['area']}px² <{top['tag']}.{top['cls'][:34]}>"
                             if top else ""))
            print(f"      玻璃面合计 {data.get('glassN', 0)}（浮着 {data.get('glassFloat', 0)}）"
                  f"｜族里可归因的选择器条 {data.get('partsN', 0)}"
                  f"｜归不到任何条上的 {data.get('orphanN', 0)}"
                  f"｜被 ks- 规则排掉的 {len(data.get('skipped', []))}")
            for p in data.get("parts", []):
                pl = pos_of(p)
                fl = pl["fixed"] + pl["sticky"]
                st = p["n"] - fl
                samp = (p["still"][0] if p["still"] else
                        (p["float"][0] if p["float"] else None))
                print(f"      族条 {p['p'][:56]:58} 面 {p['n']:3}｜浮 {fl:2}｜静止 {st:3}"
                      f"  最大单面 {samp['area'] if samp else 0}px²"
                      f" <{(samp['tag'] + '.' + samp['cls'][:40]) if samp else '—'}>")
                # 浮面签名：收窄定价要的是"换成精确词后这块还剩不剩"，只有类名答得出来。
                # 探针每截带回前 6 份（proxy.py 的 slice(0, 6)，从前是 2），所以 fl 大于点名牌数时
                # 必须把差额说出来——不然这张表会显得"浮面全在这里"。
                named = p["float"]
                if fl and not named:
                    sys.exit(f"ROOT ERROR: 族条 {p['p'][:44]} 报「浮 {fl}」却一块都没点名"
                             "——签名不在 payload 里，这一站的浮侧读数不可用")
                for s in named:
                    print(f"        浮面 {s['pos']:6} {s['w']}×{s['h']} "
                          f"<{s['tag']}{'#' + s['id'] if s['id'] else ''}.{s['cls'][:88]}>"
                          f" 父链{'>'.join(s.get('up', [])[:3]) or '—'}")
                if fl > len(named):
                    print(f"        （另有 {fl - len(named)} 块浮面没签名，探针每截上限 6 份）")
                # 静止侧只点前 3 块，但每块带父链：嵌套那一问要的不是"有多少块"，
                # 是"这块是不是某一浮面的祖先或后代"——两边都有链才比得出来。
                for s in p.get("still", [])[:3]:
                    print(f"        静止 {s['pos']:6} {s['w']}×{s['h']} "
                          f"<{s['tag']}{'#' + s['id'] if s['id'] else ''}.{s['cls'][:70]}>"
                          f" 父链{'>'.join(s.get('up', [])[:3]) or '—'}")
            for s in data.get("stray", []):
                print(f"      ⚠ 玻璃在文档流上：{s['pos']:8} {s['w']}×{s['h']} "
                      f"<{s['tag']}{'#' + s['id'] if s['id'] else ''}.{s['cls'][:88]}>"
                      f"  由 {len(s.get('by', []))} 条词根追到 "
                      f"{[b[:30] for b in s.get('by', [])]}"
                      f"  bg={s.get('bg')} bf={s.get('bf')}"
                      f" 父链{'>'.join(s.get('up', [])[:3]) or '—'}")
            for s in data.get("orphan", []):
                # 从前这一行只给形状，于是"尺子的洞"和"站点本来就透"两种原因在表上长一样。
                # bg/bf 就是分辨它们的那一格：自家玻璃的 bg 序列化成形是 color(srgb … / 0.86)，
                # 站点自涂的那半既不是这个值、也不在 famParts 扫得到的规则里。
                print(f"      ⚠ 有玻璃却归不到任何族条上：{s['pos']:8} {s['w']}×{s['h']} "
                      f"<{s['tag']}{'#' + s['id'] if s['id'] else ''}.{s['cls'][:70]}>"
                      f"  bg={s.get('bg')} bf={s.get('bf')}"
                      f" 父链{'>'.join(s.get('up', [])[:3]) or '—'}"
                      "（尺子的洞，或站点本来就透——归谁由 ?noskin 对照档定）")
    finally:
        if proxy:
            proxy.terminate()

    if not rows:
        sys.exit("ROOT ERROR: 一站都没量到——这张表的 0 不是「词根都安全」，是链路断了")
    print(f"\n  汇总（{len(rows)}/{len(picked)} 站量到）：每截词根跨站的计数，两形各一张")
    for shape, pick in (("子串形", lambda t: dict(t, still=t["still"])),
                        ("词边界形", lambda t: dict(t.get("wb", {"pos": {}, "still": []}),
                                                    t=t["t"]))):
        tally = {}
        for tag, data in rows:
            for orig in data["tokens"]:
                t = pick(orig)
                acc = tally.setdefault(t["t"], {"n": 0, "float": 0, "stat": 0,
                                                 "abs": 0, "maxstill": 0})
                p = t.get("pos", {})
                fl = p.get("fixed", 0) + p.get("sticky", 0)
                acc["n"] += t.get("n", 0)
                acc["float"] += fl
                acc["stat"] += p.get("static", 0) + p.get("relative", 0)
                acc["abs"] += p.get("absolute", 0)
                acc["maxstill"] = max([acc["maxstill"]] + [s["area"] for s in t.get("still", [])])
        print(f"    【{shape}】")
        for t, a in sorted(tally.items(), key=lambda kv: -kv[1]["float"]):
            # 「文档流」在预注册规则里没分 absolute 那一支，所以两个分母都印出来，
            # 判定时要求两边都过线（更严的那个），不靠挑一个分母过关。
            r1 = f"{a['float'] / a['n'] * 100:.0f}%" if a["n"] else "—"
            den = a["float"] + a["stat"]
            r2 = f"{a['float'] / den * 100:.0f}%" if den else "—"
            print(f"      {t:9} 命中 {a['n']:4}｜浮 {a['float']:3}｜静止 {a['stat']:4}"
                  f"｜绝对 {a['abs']:3}｜浮/全部 {r1:>4}｜浮/(浮+静止) {r2:>4}"
                  f"｜最大误伤 {a['maxstill']:9}px²")
    print("  读法：预注册规则要求「浮 >= 3」且两种分母都 >= 50% 且最大误伤面积 < 100000px²；"
          "浮 >= 3 但静止 > 浮时只许词边界形。这一张表不出红绿。")

    tally_raw = {}
    for tag, data in rows:
        for r in data.get("raws", []):
            acc = tally_raw.setdefault(r["s"], {"label": r["label"], "n": 0, "float": 0,
                                                "stat": 0, "abs": 0, "maxstill": 0,
                                                "unglassed": 0, "sites": 0, "err": ""})
            if r.get("err"):
                acc["err"] = r["err"]
            rp = r.get("pos", {})
            fl = rp.get("fixed", 0) + rp.get("sticky", 0)
            acc["n"] += r.get("n", 0)
            acc["float"] += fl
            acc["stat"] += rp.get("static", 0) + rp.get("relative", 0)
            acc["abs"] += rp.get("absolute", 0)
            acc["unglassed"] += len([x for x in r.get("float", []) if not x.get("glass")])
            acc["sites"] += 1 if r.get("n") else 0
            acc["maxstill"] = max([acc["maxstill"]] + [s["area"] for s in r.get("still", [])])
    print("\n  【结构形】跨站汇总（不按类名，按标签与祖先关系；同一把尺 T1，另加 T2 净新增一列）")
    for k, a in sorted(tally_raw.items(), key=lambda kv: -kv[1]["float"]):
        den = a["float"] + a["stat"]
        r1 = f"{a['float'] / a['n'] * 100:.0f}%" if a["n"] else "—"
        r2 = f"{a['float'] / den * 100:.0f}%" if den else "—"
        print(f"      {a['label'][:26]:28} 命中 {a['n']:4}｜浮 {a['float']:3}｜静止 {a['stat']:4}"
              f"｜绝对 {a['abs']:3}｜站点 {a['sites']:2}/{len(rows)}"
              f"｜浮/全部 {r1:>4}｜浮/(浮+静止) {r2:>4}"
              f"｜最大误伤 {a['maxstill']:9}px²｜浮里没穿玻璃 {a['unglassed']:3}"
              + (f"｜{a['err']}" if a["err"] else ""))
    print("  读法（结构形）：T1 与词根同一条——浮 >= 3 且两种分母都 >= 50% 且最大误伤 < 100000px²；"
          "T2 还要「浮里没穿玻璃」>= 1 才算净新增，全是已穿上的那条只是重复覆盖，不加。"
          "未穿玻璃那一列只数探针点名的前 6 块，站点浮面多于 6 时会少报（上面逐站那行有差额提示）。")

    # 在职那一格的尺子：不按我拼的形状数，按「这一页真在生效的族条」数。
    # 一份面可以被多条词根同时追到（by 的长度 > 1），所以「面」这一列是按词根计格的，
    # 各条相加会 ≥ 全站玻璃面数——这是归因表，不是清点表，两条口径分开读。
    print(f"\n  【族内实形】跨站汇总（同一条词根的正文/副本两份合并计，{len(rows)} 站）")
    pt = {}
    for tag, data in rows:
        for rec in data.get("parts", []):
            acc = pt.setdefault(rec["p"], {"n": 0, "float": 0, "stat": 0, "abs": 0,
                                           "maxstill": 0, "sites": 0})
            pl = pos_of(rec)
            fl = pl["fixed"] + pl["sticky"]
            acc["n"] += rec["n"]
            acc["float"] += fl
            acc["stat"] += pl["static"] + pl["relative"]
            acc["abs"] += pl["absolute"]
            acc["sites"] += 1 if rec["n"] else 0
            acc["maxstill"] = max([acc["maxstill"]] + [s["area"] for s in rec.get("still", [])])
    for k, a in sorted(pt.items(), key=lambda kv: (-kv[1]["float"], -kv[1]["stat"])):
        den = a["float"] + a["stat"]
        r2 = f"{a['float'] / den * 100:.0f}%" if den else "—"
        print(f"      {k[:52]:54} 面 {a['n']:4}｜浮 {a['float']:3}｜静止 {a['stat']:4}"
              f"｜绝对 {a['abs']:3}｜站点 {a['sites']:2}/{len(rows)}"
              f"｜浮/(浮+静止) {r2:>4}｜最大误伤 {a['maxstill']:9}px²")
    print("  读法（在职格）：浮 >= 3 且浮/(浮+静止) >= 50% 且最大误伤 < 100000px² 才原样留；"
          "浮 >= 1 但比例不过线只许收窄形状，收窄后要用同一把尺重跑；浮 == 0 才谈摘除。"
          "absolute 的瞬时弹层算定义外，不算收益。")
    print("  这条尺子的口径是**位置浮着**。2026-10-03「接管常驻条」那一次收进来的两截"
          "（页头那一截、navbar 那一截）按的是**视觉上常驻**，在真站上量到浮 0／静止 6 仍进了族——"
          "对那两截，浮 == 0 本身不是摘除理由，要谈的是「这块底该不该由我们统一」。"
          "浮层与浮面那几截仍按上面那条办。阈值一个没动，动的只是点名这条尺子管到哪一格。")
    sys.exit(rc)


if __name__ == "__main__":
    main()
