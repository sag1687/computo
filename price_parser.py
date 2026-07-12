import csv
import io
import os
import re
import sqlite3
import tempfile
import unicodedata
from pathlib import Path
from zipfile import ZipFile, is_zipfile

from .models import ImportedPriceList, PriceItem
from .xlsx_utils import read_first_sheet


HEADER_ALIASES = {
    "code": {"codice", "code", "item_code", "voce", "cod", "codice_articolo", "codice_pug2024"},
    "description": {"descrizione", "description", "voce_desc", "voce_descrizione", "desc", "articolo"},
    "unit": {"um", "u_m", "unita", "unit", "unita_misura", "misura"},
    "unit_price": {
        "prezzo",
        "prezzo_unitario",
        "unit_price",
        "prezzo_unit",
        "euro",
        "importo",
        "price",
        "totale_generale",
        "prezzo_rilevato",
        "rilev_prezzo",
    },
    "category": {"categoria", "category", "capitolo", "gruppo", "tipologia", "famiglia", "voce"},
    "notes": {"note", "notes", "osservazioni", "np", "tol"},
}

REQUIRED_FIELDS = ("code", "description", "unit", "unit_price")
UNIT_ALIASES = {
    "m2": "mq",
    "mq": "mq",
    "m²": "mq",
    "ha": "ha",
    "m": "ml",
    "ml": "ml",
    "mt": "ml",
    "km": "km",
    "cad": "cad",
    "nr": "cad",
    "n": "cad",
    "pz": "cad",
    "each": "cad",
    "m3": "mc",
    "mc": "mc",
    "m³": "mc",
}

EXPECTED_HEADERS = "codice;descrizione;um;prezzo_unitario;categoria;note"
EXAMPLE_ROW = "DEM-AREA-001;Pavimentazione drenante;mq;36,20;Superfici;Area da geometria"


class PriceListFormatError(ValueError):
    def __init__(self, message: str, details: str = ""):
        super().__init__(message)
        self.details = details


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.lower().strip()
    return re.sub(r"[^a-z0-9]+", "_", ascii_text).strip("_")


def normalize_unit(value: str) -> str:
    key = _normalize_text(value).replace("_", "")
    return UNIT_ALIASES.get(key, value.strip().lower())


def parse_decimal(value: object) -> float:
    if value is None:
        raise ValueError("Valore numerico mancante.")

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        raise ValueError("Valore numerico vuoto.")

    text = text.replace("€", "").replace(" ", "")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(".", "").replace(",", ".")

    return float(text)


def format_expectations_text() -> str:
    return (
        "Formato prezziario atteso:\n"
        f"- intestazione minima: {EXPECTED_HEADERS}\n"
        f"- esempio riga: {EXAMPLE_ROW}\n"
        "- colonne obbligatorie: codice, descrizione, unita di misura, prezzo unitario\n"
        "- colonne opzionali: categoria, note\n"
        "- alias accettati: codice/code/voce, descrizione/description, um/unita/unit, prezzo/prezzo_unitario/unit_price\n"
        "- supporto DCF: solo se il file è realmente leggibile come ZIP, SQLite o tabella uniforme"
    )


def format_expectations_html() -> str:
    return (
        "<h3>Formato atteso del prezziario</h3>"
        "<p>Il plugin accetta CSV e XLSX con intestazioni anche non identiche, "
        "purch&eacute; riconducibili ai campi richiesti.</p>"
        f"<p><b>Intestazione minima:</b> <code>{EXPECTED_HEADERS}</code></p>"
        f"<p><b>Esempio:</b> <code>{EXAMPLE_ROW}</code></p>"
        "<ul>"
        "<li>Colonne obbligatorie: codice, descrizione, um, prezzo unitario.</li>"
        "<li>Colonne opzionali: categoria, note.</li>"
        "<li>Separatore CSV supportato: <code>;</code> o <code>,</code>.</li>"
        "<li>Prezzi supportati con decimale italiano o internazionale: <code>36,20</code> oppure <code>36.20</code>.</li>"
        "<li>DCF supportato solo in modo sperimentale, quando il contenitore espone dati leggibili.</li>"
        "</ul>"
    )


def _map_headers(headers: list[str]) -> dict[str, int]:
    normalized = [_normalize_text(value) for value in headers]
    mapping: dict[str, int] = {}
    for canonical, aliases in HEADER_ALIASES.items():
        for index, header in enumerate(normalized):
            if header == canonical or header in aliases:
                mapping[canonical] = index
                break
    return mapping


def _rows_from_csv(path: str | Path) -> list[list[str]]:
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = Path(path).read_text(encoding="latin-1")
    sample = text[:4096]
    delimiter = ";"
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,")
        delimiter = dialect.delimiter
    except csv.Error:
        pass

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    return [list(row) for row in reader]


def _rows_from_xlsx(path: str | Path) -> list[list[str]]:
    return read_first_sheet(path)


def _rows_from_path(path: str | Path) -> list[list[str]]:
    suffix = Path(path).suffix.lower()
    if suffix == ".csv":
        return _rows_from_csv(path)
    if suffix in {".xlsx", ".xlsm"}:
        return _rows_from_xlsx(path)
    if suffix == ".dcf":
        return _rows_from_dcf(path)
    raise PriceListFormatError(
        "Formato file non supportato.",
        "Usa un file CSV, XLSX oppure DCF leggibile con intestazione riconoscibile.",
    )


def _clean_rows(rows: list[list[object]]) -> list[list[str]]:
    cleaned: list[list[str]] = []
    for row in rows:
        normalized = [str(value).strip() for value in row]
        if any(normalized):
            cleaned.append(normalized)
    return cleaned


def normalize_price_rows(rows: list[list[object]], list_name: str = "Prezziario importato") -> ImportedPriceList:
    cleaned = _clean_rows(rows)
    if len(cleaned) < 2:
        raise PriceListFormatError(
            "Il file non contiene abbastanza righe.",
            format_expectations_text(),
        )

    headers = cleaned[0]
    mapping = _map_headers(headers)
    missing = [field for field in REQUIRED_FIELDS if field not in mapping]
    if missing:
        raise PriceListFormatError(
            "Intestazioni non riconosciute.",
            f"Campi mancanti: {', '.join(missing)}\n\n{format_expectations_text()}",
        )

    errors: list[str] = []
    items: list[PriceItem] = []
    for row_number, row in enumerate(cleaned[1:], start=2):
        try:
            code = row[mapping["code"]].strip()
            description = row[mapping["description"]].strip()
            unit = normalize_unit(row[mapping["unit"]])
            unit_price = parse_decimal(row[mapping["unit_price"]])
            category = row[mapping["category"]].strip() if "category" in mapping and mapping["category"] < len(row) else ""
            notes = row[mapping["notes"]].strip() if "notes" in mapping and mapping["notes"] < len(row) else ""

            if not code or not description or not unit:
                raise ValueError("Codice, descrizione o unità mancanti.")

            items.append(
                PriceItem(
                    code=code,
                    description=description,
                    unit=unit,
                    unit_price=unit_price,
                    category=category,
                    notes=notes,
                )
            )
        except Exception as exc:  # pragma: no cover - aggregated for UI
            errors.append(f"Riga {row_number}: {exc}")

    if errors:
        preview = "\n".join(errors[:10])
        raise PriceListFormatError(
            "Il prezziario contiene righe non uniformi.",
            f"{preview}\n\nCorreggi le righe e usa questo formato:\n{format_expectations_text()}",
        )

    if not items:
        raise PriceListFormatError(
            "Nessuna riga valida trovata nel prezziario.",
            format_expectations_text(),
        )

    return ImportedPriceList(name=list_name, source_type="manuale", items=items)


def load_price_list(path: str | Path, source_url: str = "") -> ImportedPriceList:
    suffix = Path(path).suffix.lower()
    if suffix == ".zip":
        extracted = _extract_supported_from_zip(path)
        price_list = load_price_list(extracted, source_url=source_url)
        price_list.source_path = str(path)
        price_list.notes = (
            f"Importato da archivio ZIP, file interno: {Path(extracted).name}"
        )
        return price_list

    rows = _rows_from_path(path)
    name = Path(path).stem.replace("_", " ").strip() or "Prezziario importato"
    price_list = normalize_price_rows(rows, list_name=name)
    price_list.source_path = str(path)
    price_list.source_url = source_url
    price_list.source_type = "url" if source_url else "file"
    return price_list


def _rows_from_dcf(path: str | Path) -> list[list[str]]:
    if is_zipfile(path):
        extracted = _extract_supported_from_zip(path)
        return _rows_from_path(extracted)

    with open(path, "rb") as handle:
        signature = handle.read(32)

    if signature.startswith(b"SQLite format 3"):
        return _rows_from_sqlite_container(path)

    try:
        rows = _rows_from_csv(path)
        if len(_clean_rows(rows)) >= 2:
            return rows
    except Exception:
        pass

    raise PriceListFormatError(
        "File DCF non importabile automaticamente.",
        "Il file DCF non è un contenitore ZIP, non è un database SQLite leggibile e non espone "
        "una tabella uniforme. Se il DCF è proprietario devi convertirlo in CSV/XLSX prima "
        "dell'import.",
    )


def _rows_from_sqlite_container(path: str | Path) -> list[list[str]]:
    connection = sqlite3.connect(str(path))
    try:
        tables = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type IN ('table', 'view')
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()

        for (table_name,) in tables:
            # Identificatore letto da sqlite_master del file aperto, quotato
            # con escape dei doppi apici (gli identificatori non sono
            # parametrizzabili in SQLite).
            safe_table = str(table_name).replace('"', '""')
            columns = connection.execute(f'PRAGMA table_info("{safe_table}")').fetchall()  # nosec B608
            headers = [str(column[1]) for column in columns]
            mapping = _map_headers(headers)
            if any(field not in mapping for field in REQUIRED_FIELDS):
                continue

            rows = connection.execute(f'SELECT * FROM "{safe_table}"').fetchall()  # nosec B608
            result = [headers]
            for row in rows:
                result.append(
                    [
                        "" if value is None else str(value)
                        for value in row
                    ]
                )
            return result
    finally:
        connection.close()

    raise PriceListFormatError(
        "DCF SQLite non riconosciuto.",
        "Il file DCF contiene un database SQLite ma nessuna tabella con colonne compatibili "
        "con codice, descrizione, um e prezzo unitario.",
    )


def _extract_supported_from_zip(path: str | Path) -> str:
    with ZipFile(path, "r") as archive:
        candidates = [
            name
            for name in archive.namelist()
            if Path(name).suffix.lower() in {".csv", ".xlsx", ".xlsm"}
        ]
        if not candidates:
            raise PriceListFormatError(
                "Archivio ZIP non importabile.",
                "Lo ZIP non contiene file CSV/XLSX/XLSM leggibili dal plugin.",
            )
        preferred = sorted(
            candidates,
            key=lambda name: (
                0 if "lavoraz" in name.lower() or "prezzar" in name.lower() else 1,
                0 if Path(name).suffix.lower() in {".xlsx", ".xlsm"} else 1,
                0 if Path(name).suffix.lower() == ".csv" else 1,
                len(name),
            ),
        )[0]
        suffix = Path(preferred).suffix.lower()
        fd, temp_path = tempfile.mkstemp(prefix="computo_zip_", suffix=suffix)
        os.close(fd)
        Path(temp_path).write_bytes(archive.read(preferred))
        return temp_path
