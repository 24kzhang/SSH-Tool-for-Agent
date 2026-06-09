from pathlib import Path

from fastapi.testclient import TestClient
from fastapi import FastAPI
from PySide6.QtWidgets import QApplication

import app as app_module
from config import AppConfig, ServerConfig, load_config, save_config, validate_servers
from client import parse_args
from remote import RemoteShell
from server import CommandManager, create_app
from paths import get_config_path, get_encryption_key_path


def test_config_path_prefers_remote_tool_config_path(tmp_path: Path, monkeypatch):
    custom = tmp_path / "custom-config.json"
    monkeypatch.setenv("REMOTE_TOOL_CONFIG_PATH", str(custom))

    assert get_config_path() == custom


def test_config_path_defaults_to_appdata_remote_tool(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("REMOTE_TOOL_CONFIG_PATH", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert get_config_path() == tmp_path / "RemoteTool" / "config.json"


def test_config_creates_token_and_persists_plain_password(tmp_path: Path):
    path = tmp_path / "config.json"

    config = load_config(path)
    config.servers = [
        ServerConfig(
            name="dev",
            host="192.0.2.10",
            port=2222,
            username="root",
            password="plain-secret",
        )
    ]
    save_config(path, config)

    loaded = load_config(path)

    assert loaded.servers[0].name == "dev"
    assert loaded.servers[0].host == "192.0.2.10"
    assert loaded.servers[0].port == 2222
    assert loaded.servers[0].username == "root"
    assert loaded.servers[0].password == "plain-secret"
    assert len(loaded.api_token) >= 32


def test_save_config_encrypts_server_details(tmp_path: Path):
    path = tmp_path / "config.json"
    config = AppConfig(
        api_token="secret-token",
        servers=[
            ServerConfig(
                name="dev",
                host="192.0.2.10",
                port=2222,
                username="root",
                password="plain-secret",
            )
        ],
    )

    save_config(path, config)
    raw = path.read_text(encoding="utf-8")
    loaded = load_config(path)

    assert get_encryption_key_path(path).exists()
    assert "enc:v1:" in raw
    assert "192.0.2.10" not in raw
    assert "2222" not in raw
    assert "root" not in raw
    assert "plain-secret" not in raw
    assert loaded.servers[0].host == "192.0.2.10"
    assert loaded.servers[0].port == 2222
    assert loaded.servers[0].username == "root"
    assert loaded.servers[0].password == "plain-secret"


def test_config_migrates_single_server_from_old_schema(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_text(
        """
{
  "host": "192.0.2.20",
  "port": 22,
  "username": "alice",
  "password": "plain-secret",
  "api_token": "secret-token"
}
""",
        encoding="utf-8",
    )

    loaded = load_config(path)

    assert loaded.api_token == "secret-token"
    assert len(loaded.servers) == 1
    assert loaded.servers[0].name == "default"
    assert loaded.servers[0].host == "192.0.2.20"
    assert loaded.servers[0].password == "plain-secret"
    assert "192.0.2.20" not in path.read_text(encoding="utf-8")


def test_load_config_migrates_plaintext_servers_to_encrypted(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_text(
        """
{
  "api_token": "secret-token",
  "servers": [
    {
      "name": "dev",
      "host": "192.0.2.30",
      "port": 2200,
      "username": "alice",
      "password": "plain-secret"
    }
  ]
}
""",
        encoding="utf-8",
    )

    loaded = load_config(path)
    raw = path.read_text(encoding="utf-8")

    assert loaded.servers[0].host == "192.0.2.30"
    assert loaded.servers[0].port == 2200
    assert loaded.servers[0].username == "alice"
    assert loaded.servers[0].password == "plain-secret"
    assert "enc:v1:" in raw
    assert "192.0.2.30" not in raw
    assert "2200" not in raw
    assert "alice" not in raw
    assert "plain-secret" not in raw


def test_config_loads_json_with_utf8_bom(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_text(
        """
{
  "api_host": "127.0.0.1",
  "api_port": 9010,
  "api_token": "secret-token",
  "servers": []
}
""",
        encoding="utf-8-sig",
    )

    loaded = load_config(path)

    assert loaded.api_port == 9010
    assert loaded.api_token == "secret-token"


def test_server_names_must_be_unique_and_limited_to_six():
    duplicate = [
        ServerConfig(name="dev", host="h1", username="u", password="p"),
        ServerConfig(name="dev", host="h2", username="u", password="p"),
    ]
    too_many = [
        ServerConfig(name=f"s{i}", host="h", username="u", password="p")
        for i in range(7)
    ]

    assert "不能重复" in validate_servers(duplicate)[0]
    assert "最多保存 6 个服务器" in validate_servers(too_many)[0]


def test_api_rejects_missing_or_wrong_token():
    config = AppConfig(api_token="secret-token")
    manager = CommandManager(config)
    client = TestClient(create_app(manager))

    assert client.post("/api/commands", json={"cmd": "echo hi"}).status_code == 401
    assert client.post(
        "/api/commands",
        headers={"X-Remote-Token": "bad"},
        json={"cmd": "echo hi"},
    ).status_code == 401


def test_api_requires_known_server_name_and_auto_queues_command():
    config = AppConfig(
        api_token="secret-token",
        servers=[ServerConfig(name="dev", host="host", username="u", password="p")],
    )
    manager = CommandManager(config)
    client = TestClient(create_app(manager))

    missing = client.post(
        "/api/commands",
        headers={"X-Remote-Token": "secret-token"},
        json={"cmd": "echo hi"},
    )
    unknown = client.post(
        "/api/commands",
        headers={"X-Remote-Token": "secret-token"},
        json={"server": "prod", "cmd": "echo hi"},
    )
    response = client.post(
        "/api/commands",
        headers={"X-Remote-Token": "secret-token"},
        json={"server": "dev", "cmd": "echo hi"},
    )
    body = response.json()

    assert missing.status_code == 422
    assert unknown.status_code == 404
    assert response.status_code == 200
    assert body["server"] == "dev"
    assert body["status"] == "queued"

    command = manager.get(body["id"])
    assert command is not None
    manager.mark_running(command.id)
    manager.complete(command.id, stdout="hi\n", stderr="", exit_code=0, duration_ms=12)

    result = client.get(
        f"/api/commands/{command.id}",
        headers={"X-Remote-Token": "secret-token"},
    ).json()

    assert result["status"] == "completed"
    assert result["server"] == "dev"
    assert result["stdout"] == "hi\n"
    assert result["exit_code"] == 0


def test_api_lists_configured_servers_with_connection_status():
    config = AppConfig(
        api_token="secret-token",
        servers=[ServerConfig(name="dev", host="host", username="u", password="p")],
    )
    manager = CommandManager(config)
    manager.set_server_status("dev", "connected")
    client = TestClient(create_app(manager))

    response = client.get(
        "/api/servers",
        headers={"X-Remote-Token": "secret-token"},
    )

    assert response.status_code == 200
    assert response.json() == [{"name": "dev", "status": "connected"}]


def test_command_lifecycle_does_not_create_log_file(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "config.json"
    monkeypatch.setenv("REMOTE_TOOL_CONFIG_PATH", str(config_path))
    config = AppConfig(
        api_token="secret-token",
        servers=[ServerConfig(name="dev", host="host", username="u", password="p")],
    )
    manager = CommandManager(config)

    command = manager.submit("dev", "echo hi")
    manager.mark_running(command.id)
    manager.complete(command.id, stdout="hi\n", stderr="", exit_code=0, duration_ms=10)
    manager.fail(command.id, "failed", "sample")

    assert not (tmp_path / "logs").exists()


def test_client_accepts_unquoted_multi_word_command_with_server():
    args = parse_args(["--server", "dev", "conda", "env", "list"])

    assert args.server == "dev"
    assert args.cmd == "conda env list"


def test_client_accepts_options_before_multi_word_command():
    args = parse_args(["--server", "dev", "--timeout", "5", "--wait", "20", "conda", "env", "list"])

    assert args.server == "dev"
    assert args.timeout == 5
    assert args.wait == 20
    assert args.cmd == "conda env list"


def test_remote_output_cleanup_removes_echo_prompt_and_ansi():
    raw = "\x1b[?2004h(base) user@host:~$ conda env list\r\n\x1b[?2004l\r\nbase * /opt/conda\r\n"

    cleaned = RemoteShell._clean_output(raw, "conda env list", "unused")

    assert cleaned == "base * /opt/conda\n"


def test_gui_saves_api_port_and_restarts_api(tmp_path: Path, monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    path = tmp_path / "config.json"
    restart_count = 0

    def fake_start(self):
        return None

    def fake_restart(self):
        nonlocal restart_count
        restart_count += 1

    monkeypatch.setattr(app_module, "get_config_path", lambda: path)
    monkeypatch.setattr(app_module.MainWindow, "_start_api_server", fake_start)
    monkeypatch.setattr(app_module.MainWindow, "_restart_api_server", fake_restart)

    config = AppConfig(api_token="secret-token", api_port=8765)
    window = app_module.MainWindow(config, CommandManager(config))
    window.api_port_input.setValue(9876)
    window.save_config()
    window.close()

    saved = load_config(path)
    assert saved.api_port == 9876
    assert restart_count == 1


def test_main_window_does_not_show_bottom_plain_password_warning(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])

    def fake_start(self):
        return None

    monkeypatch.setattr(app_module.MainWindow, "_start_api_server", fake_start)

    config = AppConfig(api_token="secret-token", api_port=8765)
    window = app_module.MainWindow(config, CommandManager(config))
    labels = [label.text() for label in window.findChildren(app_module.QLabel)]
    window.close()

    assert "密码按当前配置明文保存" not in "\n".join(labels)


def test_uvicorn_config_does_not_require_console_stream(monkeypatch):
    monkeypatch.setattr("sys.stderr", None)
    config = AppConfig(api_token="secret-token", api_port=9876)

    uvicorn_config = app_module.build_uvicorn_config(FastAPI(), config)

    assert uvicorn_config.log_config is None


def test_theme_stylesheets_have_distinct_light_and_dark_palettes():
    light = app_module.build_theme_stylesheet(False)
    dark = app_module.build_theme_stylesheet(True)

    assert light != dark
    assert "#f6f8f9" in light
    assert "#111312" in dark
    assert "QLabel {" in dark
    assert "color: #edf2ee" in dark
    assert "QTableWidget::item:selected" in light
    assert "QTableWidget::item:selected" in dark


def test_packaging_uses_custom_app_icon():
    spec = Path("RemoteTool.spec").read_text(encoding="utf-8")

    assert Path("assets/remote-tool.ico").exists()
    assert 'icon=str(project_root / "assets" / "remote-tool.ico")' in spec


def test_skill_uses_config_path_env_and_not_fixed_port():
    skill = Path("skills/remote-linux-http/SKILL.md").read_text(encoding="utf-8")

    assert "REMOTE_TOOL_CONFIG_PATH" in skill
    assert "api_port" in skill
    assert "8765" not in skill
