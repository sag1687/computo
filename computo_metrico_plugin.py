import os

from .dialog import ComputoMetricoDialog
from .qt_compat import QAction, QIcon


class ComputoMetricoPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dialog = None
        self.plugin_dir = os.path.dirname(__file__)
        self.menu_name = "Computo Metrico GIS"

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, "assets", "icon.svg")
        self.action = QAction(QIcon(icon_path), self.menu_name, self.iface.mainWindow())
        self.action.triggered.connect(self.run)

        self.iface.addPluginToMenu(self.menu_name, self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        if self.action:
            self.iface.removePluginMenu(self.menu_name, self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action = None
        if self.dialog:
            self.dialog.close()
            self.dialog.deleteLater()
            self.dialog = None

    def run(self, checked=False):
        if self.dialog is None:
            self.dialog = ComputoMetricoDialog(self.iface, self.plugin_dir)
        self.dialog.refresh_all()
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
