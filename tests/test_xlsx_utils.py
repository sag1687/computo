from pathlib import Path

from COMPUTO.xlsx_utils import read_first_sheet, write_workbook


def test_write_and_read_workbook_roundtrip(tmp_path: Path):
    path = tmp_path / "sample.xlsx"
    write_workbook(
        path,
        [("Computo", [["Codice", "Prezzo"], ["A-001", 12.5], ["A-002", 48]])],
    )

    rows = read_first_sheet(path)
    assert rows[0] == ["Codice", "Prezzo"]
    assert rows[1][0] == "A-001"
    assert rows[1][1] == "12.5"
