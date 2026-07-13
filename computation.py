from dataclasses import dataclass

from qgis.core import QgsDistanceArea, QgsGeometry, QgsProject, QgsWkbTypes

from .models import MeasurementItem, PriceItem
from .price_parser import normalize_unit

FIELD_HINTS = {
    "code": ("item_code", "codice", "code", "voce", "articolo"),
    "description": (
        "descrizione",
        "description",
        "voce_desc",
        "voce_descrizione",
    ),
    "category": ("categoria", "category", "capitolo", "gruppo"),
    "quantity": ("quantita_man", "quantita", "qty", "quantity", "qta"),
    "coefficient": ("coefficiente", "coef", "coeff", "moltiplicatore"),
    "notes": ("note", "notes", "osservazioni"),
    "unit_override": ("unita_override", "unita", "unit", "um"),
    "width": ("larghezza_m", "larghezza", "width_m", "width"),
    "height": ("altezza_m", "altezza", "height_m", "height"),
    "thickness": ("spessore_m", "spessore", "thickness_m", "thickness"),
    "pieces": ("pezzi", "pieces", "numero_pezzi", "n_pezzi", "pezzi_n"),
}

AREA_UNITS = {"mq", "ha"}
LENGTH_UNITS = {"ml", "km"}
COUNT_UNITS = {"cad"}
VOLUME_UNITS = {"mc"}


def _text_value(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"none", "null"} else text


@dataclass
class MappingConfig:
    code_field: str
    description_field: str = ""
    category_field: str = ""
    quantity_field: str = ""
    coefficient_field: str = ""
    notes_field: str = ""
    unit_override_field: str = ""
    width_field: str = ""
    height_field: str = ""
    thickness_field: str = ""
    pieces_field: str = ""


def guess_field_name(layer, role: str) -> str:
    candidates = FIELD_HINTS.get(role, ())
    available = {
        field.name().lower(): field.name() for field in layer.fields()
    }
    for candidate in candidates:
        if candidate.lower() in available:
            return available[candidate.lower()]
    return ""


def _numeric_value(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


class LayerComputationEngine:
    def __init__(self, project=None):
        self.project = project or QgsProject.instance()
        self.distance_area = QgsDistanceArea()
        self.distance_area.setSourceCrs(
            self.project.crs(),
            self.project.transformContext(),
        )
        ellipsoid = self.project.ellipsoid() or "WGS84"
        self.distance_area.setEllipsoid(ellipsoid)

    def validate_mapping(self, layer, mapping: MappingConfig) -> list[str]:
        warnings: list[str] = []
        field_names = {field.name() for field in layer.fields()}
        if not mapping.code_field or mapping.code_field not in field_names:
            warnings.append(
                "Il layer deve avere un campo codice voce. Campo consigliato: "
                "item_code."
            )
        for label, field_name in (
            ("descrizione", mapping.description_field),
            ("categoria", mapping.category_field),
            ("quantità manuale", mapping.quantity_field),
            ("coefficiente", mapping.coefficient_field),
            ("note", mapping.notes_field),
            ("unità override", mapping.unit_override_field),
            ("larghezza", mapping.width_field),
            ("altezza", mapping.height_field),
            ("spessore", mapping.thickness_field),
            ("pezzi", mapping.pieces_field),
        ):
            if field_name and field_name not in field_names:
                warnings.append(
                    f"Il campo {label} selezionato non esiste nel layer."
                )
        return warnings

    def _measurement_for_geometry(
        self,
        geometry: QgsGeometry,
        unit: str,
        width: float | None = None,
        height: float | None = None,
        thickness: float | None = None,
        pieces: float | None = None,
    ) -> float:
        normalized_unit = normalize_unit(unit)
        if normalized_unit in AREA_UNITS:
            geom_type = QgsWkbTypes.geometryType(geometry.wkbType())
            if geom_type == QgsWkbTypes.LineGeometry and width and width > 0:
                area = self.distance_area.measureLength(geometry) * width
                return area / 10000.0 if normalized_unit == "ha" else area
            if geom_type == QgsWkbTypes.PointGeometry and width and height:
                area = width * height
                return area / 10000.0 if normalized_unit == "ha" else area
            area = self.distance_area.measureArea(geometry)
            return area / 10000.0 if normalized_unit == "ha" else area
        if normalized_unit in LENGTH_UNITS:
            if (
                QgsWkbTypes.geometryType(geometry.wkbType())
                == QgsWkbTypes.PolygonGeometry
            ):
                length = self.distance_area.measurePerimeter(geometry)
            else:
                length = self.distance_area.measureLength(geometry)
            return length / 1000.0 if normalized_unit == "km" else length
        if normalized_unit in COUNT_UNITS:
            return pieces if pieces and pieces > 0 else 1.0
        if normalized_unit in VOLUME_UNITS:
            geom_type = QgsWkbTypes.geometryType(geometry.wkbType())
            section_height = height or thickness
            if (
                geom_type == QgsWkbTypes.PolygonGeometry
                and section_height
                and section_height > 0
            ):
                return (
                    self.distance_area.measureArea(geometry) * section_height
                )
            if (
                geom_type == QgsWkbTypes.LineGeometry
                and width
                and width > 0
                and section_height
                and section_height > 0
            ):
                return (
                    self.distance_area.measureLength(geometry)
                    * width
                    * section_height
                )
            if (
                geom_type == QgsWkbTypes.PointGeometry
                and width
                and height
                and thickness
            ):
                return width * height * thickness
            return 0.0
        return 0.0

    def compute_layer(
        self, layer, mapping: MappingConfig, price_lookup: dict[str, PriceItem]
    ):
        warnings = self.validate_mapping(layer, mapping)
        items: list[MeasurementItem] = []

        self.distance_area.setSourceCrs(
            layer.crs(), self.project.transformContext()
        )
        geometry_type_name = QgsWkbTypes.displayString(layer.wkbType())

        for feature in layer.getFeatures():
            code = (
                _text_value(feature[mapping.code_field])
                if mapping.code_field
                else ""
            )
            if not code:
                warnings.append(
                    f"Feature {feature.id()}: codice voce mancante, elemento "
                    f"saltato."
                )
                continue

            price_item = price_lookup.get(code)
            unit_override = ""
            if mapping.unit_override_field:
                unit_override = _text_value(
                    feature[mapping.unit_override_field]
                )

            unit = normalize_unit(
                unit_override or (price_item.unit if price_item else "cad")
            )
            width = (
                _numeric_value(feature[mapping.width_field])
                if mapping.width_field
                else None
            )
            height = (
                _numeric_value(feature[mapping.height_field])
                if mapping.height_field
                else None
            )
            thickness = (
                _numeric_value(feature[mapping.thickness_field])
                if mapping.thickness_field
                else None
            )
            pieces = (
                _numeric_value(feature[mapping.pieces_field])
                if mapping.pieces_field
                else None
            )
            description = (
                _text_value(feature[mapping.description_field])
                if mapping.description_field
                else ""
            ) or (price_item.description if price_item else code)
            category = (
                _text_value(feature[mapping.category_field])
                if mapping.category_field
                else ""
            ) or (price_item.category if price_item else "")
            note = (
                _text_value(feature[mapping.notes_field])
                if mapping.notes_field
                else ""
            )
            unit_price = price_item.unit_price if price_item else 0.0

            quantity = None
            calc_reason = ""
            if mapping.quantity_field:
                raw_quantity = feature[mapping.quantity_field]
                if raw_quantity not in (None, ""):
                    try:
                        quantity = float(raw_quantity)
                        calc_reason = (
                            f"[Calcolo: quantità manuale da campo = "
                            f"{round(quantity, 4)} {unit}]")
                    except Exception:
                        warnings.append(
                            f"Feature {feature.id()}: quantità manuale non "
                            f"numerica, uso la geometria."
                        )
                        quantity = None

            if quantity is None:
                geometry = feature.geometry()
                if not geometry or geometry.isEmpty():
                    warnings.append(
                        f"Feature {feature.id()}: geometria assente, "
                        f"impossibile misurare."
                    )
                    quantity = 0.0
                    calc_reason = "[Calcolo: geometria assente, Qta = 0]"
                else:
                    quantity = self._measurement_for_geometry(
                        geometry,
                        unit,
                        width=width,
                        height=height,
                        thickness=thickness,
                        pieces=pieces,
                    )
                    section_h = height or thickness
                    if unit in AREA_UNITS:
                        if (
                            QgsWkbTypes.geometryType(geometry.wkbType())
                            == QgsWkbTypes.LineGeometry
                            and width
                        ):
                            calc_reason = (
                                f"[Calcolo: Superficie da Lunghezza x "
                                f"Larghezza ({width} m) = "
                                f"{round(quantity, 4)} {unit}]")
                        else:
                            calc_reason = (
                                f"[Calcolo: Area misurata dalla geometria = "
                                f"{round(quantity, 4)} {unit}]")
                    elif unit in LENGTH_UNITS:
                        if (
                            QgsWkbTypes.geometryType(geometry.wkbType())
                            == QgsWkbTypes.PolygonGeometry
                        ):
                            calc_reason = (
                                f"[Calcolo: Perimetro del poligono = "
                                f"{round(quantity, 4)} {unit}]")
                        else:
                            calc_reason = (
                                f"[Calcolo: Lunghezza misurata dal tracciato "
                                f"= {round(quantity, 4)} {unit}]")
                    elif unit in VOLUME_UNITS:
                        if (
                            QgsWkbTypes.geometryType(geometry.wkbType())
                            == QgsWkbTypes.PolygonGeometry
                            and section_h
                        ):
                            calc_reason = (
                                f"[Calcolo: Volume da Area geometria x "
                                f"Spessore/Altezza ({section_h} m) = "
                                f"{round(quantity, 4)} {unit}]")
                        elif (
                            QgsWkbTypes.geometryType(geometry.wkbType())
                            == QgsWkbTypes.LineGeometry
                            and width
                            and section_h
                        ):
                            calc_reason = (
                                f"[Calcolo: Volume da Lunghezza x Larghezza "
                                f"({width} m) x Spessore/Altezza ({section_h} "
                                f"m) = {round(quantity, 4)} {unit}]")
                        else:
                            calc_reason = (
                                f"[Calcolo: Volume non ricavabile senza "
                                f"spessore/altezza per l'unità {unit}]")
                    elif unit in COUNT_UNITS:
                        calc_reason = (
                            f"[Calcolo: A corpo / Pezzi = "
                            f"{round(quantity, 4)} {unit}]")
                    else:
                        calc_reason = f"[Calcolo: {round(quantity, 4)} {unit}]"

            coefficient = 1.0
            if mapping.coefficient_field:
                raw_coefficient = feature[mapping.coefficient_field]
                if raw_coefficient not in (None, ""):
                    try:
                        coefficient = float(raw_coefficient)
                        if coefficient != 1.0:
                            calc_reason += f" (x coeff. {coefficient})"
                    except Exception:
                        warnings.append(
                            f"Feature {feature.id()}: coefficiente non "
                            f"numerico, uso 1.0."
                        )

            if unit in VOLUME_UNITS and quantity == 0.0:
                warnings.append(
                    f"Feature {feature.id()}: unità '{unit}' richiede "
                    f"quantità manuale o campi larghezza/altezza/spessore."
                )

            final_quantity = round(quantity * coefficient, 4)
            total_price = round(final_quantity * unit_price, 2)

            if not price_item:
                note = (
                    note + " | " if note else ""
                ) + "Codice non presente nel prezziario attivo"
                warnings.append(
                    f"Feature {feature.id()}: codice '{code}' non trovato nel "
                    f"prezziario."
                )

            full_note = (
                f"{note} | {calc_reason}".strip(" |") if note else calc_reason
            )

            items.append(
                MeasurementItem(
                    layer_name=layer.name(),
                    feature_id=int(feature.id()),
                    geometry_type=geometry_type_name,
                    price_code=code,
                    description=description,
                    unit=unit,
                    quantity=final_quantity,
                    unit_price=unit_price,
                    total_price=total_price,
                    category=category,
                    note=full_note,
                )
            )

        return items, warnings
