# 本地远程 Linux 控制中间程序

这个工具在本机启动 PySide6 图形界面，并监听本地 HTTP API。Codex 通过服务器名称提交 Linux 指令，不需要知道远程服务器 IP、账号或密码。

## 配置位置

程序现在优先读取环境变量：

```powershell
REMOTE_TOOL_CONFIG_PATH
```

如果没有设置，Windows 默认配置文件为：

```text
%APPDATA%\RemoteTool\config.json
```

服务器连接信息会加密保存到 `config.json`，解密 key 保存在同目录的 `config.key`。

用户在 GUI 中修改 HTTP 端口后，新端口会写入同一个 `config.json`。Skill 每次访问前读取这个配置文件，所以不会因为端口变化而继续访问旧端口。

## 安装开发依赖

```powershell
cd /d F:\remote_tool
uv sync --extra test --extra build --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

## 启动 GUI

源码运行：

```powershell
F:\remote_tool\.venv\Scripts\python.exe F:\remote_tool\app.py
```

打包后运行：

```powershell
F:\remote_tool\dist\RemoteTool\RemoteTool.exe
```

## GUI 使用

- 主界面不直接展示账号密码。
- 点击“添加并连接”，在弹窗中输入服务器名称、IP、端口、账号、密码。
- 服务器名称不能重复，最多保存 6 个服务器。
- 保存后的服务器可在主界面快速连接、断开、编辑、删除。
- HTTP 指令会自动执行，不再需要人工审核。
- 本地 HTTP 端口可在 GUI 中修改，保存后会自动重启本地 API。

## Codex 调用方式

直接 HTTP 是推荐方式，因为它只依赖配置文件中的端口和 token。

如果使用源码版客户端，必须显式指定服务器名称：

```powershell
F:\remote_tool\.venv\Scripts\python.exe F:\remote_tool\client.py --server "dev" pwd
F:\remote_tool\.venv\Scripts\python.exe F:\remote_tool\client.py --server "dev" conda env list
F:\remote_tool\.venv\Scripts\python.exe F:\remote_tool\client.py --server "prod" --timeout 30 uptime
```

参数必须放在 Linux 命令前面。

## 本地 API

- `GET /api/health`
- `GET /api/servers`
- `POST /api/commands`
- `GET /api/commands/{id}`

`GET /api/servers`、`POST /api/commands`、`GET /api/commands/{id}` 必须带请求头：

```text
X-Remote-Token: config.json 中的 api_token
```

PowerShell 直接 HTTP 示例：

```powershell
$configPath = $env:REMOTE_TOOL_CONFIG_PATH
if (-not $configPath) { $configPath = Join-Path $env:APPDATA "RemoteTool\config.json" }
$cfg = Get-Content $configPath -Raw | ConvertFrom-Json
$headers = @{ "X-Remote-Token" = $cfg.api_token }
$body = @{ server = "dev"; cmd = "pwd"; timeout = 30; source = "codex-http" } | ConvertTo-Json
$base = "http://$($cfg.api_host):$($cfg.api_port)"
$cmd = Invoke-RestMethod -Method Post -Uri "$base/api/commands" -Headers $headers -Body $body -ContentType "application/json"
Invoke-RestMethod -Method Get -Uri "$base/api/commands/$($cmd.id)" -Headers $headers
```

## Codex Skill

项目内置 Skill：

```text
skills\remote-linux-http
```

这个 Skill 不硬编码安装目录或 HTTP 端口。Codex 使用时优先读取 `REMOTE_TOOL_CONFIG_PATH`，否则读取系统默认用户配置目录中的 `config.json`。

## 打包

当前先提供 PyInstaller 可执行目录包：

```powershell
uv run --extra build pyinstaller RemoteTool.spec --noconfirm --clean
```

生成目录：

```text
dist\RemoteTool
```

后续如果要做完整安装包，可以基于这个目录再接 Inno Setup、WiX 或 NSIS，并在安装时设置 `REMOTE_TOOL_CONFIG_PATH`。

## 安全说明

- API 默认只监听 `127.0.0.1`。
- 本地 API 使用随机 token。
- 服务器连接信息在 `config.json` 中以简单加密形式保存。
- `config.key` 与 `config.json` 需要一起保留；如果丢失 `config.key`，已保存的服务器连接信息无法解密。
- v1 仅支持密码登录；后续可以增加 SSH key 和 Windows 凭据管理器。
