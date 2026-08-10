# QQ 通知 / 命令通道接入说明

> 结论：**不能直接连接个人微信/QQ 账号**（第三方协议接入有封号风险，微信个人号基本无官方开放通道）。
> 本项目采用 **QQ 官方开放平台机器人** 方案，需要你到 QQ 开放平台申请一个官方机器人并通过审核后，才能收到投递结果通知和发送命令。

## 前置条件
1. 注册 [QQ 开放平台](https://q.qq.com) 并完成开发者认证（个人/企业均可）。
2. 创建一个「机器人」应用，接入渠道选择 **QQ 频道 / 单聊（C2C）**，提交审核。
3. 审核通过后，在机器人管理页拿到：
   - `AppID`
   - `AppSecret`
   - 机器人的 `openid`

## 配置
在 `backend/.env` 中添加：

```ini
QQ_BOT_ENABLED=true
QQ_BOT_APP_ID=你的AppID
QQ_BOT_APP_SECRET=你的AppSecret
QQ_BOT_TARGET_UID=接收消息的QQ用户openid
```

- `QQ_BOT_TARGET_UID` 是**接收通知的 QQ 用户 openid**（不是QQ号）。
  获取方式：用户在 QQ 里主动给机器人发一条消息后，从机器人收到的消息事件里取 `author.id`（C2C 场景的 openid）。
- 未配置或 `QQ_BOT_ENABLED=false` 时，通知通道自动跳过，不影响投递功能。

## 通知内容
- 每轮批量投递完成后推送：任务ID / 总数 / 成功数 / 失败数 / 剩余名额 / 关键失败原因。
- 命令通道（后续迭代）：在 QQ 里向机器人发送 `状态`、`继续投递`、`停止` 等指令，机器人回传执行结果。
  命令解析依赖服务端主动拉取消息（通过机器人 API 轮询），需要 `QQ_BOT_APP_SECRET` 换取 `access_token` 后调用
  `GET https://bots.qq.com/api/v3/guilds/{guild_id}/messages`（频道）或 C2C 消息接口（单聊）。

## 安全提醒
- AppSecret 只保存在本机 `.env`，不要提交到 GitHub。
- 不要尝试用 anytone/go-cqhttp 等非官方协议登录个人QQ号，极易触发腾讯风控导致封号。
