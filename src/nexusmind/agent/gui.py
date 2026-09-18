from __future__ import annotations

import sys
import webbrowser
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSystemTrayIcon,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from nexusmind.agent.autostart import set_autostart
from nexusmind.agent.brand import app_icon_path
from nexusmind.agent.configuration import AgentConfig, AgentConfigStore
from nexusmind.agent.runtime import AgentStatus, AgentSupervisor


class StatusBridge(QObject):
    changed = Signal(object)


class AgentWindow(QMainWindow):
    def __init__(self, store: AgentConfigStore):
        super().__init__()
        self.store = store
        self.bridge = StatusBridge()
        self.bridge.changed.connect(self._render_status)
        self.supervisor = AgentSupervisor(store, self.bridge.changed.emit)
        self._quitting = False

        self.setWindowTitle("NexusMind Agent")
        self.resize(720, 760)
        self._build_ui()
        self._build_tray()
        self._load_config(store.load())
        self.supervisor.start()


    def _build_ui(self) -> None:
        self.setMinimumSize(820, 760)
        self.resize(900, 860)
        self._apply_theme()

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        root = QWidget()
        root.setObjectName("page")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 28)
        layout.setSpacing(18)

        layout.addWidget(self._hero_section())
        layout.addWidget(self._summary_section())

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)
        grid.addWidget(self._local_api_group(), 0, 0)
        grid.addWidget(self._cloud_group(), 0, 1)
        grid.addWidget(self._folders_group(), 1, 0, 1, 2)
        grid.addWidget(self._runtime_group(), 2, 0, 1, 2)
        layout.addLayout(grid)

        layout.addWidget(self._action_section())
        layout.addWidget(self._status_section())
        layout.addStretch(1)

        scroll.setWidget(root)
        self.setCentralWidget(scroll)

    def _hero_section(self) -> QFrame:
        card = QFrame()
        card.setObjectName("heroCard")
        row = QHBoxLayout(card)
        row.setContentsMargins(22, 20, 22, 20)
        row.setSpacing(16)

        icon = QLabel()
        icon.setObjectName("brandIcon")
        pixmap = QPixmap(str(app_icon_path()))
        if not pixmap.isNull():
            icon.setPixmap(
                pixmap.scaled(
                    58,
                    58,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )
        icon.setFixedSize(58, 58)
        row.addWidget(icon)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)
        title = QLabel("NexusMind Local Agent")
        title.setObjectName("heroTitle")
        subtitle = QLabel("本地知识采集、Git 活动同步与云端连接控制中心")
        subtitle.setObjectName("heroSubtitle")
        text_col.addWidget(title)
        text_col.addWidget(subtitle)
        row.addLayout(text_col, 1)

        self.status_pill = QLabel("● 正在启动")
        self.status_pill.setObjectName("statusPill")
        self.status_pill.setAlignment(Qt.AlignCenter)
        row.addWidget(self.status_pill)
        return card

    def _summary_section(self) -> QFrame:
        wrap = QFrame()
        wrap.setObjectName("summaryWrap")
        grid = QGridLayout(wrap)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)

        self.api_summary = self._metric_card("本地服务", "启动中", "API")
        self.cloud_summary = self._metric_card("云端同步", "未配置", "Cloud")
        self.repo_summary = self._metric_card("采集仓库", "0", "Repositories")
        self.sync_summary = self._metric_card("最近同步", "暂无", "Last Sync")

        for index, widget in enumerate(
            [
                self.api_summary,
                self.cloud_summary,
                self.repo_summary,
                self.sync_summary,
            ]
        ):
            grid.addWidget(widget, 0, index)
        return wrap

    def _metric_card(self, label: str, value: str, hint: str) -> QFrame:
        card = QFrame()
        card.setObjectName("metricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(3)
        label_widget = QLabel(label)
        label_widget.setObjectName("metricLabel")
        value_widget = QLabel(value)
        value_widget.setObjectName("metricValue")
        hint_widget = QLabel(hint)
        hint_widget.setObjectName("metricHint")
        layout.addWidget(label_widget)
        layout.addWidget(value_widget)
        layout.addWidget(hint_widget)
        card.value_label = value_widget
        return card

    def _section_header(self, title: str, description: str) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(2)
        label = QLabel(title)
        label.setObjectName("sectionTitle")
        desc = QLabel(description)
        desc.setObjectName("sectionDescription")
        desc.setWordWrap(True)
        layout.addWidget(label)
        layout.addWidget(desc)
        return layout

    def _local_api_group(self) -> QGroupBox:
        box = QGroupBox()
        box.setObjectName("configCard")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)
        layout.addLayout(
            self._section_header(
                "本地服务",
                "运行 NexusMind 本地 API 和 Web 管理台。",
            )
        )

        self.local_api_enabled = QCheckBox("启用本地服务")
        self.local_api_enabled.toggled.connect(self._update_local_api_state)
        layout.addWidget(self.local_api_enabled)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        self.local_api_host = QLineEdit()
        self.local_api_host.setPlaceholderText("127.0.0.1")
        self.local_api_port = QSpinBox()
        self.local_api_port.setRange(1, 65535)
        self.data_root = QLineEdit()
        browse = QPushButton("选择")
        browse.setObjectName("subtleButton")
        browse.clicked.connect(self._choose_data_root)
        data_row = QHBoxLayout()
        data_row.setSpacing(8)
        data_row.addWidget(self.data_root, 1)
        data_row.addWidget(browse)
        form.addRow("Host", self.local_api_host)
        form.addRow("Port", self.local_api_port)
        form.addRow("数据目录", data_row)
        layout.addLayout(form)
        return box

    def _cloud_group(self) -> QGroupBox:
        box = QGroupBox()
        box.setObjectName("configCard")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)
        layout.addLayout(
            self._section_header(
                "云端同步",
                "连接 Cloudflare Worker 或其他 NexusMind Cloud API。",
            )
        )

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        self.cloud_url = QLineEdit()
        self.cloud_url.setPlaceholderText("https://nexusmind.example.workers.dev")
        self.cloud_token = QLineEdit()
        self.cloud_token.setEchoMode(QLineEdit.Password)
        self.cloud_token.setPlaceholderText("SYNC_TOKEN")
        form.addRow("云端地址", self.cloud_url)
        form.addRow("同步令牌", self.cloud_token)
        layout.addLayout(form)

        test_button = QPushButton("测试连接")
        test_button.setObjectName("secondaryButton")
        test_button.clicked.connect(self._test_cloud)
        layout.addWidget(test_button, 0, Qt.AlignRight)
        return box

    def _folders_group(self) -> QGroupBox:
        box = QGroupBox()
        box.setObjectName("configCard")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.addLayout(
            self._section_header(
                "Git 采集目录",
                "支持多次添加 Git 仓库或包含多个仓库的上级目录。",
            ),
            1,
        )
        self.folder_count_label = QLabel("0 个目录")
        self.folder_count_label.setObjectName("countBadge")
        header.addWidget(self.folder_count_label, 0, Qt.AlignTop)
        layout.addLayout(header)

        self.folder_list = QListWidget()
        self.folder_list.setObjectName("folderList")
        self.folder_list.setMinimumHeight(128)
        self.folder_list.setAlternatingRowColors(False)
        layout.addWidget(self.folder_list)

        row = QHBoxLayout()
        row.setSpacing(8)
        add = QPushButton("＋ 添加文件夹")
        add.setObjectName("secondaryButton")
        remove = QPushButton("移除选中")
        remove.setObjectName("subtleButton")
        add.clicked.connect(self._add_folder)
        remove.clicked.connect(self._remove_folder)
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch(1)
        layout.addLayout(row)
        return box

    def _runtime_group(self) -> QGroupBox:
        box = QGroupBox()
        box.setObjectName("configCard")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)
        layout.addLayout(
            self._section_header(
                "运行偏好",
                "控制同步频率以及系统登录后的 Agent 行为。",
            )
        )

        row = QHBoxLayout()
        row.setSpacing(18)
        interval_box = QVBoxLayout()
        interval_label = QLabel("同步周期")
        interval_label.setObjectName("fieldLabel")
        self.sync_interval = QSpinBox()
        self.sync_interval.setRange(60, 86400)
        self.sync_interval.setSuffix(" 秒")
        interval_box.addWidget(interval_label)
        interval_box.addWidget(self.sync_interval)
        row.addLayout(interval_box, 1)

        options = QVBoxLayout()
        self.auto_start = QCheckBox("登录系统后自动启动")
        self.start_minimized = QCheckBox("启动后直接最小化到托盘")
        options.addWidget(self.auto_start)
        options.addWidget(self.start_minimized)
        row.addLayout(options, 2)
        layout.addLayout(row)
        return box

    def _action_section(self) -> QFrame:
        card = QFrame()
        card.setObjectName("actionBar")
        row = QHBoxLayout(card)
        row.setContentsMargins(14, 12, 14, 12)
        row.setSpacing(10)

        self.save_button = QPushButton("保存并应用")
        self.save_button.setObjectName("primaryButton")
        self.save_button.clicked.connect(self._save_apply)
        self.sync_button = QPushButton("立即同步")
        self.sync_button.setObjectName("secondaryButton")
        self.sync_button.clicked.connect(self.supervisor.sync_now)
        self.open_button = QPushButton("打开 Web 管理台")
        self.open_button.setObjectName("secondaryButton")
        self.open_button.clicked.connect(self._open_local_console)

        row.addWidget(self.save_button)
        row.addWidget(self.sync_button)
        row.addStretch(1)
        row.addWidget(self.open_button)
        return card

    def _status_section(self) -> QFrame:
        card = QFrame()
        card.setObjectName("statusCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 13, 16, 13)
        layout.setSpacing(5)
        title = QLabel("运行状态")
        title.setObjectName("statusTitle")
        self.status_label = QLabel("Agent 正在启动…")
        self.status_label.setObjectName("statusText")
        self.status_label.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(self.status_label)
        return card

    def _apply_theme(self) -> None:
        check_icon = (app_icon_path().parent / "check.svg").as_posix()
        up_icon = (app_icon_path().parent / "chevron-up.svg").as_posix()
        down_icon = (app_icon_path().parent / "chevron-down.svg").as_posix()
        self.setStyleSheet(
            f"""
            QMainWindow, QWidget#page, QScrollArea {
                background: #F5F8FC;
                color: #172033;
                font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
                font-size: 13px;
            }
            QScrollArea { border: 0; }
            QFrame#heroCard {
                background: #FFFFFF;
                border: 1px solid #DCE5F2;
                border-radius: 14px;
            }
            QLabel#heroTitle {
                color: #12213F;
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#heroSubtitle {
                color: #6B7890;
                font-size: 12px;
            }
            QLabel#statusPill {
                min-width: 88px;
                padding: 7px 11px;
                border-radius: 13px;
                background: #E8F7FF;
                color: #087CB9;
                font-weight: 600;
            }
            QFrame#metricCard {
                background: #FFFFFF;
                border: 1px solid #DFE7F2;
                border-radius: 11px;
            }
            QLabel#metricLabel, QLabel#metricHint {
                color: #7B879D;
                font-size: 11px;
            }
            QLabel#metricValue {
                color: #173A7A;
                font-size: 17px;
                font-weight: 700;
            }
            QGroupBox#configCard {
                background: #FFFFFF;
                border: 1px solid #DCE5F2;
                border-radius: 12px;
                margin: 0;
            }
            QLabel#sectionTitle {
                color: #182B4D;
                font-size: 14px;
                font-weight: 700;
            }
            QLabel#sectionDescription {
                color: #7A879C;
                font-size: 11px;
            }
            QLabel#fieldLabel {
                color: #5F6D84;
                font-size: 11px;
            }
            QLabel#countBadge {
                padding: 4px 9px;
                border-radius: 9px;
                background: #EEF5FF;
                color: #1769C2;
                font-size: 11px;
                font-weight: 600;
            }
            QLineEdit, QSpinBox {
                min-height: 34px;
                padding: 0 10px;
                border: 1px solid #CDD8E8;
                border-radius: 7px;
                background: #FBFDFF;
                selection-background-color: #1689E6;
            }
            QLineEdit:focus, QSpinBox:focus {
                border: 1px solid #1689E6;
                background: #FFFFFF;
            }
            QLineEdit:disabled, QSpinBox:disabled {
                color: #98A3B3;
                background: #F1F4F8;
            }
            QSpinBox {
                padding-right: 38px;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                width: 30px;
                border-left: 1px solid #D5E0EC;
                background: #F7FAFD;
            }
            QSpinBox::up-button {
                subcontrol-origin: border;
                subcontrol-position: top right;
                border-top-right-radius: 6px;
                border-bottom: 1px solid #E5ECF4;
            }
            QSpinBox::down-button {
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                border-bottom-right-radius: 6px;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background: #EAF4FF;
            }
            QSpinBox::up-button:pressed, QSpinBox::down-button:pressed {
                background: #D8ECFF;
            }
            QSpinBox::up-arrow {
                image: url("{up_icon}");
                width: 12px;
                height: 12px;
            }
            QSpinBox::down-arrow {
                image: url("{down_icon}");
                width: 12px;
                height: 12px;
            }
            QSpinBox::up-button:disabled, QSpinBox::down-button:disabled {
                background: #F1F4F8;
                border-left: 1px solid #E0E6EE;
            }
            QCheckBox {
                spacing: 9px;
                color: #33445F;
                min-height: 26px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 1px solid #AFC0D4;
                border-radius: 5px;
                background: #FFFFFF;
            }
            QCheckBox::indicator:hover {
                border: 1px solid #1689E6;
                background: #F2F8FF;
            }
            QCheckBox::indicator:pressed {
                border: 1px solid #0877E4;
                background: #E3F1FF;
            }
            QCheckBox::indicator:checked {
                border: 1px solid #0877E4;
                background: #0877E4;
                image: url("{check_icon}");
            }
            QCheckBox::indicator:checked:hover {
                border: 1px solid #0069D5;
                background: #0069D5;
            }
            QCheckBox::indicator:disabled {
                border: 1px solid #D5DEE9;
                background: #EEF2F6;
            }
            QCheckBox::indicator:checked:disabled {
                border: 1px solid #AFC7E4;
                background: #AFC7E4;
            }
            QListWidget#folderList {
                border: 1px solid #D7E1EE;
                border-radius: 8px;
                background: #F9FBFE;
                padding: 5px;
                outline: none;
            }
            QListWidget#folderList::item {
                min-height: 34px;
                padding: 4px 8px;
                border-radius: 6px;
            }
            QListWidget#folderList::item:selected {
                color: #0B4E98;
                background: #DDEEFF;
            }
            QPushButton {
                min-height: 34px;
                padding: 0 14px;
                border-radius: 7px;
                font-weight: 600;
            }
            QPushButton#primaryButton {
                color: #FFFFFF;
                border: 1px solid #086AD8;
                background: #0877E4;
            }
            QPushButton#primaryButton:hover {
                background: #0069D5;
            }
            QPushButton#secondaryButton {
                color: #075AAE;
                border: 1px solid #A8C9EB;
                background: #EDF6FF;
            }
            QPushButton#secondaryButton:hover {
                background: #DDEEFF;
            }
            QPushButton#subtleButton {
                color: #52637C;
                border: 1px solid #D3DCE8;
                background: #FFFFFF;
            }
            QPushButton#subtleButton:hover {
                background: #F3F7FB;
            }
            QFrame#actionBar {
                background: #FFFFFF;
                border: 1px solid #DCE5F2;
                border-radius: 11px;
            }
            QFrame#statusCard {
                background: #EEF7FF;
                border: 1px solid #CDE5F8;
                border-radius: 11px;
            }
            QLabel#statusTitle {
                color: #135A9E;
                font-weight: 700;
            }
            QLabel#statusText {
                color: #4B627A;
                font-size: 12px;
            }
            """
        )
    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self)
        icon_path = app_icon_path()
        icon = QIcon(str(icon_path)) if icon_path.exists() else self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.tray.setIcon(icon)
        self.setWindowIcon(icon)
        menu = QMenu()
        show_action = QAction("打开配置", self)
        sync_action = QAction("立即同步", self)
        restart_action = QAction("重新加载配置", self)
        quit_action = QAction("退出 NexusMind Agent", self)
        show_action.triggered.connect(self._show_window)
        sync_action.triggered.connect(self.supervisor.sync_now)
        restart_action.triggered.connect(self.supervisor.reload)
        quit_action.triggered.connect(self._quit)
        menu.addAction(show_action)
        menu.addAction(sync_action)
        menu.addAction(restart_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()


    def _load_config(self, config: AgentConfig) -> None:
        self.local_api_enabled.setChecked(config.local_api_enabled)
        self.local_api_host.setText(config.local_api_host)
        self.local_api_port.setValue(config.local_api_port)
        self.data_root.setText(config.data_root)
        self.cloud_url.setText(config.cloud_url)
        self.cloud_token.setText(config.cloud_token)
        self.sync_interval.setValue(config.sync_interval)
        self.auto_start.setChecked(config.auto_start)
        self.start_minimized.setChecked(config.start_minimized)
        self.folder_list.clear()
        self.folder_list.addItems(config.folders)
        self._update_folder_count()
        self._update_local_api_state(config.local_api_enabled)

    def _collect_config(self) -> AgentConfig:
        return AgentConfig(
            folders=[
                self.folder_list.item(i).text()
                for i in range(self.folder_list.count())
            ],
            local_api_enabled=self.local_api_enabled.isChecked(),
            local_api_host=self.local_api_host.text(),
            local_api_port=self.local_api_port.value(),
            data_root=self.data_root.text(),
            cloud_url=self.cloud_url.text(),
            cloud_token=self.cloud_token.text(),
            sync_interval=self.sync_interval.value(),
            auto_start=self.auto_start.isChecked(),
            start_minimized=self.start_minimized.isChecked(),
        ).normalized()

    def _save_apply(self) -> None:
        try:
            config = self._collect_config()
            Path(config.data_root).mkdir(parents=True, exist_ok=True)
            set_autostart(config.auto_start)
            self.supervisor.apply(config)
            self._load_config(config)
            self.tray.showMessage(
                "NexusMind Agent",
                "配置已保存并热更新。",
                QSystemTrayIcon.Information,
                2500,
            )
        except Exception as exc:
            QMessageBox.critical(self, "配置保存失败", str(exc))


    def _add_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "选择 Git 仓库或包含 Git 仓库的目录",
            str(Path.home()),
        )
        if not selected:
            return
        path = str(Path(selected).resolve())
        existing = {
            self.folder_list.item(i).text().lower()
            for i in range(self.folder_list.count())
        }
        if path.lower() not in existing:
            self.folder_list.addItem(path)
            self._update_folder_count()

    def _remove_folder(self) -> None:
        for item in self.folder_list.selectedItems():
            self.folder_list.takeItem(self.folder_list.row(item))
        self._update_folder_count()

    def _update_folder_count(self) -> None:
        count = self.folder_list.count()
        self.folder_count_label.setText(f"{count} 个目录")

    def _update_local_api_state(self, enabled: bool) -> None:
        self.local_api_host.setEnabled(enabled)
        self.local_api_port.setEnabled(enabled)
        self.data_root.setEnabled(enabled)
        self.open_button.setEnabled(enabled)

    def _choose_data_root(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "选择 NexusMind 本地数据目录",
            self.data_root.text() or str(Path.home()),
        )
        if selected:
            self.data_root.setText(str(Path(selected).resolve()))

    def _open_local_console(self) -> None:
        if not self.local_api_enabled.isChecked():
            QMessageBox.information(self, "本地 API 未启用", "请先启用本地 API。")
            return
        webbrowser.open(
            f"http://{self.local_api_host.text()}:{self.local_api_port.value()}/"
        )

    def _test_cloud(self) -> None:
        url = self.cloud_url.text().strip().rstrip("/")
        if not url:
            QMessageBox.information(self, "Cloud API", "请先填写 Cloud API URL。")
            return
        try:
            import httpx

            response = httpx.get(url + "/health", timeout=5.0)
            response.raise_for_status()
            self.cloud_summary.value_label.setText("连接正常")
            self.cloud_summary.value_label.setStyleSheet("color: #087CB9;")
            QMessageBox.information(
                self,
                "云端连接",
                f"连接成功 · HTTP {response.status_code}",
            )
        except Exception as exc:
            self.cloud_summary.value_label.setText("连接失败")
            self.cloud_summary.value_label.setStyleSheet("color: #C33C54;")
            QMessageBox.critical(self, "云端连接失败", str(exc))

    def _render_status(self, status: AgentStatus) -> None:
        running = status.state == "running"
        error = status.state == "error"
        api = "运行中" if status.api_running else "未启用"
        cloud_configured = bool(self.cloud_url.text().strip())
        cloud = (
            "已同步"
            if status.cloud_delivered
            else ("等待同步" if cloud_configured else "未配置")
        )

        if error:
            self.status_pill.setText("● 异常")
            self.status_pill.setStyleSheet(
                "background:#FFF0F2;color:#C33C54;padding:7px 11px;"
                "border-radius:13px;font-weight:600;"
            )
        elif running:
            self.status_pill.setText("● 运行中")
            self.status_pill.setStyleSheet(
                "background:#E9FAF4;color:#11835F;padding:7px 11px;"
                "border-radius:13px;font-weight:600;"
            )
        else:
            self.status_pill.setText("● 已停止")
            self.status_pill.setStyleSheet(
                "background:#EEF2F7;color:#68768C;padding:7px 11px;"
                "border-radius:13px;font-weight:600;"
            )

        self.api_summary.value_label.setText(api)
        self.cloud_summary.value_label.setText(cloud)
        self.repo_summary.value_label.setText(str(status.repository_count))
        self.sync_summary.value_label.setText(status.last_sync or "暂无")
        self.status_label.setText(
            f"本地服务：{api}　·　云端：{cloud}　·　"
            f"仓库：{status.repository_count}　·　Commit：{status.commit_count}\n"
            f"{status.message or 'Agent 正常运行'}"
        )


    def _show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _tray_activated(self, reason) -> None:
        if reason in (
            QSystemTrayIcon.Trigger,
            QSystemTrayIcon.DoubleClick,
        ):
            self._show_window()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._quitting:
            event.accept()
            return
        event.ignore()
        self.hide()
        self.tray.showMessage(
            "NexusMind Agent",
            "Agent 仍在后台运行。右键托盘图标可退出。",
            QSystemTrayIcon.Information,
            2000,
        )

    def _quit(self) -> None:
        self._quitting = True
        self.supervisor.stop()
        self.tray.hide()
        QApplication.instance().quit()


def _notify_existing_instance() -> bool:
    socket = QLocalSocket()
    socket.connectToServer("NexusMindAgent")
    if not socket.waitForConnected(250):
        return False
    socket.write(b"show")
    socket.flush()
    socket.waitForBytesWritten(250)
    socket.disconnectFromServer()
    return True


def run_agent_gui(minimized: bool = False) -> int:
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "NexusMind.Agent"
            )
        except Exception:
            pass

    app = QApplication(sys.argv)
    icon_path = app_icon_path()
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    app.setQuitOnLastWindowClosed(False)

    if _notify_existing_instance():
        return 0

    QLocalServer.removeServer("NexusMindAgent")
    server = QLocalServer()
    if not server.listen("NexusMindAgent"):
        QMessageBox.critical(
            None,
            "NexusMind Agent",
            "无法启动本地单实例服务。",
        )
        return 1

    store = AgentConfigStore()
    window = AgentWindow(store)

    def handle_connection() -> None:
        socket = server.nextPendingConnection()
        if socket is None:
            return
        if socket.waitForReadyRead(250):
            command = bytes(socket.readAll()).decode("utf-8", errors="ignore")
            if command.strip() == "show":
                window._show_window()
        socket.disconnectFromServer()

    server.newConnection.connect(handle_connection)
    window._ipc_server = server
    config = store.load()
    if not (minimized or config.start_minimized):
        window.show()
    return app.exec()
