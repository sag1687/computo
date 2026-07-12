import csv
import json
from dataclasses import dataclass
from pathlib import Path

from .bundled_datasets import BUNDLED_DATASETS
from .price_parser import EXPECTED_HEADERS, format_expectations_text
from .regional_sources import REGIONAL_SOURCES


STATUS_LABELS = {
    "bundled": "Dataset pronto",
    "manual_required": "Conversione manuale",
    "unresolved": "Portale censito",
}

STATUS_COLORS = {
    "bundled": "#2e8b57",
    "manual_required": "#c58b2b",
    "unresolved": "#5b7aa0",
}


@dataclass(frozen=True)
class RegionalCatalogEntry:
    key: str
    name: str
    homepage: str
    status: str = "unresolved"
    notes: str = ""
    source_page: str = ""
    update_url: str = ""
    local_dataset: str = ""
    local_download: str = ""
    item_count: int = 0
    format: str = ""
    bundled_key: str = ""

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status or "Sconosciuto")

    @property
    def status_color(self) -> str:
        return STATUS_COLORS.get(self.status, "#5b7aa0")

    @property
    def action_hint(self) -> str:
        if self.status == "bundled":
            return "Importa dataset pronto"
        if self.status == "manual_required":
            return "Scarica e compila template"
        return "Apri portale e verifica"


def _normalize_name(text: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in text).strip("-")


def _load_catalog_file(plugin_dir: str) -> dict[str, dict]:
    path = Path(plugin_dir) / "data" / "regions_catalog.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {entry["key"]: entry for entry in data}


def _bundled_by_source_key() -> dict[str, object]:
    lookup: dict[str, object] = {}
    for dataset in BUNDLED_DATASETS:
        key = _normalize_name(dataset.region)
        lookup[key] = dataset
    return lookup


def _latest_download(download_dir: str, source_key: str) -> str:
    if not download_dir:
        return ""
    folder = Path(download_dir) / source_key
    if not folder.exists():
        return ""
    files = [path for path in folder.iterdir() if path.is_file()]
    if not files:
        return ""
    latest = max(files, key=lambda path: path.stat().st_mtime)
    return str(latest)


def resolve_relative_path(plugin_dir: str, relative_path: str) -> str:
    if not relative_path:
        return ""
    candidate = Path(plugin_dir) / relative_path
    return str(candidate) if candidate.exists() else ""


def _count_dataset_items(path: str) -> int:
    if not path:
        return 0
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return max(sum(1 for _ in handle) - 1, 0)
    except OSError:
        return 0


def load_regional_catalog(plugin_dir: str, download_dir: str = "") -> list[RegionalCatalogEntry]:
    catalog_data = _load_catalog_file(plugin_dir)
    bundled_lookup = _bundled_by_source_key()
    entries: list[RegionalCatalogEntry] = []

    for source in REGIONAL_SOURCES:
        raw = dict(catalog_data.get(source.key, {}))
        dataset = bundled_lookup.get(source.key)

        status = raw.get("status") or "unresolved"
        source_page = raw.get("source_page") or source.homepage
        update_url = raw.get("update_url") or ""
        local_dataset = resolve_relative_path(plugin_dir, raw.get("local_dataset", ""))
        local_download = resolve_relative_path(plugin_dir, raw.get("local_download", ""))

        if not local_download:
            local_download = _latest_download(download_dir, source.key)

        if dataset:
            local_dataset = str(Path(plugin_dir) / dataset.relative_path)
            source_page = dataset.source_page or source_page
            update_url = dataset.update_url or update_url
            status = "bundled"
            raw["notes"] = dataset.notes or raw.get("notes", "")
            raw["item_count"] = raw.get("item_count") or _count_dataset_items(local_dataset)

        if status != "manual_required" and local_download.endswith(".pdf") and not update_url:
            local_download = ""

        entries.append(
            RegionalCatalogEntry(
                key=source.key,
                name=raw.get("name") or source.name,
                homepage=raw.get("homepage") or source.homepage,
                status=status,
                notes=raw.get("notes", ""),
                source_page=source_page,
                update_url=update_url,
                local_dataset=local_dataset,
                local_download=local_download,
                item_count=int(raw.get("item_count") or 0),
                format=raw.get("format") or Path(local_download).suffix.lower(),
                bundled_key=getattr(dataset, "key", ""),
            )
        )

    return sorted(entries, key=lambda entry: entry.name.lower())


def ensure_manual_template(output_dir: str, entry: RegionalCatalogEntry) -> dict[str, str]:
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)

    csv_path = folder / f"{entry.key}_prezziario_template.csv"
    readme_path = folder / f"{entry.key}_prezziario_template_README.txt"

    if not csv_path.exists():
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(EXPECTED_HEADERS.split(";"))

    if not readme_path.exists():
        readme_path.write_text(
            "\n".join(
                [
                    f"Template manuale per {entry.name}",
                    "",
                    "Compila il CSV usando il formato seguente:",
                    format_expectations_text(),
                    "",
                    f"Pagina ufficiale: {entry.source_page or entry.homepage}",
                    f"Download / aggiornamento: {entry.update_url or 'non disponibile'}",
                    "",
                    "Nota: il template contiene solo l'intestazione per evitare import fittizi.",
                ]
            ),
            encoding="utf-8",
        )

    return {
        "csv_path": str(csv_path),
        "readme_path": str(readme_path),
    }
