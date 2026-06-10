from __future__ import annotations

import argparse
import sys
import time

import requests

from config import load_config


FINAL_STATES = {"completed", "failed", "timeout", "rejected"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="向本地 remote_tool 提交 Linux 命令")
    parser.add_argument("--server", required=True, help="目标服务器名称，必须与 GUI 中保存的名称一致")
    parser.add_argument("--timeout", type=int, default=None, help="远程命令超时时间，单位秒")
    parser.add_argument("--wait", type=int, default=1800, help="等待命令完成的最长时间，单位秒")
    parser.add_argument("cmd", nargs=argparse.REMAINDER, help="要在远程 Linux shell 中执行的命令")
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.cmd:
        parser.error("缺少要执行的 Linux 命令")
    args.cmd = " ".join(args.cmd).strip()
    if not args.cmd:
        parser.error("缺少要执行的 Linux 命令")
    return args


def main() -> int:
    args = parse_args()

    config = load_config()
    base_url = f"http://{config.api_host}:{config.api_port}"
    headers = {"X-Remote-Token": config.api_token}

    try:
        response = requests.post(
            f"{base_url}/api/commands",
            headers=headers,
            json={"server": args.server, "cmd": args.cmd, "timeout": args.timeout, "source": "codex"},
            timeout=10,
        )
        response.raise_for_status()
        command = response.json()
    except requests.RequestException as exc:
        print(f"提交命令失败：{exc}", file=sys.stderr)
        return 2

    command_id = command["id"]
    started = time.monotonic()
    last_progress = 0.0
    while True:
        if time.monotonic() - started > args.wait:
            print(f"等待命令超时：{command_id}", file=sys.stderr)
            return 4
        try:
            response = requests.get(f"{base_url}/api/commands/{command_id}", headers=headers, timeout=10)
            response.raise_for_status()
            command = response.json()
        except requests.RequestException as exc:
            print(f"查询命令失败：{exc}", file=sys.stderr)
            return 2

        status = command["status"]
        if status in FINAL_STATES:
            stdout = command.get("stdout") or ""
            stderr = command.get("stderr") or command.get("error") or ""
            if stdout:
                print(stdout, end="")
            if stderr:
                print(stderr, end="" if stderr.endswith("\n") else "\n", file=sys.stderr)
            if status == "completed":
                return int(command.get("exit_code") or 0)
            if status == "rejected":
                return 3
            return 4
        now = time.monotonic()
        if now - last_progress >= 10:
            elapsed = int(now - started)
            message = command.get("message") or f"命令仍在执行，已等待 {elapsed} 秒"
            updated = command.get("updated_text") or ""
            suffix = f"，最近更新：{updated}" if updated else ""
            print(f"[remote-tool] {status}: {message}{suffix}", file=sys.stderr, flush=True)
            last_progress = now
        time.sleep(0.3)


if __name__ == "__main__":
    raise SystemExit(main())
