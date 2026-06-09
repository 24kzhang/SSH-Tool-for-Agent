from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Mapping


APP_DIR_NAME = "RemoteTool"
CONFIG_ENV = "REMOTE_TOOL_CONFIG_PATH"


def get_config_path(env: Mapping[str, str] | None = None) -> Path:
    current_env = os.environ if env is None else env
    override = current_env.get(CONFIG_ENV)
    if override:
        return Path(override).expanduser()
    return get_user_config_dir(current_env) / "config.json"


def get_user_config_dir(env: Mapping[str, str] | None = None) -> Path:
    current_env = os.environ if env is None else env
    if sys.platform.startswith("win"):
        root = current_env.get("APPDATA")
        if root:
            return Path(root) / APP_DIR_NAME
        return Path.home() / "AppData" / "Roaming" / APP_DIR_NAME
    root = current_env.get("XDG_CONFIG_HOME")
    if root:
        return Path(root) / "remote-tool"
    return Path.home() / ".config" / "remote-tool"


def get_encryption_key_path(config_path: Path | None = None) -> Path:
    path = config_path or get_config_path()
    return path.parent / "config.key"


def get_legacy_project_config_path() -> Path:
    return Path(__file__).with_name("config.json")


def is_frozen_app() -> bool:
    return bool(getattr(sys, "frozen", False))
