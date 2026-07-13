"""Compatibility re-export module: single Qt5/Qt6 import point for the plugin.

The names imported here are intentionally re-exported for the other modules
(hence the ``noqa: F401`` markers).
"""

from qgis.core import QgsLayoutExporter, QgsUnitTypes  # noqa: F401
from qgis.PyQt.QtCore import (  # noqa: F401
    QDateTime,
    QRectF,
    Qt,
    QStandardPaths,
    QUrl,
    QVariant,
)
from qgis.PyQt.QtGui import (  # noqa: F401
    QColor,
    QDesktopServices,
    QFont,
    QIcon,
    QTextDocument,
)
from qgis.PyQt.QtPrintSupport import QPrinter  # noqa: F401
from qgis.PyQt.QtWidgets import (  # noqa: F401
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

try:
    from qgis.PyQt.QtGui import QAction  # noqa: F401
except ImportError:  # pragma: no cover - Qt5 fallback
    from qgis.PyQt.QtWidgets import QAction  # noqa: F401


QT_HORIZONTAL = getattr(getattr(Qt, "Orientation", Qt), "Horizontal")
QT_VERTICAL = getattr(getattr(Qt, "Orientation", Qt), "Vertical")
QT_WINDOW = getattr(getattr(Qt, "WindowType", Qt), "Window")
QT_USER_ROLE = getattr(getattr(Qt, "ItemDataRole", Qt), "UserRole")

SELECTION_SELECT_ROWS = getattr(
    getattr(QAbstractItemView, "SelectionBehavior", QAbstractItemView),
    "SelectRows",
)
EDIT_NO_TRIGGERS = getattr(
    getattr(QAbstractItemView, "EditTrigger", QAbstractItemView),
    "NoEditTriggers",
)

PRINTER_HIGH_RESOLUTION = getattr(
    getattr(QPrinter, "PrinterMode", QPrinter),
    "HighResolution",
)
PRINTER_PDF_FORMAT = getattr(
    getattr(QPrinter, "OutputFormat", QPrinter),
    "PdfFormat",
)

LAYOUT_UNIT_MM = getattr(
    getattr(QgsUnitTypes, "LayoutUnit", QgsUnitTypes), "LayoutMillimeters"
)
LAYOUT_EXPORT_SUCCESS = getattr(
    getattr(QgsLayoutExporter, "ExportResult", QgsLayoutExporter),
    "Success",
)

POLICY_EXPANDING = getattr(
    getattr(QSizePolicy, "Policy", QSizePolicy), "Expanding"
)
POLICY_PREFERRED = getattr(
    getattr(QSizePolicy, "Policy", QSizePolicy), "Preferred"
)
POLICY_MINIMUM_EXPANDING = getattr(
    getattr(QSizePolicy, "Policy", QSizePolicy), "MinimumExpanding"
)
POLICY_FIXED = getattr(getattr(QSizePolicy, "Policy", QSizePolicy), "Fixed")

FRAME_NO_FRAME = getattr(getattr(QFrame, "Shape", QFrame), "NoFrame")

if hasattr(QSizePolicy, "Policy"):
    for _attr in dir(QSizePolicy.Policy):
        if not _attr.startswith("_") and not hasattr(QSizePolicy, _attr):
            setattr(QSizePolicy, _attr, getattr(QSizePolicy.Policy, _attr))

if hasattr(QFrame, "Shape"):
    for _attr in dir(QFrame.Shape):
        if not _attr.startswith("_") and not hasattr(QFrame, _attr):
            setattr(QFrame, _attr, getattr(QFrame.Shape, _attr))


def dialog_exec(dialog: QDialog) -> int:
    if hasattr(dialog, "exec"):
        return dialog.exec()
    return dialog.exec_()


def header_stretch_mode():
    resize_mode = getattr(QHeaderView, "ResizeMode", QHeaderView)
    return resize_mode.Stretch
