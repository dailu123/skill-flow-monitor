// Copilot Auto Continue
// 原理:监控当前工作区 Copilot 对话的落盘文件。
//   - agent 干活时,chatSessions/ 或 chatEditingSessions/ 下的 json 会被写入。
//   - 一旦停下,这些文件就不再变化。
//   - 连续 idleSeconds 秒没有写入 => 判定为停止 => 用命令把『继续』提交进 chat。
// 全程不碰鼠标键盘,你可以同时干别的。

const vscode = require('vscode');
const fs = require('fs');
const path = require('path');

let enabled = false;          // 当前是否在监控
let statusBar = null;         // 状态栏按钮
let timer = null;             // 轮询定时器
let continueCount = 0;        // 已自动发送次数

let lastMtime = 0;            // 已观察到的最新写盘时间
let lastChangeTs = 0;         // 上次检测到文件变化的本地时刻
let cooldownUntil = 0;        // 冷却截止时刻
let sawActivity = false;      // 开启/上次发送后,是否观察到过新的写盘
let lastNewestFile = null;    // 最近变化的文件(诊断用)

function cfg(key) {
  return vscode.workspace.getConfiguration('copilotAutoContinue').get(key);
}

// storageUri = .../workspaceStorage/<hash>/<publisher.name>
// 它的上一级 <hash> 目录下有 chatSessions/ 和 chatEditingSessions/
function hashDir(context) {
  if (!context.storageUri) return null;
  return path.dirname(context.storageUri.fsPath);
}

// 只监控 chat 相关目录,避免被 state.vscdb 等高频写入污染判断。
function chatRoots(context) {
  const h = hashDir(context);
  if (!h) return [];
  return [path.join(h, 'chatSessions'), path.join(h, 'chatEditingSessions')];
}

// 当前要忽略的文件名集合(小写)。state.json 等元数据跟聊天无关也会变动。
function ignoreSet() {
  const list = cfg('ignoreFiles') || ['state.json', 'states.json'];
  return new Set(list.map(s => String(s).toLowerCase()));
}

// 递归扫描目录里 .json 的最新修改时间,跳过被忽略的文件。
function latestMtimeIn(dir, ignore) {
  let m = 0, newest = null;
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch (e) {
    return { m, newest };
  }
  for (const e of entries) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) {
      const r = latestMtimeIn(p, ignore);
      if (r.m > m) { m = r.m; newest = r.newest; }
    } else if (e.name.endsWith('.json') && !ignore.has(e.name.toLowerCase())) {
      try {
        const st = fs.statSync(p);
        if (st.mtimeMs > m) { m = st.mtimeMs; newest = p; }
      } catch (e2) { /* ignore */ }
    }
  }
  return { m, newest };
}

// 取所有 chat 目录里最新的写盘时间。
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

async function sendContinue() {
  continueCount++;
  const msg = cfg('message') || '继续';
  try {
    await vscode.commands.executeCommand('workbench.action.chat.open', {
      query: msg,
      isPartialQuery: false, // false = 直接提交
    });
  } catch (e) {
    vscode.window.showErrorMessage('Copilot Auto Continue 发送失败: ' + e);
  }
  const now = Date.now();
  cooldownUntil = now + (cfg('cooldownSeconds') || 12) * 1000;
  lastChangeTs = now;
  sawActivity = false; // 发完后,要重新观察到 agent 真的动起来,才允许下一次判定空闲

  if (continueCount >= (cfg('maxContinues') || 100)) {
    stop();
    vscode.window.showWarningMessage(
      `Copilot Auto Continue 已达上限(${continueCount} 次),自动停止。点状态栏可重新开启。`
    );
  }
}

function tick(context) {
  if (!enabled) return;
  if (chatRoots(context).length === 0) {
    setStatus('$(sync~spin) Auto继续: 无工作区', '没有打开工作区,无法定位对话文件');
    return;
  }

  const now = Date.now();
  const res = latestMtime(context);
  const m = res.m;
  if (m > lastMtime) {
    lastMtime = m;
    lastChangeTs = now;
    sawActivity = true;
    lastNewestFile = res.newest;
  }

  if (now < cooldownUntil) {
    const left = Math.ceil((cooldownUntil - now) / 1000);
    setStatus(`$(clock) Auto继续: 冷却 ${left}s`, '刚发过继续,冷却中');
    return;
  }

  const idleMs = now - lastChangeTs;
  const idleLimit = (cfg('idleSeconds') || 30) * 1000;

  if (sawActivity && lastMtime > 0 && idleMs >= idleLimit) {
    setStatus('$(debug-step-over) Auto继续: 发送中…', '检测到停止,正在发送继续');
    sendContinue();
    return;
  }

  if (!sawActivity) {
    setStatus('$(eye) Auto继续: 等待活动',
      '等 agent 开始写盘后才会接管。若 agent 明明在干活却一直停在这,运行命令「Copilot Auto Continue: 诊断」看监控路径');
  } else {
    const idleLeft = Math.max(0, Math.ceil((idleLimit - idleMs) / 1000));
    setStatus(`$(eye) Auto继续: 监控中 ${idleLeft}s`, `空闲 ${idleLeft}s 后将发送继续 | 已发 ${continueCount} 次`);
  }
}

// 递归收集目录下所有 .json(跳过 .vscdb 等),返回 {rel, mtimeMs, size}。
function collectJson(dir, baseDir, acc) {
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch (e) {
    return;
  }
  for (const e of entries) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) {
      collectJson(p, baseDir, acc);
    } else if (e.name.endsWith('.json')) {
      try {
        const st = fs.statSync(p);
        acc.push({ rel: path.relative(baseDir, p), mtimeMs: st.mtimeMs, size: st.size });
      } catch (e2) { /* ignore */ }
    }
  }
}

function diagnose(context) {
  const h = hashDir(context);
  const roots = chatRoots(context);
  const res = latestMtime(context);
  const ageSec = res.m ? Math.round((Date.now() - res.m) / 1000) : -1;
  const ignore = ignoreSet();

  // 把整个工作区 hash 目录下的 json 全列出来(不只是被监控的两个子目录),
  // 这样能看清聊天数据到底落在哪、哪个文件在变。
  const all = [];
  if (h) collectJson(h, h, all);
  all.sort((a, b) => b.mtimeMs - a.mtimeMs);
  const now = Date.now();
  const top = all.slice(0, 25).map(f => {
    const age = Math.round((now - f.mtimeMs) / 1000);
    const ign = ignore.has(path.basename(f.rel).toLowerCase()) ? ' [已忽略]' : '';
    return `  ${String(age).padStart(5)}s前  ${String(f.size).padStart(8)}B  ${f.rel}${ign}`;
  });

  const lines = [
    `enabled=${enabled}  sawActivity=${sawActivity}  已发=${continueCount} 次`,
    `工作区 hash 目录: ${h || '(无,未打开工作区)'}`,
    '',
    '当前监控的目录:',
    ...roots.map(r => `  ${fs.existsSync(r) ? '✓' : '✗'} ${r}`),
    `忽略的文件名: ${[...ignore].join(', ') || '(无)'}`,
    `当前判定用的最近文件: ${res.newest || '(无)'}  距今 ${ageSec < 0 ? '— 没扫到符合条件的 json' : ageSec + 's'}`,
    '',
    `hash 目录下全部 json 共 ${all.length} 个,按最近修改排序(前 25):`,
    ...(top.length ? top : ['  (一个都没有)']),
  ];
  const msg = lines.join('\n');
  console.log('[CopilotAutoContinue] 诊断\n' + msg);
  vscode.window.showInformationMessage('Copilot Auto Continue 诊断(完整内容见开发人员工具 Console,可复制)', { modal: true, detail: msg });
}

function start(context) {
  enabled = true;
  continueCount = 0;
  lastMtime = latestMtime(context).m;
  lastChangeTs = Date.now();
  cooldownUntil = 0;
  sawActivity = false;
  setStatus('$(eye) Auto继续: 等待活动', '已开启');
}

function stop() {
  enabled = false;
  setStatus('$(circle-slash) Auto继续: 关', '点击开启');
}

function activate(context) {
  statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusBar.command = 'copilotAutoContinue.toggle';
  statusBar.show();
  context.subscriptions.push(statusBar);

  context.subscriptions.push(
    vscode.commands.registerCommand('copilotAutoContinue.toggle', () => {
      if (enabled) stop();
      else start(context);
    })
  );
  context.subscriptions.push(
    vscode.commands.registerCommand('copilotAutoContinue.sendNow', () => sendContinue())
  );
  context.subscriptions.push(
    vscode.commands.registerCommand('copilotAutoContinue.diagnose', () => diagnose(context))
  );

  if (cfg('enabledOnStartup')) start(context);
  else stop();

  const poll = Math.max(1, cfg('pollSeconds') || 2) * 1000;
  timer = setInterval(() => tick(context), poll);
  context.subscriptions.push({ dispose: () => clearInterval(timer) });
}

function deactivate() {
  if (timer) clearInterval(timer);
}

module.exports = { activate, deactivate };
