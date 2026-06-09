from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from paths import get_config_path, get_encryption_key_path, get_legacy_project_config_path, is_frozen_app

CONFIG_PATH = get_config_path()
ENCRYPTION_PREFIX = "enc:v1:"


@dataclass
class ServerConfig:
    name: str
    host: str = ""
    port: int = 22
    username: str = ""
    password: str = ""


@dataclass
class AppConfig:
    api_host: str = "127.0.0.1"
    api_port: int = 8765
    api_token: str = ""
    command_timeout: int = 120
    servers: list[ServerConfig] = field(default_factory=list)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def load_config(path: Path | None = None) -> AppConfig:
    config_path = path or get_config_path()
    if not config_path.exists():
        legacy_path = get_legacy_project_config_path()
        if path is None and not is_frozen_app() and legacy_path.exists() and legacy_path != config_path:
            config = _config_from_dict(_read_config_json(legacy_path), config_path)
            if not config.api_token:
                config.api_token = new_token()
            save_config(config_path, config)
            return config
        config = AppConfig(api_token=new_token())
        save_config(config_path, config)
        return config

    data = _read_config_json(config_path)
    config = _config_from_dict(data, config_path)
    needs_rewrite = _needs_encryption_migration(data)
    if not config.api_token:
        config.api_token = new_token()
        needs_rewrite = True
    if needs_rewrite:
        save_config(config_path, config)
    return config


def save_config(path: Path, config: AppConfig) -> None:
    errors = validate_servers(config.servers)
    if errors:
        raise ValueError("；".join(errors))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_config_to_dict(path, config), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _read_config_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _config_to_dict(path: Path, config: AppConfig) -> dict:
    return {
        "api_host": config.api_host,
        "api_port": config.api_port,
        "api_token": config.api_token,
        "command_timeout": config.command_timeout,
        "servers": [_server_to_encrypted_dict(path, server) for server in config.servers],
    }


def _config_from_dict(data: dict, path: Path) -> AppConfig:
    servers = [_server_from_dict(item, path) for item in data.get("servers", []) if isinstance(item, dict)]
    if not servers and (data.get("host") or data.get("username") or data.get("password")):
        servers = [
            ServerConfig(
                name="default",
                host=str(data.get("host", "")),
                port=int(data.get("port") or 22),
                username=str(data.get("username", "")),
                password=str(data.get("password", "")),
            )
        ]
    return AppConfig(
        api_host=str(data.get("api_host") or "127.0.0.1"),
        api_port=int(data.get("api_port") or 8765),
        api_token=str(data.get("api_token") or ""),
        command_timeout=int(data.get("command_timeout") or 120),
        servers=servers,
    )


def _server_from_dict(data: dict, path: Path) -> ServerConfig:
    encrypted = str(data.get("data") or "")
    if encrypted.startswith(ENCRYPTION_PREFIX):
        payload = _decrypt_payload(path, encrypted)
        return ServerConfig(
            name=str(data.get("name") or payload.get("name") or "").strip(),
            host=str(payload.get("host") or "").strip(),
            port=int(payload.get("port") or 22),
            username=str(payload.get("username") or "").strip(),
            password=str(payload.get("password") or ""),
        )
    return ServerConfig(
        name=str(data.get("name") or "").strip(),
        host=str(data.get("host") or "").strip(),
        port=int(data.get("port") or 22),
        username=str(data.get("username") or "").strip(),
        password=str(data.get("password") or ""),
    )


def _server_to_encrypted_dict(path: Path, server: ServerConfig) -> dict:
    payload = {
        "host": server.host,
        "port": server.port,
        "username": server.username,
        "password": server.password,
    }
    return {
        "name": server.name,
        "data": _encrypt_payload(path, payload),
    }


def _encrypt_payload(path: Path, payload: dict) -> str:
    token = _fernet(path).encrypt(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")
    return f"{ENCRYPTION_PREFIX}{token}"


def _decrypt_payload(path: Path, value: str) -> dict:
    token = value.removeprefix(ENCRYPTION_PREFIX)
    try:
        raw = _fernet(path).decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("无法解密服务器配置，请确认 config.key 与 config.json 匹配") from exc
    return json.loads(raw)


def _fernet(path: Path) -> Fernet:
    return Fernet(_load_or_create_key(path))


def _load_or_create_key(path: Path) -> bytes:
    key_path = get_encryption_key_path(path)
    if key_path.exists():
        return key_path.read_text(encoding="ascii").strip().encode("ascii")
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    key_path.write_text(key.decode("ascii"), encoding="ascii")
    return key


def _needs_encryption_migration(data: dict) -> bool:
    if data.get("host") or data.get("username") or data.get("password"):
        return True
    for item in data.get("servers", []):
        if not isinstance(item, dict):
            continue
        encrypted = str(item.get("data") or "")
        if not encrypted.startswith(ENCRYPTION_PREFIX):
            return True
        for key in ("host", "port", "username", "password"):
            if key in item:
                return True
    return False


def validate_servers(servers: list[ServerConfig]) -> list[str]:
    errors: list[str] = []
    if len(servers) > 6:
        errors.append("最多保存 6 个服务器")
    names = [server.name.strip() for server in servers]
    if any(not name for name in names):
        errors.append("服务器名称不能为空")
    normalized = [name.casefold() for name in names]
    if len(normalized) != len(set(normalized)):
        errors.append("服务器名称不能重复")
    for server in servers:
        if server.port < 1 or server.port > 65535:
            errors.append(f"服务器 {server.name} 的端口无效")
    return errors


def find_server(config: AppConfig, name: str) -> ServerConfig | None:
    wanted = name.strip().casefold()
    for server in config.servers:
        if server.name.casefold() == wanted:
            return server
    return None


def upsert_server(config: AppConfig, server: ServerConfig, old_name: str | None = None) -> None:
    target = old_name.strip().casefold() if old_name else server.name.strip().casefold()
    for index, item in enumerate(config.servers):
        if item.name.casefold() == target:
            config.servers[index] = server
            break
    else:
        config.servers.append(server)


def delete_server(config: AppConfig, name: str) -> None:
    wanted = name.strip().casefold()
    config.servers = [server for server in config.servers if server.name.casefold() != wanted]
