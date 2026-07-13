import csv
import os
import shutil
from pathlib import Path

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsField,
    QgsFillSymbol,
    QgsGeometry,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsReferencedRectangle,
    QgsSingleSymbolRenderer,
    QgsTextFormat,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)

from qgis.PyQt.QtGui import QColor

from .qt_compat import QVariant
from .accounting import build_accounting_html, export_accounting_xlsx
from .models import ReportMetadata, ReportProfile, ReportReference
from .reporting import build_report_html, export_pdf, export_xlsx


class TemplateProjectBuilder:
    def __init__(self, plugin_dir: str):
        self.plugin_dir = plugin_dir
        self.crs = QgsCoordinateReferenceSystem("EPSG:32633")

    def _fields(self):
        return [
            QgsField("item_code", QVariant.String, len=48),
            QgsField("descrizione", QVariant.String, len=120),
            QgsField("categoria", QVariant.String, len=60),
            QgsField("coefficiente", QVariant.Double, len=10, prec=3),
            QgsField("quantita_man", QVariant.Double, len=12, prec=3),
            QgsField("unita_override", QVariant.String, len=24),
            QgsField("larghezza_m", QVariant.Double, len=12, prec=3),
            QgsField("altezza_m", QVariant.Double, len=12, prec=3),
            QgsField("spessore_m", QVariant.Double, len=12, prec=3),
            QgsField("pezzi", QVariant.Double, len=12, prec=3),
            QgsField("note", QVariant.String, len=254),
        ]

    def _create_memory_layer(self, geometry: str, layer_name: str):
        layer = QgsVectorLayer(
            f"{geometry}?crs={self.crs.authid()}", layer_name, "memory"
        )
        provider = layer.dataProvider()
        provider.addAttributes(self._fields())
        layer.updateFields()
        return layer

    def _sample_layers(self):
        point_layer = self._create_memory_layer("Point", "cm_punti")
        line_layer = self._create_memory_layer("LineString", "cm_linee")
        polygon_layer = self._create_memory_layer("Polygon", "cm_poligoni")

        point_feature = QgsFeature(point_layer.fields())
        point_feature.setAttributes(
            [
                "DEM-POINT-001",
                "Picchetto topografico",
                "Rilievo",
                1.0,
                None,
                "",
                None,
                None,
                None,
                1.0,
                "Voce a corpo/pezzi (cad) per singolo punto",
            ]
        )
        point_feature.setGeometry(
            QgsGeometry.fromPointXY(QgsPointXY(500000, 4649500))
        )
        point_layer.dataProvider().addFeatures([point_feature])

        line_feature = QgsFeature(line_layer.fields())
        line_feature.setAttributes(
            [
                "DEM-LINE-001",
                "Recinzione metallica",
                "Opere lineari",
                1.0,
                None,
                "",
                None,
                None,
                None,
                None,
                "Lunghezza (ml) calcolata automaticamente dal tracciato "
                "lineare",
            ]
        )
        line_feature.setGeometry(
            QgsGeometry.fromPolylineXY(
                [
                    QgsPointXY(500050, 4649500),
                    QgsPointXY(500130, 4649540),
                    QgsPointXY(500230, 4649525),
                ]
            )
        )
        line_layer.dataProvider().addFeatures([line_feature])

        polygon_feature = QgsFeature(polygon_layer.fields())
        polygon_feature.setAttributes(
            [
                "DEM-AREA-001",
                "Pavimentazione drenante",
                "Superfici",
                1.0,
                None,
                "",
                None,
                None,
                0.12,
                None,
                "Volume calcolato (mc) = Area geometria (1.200 mq) x "
                "spessore_m (0,12 m)",
            ]
        )
        polygon_feature.setGeometry(
            QgsGeometry.fromPolygonXY(
                [
                    [
                        QgsPointXY(500020, 4649400),
                        QgsPointXY(500060, 4649400),
                        QgsPointXY(500060, 4649370),
                        QgsPointXY(500020, 4649370),
                        QgsPointXY(500020, 4649400),
                    ]
                ]
            )
        )
        polygon_layer.dataProvider().addFeatures([polygon_feature])

        self._apply_styles(point_layer, "point")
        self._apply_styles(line_layer, "line")
        self._apply_styles(polygon_layer, "polygon")

        point_layer.updateExtents()
        line_layer.updateExtents()
        polygon_layer.updateExtents()
        return [point_layer, line_layer, polygon_layer]

    def _apply_styles(self, layer, geometry_family: str):
        if geometry_family == "point":
            symbol = QgsMarkerSymbol.createSimple(
                {
                    "name": "circle",
                    "color": "#0f766e",
                    "size": "3.2",
                    "outline_color": "#ffffff",
                }
            )
        elif geometry_family == "line":
            symbol = QgsLineSymbol.createSimple(
                {"color": "#d97706", "width": "0.9"}
            )
        else:
            symbol = QgsFillSymbol.createSimple(
                {
                    "color": "37, 99, 235, 90",
                    "outline_color": "#1d4ed8",
                    "outline_width": "0.5",
                }
            )
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        try:
            self._apply_labeling(layer, geometry_family)
        except Exception:
            pass

    def _apply_labeling(self, layer, geometry_family: str):
        pal_settings = QgsPalLayerSettings()
        pal_settings.fieldName = "item_code"
        text_format = QgsTextFormat()
        text_format.setSize(8)
        text_format.setColor(QColor("#1f2933"))
        buffer_settings = text_format.buffer()
        buffer_settings.setEnabled(True)
        buffer_settings.setSize(1)
        buffer_settings.setColor(QColor("#ffffff"))
        text_format.setBuffer(buffer_settings)
        pal_settings.setFormat(text_format)
        if geometry_family == "point":
            pal_settings.placement = QgsPalLayerSettings.Placement.OverPoint
            pal_settings.yOffset = 2.5
            pal_settings.placementFlags = (
                QgsPalLayerSettings.OffsetType.FromPoint
            )
        elif geometry_family == "line":
            pal_settings.placement = QgsPalLayerSettings.Placement.Line
        else:
            pal_settings.placement = QgsPalLayerSettings.Placement.OverPoint
        layer.setLabeling(QgsVectorLayerSimpleLabeling(pal_settings))
        layer.setLabelsEnabled(True)

    def _writer_result_ok(self, result) -> bool:
        if isinstance(result, tuple):
            code = result[0]
        else:
            code = result
        return code == QgsVectorFileWriter.NoError

    def _write_layer(self, layer, gpkg_path: str, overwrite_file: bool):
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = layer.name()
        options.actionOnExistingFile = (
            QgsVectorFileWriter.CreateOrOverwriteFile
            if overwrite_file
            else QgsVectorFileWriter.CreateOrOverwriteLayer
        )

        writer = QgsVectorFileWriter
        transform_context = QgsProject.instance().transformContext()
        if hasattr(writer, "writeAsVectorFormatV3"):
            result = writer.writeAsVectorFormatV3(
                layer, gpkg_path, transform_context, options
            )
        else:  # pragma: no cover - compatibility fallback
            result = writer.writeAsVectorFormatV2(
                layer, gpkg_path, transform_context, options
            )

        if not self._writer_result_ok(result):
            raise RuntimeError(
                f"Impossibile salvare il layer demo '{layer.name()}'."
            )

    def _build_project(self, project_path: str, gpkg_path: str):
        try:
            project = QgsProject()
        except Exception as exc:  # pragma: no cover - defensive fallback
            raise RuntimeError(
                "QGIS non supporta la creazione del progetto demo."
            ) from exc

        project.setTitle("Computo Metrico Demo")
        project.setCrs(self.crs)
        project.setFileName(project_path)
        project.setPresetHomePath(str(Path(project_path).parent))

        combined_extent = None
        for layer_name, geometry_family in (
            ("cm_punti", "point"),
            ("cm_linee", "line"),
            ("cm_poligoni", "polygon"),
        ):
            layer = QgsVectorLayer(
                f"{gpkg_path}|layername={layer_name}", layer_name, "ogr"
            )
            if not layer.isValid():
                raise RuntimeError(f"Layer demo '{layer_name}' non valido.")
            self._apply_styles(layer, geometry_family)
            project.addMapLayer(layer)
            layer_extent = layer.extent()
            if not layer_extent.isNull() and not layer_extent.isEmpty():
                if combined_extent is None:
                    combined_extent = QgsRectangle(layer_extent)
                else:
                    combined_extent.combineExtentWith(layer_extent)

        if combined_extent is not None:
            combined_extent.scale(1.3)
            try:
                project.viewSettings().setDefaultViewExtent(
                    QgsReferencedRectangle(combined_extent, self.crs)
                )
            except Exception:
                pass

        if not project.write(project_path):
            raise RuntimeError("Impossibile scrivere il file progetto QGIS.")

    def _write_instructions(self, output_dir: str):
        instructions_path = os.path.join(output_dir, "ISTRUZIONI_PROGETTO.txt")
        content = (
            "Computo Metrico GIS - Progetto Demo\n\n"
            "1. Apri il file computo_metrico_demo.qgs in QGIS.\n"
            "2. Il file prezziario_demo.csv viene importato automaticamente "
            "nel plugin al momento della creazione del progetto demo (se "
            "necessiti di re-importarlo, trovi il file nella cartella e puoi "
            "caricarlo dalla scheda Prezziari).\n"
            "3. Seleziona uno dei layer demo: cm_punti, cm_linee, "
            "cm_poligoni.\n"
            "4. Verifica il mapping dei campi (il plugin rileva "
            "automaticamente 'item_code', 'descrizione', 'spessore_m', "
            "ecc.).\n"
            "5. Clicca su 'Calcola Computo e Risultati' per generare il "
            "computo e vedere il dettaglio delle quantità misurate e dei "
            "costi.\n\n"
            "COME VENGONO CALCOLATE LE QUANTITA' E I COSTI:\n"
            "Il motore di calcolo legge l'Unità di Misura (UM) della voce del "
            "prezziario (oppure dal campo 'unita_override') e applica "
            "automaticamente le seguenti regole:\n\n"
            "1. Superfici (mq, ha):\n"
            "   - Poligoni: calcola l'Area geometrica reale nel CRS "
            "proiettato del progetto.\n"
            "   - Linee: calcola Lunghezza tracciato × larghezza_m.\n"
            "   - Punti: calcola larghezza_m × altezza_m.\n\n"
            "2. Lunghezze (ml, km):\n"
            "   - Linee: calcola la Lunghezza reale del tracciato.\n"
            "   - Poligoni: calcola il Perimetro del poligono.\n\n"
            "3. Volumi (mc):\n"
            "   - Poligoni: calcola Area geometrica × spessore_m (oppure "
            "altezza_m).\n"
            "     * Esempio operativo nel layer demo cm_poligoni "
            "(DEM-AREA-001 in mc):\n"
            "       L'area del poligono misurata da QGIS è esattamente 1.200 "
            "mq (40m x 30m).\n"
            "       Poiché la voce di prezziario richiede metri cubi (mc) e "
            "il campo 'spessore_m' è impostato a 0,12 m:\n"
            "       Quantità calcolata = 1.200 mq × 0,12 m = 144,00 mc.\n"
            "       Costo totale feature = 144,00 mc × 85,00 €/mc = 12.240,00 "
            "€.\n"
            "   - Linee: calcola Lunghezza × larghezza_m × "
            "spessore/altezza_m.\n"
            "   - Punti: calcola larghezza_m × altezza_m × spessore_m.\n\n"
            "4. A corpo / Pezzi (cad):\n"
            "   - Punti/Linee/Poligoni: legge il campo 'pezzi' (se vuoto o "
            "zero, vale 1 pezzo per ogni feature GIS).\n\n"
            "5. Sovrascrittura Manuale ('quantita_man'):\n"
            "   - Se per una feature il campo 'quantita_man' è valorizzato "
            "(es. 50.5), questo valore sostituisce del tutto il calcolo "
            "geometrico.\n\n"
            "Moltiplicatore ('coefficiente'):\n"
            "Qualsiasi quantità ricavata (geometrica o manuale) viene "
            "moltiplicata per il campo 'coefficiente' (es. per considerare "
            "quote parti, sfridi o ripetizioni. Se vuoto o 1.0, non altera il "
            "valore).\n\n"
            "Campi principali presenti nei layer demo:\n"
            "- item_code: codice voce del prezziario (obbligatorio)\n"
            "- descrizione: testo opzionale da usare nel report\n"
            "- categoria: raggruppamento opzionale\n"
            "- coefficiente: moltiplicatore numerico opzionale\n"
            "- quantita_man: quantità manuale (se valorizzata, sovrascrive la "
            "misura geometrica)\n"
            "- unita_override: consente di forzare l'UM per la singola "
            "feature\n"
            "- larghezza_m / altezza_m / spessore_m: dimensioni geometriche "
            "integrative per sezioni, aree o volumi\n"
            "- pezzi: per quantità a cad integrate\n"
            "- note: annotazioni (dove il plugin riporta anche la spiegazione "
            "esatta del calcolo effettuato)\n\n"
            "Nota sul CRS (Sistema di Riferimento Coordinate):\n"
            "Il progetto demo usa EPSG:32633 come esempio metrico proiettato, "
            "fondamentale affinché le misure lineari e di superficie in QGIS "
            "siano esatte in metri e metri quadri.\n"
        )
        Path(instructions_path).write_text(content, encoding="utf-8")

    def _write_demo_price_list(self, output_dir: str) -> str:
        csv_path = os.path.join(output_dir, "prezziario_demo.csv")
        rows = [
            [
                "codice",
                "descrizione",
                "um",
                "prezzo_unitario",
                "categoria",
                "note",
            ],
            [
                "DEM-POINT-001",
                "Picchetto topografico",
                "cad",
                "85,00",
                "Rilievo",
                "Voce a corpo su punto",
            ],
            [
                "DEM-LINE-001",
                "Recinzione metallica",
                "ml",
                "54,80",
                "Opere lineari",
                "Sviluppo misurato da linea",
            ],
            [
                "DEM-AREA-001",
                "Pavimentazione drenante con sottofondo",
                "mc",
                "85,00",
                "Superfici",
                "Volume da area x spessore",
            ],
        ]
        with open(csv_path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerows(rows)
        return csv_path

    def _demo_report_profile(self) -> ReportProfile:
        return ReportProfile(
            title="Demo computo metrico estimativo",
            subtitle="Esempio operativo completo generato dal plugin",
            organization="Computo Metrico GIS",
            logo_path=os.path.join(self.plugin_dir, "assets", "icon.svg"),
            footer_text=(
                "Documento demo generato automaticamente dal progetto di "
                "esempio."),
            include_map=False,
            map_title="Mappa demo",
            references=[
                ReportReference(
                    label="Progetto", value="Computo metrico demo"
                ),
                ReportReference(
                    label="Prezziario", value="prezziario_demo.csv"
                ),
                ReportReference(
                    label="Uso",
                    value="Esempio completo di computo e contabilita",
                ),
            ],
        )

    def _demo_summary_rows(self) -> list[dict]:
        return [
            {
                "code": "DEM-POINT-001",
                "description": "Picchetto topografico",
                "unit": "cad",
                "quantity": 1.0,
                "unit_price": 85.0,
                "total_price": 85.0,
                "category": "Rilievo",
            },
            {
                "code": "DEM-LINE-001",
                "description": "Recinzione metallica",
                "unit": "ml",
                "quantity": 190.56,
                "unit_price": 54.8,
                "total_price": 10442.69,
                "category": "Opere lineari",
            },
            {
                "code": "DEM-AREA-001",
                "description": "Pavimentazione drenante con sottofondo",
                "unit": "mc",
                "quantity": 144.0,
                "unit_price": 85.0,
                "total_price": 12240.0,
                "category": "Superfici",
            },
        ]

    def _demo_detail_rows(self) -> list[dict]:
        return [
            {
                "layer_name": "cm_punti",
                "feature_id": 1,
                "geometry_type": "Point",
                "price_code": "DEM-POINT-001",
                "description": "Picchetto topografico",
                "unit": "cad",
                "quantity": 1.0,
                "unit_price": 85.0,
                "total_price": 85.0,
                "category": "Rilievo",
                "note": "Voce a corpo per singolo punto",
            },
            {
                "layer_name": "cm_linee",
                "feature_id": 1,
                "geometry_type": "LineString",
                "price_code": "DEM-LINE-001",
                "description": "Recinzione metallica",
                "unit": "ml",
                "quantity": 190.56,
                "unit_price": 54.8,
                "total_price": 10442.69,
                "category": "Opere lineari",
                "note": "Lunghezza letta dalla geometria",
            },
            {
                "layer_name": "cm_poligoni",
                "feature_id": 1,
                "geometry_type": "Polygon",
                "price_code": "DEM-AREA-001",
                "description": "Pavimentazione drenante con sottofondo",
                "unit": "mc",
                "quantity": 144.0,
                "unit_price": 85.0,
                "total_price": 12240.0,
                "category": "Superfici",
                "note": "Volume da area x spessore 0.12 m",
            },
        ]

    def _write_demo_outputs(self, output_dir: str) -> dict[str, str]:
        output_demo_dir = os.path.join(output_dir, "output_demo")
        Path(output_demo_dir).mkdir(parents=True, exist_ok=True)

        metadata = ReportMetadata(
            run_id=1,
            layer_name="cm_punti, cm_linee, cm_poligoni",
            price_list_name="prezziario_demo.csv",
            crs_authid=self.crs.authid(),
            generated_at="demo",
            notes="Output dimostrativo generato automaticamente.",
        )
        profile = self._demo_report_profile()
        summary_rows = self._demo_summary_rows()
        detail_rows = self._demo_detail_rows()

        computo_pdf = os.path.join(output_demo_dir, "computo_demo.pdf")
        computo_xlsx = os.path.join(output_demo_dir, "computo_demo.xlsx")
        contabilita_pdf = os.path.join(output_demo_dir, "contabilita_demo.pdf")
        contabilita_xlsx = os.path.join(
            output_demo_dir, "contabilita_demo.xlsx"
        )

        report_html = build_report_html(
            metadata, summary_rows, detail_rows, profile=profile
        )
        export_pdf(computo_pdf, report_html)
        export_xlsx(
            computo_xlsx, metadata, summary_rows, detail_rows, profile=profile
        )

        sal_record = {
            "sal_number": 1,
            "sal_date": "demo",
            "security_costs": 450.0,
            "retention_percent": 0.5,
            "vat_percent": 22.0,
            "previous_paid": 0.0,
            "notes": "SAL dimostrativo generato automaticamente.",
        }
        journal_entries = [
            {
                "work_date": "demo",
                "title": "Avvio cantiere",
                "weather": "Sereno",
                "workers": "3 operatori",
                "description": (
                    "Installazione picchetti, recinzione e lavorazioni di "
                    "superficie."),
            }
        ]
        accounting_html = build_accounting_html(
            metadata,
            summary_rows,
            detail_rows,
            sal_record,
            journal_entries,
            profile=profile,
        )
        export_pdf(contabilita_pdf, accounting_html)
        export_accounting_xlsx(
            contabilita_xlsx,
            metadata,
            summary_rows,
            detail_rows,
            sal_record,
            journal_entries,
            profile=profile,
        )

        return {
            "demo_output_dir": output_demo_dir,
            "computo_pdf": computo_pdf,
            "computo_xlsx": computo_xlsx,
            "contabilita_pdf": contabilita_pdf,
            "contabilita_xlsx": contabilita_xlsx,
        }

    def create(self, output_dir: str) -> dict[str, str]:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        gpkg_path = os.path.join(output_dir, "computo_metrico_demo.gpkg")
        project_path = os.path.join(output_dir, "computo_metrico_demo.qgs")
        csv_path = os.path.join(output_dir, "prezziario_template.csv")

        if os.path.exists(gpkg_path):
            os.remove(gpkg_path)
        if os.path.exists(project_path):
            os.remove(project_path)

        for index, layer in enumerate(self._sample_layers()):
            self._write_layer(layer, gpkg_path, overwrite_file=index == 0)

        self._build_project(project_path, gpkg_path)
        shutil.copyfile(
            os.path.join(
                self.plugin_dir, "templates", "prezziario_template.csv"
            ),
            csv_path,
        )
        demo_price_list_path = self._write_demo_price_list(output_dir)
        self._write_instructions(output_dir)
        demo_outputs = self._write_demo_outputs(output_dir)

        result = {
            "project_path": project_path,
            "gpkg_path": gpkg_path,
            "csv_path": csv_path,
            "demo_price_list_path": demo_price_list_path,
            "instructions_path": os.path.join(
                output_dir, "ISTRUZIONI_PROGETTO.txt"
            ),
        }
        result.update(demo_outputs)
        return result
