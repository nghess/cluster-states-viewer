"""Dark palette. Qt/PySide6 follows the OS theme by default (light, on most
lab machines) rather than anything set here in code, so this is applied
explicitly at startup instead of relying on a system setting."""
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def apply_dark_theme(app: QApplication):
    app.setStyle('Fusion')

    palette = QPalette()
    window = QColor(45, 45, 48)
    base = QColor(30, 30, 30)
    text = QColor(220, 220, 220)
    highlight = QColor(0, 120, 215)

    palette.setColor(QPalette.Window, window)
    palette.setColor(QPalette.WindowText, text)
    palette.setColor(QPalette.Base, base)
    palette.setColor(QPalette.AlternateBase, window)
    palette.setColor(QPalette.ToolTipBase, text)
    palette.setColor(QPalette.ToolTipText, text)
    palette.setColor(QPalette.Text, text)
    palette.setColor(QPalette.Button, window)
    palette.setColor(QPalette.ButtonText, text)
    palette.setColor(QPalette.BrightText, QColor(255, 80, 80))
    palette.setColor(QPalette.Link, highlight)
    palette.setColor(QPalette.Highlight, highlight)
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(120, 120, 120))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(120, 120, 120))

    app.setPalette(palette)
