import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMainWindow

from nexusmind.agent.gui import AgentWindow


def test_agent_theme_applies_without_runtime_name_errors():
    app = QApplication.instance() or QApplication([])
    window = AgentWindow.__new__(AgentWindow)
    QMainWindow.__init__(window)
    window._quitting = True

    window._apply_theme()

    stylesheet = window.styleSheet()
    assert "QMainWindow" in stylesheet
    assert "background: #F5F8FC;" in stylesheet
    assert "{check_icon}" not in stylesheet
    assert "{up_icon}" not in stylesheet
    assert "{down_icon}" not in stylesheet

    window.close()
    app.processEvents()
