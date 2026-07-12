from zipfile import ZipFile

from COMPUTO.price_parser import PriceListFormatError, normalize_price_rows, parse_decimal
from COMPUTO.xlsx_utils import write_workbook


def test_parse_decimal_supports_it_and_en_formats():
    assert parse_decimal("36,20") == 36.20
    assert parse_decimal("1.234,56") == 1234.56
    assert parse_decimal("1234.56") == 1234.56


def test_normalize_price_rows_accepts_alias_headers():
    rows = [
        ["code", "description", "unit", "price", "category"],
        ["A-001", "Voce test", "mq", "12,50", "Capitolo 1"],
    ]
    price_list = normalize_price_rows(rows, list_name="Test")
    assert price_list.name == "Test"
    assert len(price_list.items) == 1
    assert price_list.items[0].unit == "mq"
    assert price_list.items[0].unit_price == 12.50


def test_normalize_price_rows_reports_missing_columns():
    rows = [
        ["codice", "descrizione", "categoria"],
        ["A-001", "Voce test", "Capitolo 1"],
    ]
    try:
        normalize_price_rows(rows)
    except PriceListFormatError as exc:
        assert "Campi mancanti" in exc.details
    else:  # pragma: no cover - explicit failure branch
        raise AssertionError("Expected PriceListFormatError")


def test_normalize_price_rows_accepts_official_structured_headers():
    rows = [
        ["codice", "articolo", "um", "TOTALE_GENERALE", "tipologia", "voce"],
        ["BAS2026/A.01.001.01", "Veicolo a caldo", "ora", "63.29", "NOLEGGI", "Veicolo peso totale:"],
    ]
    price_list = normalize_price_rows(rows, list_name="Basilicata 2026")
    assert price_list.items[0].code == "BAS2026/A.01.001.01"
    assert price_list.items[0].description == "Veicolo a caldo"
    assert price_list.items[0].unit_price == 63.29
    assert "NOLEGGI" in price_list.items[0].category


def test_load_price_list_from_zip_with_xlsx(tmp_path):
    xlsx_path = tmp_path / "prezziario.xlsx"
    zip_path = tmp_path / "prezziario.zip"
    write_workbook(
        xlsx_path,
        [("Computo", [["codice", "descrizione", "um", "prezzo_unitario"], ["A-001", "Voce test", "mq", 12.5]])],
    )
    with ZipFile(zip_path, "w") as archive:
        archive.write(xlsx_path, arcname="cartella/prezziario.xlsx")

    from COMPUTO.price_parser import load_price_list

    price_list = load_price_list(zip_path)
    assert price_list.source_path.endswith(".zip")
    assert price_list.items[0].code == "A-001"
