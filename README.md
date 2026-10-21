# 决策助手 — 个人生活决策系统

飞书机器人 + FastAPI 后端，帮助你在冲动消费前按下暂停键。

## 混合方案（推荐）

本方案同时支持两种飞书机器人能力：

| 能力 | 方式 | 用途 |
|------|------|------|
| **接收消息** | 自建应用（Event Subscription） | 你直接跟机器人对话，输入想法、查看评分 |
| **推送报告** | 群机器人 Webhook（可选） | 周报/月报自动推送到指定群（如家庭群） |

> 如果只想要"自己偷偷用"，不填 Webhook URL 即可，所有消息通过自建应用发给你本人。

## 快速启动

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，按需修改：

```bash
# 主模式固定为 app（接收消息必须用自建应用）
BOT_MODE=app

# 自建应用凭证（已填入你的凭证）
FEISHU_APP_ID=cli_aa52ebf90678dd04
FEISHU_APP_SECRET=nozLsnmLOMQ2fgq5Ndy4zgv1Oa4ZDYP2

# 群机器人 Webhook（可选）
# 在飞书群里添加「自定义机器人」→ 复制 webhook 地址填入
# FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
```

### 3. 启动服务

```bash
python main.py
```

访问 http://localhost:8000/health 验证。

## 部署到 Render

1. 注册 [Render](https://render.com)，用 GitHub 登录
2. New + → Web Service → Build and deploy from a Git repository
3. 把代码推送到 GitHub 仓库，选择该仓库
4. 配置：
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py`
5. 在「Environment」中添加：
   - `BOT_MODE` = `app`
   - `FEISHU_APP_ID` = `cli_aa52ebf90678dd04`
   - `FEISHU_APP_SECRET` = `nozLsnmLOMQ2fgq5Ndy4zgv1Oa4ZDYP2`
   - `FEISHU_WEBHOOK_URL` = （可选，群机器人 webhook 地址）
6. 点击「Create Web Service」，等待部署完成
7. 复制生成的公网 URL（如 `https://decision-bot-xxxxx.onrender.com`）

## 飞书应用配置

部署完成后，回到 [飞书开放平台](https://open.feishu.cn/app)：

1. 打开你的应用 →「事件与回调」
2. **请求网址**：填入 `https://你的域名/webhook/feishu/event`
3. **加密密钥**：留空
4. 在「事件订阅」中添加：
   - `im.message.receive_v1`
5. 在「权限管理」中申请：
   - `im:message:send_as_bot`
   - `im:chat:readonly`
6. 「添加应用能力」→「机器人」→ 启用
7. 发布版本，将机器人添加到你的飞书会话中

### 可选：配置群机器人 Webhook（用于推送报告）

1. 打开你想接收报告的飞书群
2. 群设置 → 群机器人 → 添加机器人 → 自定义机器人
3. 复制 webhook 地址
4. 填入 Render 环境变量 `FEISHU_WEBHOOK_URL`
5. 重启服务

## 本地测试（Mock 模式）

```bash
export BOT_MODE=mock
python main.py

# 另开终端测试
curl -X POST http://localhost:8000/mock/message \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test_user", "text": "想买 Sony A7M4，大概 1 万 5"}'
```

## 项目结构

```
.
├── main.py              # FastAPI 入口
├── config.py            # 环境变量配置
├── models.py            # SQLAlchemy 数据模型
├── parser.py            # 自然语言解析
├── scoring.py           # 五维度评分引擎
├── feishu_client.py     # 飞书客户端（app + webhook 混合）
├── handlers.py          # 消息处理器
├── scheduler.py         # 定时任务
├── requirements.txt     # 依赖
├── Procfile            # 部署入口
├── .env.example        # 环境变量模板
└── README.md           # 本文档
```

## 核心功能

| 功能 | 说明 |
|------|------|
| 想法录入 | 一句话记录冲动想法，自动解析金额和分类 |
| 即时评分 | 五维度加权评分 |
| 冷静期 | 自动 72h 延迟，到期提醒 |
| 预算管理 | 月度冲动预算设置 + 实时余量检查 |
| 拦截记录 | 成功拦截标记 + 累计节省金额 |
| 满意度追踪 | 执行 7 天后自动回访 |
| 定时报告 | 每周一 / 每月 1 日自动推送（支持 webhook 到群） |

## 消息指令

| 指令 | 效果 |
|------|------|
| 想买 XXX，大概 Y 元 | 记录想法 + 评分 + 预算检查 |
| 确认 | 执行当前想法 |
| 不买了 / 取消 | 拦截当前想法 |
| 冷静 | 启动 72h 冷静期 |
| 设置预算 XXXX | 设置本月冲动预算 |
| 查看预算 | 查看预算余量 |
| 历史 / 记录 | 查看最近想法清单 |
| 帮助 | 查看使用指南 |
