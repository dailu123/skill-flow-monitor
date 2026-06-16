# Copilot Auto Continue

一个极小的 VSCode 扩展:检测到 Copilot **agent 对话停下来**后,自动帮你发送「继续」,
**不劫持鼠标键盘**,你可以同时干别的活。

## 原理

- Copilot 的对话会实时落盘到 `…/workspaceStorage/<hash>/chatSessions/*.json`,agent 每走一步都会写。
- 扩展监控这些文件:**连续 N 秒不再写入** = 它停了 → 用官方命令 `workbench.action.chat.open` 把「继续」提交进当前 chat。
- 这两件事都在扩展内部完成,不模拟键鼠,不抢焦点。

## 安装

### 方式一:装 .vsix(推荐,最稳)

本目录已附带打包好的 `copilot-auto-continue-0.0.1.vsix`。任选一种:

- 命令行:
  ```
  code --install-extension copilot-auto-continue-0.0.1.vsix
  ```
- 或:扩展侧栏右上角 `...` 菜单 → **Install from VSIX...** → 选这个文件。

装完 `Developer: Reload Window` 或重启 VSCode。

### 方式二:直接复制文件夹(不一定生效,新版 VSCode 常忽略)

把整个 `copilot-auto-continue` 文件夹复制到扩展目录,**注意 `package.json` 必须直接在该层、不能套娃**:

- Windows:`%USERPROFILE%\.vscode\extensions\copilot-auto-continue\package.json`
- macOS/Linux:`~/.vscode/extensions/copilot-auto-continue/package.json`
- Insiders 版要放 `.vscode-insiders\extensions\`

然后**完全退出并重启 VSCode**(光关窗口不够)。

> 装完确认:命令面板运行 `Developer: Show Running Extensions`,或扩展侧栏搜 `Copilot Auto Continue`。
> 加载成功的话右下角状态栏会出现 `Auto继续: 关`。看不到就是没加载,改用方式一。

### 方式三:开发调试

用 VSCode 打开本文件夹,按 `F5` 启动「扩展开发宿主」窗口测试。

> 你**不需要**手工往 settings.json 里加任何配置,所有设置都有默认值,装上即可用。

## 使用

1. 重启后,右下角状态栏会出现 **`Auto继续: 关`**。
2. 在 Copilot agent 里发起你的大循环任务。
3. **点状态栏那个按钮**开启 → 变成 `Auto继续: 等待活动`。
4. 它先等 agent 开始写盘(确认对话是活的),之后只要空闲超过设定秒数,就自动发「继续」。
5. 想停就再点一下状态栏,或命令面板 `Copilot Auto Continue: 开关监控`。

> 命令面板还有 `Copilot Auto Continue: 立即发送一次继续`,可手动捅一下。

## 设置(`settings.json`,前缀 `copilotAutoContinue.`)

| 设置 | 默认 | 说明 |
|---|---|---|
| `enabledOnStartup` | `false` | 启动即开启监控 |
| `idleSeconds` | `300` | 空闲多少秒判定为停止(太短会在模型思考时误触发) |
| `message` | `继续` | 自动发送的内容 |
| `pollSeconds` | `5` | 检查文件的间隔 |
| `cooldownSeconds` | `300` | 发送后冷却多久再恢复监控 |
| `maxContinues` | `100` | 本次最多自动发多少次(防止任务真干完后无限刷) |
| `ignoreFiles` | `["state.json","states.json"]` | 扫描时忽略的文件名(会话元数据,跟聊天无关也会变,会误判) |

## 注意 / 调试

- **只在「模型主动收手」时用**。如果它是停在「等你批准命令(Allow)」,这个扩展发「继续」未必有用,那种情况请开 `chat.tools.autoApprove`。
- **`idleSeconds` 是关键**:先用 30s。若发现它在模型还在思考时就误发,调大到 45~60。
- **首次务必验证**:开启后看它发的「继续」是不是进了**当前那个 agent 对话**(而不是新开了对话)。如果进错了,告诉我,我换成 `workbench.action.chat.submit` 之类的方案。
- **安全阀**:到 `maxContinues` 会自动停;任务其实早干完的话它会一直发到上限,所以别把上限设太离谱,且建议人偶尔瞄一眼。
- 看不到日志可在 `帮助 → 切换开发人员工具` 的 Console 里看报错。
