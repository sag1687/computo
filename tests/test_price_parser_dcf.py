import sqlite3
from pathlib import Path

from COMPUTO.price_parser import PriceListFormatError, load_price_list


def test_load_price_list_from_sqlite_dcf(tmp_path: Path):
    dcf_path = tmp_path / "prezziario.dcf"
    connection = sqlite3.connect(dcf_path)
    try:
        connection.execute(
            """
            CREATE TABLE prezziario (
                codice TEXT,
                descrizione TEXT,
                um TEXT,
                prezzo_unitario REAL,
                categoria TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO prezziario(codice, descrizione, um, prezzo_unitario, categoria)
            VALUES ('DCF-001', 'Voce da database', 'mq', 42.5, 'Pavimenti')
            """
        )
        connection.commit()
    finally:
        connection.close()

    price_list = load_price_list(dcf_path)
    assert price_list.items[0].code == "DCF-001"
    assert price_list.items[0].unit_price == 42.5


def test_load_price_list_from_unknown_dcf_raises(tmp_path: Path):
    dcf_path = tmp_path / "ignoto.dcf"
    dcf_path.write_text("contenuto proprietario", encoding="utf-8")

    try:
        load_price_list(dcf_path)
    except PriceListFormatError as exc:
        assert "DCF" in str(exc)
    else:  # pragma: no cover - explicit failure branch
        raise AssertionError("Expected PriceListFormatError")
