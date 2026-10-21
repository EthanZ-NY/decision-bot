# 部署指南（无 GitHub / 无 Render）

## 方案一：本地电脑 + ngrok（最快，5分钟）

适合：想立刻测试、不介意电脑一直开着

### 1. 安装依赖

```bash
# 1. 安装 Python 3.10+（如果还没有）
# 2. 解压代码包
# 3. 进入代码目录
pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件：

```bash
BOT_MODE=app
FEISHU_APP_ID=cli_aa52ebf90678dd04
FEISHU_APP_SECRET=nozLsnmLOMQ2fgq5Ndy4zgv1Oa4ZDYP2
```

### 3. 启动服务

```bash
python main.py
```

服务启动后会显示 `http://0.0.0.0:8000`，但这不是公网地址，飞书访问不到。

### 4. 安装 ngrok 暴露公网地址

```bash
# macOS
brew install ngrok

# Windows
# 下载 https://ngrok.com/download 并解压

# Linux
wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz
tar xvzf ngrok-v3-stable-linux-amd64.tgz
```

注册 ngrok 账号（免费）：https://dashboard.ngrok.com/signup

获取 Authtoken（登录后在个人设置里），执行：

```bash
ngrok config add-authtoken 你的token
```

### 5. 启动 ngrok 隧道

另开一个终端：

```bash
ngrok http 8000
```

会显示一个公网地址，例如：

```
Forwarding  https://abc123.ngrok-free.app -> http://localhost:8000
```

### 6. 配置飞书回调

复制 `https://abc123.ngrok-free.app/webhook/feishu/event`，填入飞书「事件与回调」→ 请求网址。

> 注意：ngrok 免费版每次重启地址会变，需要重新配置飞书。如果嫌麻烦，可以用方案二。

---

## 方案二：PythonAnywhere（免费，固定地址）

适合：不想本地一直开着电脑

### 1. 注册账号

https://www.pythonanywhere.com/registration/register/begin/

### 2. 上传代码

1. 登录后进入 Dashboard → Files → Upload a file
2. 上传 `decision-bot-mvp-hybrid.zip`
3. 在 Bash console 中执行：

```bash
unzip decision-bot-mvp-hybrid.zip
cd decision-bot-mvp-hybrid
pip install -r requirements.txt --user
```

### 3. 配置环境变量

在 Dashboard → Account → Environment variables 中添加：

- `BOT_MODE` = `app`
- `FEISHU_APP_ID` = `cli_aa52ebf90678dd04`
- `FEISHU_APP_SECRET` = `nozLsnmLOMQ2fgq5Ndy4zgv1Oa4ZDYP2`

### 4. 创建 Web App

1. Dashboard → Web → Add a new web app
2. 选择「Manual configuration」→ Python 3.10
3. 在 WSGI 文件路径中指向 `main.py`
4. 或者更简单：在 Bash console 中执行 `python main.py &`

### 5. 拿到公网地址

PythonAnywhere 会给你分配一个固定地址，例如：

```
https://你的用户名.pythonanywhere.com
```

填入飞书「事件与回调」→ 请求网址：`https://你的用户名.pythonanywhere.com/webhook/feishu/event`

---

## 方案三：Replit（最简单，浏览器里搞定）

适合：什么都不想装

### 1. 注册 Replit

https://replit.com/ 用 Google/Apple/GitHub 账号登录（不需要 GitHub 仓库）

### 2. 导入代码

1. Create → Import from GitHub（不需要有仓库，可以上传）
2. 或者直接 Create → Python → 把代码文件一个个拖进去
3. 更简单：上传 zip 后解压

### 3. 配置环境变量

左侧 Secrets（🔒 图标）→ 添加：

- `BOT_MODE` = `app`
- `FEISHU_APP_ID` = `cli_aa52ebf90678dd04`
- `FEISHU_APP_SECRET` = `nozLsnmLOMQ2fgq5Ndy4zgv1Oa4ZDYP2`

### 4. 运行

点击「Run」按钮，Replit 会自动分配一个公网 URL（右侧 Webview 里能看到）。

把 `https://你的项目名.用户名.repl.co/webhook/feishu/event` 填入飞书回调。

> Replit 免费版需要每 30 天重新激活一次，且服务会在 30 分钟无访问后休眠，第一次访问会慢几秒。

---

## 飞书配置（三种方案通用）

部署完成后：

1. 打开 https://open.feishu.cn/app，进入你的应用
2. 「事件与回调」→ 请求网址填入：`https://你的公网地址/webhook/feishu/event`
3. 「事件订阅」→ 添加 `im.message.receive_v1`
4. 「权限管理」→ 申请 `im:message:send_as_bot`
5. 「添加应用能力」→ 启用「机器人」
6. 发布版本，把机器人添加到你的飞书会话

然后给机器人发：「想买 Sony A7M4，大概 1 万 5」测试。
