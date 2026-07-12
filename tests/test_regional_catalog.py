from pathlib import Path

from COMPUTO.regional_catalog import ensure_manual_template, load_regional_catalog


def test_load_regional_catalog_includes_bundled_basilicata():
    plugin_dir = Path(__file__).resolve().parents[1]
    entries = load_regional_catalog(str(plugin_dir), "")
    basilicata = next(entry for entry in entries if entry.key == "basilicata")

    assert basilicata.status == "bundled"
    assert basilicata.item_count > 1000
    assert basilicata.local_dataset.endswith("basilicata_2026_lavorazioni.csv")


def test_ensure_manual_template_creates_csv_and_readme(tmp_path: Path):
    plugin_dir = Path(__file__).resolve().parents[1]
    entry = next(entry for entry in load_regional_catalog(str(plugin_dir), "") if entry.key == "calabria")

    created = ensure_manual_template(str(tmp_path), entry)
    csv_text = Path(created["csv_path"]).read_text(encoding="utf-8")
    readme_text = Path(created["readme_path"]).read_text(encoding="utf-8")

    assert "codice;descrizione;um;prezzo_unitario;categoria;note" in csv_text
    assert "Calabria" in readme_text
