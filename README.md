# RemoteTool

RemoteTool is a local middleware for remote Linux control. It starts a GUI and a local HTTP API bound to 127.0.0.1; servers are saved in the GUI and remote commands are submitted to the local API so automation tools (for example Codex) only send Linux commands to the local API.

This avoids exposing remote server IPs, usernames, and passwords in chat windows. An automation agent only needs to know a saved server name, the local API port and the local token.

Features

- Support multiple servers and multiple accounts for agent use.
- Local HTTP API listens on 127.0.0.1:8765 by default; the port is configurable from the GUI.
- Every command must explicitly specify a server name to avoid sending commands to the wrong target in multi-server setups.
- Commands run automatically; the GUI displays the command list, status, stdout, stderr, exit code and execution time.
- SSH uses a persistent shell session so stateful operations like cd and export affect subsequent commands.
- Saved server connection info is encrypted in the local config file.
- Includes a built-in skill to make it easy for agents to access the local API when there is no conversation history.

Installation

Option 1 — Download the installer

1. Open the project's Releases page on GitHub and download the installer and the skill package.
2. In the GUI add a server: provide a server name, IP, port, username and password.
3. Click Connect. Once connected you can run remote commands from the GUI or the local HTTP API.

After installation the application stores configuration in the current user's profile by default:

Windows:

```text
%APPDATA%\RemoteTool\config.json
%APPDATA%\RemoteTool\config.key
```

Option 2 — Run from source

Requirements:

- Python 3.10 or newer
- uv
- Git

Clone the repository:

```powershell
git clone https://github.com/24kzhang/SSH-Tool-for-Agent.git
cd remote-tool
```

Install dependencies:

```powershell
uv sync --extra test --extra build
```

If PyPI is slow, use a mirror:

```powershell
uv sync --extra test --extra build --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

Start the GUI:

```powershell
uv run python app.py
```

Usage

1. Start RemoteTool.
2. Set the local API port and the default command timeout in the main window and save if needed.
3. Click Add Server and fill in the connection details.
4. Server names must be unique; agents and the local API select targets by server name.
5. Click Connect; when the status becomes Connected you can execute commands on the remote server.
6. The main window displays commands submitted by agents or the local API along with results.

![GUI.png](pic/GUI.png)

Agent invocation

We recommend calling RemoteTool via the local HTTP API. The config file stores the current api_host, api_port and api_token so agents can find the correct port even if the user changes it in the GUI. The skill should only read connection metadata — it must not expose or print server IP, usernames or passwords.

![提问.png](pic/%E6%8F%90%E9%97%AE.png)

Skill installation

After installing RemoteTool the distribution contains a `skills` folder. Copy the included `remote-server-control` skill into your agent's skills directory, for example:

```text
skills/remote-server-control
```

The skill does not hard-code install paths or HTTP ports. When using the skill, the agent should retrieve the config path in this order:

1. `REMOTE_TOOL_CONFIG_PATH` environment variable
2. Windows default: `%APPDATA%\RemoteTool\config.json`
3. Linux/macOS default: `$XDG_CONFIG_HOME/remote-tool/config.json` or `~/.config/remote-tool/config.json`

The skill only reads `api_host`, `api_port`, `api_token` and `servers[].name`. Do not output or leak server connection details.

Client example (source distribution)

You can also use `client.py` in the source tree to call the local API:

```powershell
uv run python client.py --server "dev" pwd
uv run python client.py --server "dev" conda env list
uv run python client.py --server "prod" --timeout 30 uptime
```

Note: `--server`, `--timeout` and other options must appear before the remote command.

Local HTTP API

All authenticated endpoints require the header:

```text
X-Remote-Token: <api_token from config.json>
```

Endpoints

- GET /api/health
- GET /api/servers
- POST /api/commands
- GET /api/commands/{id}

PowerShell example

```powershell
$configPath = $env:REMOTE_TOOL_CONFIG_PATH
if (-not $configPath) {
  $configPath = Join-Path $env:APPDATA "RemoteTool\config.json"
}

$cfg = Get-Content $configPath -Raw | ConvertFrom-Json
$headers = @{ "X-Remote-Token" = $cfg.api_token }
$base = "http://$($cfg.api_host):$($cfg.api_port)"

$body = @{
  server = "dev"
  cmd = "pwd"
  timeout = 30
  source = "manual-http"
} | ConvertTo-Json

$created = Invoke-RestMethod -Method Post -Uri "$base/api/commands" -Headers $headers -Body $body -ContentType "application/json"
Invoke-RestMethod -Method Get -Uri "$base/api/commands/$($created.id)" -Headers $headers
```

Always specify the `server` name in multi-server environments rather than relying on a default server.

Configuration file

Default locations:

Windows: `%APPDATA%\RemoteTool\config.json`
Linux/macOS: `~/.config/remote-tool/config.json` or `$XDG_CONFIG_HOME/remote-tool/config.json`

You can override the path using the `REMOTE_TOOL_CONFIG_PATH` environment variable.

Server connection information is encrypted inside `config.json`. The decryption key is stored in `config.key` in the same directory. If `config.key` is lost the saved server entries cannot be decrypted and must be re-added.

Security notes

- The local API is bound to `127.0.0.1` by default.
- The local API uses a random token for authentication.
- Agents do not need server IPs, usernames or passwords.
- Saved connection info uses simple local encryption and is not a system-level secure credential store.
- Do not check `config.json`, `config.key`, logs, build artifacts or virtual environments into public source control.
- v1 supports password authentication only. Future versions may add SSH key support, system credential stores and finer-grained access controls.
- Commands submitted to RemoteTool execute automatically — only run RemoteTool in trusted environments.

Development

Run tests:

```powershell
uv run --extra test pytest -q
```

Syntax check:

```powershell
uv run python -m py_compile app.py client.py config.py paths.py remote.py server.py
```

Project layout (common files)

```text
app.py                         # GUI and local API entrypoint
client.py                      # CLI HTTP client
config.py                      # config read/write, encryption and migration
paths.py                       # configuration path resolution
remote.py                      # persistent SSH shell execution
server.py                      # FastAPI local endpoints
assets/                        # icons and images
installer/windows/             # windows installer scripts
skills/remote-server-control/  # Codex/agent skill
tests/                         # automated tests
```

License

This project is licensed under the MIT License. See the `LICENSE` file for details.

