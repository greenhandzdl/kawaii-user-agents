#!/usr/bin/env node
// overlay-probe.mjs —— 量「站点用 JS 现造的浮层」穿没穿上我们的玻璃。
//
// 为什么要有这一把尺：?glassprobe 那一档在 load 那一刻跑一次，读的是页面**静息时**
// 就在场的面；下拉／弹层／遮罩这些要用户点一下才存在的东西，它结构上看不见
// （proxy.py 的 ROOT_PROBE 抬头也记着同一件事）。2026-10-03 之前这一格只靠一次性手工
// 探针，所以我把一个真结论撤回了两次——页里合成的 .click() 打不开任何触发器，我就判了
// "复现不了"，而 CDP 的真键盘事件 `/` 一按，GitHub 的搜索面板整套穿上了玻璃。
// 这一档把那条路钉下来：可信事件只有 Input.dispatch* 这一条路。
//
// 判据一份都不抄：把 tools/proxy.py 里的 GLASS_PROBE 整段读出来，在同一个页面里跑两遍
// （静息一遍、每次真事件之后一遍），两遍的**面集合之差**就是"被点出来的浮层"。
// 所以这里的 glass 那位和 ?glassprobe 那一档逐字同一条，改那条就改这里。
//
// 跑法见 README「本地自检」那节；需要一个起着 tools/proxy.py 的 8748。
// 默认不写任何产物文件（KS_OVERLAY_JSON 指了路径才落盘）。

import { execFileSync, spawn } from "node:child_process";
import { readFileSync, mkdtempSync, rmSync, writeFileSync, createWriteStream, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");
const CHROME = process.env.KS_CHROME ||
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = Number(process.env.KS_OVERLAY_PORT || 8748);
const MAX_CLICKS = Number(process.env.KS_OVERLAY_CLICKS || 3);
// KS_OVERLAY_SHOT=<目录>：把"点开才出现"的那一格当场出一张图。DOM 读数说不上"看着和合不合"，
// 而这一档的浮层只有真键盘／真点击之后才在，无头 --screenshot 够不着，只能在这条链路里出图。
const SHOT_DIR = process.env.KS_OVERLAY_SHOT || "";
// #155 的重试上限。给成环境变量是为了能下一把正控制：KS_OVERLAY_OPEN_TRIES=1 退回
// "只按一次"的旧读法，同一站同一档应当能读到比默认更少的块——读不出差别就是空转判据。
const OPEN_TRIES = Number(process.env.KS_OVERLAY_OPEN_TRIES || 3);
const KEEP_DIR = process.env.KS_OVERLAY_DEBUG === "1";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// —— 唯一的那条判据：从 tools/proxy.py 里取 GLASS_PROBE 原文 ————————————
// 同时取它里面那**一条** glass 表达式（`bf.indexOf('blur') … && /^color\(srgb/…`）。
// 下面【浮层直读】那一格要判的不是 fixed 面，GLASS_PROBE 的普查在位置那一步就筛掉了，
// 所以那一格需要把同一条判据单独用在候选元素上——从原文里抠出来用，不抄第二份。
function probeSource() {
  const raw = readFileSync(join(ROOT, "tools/proxy.py"), "utf8");
  const js = execFileSync("python3", ["-c",
    "import sys; sys.path.insert(0, 'tools'); import proxy; sys.stdout.write(proxy.GLASS_PROBE)",
  ], { cwd: ROOT, encoding: "utf8" });
  if (!js.includes("glass:") || js.length < 800)
    throw new Error("没从 tools/proxy.py 取出 GLASS_PROBE——它的写法变了要同时改这里");
  const m = /glass: (bf\.indexOf\('blur'\)[^\n]*?),\n/.exec(raw);
  if (!m) throw new Error("没从 tools/proxy.py 抠到 glass 那一条——它的写法变了要同时改这里");
  // token 名也从同一个定义处抠：静息档的轻形回退要读它，抄第二份迟早和 CSS 分家。
  const t = /getPropertyValue\(['"](--ks-[a-z0-9-]+)['"]\)/.exec(raw);
  if (!t) throw new Error("没从 tools/proxy.py 抠到 token 名——它的写法变了要同时改这里");
  return { js, expr: m[1], tokName: t[1] };
}

const PROBE = probeSource();

// 【浮层直读】：不看位置，专挑"语义上是浮层"的那几形，报每一形穿上玻璃没有。
// 为什么要有这一格：GLASS_PROBE 在 `s.position !== 'fixed' && !== 'sticky'` 那一步
// 就把面筛掉了，而**开起来的原生 <dialog> 计算位置是 absolute**（UA 样式表如此），
// 于是"族的第一位成员 dialog"在普查那一档里结构上读不到。这一格补的就是这一眼。
const OVERLAY_SCAN = `(function(){
  var glass = function (bf, bg) { return __EXPR__; };
  var sel = 'dialog[open], [role="dialog"], [role="alertdialog"], [aria-modal="true"], ' +
            '[role="menu"], [role="listbox"], [role="tooltip"], [popover]';
  var out = [];
  for (var el of document.querySelectorAll(sel)) {
    var s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') continue;
    var r = el.getBoundingClientRect();
    if (r.width * r.height < 3200) continue;
    out.push({
      tag: el.tagName.toLowerCase(), pos: s.position,
      role: el.getAttribute('role') || (el.tagName === 'DIALOG' ? 'dialog' : ''),
      modal: el.tagName === 'DIALOG' && el.open && !!el.ownerDocument && el.matches(':modal'),
      label: (el.getAttribute('aria-label') || '').slice(0, 40),
      w: Math.round(r.width), h: Math.round(r.height),
      bg: s.backgroundColor.slice(0, 64),
      bf: (s.backdropFilter || s.webkitBackdropFilter || 'none').slice(0, 40),
      // 遮罩那一格：开起来的原生 <dialog> 背后那层 ::backdrop 只有按伪元素读才拿得到，
      // 而 §4 那条遮罩规则（含 class 形五支）到底在真站上涂没涂到粉，就住在这一列里。
      // 只给原生弹窗读：非 dialog 的站点自画遮罩本来就是普通 div，它的底色已经在 bg 里。
      scrim: (el.tagName === 'DIALOG' && el.open)
        ? (function () {
            var b = getComputedStyle(el, '::backdrop');
            return (b.backgroundColor || '').slice(0, 48) +
                   '｜bf=' + (b.backdropFilter || b.webkitBackdropFilter || 'none').slice(0, 24);
          })()
        : '',
      ink: s.color, txt: (el.innerText || '').replace(/\\s+/g, '').length,
      cls: (el.getAttribute('class') || '').replace(/\\s+/g, ' ').slice(0, 60)
    });
    out[out.length - 1].glass = glass(out[out.length - 1].bf, out[out.length - 1].bg);
  }
  return out;
})()`;

async function overlayScan(c) {
  const list = await c.value(OVERLAY_SCAN.replace("__EXPR__", PROBE.expr));
  return Array.isArray(list) ? list : [];
}

// KS_S4B_WITNESS=1：真事件之后现读「玻璃面里的控件壳」那一形——命中数、面积，以及
// **实际落地的底色**。为什么要现读：
//   ① 这一形的读者只在按下 / 并输入之后才在（未聚焦时 GitHub 那几枚壳里根本没有 input，
//      形状命中从 3 掉到 0），所以命中数必须与出图同一个事件之后、同一个进程里取；
//   ② "补丁到没到这一页"不能只看盘上字节——底色要从被抽样的那几个节点上读出来才算。
// FACE 不写死：从 CSSOM 现取 §4c 那条（声明体里同时含 --kGlass 与 backdrop-filter 的
// 唯一一块），取到几条、选择器多长都一起印出来，多于一条就当仪器失效。
const S4B_WITNESS = `(function(){
  var SH=':is([class*="input" i],[class*="search" i],[class*="field" i]):not(:is(input,textarea,select))';
  var FACE='', faceCount=0, multi=false, s4bRule=false, sheets=0;
  for (var sh of document.styleSheets) {
    var rules=null; try { rules=sh.cssRules } catch(e) { continue }
    sheets++;
    for (var r of rules) {
      if (!r || r.type !== 1 || !r.selectorText) continue;
      var txt=r.cssText||''; var body=txt.slice(txt.indexOf('{'));
      if (body.indexOf('--kGlass')>=0 && body.indexOf('backdrop-filter')>=0) {
        faceCount++;
        if (!FACE) FACE=r.selectorText; else if (FACE!==r.selectorText) multi=true;
      }
      if (body.indexOf(':has(:is(input')>=0) s4bRule=true;
    }
  }
  if (multi || !FACE) return {err: multi?'FACE_MULTI':'FACE_MISS', faceCount:faceCount};
  var third=FACE+' '+SH+':not('+FACE+')';
  var s4b=third+':has(:is(input,textarea,[role="textbox"],[role="searchbox"],[role="combobox"]))';
  // s4c＝同一形但**不写** :not(面)——落地时面选择器只抄一遍，副本计数守卫只 +1 而不是 +2。
  // 这一格问的就是那道排除在有 :has(input…) 之后还剩不剩下读者：剩下＝必须抄两遍。
  var s4c=FACE+' '+SH+':has(:is(input,textarea,[role="textbox"],[role="searchbox"],[role="combobox"]))';
  var hits=[], px2=0, s4cN=0, s4cInFace=0, s4cCls=[];
  for (var el of document.querySelectorAll(s4c)) {
    var s2=getComputedStyle(el), r2=el.getBoundingClientRect();
    if (r2.width*r2.height<=0 || s2.display==='none' || s2.visibility==='hidden' || s2.opacity==='0') continue;
    s4cN++;
    if (el.matches(FACE)) { s4cInFace++; s4cCls.push(el.tagName.toLowerCase()+'.'+(el.getAttribute('class')||el.getAttribute('role')||'').slice(0,30)); }
  }
  for (var el of document.querySelectorAll(s4b)) {
    var s=getComputedStyle(el), rc=el.getBoundingClientRect();
    if (rc.width*rc.height<=0 || s.display==='none' || s.visibility==='hidden' || s.opacity==='0') continue;
    px2+=Math.round(rc.width*rc.height);
    hits.push({tag:el.tagName.toLowerCase(),
      cls:(el.getAttribute('class')||'').replace(/\\s+/g,' ').slice(0,40),
      w:Math.round(rc.width), h:Math.round(rc.height), bg:s.backgroundColor.slice(0,48),
      inFace: el.matches(FACE)});
  }
  return {faceLen:FACE.length, faceCount:faceCount, s4bRule:s4bRule, sheets:sheets,
    thirdN:document.querySelectorAll(third).length, s4bN:hits.length, px2:px2, hits:hits,
    s4cN:s4cN, s4cInFace:s4cInFace, s4cCls:s4cCls};
})()`;

async function s4bWitness(c) {
  try {
    const w = await c.value(S4B_WITNESS);
    return w && typeof w === "object" ? w : { err: "非对象" };
  } catch (e) { return { err: String(e.message).slice(0, 70) }; }
}

// —— 名单：github 首页 + spot-check.sh 那份 SITES（同一个取法，不抄第二份）——
// 首页为什么单独加：它被 spot-check 换出去了（那一格的读数对取样窗口零余量），
// 但它正是"JS 现造浮层"最多的那一站，这一档要问的就是它。
function sites() {
  const src = readFileSync(join(ROOT, "tools/spot-check.sh"), "utf8");
  const m = src.match(/^SITES="\n([\s\S]*?)"$/m);
  if (!m) throw new Error("没按 `^SITES=\"` … `^\"` 从 spot-check.sh 取出名单");
  const out = [["github-home", "https://github.com/"]];
  for (const line of m[1].split("\n")) {
    if (!line.includes("|")) continue;
    const [tag, url] = line.split("|");
    out.push([tag.trim(), url.trim()]);
  }
  // KS_OVERLAY_ONLY=docs-github,mdn —— 只跑点名的那几格（调试用；整跑时不设）
  const only = (process.env.KS_OVERLAY_ONLY || "").split(",").map((s) => s.trim()).filter(Boolean);
  return only.length ? out.filter(([t]) => only.includes(t)) : out;
}

// —— 真事件触发器 ——————————————————————————————————————————————————
// 刻意不在页里跑 JS 去点（.click() 不可信，2026-10-03 量过：0/15 枚触发器打得开），
// 也不写站点私有类名：这一档要问的就是"用户真点得开的浮层"。
// 点击候选按**可访问名**筛，且排除带 href 的（那是链接，点了会跳走）。
// 真用户按下 `/` 之后是**接着打字**的：GitHub 的搜索面板在按下 `/` 那一格就出现，
// docs.github 那一个要 focus 之后才把 <dialog> 打开。所以这一档把"按下＋打几个字"
// 当成一枚触发器，而不是只按一下就判"这站没浮层"。
async function typeChars(c, text) {
  for (const ch of text) {
    const vk = ch.toUpperCase().charCodeAt(0);
    await c.cmd("Input.dispatchKeyEvent", { type: "keyDown", key: ch, code: `Key${ch.toUpperCase()}`,
      text: ch, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk });
    await c.cmd("Input.dispatchKeyEvent", { type: "keyUp", key: ch, code: `Key${ch.toUpperCase()}`,
      windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk });
  }
}

function keyTriggers() {
  const k = (key, code, vk, modifiers, text, then) => ({
    label: `key:${key}${then ? "+type" : ""}`,
    isKey: true,   // 只有键盘那一格重试：#155 的根因（水合没完、事件被吞）在这条路上量到，
                   // 而每多试一次要多跑一遍 lightFaces（重站点 15–25s），点击那一格吃不起这个钱。
    async fire(c) {
      await c.cmd("Input.dispatchKeyEvent", { type: "keyDown", key, code, text,
        ...(modifiers ? { modifiers } : {}), windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk });
      await c.cmd("Input.dispatchKeyEvent", { type: "keyUp", key, code,
        ...(modifiers ? { modifiers } : {}), windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk });
      if (then) await typeChars(c, then);
    },
    async close(c) { await typeChars(c, "\b".repeat(0)); },
  });
  return [k("/", "Slash", 191, 0, "/", "map"), k("?", "Slash", 191, 4, "?", null)];
}

const CLICK_PROBE = `(function(){
  var WORD = /(search|menu|more|option|filter|cookie|theme|help|language|product|explore|topic|tutorial|导航|菜单|搜索|登录|语言|示例)/i;
  var out = [], seen = {};
  var els = document.querySelectorAll('button, [role="button"], summary, [aria-haspopup]');
  for (var el of els) {
    if (el.href) continue;
    if (el.closest('dialog[open]')) continue;
    var r = el.getBoundingClientRect();
    if (r.width < 16 || r.height < 12) continue;
    if (r.top < 0 || r.bottom > innerHeight) continue;
    var name = ((el.getAttribute('aria-label') || '') + ' ' + (el.title || '') + ' ' +
                (el.innerText || '')).trim().slice(0, 60);
    if (!WORD.test(name)) continue;
    var id = name + '|' + Math.round(r.left) + ',' + Math.round(r.top);
    if (seen[id]) continue;
    seen[id] = 1;
    out.push({ name: name, x: r.left + r.width / 2, y: r.top + r.height / 2 });
    if (out.length >= __N__) break;
  }
  return out;
})()`;

function clickTriggers(list) {
  return list.map((t) => ({
    label: `click:"${t.name.slice(0, 24)}"`,
    async fire(c) {
      for (const type of ["mouseMoved", "mousePressed", "mouseReleased"])
        await c.cmd("Input.dispatchMouseEvent", { type, x: t.x, y: t.y, button: "left", clickCount: 1 });
    },
    // 收场用 Esc：点了别的按钮时，上一格打开的那层得先关掉，不然"新面"会算到错的触发器头上
    async close(c) {
      for (const type of ["keyDown", "keyUp"])
        await c.cmd("Input.dispatchKeyEvent", { type, key: "Escape", code: "Escape",
          windowsVirtualKeyCode: 27, nativeVirtualKeyCode: 27 });
    },
  }));
}

// ————————————————————————————————— CDP 客户端 ——————————————————————————
class Cdp {
  constructor(ws) {
    this.ws = ws; this.n = 0; this.waiters = new Map(); this.events = [];
    this.net = [];   // Network.* 另存一份：waitEvent 会按名字摘走 events，那一格不该把取数失败的历史一起摘走
    ws.addEventListener("message", (e) => {
      const msg = JSON.parse(e.data);
      if (msg.id && this.waiters.has(msg.id)) {
        const w = this.waiters.get(msg.id); this.waiters.delete(msg.id);
        msg.error ? w.bad(new Error(msg.error.message)) : w.ok(msg.result);
      } else if (msg.method) { this.events.push(msg); if (msg.method.startsWith("Network.")) this.net.push(msg); }
    });
  }
  static async connect(url) {
    const ws = new WebSocket(url);
    SOCKETS.push(ws);
    await new Promise((res, rej) => {
      ws.addEventListener("open", res, { once: true });
      ws.addEventListener("error", rej, { once: true });
    });
    return new Cdp(ws);
  }
  cmd(method, params = {}, ms = 9000) {
    const id = ++this.n;
    const send = new Promise((resolve, reject) => {
      this.waiters.set(id, { ok: resolve, bad: reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
    // 点了会跳页的触发器之后，执行上下文被丢掉，Runtime.evaluate 可以 indefinitely 挂在那儿
    // ——2026-10-03 第一跑就是被这一格卡住（单站 7 分钟不出数）。每个调用都带表。
    return Promise.race([send, new Promise((resolve) =>
      setTimeout(() => { this.waiters.delete(id); resolve(method === "Runtime.evaluate" ? null
        : { __timeout: true }); }, ms))]);
  }
  // #161：浮层的内容有时靠页里自己的一次取数才挂载（DocSearch 打 Algolia 那一跳就是这一形）。
  // 那一跳断了的时候，「没有新的面」既可以是「这站没有浮层」也可以是「浮层的 feeder 没回数」，
  // 旧版两个读法印在同一行。按「没读到不并入没有」的既有纪律，这一格单独成档。
  // 只认 Fetch／XHR 两型：Script 那一型在真站上多半是站家的统计脚本，收进来会把每一站都判成断。
  failedFeeds(from) {
    const url = new Map();
    const out = [];
    for (const e of this.net.slice(from)) {
      const q = e.params || {};
      if (e.method === "Network.requestWillBeSent") url.set(q.requestId, (q.request || {}).url || "?");
      else if (e.method === "Network.loadingFailed" && /^(Fetch|XHR)$/.test(q.type || ""))
        out.push(q.type + ":" + String(url.get(q.requestId) || "?").slice(0, 64) +
          "(" + (q.errorText || q.reason || "?") + ")");
    }
    return out;
  }
  async waitEvent(name, ms) {
    const t0 = Date.now();
    while (Date.now() - t0 < ms) {
      if (this.events.some((e) => e.method === name)) {
        this.events = this.events.filter((e) => e.method !== name);
        return true;
      }
      await sleep(120);
    }
    return false;
  }
  // ms 单独给：跑一遍 GLASS_PROBE 在 30 万节点的站上要十几秒（9s 那格会把它判成
  // "探针没落位"，而页面其实画得好好的——2026-10-03 五站同报这一错，先怀疑表太紧）。
  async value(expression, ms = 9000) {
    const r = await this.cmd("Runtime.evaluate",
      { expression, returnByValue: true, awaitPromise: true }, ms);
    if (r === null) return undefined;              // 上下文没了/超时：交回调用侧按"这格没读到"办
    if (r.exceptionDetails) {
      const msg = String(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
      if (/Execution context was destroyed|Cannot find context/.test(msg)) return undefined;
      throw new Error("页内脚本异常: " + msg.slice(0, 160));
    }
    return r.result.value;
  }
}

// 读 #ks-glass。探针自己挂在 load 上，所以第一次读不到时把**同一段原文**再跑一遍
// （不抄第二份判据），并把这次读取绑到当前 URL 上——跳页了要能认出来。
// 每读一次都要**先重跑一遍探针**再取回。GLASS_PROBE 把结果写进 `<output id="ks-glass">`
// 并留在那儿，所以"先读、读不到才跑"那个写法会把 load 那一刻的快照一路读到底——
// 浮层出现之后那一格读到的还是静息的名册，"没有新面"是必然读数。
// 2026-10-03 第一跑就是这样把 GitHub 的搜索面板从 [fixed] 通道里漏掉的（[语义] 通道
// 每次都现场跑，所以它看得见同一个面板——两条通道打架，才抓出这一格）。
// 上限按**次数**给，不按墙上时间给：30 万节点的站跑一遍 GLASS_PROBE 要 15–25s，而 12s 的
// 墙上时间上限连第一次都没跑完就判"页面没画完"——2026-10-03 同一段代码在 clicks=1 那跑里
// mdn/features/w3schools 都回数了，clicks=2 这跑四站同报"没落位"，差别只在表太紧。
// 按次数给之后，"回数了没有"跟页有多重脱钩，读数的口径才站得住。
async function readFaces(c, probe, tries) {
  const run = probe.replace("if (document.readyState === 'complete') run();", "run();")
    .replace("else window.addEventListener('load', run);", "");
  const grab = () => c.value(`(function(){var o=document.getElementById('ks-glass');
    return o && o.textContent ? o.textContent : '';})()`);
  for (let i = 0; i < tries; i++) {
    await c.value(run, 25000);
    const raw = await grab();
    if (typeof raw === "string" && raw) {
      const d = JSON.parse(raw);
      d.pageUrl = (await c.value("location.href")) || "?";
      d.keys = new Set(d.faces.map(faceKey));
      return d;
    }
    await sleep(500);
  }
  return null;
}

function overlayKey(o) {
  return `${o.tag}|${o.role}|${o.cls.slice(0, 40)}|${o.w}x${o.h}`;
}

// 轻形面集合：和 GLASS_PROBE 同样的位置／尺寸／可见性筛，同一条 glass 判据（从 proxy.py 抠），
// 但**不算 cover、不数衬底**——那两个循环要对着每块面的全部子孙各跑一遍 getComputedStyle，
// 在 MDN / docs.github / w3schools 这种量级的页面上要几十秒，把事件之间本该几秒一次的
// 重读拖成了超时（2026-10-03 那五站同报「页面没画完」就是这个）。
// 所以这一档分工：静息那一格用 GLASS_PROBE 原形（和 glass-census 逐字同源，可比），
// 事件之间用轻形（它只答「这块面穿上玻璃没有」，答不了「玻璃底下衬的是谁」）。
const LIGHT_FACES = `(function(){
  var glass = function (bf, bg) { return __EXPR__; };
  var faces = [];
  for (var el of document.body ? document.body.querySelectorAll('*') : []) {
    var s = getComputedStyle(el);
    if (s.position !== 'fixed' && s.position !== 'sticky') continue;
    var r = el.getBoundingClientRect();
    if (r.width < 40 || r.height < 16 || r.width * r.height <= 400) continue;
    if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') continue;
    if (r.bottom <= 0 || r.top >= innerHeight || r.right <= 0 || r.left >= innerWidth) continue;
    var bf = s.backdropFilter || s.webkitBackdropFilter || 'none';
    faces.push({
      tag: el.tagName.toLowerCase(), id: el.id || '',
      cls: (el.getAttribute('class') || '').replace(/\\s+/g, ' ').slice(0, 90),
      pos: s.position, w: Math.round(r.width), h: Math.round(r.height),
      x: Math.round(r.left), y: Math.round(r.top),
      txt: (el.innerText || '').replace(/\\s+/g, '').length,
      bg: s.backgroundColor.slice(0, 64), bf: bf.slice(0, 40), ink: s.color,
      glass: glass(bf, s.backgroundColor)
    });
  }
  return faces;
})()`;

async function lightFaces(c) {
  const faces = await c.value(LIGHT_FACES.replace("__EXPR__", PROBE.expr), 25000);
  if (!Array.isArray(faces)) return null;
  const keys = new Set(faces.map(faceKey));
  // pageUrl 必须有：点了会跳页的触发器要能被认出来，不然新页面上那一片面会被当成
  // "被点出来的浮层"，是个假读数。
  const pageUrl = (await c.value("location.href", 4000)) || "?";
  return { faces, keys, pageUrl, n: faces.length, g: faces.filter((f) => f.glass).length };
}

// 静息那一格：先要全形读（它跟 glass-census 逐字同源，数出来的面能与普查那张表对账），
// 全形 3 次都没回数才退轻形——轻形只答"穿没穿上玻璃"，答不了"玻璃底下衬的是谁"（没有 盖% 列），
// 但它一趟不遍历子孙，重页上不会被拖成超时。两档都得**印出来是哪一档**：口径不同的数
// 不能混进同一句话里读。token／scheme 在轻形档另配一次小表达式读，名从 proxy.py 那一个定义处抠。
async function restFaces(c, probe, tries) {
  const heavy = await readFaces(c, probe, tries);
  if (heavy) return { ...heavy, form: "全形" };
  const light = await lightFaces(c);
  if (!light) return null;
  const tok = await c.value(
    `getComputedStyle(document.documentElement).getPropertyValue('${PROBE.tokName}')`, 6000);
  const scheme = await c.value(
    "getComputedStyle(document.documentElement).colorScheme", 6000);
  return { n: light.n, g: light.g, faces: light.faces, keys: light.keys, pageUrl: light.pageUrl,
    tok: tok || "", htmlScheme: scheme || "undefined", form: "轻形" };
}

function faceKey(f) {
  return `${f.tag}|${f.id}|${f.cls.slice(0, 40)}|${f.w}x${f.h}|${f.x},${f.y}`;
}

// 静息→事件之后，多出来的那些面里挑出"浮层"：只认 fixed（absolute 的菜单壳这一档
// 看不见，同 ROOT_PROBE 抬头记的那格），且面积 >=3200px²（比 GLASS_PROBE 自己的
// 400px² 收紧一点，免得把弹出来的小徽标当浮层报）。
function appeared(before, after) {
  const out = [];
  for (const f of after.faces) {
    if (before.keys.has(faceKey(f))) continue;
    if (f.pos !== "fixed") continue;
    if (f.w * f.h < 3200) continue;
    out.push(f);
  }
  return out;
}

// ours＝glass 那位（来自 GLASS_PROBE，逐字同一条）；risk＝没穿上且面上的墨是站家浅色
// ⇒ 我们的地面/别家的底配上别家的浅字，肉眼读不动的那一格。
function inkLum(ink) {
  const m = /rgba?\(\s*(\d+),\s*(\d+),\s*(\d+)/.exec(ink || "");
  return m ? (0.2126 * +m[1] + 0.7152 * +m[2] + 0.0722 * +m[3]) : 0;
}

// 沿 und 链往下找第一层"不透明且不是站点画的图"的底；找不到返回 null。
// null 既不给 risk 开火，也不能判成"底是深的所以没事"——那是把"算不出"读成"没事"。
function groundLum(f) {
  for (const u of f.und || []) {
    if (u.b.startsWith("img:")) continue;
    const m = /^rgba?\(\s*(\d+),\s*(\d+),\s*(\d+)(?:\s*,\s*([\d.]+))?\s*\)$/.exec(u.b);
    if (!m) continue;
    const a = m[4] === undefined ? 1 : Number(m[4]);
    if (a < 0.85) continue;
    return 0.2126 * +m[1] + 0.7152 * +m[2] + 0.0722 * +m[3];
  }
  return null;
}

// ours＝glass 那位（来自 GLASS_PROBE，逐字同一条）；risk＝没穿上、面上浅字有字、且衬的底也是浅色。
// 只看墨不行：站点刻意画的深色 hero 配白字读得动（2026-10-06 github-home 两行假火）。
function classify(f) {
  const ours = !!f.glass;
  const lightInk = inkLum(f.ink) > 150 && f.txt > 0;
  const g = groundLum(f);
  return {
    ours,
    risk: !ours && lightInk && g !== null && g > 150,
    unknown: !ours && lightInk && g === null,
  };
}

// 代理的路径形是 /s/https://site/path（**不转义**；转义了代理回 400，而 400 那页在页里
// 长得像"这站一个浮层都没有"—— 2026-10-03 第一跑就是整场空的）。所以先直接问代理一次：
// 这一档到底有没有把皮肤注进这一页。没注就整格不算、不进触发器循环——皮肤没上时
// "0 块穿上玻璃"是必然读数，不是证据（这一条是那一跑教的）。
async function preflight(target) {
  try {
    const res = await fetch(target, { signal: AbortSignal.timeout(30000) });
    const body = await res.text();
    if (!res.ok) return `代理回 ${res.status}`;
    if (!body.includes("ks-skin")) return "代理回包里没有 ks-skin（皮肤没注进来）";
    return null;
  } catch (e) { return `代理取不到：${String(e && e.message || e).slice(0, 60)}`; }
}

// KS_OVERLAY_NIGHT=1 的读法只留这一处：URL 拼什么、图例印哪一档，都从它派生——
// 之前图例那句是硬编码的「白天」，跑夜档时标签与读数不合（2026-10-12 现读）。
const NIGHT = process.env.KS_OVERLAY_NIGHT === "1";
const BAND_NAME = NIGHT ? "夜晚" : "白天";

async function probeSite(c, base, tag, url, probe) {
  // 同一格改跑夜晚档＝代理的 ?night 旋钮。默认不设＝白天档，
  // 出货名册与既有那批图都不受影响。两档要配对着读，别拿一档的 0 说另一档的事。
  const night = NIGHT ? "&night" : "";
  const target = `${base}${url}?keepjs${night}`;
  const bad = await preflight(target);
  if (bad) return { tag, url: target, err: `${bad} —— 整格不算` };
  await c.cmd("Page.navigate", { url: target });
  await c.waitEvent("Page.loadEventFired", 30000);
  let snap = await restFaces(c, probe, 3);
  if (!snap) return { tag, url: target,
    err: "静息格全形读 3 次（每次上限 25s）加一次轻形读都没回数 —— 这格按链路断办，不算\"这站没有浮层\"" };
  if (!snap.tok) return { tag, url: target,
    err: "页里 token 缺（preflight 说有皮肤、页内却解不出来）—— 整格不算" };
  // 静息那一格只认这一次全形读，不能被后面的轻形读顶掉：轻形带 n/g/faces/pageUrl，
  // 但**不带 tok／htmlScheme**——2026-10-03 让 `snap = now` 一路跟着循环走，结果最后那次
  // 轻形读冒充了"静息"，mdn 和 github-features 两站被印成「token 缺｜scheme undefined」，
  // 而同一行里 3/4 块面正穿着我们那面粉（皮肤显然上了）。那是本页的形状缺格，
  // 不是页里没皮肤；照着"缺＝整格不算"办，两站的读数被自家尺子作废掉了。
  const restSnap = snap;
  const restOv = await overlayScan(c);      // 静息那一格要在触发器之前取，别拿收尾状态冒充
  let ovs = restOv;
  let ovKeys = new Set(ovs.map(overlayKey));
  const rows = [];
  const unread = [];
  let firedN = 0;   // 真事件发出去了几次：一次都没发出去的「零新面」不能读成「这站没开」
  let triggers = keyTriggers();
  const clicks = (await c.value(CLICK_PROBE.replace("__N__", String(MAX_CLICKS)))) || [];
  triggers = triggers.concat(clickTriggers(clicks));
  const netFrom = c.net.length;   // 只数触发器之后的取数，页头那批脚本／样式不算进来
  for (const t of triggers) {
    const wasOv = ovKeys;
    const was = (await lightFaces(c)) || restSnap;   // 就在按之前现读一遍，别拿上一格的收尾冒充
    // #155：一次按下没开出新面 ≠ 这站没有"点开才出现"的浮层。2026-10-11 白天档
    // github-home 第一跑读 0 块、重试读到 6 块（4 块穿玻璃），根因是站点水合还没完，
    // 键盘事件被吞。所以下限按"试过几次"给，重试时把按下原样再来一遍（只在零新面时再来，
    // 已经开着的浮层不会被第二下关掉——第二下要么同一格要么什么都没多出来）。
    let now = null;
    let fired = false;
    for (let attempt = 0; attempt < (t.isKey ? OPEN_TRIES : 1); attempt++) {
      try { await t.fire(c); fired = true; } catch (e) { break; }
      await sleep(900 + attempt * 900);
      now = await lightFaces(c);
      if (now && appeared(was, now).length) break;
    }
    if (!fired) continue;
    firedN++;
    if (!now) continue;   // 这一格没读到，不算"没出现浮层"

    // #73：「真事件之后没有新的面」有两种形状——站点根本没开，和开了但这把尺子看不见
    // （appeared() 那道 pos !== "fixed" 把 absolute 的原生 dialog 按构造筛掉了）。
    // 这一行不问玻璃、不问对比，只点名原生 <dialog> 此刻开没开、走没走 showModal、
    // JS 有没有往里面填子节点——把"探针外"这个说法换成一个能复跑的读数。
    if (process.env.KS_OPEN_WITNESS === "1") {
      const ow = await c.value(`(function(){
        var d = [].slice.call(document.querySelectorAll('dialog'));
        return JSON.stringify(d.map(function (x) {
          return { label: (x.getAttribute('aria-label') || '').slice(0, 32),
                   open: !!x.open, modal: x.matches(':modal'), kids: x.querySelectorAll('*').length };
        }));
      })()`);
      console.error(`OPEN ${tag} ${t.label} ${ow}`);
    }

    // 页址读回来是 "?" 这个占位（lightFaces 的 `|| "?"`）＝上下文没了或求值超时，
    // 这一格既不能印成"点了跳走"（把链路断说成站点行为），也不能算进"没有新面"
    // （把零证据说成零浮层）。2026-10-06 github-home 那跑就是被这条冒充成"2 次跳走"的。
    if (now.pageUrl === "?" || was.pageUrl === "?") {
      unread.push(t.label);
      continue;
    }
    if (now.pageUrl !== was.pageUrl) {
      rows.push({ via: t.label, navigated: true, to: now.pageUrl });
      continue;
    }
    ovs = await overlayScan(c);
    ovKeys = new Set(ovs.map(overlayKey));
    if (process.env.KS_S4B_WITNESS === "1") {
      console.error(`S4B ${tag} ${t.label} ${JSON.stringify(await s4bWitness(c))}`);
    }
    const fresh = appeared(was, now);
    if (fresh.length && SHOT_DIR) {
      // 出图只是取证，不参与判定：判据仍然读 DOM，图给人看
      try {
        mkdirSync(SHOT_DIR, { recursive: true });
        const f = join(SHOT_DIR, `${tag}__${t.label.replace(/[^\w.-]+/g, "_")}.png`);
        const s = await c.cmd("Page.captureScreenshot", { format: "png" });
        writeFileSync(f, Buffer.from(s.data, "base64"));
        console.error(`SHOT ${f}（新面 ${fresh.length} 块）`);
      } catch (e) { console.error(`SHOT FAIL ${tag} ${t.label}：${e.message}`); }
    }
    if (fresh.length) {
      // 轻形那一档没有 盖%／衬底 两列，而「玻璃底下衬的是不是我们的粉」这一问只有在页里
      // 才量得出来（GLASS_PROBE 的 und 那一串）。原先事件档只用轻形，于是被点出来的浮层
      // ——恰好是 GitHub 那类站点浮层的全部来源——结构上回答不了用户那一问。这里对
      // "新出现的面"补一次全形读，按 faceKey 把那两列并回来；静息档那一次全形读照旧只跑一次。
      const heavy = await readFaces(c, probe, 2);
      if (heavy) {
        const by = new Map(heavy.faces.map((f) => [faceKey(f), f]));
        for (const f of fresh) {
          const h = by.get(faceKey(f));
          if (h) { f.cover = h.cover; f.und = h.und; }
        }
      }
    }
    for (const f of fresh) rows.push({ via: t.label, kind: "fixed", ...f, ...classify(f) });
    // 同一格的真事件，两条通道各报一次：fixed 那一格 GLASS_PROBE 看得见，
    // 语义浮层这一格（含 absolute 的原生 dialog）只有 overlayScan 看得见。
    for (const o of ovs) if (!wasOv.has(overlayKey(o)))
      rows.push({ via: t.label, kind: "语义", ...o, ...classify(o) });
    try { await t.close(c); } catch (e) { /* 关不掉就带着它走下一格 */ }
    await sleep(400);
    // 收场只重读语义那一格（它便宜）；[fixed] 那一格由下一轮开头的 was 现读
    const bo = await overlayScan(c);
    ovKeys = new Set(bo.map(overlayKey));
  }
  return { tag, url: target,
    resting: { n: restSnap.n, g: restSnap.g, tok: restSnap.tok, scheme: restSnap.htmlScheme,
      form: restSnap.form,
      ov: restOv.length, ovGlass: restOv.filter((o) => o.glass).length },
    candidates: clicks.map((t) => t.name.slice(0, 28)),   // 空表＝这一站没有点得着的浮层触发器，
                                                          // 和"点了没反应"是两件事，要分开印
    unread, rows, fired: firedN, feeds: c.failedFeeds(netFrom) };
}

// —— 正控制：这条判据必须能报"没穿上"，否则它的绿不能当证据 ——————————
// 「读到数」的口径：每格必须没有 err，且名册不能是空的。
// 2026-10-06 那一跑 7 站只回 2 站却 EXIT=0——覆盖缺成那样不往退出码上落，
// 于是"2/7"读起来像跑完了。这一函数是覆盖判据的单一定义，printVerdict 和退出码都读它。
function coverage(rs) {
  const m = rs.filter((r) => !r.err).length;
  return { m, n: rs.length, rc: (rs.length === 0 || m < rs.length) ? 1 : 0 };
}

function selftest() {
  const covCases = [
    ["覆盖断言 I（7 站里 5 站没回数＝今天实录的那一跑 ⇒ 退出码必须非 0）",
      [{ tag: "a" }, { tag: "b" },
       { tag: "c", err: "链路断" }, { tag: "d", err: "链路断" }, { tag: "e", err: "链路断" },
       { tag: "f", err: "链路断" }, { tag: "g", err: "链路断" }],
      { m: 2, n: 7, rc: 1 }],
    ["覆盖断言 J（全都回数 ⇒ 退出码 0）",
      [{ tag: "a" }, { tag: "b" }], { m: 2, n: 2, rc: 0 }],
    ["覆盖断言 K（KS_OVERLAY_ONLY 名字打错、一格都没跑 ⇒ 也不能读成\"0/0＝全绿\"）",
      [], { m: 0, n: 0, rc: 1 }],
  ];
  const cases = [
    ["合成人面 A（我们那面粉＋我们的墨）",
      { glass: true, ink: "rgb(58, 43, 62)", txt: 40 }, { ours: true, risk: false, unknown: false }],
    ["合成人面 B（站家的浅底＋站家的浅色字 ⇒ 真撞色）",
      { glass: false, ink: "rgb(246, 248, 250)", txt: 40,
        und: [{ t: "div", i: "", c: "", b: "rgb(246, 248, 250)", own: false }] },
      { ours: false, risk: true, unknown: false }],
    ["合成人面 C（没穿上但字是深色 ⇒ 不算撞色）",
      { glass: false, ink: "rgb(31, 35, 40)", txt: 40 }, { ours: false, risk: false, unknown: false }],
    ["合成人面 D（穿上玻璃且字是浅色 ⇒ 不开火）",
      { glass: true, ink: "rgb(246, 248, 250)", txt: 40 }, { ours: true, risk: false, unknown: false }],
    ["合成人面 E（没穿上但面上 0 字 ⇒ 不进风险表）",
      { glass: false, ink: "rgb(250, 250, 250)", txt: 0 }, { ours: false, risk: false, unknown: false }],
    ["合成人面 F（浅墨压站家深色 hero ⇒ 读得动，不能开火）",
      { glass: false, ink: "rgb(255, 255, 255)", txt: 86,
        und: [{ t: "div", i: "", c: "", b: "rgb(13, 17, 23)", own: false }] },
      { ours: false, risk: false, unknown: false }],
    ["合成人面 G（浅墨、底一路是站点画的图／全透明 ⇒ 算不出，单独点名）",
      { glass: false, ink: "rgb(255, 255, 255)", txt: 86,
        und: [{ t: "div", i: "", c: "", b: "img:rgba(0, 0, 0, 0)", own: false },
              { t: "div", i: "", c: "", b: "rgba(0, 0, 0, 0.4)", own: false }] },
      { ours: false, risk: false, unknown: true }],
    ["合成人面 H（浅墨、底只有半透的深色 ⇒ α<0.85 不算底，算不出）",
      { glass: false, ink: "rgb(250, 250, 250)", txt: 40,
        und: [{ t: "div", i: "", c: "", b: "rgba(13, 17, 23, 0.4)", own: false }] },
      { ours: false, risk: false, unknown: true }],
  ];
  const evCases = [
    ["事件分档 L（零新面＋那一趟有取数没回数 ⇒ 必须读成 feeder 断，不能读成本站没开）",
      { rows: [], fired: 3, unread: [], feeds: ["Fetch:https://x.algolia.net/1/query(net::ERR_FAILED)"] },
      "feeder 断"],
    ["事件分档 M（零新面、取数全回数、触发器也发出去了 ⇒ 这才叫本站没开）",
      { rows: [], fired: 3, unread: [], feeds: [] }, "本站没开"],
    ["事件分档 N（有面 ⇒ 这一格不开火，读到数的站不能被分档）",
      { rows: [{ navigated: false }], fired: 3, unread: [], feeds: ["Fetch:?"] }, ""],
    ["事件分档 O（一格触发器都没发出去 ⇒ 不能读成本站没开）",
      { rows: [], fired: 0, unread: [], feeds: [] }, "没试到触发器"],
    ["事件分档 P（取数没回数优先于没读到：两个都在时按 feeder 断办）",
      { rows: [], fired: 2, unread: ["key:?"], feeds: ["XHR:?(err)"] }, "feeder 断"],
  ];
  let bad = 0;
  for (const [name, rs, want] of covCases) {
    const got = coverage(rs);
    const ok = Object.keys(want).every((k) => got[k] === want[k]);
    if (!ok) bad++;
    console.log(`  ${ok ? "√" : "×"} ${name}：读到数 ${got.m}/${got.n} rc=${got.rc}` +
      `（要 ${want.m}/${want.n}/rc${want.rc}）`);
  }
  for (const [name, f, want] of cases) {
    const got = classify(f);
    const ok = Object.keys(want).every((k) => got[k] === want[k]);
    if (!ok) bad++;
    console.log(`  ${ok ? "√" : "×"} ${name}：ours=${got.ours} risk=${got.risk} unknown=${got.unknown}` +
      `（要 ${want.ours}/${want.risk}/${want.unknown}）`);
  }
  for (const [name, r, want] of evCases) {
    const got = eventBucket(r);
    if (got !== want) bad++;
    console.log(`  ${got === want ? "√" : "×"} ${name}：读到「${got || "不分档"}」（要「${want || "不分档"}」）`);
  }
  console.log("  读法（事件分档）：L 不开火＝把断了的取数通道读成「这站没有浮层」；M 开了火＝真没开的站被推给通道；" +
    "N 开了火＝明明读到面的站也被贴分档；O 开了火＝事件根本没发出去却判「本站没开」；" +
    "P 不开火＝两种缺格同时在场时丢了更硬的那一个。");
  console.log(`  读法：A 不开火＝glass 那位断了；B 不开火＝"漏判"这一格结构上永远不红，` +
    `普查报"0 处撞色"不算证据；C 开了火＝把深色字也当撞色；D 开了火＝穿上玻璃的也被判风险；` +
    `E 开了火＝0 字的面也进风险表；F 开了火＝只看墨不看底，站点自家深色 hero 的白字被当成撞色` +
    `（2026-10-06 github-home 真踩过，两行假火）；G 不开火＝"底算不出"被读成"没事"；` +
    `H 开了火＝半透明底被当成了不透明底；` +
    `I 不开火＝覆盖缺站还往退出码上落 0（2026-10-06 真踩过：7 站回 2 站、EXIT=0）；` +
    `J 开了火＝全都回数也被判缺；K 开了火＝名册打空了还报"跑完了"`);
  return bad ? 1 : 0;
}

// 事件档「零新面」的分档：读到面就不分档；没面时分四种，读的那一格不许在「没回数」和「没有」之间换。
function eventBucket(r) {
  if ((r.rows || []).some((x) => !x.navigated)) return "";
  if ((r.feeds || []).length) return "feeder 断";
  if (!r.fired) return "没试到触发器";
  if ((r.unread || []).length) return "没读到";
  return "本站没开";
}

function printSite(r) {
  console.log(`\n【${r.tag}】${r.url}`);
  if (r.err) return console.log(`  错误：${r.err}`);
  console.log(`  静息：fixed/sticky 面 ${r.resting.n} 块／穿上玻璃 ${r.resting.g} 块` +
    `｜语义浮层 ${r.resting.ov} 块／穿上玻璃 ${r.resting.ovGlass} 块｜静息档＝${r.resting.form}` +
    `｜token ${r.resting.tok || "缺"}` +
    `｜scheme ${r.resting.scheme}`);
  console.log(`  点击候选 ${r.candidates.length} 枚：${r.candidates.join(" / ") || "（无）"}`);
  const real = r.rows.filter((x) => !x.navigated);
  const nav = r.rows.filter((x) => x.navigated);
  if (r.unread.length) console.log(`  没读到（页址回不来）${r.unread.length} 格：${r.unread.join(" / ")}` +
    "——这些格不作证，站点有没有浮层都没说");
  if (!real.length) {
    const bk = eventBucket(r);
    console.log("  真事件之后：没有新的 fixed 面｜这一格按「" + bk + "」办" +
      (bk === "feeder 断" ? "（浮层内容靠的那一跳没回数：" + r.feeds.slice(0, 3).join(" / ") +
        "）——不算「这站没有浮层」" : "") +
      (nav.length ? `（有 ${nav.length} 次点了跳走）` : "") +
      (r.unread.length ? `（另有 ${r.unread.length} 次没读到，见上一行）` : ""));
  }
  for (const f of real) {
    console.log(`  ${f.ours ? "穿上玻璃" : "没穿"}${f.risk ? "｜浅字撞底" : ""}  [${f.kind}]  ${f.via}  ` +
      `${f.pos}${f.role ? "/" + f.role : ""}${f.modal ? "/modal" : ""} ${f.w}x${f.h}  ` +
      `<${f.tag} ${(f.id || f.label || f.cls.slice(0, 44))}>  字${f.txt}` +
      (f.cover === undefined ? "" : ` 盖${f.cover}%`) +
      (f.scrim ? ` 遮罩=${f.scrim}` : "") +
      (f.unknown ? "｜底算不出" : ""));
    console.log(`      bg=${f.bg}  bf=${f.bf}  ink=${f.ink}`);
    if (f.kind === "fixed") {
      console.log(f.und === undefined
        ? "      衬底=未读到（全形补读没回数或键没对上）——这一格不算\"底下没有粉\""
        : `      衬底=${f.und.length ? f.und.map((u) =>
            `${u.t}${u.i ? "#" + u.i : ""}.${u.c.slice(0, 22)}=${u.b}${u.own ? "·own" : ""}`).join(" ← ") : "一路到 body 都没有涂底的祖先"}`);
    }
  }
}

function printVerdict(results) {
  const cov = coverage(results);
  const ok = results.filter((r) => !r.err);
  const rows = ok.flatMap((r) => r.rows.filter((f) => !f.navigated).map((f) => ({ ...f, tag: r.tag })));
  const byKind = {};
  for (const f of rows) (byKind[f.kind] ||= []).push(f);
  console.log(`\n判定：覆盖 ${cov.m}/${cov.n} 站读到数` +
    (cov.n === 0 ? "（名册是空的，一格都没跑）"
      : cov.m < cov.n ? `（缺 ${cov.n - cov.m} 站——下面的总数只对回数的那几站成立，不能读成"缺的那几站没有浮层"）` : "") +
    `；被真事件点出来的浮层 ` +
    `${rows.length} 块，其中穿上玻璃 ${rows.filter((f) => f.ours).length} 块、` +
    `没穿 ${rows.filter((f) => !f.ours).length} 块（没穿且面上浅字有字的 ${rows.filter((f) => f.risk).length} 块）`);
  for (const k of Object.keys(byKind)) {
    const v = byKind[k];
    console.log(`  · [${k}] ${v.length} 块：穿 ${v.filter((f) => f.ours).length}／没穿 ${v.filter((f) => !f.ours).length}`);
  }
  console.log(`  两条通道的分工：[fixed] 那一格按 proxy.py 里同一条 glass 判据与同样的位置／尺寸筛挑面；` +
    `静息档优先用 ?glassprobe 的 GLASS_PROBE 原形（所以它能和 glass-census 那张表对账），` +
    `原形 3 次没回数才退轻形——轻形没有 盖% 列，两档各印在哪一档由行首「静息档＝」点名。` +
    `[语义] 那一格按 role／dialog／popover 挑，不看位置——` +
    `开起来的原生 <dialog> 计算位置是 absolute，GLASS_PROBE 在位置那一步就筛掉了它，` +
    `所以普查那一档结构上读不到族的第一位成员。判据只有 proxy.py 里那一条，两处都是读它。` +
    `档＝?keepjs ${BAND_NAME}；昼夜两档的静息浮面归 glass-census。`);
}

async function main() {
  if (process.argv.includes("--selftest")) process.exit(selftest());
  const probe = PROBE.js;
  const health = await fetch(`http://127.0.0.1:${PORT}/healthz`).then((r) => r.ok).catch(() => false);
  if (!health) {
    console.error(`OVERLAY PROBE ERROR: ${PORT} 上没起 tools/proxy.py（先起它：python3 tools/proxy.py ${PORT}）`);
    process.exit(2);
  }
  const udir = mkdtempSync(join(tmpdir(), "ks-overlay-"));
  const chrome = spawn(CHROME, ["--headless=new", "--disable-gpu", "--no-sandbox",
    `--user-data-dir=${udir}`, "--remote-debugging-port=0",
    // 高度与 glass-census 对齐（1500 名义 ⇒ innerHeight 实测 1413；900 那一档只有 813）。
    // 不对账的后果现量过：github-features 的 sticky 锚点导航条在 y=885，813 视口够不着 ⇒
    // 探针报「静息 0 块」而普查报 1 块，同一判据两个数。矮视口把"首屏没有"冒充成"这页没有"。
    "--window-size=1440,1500", "--no-first-run", "--disable-background-networking",
    "about:blank"], { stdio: ["ignore", "ignore", "pipe"] });
  chrome.stderr.pipe(createWriteStream(join(tmpdir(), "ks-overlay-chrome.log")));
  try {
    // 端口由 Chrome 自己挑（=0），从 udir/DevToolsActivePort 第一行读回来。
    // 固定端口那一格今天真撞过：上一跑的进程没退干净、它的 headless 实例还占着 9333，
    // 这一跑就连到了别人家的浏览器上，20 分钟不出一个数。
    const port = await devPort(udir, 40000);
    const get = (path) => fetch(`http://127.0.0.1:${port}${path}`)
      .then((r) => r.json()).catch(() => null);
    let ver = null;
    for (let i = 0; i < 160 && !ver; i++) {
      await sleep(250);
      ver = await get("/json/version");
    }
    if (!ver) throw new Error(`headless Chrome 的 CDP 没起来（端口 ${port}）`);
    const b = await Cdp.connect(ver.webSocketDebuggerUrl);
    const { targetId } = await b.cmd("Target.createTarget", { url: "about:blank" });
    const list = (await get("/json/list")) || [];
    const page = list.find((p) => p.id === targetId) || list[0];
    const c = await Cdp.connect(page.webSocketDebuggerUrl);
    await c.cmd("Runtime.enable"); await c.cmd("Page.enable");
    await c.cmd("Network.enable");   // 不开这个域，failedFeeds 没得读
    for (const [tag, url] of sites()) {
      let r;
      try { r = await probeSite(c, `http://127.0.0.1:${PORT}/s/`, tag, url, probe); }
      catch (e) { r = { tag, url, err: String((e && e.message) || e).slice(0, 140) }; }
      results.push(r);
      printSite(r);
    }
    printVerdict(results);
    if (process.env.KS_OVERLAY_JSON) {
      writeFileSync(process.env.KS_OVERLAY_JSON, JSON.stringify(results, null, 1));
      console.log(`明细落 ${process.env.KS_OVERLAY_JSON}`);
    }
    await b.cmd("Browser.close").catch(() => {});
  } finally {
    // 跑完不退是今天撞到的第二格：chrome.kill() 打的是 spawn 的那个壳，
    // 真浏览器被 launchd 收去（ppid=1、54% CPU）继续活着，而 chrome.killed 已经是 true，
    // SIGKILL 那一发就永远不会发；rmSync 又和它的写入赛跑，于是堆了 13 个临时 profile。
    // 改按身份收回：这一跑独有的 --user-data-dir 路径就是那枚身份。
    const survivors = await reapChrome(chrome, udir);
    if (survivors.length) {
      console.error(`OVERLAY PROBE ERROR: 浏览器 ${survivors.join(",")} 按身份（${udir}）没收回 ——` +
        `这一跑会污染下一跑的端口与 CPU，目录留着不清，供复核`);
      process.exit(3);
    }
    if (KEEP_DIR) console.error(`保留 ${udir} 供复核`);
    else {
      let last = null;
      for (let i = 0; i < 10; i++) {
        try { rmSync(udir, { recursive: true, force: true }); last = null; break; }
        catch (e) { last = e; await sleep(400); }
      }
      if (last) console.error(`OVERLAY PROBE ERROR: ${udir} 删不掉（${String(last.message).slice(0, 90)}）——留着复核`);
    }
    for (const w of SOCKETS) { try { w.close(); } catch (e) { /* 已经关了 */ } }
  }
  process.exit(coverage(results).rc);
}

function pidAlive(p) {
  try { process.kill(p, 0); return true; } catch (e) { return e.code === "EPERM"; }
}

function pidsForProfile(dir) {
  let raw = "";
  try { raw = execFileSync("pgrep", ["-f", `user-data-dir=${dir}`], { encoding: "utf8" }); }
  catch (e) { return []; }
  return raw.split("\n").map((x) => Number(x.trim())).filter((n) => n > 0);
}

// 只按这一跑独有的临时目录名认人，认出来的才杀——不碰别人家的 Chrome。
async function reapChrome(chrome, dir) {
  const mine = new Set([chrome.pid, ...pidsForProfile(dir)].filter((n) => n > 0));
  chrome.kill("SIGINT");
  for (const p of pidsForProfile(dir)) {
    if (p !== chrome.pid) { try { process.kill(p, "SIGTERM"); } catch (e) { /* 已经走了 */ } }
  }
  for (let i = 0; i < 24; i++) {
    await sleep(500);
    const left = [...mine].filter(pidAlive);
    if (!left.length) return [];
  }
  const left = [...mine].filter(pidAlive);
  for (const p of left) { try { process.kill(p, "SIGKILL"); } catch (e) { /* 已经走了 */ } }
  await sleep(600);
  return left.filter(pidAlive);
}

function devPort(dir, ms) {
  const f = join(dir, "DevToolsActivePort");
  const t0 = Date.now();
  return new Promise((resolve, reject) => {
    const tick = () => {
      let raw = "";
      try { raw = readFileSync(f, "utf8"); } catch (e) { raw = ""; }
      const n = Number((raw || "").split("\n")[0]);
      if (n > 0) return resolve(n);
      if (Date.now() - t0 > ms) return reject(new Error("Chrome 没写出 DevToolsActivePort"));
      setTimeout(tick, 200);
    };
    tick();
  });
}

const results = [];
const SOCKETS = [];
main().catch((e) => { console.error("OVERLAY PROBE ERROR:", e); process.exit(1); });
