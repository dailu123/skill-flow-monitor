# Copilot Auto Continue

一个 VSCode 扩展,两种模式,都**不劫持鼠标键盘**:

- **babysit(保姆)**:检测到 Copilot agent 对话停下来后,自动发「继续」,救被中断的长任务。
- **driver(并行驱动器)**:多窗口分片并行消费 `PROGRESS.md` 队列——每个窗口认领一个分片,
  循环「开新会话 → 发提示词 → 等它跑完 → 下一个」,跑完该分片再认领下一片。配合 `parallel/shard.py`。

> 检测原理:对话转录是 `…/workspaceStorage/<hash>/chatSessions/<uuid>.jsonl`,agent 每走一步往里追加,
> 停下就不再变化。扩展监控它的修改时间判断「在跑 / 停了」,全程不模拟键鼠、不抢焦点。

## 多人分块协作 —— 把 N 千个块分给若干人,各跑各的,Git 汇总

适用场景:`PROGRESS.md` 是任务队列表,Copilot 按 `copilot-instructions.md` 的 LOOP 逐单元处理。
要多人分工又**不让大家改崩同一批文件**,做法是**分片成独立命名空间**(各有自己的
`work/`、`evidence/`、`notes/`)——不同人改的是完全不同的文件,**Git 合并零冲突**。

### 维护者(一次性)

```bash
# 1) 切片(按"文件数"均衡):hub 2000 → 10 片,mca 1000 → 10 片
python code-analysis-kit/parallel/shard.py split --repo hub --shards 10
python code-analysis-kit/parallel/shard.py split --repo mca --shards 10

# 2) 分配 + 生成每人可复制的「咒语」→ 写出 code-analysis-kit/ASSIGNMENTS.md
python code-analysis-kit/parallel/shard.py assign --repos hub,mca --people 10

# 把分片目录、shards.json、ASSIGNMENTS.md 提交推送
```

### 每个人

1. `git pull` → 打开本仓库 → 装本扩展(见下方安装)。
2. 在 `ASSIGNMENTS.md` 找到自己负责的命名空间(如 `hub__s3`、`mca__s3`)。
3. 对**每个命名空间**:在 Copilot agent 里**新开一个会话**,把该命名空间的「咒语」粘贴进去回车。
4. 点右下角状态栏开启 **babysit** —— agent 跑一会儿停了,它会自动发「继续」,你可以去干别的。
5. 跑完后**只提交自己命名空间的目录**(`work/<ns>`、`evidence/<ns>`、`notes/<ns>`),发 PR。

### 维护者汇总

```bash
# 看总进度
python code-analysis-kit/parallel/shard.py status --repo hub
# 合并所有人的 PR(因为各改各的文件,不会冲突),然后折叠回主仓库
python code-analysis-kit/parallel/shard.py merge --repo hub
python code-analysis-kit/parallel/shard.py merge --repo mca
```

### 关键点 / 注意

- **每个分片 = 一个独立"仓库" R**(`hub__s3`…)。咒语告诉 agent「本轮 R = hub__s3」,
  你现成的 `copilot-instructions.md` 里所有 `work/R`、`evidence/R`、`notes/R` 自动落到该分片目录,**零写冲突,不用改宪法**。
- **每人本地要有被分析的源码**:`PROGRESS.md` 顶部 `ROOT:` 指向真实源码路径,分析要读源文件;
  约定好统一路径,源码本身别提交进本仓库(`.gitignore` 掉)。
- 建议每人打开 `chat.tools.autoApprove`,否则 agent 会停在「Allow」批准上,babysit 发「继续」也推不动。
- `merge` 会智能去重 CSV 表头、按 ID 回填 PROGRESS 状态、搬运 notes;确认无误后可 `clean` 清分片目录。

> 注:扩展里还有一个 `driver` 单机自动模式(命令「启动并行驱动器」),能在一个窗口里循环逐单元跑;
> 多人分工场景用不到它,上面的「咒语 + babysit」就够。

## babysit 原理

- Copilot 的对话实时落盘到 `…/workspaceStorage/<hash>/chatSessions/<uuid>.jsonl`,agent 每走一步都会写。
- 扩展监控:**连续 N 秒不再写入** = 它停了 → 用 `workbench.action.chat.open` 把「继续」提交进当前 chat。
- 全在扩展内部完成,不模拟键鼠、不抢焦点。

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
