# QQ ↔ Codex 接入说明（在 QQ 里直接跟 Codex 对话）

> 本模块让 **Codex 本身接入 QQ**（不是投递软件接入）：在 QQ 里给机器人发消息，消息会交给本地 Codex
> 处理——它可以读项目、跑命令、改文件，然后把结果回传到你的 QQ。每个 QQ 用户对应一个独立的
> Codex 会话，上下文连续，重启桥接后仍能续接。

## 工作原理

```
QQ 用户 ──发消息──▶ QQ开放平台机器人（C2C单聊）
                        │ 事件网关 WebSocket（wss://api.sgroup.qq.com/websocket）
                        ▼
                  codex_qq 桥接（本模块，运行在本地）
                        │ 1. 校验白名单，调用本地 codex CLI：codex exec [resume <会话>]
                        │    （复用 ~/.codex 配置与登录，工作目录=你的项目根）
                        │ 2. 处理期间不发任何状态消息（QQ 客户端自带"加载中"动画）
                        ▼
                  处理完毕 ──分块流式──▶ 结果分小块陆续回传 QQ（模拟流式输出）
```

- 处理期间**不发送任何状态消息**（QQ 客户端自带"加载中"动画，不打断它）；
  但超过 30 秒仍无回复时会补一句轻提示（默认"还在弄哦，稍等一下下~"，可用
  `QQ_SLOW_HINT` 自定义），避免长任务时显得没反应。回复完成后内容拆成小块、
  隔 0.35s 陆续到达，看起来像流式输出。
- 提示与分块默认走被动回复（收到消息后 5 分钟内有效），超时自动退回主动消息；长任务较多时
  注意 QQ 开放平台的主动消息配额。
- 主动消息受 QQ 开放平台频率限制（个人机器人每天有配额），长任务较多时注意用量。
- 流式输出的块大小/间隔在 `codex_qq/bridge.py` 的 `STREAM_CHUNK_SIZE`、`STREAM_CHUNK_DELAY`
  里调整（默认 150 字符 / 0.35s）。

## 前置条件

1. 在 [QQ 开放平台](https://q.qq.com) 注册并完成开发者认证。
2. 创建「机器人」应用，接入渠道选择 **单聊（C2C）**，提交审核。
3. 审核通过后拿到 `AppID` 与 `AppSecret`。
4. 安装依赖：
   - Python：`pip install websockets httpx`
   - Codex CLI：`npm install -g @openai/codex`（桥接会调用 `codex exec`，复用
     `~/.codex/config.toml` 里的模型与登录配置）
5. 获取允许对话的 QQ 用户 openid：在 QQ 里**主动给机器人发一条消息**建立会话，
   然后从桥接日志中查看 `author.id`（或机器人后台消息记录），填入白名单。

## 配置

```powershell
cd codex_qq
Copy-Item .env.example .env
# 编辑 .env：
```

```ini
QQ_BOT_APP_ID=你的AppID
QQ_BOT_APP_SECRET=你的AppSecret
QQ_BOT_SANDBOX=false
QQ_ALLOW_UIDS=接收人的openid,可多个用逗号分隔
```

- `QQ_BOT_SANDBOX=true` 使用沙箱网关调试（`wss://sandbox.api.sgroup.qq.com`），正式上线设 `false`。
- `QQ_ALLOW_UIDS` 是安全白名单：**留空会拒绝所有 QQ 消息**，务必填写。
  圆点会自动在文案后增减。
- 可选：`CODEX_BIN`（codex CLI 路径）、`CODEX_WORKDIR`（Codex 工作目录，默认项目根）、
  `CODEX_TIMEOUT`（单条消息超时秒数，默认 1800）。
- 可选人格设定（默认开启）：机器人回复会按 `codex_qq/persona/maya.md` 里定义的
  「赛博黑奴摩耶酱」人设说话。设定只在**新会话的第一条消息**注入，续接的旧会话沿用旧上下文。
  编辑该文件即可调整人设；`PERSONA_ENABLED=false` 关闭，`PERSONA_FILE` 可换成其他设定文件。

## 启动

```powershell
python -m codex_qq.cli bridge
```

启动后保持窗口运行即可。断线会自动重连。


## QQbot 常驻在线（看门狗保活）

> 已注册：开机登录后自动启动，QQbot **常驻在线**，不随 Codex 桌面 App 开关，随时可聊。

- `codex_qq/qqbot_watchdog.ps1`：后台保活看门狗，每 10 秒检查一次：
  - QQbot 不在线 → 自动拉起（隐藏窗口，日志写 `data/bridge.log`）；
  - 桥接意外崩溃 → 记录原因并自动重启重连；
  - 连续快速崩溃（启动 30s 内）达 5 次 → 停止自动重启，防止死循环。
- 注册方式：`codex_qq/qqbot_watchdog_autostart.vbs` 已复制到用户「启动」文件夹，
  开机登录后自动运行。
- 看门狗日志：`codex_qq/data/watchdog.log`；单实例保护，重复启动会自动退出。
- 想彻底停掉：删除启动文件夹里的 `qqbot_watchdog_autostart.vbs`，
  结束 `qqbot_watchdog.ps1` 的 powershell 进程，以及 `codex_qq.cli bridge` 的 python 进程。

### 崩溃自动处理
- 桥接异常退出时：看门狗自动把崩溃证据（`bridge.log.err` / `bridge.log` 尾部 + 连续崩溃次数）
  写入 `data/bridge.crash.log`，然后自动重启重连。
- 桥接进程内的未捕获异常：`cli.py` 会先写入 `data/crash.log`（完整 traceback）再退出，避免原因丢失。
- 连续快速崩溃（启动 30s 内）达 5 次会停止自动重启，防止死循环；
  此时请把 `data/bridge.crash.log` / `data/crash.log` 的内容发出来修复根因。

## 常用命令

```powershell
python -m codex_qq.cli status            # 查看配置、白名单、codex 通路状态
python -m codex_qq.cli chat "你好"        # 本地测试 Codex 通路（不经过 QQ）
python -m codex_qq.cli send <openid> "文本"  # 主动推送一条消息到 QQ
python -m codex_qq.cli bridge            # 启动桥接（默认命令）
```

## 会话管理

- 每个 QQ 用户一个独立 Codex 会话，session id 保存在 `codex_qq/data/sessions.json`。
- 同一用户的连续消息会排队串行处理，避免上下文交错。
- 删除某用户的 session 文件条目即可重置该用户的 Codex 记忆。
- 改完人设后想立刻生效：删除 `codex_qq/data/sessions.json` 里对应 openid 的条目，
  再发一条新消息即可（会新建会话并注入新设定）。

## 安全提醒

- `AppSecret` 只保存在本机 `codex_qq/.env`（已被 .gitignore 忽略），不要提交到仓库。
- 白名单一定要配：Codex 在项目目录有完整执行能力，只允许你信任的 QQ 账号对话。
- 不要使用 anytone/go-cqhttp 等非官方协议登录个人 QQ，极易触发风控封号。