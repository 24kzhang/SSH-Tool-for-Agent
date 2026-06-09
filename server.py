from __future__ import annotations

import threading
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Callable

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from config import AppConfig


@dataclass
class CommandRecord:
    id: str
    server: str
    cmd: str
    status: str
    timeout: int
    created_at: float
    source: str = "codex"
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    duration_ms: int | None = None
    error: str = ""
    danger_hint: str = ""


class CommandRequest(BaseModel):
    server: str = Field(min_length=1)
    cmd: str = Field(min_length=1)
    timeout: int | None = Field(default=None, ge=1, le=86400)
    source: str = "codex"


class CommandManager:
    def __init__(self, config: AppConfig):
        self.config = config
        self._commands: dict[str, CommandRecord] = {}
        self._server_status: dict[str, str] = {}
        self._lock = threading.RLock()
        self.on_command: Callable[[CommandRecord], None] | None = None

    def submit(self, server: str, cmd: str, timeout: int | None = None, source: str = "codex") -> CommandRecord:
        server_name = server.strip()
        if server_name not in self.server_names():
            raise KeyError(server_name)
        record = CommandRecord(
            id=str(uuid.uuid4()),
            server=server_name,
            cmd=cmd,
            status="queued",
            timeout=timeout or self.config.command_timeout,
            created_at=time.time(),
            source=source,
            danger_hint=danger_hint(cmd),
        )
        with self._lock:
            self._commands[record.id] = record
        if self.on_command:
            self.on_command(record)
        return record

    def server_names(self) -> list[str]:
        return [server.name for server in self.config.servers]

    def set_server_status(self, name: str, status: str) -> None:
        with self._lock:
            self._server_status[name] = status

    def server_statuses(self) -> list[dict[str, str]]:
        with self._lock:
            return [
                {"name": server.name, "status": self._server_status.get(server.name, "disconnected")}
                for server in self.config.servers
            ]

    def list(self) -> list[CommandRecord]:
        with self._lock:
            return sorted(self._commands.values(), key=lambda item: item.created_at, reverse=True)

    def get(self, command_id: str) -> CommandRecord | None:
        with self._lock:
            return self._commands.get(command_id)

    def mark_running(self, command_id: str) -> None:
        self._set(command_id, status="running")

    def complete(
        self,
        command_id: str,
        stdout: str,
        stderr: str,
        exit_code: int,
        duration_ms: int,
    ) -> None:
        self._set(
            command_id,
            status="completed",
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_ms=duration_ms,
        )

    def fail(self, command_id: str, status: str, error: str, duration_ms: int | None = None) -> None:
        self._set(command_id, status=status, error=error, stderr=error, duration_ms=duration_ms)

    def reject(self, command_id: str) -> None:
        self.fail(command_id, "rejected", "用户在 GUI 中拒绝执行")

    def _set(self, command_id: str, **changes) -> None:
        with self._lock:
            record = self._commands.get(command_id)
            if not record:
                return
            for key, value in changes.items():
                setattr(record, key, value)


def danger_hint(cmd: str) -> str:
    lowered = cmd.lower()
    patterns = [
        ("rm -rf /", "包含 rm -rf /，请确认目标路径"),
        ("mkfs", "包含 mkfs，可能格式化磁盘"),
        ("shutdown", "包含 shutdown，可能关闭服务器"),
        ("reboot", "包含 reboot，可能重启服务器"),
        (":(){", "疑似 fork bomb"),
    ]
    for pattern, message in patterns:
        if pattern in lowered:
            return message
    return ""


def command_to_dict(record: CommandRecord) -> dict:
    data = asdict(record)
    data["created_text"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created_at))
    return data


def create_app(manager: CommandManager) -> FastAPI:
    app = FastAPI(title="Remote Tool Local API")

    def require_token(x_remote_token: str | None = Header(default=None)) -> None:
        if not manager.config.api_token or x_remote_token != manager.config.api_token:
            raise HTTPException(status_code=401, detail="invalid token")

    @app.get("/api/health")
    def health():
        return {
            "ok": True,
            "api_host": manager.config.api_host,
            "api_port": manager.config.api_port,
            "servers": manager.server_statuses(),
        }

    @app.get("/api/servers", dependencies=[Depends(require_token)])
    def list_servers():
        return manager.server_statuses()

    @app.post("/api/commands", dependencies=[Depends(require_token)])
    def submit_command(request: CommandRequest):
        try:
            record = manager.submit(request.server, request.cmd, request.timeout, request.source)
        except KeyError:
            raise HTTPException(status_code=404, detail="server not found")
        return command_to_dict(record)

    @app.get("/api/commands/{command_id}", dependencies=[Depends(require_token)])
    def get_command(command_id: str):
        record = manager.get(command_id)
        if not record:
            raise HTTPException(status_code=404, detail="command not found")
        return command_to_dict(record)

    return app
