from __future__ import annotations

import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import uvicorn
from PySide6.QtCore import QObject, Qt, Signal, Slot, QTimer
from PySide6.QtGui import QIcon, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config import (
    AppConfig,
    ServerConfig,
    delete_server,
    find_server,
    load_config,
    save_config,
    upsert_server,
    validate_servers,
)
from paths import get_config_path
from remote import RemoteShell
from server import CommandManager, CommandRecord, create_app


class Bridge(QObject):
    command_added = Signal(str)
    command_changed = Signal(str)
    server_changed = Signal(str)
    message = Signal(str)


def resource_path(relative_path: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative_path


def app_icon_path() -> Path:
    return resource_path("assets/remote-tool.ico")


def prefers_dark_mode(app: QApplication | None = None) -> bool:
    current_app = app or QApplication.instance()
    if not current_app:
        return False
    hints = current_app.styleHints()
    color_scheme = getattr(hints, "colorScheme", None)
    if callable(color_scheme):
        scheme = color_scheme()
        dark_value = getattr(Qt.ColorScheme, "Dark", None)
        light_value = getattr(Qt.ColorScheme, "Light", None)
        if scheme == dark_value:
            return True
        if scheme == light_value:
            return False
    return current_app.palette().color(QPalette.Window).lightness() < 128


def build_theme_stylesheet(dark: bool) -> str:
    if dark:
        colors = {
            "root": "#111312",
            "panel": "#191d1b",
            "panel2": "#202621",
            "line": "#303832",
            "lineStrong": "#465348",
            "text": "#edf2ee",
            "textSoft": "#aeb9b2",
            "heading": "#f7faf6",
            "field": "#121614",
            "fieldLine": "#3d4942",
            "primary": "#3aa889",
            "primaryHover": "#47b996",
            "primaryText": "#07120f",
            "secondary": "#28312c",
            "secondaryHover": "#334039",
            "danger": "#b85f55",
            "dangerHover": "#ca7467",
            "statusBg": "#172b24",
            "statusText": "#8fe1c2",
            "statusLine": "#285c4c",
            "header": "#232a25",
            "selected": "#264a40",
            "selectedText": "#f2faf6",
        }
    else:
        colors = {
            "root": "#f6f8f9",
            "panel": "#ffffff",
            "panel2": "#edf3f1",
            "line": "#d7dfdc",
            "lineStrong": "#bdc9c5",
            "text": "#24302b",
            "textSoft": "#66736e",
            "heading": "#15221d",
            "field": "#ffffff",
            "fieldLine": "#c7d2ce",
            "primary": "#1f7a68",
            "primaryHover": "#258d78",
            "primaryText": "#ffffff",
            "secondary": "#e7eeeb",
            "secondaryHover": "#dce6e2",
            "danger": "#b25a4c",
            "dangerHover": "#c76a5b",
            "statusBg": "#e5f4ef",
            "statusText": "#17624f",
            "statusLine": "#b9dacf",
            "header": "#e8efec",
            "selected": "#cfe7de",
            "selectedText": "#10241d",
        }
    return f"""
        QWidget#root, QDialog {{
            background: {colors["root"]}; color: {colors["text"]}; font-size: 13px;
        }}
        QLabel {{ color: {colors["text"]}; }}
        QLabel#title {{ font-size: 26px; font-weight: 700; color: {colors["heading"]}; }}
        QLabel#subtitle {{ color: {colors["textSoft"]}; font-size: 13px; }}
        QLabel#sectionTitle {{ font-size: 15px; font-weight: 700; color: {colors["heading"]}; padding: 4px 0; }}
        QLabel#statusPill {{
            background: {colors["statusBg"]}; color: {colors["statusText"]}; border: 1px solid {colors["statusLine"]};
            border-radius: 8px; padding: 7px 12px; font-weight: 600;
        }}
        QLabel#muted {{ color: {colors["textSoft"]}; }}
        QFrame#panel {{
            background: {colors["panel"]}; border: 1px solid {colors["line"]}; border-radius: 8px;
        }}
        QLineEdit, QSpinBox, QPlainTextEdit {{
            background: {colors["field"]}; color: {colors["text"]}; border: 1px solid {colors["fieldLine"]};
            border-radius: 6px; padding: 6px; selection-background-color: {colors["primary"]};
            selection-color: {colors["primaryText"]};
        }}
        QSpinBox::up-button, QSpinBox::down-button {{
            background: {colors["panel2"]}; border: 0; width: 16px;
        }}
        QPushButton {{
            background: {colors["secondary"]}; color: {colors["text"]}; border: 1px solid {colors["lineStrong"]};
            border-radius: 6px; padding: 8px 12px; font-weight: 600;
        }}
        QPushButton:hover {{ background: {colors["secondaryHover"]}; }}
        QPushButton#primaryButton {{
            background: {colors["primary"]}; color: {colors["primaryText"]}; border: 1px solid {colors["primary"]};
        }}
        QPushButton#primaryButton:hover {{ background: {colors["primaryHover"]}; }}
        QPushButton#dangerButton {{
            background: transparent; color: {colors["danger"]}; border: 1px solid {colors["danger"]};
        }}
        QPushButton#dangerButton:hover {{ background: {colors["dangerHover"]}; color: #ffffff; }}
        QPushButton:disabled {{
            background: {colors["panel2"]}; color: {colors["textSoft"]}; border: 1px solid {colors["line"]};
        }}
        QTableWidget {{
            background: {colors["panel"]}; color: {colors["text"]}; border: 1px solid {colors["line"]};
            border-radius: 6px; gridline-color: {colors["line"]}; alternate-background-color: {colors["panel2"]};
        }}
        QHeaderView::section {{
            background: {colors["header"]}; color: {colors["heading"]}; border: 0; padding: 7px;
            font-weight: 700;
        }}
        QTableWidget::item {{ padding: 6px; }}
        QTableWidget::item:selected {{ background: {colors["selected"]}; color: {colors["selectedText"]}; }}
        QSplitter::handle {{ background: {colors["line"]}; }}
    """


class ServerDialog(QDialog):
    def __init__(self, existing_names: list[str], server: ServerConfig | None = None, parent=None):
        super().__init__(parent)
        self.existing_names = [name.casefold() for name in existing_names]
        self.old_name = server.name if server else ""
        self.setWindowTitle("服务器连接信息")
        self.setModal(True)
        self.resize(420, 260)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_input = QLineEdit(server.name if server else "")
        self.host_input = QLineEdit(server.host if server else "")
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(server.port if server else 22)
        self.user_input = QLineEdit(server.username if server else "")
        self.password_input = QLineEdit(server.password if server else "")
        self.password_input.setEchoMode(QLineEdit.Password)

        form.addRow("服务器名称", self.name_input)
        form.addRow("IP/主机", self.host_input)
        form.addRow("SSH端口", self.port_input)
        form.addRow("账号", self.user_input)
        form.addRow("密码", self.password_input)
        layout.addLayout(form)

        note = QLabel("保存后可在主界面快速连接。")
        note.setWordWrap(True)
        note.setObjectName("muted")
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:
        server = self.server_config()
        if not server.name:
            QMessageBox.warning(self, "名称不能为空", "请输入服务器名称。")
            return
        if server.name.casefold() != self.old_name.casefold() and server.name.casefold() in self.existing_names:
            QMessageBox.warning(self, "名称重复", "服务器名称不能重复。")
            return
        if not server.host:
            QMessageBox.warning(self, "主机不能为空", "请输入服务器 IP 或主机名。")
            return
        if not server.username:
            QMessageBox.warning(self, "账号不能为空", "请输入登录账号。")
            return
        super().accept()

    def server_config(self) -> ServerConfig:
        return ServerConfig(
            name=self.name_input.text().strip(),
            host=self.host_input.text().strip(),
            port=self.port_input.value(),
            username=self.user_input.text().strip(),
            password=self.password_input.text(),
        )


def build_uvicorn_config(api_app, config: AppConfig) -> uvicorn.Config:
    return uvicorn.Config(
        api_app,
        host=config.api_host,
        port=config.api_port,
        log_level="warning",
        access_log=False,
        log_config=None,
    )


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig, manager: CommandManager):
        super().__init__()
        self.config = config
        self.manager = manager
        self.bridge = Bridge()
        self.executor = ThreadPoolExecutor(max_workers=8)
        self.sessions: dict[str, RemoteShell] = {}
        self.session_lock = threading.RLock()
        self.health_check_running = False
        self.command_rows: dict[str, int] = {}
        self.api_server: uvicorn.Server | None = None
        self.api_thread: threading.Thread | None = None

        self.setWindowTitle("Remote Tool - 多服务器 Linux 控制")
        icon_path = app_icon_path()
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1220, 780)
        self._build_ui()
        self._load_settings()
        self._wire()
        self._wire_theme_listener()
        self._refresh_servers()
        self.health_timer = QTimer(self)
        self.health_timer.setInterval(30000)
        self.health_timer.timeout.connect(self._schedule_health_check)
        self.health_timer.start()

        self.manager.on_command = lambda record: self.bridge.command_added.emit(record.id)
        self._start_api_server()
        self._set_status("本地 API 已启动")

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Remote Tool")
        title.setObjectName("title")
        subtitle = QLabel("多服务器 SSH 会话与本地 HTTP 指令网关")
        subtitle.setObjectName("subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch(1)
        self.status = QLabel()
        self.status.setObjectName("statusPill")
        header.addWidget(self.status)
        layout.addLayout(header)

        settings = QFrame()
        settings.setObjectName("panel")
        settings_layout = QHBoxLayout(settings)
        settings_layout.addWidget(QLabel("本地HTTP端口"))
        self.api_port_input = QSpinBox()
        self.api_port_input.setRange(1024, 65535)
        settings_layout.addWidget(self.api_port_input)
        settings_layout.addWidget(QLabel("默认超时(秒)"))
        self.timeout_input = QSpinBox()
        self.timeout_input.setRange(1, 86400)
        settings_layout.addWidget(self.timeout_input)
        settings_layout.addStretch(1)
        self.save_button = QPushButton("保存设置")
        self.save_button.setObjectName("primaryButton")
        settings_layout.addWidget(self.save_button)
        layout.addWidget(settings)

        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter, 1)

        left = QFrame()
        left.setObjectName("panel")
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self._section_label("服务器"))
        self.server_table = QTableWidget(0, 4)
        self.server_table.setHorizontalHeaderLabels(["名称", "主机", "SSH端口", "状态"])
        self.server_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.server_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.server_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.server_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.server_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.server_table.setEditTriggers(QTableWidget.NoEditTriggers)
        left_layout.addWidget(self.server_table, 1)

        server_buttons = QHBoxLayout()
        self.add_button = QPushButton("添加并连接")
        self.add_button.setObjectName("primaryButton")
        self.edit_button = QPushButton("编辑")
        self.delete_button = QPushButton("删除")
        self.delete_button.setObjectName("dangerButton")
        server_buttons.addWidget(self.add_button)
        server_buttons.addWidget(self.edit_button)
        server_buttons.addWidget(self.delete_button)
        left_layout.addLayout(server_buttons)

        connect_buttons = QHBoxLayout()
        self.connect_button = QPushButton("连接选中")
        self.connect_button.setObjectName("primaryButton")
        self.disconnect_button = QPushButton("断开选中")
        connect_buttons.addWidget(self.connect_button)
        connect_buttons.addWidget(self.disconnect_button)
        left_layout.addLayout(connect_buttons)
        splitter.addWidget(left)

        right = QFrame()
        right.setObjectName("panel")
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self._section_label("指令记录"))
        self.command_table = QTableWidget(0, 7)
        self.command_table.setHorizontalHeaderLabels(["时间", "服务器", "来源", "状态", "退出码", "耗时", "命令"])
        self.command_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        self.command_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.command_table.setEditTriggers(QTableWidget.NoEditTriggers)
        right_layout.addWidget(self.command_table, 2)
        right_layout.addWidget(self._section_label("运行结果"))
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        right_layout.addWidget(self.output, 1)
        splitter.addWidget(right)
        splitter.setSizes([380, 820])

        self.setCentralWidget(root)
        self._apply_style()

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionTitle")
        return label

    def _apply_style(self) -> None:
        stylesheet = build_theme_stylesheet(prefers_dark_mode())
        app = QApplication.instance()
        if app:
            app.setStyleSheet(stylesheet)
        self.setStyleSheet(stylesheet)

    def _wire_theme_listener(self) -> None:
        app = QApplication.instance()
        if not app:
            return
        signal = getattr(app.styleHints(), "colorSchemeChanged", None)
        if signal:
            signal.connect(lambda *_: self._apply_style())

    def _load_settings(self) -> None:
        self.api_port_input.setValue(self.config.api_port)
        self.timeout_input.setValue(self.config.command_timeout)

    def _wire(self) -> None:
        self.save_button.clicked.connect(self.save_config)
        self.add_button.clicked.connect(self.add_server)
        self.edit_button.clicked.connect(self.edit_server)
        self.delete_button.clicked.connect(self.delete_server)
        self.connect_button.clicked.connect(self.connect_selected_server)
        self.disconnect_button.clicked.connect(self.disconnect_selected_server)
        self.server_table.cellDoubleClicked.connect(lambda *_: self.connect_selected_server())
        self.command_table.itemSelectionChanged.connect(self.show_selected_output)
        self.bridge.command_added.connect(self.on_command_added)
        self.bridge.command_changed.connect(self.on_command_changed)
        self.bridge.server_changed.connect(self.on_server_changed)
        self.bridge.message.connect(self.append_message)

    def _start_api_server(self) -> None:
        config = build_uvicorn_config(create_app(self.manager), self.config)
        self.api_server = uvicorn.Server(config)
        self.api_thread = threading.Thread(target=self.api_server.run, name="remote-tool-api", daemon=True)
        self.api_thread.start()

    def _stop_api_server(self) -> None:
        if self.api_server:
            self.api_server.should_exit = True
        if self.api_thread and self.api_thread.is_alive():
            self.api_thread.join(timeout=3)
        self.api_server = None
        self.api_thread = None

    def _restart_api_server(self) -> None:
        self._stop_api_server()
        self._start_api_server()

    @Slot()
    def save_config(self) -> None:
        old_api_port = self.config.api_port
        self.config.api_port = self.api_port_input.value()
        self.config.command_timeout = self.timeout_input.value()
        try:
            save_config(get_config_path(), self.config)
        except ValueError as exc:
            QMessageBox.warning(self, "配置无效", str(exc))
            return
        if self.config.api_port != old_api_port:
            self._restart_api_server()
            self._set_status("设置已保存，API 端口已重启")
        else:
            self._set_status("设置已保存")

    @Slot()
    def add_server(self) -> None:
        if len(self.config.servers) >= 6:
            QMessageBox.warning(self, "数量已达上限", "最多保存 6 个服务器。")
            return
        dialog = ServerDialog([server.name for server in self.config.servers], parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        server = dialog.server_config()
        self._save_server(server)
        self.connect_server(server.name)

    @Slot()
    def edit_server(self) -> None:
        name = self._selected_server_name()
        if not name:
            return
        server = find_server(self.config, name)
        if not server:
            return
        dialog = ServerDialog([item.name for item in self.config.servers], server=server, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        updated = dialog.server_config()
        if updated.name.casefold() != server.name.casefold():
            self.disconnect_server(server.name)
        self._save_server(updated, old_name=server.name)

    @Slot()
    def delete_server(self) -> None:
        name = self._selected_server_name()
        if not name:
            return
        answer = QMessageBox.question(self, "删除服务器", f"确定删除服务器“{name}”的保存信息吗？")
        if answer != QMessageBox.Yes:
            return
        self.disconnect_server(name)
        delete_server(self.config, name)
        save_config(get_config_path(), self.config)
        self._refresh_servers()
        self._set_status(f"已删除服务器 {name}")

    def _save_server(self, server: ServerConfig, old_name: str | None = None) -> None:
        original = list(self.config.servers)
        upsert_server(self.config, server, old_name=old_name)
        errors = validate_servers(self.config.servers)
        if errors:
            self.config.servers = original
            QMessageBox.warning(self, "服务器配置无效", "；".join(errors))
            return
        save_config(get_config_path(), self.config)
        self.manager.config = self.config
        self._refresh_servers()
        self._set_status(f"已保存服务器 {server.name}")

    @Slot()
    def connect_selected_server(self) -> None:
        name = self._selected_server_name()
        if name:
            self.connect_server(name)

    def connect_server(self, name: str) -> None:
        server = find_server(self.config, name)
        if not server:
            QMessageBox.warning(self, "服务器不存在", f"未找到服务器 {name}。")
            return
        self.manager.set_server_status(server.name, "connecting")
        self._refresh_servers()
        self._set_status(f"正在连接 {server.name}...")
        self.executor.submit(self._connect_worker, server)

    def _connect_worker(self, server: ServerConfig) -> None:
        shell = RemoteShell()
        try:
            shell.connect(server.host, server.port, server.username, server.password)
            with self.session_lock:
                old = self.sessions.get(server.name)
                if old:
                    old.close()
                self.sessions[server.name] = shell
            self.manager.set_server_status(server.name, "connected")
            self.bridge.message.emit(f"服务器 {server.name} 已连接")
        except Exception as exc:
            shell.close()
            self.manager.set_server_status(server.name, "failed")
            self.bridge.message.emit(f"服务器 {server.name} 连接失败：{exc}")
        self.bridge.server_changed.emit(server.name)

    @Slot()
    def disconnect_selected_server(self) -> None:
        name = self._selected_server_name()
        if name:
            self.disconnect_server(name)

    def disconnect_server(self, name: str) -> None:
        with self.session_lock:
            shell = self.sessions.pop(name, None)
        if shell:
            shell.close()
        self.manager.set_server_status(name, "disconnected")
        self._refresh_servers()
        self._set_status(f"已断开 {name}")

    @Slot(str)
    def on_server_changed(self, name: str) -> None:
        self._refresh_servers()
        status = self.manager._server_status.get(name, "disconnected")
        self._set_status(f"{name}: {status}")

    def _refresh_servers(self) -> None:
        self.server_table.setRowCount(0)
        for server in self.config.servers:
            row = self.server_table.rowCount()
            self.server_table.insertRow(row)
            status = self.manager._server_status.get(server.name, "disconnected")
            values = [server.name, server.host, str(server.port), status]
            for col, value in enumerate(values):
                self.server_table.setItem(row, col, QTableWidgetItem(value))

    def _selected_server_name(self) -> str:
        selected = self.server_table.selectedItems()
        if not selected:
            return ""
        row = selected[0].row()
        item = self.server_table.item(row, 0)
        return item.text() if item else ""

    @Slot(str)
    def on_command_added(self, command_id: str) -> None:
        record = self.manager.get(command_id)
        if not record:
            return
        row = self.command_table.rowCount()
        self.command_table.insertRow(row)
        self.command_rows[command_id] = row
        self._render_command(record)
        self.execute_command(command_id)

    @Slot(str)
    def on_command_changed(self, command_id: str) -> None:
        record = self.manager.get(command_id)
        if record:
            self._render_command(record)
            self.show_selected_output()

    def _render_command(self, record: CommandRecord) -> None:
        row = self.command_rows.get(record.id)
        if row is None:
            return
        values = [
            self._time_text(record.created_at),
            record.server,
            record.source,
            record.status,
            "" if record.exit_code is None else str(record.exit_code),
            "" if record.duration_ms is None else f"{record.duration_ms}ms",
            record.cmd,
        ]
        for col, value in enumerate(values):
            self.command_table.setItem(row, col, QTableWidgetItem(value))

    @staticmethod
    def _time_text(timestamp: float) -> str:
        import time

        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))

    def execute_command(self, command_id: str) -> None:
        record = self.manager.get(command_id)
        if not record or record.status != "queued":
            return
        self.manager.mark_running(command_id)
        self.bridge.command_changed.emit(command_id)
        self.executor.submit(self._execute_worker, command_id)

    def _ensure_command_shell(self, server_name: str) -> RemoteShell:
        with self.session_lock:
            shell = self.sessions.get(server_name)
        if shell and shell.probe():
            self.manager.set_server_status(server_name, "connected")
            return shell

        if shell:
            shell.close()
            with self.session_lock:
                if self.sessions.get(server_name) is shell:
                    self.sessions.pop(server_name, None)

        server = find_server(self.config, server_name)
        if not server:
            raise RuntimeError(f"服务器 {server_name} 不存在")

        self.manager.set_server_status(server_name, "reconnecting")
        self.bridge.server_changed.emit(server_name)
        self.bridge.message.emit(f"服务器 {server_name} 连接已失效，正在自动重连...")

        new_shell = RemoteShell()
        try:
            new_shell.connect(server.host, server.port, server.username, server.password)
        except Exception:
            new_shell.close()
            self.manager.set_server_status(server_name, "failed")
            self.bridge.server_changed.emit(server_name)
            raise

        with self.session_lock:
            self.sessions[server_name] = new_shell
        self.manager.set_server_status(server_name, "connected")
        self.bridge.server_changed.emit(server_name)
        self.bridge.message.emit(f"服务器 {server_name} 已自动重连")
        return new_shell

    def _execute_worker(self, command_id: str) -> None:
        record = self.manager.get(command_id)
        if not record:
            return
        try:
            shell = self._ensure_command_shell(record.server)

            def heartbeat(duration_ms: int, stdout: str) -> None:
                self.manager.heartbeat(command_id, duration_ms, stdout)
                self.bridge.command_changed.emit(command_id)

            stdout, stderr, exit_code, duration_ms = shell.execute(record.cmd, record.timeout, heartbeat)
            self.manager.complete(command_id, stdout, stderr, exit_code, duration_ms)
        except TimeoutError as exc:
            self.manager.fail(command_id, "timeout", str(exc))
        except Exception as exc:
            self.manager.fail(command_id, "failed", str(exc))
        self.bridge.command_changed.emit(command_id)

    @Slot()
    def _schedule_health_check(self) -> None:
        if self.health_check_running:
            return
        self.health_check_running = True
        self.executor.submit(self._health_check_worker)

    def _health_check_worker(self) -> None:
        try:
            with self.session_lock:
                sessions = list(self.sessions.items())
            for name, shell in sessions:
                if shell.probe(timeout=3):
                    self.manager.set_server_status(name, "connected")
                    self.bridge.server_changed.emit(name)
                    continue
                shell.close()
                with self.session_lock:
                    if self.sessions.get(name) is shell:
                        self.sessions.pop(name, None)
                self.manager.set_server_status(name, "disconnected")
                self.bridge.server_changed.emit(name)
                self.bridge.message.emit(f"服务器 {name} 连接已失效")
        finally:
            self.health_check_running = False

    @Slot()
    def show_selected_output(self) -> None:
        record = self._selected_command()
        if not record:
            return
        text = (
            f"服务器：{record.server}\n"
            f"命令：{record.cmd}\n"
            f"状态：{record.status}\n"
            f"退出码：{record.exit_code}\n"
            f"耗时：{record.duration_ms}ms\n"
            f"风险提示：{record.danger_hint or '无'}\n\n"
            f"--- stdout ---\n{record.stdout}\n"
            f"--- stderr/error ---\n{record.stderr or record.error}\n"
        )
        self.output.setPlainText(text)

    def _selected_command(self) -> CommandRecord | None:
        selected = self.command_table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        for command_id, known_row in self.command_rows.items():
            if known_row == row:
                return self.manager.get(command_id)
        return None

    @Slot(str)
    def append_message(self, message: str) -> None:
        self.output.appendPlainText(message)

    def _set_status(self, message: str) -> None:
        self.status.setText(f"{message} | API http://{self.config.api_host}:{self.config.api_port}")

    def closeEvent(self, event) -> None:
        self.health_timer.stop()
        with self.session_lock:
            sessions = list(self.sessions.values())
            self.sessions.clear()
        for shell in sessions:
            shell.close()
        self._stop_api_server()
        self.executor.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)


def main() -> int:
    config = load_config()
    manager = CommandManager(config)
    app = QApplication(sys.argv)
    icon_path = app_icon_path()
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    window = MainWindow(config, manager)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
