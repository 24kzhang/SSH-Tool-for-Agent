from __future__ import annotations

import re
import socket
import threading
import time
import uuid

import paramiko


class RemoteExecutionError(RuntimeError):
    pass


class RemoteShell:
    HEARTBEAT_INTERVAL = 5

    def __init__(self):
        self.client: paramiko.SSHClient | None = None
        self.channel: paramiko.Channel | None = None
        self._lock = threading.Lock()

    @property
    def connected(self) -> bool:
        transport = self.client.get_transport() if self.client else None
        return bool(transport and transport.is_active() and self.channel and not self.channel.closed)

    def connect(self, host: str, port: int, username: str, password: str, timeout: int = 15) -> None:
        self.close()
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=host,
            port=port,
            username=username,
            password=password,
            timeout=timeout,
            banner_timeout=timeout,
            auth_timeout=timeout,
            look_for_keys=False,
            allow_agent=False,
        )
        transport = client.get_transport()
        if transport:
            transport.set_keepalive(30)
        channel = client.invoke_shell(width=160, height=48)
        channel.settimeout(0.2)
        self.client = client
        self.channel = channel
        time.sleep(0.3)
        self._drain()

    def close(self) -> None:
        if self.channel:
            self.channel.close()
        if self.client:
            self.client.close()
        self.channel = None
        self.client = None

    def probe(self, timeout: int = 5) -> bool:
        if not self.connected or not self.channel:
            return False
        marker = f"__REMOTE_TOOL_PROBE_{uuid.uuid4().hex}"
        started = time.monotonic()
        output = ""
        if not self._lock.acquire(timeout=0.1):
            return True
        try:
            self.channel.send(f"printf '\\n{marker}\\n'\n")
            while time.monotonic() - started <= timeout:
                if self.channel.recv_ready():
                    output += self.channel.recv(65535).decode("utf-8", errors="replace")
                    if marker in output:
                        return True
                else:
                    time.sleep(0.05)
        except (OSError, EOFError, socket.timeout):
            return False
        finally:
            self._lock.release()
        return False

    def execute(self, cmd: str, timeout: int = 120, on_heartbeat=None) -> tuple[str, str, int, int]:
        if not self.connected or not self.channel:
            raise RemoteExecutionError("SSH 未连接")

        marker = f"__REMOTE_TOOL_DONE_{uuid.uuid4().hex}"
        wrapped = f"{cmd}\n_ec=$?; printf '\\n{marker}:%s\\n' \"$_ec\"\n"
        pattern = re.compile(rf"{re.escape(marker)}:(\d+)")
        started = time.monotonic()
        last_heartbeat = started
        output = ""

        with self._lock:
            try:
                self.channel.send(wrapped)
            except (OSError, EOFError) as exc:
                raise RemoteExecutionError(f"SSH 连接已断开：{exc}") from exc
            while True:
                now = time.monotonic()
                if now - started > timeout:
                    raise TimeoutError(f"命令执行超过 {timeout} 秒")
                if on_heartbeat and now - last_heartbeat >= self.HEARTBEAT_INTERVAL:
                    on_heartbeat(int((now - started) * 1000), self._clean_output(output, cmd, marker))
                    last_heartbeat = now
                try:
                    if self.channel.recv_ready():
                        chunk = self.channel.recv(65535).decode("utf-8", errors="replace")
                        output += chunk
                        match = pattern.search(output)
                        if match:
                            exit_code = int(match.group(1))
                            cleaned = output[: match.start()]
                            duration_ms = int((time.monotonic() - started) * 1000)
                            return self._clean_output(cleaned, cmd, marker), "", exit_code, duration_ms
                    else:
                        time.sleep(0.05)
                except socket.timeout:
                    time.sleep(0.05)
                except (OSError, EOFError) as exc:
                    raise RemoteExecutionError(f"SSH 连接已断开：{exc}") from exc

    def _drain(self) -> None:
        if not self.channel:
            return
        try:
            while self.channel.recv_ready():
                self.channel.recv(65535)
        except socket.timeout:
            pass

    @staticmethod
    def _clean_output(output: str, cmd: str, marker: str) -> str:
        ansi_pattern = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
        output = ansi_pattern.sub("", output)
        lines = output.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        cleaned: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped == cmd.strip() or stripped.endswith(cmd.strip()):
                continue
            if stripped.startswith("_ec=$?; printf"):
                continue
            if marker in stripped:
                continue
            cleaned.append(line)
        text = "\n".join(cleaned).strip("\n")
        return text + ("\n" if text else "")
