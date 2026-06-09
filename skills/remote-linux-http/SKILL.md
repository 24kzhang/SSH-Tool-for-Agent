---
name: remote-linux-http
description: Use when the user wants Codex to run Linux commands through a local Remote Tool HTTP gateway while keeping server IP, account, and password out of chat. Always route commands by an explicit saved server name and read the current HTTP host, port, and token from the Remote Tool config path.
---

# Remote Linux HTTP

Use this skill to access remote Linux servers through a locally running Remote Tool GUI/API.

## Rules

- Never ask for, print, infer, or expose server IP, username, or password.
- Never SSH directly. Use only the local Remote Tool HTTP API or its client wrapper.
- Always target a saved server by explicit server name.
- If more than one server is saved and the user did not name one, ask which server name to use.
- HTTP command execution is automatic. Run only the command the user requested.
- If the GUI service is closed or the target server is disconnected, report that and stop.

## Find Config

Always read the config file immediately before making HTTP requests. Do not hardcode the default port.

Find the config file in this order:

1. Use `$env:REMOTE_TOOL_CONFIG_PATH` if it is set.
2. On Windows, use `$env:APPDATA\RemoteTool\config.json`.
3. On Linux or macOS, use `$env:XDG_CONFIG_HOME\remote-tool\config.json` if `XDG_CONFIG_HOME` is set, otherwise `~/.config/remote-tool/config.json`.
4. If the config file is missing, tell the user to start Remote Tool once or set `REMOTE_TOOL_CONFIG_PATH`.

Use only these fields:

- `api_host`
- `api_port`
- `api_token`
- `servers[].name`

Do not reveal other fields from the config file.

PowerShell pattern:

```powershell
$configPath = $env:REMOTE_TOOL_CONFIG_PATH
if (-not $configPath) { $configPath = Join-Path $env:APPDATA "RemoteTool\config.json" }
$cfg = Get-Content $configPath -Raw | ConvertFrom-Json
```

## Choose Server

- If the user named a server, use that exact saved name.
- If no server was named and exactly one saved server exists, use that saved name explicitly.
- If no server was named and multiple saved servers exist, ask the user to choose a server name.
- If the requested name is not in `servers[].name`, tell the user it is not saved.

## Direct HTTP Execution

Use direct HTTP by default. It does not require knowing where the executable is installed.

```powershell
$headers = @{ "X-Remote-Token" = $cfg.api_token }
$base = "http://$($cfg.api_host):$($cfg.api_port)"
$body = @{
  server = "<server-name>"
  cmd = "<linux-command>"
  timeout = 120
  source = "codex-skill"
} | ConvertTo-Json
$cmd = Invoke-RestMethod -Method Post -Uri "$base/api/commands" -Headers $headers -Body $body -ContentType "application/json"
```

Poll until `status` is `completed`, `failed`, or `timeout`:

```powershell
Invoke-RestMethod -Method Get -Uri "$base/api/commands/$($cmd.id)" -Headers $headers
```

## Health Checks

Use `GET /api/health` to check whether the GUI service is running. Use `GET /api/servers` with the token to see saved server names and connection status.

If the configured port was changed in the GUI, the config file contains the new `api_port`; use that value.
