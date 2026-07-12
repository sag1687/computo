import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from qgis.core import (
    QgsApplication,
    QgsLayoutExporter,
    QgsLayoutItemMap,
    QgsLayoutItemPicture,
    QgsLayoutItemScaleBar,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsMapLayerType,
    QgsPrintLayout,
    QgsProject,
    QgsRectangle,
)

from .accounting import build_accounting_html, build_category_summary, export_accounting_xlsx
from .bundled_datasets import BUNDLED_DATASETS
from .computation import LayerComputationEngine, MappingConfig, guess_field_name
from .db import DatabaseManager
from .models import ReportProfile, ReportReference
from .price_parser import (
    PriceListFormatError,
    format_expectations_html,
    load_price_list,
)
from .regional_catalog import ensure_manual_template, load_regional_catalog
from .project_template import TemplateProjectBuilder
from .regional_sources import RegionalPriceListService
from .qt_compat import (
    QApplication,
    QCheckBox,
    QColor,
    QComboBox,
    QDateTime,
    QDesktopServices,
    EDIT_NO_TRIGGERS,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRectF,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QT_HORIZONTAL,
    QT_USER_ROLE,
    QT_VERTICAL,
    QT_WINDOW,
    POLICY_EXPANDING,
    POLICY_PREFERRED,
    POLICY_MINIMUM_EXPANDING,
    POLICY_FIXED,
    FRAME_NO_FRAME,
    LAYOUT_EXPORT_SUCCESS,
    LAYOUT_UNIT_MM,
    SELECTION_SELECT_ROWS,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QUrl,
    QVBoxLayout,
    QWidget,
    header_stretch_mode,
)
from .reporting import build_report_html, export_pdf, export_xlsx


PLUGIN_NAME = "Computo Metrico GIS"
PLUGIN_VERSION = "0.2.1"


class ComputoMetricoDialog(QWidget):
    def __init__(self, iface, plugin_dir: str, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.plugin_dir = plugin_dir
        self.data_dir = os.path.join(QgsApplication.qgisSettingsDirPath(), "computo_metrico_gis")
        self.export_dir = os.path.join(self.data_dir, "exports")
        self.download_dir = os.path.join(self.data_dir, "downloads")
        os.makedirs(self.export_dir, exist_ok=True)
        os.makedirs(self.download_dir, exist_ok=True)

        self.db_path = os.path.join(self.data_dir, "computo_metrico.sqlite")
        self.db = DatabaseManager(self.db_path)
        self.db.initialize()
        self.template_builder = TemplateProjectBuilder(plugin_dir)
        self.regional_service = RegionalPriceListService()
        self.last_downloaded_path = ""
        self.last_downloaded_url = ""
        self.last_downloaded_page_url = ""
        self.bundled_datasets = BUNDLED_DATASETS
        self.regional_catalog_entries = []
        self.report_profile = ReportProfile()

        self.setWindowTitle(PLUGIN_NAME)
        self.setWindowFlag(QT_WINDOW, True)
        self.resize(1540, 980)
        self.setMinimumSize(1320, 860)

        self._build_ui()
        self._apply_styles()
        self.refresh_all()
        self.log(f"Database inizializzato in {self.db_path}")

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        title = QLabel(
            f"<h2 style='margin:0;color:#eef6ff'>{PLUGIN_NAME}</h2>"
            "<div style='color:#9eb6d5'>Computo metrico estimativo da QGIS con prezziari e report.</div>"
        )
        title.setWordWrap(True)
        root_layout.addWidget(title)

        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        root_layout.addWidget(self.tabs, 1)

        self.info_tab = self._build_info_tab()
        self.price_tab = self._build_price_tab()
        self.measurement_tab = self._build_measurement_tab()
        self.report_tab = self._build_report_tab()
        self.accounting_tab = self._build_accounting_tab()
        self.help_tab = self._build_help_tab()

        self.tabs.addTab(self.info_tab, "Info")
        self.tabs.addTab(self.price_tab, "Prezziari")
        self.tabs.addTab(self.measurement_tab, "Misurazioni")
        self.tabs.addTab(self.report_tab, "Computo")
        self.tabs.addTab(self.accounting_tab, "Contabilità")
        self.tabs.addTab(self.help_tab, "Help")

        log_group = QGroupBox("Log operativo")
        log_group.setMaximumHeight(190)
        log_layout = QVBoxLayout(log_group)
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumBlockCount(500)
        self.log_output.setMinimumHeight(110)
        self.log_output.setMaximumHeight(150)
        log_layout.addWidget(self.log_output)
        root_layout.addWidget(log_group)

    def _build_info_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        actions_layout = QHBoxLayout()
        self.btn_init_db = QPushButton("Inizializza database")
        self.btn_create_template = QPushButton("Crea progetto demo")
        self.btn_refresh_context = QPushButton("Ricarica contesto")
        for button in (self.btn_init_db, self.btn_create_template, self.btn_refresh_context):
            self._configure_action_button(button, min_width=170)
        actions_layout.addWidget(self.btn_init_db)
        actions_layout.addWidget(self.btn_create_template)
        actions_layout.addWidget(self.btn_refresh_context)
        actions_layout.addStretch(1)
        layout.addLayout(actions_layout)

        status_frame = QFrame()
        status_layout = QFormLayout(status_frame)
        self.lbl_data_dir = QLabel()
        self.lbl_db_path = QLabel()
        self.lbl_active_pricelist = QLabel()
        self.lbl_active_run = QLabel()
        status_layout.addRow("Directory dati", self.lbl_data_dir)
        status_layout.addRow("Database", self.lbl_db_path)
        status_layout.addRow("Prezziario attivo", self.lbl_active_pricelist)
        status_layout.addRow("Run attivo", self.lbl_active_run)
        layout.addWidget(status_frame)

        self.info_browser = QTextBrowser()
        self.info_browser.setOpenExternalLinks(True)
        self._configure_browser(self.info_browser, min_height=520)
        layout.addWidget(self.info_browser, 1)

        self.btn_init_db.clicked.connect(self.initialize_database)
        self.btn_create_template.clicked.connect(self.create_demo_project)
        self.btn_refresh_context.clicked.connect(self.refresh_all)
        return self._wrap_scroll_tab(tab, min_width=1080)

    def _build_price_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        actions_group = QGroupBox("Azioni prezziario")
        actions_layout = QGridLayout(actions_group)
        self.btn_import_csv = QPushButton("Importa CSV")
        self.btn_import_xlsx = QPushButton("Importa XLSX / DCF")
        self.btn_download_link = QPushButton("Scarica da link")
        self.btn_add_link = QPushButton("Aggiungi link")
        self.btn_remove_link = QPushButton("Rimuovi link")
        self.btn_open_link = QPushButton("Apri link")
        for index, button in enumerate((
            self.btn_import_csv,
            self.btn_import_xlsx,
            self.btn_download_link,
            self.btn_add_link,
            self.btn_remove_link,
            self.btn_open_link,
        )):
            self._configure_action_button(button)
            actions_layout.addWidget(button, index // 3, index % 3)
        for column in range(3):
            actions_layout.setColumnStretch(column, 1)
        layout.addWidget(actions_group)

        price_sections = QTabWidget()
        sources_page = QWidget()
        sources_layout = QVBoxLayout(sources_page)
        sources_layout.setSpacing(10)
        archive_page = QWidget()
        archive_layout = QVBoxLayout(archive_page)
        archive_layout.setSpacing(10)

        catalog_group = QGroupBox("Catalogo regionale")
        catalog_layout = QVBoxLayout(catalog_group)
        catalog_actions = QGridLayout()
        self.btn_catalog_import = QPushButton("Importa dataset pronto")
        self.btn_catalog_download = QPushButton("Scarica / aggiorna")
        self.btn_catalog_open_page = QPushButton("Apri pagina ufficiale")
        self.btn_catalog_open_file = QPushButton("Apri file locale")
        self.btn_catalog_create_template = QPushButton("Crea template manuale")
        for index, button in enumerate((
            self.btn_catalog_import,
            self.btn_catalog_download,
            self.btn_catalog_open_page,
            self.btn_catalog_open_file,
            self.btn_catalog_create_template,
        )):
            self._configure_action_button(button)
            catalog_actions.addWidget(button, index // 3, index % 3)
        for column in range(3):
            catalog_actions.setColumnStretch(column, 1)
        catalog_layout.addLayout(catalog_actions)

        self.region_catalog_table = QTableWidget(0, 5)
        self.region_catalog_table.setHorizontalHeaderLabels(
            ["Regione", "Stato", "Voci", "Formato", "Azione"]
        )
        self._configure_table(self.region_catalog_table, stretch_column=0, min_height=250)
        catalog_layout.addWidget(self.region_catalog_table)

        self.region_catalog_browser = QTextBrowser()
        self.region_catalog_browser.setOpenExternalLinks(True)
        self._configure_browser(self.region_catalog_browser, min_height=190)
        catalog_layout.addWidget(self.region_catalog_browser)
        sources_layout.addWidget(catalog_group)

        active_row = QHBoxLayout()
        active_row.addWidget(QLabel("Prezziario ufficiale per regione"))
        self.official_region_combo = QComboBox()
        self.btn_download_official = QPushButton("Scarica ufficiale")
        self.btn_open_official = QPushButton("Apri portale")
        self._configure_action_button(self.btn_download_official)
        self._configure_action_button(self.btn_open_official)
        active_row.addWidget(self.official_region_combo, 1)
        active_row.addWidget(self.btn_download_official)
        active_row.addWidget(self.btn_open_official)
        sources_layout.addLayout(active_row)

        official_note = QLabel(
            "Il plugin prova a risolvere il prezziario ufficiale della regione selezionata, "
            "lo salva in una cartella locale del plugin e importa subito i formati leggibili."
        )
        official_note.setWordWrap(True)
        sources_layout.addWidget(official_note)

        bundled_group = QGroupBox("Dataset pronti inclusi")
        bundled_layout = QVBoxLayout(bundled_group)
        bundled_row = QHBoxLayout()
        self.bundled_dataset_combo = QComboBox()
        self.btn_import_bundled = QPushButton("Importa dataset incluso")
        self.btn_open_bundled_source = QPushButton("Apri sorgente aggiornamento")
        self._configure_action_button(self.btn_import_bundled)
        self._configure_action_button(self.btn_open_bundled_source)
        bundled_row.addWidget(self.bundled_dataset_combo, 1)
        bundled_row.addWidget(self.btn_import_bundled)
        bundled_row.addWidget(self.btn_open_bundled_source)
        bundled_layout.addLayout(bundled_row)
        self.bundled_info_browser = QTextBrowser()
        self.bundled_info_browser.setOpenExternalLinks(True)
        self._configure_browser(self.bundled_info_browser, min_height=135)
        bundled_layout.addWidget(self.bundled_info_browser)
        sources_layout.addWidget(bundled_group)

        progress_group = QGroupBox("Stato download")
        progress_layout = QVBoxLayout(progress_group)
        self.download_status_label = QLabel("Nessun download in corso.")
        self.download_progress = QProgressBar()
        self.download_progress.setRange(0, 100)
        self.download_progress.setValue(0)
        self.download_result_browser = QTextBrowser()
        self.download_result_browser.setOpenExternalLinks(True)
        self._configure_browser(self.download_result_browser, min_height=165)
        self.download_result_browser.setHtml(
            "<p>Nessun file scaricato.</p>"
            "<p>Qui compariranno il percorso locale, il link al file e il link alla cartella.</p>"
        )
        progress_layout.addWidget(self.download_status_label)
        progress_layout.addWidget(self.download_progress)
        progress_layout.addWidget(self.download_result_browser)
        sources_layout.addWidget(progress_group)

        active_row = QHBoxLayout()
        active_row.addWidget(QLabel("Prezziario attivo"))
        self.price_list_combo = QComboBox()
        active_row.addWidget(self.price_list_combo, 1)
        archive_layout.addLayout(active_row)

        splitter = QSplitter(QT_HORIZONTAL)

        links_group = QGroupBox("Link diretti ai prezziari")
        links_layout = QVBoxLayout(links_group)
        self.download_links_table = QTableWidget(0, 3)
        self.download_links_table.setHorizontalHeaderLabels(["Etichetta", "Regione/ente", "URL"])
        self._configure_table(self.download_links_table, stretch_column=2, min_height=240)
        links_layout.addWidget(self.download_links_table)

        format_group = QGroupBox("Formato atteso")
        format_layout = QVBoxLayout(format_group)
        self.format_browser = QTextBrowser()
        self._configure_browser(self.format_browser, min_height=240)
        self.format_browser.setHtml(format_expectations_html())
        format_layout.addWidget(self.format_browser)

        splitter.addWidget(links_group)
        splitter.addWidget(format_group)
        self._configure_splitter(splitter, [780, 500])
        archive_layout.addWidget(splitter, 1)

        items_group = QGroupBox("Voci del prezziario")
        items_layout = QVBoxLayout(items_group)
        self.price_items_table = QTableWidget(0, 5)
        self.price_items_table.setHorizontalHeaderLabels(
            ["Codice", "Descrizione", "UM", "Prezzo unitario", "Categoria"]
        )
        self._configure_table(self.price_items_table, stretch_column=1, min_height=320)
        items_layout.addWidget(self.price_items_table)
        archive_layout.addWidget(items_group, 1)

        price_sections.addTab(sources_page, "Sorgenti e download")
        price_sections.addTab(archive_page, "Archivio e voci")
        layout.addWidget(price_sections, 1)

        self.btn_import_csv.clicked.connect(self.import_csv)
        self.btn_import_xlsx.clicked.connect(self.import_xlsx)
        self.btn_catalog_import.clicked.connect(self.import_catalog_dataset)
        self.btn_catalog_download.clicked.connect(self.download_catalog_entry)
        self.btn_catalog_open_page.clicked.connect(self.open_catalog_page)
        self.btn_catalog_open_file.clicked.connect(self.open_catalog_file)
        self.btn_catalog_create_template.clicked.connect(self.create_catalog_template)
        self.btn_add_link.clicked.connect(self.add_download_link)
        self.btn_remove_link.clicked.connect(self.remove_download_link)
        self.btn_open_link.clicked.connect(self.open_download_link)
        self.btn_download_link.clicked.connect(self.download_selected_link)
        self.btn_download_official.clicked.connect(self.download_official_pricelist)
        self.btn_open_official.clicked.connect(self.open_official_source)
        self.btn_import_bundled.clicked.connect(self.import_bundled_dataset)
        self.btn_open_bundled_source.clicked.connect(self.open_bundled_source)
        self.bundled_dataset_combo.currentIndexChanged.connect(self.refresh_bundled_dataset_info)
        self.region_catalog_table.itemSelectionChanged.connect(self.refresh_catalog_details)
        self.price_list_combo.currentIndexChanged.connect(self.refresh_price_items_table)
        return self._wrap_scroll_tab(tab, min_width=1320)

    def _build_measurement_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        selector_row = QHBoxLayout()
        selector_row.addWidget(QLabel("Layer vettoriale"))
        self.layer_combo = QComboBox()
        self.btn_refresh_layers = QPushButton("Aggiorna layer")
        self.btn_auto_fields = QPushButton("Auto-rileva campi")
        self._configure_action_button(self.btn_refresh_layers, min_width=160)
        self._configure_action_button(self.btn_auto_fields, min_width=170)
        selector_row.addWidget(self.layer_combo, 1)
        selector_row.addWidget(self.btn_refresh_layers)
        selector_row.addWidget(self.btn_auto_fields)
        layout.addLayout(selector_row)

        main_splitter = QSplitter(QT_HORIZONTAL)

        mapping_group = QGroupBox("Mapping campi layer")
        mapping_form = QFormLayout(mapping_group)
        self.code_field_combo = QComboBox()
        self.description_field_combo = QComboBox()
        self.category_field_combo = QComboBox()
        self.quantity_field_combo = QComboBox()
        self.coefficient_field_combo = QComboBox()
        self.unit_override_field_combo = QComboBox()
        self.width_field_combo = QComboBox()
        self.height_field_combo = QComboBox()
        self.thickness_field_combo = QComboBox()
        self.pieces_field_combo = QComboBox()
        self.notes_field_combo = QComboBox()
        mapping_form.addRow("Codice voce", self.code_field_combo)
        mapping_form.addRow("Descrizione", self.description_field_combo)
        mapping_form.addRow("Categoria", self.category_field_combo)
        mapping_form.addRow("Quantità manuale", self.quantity_field_combo)
        mapping_form.addRow("Coefficiente", self.coefficient_field_combo)
        mapping_form.addRow("UM override", self.unit_override_field_combo)
        mapping_form.addRow("Larghezza m", self.width_field_combo)
        mapping_form.addRow("Altezza m", self.height_field_combo)
        mapping_form.addRow("Spessore m", self.thickness_field_combo)
        mapping_form.addRow("Pezzi", self.pieces_field_combo)
        mapping_form.addRow("Note", self.notes_field_combo)

        help_group = QGroupBox("Regole operative")
        help_layout = QVBoxLayout(help_group)
        self.measurement_help_browser = QTextBrowser()
        self._configure_browser(self.measurement_help_browser, min_height=300)
        self.measurement_help_browser.setHtml(
            "<h3>Layer consigliato</h3>"
            "<p>Il campo <code>item_code</code> &egrave; quello essenziale. "
            "Gli altri campi sono facoltativi ma utili per controllare il computo.</p>"
            "<ul>"
            "<li><b>mq / ha</b>: usa l'area della geometria.</li>"
            "<li><b>mq da linea</b>: se imposti <code>larghezza_m</code>, usa lunghezza x larghezza.</li>"
            "<li><b>ml / km</b>: usa la lunghezza, o il perimetro se il layer &egrave; poligonale.</li>"
            "<li><b>cad</b>: conta una feature = una quantità.</li>"
            "<li><b>mc</b>: usa area x spessore oppure lunghezza x larghezza x altezza/spessore.</li>"
            "</ul>"
        )
        help_layout.addWidget(self.measurement_help_browser)

        main_splitter.addWidget(mapping_group)
        main_splitter.addWidget(help_group)
        self._configure_splitter(main_splitter, [540, 760])
        layout.addWidget(main_splitter)

        execute_row = QHBoxLayout()
        self.btn_compute = QPushButton("Calcola computo dal layer")
        self._configure_action_button(self.btn_compute, min_width=260)
        execute_row.addWidget(self.btn_compute)
        execute_row.addStretch(1)
        layout.addLayout(execute_row)

        feedback_group = QGroupBox("Esito e controlli")
        feedback_layout = QVBoxLayout(feedback_group)
        self.measurement_feedback = QTextBrowser()
        self._configure_browser(self.measurement_feedback, min_height=220)
        feedback_layout.addWidget(self.measurement_feedback)
        layout.addWidget(feedback_group, 1)

        self.btn_refresh_layers.clicked.connect(self.refresh_layers)
        self.btn_auto_fields.clicked.connect(self.auto_detect_fields)
        self.btn_compute.clicked.connect(self.run_computation)
        self.layer_combo.currentIndexChanged.connect(self.populate_field_combos)
        return self._wrap_scroll_tab(tab, min_width=1200)

    def _build_report_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        report_sections = QTabWidget()
        profile_page = QWidget()
        profile_page_layout = QVBoxLayout(profile_page)
        profile_page_layout.setSpacing(10)
        results_page = QWidget()
        results_layout = QVBoxLayout(results_page)
        results_layout.setSpacing(10)

        profile_group = QGroupBox("Intestazione e mappa del report")
        profile_layout = QVBoxLayout(profile_group)

        logo_row = QHBoxLayout()
        logo_row.addWidget(QLabel("Logo"))
        self.report_logo_path = QLineEdit()
        self.report_logo_path.setPlaceholderText("Percorso file immagine")
        self.btn_choose_logo = QPushButton("Seleziona logo")
        self.btn_clear_logo = QPushButton("Pulisci")
        logo_row.addWidget(self.report_logo_path, 1)
        logo_row.addWidget(self.btn_choose_logo)
        logo_row.addWidget(self.btn_clear_logo)
        profile_layout.addLayout(logo_row)

        header_form = QFormLayout()
        self.report_title_edit = QLineEdit()
        self.report_subtitle_edit = QLineEdit()
        self.report_organization_edit = QLineEdit()
        self.report_map_title_edit = QLineEdit()
        self.report_map_title_edit.setPlaceholderText("Mappa di inquadramento")
        header_form.addRow("Titolo", self.report_title_edit)
        header_form.addRow("Sottotitolo", self.report_subtitle_edit)
        header_form.addRow("Organizzazione", self.report_organization_edit)
        header_form.addRow("Titolo mappa", self.report_map_title_edit)
        profile_layout.addLayout(header_form)

        self.report_include_map_checkbox = QCheckBox("Includi la mappa corrente nel PDF")
        self.report_include_map_checkbox.setChecked(True)
        profile_layout.addWidget(self.report_include_map_checkbox)

        self.report_footer_edit = QPlainTextEdit()
        self.report_footer_edit.setPlaceholderText("Piè di pagina, note finali, riferimenti normativi sintetici.")
        self.report_footer_edit.setMinimumHeight(100)
        self.report_footer_edit.setMaximumHeight(150)
        profile_layout.addWidget(QLabel("Piè di pagina / note finali"))
        profile_layout.addWidget(self.report_footer_edit)

        refs_actions = QHBoxLayout()
        refs_actions.addWidget(QLabel("Riferimenti aggiuntivi"))
        self.btn_add_reference = QPushButton("Add +")
        self.btn_remove_reference = QPushButton("Rimuovi riferimento")
        refs_actions.addWidget(self.btn_add_reference)
        refs_actions.addWidget(self.btn_remove_reference)
        refs_actions.addStretch(1)
        profile_layout.addLayout(refs_actions)

        self.report_refs_table = QTableWidget(0, 2)
        self.report_refs_table.setHorizontalHeaderLabels(["Etichetta", "Valore"])
        self._configure_table(self.report_refs_table, stretch_column=1, min_height=180)
        profile_layout.addWidget(self.report_refs_table)

        self.btn_save_report_profile = QPushButton("Salva profilo report")
        self._configure_action_button(self.btn_save_report_profile, min_width=220)
        profile_layout.addWidget(self.btn_save_report_profile)
        profile_page_layout.addWidget(profile_group)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Run di computo"))
        self.run_combo = QComboBox()
        self.btn_refresh_runs = QPushButton("Aggiorna run")
        self.btn_export_pdf = QPushButton("Esporta PDF")
        self.btn_export_xlsx = QPushButton("Esporta XLSX")
        for button in (self.btn_refresh_runs, self.btn_export_pdf, self.btn_export_xlsx):
            self._configure_action_button(button, min_width=150)
        top_row.addWidget(self.run_combo, 1)
        top_row.addWidget(self.btn_refresh_runs)
        top_row.addWidget(self.btn_export_pdf)
        top_row.addWidget(self.btn_export_xlsx)
        results_layout.addLayout(top_row)

        splitter = QSplitter(QT_VERTICAL)

        summary_group = QGroupBox("Riepilogo computo")
        summary_layout = QVBoxLayout(summary_group)
        self.summary_table = QTableWidget(0, 6)
        self.summary_table.setHorizontalHeaderLabels(
            ["Codice", "Descrizione", "UM", "Quantità", "Prezzo unitario", "Totale"]
        )
        self._configure_table(self.summary_table, stretch_column=1, min_height=280)
        summary_layout.addWidget(self.summary_table)

        detail_group = QGroupBox("Dettaglio elementi")
        detail_layout = QVBoxLayout(detail_group)
        self.detail_table = QTableWidget(0, 10)
        self.detail_table.setHorizontalHeaderLabels(
            ["Layer", "Feature ID", "Geometria", "Codice", "Descrizione", "UM", "Quantità", "P. Unit (€)", "Totale (€)", "Regola e Note calcolo"]
        )
        self._configure_table(self.detail_table, stretch_column=9, min_height=300)
        detail_layout.addWidget(self.detail_table)

        splitter.addWidget(summary_group)
        splitter.addWidget(detail_group)
        self._configure_splitter(splitter, [360, 420])
        results_layout.addWidget(splitter, 1)

        report_sections.addTab(profile_page, "Profilo documento")
        report_sections.addTab(results_page, "Riepilogo e dettaglio")
        layout.addWidget(report_sections, 1)

        self.btn_refresh_runs.clicked.connect(self.refresh_runs)
        self.run_combo.currentIndexChanged.connect(self.refresh_report_tables)
        self.btn_export_pdf.clicked.connect(self.export_current_pdf)
        self.btn_export_xlsx.clicked.connect(self.export_current_xlsx)
        self.btn_choose_logo.clicked.connect(self.choose_report_logo)
        self.btn_clear_logo.clicked.connect(self.clear_report_logo)
        self.btn_add_reference.clicked.connect(self.add_report_reference)
        self.btn_remove_reference.clicked.connect(self.remove_report_reference)
        self.btn_save_report_profile.clicked.connect(self.save_report_profile)
        return self._wrap_scroll_tab(tab, min_width=1280)

    def _build_accounting_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Run per contabilità"))
        self.accounting_run_combo = QComboBox()
        self.btn_refresh_accounting = QPushButton("Aggiorna contabilità")
        self.btn_export_accounting_pdf = QPushButton("PDF contabilità")
        self.btn_export_accounting_xlsx = QPushButton("XLSX contabilità")
        for button in (
            self.btn_refresh_accounting,
            self.btn_export_accounting_pdf,
            self.btn_export_accounting_xlsx,
        ):
            self._configure_action_button(button, min_width=170)
        top_row.addWidget(self.accounting_run_combo, 1)
        top_row.addWidget(self.btn_refresh_accounting)
        top_row.addWidget(self.btn_export_accounting_pdf)
        top_row.addWidget(self.btn_export_accounting_xlsx)
        layout.addLayout(top_row)

        sal_group = QGroupBox("Stato avanzamento lavori")
        sal_layout = QVBoxLayout(sal_group)
        sal_form = QFormLayout()
        self.sal_number_edit = QLineEdit("1")
        self.sal_date_edit = QLineEdit(QDateTime.currentDateTime().toString("yyyy-MM-dd"))
        self.sal_security_costs_edit = QLineEdit("0")
        self.sal_retention_percent_edit = QLineEdit("0")
        self.sal_vat_percent_edit = QLineEdit("22")
        self.sal_previous_paid_edit = QLineEdit("0")
        self.sal_notes_edit = QPlainTextEdit()
        self.sal_notes_edit.setMinimumHeight(95)
        self.sal_notes_edit.setMaximumHeight(140)
        sal_form.addRow("Numero SAL", self.sal_number_edit)
        sal_form.addRow("Data SAL", self.sal_date_edit)
        sal_form.addRow("Oneri sicurezza", self.sal_security_costs_edit)
        sal_form.addRow("Ritenuta %", self.sal_retention_percent_edit)
        sal_form.addRow("IVA %", self.sal_vat_percent_edit)
        sal_form.addRow("Già pagato / certificato", self.sal_previous_paid_edit)
        sal_layout.addLayout(sal_form)
        sal_layout.addWidget(QLabel("Note SAL"))
        sal_layout.addWidget(self.sal_notes_edit)
        sal_actions = QHBoxLayout()
        self.btn_generate_sal = QPushButton("Genera SAL")
        self.btn_load_last_sal = QPushButton("Carica ultimo SAL")
        self._configure_action_button(self.btn_generate_sal)
        self._configure_action_button(self.btn_load_last_sal)
        sal_actions.addWidget(self.btn_generate_sal)
        sal_actions.addWidget(self.btn_load_last_sal)
        sal_actions.addStretch(1)
        sal_layout.addLayout(sal_actions)
        self.accounting_certificate_browser = QTextBrowser()
        self.accounting_certificate_browser.setOpenExternalLinks(True)
        self._configure_browser(self.accounting_certificate_browser, min_height=180)
        sal_layout.addWidget(self.accounting_certificate_browser)
        layout.addWidget(sal_group)

        accounting_splitter = QSplitter(QT_VERTICAL)

        docs_tabs = QTabWidget()
        self.accounting_libretto_table = QTableWidget(0, 9)
        self.accounting_libretto_table.setHorizontalHeaderLabels(
            ["Layer", "FID", "Codice", "Descrizione", "UM", "Quantità", "Prezzo", "Importo", "Note calcolo"]
        )
        self._configure_table(self.accounting_libretto_table, stretch_column=8, min_height=300)
        libretto_page = QWidget()
        libretto_layout = QVBoxLayout(libretto_page)
        libretto_layout.addWidget(self.accounting_libretto_table)
        docs_tabs.addTab(libretto_page, "Libretto")

        self.accounting_registro_table = QTableWidget(0, 7)
        self.accounting_registro_table.setHorizontalHeaderLabels(
            ["Codice", "Descrizione", "Categoria", "UM", "Quantità", "Prezzo", "Importo"]
        )
        self._configure_table(self.accounting_registro_table, stretch_column=1, min_height=300)
        registro_page = QWidget()
        registro_layout = QVBoxLayout(registro_page)
        registro_layout.addWidget(self.accounting_registro_table)
        docs_tabs.addTab(registro_page, "Registro")

        self.accounting_sommario_table = QTableWidget(0, 2)
        self.accounting_sommario_table.setHorizontalHeaderLabels(["Categoria", "Importo"])
        self._configure_table(self.accounting_sommario_table, stretch_column=0, min_height=260)
        sommario_page = QWidget()
        sommario_layout = QVBoxLayout(sommario_page)
        sommario_layout.addWidget(self.accounting_sommario_table)
        docs_tabs.addTab(sommario_page, "Sommario")

        self.accounting_sal_table = QTableWidget(0, 7)
        self.accounting_sal_table.setHorizontalHeaderLabels(
            ["ID", "SAL", "Data", "Lordo", "Già pagato", "Da liquidare", "Totale certificato"]
        )
        self._configure_table(self.accounting_sal_table, stretch_column=2, min_height=260)
        sal_list_page = QWidget()
        sal_list_layout = QVBoxLayout(sal_list_page)
        sal_list_layout.addWidget(self.accounting_sal_table)
        docs_tabs.addTab(sal_list_page, "SAL emessi")

        accounting_splitter.addWidget(docs_tabs)

        journal_group = QGroupBox("Giornale lavori")
        journal_layout = QVBoxLayout(journal_group)
        journal_form = QFormLayout()
        self.journal_date_edit = QLineEdit(QDateTime.currentDateTime().toString("yyyy-MM-dd"))
        self.journal_title_edit = QLineEdit()
        self.journal_weather_edit = QLineEdit()
        self.journal_workers_edit = QLineEdit()
        journal_form.addRow("Data", self.journal_date_edit)
        journal_form.addRow("Titolo", self.journal_title_edit)
        journal_form.addRow("Meteo", self.journal_weather_edit)
        journal_form.addRow("Maestranze", self.journal_workers_edit)
        journal_layout.addLayout(journal_form)
        self.journal_description_edit = QPlainTextEdit()
        self.journal_description_edit.setMinimumHeight(110)
        self.journal_description_edit.setMaximumHeight(170)
        journal_layout.addWidget(QLabel("Descrizione"))
        journal_layout.addWidget(self.journal_description_edit)
        journal_actions = QHBoxLayout()
        self.btn_add_journal_entry = QPushButton("Aggiungi voce giornale")
        self.btn_delete_journal_entry = QPushButton("Rimuovi voce")
        self._configure_action_button(self.btn_add_journal_entry)
        self._configure_action_button(self.btn_delete_journal_entry)
        journal_actions.addWidget(self.btn_add_journal_entry)
        journal_actions.addWidget(self.btn_delete_journal_entry)
        journal_actions.addStretch(1)
        journal_layout.addLayout(journal_actions)
        self.accounting_journal_table = QTableWidget(0, 5)
        self.accounting_journal_table.setHorizontalHeaderLabels(
            ["Data", "Titolo", "Meteo", "Maestranze", "Descrizione"]
        )
        self._configure_table(self.accounting_journal_table, stretch_column=4, min_height=260)
        journal_layout.addWidget(self.accounting_journal_table)
        accounting_splitter.addWidget(journal_group)
        self._configure_splitter(accounting_splitter, [460, 300])
        layout.addWidget(accounting_splitter, 1)

        self.btn_refresh_accounting.clicked.connect(self.refresh_accounting_tab)
        self.accounting_run_combo.currentIndexChanged.connect(self.refresh_accounting_tab)
        self.btn_generate_sal.clicked.connect(self.generate_sal_document)
        self.btn_load_last_sal.clicked.connect(self.load_last_sal_document)
        self.btn_export_accounting_pdf.clicked.connect(self.export_accounting_pdf)
        self.btn_export_accounting_xlsx.clicked.connect(self.export_accounting_workbook)
        self.btn_add_journal_entry.clicked.connect(self.add_journal_entry)
        self.btn_delete_journal_entry.clicked.connect(self.delete_journal_entry)
        self.accounting_sal_table.itemSelectionChanged.connect(self.load_selected_sal_into_form)
        return self._wrap_scroll_tab(tab, min_width=1320)

    def _build_help_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.help_browser = QTextBrowser()
        self.help_browser.setOpenExternalLinks(True)
        self._configure_browser(self.help_browser, min_height=620)
        layout.addWidget(self.help_browser)
        return self._wrap_scroll_tab(tab, min_width=1080)

    def _wrap_scroll_tab(self, content: QWidget, min_width: int = 1120):
        content.setMinimumWidth(min_width)
        content.setSizePolicy(POLICY_EXPANDING, POLICY_PREFERRED)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(FRAME_NO_FRAME)
        scroll.setWidget(content)
        return scroll

    def _configure_action_button(self, button: QPushButton, min_width: int = 180):
        button.setMinimumWidth(min_width)
        button.setMinimumHeight(38)
        button.setSizePolicy(POLICY_MINIMUM_EXPANDING, POLICY_FIXED)

    def _configure_browser(self, browser: QTextBrowser, min_height: int = 140):
        browser.setMinimumHeight(min_height)
        browser.setSizePolicy(POLICY_EXPANDING, POLICY_MINIMUM_EXPANDING)

    def _configure_table(self, table: QTableWidget, stretch_column: int | None = None, min_height: int = 220):
        table.setSelectionBehavior(SELECTION_SELECT_ROWS)
        table.setEditTriggers(EDIT_NO_TRIGGERS)
        table.setAlternatingRowColors(True)
        table.setMinimumHeight(min_height)
        table.setSizePolicy(POLICY_EXPANDING, POLICY_EXPANDING)
        table.verticalHeader().setDefaultSectionSize(28)
        table.setProperty("stretch_column", -1 if stretch_column is None else stretch_column)
        if stretch_column is not None:
            table.horizontalHeader().setSectionResizeMode(stretch_column, header_stretch_mode())

    def _configure_splitter(self, splitter: QSplitter, sizes: list[int]):
        splitter.setChildrenCollapsible(False)
        splitter.setOpaqueResize(False)
        splitter.setHandleWidth(10)
        splitter.setSizes(sizes)

    def _apply_styles(self):
        self.setStyleSheet(
            """
            QWidget {
                font-size: 12px;
                color: #e8eef8;
                background: #08111f;
            }
            QLabel {
                color: #dce7f7;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollArea > QWidget > QWidget {
                background: #08111f;
            }
            QTabWidget::pane {
                border: 1px solid #20334d;
                border-radius: 8px;
                background: #0b1728;
            }
            QTabBar::tab {
                background: #0d1b2f;
                color: #a9bdd6;
                border: 1px solid #20334d;
                border-bottom: none;
                padding: 8px 14px;
                margin-right: 4px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
            QTabBar::tab:selected {
                background: #10233d;
                color: #eef6ff;
                font-weight: 600;
            }
            QGroupBox {
                border: 1px solid #20334d;
                border-radius: 10px;
                margin-top: 10px;
                padding: 14px 12px 12px 12px;
                font-weight: 600;
                background: #0e1a2d;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
                color: #cfe0f8;
            }
            QPushButton {
                background: #1b3a61;
                color: #f3f8ff;
                border: 1px solid #345786;
                border-radius: 8px;
                padding: 9px 12px;
                font-weight: 600;
                min-height: 20px;
            }
            QPushButton:hover {
                background: #244b7a;
            }
            QPushButton:pressed {
                background: #15304f;
            }
            QPushButton:disabled {
                background: #101a28;
                color: #6f83a0;
                border: 1px solid #23354d;
            }
            QComboBox, QLineEdit, QHeaderView::section {
                background: #10233d;
                color: #eef6ff;
                border: 1px solid #294668;
            }
            QComboBox, QLineEdit {
                padding: 7px 9px;
                border-radius: 6px;
                min-height: 22px;
            }
            QComboBox QAbstractItemView {
                background: #0e1c30;
                color: #eef6ff;
                selection-background-color: #244b7a;
            }
            QHeaderView::section {
                padding: 7px 6px;
                font-weight: 600;
            }
            QTableWidget {
                gridline-color: #223652;
                background: #0c1627;
                alternate-background-color: #0f1d33;
                color: #edf4ff;
                selection-background-color: #1b3a61;
                border: 1px solid #20334d;
                border-radius: 8px;
            }
            QPlainTextEdit, QTextBrowser {
                border: 1px solid #20334d;
                border-radius: 8px;
                background: #0c1627;
                color: #ebf3ff;
                selection-background-color: #244b7a;
                padding: 6px;
            }
            QProgressBar {
                background: #0c1627;
                color: #f6fbff;
                border: 1px solid #2a466b;
                border-radius: 7px;
                text-align: center;
                min-height: 20px;
                font-weight: 600;
            }
            QProgressBar::chunk {
                background: #2f6db0;
                border-radius: 6px;
            }
            QMessageBox, QInputDialog, QFileDialog {
                background: #0b1728;
                color: #eef6ff;
            }
            QMessageBox QLabel, QInputDialog QLabel {
                min-width: 420px;
                color: #eef6ff;
            }
            QMessageBox QPushButton, QInputDialog QPushButton {
                min-width: 120px;
            }
            """
        )

    def log(self, message: str):
        timestamp = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
        self.log_output.appendPlainText(f"[{timestamp}] {message}")

    def initialize_database(self):
        self.db.initialize()
        self.refresh_all()
        QMessageBox.information(self, PLUGIN_NAME, "Database SQLite inizializzato correttamente.")
        self.log("Database re-inizializzato su richiesta.")

    def refresh_all(self):
        self.lbl_data_dir.setText(self.data_dir)
        self.lbl_db_path.setText(self.db_path)
        self.refresh_download_links()
        self.refresh_official_regions()
        self.refresh_regional_catalog()
        self.refresh_bundled_datasets()
        self.refresh_price_lists()
        self.refresh_layers()
        self.refresh_runs()
        self.load_report_profile()
        self.refresh_help_tab()
        self.refresh_info_tab()

    def refresh_help_tab(self):
        self.help_browser.setHtml(self._load_doc_html("help_it.html"))

    def refresh_info_tab(self):
        price_lists_count = len(self.db.list_price_lists())
        runs_count = len(self.db.list_runs())
        active_price = self.price_list_combo.currentText() or "Nessuno"
        active_run = self.run_combo.currentText() or "Nessuno"
        self.lbl_active_pricelist.setText(active_price)
        self.lbl_active_run.setText(active_run)

        info_html = self._load_doc_html("info_it.html")
        info_html = info_html.replace("__PRICE_LISTS__", str(price_lists_count))
        info_html = info_html.replace("__RUNS__", str(runs_count))
        self.info_browser.setHtml(info_html)

    def _load_doc_html(self, file_name: str) -> str:
        path = os.path.join(self.plugin_dir, "docs", file_name)
        html = Path(path).read_text(encoding="utf-8")
        replacements = {
            "__VERSION__": PLUGIN_VERSION,
            "__DATA_DIR__": self.data_dir,
            "__DB_PATH__": self.db_path,
            "__FORMAT_HELP__": format_expectations_html(),
        }
        for key, value in replacements.items():
            html = html.replace(key, value)
        return html

    def refresh_price_lists(self, selected_id: int | None = None):
        records = self.db.list_price_lists()
        active_id = selected_id or self._active_setting_int("active_price_list_id")
        self.price_list_combo.blockSignals(True)
        self.price_list_combo.clear()

        current_index = -1
        for index, record in enumerate(records):
            label = f"{record['name']} ({record['items_count']} voci)"
            self.price_list_combo.addItem(label, record["id"])
            if active_id and record["id"] == active_id:
                current_index = index

        if current_index >= 0:
            self.price_list_combo.setCurrentIndex(current_index)
        elif records:
            self.price_list_combo.setCurrentIndex(0)
            self.db.set_setting("active_price_list_id", self.price_list_combo.currentData())

        self.price_list_combo.blockSignals(False)
        self.refresh_price_items_table()
        self.refresh_info_tab()

    def refresh_official_regions(self):
        current = self.official_region_combo.currentData()
        self.official_region_combo.blockSignals(True)
        self.official_region_combo.clear()
        for source in self.regional_service.list_sources():
            self.official_region_combo.addItem(source.name, source.key)
        if current:
            index = self.official_region_combo.findData(current)
            if index >= 0:
                self.official_region_combo.setCurrentIndex(index)
        self.official_region_combo.blockSignals(False)

    def refresh_regional_catalog(self):
        current_key = self.current_catalog_key()
        self.regional_catalog_entries = load_regional_catalog(
            self.plugin_dir,
            self.download_dir,
        )
        self.region_catalog_table.setRowCount(len(self.regional_catalog_entries))

        selected_row = 0
        for row_index, entry in enumerate(self.regional_catalog_entries):
            if current_key and entry.key == current_key:
                selected_row = row_index
            values = [
                entry.name,
                entry.status_label,
                str(entry.item_count) if entry.item_count else "-",
                entry.format or "-",
                entry.action_hint,
            ]
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column_index == 0:
                    item.setData(QT_USER_ROLE, entry.key)
                self.region_catalog_table.setItem(row_index, column_index, item)

        self.region_catalog_table.resizeColumnsToContents()
        self.region_catalog_table.horizontalHeader().setSectionResizeMode(0, header_stretch_mode())
        if self.regional_catalog_entries:
            self.region_catalog_table.selectRow(selected_row)
        self.refresh_catalog_details()

    def current_catalog_key(self) -> str:
        row = self.region_catalog_table.currentRow()
        if row < 0:
            return ""
        item = self.region_catalog_table.item(row, 0)
        return str(item.data(QT_USER_ROLE) or "") if item else ""

    def current_catalog_entry(self):
        key = self.current_catalog_key()
        if not key:
            return None
        for entry in self.regional_catalog_entries:
            if entry.key == key:
                return entry
        return None

    def refresh_catalog_details(self):
        entry = self.current_catalog_entry()
        if not entry:
            self.region_catalog_browser.setHtml("<p>Nessuna regione selezionata.</p>")
            return

        local_dataset_line = ""
        if entry.local_dataset:
            dataset_url = QUrl.fromLocalFile(entry.local_dataset).toString()
            local_dataset_line = (
                f'<p><b>Dataset locale pronto:</b> <a href="{dataset_url}">{entry.local_dataset}</a></p>'
            )

        local_download_line = ""
        if entry.local_download:
            local_download_url = QUrl.fromLocalFile(entry.local_download).toString()
            local_download_line = (
                f'<p><b>Ultimo file scaricato:</b> <a href="{local_download_url}">{entry.local_download}</a></p>'
            )

        manual_dir = str(Path(self.data_dir) / "templates_regionali")
        manual_dir_url = QUrl.fromLocalFile(manual_dir).toString()
        self.region_catalog_browser.setHtml(
            f"""
            <h3 style="margin-bottom:4px">{entry.name}</h3>
            <p><b>Stato:</b> <span style="color:{entry.status_color}">{entry.status_label}</span></p>
            <p><b>Pagina ufficiale:</b> <a href="{entry.source_page or entry.homepage}">{entry.source_page or entry.homepage}</a></p>
            <p><b>Link aggiornamento:</b> {'<a href="' + entry.update_url + '">' + entry.update_url + '</a>' if entry.update_url else 'non disponibile'}</p>
            {local_dataset_line}
            {local_download_line}
            <p><b>Cartella template manuali:</b> <a href="{manual_dir_url}">{manual_dir}</a></p>
            <p><b>Note:</b> {entry.notes or 'Portale regionale censito. Se il dataset non è pronto, usa il download ufficiale o il template manuale.'}</p>
            """
        )

    def refresh_bundled_datasets(self):
        current = self.bundled_dataset_combo.currentData()
        self.bundled_dataset_combo.blockSignals(True)
        self.bundled_dataset_combo.clear()
        for dataset in self.bundled_datasets:
            self.bundled_dataset_combo.addItem(dataset.label, dataset.key)
        if current:
            index = self.bundled_dataset_combo.findData(current)
            if index >= 0:
                self.bundled_dataset_combo.setCurrentIndex(index)
        self.bundled_dataset_combo.blockSignals(False)
        self.refresh_bundled_dataset_info()

    def refresh_bundled_dataset_info(self):
        dataset = self.current_bundled_dataset()
        if not dataset:
            self.bundled_info_browser.setHtml("<p>Nessun dataset incluso.</p>")
            return
        local_path = str(Path(self.plugin_dir) / dataset.relative_path)
        file_url = QUrl.fromLocalFile(local_path).toString()
        self.bundled_info_browser.setHtml(
            f"""
            <p><b>Regione:</b> {dataset.region}</p>
            <p><b>File locale incluso:</b> <a href="{file_url}">{local_path}</a></p>
            <p><b>Pagina ufficiale:</b> <a href="{dataset.source_page}">{dataset.source_page}</a></p>
            <p><b>Link aggiornamento:</b> <a href="{dataset.update_url}">{dataset.update_url}</a></p>
            <p>{dataset.notes}</p>
            """
        )

    def refresh_price_items_table(self):
        price_list_id = self.current_price_list_id()
        rows = self.db.list_price_items(price_list_id) if price_list_id else []
        self._populate_table(
            self.price_items_table,
            rows,
            ["code", "description", "unit", "unit_price", "category"],
        )

    def refresh_download_links(self):
        rows = self.db.list_download_links()
        self.download_links_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, key in enumerate(("label", "region", "url")):
                item = QTableWidgetItem(str(row.get(key) or ""))
                item.setData(QT_USER_ROLE, row["id"])
                self.download_links_table.setItem(row_index, column_index, item)
        self.download_links_table.resizeColumnsToContents()
        self.download_links_table.horizontalHeader().setSectionResizeMode(2, header_stretch_mode())

    def refresh_layers(self):
        vector_layers = [
            layer
            for layer in QgsProject.instance().mapLayers().values()
            if layer.type() == QgsMapLayerType.VectorLayer
        ]
        current_id = self.layer_combo.currentData()
        self.layer_combo.blockSignals(True)
        self.layer_combo.clear()
        for layer in vector_layers:
            self.layer_combo.addItem(f"{layer.name()} [{layer.crs().authid()}]", layer.id())
        if current_id:
            for index in range(self.layer_combo.count()):
                if self.layer_combo.itemData(index) == current_id:
                    self.layer_combo.setCurrentIndex(index)
                    break
        self.layer_combo.blockSignals(False)
        self.populate_field_combos()

    def populate_field_combos(self):
        layer = self.current_layer()
        combos = (
            self.code_field_combo,
            self.description_field_combo,
            self.category_field_combo,
            self.quantity_field_combo,
            self.coefficient_field_combo,
            self.unit_override_field_combo,
            self.width_field_combo,
            self.height_field_combo,
            self.thickness_field_combo,
            self.pieces_field_combo,
            self.notes_field_combo,
        )
        for combo in combos:
            combo.clear()
            combo.addItem("(nessuno)", "")

        if not layer:
            return

        field_names = [field.name() for field in layer.fields()]
        for combo in combos:
            for field_name in field_names:
                combo.addItem(field_name, field_name)

        self.auto_detect_fields()

    def auto_detect_fields(self):
        layer = self.current_layer()
        if not layer:
            return
        mapping = {
            self.code_field_combo: guess_field_name(layer, "code"),
            self.description_field_combo: guess_field_name(layer, "description"),
            self.category_field_combo: guess_field_name(layer, "category"),
            self.quantity_field_combo: guess_field_name(layer, "quantity"),
            self.coefficient_field_combo: guess_field_name(layer, "coefficient"),
            self.unit_override_field_combo: guess_field_name(layer, "unit_override"),
            self.width_field_combo: guess_field_name(layer, "width"),
            self.height_field_combo: guess_field_name(layer, "height"),
            self.thickness_field_combo: guess_field_name(layer, "thickness"),
            self.pieces_field_combo: guess_field_name(layer, "pieces"),
            self.notes_field_combo: guess_field_name(layer, "notes"),
        }
        for combo, field_name in mapping.items():
            if field_name:
                index = combo.findText(field_name)
                if index >= 0:
                    combo.setCurrentIndex(index)

    def import_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleziona prezziario CSV",
            str(Path.home()),
            "CSV (*.csv)",
        )
        if path:
            self.import_price_list_from_path(path)

    def import_xlsx(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleziona prezziario XLSX o DCF",
            str(Path.home()),
            "Prezziari (*.xlsx *.xlsm *.dcf);;Excel (*.xlsx *.xlsm);;DCF (*.dcf)",
        )
        if path:
            self.import_price_list_from_path(path)

    def import_price_list_from_path(self, path: str, source_url: str = "", page_url: str = ""):
        try:
            price_list = load_price_list(path, source_url=source_url)
            imported_id = self.db.import_price_list(price_list)
        except PriceListFormatError as exc:
            QMessageBox.warning(
                self,
                "Formato prezziario non valido",
                f"{exc}\n\n{exc.details}",
            )
            self.log(f"Import prezziario fallito: {exc}")
            self.tabs.setCurrentWidget(self.price_tab)
            return
        except Exception as exc:
            QMessageBox.critical(self, PLUGIN_NAME, f"Import non riuscito:\n{exc}")
            self.log(f"Errore import prezziario: {exc}")
            return

        self.refresh_price_lists(selected_id=imported_id)
        self.refresh_regional_catalog()
        self._set_download_result(
            file_path=path,
            source_url=source_url,
            title=f"Prezziario '{price_list.name}' importato correttamente.",
            page_url=page_url,
        )
        QMessageBox.information(
            self,
            PLUGIN_NAME,
            f"Prezziario '{price_list.name}' importato con {len(price_list.items)} voci.",
        )
        self.log(f"Prezziario importato: {price_list.name} ({len(price_list.items)} voci)")

    def import_bundled_dataset(self):
        dataset = self.current_bundled_dataset()
        if not dataset:
            QMessageBox.information(self, PLUGIN_NAME, "Nessun dataset incluso disponibile.")
            return
        local_path = str(Path(self.plugin_dir) / dataset.relative_path)
        self.import_price_list_from_path(
            local_path,
            source_url=dataset.update_url,
            page_url=dataset.source_page,
        )

    def open_bundled_source(self):
        dataset = self.current_bundled_dataset()
        if not dataset:
            QMessageBox.information(self, PLUGIN_NAME, "Nessun dataset incluso disponibile.")
            return
        QDesktopServices.openUrl(QUrl(dataset.source_page))

    def import_catalog_dataset(self):
        entry = self.current_catalog_entry()
        if not entry:
            QMessageBox.information(self, PLUGIN_NAME, "Seleziona prima una regione dal catalogo.")
            return
        if entry.local_dataset:
            self.import_price_list_from_path(
                entry.local_dataset,
                source_url=entry.update_url,
                page_url=entry.source_page,
            )
            return
        if entry.local_download and Path(entry.local_download).suffix.lower() in {".csv", ".xlsx", ".xlsm", ".zip", ".dcf"}:
            self.import_price_list_from_path(
                entry.local_download,
                source_url=entry.update_url,
                page_url=entry.source_page,
            )
            return
        QMessageBox.information(
            self,
            PLUGIN_NAME,
            "Per questa regione non è ancora presente un dataset locale importabile.\n\n"
            "Usa 'Scarica / aggiorna' oppure crea il template manuale.",
        )

    def download_catalog_entry(self):
        entry = self.current_catalog_entry()
        if not entry:
            QMessageBox.information(self, PLUGIN_NAME, "Seleziona prima una regione dal catalogo.")
            return

        if entry.update_url:
            try:
                self._start_download_feedback(f"Download del file ufficiale per {entry.name}...")
                downloaded_path = self._download_to_temp(
                    entry.update_url,
                    output_dir=os.path.join(self.download_dir, entry.key),
                    source_label=entry.key,
                )
                self.log(f"Scaricato file catalogato per {entry.name}: {downloaded_path}")
                if Path(downloaded_path).suffix.lower() in {".csv", ".xlsx", ".xlsm", ".zip", ".dcf"}:
                    self.import_price_list_from_path(
                        downloaded_path,
                        source_url=entry.update_url,
                        page_url=entry.source_page,
                    )
                else:
                    self.refresh_regional_catalog()
                    QMessageBox.information(
                        self,
                        PLUGIN_NAME,
                        "File ufficiale scaricato correttamente, ma non importabile in automatico.\n\n"
                        "Puoi aprirlo dal pannello catalogo oppure compilare il template manuale.",
                    )
                return
            except Exception as exc:
                self.log(f"Download catalogato fallito per {entry.key}: {exc}")

        index = self.official_region_combo.findData(entry.key)
        if index >= 0:
            self.official_region_combo.setCurrentIndex(index)
        self.download_official_pricelist()
        self.refresh_regional_catalog()

    def open_catalog_page(self):
        entry = self.current_catalog_entry()
        if not entry:
            QMessageBox.information(self, PLUGIN_NAME, "Seleziona prima una regione dal catalogo.")
            return
        QDesktopServices.openUrl(QUrl(entry.source_page or entry.homepage))

    def open_catalog_file(self):
        entry = self.current_catalog_entry()
        if not entry:
            QMessageBox.information(self, PLUGIN_NAME, "Seleziona prima una regione dal catalogo.")
            return
        path = entry.local_dataset or entry.local_download
        if not path:
            QMessageBox.information(
                self,
                PLUGIN_NAME,
                "Nessun file locale disponibile per questa regione. Puoi scaricarlo oppure creare il template manuale.",
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def create_catalog_template(self):
        entry = self.current_catalog_entry()
        if not entry:
            QMessageBox.information(self, PLUGIN_NAME, "Seleziona prima una regione dal catalogo.")
            return
        created = ensure_manual_template(
            os.path.join(self.data_dir, "templates_regionali"),
            entry,
        )
        self._set_download_result(
            file_path=created["csv_path"],
            source_url=entry.update_url,
            title=f"Template manuale creato per {entry.name}.",
            page_url=entry.source_page,
        )
        self.refresh_catalog_details()
        QMessageBox.information(
            self,
            PLUGIN_NAME,
            "Template creato correttamente.\n\n"
            f"CSV: {created['csv_path']}\n"
            f"Istruzioni: {created['readme_path']}",
        )

    def add_download_link(self):
        label, ok = QInputDialog.getText(self, "Nuovo link", "Etichetta del prezziario")
        if not ok or not label.strip():
            return
        url, ok = QInputDialog.getText(self, "Nuovo link", "URL diretto di download")
        if not ok or not url.strip():
            return
        region, ok = QInputDialog.getText(self, "Nuovo link", "Regione o ente (opzionale)")
        if not ok:
            region = ""

        self.db.add_download_link(label.strip(), url.strip(), region.strip())
        self.refresh_download_links()
        self.log(f"Link prezziario salvato: {label.strip()}")

    def remove_download_link(self):
        link_id = self.selected_download_link_id()
        if not link_id:
            QMessageBox.information(self, PLUGIN_NAME, "Seleziona prima un link dalla tabella.")
            return
        self.db.delete_download_link(link_id)
        self.refresh_download_links()
        self.log(f"Link prezziario rimosso: id={link_id}")

    def open_download_link(self):
        url = self.selected_download_link_url()
        if not url:
            QMessageBox.information(self, PLUGIN_NAME, "Seleziona prima un link dalla tabella.")
            return
        QDesktopServices.openUrl(QUrl(url))

    def download_selected_link(self):
        url = self.selected_download_link_url()
        if not url:
            url, ok = QInputDialog.getText(
                self,
                "Scarica prezziario",
                "Inserisci un URL diretto a un file CSV, XLSX o DCF",
            )
            if not ok or not url.strip():
                return
            url = url.strip()

        try:
            self._start_download_feedback("Download da link diretto...")
            downloaded_path = self._download_to_temp(url, output_dir=self.download_dir, source_label="manuale")
            self.import_price_list_from_path(downloaded_path, source_url=url)
            self.log(f"Prezziario scaricato da {url}")
        except PriceListFormatError as exc:
            QMessageBox.warning(
                self,
                "Formato non valido",
                f"{exc}\n\n{exc.details}\n\nIl file scaricato resta comunque disponibile nel pannello 'Stato download'.",
            )
            self.log(f"Download non importabile: {exc}")
        except Exception as exc:
            QMessageBox.critical(self, PLUGIN_NAME, f"Download non riuscito:\n{exc}")
            self.log(f"Errore download prezziario: {exc}")

    def download_official_pricelist(self):
        region_key = self.official_region_combo.currentData()
        if not region_key:
            QMessageBox.information(self, PLUGIN_NAME, "Seleziona una regione.")
            return
        try:
            self._start_download_feedback("Ricerca del prezziario ufficiale...")
            result = self.regional_service.download_latest(
                region_key,
                self.download_dir,
                progress_callback=self._update_download_progress,
            )
        except Exception as exc:
            self._finish_download_feedback("Download non riuscito.", failed=True)
            QMessageBox.warning(
                self,
                "Download ufficiale non risolto",
                f"{exc}\n\nPuoi comunque usare il caricamento manuale o registrare un link diretto.",
            )
            self.log(f"Download ufficiale fallito per {region_key}: {exc}")
            self.refresh_regional_catalog()
            return

        self.log(
            f"Scaricato prezziario ufficiale {result['source_name']}: {result['file_path']}"
        )
        self._set_download_result(
            file_path=str(result["file_path"]),
            source_url=str(result["file_url"]),
            title=f"Download ufficiale completato per {result['source_name']}.",
            page_url=str(result["page_url"]),
        )
        if result["importable"]:
            self.import_price_list_from_path(
                str(result["file_path"]),
                source_url=str(result["file_url"]),
                page_url=str(result["page_url"]),
            )
            self.refresh_regional_catalog()
            return

        self._finish_download_feedback("File scaricato ma non importabile automaticamente.")
        self.refresh_regional_catalog()
        QMessageBox.information(
            self,
            PLUGIN_NAME,
            "File ufficiale scaricato nella cartella locale del plugin.\n\n"
            f"Regione: {result['source_name']}\n"
            f"File: {result['file_path']}\n"
            f"Sorgente: {result['file_url']}\n\n"
            "Il portale ufficiale ha pubblicato un formato non ancora importabile in automatico "
            "(tipicamente PDF). Il file resta disponibile per consultazione o conversione manuale.",
        )

    def open_official_source(self):
        region_key = self.official_region_combo.currentData()
        if not region_key:
            QMessageBox.information(self, PLUGIN_NAME, "Seleziona una regione.")
            return
        url = self.regional_service.get_portal_url(region_key)
        QDesktopServices.openUrl(QUrl(url))

    def _download_to_temp(self, url: str, output_dir: str = "", source_label: str = "") -> str:
        suffix = self._guess_suffix_from_url(url)
        if urlparse(url).scheme.lower() not in ("http", "https"):
            raise RuntimeError(f"URL non consentito (solo http/https): {url}")
        request = Request(url, headers={"User-Agent": "ComputoMetricoGIS/0.1"})
        with urlopen(request, timeout=45) as response:  # nosec B310 - schema validato sopra
            content_type = response.headers.get("Content-Type", "").lower()
            total = int(response.headers.get("Content-Length", "0") or "0")
            if "text/html" in content_type and suffix not in (".csv", ".xlsx", ".zip", ".pdf", ".xls", ".xlsm", ".xml", ".dcf"):
                raise RuntimeError("L'URL non sembra puntare a un download diretto.")
            if not suffix:
                suffix = self._guess_suffix_from_content_type(content_type)

            if output_dir:
                Path(output_dir).mkdir(parents=True, exist_ok=True)
                file_name = os.path.basename(urlparse(url).path) or "prezzario_scaricato"
                file_name = self._sanitize_download_name(file_name, suffix, source_label)
                path = str(Path(output_dir) / file_name)
                temp_mode = False
            else:
                fd, path = tempfile.mkstemp(prefix="computo_prezziario_", suffix=suffix)
                os.close(fd)
                temp_mode = True

            downloaded = 0
            with open(path, "wb") as output_handle:
                while True:
                    chunk = response.read(1024 * 128)
                    if not chunk:
                        break
                    output_handle.write(chunk)
                    downloaded += len(chunk)
                    self._update_download_progress(
                        downloaded,
                        total,
                        f"Scaricati {downloaded} byte" + (f" di {total}" if total else ""),
                    )

        self._finish_download_feedback("Download completato.")
        if temp_mode:
            return path
        self._set_download_result(
            file_path=path,
            source_url=url,
            title="Download da link diretto completato.",
            page_url="",
        )
        return path

    def _guess_suffix_from_url(self, url: str) -> str:
        path = urlparse(url).path.lower()
        if path.endswith(".xlsx"):
            return ".xlsx"
        if path.endswith(".xlsm"):
            return ".xlsm"
        if path.endswith(".xls"):
            return ".xls"
        if path.endswith(".csv"):
            return ".csv"
        if path.endswith(".zip"):
            return ".zip"
        if path.endswith(".pdf"):
            return ".pdf"
        if path.endswith(".xml"):
            return ".xml"
        if path.endswith(".dcf"):
            return ".dcf"
        return ""

    def _guess_suffix_from_content_type(self, content_type: str) -> str:
        if "sheet" in content_type or "excel" in content_type:
            return ".xlsx"
        if "csv" in content_type:
            return ".csv"
        if "zip" in content_type:
            return ".zip"
        if "pdf" in content_type:
            return ".pdf"
        if "xml" in content_type:
            return ".xml"
        if "octet-stream" in content_type:
            return ".dcf"
        return ".bin"

    def run_computation(self):
        layer = self.current_layer()
        price_list_id = self.current_price_list_id()
        if not layer:
            QMessageBox.warning(self, PLUGIN_NAME, "Seleziona un layer vettoriale.")
            return
        if not price_list_id:
            QMessageBox.warning(self, PLUGIN_NAME, "Importa o seleziona un prezziario attivo.")
            self.tabs.setCurrentWidget(self.price_tab)
            return

        mapping = MappingConfig(
            code_field=self._combo_value(self.code_field_combo),
            description_field=self._combo_value(self.description_field_combo),
            category_field=self._combo_value(self.category_field_combo),
            quantity_field=self._combo_value(self.quantity_field_combo),
            coefficient_field=self._combo_value(self.coefficient_field_combo),
            notes_field=self._combo_value(self.notes_field_combo),
            unit_override_field=self._combo_value(self.unit_override_field_combo),
            width_field=self._combo_value(self.width_field_combo),
            height_field=self._combo_value(self.height_field_combo),
            thickness_field=self._combo_value(self.thickness_field_combo),
            pieces_field=self._combo_value(self.pieces_field_combo),
        )

        engine = LayerComputationEngine(QgsProject.instance())
        price_lookup = self.db.get_price_lookup(price_list_id)
        items, warnings = engine.compute_layer(layer, mapping, price_lookup)

        if layer.crs().isGeographic():
            warnings.insert(
                0,
                "Il layer usa un CRS geografico. Per computi affidabili è preferibile un CRS metrico proiettato.",
            )

        if not items:
            QMessageBox.warning(self, PLUGIN_NAME, "Nessuna feature valida da computare.")
            self.measurement_feedback.setHtml("<p><b>Nessun risultato.</b> Controlla il mapping e i codici voce.</p>")
            return

        notes = (
            f"Mapping codice={mapping.code_field}; descrizione={mapping.description_field}; "
            f"quantita_man={mapping.quantity_field}; coefficiente={mapping.coefficient_field}"
        )
        run_id = self.db.create_measurement_run(
            layer_name=layer.name(),
            price_list_id=price_list_id,
            crs_authid=layer.crs().authid(),
            items=items,
            notes=notes,
        )
        self.refresh_runs(selected_id=run_id)

        rows_html = "".join(
            f"<tr><td><b>{it.price_code}</b></td><td>{it.description}</td>"
            f"<td><b>{it.quantity} {it.unit}</b></td><td>€ {it.unit_price:.2f}</td>"
            f"<td><b>€ {it.total_price:.2f}</b></td><td style='font-size:10px;color:#334155;'>{it.note}</td></tr>"
            for it in items[:25]
        )
        table_html = (
            "<table border='1' cellspacing='0' cellpadding='4' style='border-collapse:collapse;width:100%;margin-top:8px;'>"
            "<tr style='background:#f1f5f9;'><th>Codice</th><th>Descrizione</th><th>Misura (UM)</th><th>P. Unit.</th><th>Totale (€)</th><th>Regola di calcolo e note</th></tr>"
            f"{rows_html}</table>"
        )

        if warnings:
            warnings_html = "<br/>".join(f"- {warning}" for warning in warnings[:30])
            self.measurement_feedback.setHtml(
                f"<h3>Computo salvato: Run #{run_id} ({len(items)} elementi)</h3><p style='color:#b91c1c;'><b>Avvisi / Anomalie:</b><br/>{warnings_html}</p>{table_html}"
            )
        else:
            self.measurement_feedback.setHtml(
                f"<h3>Computo salvato: Run #{run_id} ({len(items)} elementi)</h3><p style='color:#15803d;'><b>✓ Computo calcolato correttamente senza anomalie.</b></p>{table_html}"
            )

        self.tabs.setCurrentWidget(self.report_tab)
        self.log(f"Creato run di computo #{run_id} dal layer '{layer.name()}' con {len(items)} elementi")

    def refresh_runs(self, selected_id: int | None = None):
        runs = self.db.list_runs()
        active_id = selected_id or self._active_setting_int("active_run_id")
        self.run_combo.blockSignals(True)
        self.accounting_run_combo.blockSignals(True)
        self.run_combo.clear()
        self.accounting_run_combo.clear()
        chosen_index = -1
        for index, run in enumerate(runs):
            label = (
                f"#{run['id']} {run['layer_name']} | {run['price_list_name']} | "
                f"€ {run['grand_total']}"
            )
            self.run_combo.addItem(label, run["id"])
            self.accounting_run_combo.addItem(label, run["id"])
            if active_id and run["id"] == active_id:
                chosen_index = index
        if chosen_index >= 0:
            self.run_combo.setCurrentIndex(chosen_index)
            self.accounting_run_combo.setCurrentIndex(chosen_index)
        elif runs:
            self.run_combo.setCurrentIndex(0)
            self.accounting_run_combo.setCurrentIndex(0)
            self.db.set_setting("active_run_id", self.run_combo.currentData())
        self.run_combo.blockSignals(False)
        self.accounting_run_combo.blockSignals(False)
        self.refresh_report_tables()
        self.refresh_accounting_tab()
        self.refresh_info_tab()

    def refresh_report_tables(self):
        run_id = self.current_run_id()
        if not run_id:
            self.summary_table.setRowCount(0)
            self.detail_table.setRowCount(0)
            return

        self.db.set_setting("active_run_id", run_id)
        summary_rows = self.db.get_run_summary(run_id)
        detail_rows = self.db.get_run_details(run_id)
        self._populate_table(
            self.summary_table,
            summary_rows,
            ["code", "description", "unit", "quantity", "unit_price", "total_price"],
        )
        self._populate_table(
            self.detail_table,
            detail_rows,
            ["layer_name", "feature_id", "geometry_type", "price_code", "description", "unit", "quantity", "unit_price", "total_price", "note"],
        )

    def refresh_accounting_tab(self):
        run_id = self.current_accounting_run_id()
        if not run_id:
            self.accounting_libretto_table.setRowCount(0)
            self.accounting_registro_table.setRowCount(0)
            self.accounting_sommario_table.setRowCount(0)
            self.accounting_sal_table.setRowCount(0)
            self.accounting_journal_table.setRowCount(0)
            self.accounting_certificate_browser.setHtml("<p>Nessun run disponibile per la contabilità.</p>")
            return

        summary_rows = self.db.get_run_summary(run_id)
        detail_rows = self.db.get_run_details(run_id)
        category_rows = build_category_summary(summary_rows)
        sal_rows = self.db.list_sal_documents(run_id)
        journal_rows = self.db.list_journal_entries(run_id)

        self._populate_table(
            self.accounting_libretto_table,
            detail_rows,
            ["layer_name", "feature_id", "price_code", "description", "unit", "quantity", "unit_price", "total_price", "note"],
        )
        self._populate_table(
            self.accounting_registro_table,
            summary_rows,
            ["code", "description", "category", "unit", "quantity", "unit_price", "total_price"],
        )
        self._populate_table(
            self.accounting_sommario_table,
            category_rows,
            ["category", "total_price"],
        )
        self.accounting_journal_table.setRowCount(len(journal_rows))
        for row_index, row in enumerate(journal_rows):
            for column_index, key in enumerate(("work_date", "title", "weather", "workers", "description")):
                item = QTableWidgetItem(str(row.get(key) or ""))
                if column_index == 0:
                    item.setData(QT_USER_ROLE, row["id"])
                self.accounting_journal_table.setItem(row_index, column_index, item)
        self.accounting_journal_table.resizeColumnsToContents()
        self.accounting_journal_table.horizontalHeader().setSectionResizeMode(4, header_stretch_mode())

        self.accounting_sal_table.setRowCount(len(sal_rows))
        for row_index, row in enumerate(sal_rows):
            summary = self.db.get_run_summary(int(row["run_id"]))
            sal_data = self._sal_record_with_totals(row, summary)
            values = [
                row["id"],
                row["sal_number"],
                row["sal_date"],
                sal_data["gross_total"],
                sal_data["previous_paid"],
                sal_data["due_before_vat"],
                sal_data["total_due"],
            ]
            for column_index, value in enumerate(values):
                item = QTableWidgetItem("" if value is None else str(value))
                if column_index == 0:
                    item.setData(QT_USER_ROLE, row["id"])
                self.accounting_sal_table.setItem(row_index, column_index, item)
        self.accounting_sal_table.resizeColumnsToContents()

        self.accounting_certificate_browser.setHtml(self._build_accounting_certificate_preview(summary_rows))

    def _build_accounting_certificate_preview(self, summary_rows: list[dict]) -> str:
        sal_record = self.current_sal_form_record()
        sal_data = self._sal_record_with_totals(sal_record, summary_rows)
        return f"""
            <h3>Anteprima certificato</h3>
            <p><b>Importo lavori:</b> € {sal_data['works_total']:.2f}</p>
            <p><b>Oneri sicurezza:</b> € {sal_data['security_costs']:.2f}</p>
            <p><b>Importo lordo SAL:</b> € {sal_data['gross_total']:.2f}</p>
            <p><b>Ritenuta:</b> {sal_data['retention_percent']:.2f}% = € {sal_data['retention_amount']:.2f}</p>
            <p><b>Certificato a tutto il SAL:</b> € {sal_data['certified_to_date']:.2f}</p>
            <p><b>Già pagato:</b> € {sal_data['previous_paid']:.2f}</p>
            <p><b>Da liquidare:</b> € {sal_data['due_before_vat']:.2f}</p>
            <p><b>IVA:</b> {sal_data['vat_percent']:.2f}% = € {sal_data['vat_due']:.2f}</p>
            <p><b>Totale certificato:</b> <span style="font-size:15px"><b>€ {sal_data['total_due']:.2f}</b></span></p>
        """

    def _sal_record_with_totals(self, sal_record: dict, summary_rows: list[dict]) -> dict:
        from .accounting import compute_sal_totals

        totals = compute_sal_totals(
            summary_rows,
            security_costs=float(sal_record.get("security_costs") or 0.0),
            retention_percent=float(sal_record.get("retention_percent") or 0.0),
            vat_percent=float(sal_record.get("vat_percent") or 22.0),
            previous_paid=float(sal_record.get("previous_paid") or 0.0),
        )
        merged = dict(sal_record)
        merged.update(totals)
        return merged

    def current_sal_form_record(self) -> dict:
        return {
            "sal_number": self._safe_int(self.sal_number_edit.text(), 1),
            "sal_date": self.sal_date_edit.text().strip(),
            "security_costs": self._safe_float(self.sal_security_costs_edit.text(), 0.0),
            "retention_percent": self._safe_float(self.sal_retention_percent_edit.text(), 0.0),
            "vat_percent": self._safe_float(self.sal_vat_percent_edit.text(), 22.0),
            "previous_paid": self._safe_float(self.sal_previous_paid_edit.text(), 0.0),
            "notes": self.sal_notes_edit.toPlainText().strip(),
        }

    def generate_sal_document(self):
        run_id = self.current_accounting_run_id()
        if not run_id:
            QMessageBox.information(self, PLUGIN_NAME, "Nessun run disponibile per generare il SAL.")
            return
        sal_record = self.current_sal_form_record()
        sal_id = self.db.create_sal_document(
            run_id=run_id,
            sal_number=int(sal_record["sal_number"]),
            sal_date=str(sal_record["sal_date"]),
            security_costs=float(sal_record["security_costs"]),
            retention_percent=float(sal_record["retention_percent"]),
            vat_percent=float(sal_record["vat_percent"]),
            previous_paid=float(sal_record["previous_paid"]),
            notes=str(sal_record["notes"]),
        )
        self.refresh_accounting_tab()
        self.log(f"Creato SAL #{sal_id} per run {run_id}")
        QMessageBox.information(self, PLUGIN_NAME, f"SAL registrato correttamente. ID documento: {sal_id}")

    def load_last_sal_document(self):
        run_id = self.current_accounting_run_id()
        if not run_id:
            QMessageBox.information(self, PLUGIN_NAME, "Nessun run disponibile.")
            return
        rows = self.db.list_sal_documents(run_id)
        if not rows:
            QMessageBox.information(self, PLUGIN_NAME, "Non esistono SAL registrati per questo run.")
            return
        self._load_sal_form(rows[0])

    def load_selected_sal_into_form(self):
        sal_id = self.selected_sal_document_id()
        if not sal_id:
            return
        try:
            row = self.db.get_sal_document(sal_id)
        except Exception:
            return
        self._load_sal_form(row)

    def _load_sal_form(self, row: dict):
        self.sal_number_edit.setText(str(row.get("sal_number") or 1))
        self.sal_date_edit.setText(str(row.get("sal_date") or ""))
        self.sal_security_costs_edit.setText(str(row.get("security_costs") or 0))
        self.sal_retention_percent_edit.setText(str(row.get("retention_percent") or 0))
        self.sal_vat_percent_edit.setText(str(row.get("vat_percent") or 22))
        self.sal_previous_paid_edit.setText(str(row.get("previous_paid") or 0))
        self.sal_notes_edit.setPlainText(str(row.get("notes") or ""))
        run_id = self.current_accounting_run_id()
        if run_id:
            self.accounting_certificate_browser.setHtml(
                self._build_accounting_certificate_preview(self.db.get_run_summary(run_id))
            )

    def add_journal_entry(self):
        run_id = self.current_accounting_run_id()
        title = self.journal_title_edit.text().strip()
        if not title:
            QMessageBox.information(self, PLUGIN_NAME, "Inserisci almeno il titolo della voce di giornale.")
            return
        self.db.add_journal_entry(
            work_date=self.journal_date_edit.text().strip(),
            title=title,
            description=self.journal_description_edit.toPlainText().strip(),
            weather=self.journal_weather_edit.text().strip(),
            workers=self.journal_workers_edit.text().strip(),
            run_id=run_id,
        )
        self.journal_title_edit.clear()
        self.journal_weather_edit.clear()
        self.journal_workers_edit.clear()
        self.journal_description_edit.clear()
        self.refresh_accounting_tab()
        self.log("Voce di giornale lavori aggiunta.")

    def delete_journal_entry(self):
        entry_id = self.selected_journal_entry_id()
        if not entry_id:
            QMessageBox.information(self, PLUGIN_NAME, "Seleziona prima una voce del giornale lavori.")
            return
        self.db.delete_journal_entry(entry_id)
        self.refresh_accounting_tab()
        self.log(f"Voce di giornale rimossa: id={entry_id}")

    def export_accounting_pdf(self):
        run_id = self.current_accounting_run_id()
        if not run_id:
            QMessageBox.information(self, PLUGIN_NAME, "Nessun run disponibile per l'export contabile.")
            return
        self.save_report_profile(show_message=False)
        suggested = os.path.join(self.export_dir, f"contabilita_run_{run_id}.pdf")
        path, _ = QFileDialog.getSaveFileName(self, "Esporta PDF contabilità", suggested, "PDF (*.pdf)")
        if not path:
            return
        metadata = self.db.get_run_metadata(run_id)
        summary = self.db.get_run_summary(run_id)
        details = self.db.get_run_details(run_id)
        journal = self.db.list_journal_entries(run_id)
        sal_record = self._current_or_last_sal_record(run_id)
        map_path = self.capture_report_map(run_id) if self.report_include_map_checkbox.isChecked() else ""
        html = build_accounting_html(
            metadata,
            summary,
            details,
            sal_record,
            journal,
            profile=self.report_profile,
            map_image_path=map_path,
        )
        export_pdf(path, html)
        self.log(f"PDF contabilità esportato: {path}")
        QMessageBox.information(self, PLUGIN_NAME, f"PDF contabilità generato:\n{path}")

    def export_accounting_workbook(self):
        run_id = self.current_accounting_run_id()
        if not run_id:
            QMessageBox.information(self, PLUGIN_NAME, "Nessun run disponibile per l'export contabile.")
            return
        self.save_report_profile(show_message=False)
        suggested = os.path.join(self.export_dir, f"contabilita_run_{run_id}.xlsx")
        path, _ = QFileDialog.getSaveFileName(self, "Esporta XLSX contabilità", suggested, "Excel (*.xlsx)")
        if not path:
            return
        metadata = self.db.get_run_metadata(run_id)
        summary = self.db.get_run_summary(run_id)
        details = self.db.get_run_details(run_id)
        journal = self.db.list_journal_entries(run_id)
        sal_record = self._current_or_last_sal_record(run_id)
        export_accounting_xlsx(
            path,
            metadata,
            summary,
            details,
            sal_record,
            journal,
            profile=self.report_profile,
        )
        self.log(f"XLSX contabilità esportato: {path}")
        QMessageBox.information(self, PLUGIN_NAME, f"File XLSX contabilità generato:\n{path}")

    def _current_or_last_sal_record(self, run_id: int) -> dict:
        sal_id = self.selected_sal_document_id()
        if sal_id:
            try:
                row = self.db.get_sal_document(sal_id)
                if int(row["run_id"]) == int(run_id):
                    return row
            except Exception:
                pass
        rows = self.db.list_sal_documents(run_id)
        return rows[0] if rows else self.current_sal_form_record()

    def export_current_pdf(self):
        run_id = self.current_run_id()
        if not run_id:
            QMessageBox.information(self, PLUGIN_NAME, "Nessun run disponibile da esportare.")
            return

        self.save_report_profile(show_message=False)
        suggested = os.path.join(self.export_dir, f"computo_run_{run_id}.pdf")
        path, _ = QFileDialog.getSaveFileName(self, "Esporta PDF", suggested, "PDF (*.pdf)")
        if not path:
            return

        metadata = self.db.get_run_metadata(run_id)
        summary = self.db.get_run_summary(run_id)
        details = self.db.get_run_details(run_id)
        map_path = self.capture_report_map(run_id) if self.report_include_map_checkbox.isChecked() else ""
        html = build_report_html(metadata, summary, details, profile=self.report_profile, map_image_path=map_path)
        export_pdf(path, html)
        self.log(f"Report PDF esportato: {path}")
        QMessageBox.information(self, PLUGIN_NAME, f"PDF generato:\n{path}")

    def export_current_xlsx(self):
        run_id = self.current_run_id()
        if not run_id:
            QMessageBox.information(self, PLUGIN_NAME, "Nessun run disponibile da esportare.")
            return

        self.save_report_profile(show_message=False)
        suggested = os.path.join(self.export_dir, f"computo_run_{run_id}.xlsx")
        path, _ = QFileDialog.getSaveFileName(self, "Esporta XLSX", suggested, "Excel (*.xlsx)")
        if not path:
            return

        metadata = self.db.get_run_metadata(run_id)
        summary = self.db.get_run_summary(run_id)
        details = self.db.get_run_details(run_id)
        export_xlsx(path, metadata, summary, details, profile=self.report_profile)
        self.log(f"Report XLSX esportato: {path}")
        QMessageBox.information(self, PLUGIN_NAME, f"File XLSX generato:\n{path}")

    def choose_report_logo(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleziona logo",
            str(Path.home()),
            "Immagini (*.png *.jpg *.jpeg *.svg)",
        )
        if path:
            self.report_logo_path.setText(path)

    def clear_report_logo(self):
        self.report_logo_path.clear()

    def add_report_reference(self):
        row = self.report_refs_table.rowCount()
        self.report_refs_table.insertRow(row)
        self.report_refs_table.setItem(row, 0, QTableWidgetItem(""))
        self.report_refs_table.setItem(row, 1, QTableWidgetItem(""))

    def remove_report_reference(self):
        row = self.report_refs_table.currentRow()
        if row >= 0:
            self.report_refs_table.removeRow(row)

    def load_report_profile(self):
        self.report_profile = self.db.load_report_profile()
        self.report_title_edit.setText(self.report_profile.title)
        self.report_subtitle_edit.setText(self.report_profile.subtitle)
        self.report_organization_edit.setText(self.report_profile.organization)
        self.report_logo_path.setText(self.report_profile.logo_path)
        self.report_footer_edit.setPlainText(self.report_profile.footer_text)
        self.report_map_title_edit.setText(self.report_profile.map_title)
        self.report_include_map_checkbox.setChecked(self.report_profile.include_map)

        self.report_refs_table.setRowCount(0)
        for reference in self.report_profile.references:
            row = self.report_refs_table.rowCount()
            self.report_refs_table.insertRow(row)
            self.report_refs_table.setItem(row, 0, QTableWidgetItem(reference.label))
            self.report_refs_table.setItem(row, 1, QTableWidgetItem(reference.value))

    def save_report_profile(self, show_message: bool = True):
        references: list[ReportReference] = []
        for row in range(self.report_refs_table.rowCount()):
            label_item = self.report_refs_table.item(row, 0)
            value_item = self.report_refs_table.item(row, 1)
            label = label_item.text().strip() if label_item else ""
            value = value_item.text().strip() if value_item else ""
            if label and value:
                references.append(ReportReference(label=label, value=value))

        self.report_profile = ReportProfile(
            title=self.report_title_edit.text().strip() or "Computo metrico estimativo",
            subtitle=self.report_subtitle_edit.text().strip(),
            organization=self.report_organization_edit.text().strip(),
            logo_path=self.report_logo_path.text().strip(),
            footer_text=self.report_footer_edit.toPlainText().strip(),
            include_map=self.report_include_map_checkbox.isChecked(),
            map_title=self.report_map_title_edit.text().strip() or "Mappa di inquadramento",
            references=references,
        )
        self.db.save_report_profile(self.report_profile)
        if show_message:
            QMessageBox.information(self, PLUGIN_NAME, "Profilo report salvato.")
        self.log("Profilo report aggiornato.")

    def _run_layer_extent(self, run_id: int) -> QgsRectangle | None:
        try:
            metadata = self.db.get_run_metadata(run_id)
        except Exception:
            return None
        layer_names = [name.strip() for name in metadata.layer_name.split(",") if name.strip()]
        extent = None
        for name in layer_names:
            for layer in QgsProject.instance().mapLayersByName(name):
                layer_extent = layer.extent()
                if layer_extent.isNull() or layer_extent.isEmpty():
                    continue
                if extent is None:
                    extent = QgsRectangle(layer_extent)
                else:
                    extent.combineExtentWith(layer_extent)
        return extent

    def capture_report_map(self, run_id: int) -> str:
        maps_dir = os.path.join(self.export_dir, "mappe")
        os.makedirs(maps_dir, exist_ok=True)
        path = os.path.join(maps_dir, f"computo_run_{run_id}_map.png")

        target_extent = self._run_layer_extent(run_id)
        if target_extent is None or target_extent.isNull() or target_extent.isEmpty():
            canvas_factory = getattr(self.iface, "mapCanvas", None)
            canvas = canvas_factory() if callable(canvas_factory) else None
            if canvas is not None and not canvas.extent().isNull() and not canvas.extent().isEmpty():
                target_extent = QgsRectangle(canvas.extent())

        if target_extent is None or target_extent.isNull() or target_extent.isEmpty():
            self.log("Esportazione mappa non riuscita: nessuna estensione disponibile per il run.")
            return ""

        buffered = QgsRectangle(target_extent)
        buffered.scale(1.3)
        if buffered.width() <= 0:
            buffered.setXMinimum(buffered.xMinimum() - 1)
            buffered.setXMaximum(buffered.xMaximum() + 1)
        if buffered.height() <= 0:
            buffered.setYMinimum(buffered.yMinimum() - 1)
            buffered.setYMaximum(buffered.yMaximum() + 1)

        top_margin = 10.0
        side_margin = 10.0
        scale_gap = 8.0
        scale_h = 14.0
        bottom_margin = 8.0
        max_map_w = 180.0
        max_map_h = 120.0
        min_map_h = 35.0

        aspect = buffered.width() / buffered.height() if buffered.height() else 1.0
        if aspect >= (max_map_w / max_map_h):
            map_w = max_map_w
            map_h = max(min_map_h, max_map_w / aspect)
        else:
            map_h = max_map_h
            map_w = max_map_h * aspect

        page_w = map_w + 2 * side_margin
        page_h = top_margin + map_h + scale_gap + scale_h + bottom_margin

        try:
            project = QgsProject.instance()
            layout = QgsPrintLayout(project)
            layout.initializeDefaults()
            page = layout.pageCollection().page(0)
            page.setPageSize(QgsLayoutSize(page_w, page_h, LAYOUT_UNIT_MM))

            map_item = QgsLayoutItemMap(layout)
            layout.addLayoutItem(map_item)
            map_item.attemptSetSceneRect(QRectF(side_margin, top_margin, map_w, map_h))
            map_item.setExtent(buffered)
            map_item.setBackgroundColor(QColor(244, 247, 249))
            map_item.setBackgroundEnabled(True)
            map_item.setFrameEnabled(True)
            map_item.setFrameStrokeColor(QColor(90, 90, 90))

            scale_bar = QgsLayoutItemScaleBar(layout)
            layout.addLayoutItem(scale_bar)
            scale_bar.setLinkedMap(map_item)
            scale_bar.setStyle("Single Box")
            scale_bar.applyDefaultSize()
            scale_bar.attemptMove(
                QgsLayoutPoint(side_margin, top_margin + map_h + scale_gap, LAYOUT_UNIT_MM)
            )

            north_arrow = QgsLayoutItemPicture(layout)
            layout.addLayoutItem(north_arrow)
            north_arrow.setPicturePath(":/images/north_arrows/layout_default_north_arrow.svg")
            north_arrow.attemptSetSceneRect(
                QRectF(side_margin + map_w - 14, top_margin + 2, 10, 14)
            )

            exporter = QgsLayoutExporter(layout)
            settings = QgsLayoutExporter.ImageExportSettings()
            settings.dpi = 200
            result = exporter.exportToImage(path, settings)
            if result != LAYOUT_EXPORT_SUCCESS:
                self.log(f"Esportazione mappa non riuscita (codice {result}).")
                return ""
        except Exception as exc:
            self.log(f"Esportazione mappa non riuscita: {exc}")
            return ""

        return path if os.path.exists(path) else ""

    def create_demo_project(self):
        default_dir = os.path.join(Path.home(), "Computo_Metrico_Demo")
        output_dir = QFileDialog.getExistingDirectory(
            self,
            "Seleziona la cartella per il progetto demo",
            default_dir,
        )
        if not output_dir:
            return
        try:
            generated = self.template_builder.create(output_dir)
            demo_price_list = load_price_list(generated["demo_price_list_path"])
            imported_id = self.db.import_price_list(demo_price_list)
            self.refresh_price_lists(selected_id=imported_id)
            self.log(f"Prezziario demo importato e attivato: {demo_price_list.name}")
        except Exception as exc:
            QMessageBox.critical(self, PLUGIN_NAME, f"Creazione progetto demo non riuscita:\n{exc}")
            self.log(f"Errore progetto demo: {exc}")
            return

        self.log(f"Progetto demo creato in {generated['project_path']}")
        QMessageBox.information(
            self,
            PLUGIN_NAME,
            "Progetto demo creato correttamente e Prezziario Demo importato.\n\n"
            f"Progetto: {generated['project_path']}\n"
            f"GeoPackage: {generated['gpkg_path']}\n"
            f"Prezziario attivo nel plugin: {generated['demo_price_list_path']}\n"
            f"Istruzioni e dettagli: {generated['instructions_path']}\n"
            f"Output demo: {generated['demo_output_dir']}",
        )

    def current_layer(self):
        layer_id = self.layer_combo.currentData()
        if not layer_id:
            return None
        return QgsProject.instance().mapLayer(layer_id)

    def current_price_list_id(self) -> int | None:
        data = self.price_list_combo.currentData()
        return int(data) if data not in (None, "") else None

    def current_run_id(self) -> int | None:
        data = self.run_combo.currentData()
        return int(data) if data not in (None, "") else None

    def current_accounting_run_id(self) -> int | None:
        data = self.accounting_run_combo.currentData()
        return int(data) if data not in (None, "") else None

    def selected_download_link_id(self) -> int | None:
        row = self.download_links_table.currentRow()
        if row < 0:
            return None
        item = self.download_links_table.item(row, 0)
        if item is None:
            return None
        return int(item.data(QT_USER_ROLE))

    def selected_download_link_url(self) -> str:
        row = self.download_links_table.currentRow()
        if row < 0:
            return ""
        item = self.download_links_table.item(row, 2)
        return item.text().strip() if item else ""

    def selected_sal_document_id(self) -> int | None:
        row = self.accounting_sal_table.currentRow()
        if row < 0:
            return None
        item = self.accounting_sal_table.item(row, 0)
        if item is None:
            return None
        data = item.data(QT_USER_ROLE)
        return int(data) if data not in (None, "") else None

    def selected_journal_entry_id(self) -> int | None:
        row = self.accounting_journal_table.currentRow()
        if row < 0:
            return None
        item = self.accounting_journal_table.item(row, 0)
        if item is None:
            return None
        data = item.data(QT_USER_ROLE)
        return int(data) if data not in (None, "") else None

    def _populate_table(self, table: QTableWidget, rows: list[dict], keys: list[str]):
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, key in enumerate(keys):
                value = row.get(key, "")
                item = QTableWidgetItem("" if value is None else str(value))
                table.setItem(row_index, column_index, item)
        table.resizeColumnsToContents()
        stretch_column = table.property("stretch_column")
        if stretch_column is not None:
            try:
                stretch_column = int(stretch_column)
            except Exception:
                stretch_column = -1
            if stretch_column >= 0 and stretch_column < table.columnCount():
                table.horizontalHeader().setSectionResizeMode(stretch_column, header_stretch_mode())

    def _active_setting_int(self, key: str) -> int | None:
        value = self.db.get_setting(key, "")
        return int(value) if value.isdigit() else None

    def current_bundled_dataset(self):
        key = self.bundled_dataset_combo.currentData()
        if not key:
            return None
        for dataset in self.bundled_datasets:
            if dataset.key == key:
                return dataset
        return None

    def _combo_value(self, combo: QComboBox) -> str:
        data = combo.currentData()
        if data in (None, ""):
            return ""
        return str(data)

    def _start_download_feedback(self, message: str):
        self.download_status_label.setText(message)
        self.download_progress.setRange(0, 0)
        self.download_progress.setValue(0)
        QApplication.processEvents()

    def _update_download_progress(self, downloaded: int, total: int, message: str = ""):
        if total > 0:
            self.download_progress.setRange(0, 100)
            self.download_progress.setValue(max(0, min(100, int((downloaded / total) * 100))))
        else:
            self.download_progress.setRange(0, 0)
        self.download_status_label.setText(message or "Download in corso...")
        QApplication.processEvents()

    def _finish_download_feedback(self, message: str, failed: bool = False):
        self.download_progress.setRange(0, 100)
        self.download_progress.setValue(0 if failed else 100)
        self.download_status_label.setText(message)
        QApplication.processEvents()

    def _set_download_result(self, file_path: str, source_url: str, title: str, page_url: str = ""):
        self.last_downloaded_path = file_path
        self.last_downloaded_url = source_url
        self.last_downloaded_page_url = page_url
        folder_path = str(Path(file_path).parent)
        file_url = QUrl.fromLocalFile(file_path).toString()
        folder_url = QUrl.fromLocalFile(folder_path).toString()
        source_line = (
            f"<p><b>Sorgente file:</b> <a href=\"{source_url}\">{source_url}</a></p>"
            if source_url
            else ""
        )
        page_line = (
            f"<p><b>Pagina ufficiale:</b> <a href=\"{page_url}\">{page_url}</a></p>"
            if page_url
            else ""
        )
        self.download_result_browser.setHtml(
            f"""
            <h3>{title}</h3>
            <p><b>File locale:</b> <a href="{file_url}">{file_path}</a></p>
            <p><b>Cartella locale:</b> <a href="{folder_url}">{folder_path}</a></p>
            {source_line}
            {page_line}
            """
        )

    def _sanitize_download_name(self, base_name: str, suffix: str, source_label: str = "") -> str:
        stem = Path(base_name).stem or "prezzario"
        if source_label:
            stem = f"{source_label}_{stem}"
        stem = "".join(char if char.isalnum() or char in "._-" else "_" for char in stem)
        return f"{stem}{suffix}"

    def _safe_float(self, value: str, default: float = 0.0) -> float:
        try:
            return float(str(value).replace(",", ".").strip())
        except Exception:
            return default

    def _safe_int(self, value: str, default: int = 0) -> int:
        try:
            return int(float(str(value).replace(",", ".").strip()))
        except Exception:
            return default
