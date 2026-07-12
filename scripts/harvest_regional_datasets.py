import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = ROOT.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from COMPUTO.price_parser import PriceListFormatError, load_price_list  # noqa: E402
from COMPUTO.regional_sources import RegionalPriceListService  # noqa: E402


OUTPUT_CATALOG = ROOT / "data" / "regions_catalog.json"
RAW_DIR = ROOT / "data" / "raw_harvest"
BUNDLED_DIR = ROOT / "data" / "bundled"


def slug_name(text: str) -> str:
    safe = "".join(char.lower() if char.isalnum() else "_" for char in text)
    while "__" in safe:
        safe = safe.replace("__", "_")
    return safe.strip("_")


def write_normalized_csv(price_list, output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["codice", "descrizione", "um", "prezzo_unitario", "categoria", "note"])
        for item in price_list.items:
            writer.writerow(
                [
                    item.code,
                    item.description,
                    item.unit,
                    item.unit_price,
                    item.category,
                    item.notes,
                ]
            )
    return len(price_list.items)


def main():
    service = RegionalPriceListService(request_timeout=12, max_search_candidates=4)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    BUNDLED_DIR.mkdir(parents=True, exist_ok=True)

    catalog: list[dict] = []
    for source in service.list_sources():
        entry = {
            "key": source.key,
            "name": source.name,
            "homepage": source.homepage,
            "status": "unresolved",
            "notes": "",
            "source_page": "",
            "update_url": "",
            "local_dataset": "",
            "local_download": "",
            "item_count": 0,
            "format": "",
        }

        try:
            result = service.download_latest(source.key, str(RAW_DIR))
            entry["source_page"] = str(result["page_url"])
            entry["update_url"] = str(result["file_url"])
            entry["local_download"] = str(Path(result["file_path"]).relative_to(ROOT))
            entry["format"] = str(result["file_extension"])

            if result["importable"]:
                try:
                    price_list = load_price_list(result["file_path"], source_url=result["file_url"])
                    csv_name = f"{source.key}_{slug_name(source.name)}.csv"
                    local_dataset = BUNDLED_DIR / csv_name
                    count = write_normalized_csv(price_list, local_dataset)
                    entry["status"] = "bundled"
                    entry["local_dataset"] = str(local_dataset.relative_to(ROOT))
                    entry["item_count"] = count
                    entry["notes"] = "Dataset ufficiale scaricato e normalizzato automaticamente."
                except (PriceListFormatError, Exception) as exc:
                    entry["status"] = "manual_required"
                    entry["notes"] = (
                        "File ufficiale scaricato ma non convertibile in modo affidabile. "
                        f"Dettaglio: {exc}"
                    )
            else:
                entry["status"] = "manual_required"
                entry["notes"] = (
                    "Il portale ufficiale pubblica un formato non importabile in automatico "
                    f"({entry['format']})."
                )
        except Exception as exc:
            entry["status"] = "unresolved"
            entry["notes"] = f"Risoluzione automatica non riuscita: {exc}"

        catalog.append(entry)
        print(f"{source.name}: {entry['status']}", flush=True)

    OUTPUT_CATALOG.write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Catalogo scritto in {OUTPUT_CATALOG}", flush=True)


if __name__ == "__main__":
    main()
