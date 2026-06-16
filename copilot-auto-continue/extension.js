// Copilot Auto Continue
// 原理:监控当前工作区 Copilot 对话的落盘文件(chatSessions/*.json)。
//   - agent 正在干活时,文件会不停被写入(每走一步都写盘)。
//   - 一旦停下,文件就不再变化。
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
                              // (必须先有活动、再变空闲,才会发继续——避免去捅一个早就结束的旧对话)

function cfg(key) {
  return vscode.workspace.getConfiguration('copilotAutoContinue').get(key);
}

// 通过扩展自己的 storageUri 反推出当前工作区的 chatSessions 目录。
// storageUri = .../workspaceStorage/<hash>/<publisher.name>
// 它的上一级 <hash> 目录下就有 chatSessions/
function chatSessionsDir(context) {
  if (!context.storageUri) return null; // 没打开工作区时没有
  const hashDir = path.dirname(context.storageUri.fsPath);
  return path.join(hashDir, 'chatSessions');
}

// 取目录下所有 .json 里最新的修改时间(毫秒)。目录不存在则返回 0。
function latestMtime(dir) {
  let m = 0;
  try {
    for (const f of fs.readdirSync(dir)) {
      if (!f.endsWith('.json')) continue;
      const st = fs.statSync(path.join(dir, f));
      if (st.mtimeMs > m) m = st.mtimeMs;
    }
  } catch (e) {
    // 目录还不存在(还没产生过对话)等情况,忽略
  }
  return m;
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
  const dir = chatSessionsDir(context);
  if (!dir) {
    setStatus('$(sync~spin) Auto继续: 无工作区', '没有打开工作区,无法定位对话文件');
    return;
  }

  const now = Date.now();
  const m = latestMtime(dir);
  if (m > lastMtime) {
    lastMtime = m;
    lastChangeTs = now;
    sawActivity = true; // 观察到 agent 在写盘 = 它活着
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
    setStatus('$(eye) Auto继续: 等待活动', '等 agent 开始干活后才会接管(避免去捅已结束的对话)');
  } else {
    const idleLeft = Math.max(0, Math.ceil((idleLimit - idleMs) / 1000));
    setStatus(`$(eye) Auto继续: 监控中 ${idleLeft}s`, `空闲 ${idleLeft}s 后将发送继续 | 已发 ${continueCount} 次`);
  }
}

function start(context) {
  enabled = true;
  continueCount = 0;
  lastMtime = latestMtime(chatSessionsDir(context) || '');
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
