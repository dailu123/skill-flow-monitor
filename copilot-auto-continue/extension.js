// Copilot Auto Continue
// 两种模式:
//   1) babysit(保姆):监控对话 .jsonl,空闲超时自动发『继续』,救被中断的长任务。
//   2) driver(并行驱动器):认领一个分片(<repo>__sK),循环 newChat→发提示词→等空闲→下一个,
//      跑完该分片再认领下一片。多窗口各装本扩展即可 N 路并行(配合 parallel/shard.py)。
// 对话转录是 chatSessions/<uuid>.jsonl(JSON Lines),agent 每产生一步都会往里追加;停下就不再变化。

const vscode = require('vscode');
const fs = require('fs');
const path = require('path');

let statusBar = null;
let timer = null;

// ---- babysit 状态 ----
let enabled = false;
let continueCount = 0;
let lastMtime = 0, lastChangeTs = 0, cooldownUntil = 0, sawActivity = false, lastNewestFile = null;

// ---- driver 状态 ----
let driverOn = false;
let claimedNs = null;
let boundJsonl = null;
let driverDone = 0;       // 本会话已完成单元数
let driverStall = 0;      // 连续无进展计数

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

function cfg(key) { return vscode.workspace.getConfiguration('copilotAutoContinue').get(key); }
function isWatchedFile(name) { return name.endsWith('.jsonl') || name.endsWith('.json'); }

function hashDir(context) {
  if (!context.storageUri) return null;
  return path.dirname(context.storageUri.fsPath);
}
function chatSessionsDir(context) {
  const h = hashDir(context);
  return h ? path.join(h, 'chatSessions') : null;
}
function chatRoots(context) {
  const h = hashDir(context);
  if (!h) return [];
  return [path.join(h, 'chatSessions'), path.join(h, 'chatEditingSessions')];
}
function ignoreSet() {
  const list = cfg('ignoreFiles') || ['state.json', 'states.json'];
  return new Set(list.map(s => String(s).toLowerCase()));
}

function latestMtimeIn(dir, ignore) {
  let m = 0, newest = null, entries;
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch (e) { return { m, newest }; }
  for (const e of entries) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) {
      const r = latestMtimeIn(p, ignore);
      if (r.m > m) { m = r.m; newest = r.newest; }
    } else if (isWatchedFile(e.name) && !ignore.has(e.name.toLowerCase())) {
      try { const st = fs.statSync(p); if (st.mtimeMs > m) { m = st.mtimeMs; newest = p; } } catch (e2) {}
    }
  }
  return { m, newest };
}
function latestMtime(context) {
  const ignore = ignoreSet();
  let m = 0, newest = null;
  for (const d of chatRoots(context)) {
    const r = latestMtimeIn(d, ignore);
    if (r.m > m) { m = r.m; newest = r.newest; }
  }
  return { m, newest };
}

function setStatus(text, tooltip) {
  if (!statusBar) return;
  statusBar.text = text;
  if (tooltip) statusBar.tooltip = tooltip;
}

function mtimeOf(p) { try { return fs.statSync(p).mtimeMs; } catch (e) { return 0; } }

// ============================ 通用:提交一条消息进当前 chat ============================
async function submitToChat(query) {
  await vscode.commands.executeCommand('workbench.action.chat.open', { query, isPartialQuery: false });
}

// ============================ babysit 模式 ============================
async function babysitSend() {
  continueCount++;
  try { await submitToChat(cfg('message') || '继续'); }
  catch (e) { vscode.window.showErrorMessage('发送失败: ' + e); }
  const now = Date.now();
  cooldownUntil = now + (cfg('cooldownSeconds') || 300) * 1000;
  lastChangeTs = now;
  sawActivity = false;
  if (continueCount >= (cfg('maxContinues') || 100)) {
    babysitStop();
    vscode.window.showWarningMessage(`已达上限(${continueCount} 次),自动停止。`);
  }
}
function babysitTick(context) {
  if (!enabled) return;
  if (chatRoots(context).length === 0) { setStatus('$(sync~spin) Auto继续: 无工作区'); return; }
  const now = Date.now();
  const res = latestMtime(context);
  if (res.m > lastMtime) { lastMtime = res.m; lastChangeTs = now; sawActivity = true; lastNewestFile = res.newest; }
  if (now < cooldownUntil) {
    setStatus(`$(clock) Auto继续: 冷却 ${Math.ceil((cooldownUntil - now) / 1000)}s`); return;
  }
  const idleMs = now - lastChangeTs, idleLimit = (cfg('idleSeconds') || 300) * 1000;
  if (sawActivity && lastMtime > 0 && idleMs >= idleLimit) { setStatus('$(debug-step-over) Auto继续: 发送中…'); babysitSend(); return; }
  if (!sawActivity) setStatus('$(eye) Auto继续: 等待活动');
  else setStatus(`$(eye) Auto继续: 监控中 ${Math.max(0, Math.ceil((idleLimit - idleMs) / 1000))}s`, `已发 ${continueCount} 次`);
}
function babysitStart(context) {
  driverStop();
  enabled = true; continueCount = 0;
  lastMtime = latestMtime(context).m; lastChangeTs = Date.now(); cooldownUntil = 0; sawActivity = false;
  setStatus('$(eye) Auto继续: 等待活动', '已开启 babysit');
}
function babysitStop() { enabled = false; if (!driverOn) setStatus('$(circle-slash) Auto继续: 关', '点击开启 babysit'); }

// ============================ driver 模式 ============================
function wsRoot() {
  const f = vscode.workspace.workspaceFolders;
  return f && f.length ? f[0].uri.fsPath : null;
}
function kitDir() { const r = wsRoot(); return r ? path.join(r, cfg('driver.kitPath') || 'code-analysis-kit') : null; }
function progressPath(ns) { return path.join(kitDir(), 'work', ns, 'PROGRESS.md'); }
function workerLock(ns) { return path.join(kitDir(), 'work', ns, '.worker-lock'); }
function submitLock() { return path.join(kitDir(), 'work', cfg('driver.repo'), '.submit-lock'); }

function readNamespaces() {
  const repo = cfg('driver.repo');
  const mf = path.join(kitDir(), 'work', repo, 'shards.json');
  try { return JSON.parse(fs.readFileSync(mf, 'utf8')).shards || []; }
  catch (e) { return []; }
}
function countTodo(ns) {
  try { return (fs.readFileSync(progressPath(ns), 'utf8').match(/\|\s*TODO\s*\|/g) || []).length; }
  catch (e) { return 0; }
}

// 目录锁(mkdir 原子);带心跳,过期可被接管。best-effort,适合低竞争多窗口。
function acquireLock(dir, staleMs) {
  try { fs.mkdirSync(dir); fs.writeFileSync(path.join(dir, 'hb'), String(Date.now())); return true; }
  catch (e) {
    let hb = 0; try { hb = Number(fs.readFileSync(path.join(dir, 'hb'), 'utf8')) || 0; } catch (e2) {}
    if (Date.now() - hb > staleMs) { try { fs.writeFileSync(path.join(dir, 'hb'), String(Date.now())); return true; } catch (e3) {} }
    return false;
  }
}
function renewLock(dir) { try { fs.writeFileSync(path.join(dir, 'hb'), String(Date.now())); } catch (e) {} }
function releaseLock(dir) { try { fs.rmSync(dir, { recursive: true, force: true }); } catch (e) {} }

function claimShard() {
  for (const ns of readNamespaces()) {
    if (countTodo(ns) > 0 && acquireLock(workerLock(ns), (cfg('driver.shardStaleSeconds') || 180) * 1000)) return ns;
  }
  return null;
}

function buildPrompt(ns) {
  const tpl = cfg('driver.promptTemplate');
  const kit = cfg('driver.kitPath') || 'code-analysis-kit';
  return tpl.split('{ns}').join(ns).split('{kit}').join(kit);
}

function listJsonl(context) {
  const d = chatSessionsDir(context);
  try { return fs.readdirSync(d).filter(f => f.endsWith('.jsonl')); } catch (e) { return []; }
}

// 全局提交锁内:newChat + 提交 + 绑定本会话刚生成的 .jsonl
async function submitUnit(context, ns) {
  if (!acquireLock(submitLock(), (cfg('driver.submitStaleSeconds') || 90) * 1000)) return false;
  try {
    const before = new Set(listJsonl(context));
    const t0 = Date.now();
    await vscode.commands.executeCommand('workbench.action.chat.newChat').then(undefined, () => {});
    await sleep(900);
    await submitToChat(buildPrompt(ns));
    // 等本会话的新 .jsonl 出现(最多 25s)
    for (let i = 0; i < 25; i++) {
      await sleep(1000);
      const news = listJsonl(context).filter(f => !before.has(f));
      if (news.length) {
        const d = chatSessionsDir(context);
        news.sort((a, b) => mtimeOf(path.join(d, b)) - mtimeOf(path.join(d, a)));
        boundJsonl = path.join(d, news[0]);
        return true;
      }
    }
    // 兜底:绑定提交后被改过的最新 .jsonl
    const d = chatSessionsDir(context);
    const cands = listJsonl(context).map(f => path.join(d, f)).filter(p => mtimeOf(p) >= t0);
    if (cands.length) { cands.sort((a, b) => mtimeOf(b) - mtimeOf(a)); boundJsonl = cands[0]; return true; }
    return false;
  } catch (e) {
    vscode.window.showErrorMessage('driver 提交失败: ' + e); return false;
  } finally { releaseLock(submitLock()); }
}

// 等绑定的 .jsonl 连续 idleSeconds 无写入 = 这个单元处理完(或卡住超 maxUnit)
async function waitUnitIdle(context) {
  const idleMs = (cfg('driver.idleSeconds') || 90) * 1000;
  const maxMs = (cfg('driver.maxUnitSeconds') || 1800) * 1000;
  const poll = Math.max(1, cfg('pollSeconds') || 5) * 1000;
  const start = Date.now();
  let lastM = mtimeOf(boundJsonl), lastChange = Date.now();
  while (driverOn) {
    await sleep(poll);
    renewLock(workerLock(claimedNs));
    const m = mtimeOf(boundJsonl), now = Date.now();
    if (m > lastM) { lastM = m; lastChange = now; }
    const idle = now - lastChange;
    setStatus(`$(rocket) 驱动 ${claimedNs}: 跑第 ${driverDone + 1} 个 (空闲 ${Math.floor(idle / 1000)}/${idleMs / 1000}s)`,
      `已完成 ${driverDone} 个 | 绑定 ${path.basename(boundJsonl || '')}`);
    if (idle >= idleMs) return 'idle';
    if (now - start >= maxMs) return 'timeout';
  }
  return 'stopped';
}

async function driverLoop(context) {
  if (!wsRoot()) { vscode.window.showErrorMessage('driver:没有打开工作区'); driverStop(); return; }
  if (!cfg('driver.repo')) { vscode.window.showErrorMessage('driver:先在设置里填 copilotAutoContinue.driver.repo'); driverStop(); return; }
  if (readNamespaces().length === 0) { vscode.window.showErrorMessage(`driver:读不到 work/${cfg('driver.repo')}/shards.json,先跑 shard.py split`); driverStop(); return; }

  while (driverOn) {
    if (!claimedNs) {
      claimedNs = claimShard();
      if (!claimedNs) { setStatus('$(check-all) 驱动: 无可认领分片(可能全完成)', '所有分片 TODO 已清零或被占用'); driverStop(); return; }
      driverStall = 0;
      setStatus(`$(rocket) 驱动: 认领 ${claimedNs}`, `剩 TODO ${countTodo(claimedNs)}`);
    }
    renewLock(workerLock(claimedNs));
    const before = countTodo(claimedNs);
    if (before === 0) { releaseLock(workerLock(claimedNs)); claimedNs = null; continue; }

    const ok = await submitUnit(context, claimedNs);
    if (!ok) { setStatus(`$(warning) 驱动 ${claimedNs}: 提交失败,5s 后重试`); await sleep(5000); continue; }

    const r = await waitUnitIdle(context);
    if (r === 'stopped') return;

    const after = countTodo(claimedNs);
    if (after < before) { driverDone += (before - after); driverStall = 0; }
    else {
      driverStall++;
      if (driverStall >= 3) {
        vscode.window.showWarningMessage(`driver ${claimedNs}: 连续 3 个单元 TODO 没减少(可能卡在等批准/出错),释放该分片。`);
        releaseLock(workerLock(claimedNs)); claimedNs = null;
      }
    }
  }
}

function driverStart(context) {
  babysitStop();
  driverOn = true; driverDone = 0; driverStall = 0; claimedNs = null; boundJsonl = null;
  setStatus('$(rocket) 驱动: 启动中…', '并行驱动器已启动');
  driverLoop(context);
}
function driverStop() {
  driverOn = false;
  if (claimedNs) { releaseLock(workerLock(claimedNs)); claimedNs = null; }
  setStatus('$(circle-slash) Auto继续: 关', '点击开启 babysit');
}

// ============================ 诊断 ============================
function collectJson(dir, baseDir, acc) {
  let entries; try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch (e) { return; }
  for (const e of entries) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) collectJson(p, baseDir, acc);
    else if (isWatchedFile(e.name)) { try { const st = fs.statSync(p); acc.push({ rel: path.relative(baseDir, p), mtimeMs: st.mtimeMs, size: st.size }); } catch (e2) {} }
  }
}
function diagnose(context) {
  const h = hashDir(context), res = latestMtime(context), ignore = ignoreSet();
  const all = []; if (h) collectJson(h, h, all);
  all.sort((a, b) => b.mtimeMs - a.mtimeMs);
  const now = Date.now();
  const top = all.slice(0, 25).map(f => {
    const ign = ignore.has(path.basename(f.rel).toLowerCase()) ? ' [已忽略]' : '';
    return `  ${String(Math.round((now - f.mtimeMs) / 1000)).padStart(5)}s前  ${String(f.size).padStart(8)}B  ${f.rel}${ign}`;
  });
  const msg = [
    `babysit=${enabled} driver=${driverOn} 认领分片=${claimedNs || '-'} 已完成=${driverDone}`,
    `工作区 hash 目录: ${h || '(无)'}`,
    `driver.repo=${cfg('driver.repo') || '(未设)'}  分片清单=${readNamespaces().join(', ') || '(无)'}`,
    '', `当前判定最近文件: ${res.newest || '(无)'}`,
    '', `hash 目录下 json/jsonl 共 ${all.length} 个(前 25,按最近修改):`,
    ...(top.length ? top : ['  (无)']),
  ].join('\n');
  console.log('[CopilotAutoContinue] 诊断\n' + msg);
  vscode.window.showInformationMessage('Copilot Auto Continue 诊断(详情见 Console)', { modal: true, detail: msg });
}

// ============================ 激活 ============================
function activate(context) {
  statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusBar.command = 'copilotAutoContinue.toggle';
  statusBar.show();
  context.subscriptions.push(statusBar);

  const reg = (id, fn) => context.subscriptions.push(vscode.commands.registerCommand(id, fn));
  reg('copilotAutoContinue.toggle', () => { if (enabled) babysitStop(); else babysitStart(context); });
  reg('copilotAutoContinue.sendNow', () => babysitSend());
  reg('copilotAutoContinue.diagnose', () => diagnose(context));
  reg('copilotAutoContinue.startDriver', () => driverStart(context));
  reg('copilotAutoContinue.stopDriver', () => driverStop());

  if (cfg('enabledOnStartup')) babysitStart(context); else babysitStop();

  timer = setInterval(() => { if (!driverOn) babysitTick(context); }, Math.max(1, cfg('pollSeconds') || 5) * 1000);
  context.subscriptions.push({ dispose: () => { clearInterval(timer); if (claimedNs) releaseLock(workerLock(claimedNs)); } });
}
function deactivate() { driverOn = false; if (timer) clearInterval(timer); if (claimedNs) releaseLock(workerLock(claimedNs)); }

module.exports = { activate, deactivate };
