from __future__ import annotations

import os
import sys
import time
import webbrowser

import psutil
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, Qt, Signal, QSettings
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtGui import QAction, QCloseEvent, QColor, QIcon, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
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
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSystemTrayIcon,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from nexusmind import __version__
from nexusmind.agent.autostart import set_autostart
from nexusmind.agent.brand import app_icon_path
from nexusmind.agent.configuration import AgentConfig, AgentConfigStore
from nexusmind.agent.runtime import AgentStatus, AgentSupervisor


class StatusBridge(QObject):
    changed = Signal(object)


class PreferenceButton(QPushButton):
    def __init__(self, text: str, menu: QMenu, parent: QWidget | None = None):
        super().__init__(text, parent)
        self._popup_menu = menu
        self._menu_open = False
        self.setObjectName("preferenceButton")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(116, 34)
        self.clicked.connect(self._toggle_menu)
        self._popup_menu.aboutToShow.connect(self._on_menu_show)
        self._popup_menu.aboutToHide.connect(self._on_menu_hide)

    def _toggle_menu(self) -> None:
        if self._menu_open:
            self._popup_menu.close()
            return
        self._popup_menu.setFixedWidth(self.width())
        self._popup_menu.popup(self.mapToGlobal(QPoint(0, self.height() + 6)))

    def _on_menu_show(self) -> None:
        self._menu_open = True
        self.setProperty("menuOpen", True)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def _on_menu_hide(self) -> None:
        self._menu_open = False
        self.setProperty("menuOpen", False)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        cx = self.width() - 17
        cy = self.height() // 2
        if self._menu_open:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#DDEEFF"))
            painter.drawEllipse(cx - 9, cy - 9, 18, 18)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#0877E4"), 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawLine(cx - 5, cy + 2, cx, cy - 3)
            painter.drawLine(cx, cy - 3, cx + 5, cy + 2)
        else:
            painter.setPen(QPen(QColor("#60758F"), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawLine(cx - 4, cy - 2, cx, cy + 2)
            painter.drawLine(cx, cy + 2, cx + 4, cy - 2)


class AgentWindow(QMainWindow):
    def __init__(self, store: AgentConfigStore):
        super().__init__()
        self.store = store
        self.bridge = StatusBridge()
        self.bridge.changed.connect(self._render_status)
        self.supervisor = AgentSupervisor(store, self.bridge.changed.emit)
        self._quitting = False
        self.ui_settings = QSettings("NexusMind", "NexusMindAgent")
        self.ui_language = str(self.ui_settings.value("ui/language", "zh-CN"))
        self.ui_theme = str(self.ui_settings.value("ui/theme", "system"))

        self.setWindowTitle("NexusMind Agent")
        self.resize(720, 760)
        self._build_ui()
        self._build_tray()
        self._load_config(store.load())
        self._apply_language()
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

    def _preference_button(
        self,
        current_value: str,
        items: list[tuple[str, str]],
        tooltip: str,
        callback,
    ) -> QPushButton:
        current_label = next(
            (label for label, value in items if value == current_value),
            items[0][0],
        )

        menu = QMenu(self)
        menu.setObjectName("preferenceMenu")
        menu.setFixedWidth(116)
        for label, value in items:
            action = QAction(label, menu)
            action.setCheckable(True)
            action.setChecked(value == current_value)
            action.setData(value)
            action.triggered.connect(
                lambda _checked=False, selected=value: callback(selected)
            )
            menu.addAction(action)

        button = PreferenceButton(current_label, menu, self)
        button.setToolTip(tooltip)
        return button

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

        prefs = QHBoxLayout()
        prefs.setSpacing(8)

        self.language_select = self._preference_button(
            self.ui_language,
            [("中文", "zh-CN"), ("English", "en-US")],
            "语言 / Language",
            self._change_language,
        )
        theme_items = (
            [
                ("System", "system"),
                ("Light", "light"),
                ("Dark", "dark"),
                ("Ocean", "ocean"),
                ("Forest", "forest"),
            ]
            if self.ui_language == "en-US"
            else [
                ("跟随系统", "system"),
                ("浅色", "light"),
                ("深色", "dark"),
                ("海洋", "ocean"),
                ("森林", "forest"),
            ]
        )
        self.theme_select = self._preference_button(
            self.ui_theme,
            theme_items,
            "主题 / Theme",
            self._change_theme,
        )
        prefs.addWidget(self.language_select)
        prefs.addWidget(self.theme_select)
        row.addLayout(prefs)

        self.status_pill = QLabel("● 正在启动")
        self.status_pill.setObjectName("statusPill")
        self.status_pill.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.status_pill.setFixedWidth(72)
        row.addWidget(self.status_pill)
        return card

    def _summary_section(self) -> QFrame:
        wrap = QFrame()
        wrap.setObjectName("summaryWrap")
        grid = QGridLayout(wrap)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)

        self.api_summary = self._metric_card("本地服务", "启动中", "接口服务")
        self.cloud_summary = self._metric_card("云端同步", "未配置", "远端服务")
        self.repo_summary = self._metric_card("采集仓库", "0", "仓库数量")
        self.sync_summary = self._metric_card("最近同步", "暂无", "同步时间")

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
        self.local_api_port.setMinimumWidth(180)
        self.local_api_port.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
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
                "连接 NexusMind Cloud API，实现云端同步与远端能力访问。",
            )
        )

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        self.cloud_url = QLineEdit()
        self.cloud_url.setPlaceholderText("https://cloud.example.com")
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
        self.sync_progress = QProgressBar()
        self.sync_progress.setObjectName("syncProgress")
        self.sync_progress.setRange(0, 0)
        self.sync_progress.setTextVisible(False)
        self.sync_progress.setFixedWidth(120)
        self.sync_progress.setFixedHeight(8)
        self.sync_progress.hide()
        self.sync_progress_label = QLabel("正在双向同步知识库…")
        self.sync_progress_label.setObjectName("syncProgressLabel")
        self.sync_progress_label.hide()
        self.open_button = QPushButton("打开 Web 管理台")
        self.open_button.setObjectName("secondaryButton")
        self.open_button.clicked.connect(self._open_local_console)

        row.addWidget(self.save_button)
        row.addWidget(self.sync_button)
        row.addWidget(self.sync_progress)
        row.addWidget(self.sync_progress_label)
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

    def _change_language(self, language: str, *_args) -> None:
        language = language or "zh-CN"
        if language == self.ui_language:
            return
        self.ui_language = str(language)
        self.ui_settings.setValue("ui/language", self.ui_language)
        config = self.store.load()
        self._build_ui()
        self._load_config(config)
        self._apply_language()

    def _change_theme(self, theme: str, *_args) -> None:
        theme = theme or "system"
        if theme == self.ui_theme:
            return
        self.ui_theme = str(theme)
        self.ui_settings.setValue("ui/theme", self.ui_theme)
        config = self.store.load()
        self._build_ui()
        self._load_config(config)
        self._apply_language()

    def _apply_language(self) -> None:
        if self.ui_language != "en-US":
            return

        translations = {
            "本地知识采集、Git 活动同步与云端连接控制中心": "Local knowledge collection, Git activity sync, and cloud connectivity",
            "● 正在启动": "● Starting",
            "本地服务": "Local Service",
            "启动中": "Starting",
            "接口服务": "API Service",
            "云端同步": "Cloud Sync",
            "未配置": "Not configured",
            "远端服务": "Remote Service",
            "采集仓库": "Repositories",
            "仓库数量": "Repository Count",
            "最近同步": "Last Sync",
            "暂无": "None",
            "同步时间": "Sync Time",
            "运行 NexusMind 本地 API 和 Web 管理台。": "Run the NexusMind local API and web console.",
            "启用本地服务": "Enable local service",
            "选择": "Browse",
            "数据目录": "Data directory",
            "连接 NexusMind Cloud API，实现云端同步与远端能力访问。": "Connect to NexusMind Cloud API for synchronization and remote capabilities.",
            "云端地址": "Cloud endpoint",
            "同步令牌": "Sync token",
            "测试连接": "Test connection",
            "Git 采集目录": "Git Collection Folders",
            "支持多次添加 Git 仓库或包含多个仓库的上级目录。": "Add Git repositories or parent folders containing multiple repositories.",
            "＋ 添加文件夹": "＋ Add Folder",
            "移除选中": "Remove Selected",
            "运行偏好": "Runtime Preferences",
            "控制同步频率以及系统登录后的 Agent 行为。": "Control sync frequency and Agent behavior after sign-in.",
            "同步周期": "Sync interval",
            "登录系统后自动启动": "Start automatically after sign-in",
            "启动后直接最小化到托盘": "Start minimized to tray",
            "保存并应用": "Save & Apply",
            "立即同步": "Sync Now",
            "正在双向同步知识库…": "Synchronizing knowledge base…",
            "打开 Web 管理台": "Open Web Console",
            "运行状态": "Runtime Status",
            "Agent 正在启动…": "Agent is starting…",
        }
        for widget_type in (QLabel, QPushButton, QCheckBox, QGroupBox):
            for widget in self.findChildren(widget_type):
                if isinstance(widget, QGroupBox):
                    current = widget.title()
                    if current in translations:
                        widget.setTitle(translations[current])
                elif hasattr(widget, "text"):
                    current = widget.text()
                    if current in translations:
                        widget.setText(translations[current])

        self.sync_interval.setSuffix(" sec")
        if hasattr(self, "folder_count_label"):
            text = self.folder_count_label.text()
            if text.endswith(" 个目录"):
                self.folder_count_label.setText(text.replace(" 个目录", " folders"))

    def _apply_theme(self) -> None:
        check_icon = (app_icon_path().parent / "check.svg").as_posix()
        up_icon = (app_icon_path().parent / "chevron-up.svg").as_posix()
        down_icon = (app_icon_path().parent / "chevron-down.svg").as_posix()
        stylesheet = """
            QMainWindow, QWidget#page, QScrollArea {
                background: #F5F8FC;
                color: #172033;
                font-family: "Segoe UI", "Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC", "Noto Sans", "Ubuntu", "DejaVu Sans", sans-serif;
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
            QPushButton#preferenceButton {
                padding: 0 32px 0 11px;
                border: 1px solid #D4DEEA;
                border-radius: 8px;
                background: #F9FBFD;
                color: #243650;
                font-size: 12px;
                font-weight: 600;
                text-align: left;
            }
            QPushButton#preferenceButton:hover {
                border-color: #1689E6;
                background: #F7FBFF;
            }
            QPushButton#preferenceButton:pressed,
            QPushButton#preferenceButton[menuOpen="true"] {
                background: #EDF6FF;
                border-color: #0F7ED6;
            }
            QMenu#preferenceMenu {
                background: #FFFFFF;
                color: #243650;
                border: 1px solid #C8D5E5;
                border-radius: 10px;
                padding: 6px;
            }
            QMenu#preferenceMenu::item {
                min-height: 34px;
                padding: 0 12px 0 34px;
                margin: 2px 0;
                border-radius: 7px;
                background: transparent;
                color: #243650;
            }
            QMenu#preferenceMenu::item:selected {
                background: #F0F7FF;
                color: #075EA8;
            }
            QMenu#preferenceMenu::item:checked {
                background: #DDEEFF;
                color: #075EA8;
                font-weight: 700;
            }
            QMenu#preferenceMenu::indicator {
                width: 14px;
                height: 14px;
                left: 10px;
            }
            QMenu#preferenceMenu::indicator:checked {
                image: url("{check_icon}");
            }
            QLabel#statusPill {
                min-width: 0;
                padding: 0;
                border: none;
                background: transparent;
                color: #0B9A78;
                font-size: 12px;
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
            QProgressBar#syncProgress {
                border: 0;
                border-radius: 4px;
                background: #E6EEF8;
            }
            QProgressBar#syncProgress::chunk {
                border-radius: 4px;
                background: #1689E6;
            }
            QLabel#syncProgressLabel {
                color: #5F6D84;
                font-size: 11px;
                font-weight: 600;
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
        stylesheet = (
            stylesheet.replace("{check_icon}", check_icon)
            .replace("{up_icon}", up_icon)
            .replace("{down_icon}", down_icon)
        )

        resolved_theme = getattr(self, "ui_theme", "system")
        if resolved_theme == "system":
            window_color = QApplication.palette().color(QPalette.Window)
            resolved_theme = "dark" if window_color.lightness() < 128 else "light"

        theme_overrides = {
            "dark": """
                QMainWindow, QWidget#page, QScrollArea { background: #111821; color: #E6EDF3; }
                QFrame#heroCard, QFrame#metricCard, QGroupBox#configCard, QFrame#actionBar { background: #18212C; border-color: #2D3A49; }
                QLabel#heroTitle, QLabel#sectionTitle, QLabel#metricValue, QLabel#fieldLabel { color: #E6EDF3; }
                QLabel#heroSubtitle, QLabel#sectionDescription, QLabel#metricLabel, QLabel#metricHint, QLabel#syncProgressLabel { color: #9EADBC; }
                QLineEdit, QSpinBox, QListWidget#folderList, QPushButton#preferenceButton { background: #111821; color: #E6EDF3; border-color: #3A4858; }
                QPushButton#preferenceButton:hover { background: #182432; border-color: #5A8CC4; }
                QMenu#preferenceMenu { background: #18212C; color: #E6EDF3; border-color: #344253; }
                QMenu#preferenceMenu::item:selected { background: #203B5D; color: #FFFFFF; }
                QMenu#preferenceMenu::item:checked { background: #285486; color: #FFFFFF; font-weight: 700; }
                QCheckBox { color: #D5DEE8; }
                QFrame#statusCard { background: #14263A; border-color: #274765; }
                QLabel#statusTitle { color: #82BFFF; }
                QLabel#statusText { color: #B7C6D6; }
                QPushButton#subtleButton { background: #18212C; color: #C6D2DF; border-color: #3A4858; }
            """,
            "ocean": """
                QMainWindow, QWidget#page, QScrollArea { background: #EEF7FB; color: #173042; }
                QFrame#heroCard, QFrame#metricCard, QGroupBox#configCard, QFrame#actionBar { background: #FFFFFF; border-color: #C9DFE8; }
                QLabel#metricValue { color: #087EA4; }
                QPushButton#preferenceButton { border-color: #A8CBD9; color: #173042; background: #FFFFFF; }
                QMenu#preferenceMenu { border-color: #B9D7E2; color: #173042; background: #FFFFFF; }
                QMenu#preferenceMenu::item:selected { background: #E7F5F9; color: #075E7A; }
                QMenu#preferenceMenu::item:checked { background: #CFEAF3; color: #075E7A; font-weight: 700; }
                QFrame#statusCard { background: #E3F3F8; border-color: #BFDFEA; }
            """,
            "forest": """
                QMainWindow, QWidget#page, QScrollArea { background: #F1F6F1; color: #203326; }
                QFrame#heroCard, QFrame#metricCard, QGroupBox#configCard, QFrame#actionBar { background: #FFFFFF; border-color: #CDDFCE; }
                QLabel#metricValue { color: #2F7D4A; }
                QPushButton#preferenceButton { border-color: #B6D0B8; color: #203326; background: #FFFFFF; }
                QMenu#preferenceMenu { border-color: #C4D9C6; color: #203326; background: #FFFFFF; }
                QMenu#preferenceMenu::item:selected { background: #E8F3EA; color: #245D37; }
                QMenu#preferenceMenu::item:checked { background: #D5E9D9; color: #245D37; font-weight: 700; }
                QFrame#statusCard { background: #E8F3E9; border-color: #C5DEC8; }
                QLabel#statusTitle { color: #2F7D4A; }
            """,
        }
        stylesheet += theme_overrides.get(resolved_theme, "")
        self.setStyleSheet(stylesheet)

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self)
        icon_path = app_icon_path()
        icon = QIcon(str(icon_path)) if icon_path.exists() else self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.tray.setIcon(icon)
        self.setWindowIcon(icon)
        menu = QMenu()
        show_action = QAction("打开配置", self)
        self.sync_action = QAction("立即同步", self)
        restart_action = QAction("重新加载配置", self)
        quit_action = QAction("退出 NexusMind Agent", self)
        show_action.triggered.connect(self._show_window)
        self.sync_action.triggered.connect(self.supervisor.sync_now)
        restart_action.triggered.connect(self.supervisor.reload)
        quit_action.triggered.connect(self._quit)
        menu.addAction(show_action)
        menu.addAction(self.sync_action)
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

    def _show_cloud_dialog(
        self,
        title: str,
        message: str,
        *,
        success: bool,
        details: list[tuple[str, str]] | None = None,
        copy_text: str = "",
    ) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        dialog.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        dialog.setAttribute(Qt.WA_TranslucentBackground, True)
        dialog.setFixedWidth(520)
        dialog.setMinimumHeight(360)

        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(8, 8, 8, 8)

        surface = QFrame()
        surface.setObjectName("connectionDialogSurface")
        outer.addWidget(surface)

        layout = QVBoxLayout(surface)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title_bar = QFrame()
        title_bar.setObjectName("connectionTitleBar")
        title_bar.setFixedHeight(46)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(18, 0, 10, 0)
        title_layout.setSpacing(8)

        window_title = QLabel("NexusMind · 云端连接")
        window_title.setObjectName("connectionWindowTitle")
        title_layout.addWidget(window_title)
        title_layout.addStretch(1)

        window_close = QPushButton("×")
        window_close.setObjectName("connectionWindowClose")
        window_close.setFixedSize(30, 30)
        window_close.clicked.connect(dialog.reject)
        title_layout.addWidget(window_close)
        layout.addWidget(title_bar)

        body = QWidget()
        body.setObjectName("connectionDialogBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 20, 24, 22)
        body_layout.setSpacing(16)
        layout.addWidget(body)

        layout = body_layout

        header = QHBoxLayout()
        header.setSpacing(14)

        icon = QLabel("✓" if success else "×")
        icon.setAlignment(Qt.AlignCenter)
        icon.setFixedSize(44, 44)
        icon.setObjectName("connectionResultIcon")
        icon.setProperty("success", success)
        header.addWidget(icon)

        header_text = QVBoxLayout()
        header_text.setSpacing(3)
        title_label = QLabel(title)
        title_label.setObjectName("connectionResultTitle")
        state_label = QLabel("连接正常" if success else "连接失败")
        state_label.setObjectName("connectionResultState")
        state_label.setProperty("success", success)
        header_text.addWidget(title_label)
        header_text.addWidget(state_label)
        header.addLayout(header_text, 1)
        layout.addLayout(header)

        message_label = QLabel(message)
        message_label.setObjectName("connectionResultMessage")
        message_label.setWordWrap(True)
        layout.addWidget(message_label)

        detail_card = QFrame()
        detail_card.setObjectName("connectionDetailCard")
        detail_layout = QGridLayout(detail_card)
        detail_layout.setContentsMargins(14, 12, 14, 12)
        detail_layout.setHorizontalSpacing(18)
        detail_layout.setVerticalSpacing(9)

        for row, (label, value) in enumerate(details or []):
            key_label = QLabel(label)
            key_label.setObjectName("connectionDetailKey")
            value_label = QLabel(value or "-")
            value_label.setObjectName("connectionDetailValue")
            value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            value_label.setWordWrap(True)
            detail_layout.addWidget(key_label, row, 0, Qt.AlignTop)
            detail_layout.addWidget(value_label, row, 1, Qt.AlignTop)

        layout.addWidget(detail_card)
        layout.addStretch(1)

        actions = QHBoxLayout()
        copy_button = QPushButton("复制详情")
        copy_button.setObjectName("connectionSecondaryButton")
        close_button = QPushButton("关闭")
        close_button.setObjectName("connectionPrimaryButton")
        close_button.setDefault(True)
        copy_button.clicked.connect(
            lambda: QApplication.clipboard().setText(copy_text)
        )
        close_button.clicked.connect(dialog.accept)
        actions.addWidget(copy_button)
        actions.addStretch(1)
        actions.addWidget(close_button)
        layout.addLayout(actions)

        dialog.setStyleSheet("""
            QDialog {
                background: transparent;
                color: #172033;
                font-family: "Segoe UI", "Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC", "Noto Sans", "Ubuntu", "DejaVu Sans", sans-serif;
                font-size: 13px;
            }
            QFrame#connectionDialogSurface {
                background: #F7F9FC;
                border: 1px solid #D9E2EE;
                border-radius: 14px;
            }
            QFrame#connectionTitleBar {
                background: #FFFFFF;
                border: none;
                border-bottom: 1px solid #E1E7F0;
                border-top-left-radius: 14px;
                border-top-right-radius: 14px;
            }
            QWidget#connectionDialogBody {
                background: #F7F9FC;
                border: none;
                border-bottom-left-radius: 14px;
                border-bottom-right-radius: 14px;
            }
            QLabel#connectionWindowTitle {
                color: #26364F;
                font-size: 13px;
                font-weight: 700;
                border: none;
                background: transparent;
            }
            QPushButton#connectionWindowClose {
                border: none;
                border-radius: 7px;
                background: transparent;
                color: #718096;
                font-size: 20px;
                font-weight: 400;
                padding: 0;
            }
            QPushButton#connectionWindowClose:hover {
                background: #EEF2F7;
                color: #25364D;
            }
            QLabel#connectionResultIcon {
                border-radius: 22px;
                font-size: 23px;
                font-weight: 800;
            }
            QLabel#connectionResultIcon[success="true"] {
                background: #E8F8F1;
                color: #12815F;
                border: 1px solid #B9E8D7;
            }
            QLabel#connectionResultIcon[success="false"] {
                background: #FFF0F2;
                color: #C43E56;
                border: 1px solid #F2C7CE;
            }
            QLabel#connectionResultTitle {
                color: #172033;
                font-size: 17px;
                font-weight: 700;
            }
            QLabel#connectionResultState {
                font-size: 12px;
                font-weight: 600;
            }
            QLabel#connectionResultState[success="true"] { color: #12815F; }
            QLabel#connectionResultState[success="false"] { color: #C43E56; }
            QLabel#connectionResultMessage {
                color: #68778E;
                line-height: 1.4;
            }
            QFrame#connectionDetailCard {
                background: #FFFFFF;
                border: 1px solid #DDE5F0;
                border-radius: 10px;
            }
            QLabel#connectionDetailKey {
                min-width: 82px;
                color: #8390A4;
                font-size: 12px;
            }
            QLabel#connectionDetailValue {
                color: #26364F;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#connectionPrimaryButton,
            QPushButton#connectionSecondaryButton {
                min-height: 34px;
                padding: 0 16px;
                border-radius: 7px;
                font-weight: 600;
            }
            QPushButton#connectionPrimaryButton {
                color: #FFFFFF;
                background: #0877E4;
                border: 1px solid #086AD8;
            }
            QPushButton#connectionPrimaryButton:hover {
                background: #0069D5;
            }
            QPushButton#connectionSecondaryButton {
                color: #52637C;
                background: #FFFFFF;
                border: 1px solid #D1DBE8;
            }
            QPushButton#connectionSecondaryButton:hover {
                background: #F0F5FA;
            }
        """)
        dialog.exec()

    def _test_cloud(self) -> None:
        url = self.cloud_url.text().strip().rstrip("/")
        token = self.cloud_token.text().strip()
        endpoint = url + "/api/cloud/vault/manifest" if url else ""
        if not url:
            self._show_cloud_dialog(
                "无法测试连接",
                "还没有配置云端服务地址，请填写 Cloud API URL 后再试。",
                success=False,
                details=[("检查项", "Cloud API URL"), ("状态", "未配置")],
                copy_text="Cloud API URL 未配置",
            )
            return
        if not token:
            self._show_cloud_dialog(
                "无法测试连接",
                "还没有配置同步令牌，请填写与 Worker SYNC_TOKEN 相同的值。",
                success=False,
                details=[("检查项", "SYNC_TOKEN"), ("状态", "未配置")],
                copy_text="SYNC_TOKEN 未配置",
            )
            return

        started = time.perf_counter()
        response = None
        try:
            import httpx

            response = httpx.get(
                endpoint,
                headers={"Authorization": f"Bearer {token}"},
                timeout=8.0,
            )
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            response.raise_for_status()
            payload = response.json()
            note_count = len(payload.get("notes", []))
            tombstone_count = len(payload.get("tombstones", []))

            self.cloud_summary.value_label.setText("连接正常")
            self.cloud_summary.value_label.setStyleSheet("color: #12815F;")
            details = [
                ("服务地址", url),
                ("HTTP 状态", str(response.status_code)),
                ("响应耗时", f"{elapsed_ms} ms"),
                ("Token 验证", "已通过"),
                ("云端知识文件", str(note_count)),
                ("删除标记", str(tombstone_count)),
            ]
            copy_text = "\n".join(
                ["NexusMind Cloud 连接测试", *[
                    f"{key}: {value}" for key, value in details
                ]]
            )
            self._show_cloud_dialog(
                "Cloud API 连接测试",
                "服务可访问，SYNC_TOKEN 已验证，双向同步接口正常。",
                success=True,
                details=details,
                copy_text=copy_text,
            )
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self.cloud_summary.value_label.setText("连接失败")
            self.cloud_summary.value_label.setStyleSheet("color: #C43E56;")
            http_status = getattr(response, "status_code", None)
            message = (
                "SYNC_TOKEN 验证失败，请确认本地令牌与 Worker 的 SYNC_TOKEN 完全一致。"
                if http_status == 401
                else "未能通过双向同步接口检查，请检查地址、网络或云端服务状态。"
            )
            details = [
                ("服务地址", url),
                ("测试接口", endpoint),
                ("HTTP 状态", str(http_status or "-")),
                ("耗时", f"{elapsed_ms} ms"),
                ("错误类型", type(exc).__name__),
                ("错误原因", str(exc)),
            ]
            copy_text = "\n".join(
                ["NexusMind Cloud 连接测试失败", *[
                    f"{key}: {value}" for key, value in details
                ]]
            )
            self._show_cloud_dialog(
                "Cloud API 连接测试",
                message,
                success=False,
                details=details,
                copy_text=copy_text,
            )

    def _render_status(self, status: AgentStatus) -> None:
        running = status.state == "running"
        error = status.state == "error"
        english = self.ui_language == "en-US"
        api = ("Running" if status.api_running else "Disabled") if english else ("运行中" if status.api_running else "未启用")
        cloud_labels = ({
            "unconfigured": "Not configured",
            "incomplete": "Incomplete",
            "syncing": "Syncing",
            "synced": "Synced",
            "partial": "Partial failure",
            "error": "Sync failed",
        } if english else {
            "unconfigured": "未配置",
            "incomplete": "配置不完整",
            "syncing": "同步中",
            "synced": "已同步",
            "partial": "部分失败",
            "error": "同步失败",
        })
        cloud = cloud_labels.get(status.cloud_state, "Not configured" if english else "未配置")

        self.sync_button.setEnabled(not status.sync_in_progress)
        self.sync_button.setText(("Syncing…" if status.sync_in_progress else "Sync Now") if english else ("同步中…" if status.sync_in_progress else "立即同步"))
        self.sync_progress.setVisible(status.sync_in_progress)
        self.sync_progress_label.setVisible(status.sync_in_progress)
        if hasattr(self, "sync_action"):
            self.sync_action.setEnabled(not status.sync_in_progress)
            self.sync_action.setText(("Syncing…" if status.sync_in_progress else "Sync Now") if english else ("正在同步…" if status.sync_in_progress else "立即同步"))

        if status.sync_in_progress:
            self.status_pill.setText("●  Syncing" if english else "●  同步中")
            self.status_pill.setStyleSheet("color:#0877E4;font-weight:600;")
        elif error:
            self.status_pill.setText("●  Error" if english else "●  异常")
            self.status_pill.setStyleSheet("color:#C33C54;font-weight:600;")
        elif running:
            self.status_pill.setText("●  Running" if english else "●  运行中")
            self.status_pill.setStyleSheet("color:#11835F;font-weight:600;")
        else:
            self.status_pill.setText("●  Stopped" if english else "●  已停止")
            self.status_pill.setStyleSheet("color:#68768C;font-weight:600;")

        self.api_summary.value_label.setText(api)
        self.cloud_summary.value_label.setText(cloud)
        self.repo_summary.value_label.setText(str(status.repository_count))
        self.sync_summary.value_label.setText(
            ("Syncing…" if english else "同步中…") if status.sync_in_progress else (status.last_sync or ("None" if english else "暂无"))
        )
        if status.sync_in_progress:
            status_message = "Collecting Git activity and synchronizing the local and cloud knowledge base…" if english else "正在采集 Git 活动并执行本地与云端知识库双向同步，请稍候…"
        else:
            status_message = status.message or ("Agent is running normally" if english else "Agent 正常运行")
        if english:
            self.status_label.setText(
                f"Local service: {api} · Cloud: {cloud} · "
                f"Repositories: {status.repository_count} · Commits: {status.commit_count}\n"
                f"{status_message}"
            )
        else:
            self.status_label.setText(
                f"本地服务：{api}　·　云端：{cloud}　·　"
                f"仓库：{status.repository_count}　·　Commit：{status.commit_count}\n"
                f"{status_message}"
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


INSTANCE_SERVER = "NexusMindAgent"


def _send_instance_command(command: str, wait_for_reply: bool = False) -> str | None:
    socket = QLocalSocket()
    socket.connectToServer(INSTANCE_SERVER)
    if not socket.waitForConnected(350):
        return None
    socket.write(command.encode("utf-8"))
    socket.flush()
    socket.waitForBytesWritten(350)
    reply = ""
    if wait_for_reply and socket.waitForReadyRead(500):
        reply = bytes(socket.readAll()).decode("utf-8", errors="ignore").strip()
    socket.disconnectFromServer()
    return reply


def _probe_existing_instance() -> str | None:
    """Return running Agent version, empty string for legacy Agent, or None."""
    return _send_instance_command("version", wait_for_reply=True)


def _terminate_legacy_agent_processes() -> bool:
    """Terminate packaged NexusMind Agent processes from an older IPC protocol."""
    current_pid = os.getpid()
    candidates: list[psutil.Process] = []
    for process in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
        try:
            if process.pid == current_pid:
                continue
            name = (process.info.get("name") or "").lower()
            exe = (process.info.get("exe") or "").lower()
            cmdline = " ".join(process.info.get("cmdline") or []).lower()
            packaged_agent = (
                "nexusmindagent" in name
                or "nexusmindagent" in Path(exe).name.lower()
                or "nexusmindagent.app/contents/macos/nexusmindagent" in exe
            )
            api_child = "--api-service" in cmdline and "nexusmindagent" in cmdline
            if packaged_agent or api_child:
                candidates.append(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if not candidates:
        return False

    for process in candidates:
        try:
            process.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    _, alive = psutil.wait_procs(candidates, timeout=3)
    for process in alive:
        try:
            process.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    psutil.wait_procs(alive, timeout=2)
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
    # Use one Qt widget style on Windows, macOS, and Linux so native theme
    # differences do not change control geometry or interaction states.
    app.setStyle("Fusion")
    icon_path = app_icon_path()
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    app.setQuitOnLastWindowClosed(False)

    existing_version = _probe_existing_instance()
    if existing_version == __version__:
        _send_instance_command("show")
        return 0
    if existing_version is not None:
        if existing_version:
            _send_instance_command("quit")
            deadline = time.time() + 3
            while time.time() < deadline and _probe_existing_instance() is not None:
                time.sleep(0.1)
        else:
            _terminate_legacy_agent_processes()
            time.sleep(0.3)

    QLocalServer.removeServer(INSTANCE_SERVER)
    server = QLocalServer()
    if not server.listen(INSTANCE_SERVER):
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
        if socket.waitForReadyRead(350):
            command = bytes(socket.readAll()).decode("utf-8", errors="ignore").strip()
            if command == "show":
                window._show_window()
            elif command == "version":
                socket.write(__version__.encode("utf-8"))
                socket.flush()
                socket.waitForBytesWritten(350)
            elif command == "quit":
                socket.disconnectFromServer()
                window._quit()
                return
        socket.disconnectFromServer()

    server.newConnection.connect(handle_connection)
    window._ipc_server = server
    config = store.load()
    if not (minimized or config.start_minimized):
        window.show()
    return app.exec()
