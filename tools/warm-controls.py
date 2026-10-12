#!/usr/bin/env python3
"""warm() 的刀：本机起一个"站点"，外链按两支各测一遍（样式表 / 图片走同一个函数）。

  /good.css  200            → 计入"就位"
  /dead.css  站点自己回 404 → 反代回 502：站点自己的坏链，点名之后放行
  /slow.css  答得比上游上限慢 → 反代回 504，而绕开代理直连真站回 200：这一跳的错，必须红
  /good.png /dead.png /slow.png  同样三具，只是这次在 ?imglist 那一支上

为什么图片那一支也要刀：它是后加的那格（css-tricks 首页 24 个坏图请求让同一档连拍定不下来，
spot-check.sh 里记了数）。两支共用 warm() 的同一段取清单/判缺代码，所以"我这一跳失败"这条
在图片支上要是静默烂掉，没有任何真跑会显示出来——真跑那一格本来就是绿的。

W1 和 W4 是同一具夹具的两次读数（一张好、一张站点自己的坏链、一张我这一跳没取到），
唯一差别是 kind。它们必须给出不同的退出码：样式表那一支红，图片那一支只报不拦。
这就是"按资产种类分严重性"这条主张的落点——两支要是被写死成同一种处理（都红或都只报），
这两具里必有一具红。
W1–W3 用 `warm <页>`（css 那一支），W4–W6 用 `warm <页> img`。
两支各自有一具红刀，因为"共用一套归因"不等于"共用一条分支"：清单查询词、汇总行、
以及最后那条 return 1 都按 kind 分岔，只在其中一支上写错的东西，另一支照样绿。

为什么用"慢"而不是"连不上"来造 504：连不上时直连探针也连不上，走的是"这台机器到不了它"
那一支，正好把要证的这一支绕开了。慢是唯一能让"我这跳失败"和"直连成功"同时成立的形状。
上游上限用 KS_PROXY_TIMEOUT 压到 4 秒，直连探针的上限（warm 里写死 -m 25）不动。

为什么这六具要留在仓库里：502/504 分开、以及"图片缺张不拦但清单取不到要拦"这件事，
全凭"红的那几支真的会红"才成立，而真跑那一趟是绿的——没有刀架的话，那条 return 1
可以静默烂掉，下一次再把站点自己的坏链算到皮肤头上，输出看起来还是一样的格式。

warm() 是从 spot-check.sh 里按行界取出来的（^warm() { … ^}），不抄第二份：
抄了一份就变成测副本，真函数改了刀架还绿。取不到或者取出来的那段不像 warm() 就停。

跑法：./tools/warm-controls.py（自己起反代，端口 8750，不碰真跑那条 8748）
"""
import http.server
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE_PORT = 8799
PROXY_PORT = 8750
SLEEP = 12          # 比 KS_PROXY_TIMEOUT=4 慢、比 warm 里直连探针的 -m 25 快
PAGE_CACHE = {}     # 每具刀一个页面路径：反代按 URL 缓存 HTML，复用路径会量到上一具的清单


def _png(size=40):
    """现场生成一张实心 PNG。手写十六进制很容易给出一张"状态码 200 但解不开"的图，
    而那正是这一支要避开的形状——由 PIL 生成，字节是不是 PNG 由解码器说了算。"""
    import io

    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (size, size), (200, 60, 120)).save(buf, "PNG")
    return buf.getvalue()


PNG = _png()


class Site(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body=b"", ctype="text/plain; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/page"):
            # 后缀决定它进哪一份清单：.css 当外链样式表，.png 当图片。
            # 两支共用一个页面形状，warm() 才有同一件事可测——换清单只换查询词，不换链路。
            tags = []
            for p in PAGE_CACHE.get(self.path, []):
                tags.append(f'<link rel="stylesheet" href="{p}">'
                            if p.endswith(".css")
                            else f'<img src="{p}" width="40" height="40">')
            links = "".join(tags)
            self._send(200, f"<html><head>{links}</head><body><p>fixture</p></body></html>"
                       .encode(), "text/html; charset=utf-8")
        elif self.path == "/dead.css" or self.path == "/dead.png":
            self._send(404)
        elif self.path == "/slow.css":
            time.sleep(SLEEP)
            self._send(200, b"body{color:red}", "text/css")
        elif self.path == "/slow.png":
            time.sleep(SLEEP)
            self._send(200, PNG, "image/png")
        elif self.path == "/good.css":
            self._send(200, b"body{color:#123456}", "text/css")
        elif self.path == "/good.png":
            self._send(200, PNG, "image/png")
        else:
            self._send(404)


def extract_warm():
    src = (ROOT / "tools" / "spot-check.sh").read_text(encoding="utf-8")
    m = re.search(r"^warm\(\) \{.*?^\}$", src, re.S | re.M)
    if not m:
        sys.exit("CONTROL ERROR: 没按 `^warm() {` … `^}` 取出函数体——spot-check.sh 的形状变了，"
                 "这把刀取到的是空的东西")
    body = m.group(0)
    for token in ("csslist", "imglist", "return 1", "$direct", "502"):
        if token not in body:
            sys.exit(f"CONTROL ERROR: 取出的那 {len(body.splitlines())} 行里没有 {token!r}，"
                     f"不像 warm() 全体——不敢拿半截函数下结论")
    return body


def run_warm(items, label, want_rc, want, base, kind=None):
    """kind=None 走 `warm <页>`（默认 css 那一支），kind="img" 走 `warm <页> img`。
    两支必须各自有一具红刀：共用一个函数不等于共用一条分支，
    清单查询词写错的那一支（?imglist 拼成 ?imglistx）只会在图片支上红。"""
    page = f"/page-{uuid.uuid4().hex[:8]}"
    PAGE_CACHE[page] = items
    site = http.server.ThreadingHTTPServer(("127.0.0.1", SITE_PORT), Site)
    th = threading.Thread(target=site.serve_forever, daemon=True)
    th.start()
    fn = Path(f"/tmp/ks-warm-{os.getpid()}.sh")
    fn.write_text(extract_warm() + "\n", encoding="utf-8")
    arg = f'warm "$PAGE" {kind}' if kind else 'warm "$PAGE"'
    try:
        env = dict(os.environ, BASE=base, PAGE=f"http://127.0.0.1:{SITE_PORT}{page}")
        r = subprocess.run(["bash", "-c", f'set -u\n. "{fn}"\n{arg}'],
                           capture_output=True, text=True, errors="replace",
                           env=env, timeout=240)
        out = (r.stdout + r.stderr).strip()
        hits = [w for w in want if re.search(w, out, re.S)]
        miss = [w for w in want if w not in hits]
        ok = r.returncode == want_rc and not miss
        print(f"{'OK  ' if ok else 'FAIL'} {label}: rc={r.returncode}(要 {want_rc})"
              f"{'，缺 ' + '、'.join(miss) if miss else ''}")
        for l in out.splitlines():
            print("     " + l[:170])
        return ok
    finally:
        fn.unlink(missing_ok=True)
        site.shutdown()
        site.server_close()


def main():
    body = extract_warm()
    print(f"取出的 warm() 有 {len(body.splitlines())} 行")
    proxy = subprocess.Popen([sys.executable, str(ROOT / "tools" / "proxy.py"), str(PROXY_PORT)],
                             env=dict(os.environ, KS_PROXY_TIMEOUT="4"),
                             stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        for _ in range(40):
            if subprocess.run(["curl", "-sf", "-m", "1",
                               f"http://127.0.0.1:{PROXY_PORT}/healthz"],
                              capture_output=True).returncode == 0:
                break
            time.sleep(0.25)
        else:
            sys.exit("CONTROL ERROR: 反代没在 8750 起来，六具刀没有比对链路")
        base = f"http://127.0.0.1:{PROXY_PORT}/s/"
        dead_base = "http://127.0.0.1:8790/s/"
        all3 = ["/good.css", "/dead.css", "/slow.css"]
        all3i = ["/good.png", "/dead.png", "/slow.png"]
        return [
            run_warm(all3, "W1 样式表：站点自己的 404 放行、我这一跳的慢链判红", 1,
                     [r"FAIL 样式表 1/3 张就位", r"直连真站却回 200", r"/dead\.css"], base),
            run_warm(["/good.css", "/dead.css"], "W2 样式表只有站点的坏链（没有我这一跳的错）→ 放行", 0,
                     [r"样式表 1/2 张就位", r"站点自己的外链就是坏的"], base),
            run_warm(all3, "W3 样式表清单取不到（反代没在听）→ 红", 1,
                     [r"样式表清单没取到"], dead_base),
            run_warm(all3i, "W4 图片：同一具慢链只报不拦（与样式表那一支的差别）", 0,
                     [r"图片 1/3 张就位", r"只报不拦", r"/slow\.png"], base, "img"),
            run_warm(["/good.png", "/dead.png"], "W5 图片只有站点的坏链 → 放行", 0,
                     [r"图片 1/2 张就位", r"站点自己的外链就是坏的", r"/dead\.png"], base, "img"),
            run_warm(all3i, "W6 图片清单取不到 → 仍然红（缺图不拦不等于这一支没有红路径）", 1,
                     [r"图片清单没取到"], dead_base, "img"),
        ]
    finally:
        proxy.terminate()
        proxy.wait(timeout=10)


if __name__ == "__main__":
    res = main()
    print(f"\n{sum(res)}/{len(res)} 具动了")
    sys.exit(0 if all(res) else 1)
