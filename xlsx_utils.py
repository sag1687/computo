from datetime import datetime, timezone
from html import escape
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile


NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _safe_fromstring(payload: bytes) -> ET.Element:
    """Parse XML rifiutando DTD ed entità (mitigazione XML bomb / XXE).

    I file XLSX legittimi non contengono mai dichiarazioni DOCTYPE/ENTITY.
    """
    lowered = payload.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise ValueError("XML con DTD o entità non consentito nel file XLSX.")
    return ET.fromstring(payload)  # nosec B314 - DTD/entità rifiutate sopra


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _column_index_from_ref(reference: str) -> int:
    letters = "".join(char for char in reference if char.isalpha()).upper()
    index = 0
    for letter in letters:
        index = (index * 26) + (ord(letter) - 64)
    return max(index - 1, 0)


def _column_letters(index: int) -> str:
    result = []
    current = index + 1
    while current:
        current, remainder = divmod(current - 1, 26)
        result.append(chr(65 + remainder))
    return "".join(reversed(result))


def _worksheet_path(zip_file: ZipFile) -> str:
    workbook = _safe_fromstring(zip_file.read("xl/workbook.xml"))
    rels = _safe_fromstring(zip_file.read("xl/_rels/workbook.xml.rels"))

    rel_map = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels
        if _local_name(rel.tag) == "Relationship"
    }

    sheets = [
        element
        for element in workbook.iter()
        if _local_name(element.tag) == "sheet"
    ]
    if not sheets:
        raise ValueError("Il file XLSX non contiene fogli.")

    relation_id = sheets[0].attrib.get(f"{{{NS_REL}}}id")
    if not relation_id or relation_id not in rel_map:
        raise ValueError("Impossibile individuare il primo foglio XLSX.")

    target = rel_map[relation_id].lstrip("/")
    if target.startswith("xl/"):
        return target
    return f"xl/{target}"


def _shared_strings(zip_file: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zip_file.namelist():
        return []

    root = _safe_fromstring(zip_file.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for si in root.iter():
        if _local_name(si.tag) != "si":
            continue
        text_parts = [node.text or "" for node in si.iter() if _local_name(node.tag) == "t"]
        values.append("".join(text_parts))
    return values


def read_first_sheet(path: str | Path) -> list[list[str]]:
    with ZipFile(path, "r") as zip_file:
        shared_strings = _shared_strings(zip_file)
        sheet_path = _worksheet_path(zip_file)
        sheet = _safe_fromstring(zip_file.read(sheet_path))

    rows: list[list[str]] = []
    for row_node in sheet.iter():
        if _local_name(row_node.tag) != "row":
            continue

        row_values: dict[int, str] = {}
        max_index = -1
        for cell in row_node:
            if _local_name(cell.tag) != "c":
                continue

            reference = cell.attrib.get("r", "")
            column_index = _column_index_from_ref(reference)
            max_index = max(max_index, column_index)
            cell_type = cell.attrib.get("t", "")

            value = ""
            value_node = next((node for node in cell if _local_name(node.tag) == "v"), None)
            if cell_type == "inlineStr":
                inline = next((node for node in cell if _local_name(node.tag) == "is"), None)
                if inline is not None:
                    value = "".join(
                        text_node.text or ""
                        for text_node in inline.iter()
                        if _local_name(text_node.tag) == "t"
                    )
            elif value_node is not None:
                raw = value_node.text or ""
                if cell_type == "s":
                    index = int(raw)
                    value = shared_strings[index] if index < len(shared_strings) else ""
                else:
                    value = raw

            row_values[column_index] = value

        if max_index >= 0:
            rows.append([row_values.get(index, "") for index in range(max_index + 1)])

    return rows


def _cell_xml(value: object, row_index: int, column_index: int) -> str:
    reference = f"{_column_letters(column_index)}{row_index}"
    if value is None:
        return f'<c r="{reference}" t="inlineStr"><is><t></t></is></c>'

    if isinstance(value, bool):
        return f"<c r=\"{reference}\" t=\"n\"><v>{1 if value else 0}</v></c>"

    if isinstance(value, (int, float)):
        return f"<c r=\"{reference}\" t=\"n\"><v>{value}</v></c>"

    text = escape(str(value))
    return f"<c r=\"{reference}\" t=\"inlineStr\"><is><t>{text}</t></is></c>"


def _build_sheet_xml(rows: list[list[object]]) -> str:
    xml_rows: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells = "".join(
            _cell_xml(value, row_index, column_index)
            for column_index, value in enumerate(row)
        )
        xml_rows.append(f"<row r=\"{row_index}\">{cells}</row>")

    rows_xml = "".join(xml_rows)
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">"
        f"<sheetData>{rows_xml}</sheetData>"
        "</worksheet>"
    )


def _safe_sheet_name(name: str, index: int) -> str:
    sanitized = (name or f"Foglio{index}")[:31]
    for char in '[]:*?/\\':
        sanitized = sanitized.replace(char, "_")
    return sanitized


def write_workbook(path: str | Path, sheets: list[tuple[str, list[list[object]]]]) -> None:
    if not sheets:
        raise ValueError("Il workbook XLSX deve contenere almeno un foglio.")

    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    workbook_sheets: list[str] = []
    workbook_rels: list[str] = []
    content_types = [
        "<Override PartName=\"/xl/workbook.xml\" "
        "ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/>",
        "<Override PartName=\"/xl/styles.xml\" "
        "ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml\"/>",
        "<Override PartName=\"/docProps/core.xml\" "
        "ContentType=\"application/vnd.openxmlformats-package.core-properties+xml\"/>",
        "<Override PartName=\"/docProps/app.xml\" "
        "ContentType=\"application/vnd.openxmlformats-officedocument.extended-properties+xml\"/>",
    ]

    for sheet_index, (sheet_name, _rows) in enumerate(sheets, start=1):
        sheet_safe_name = escape(_safe_sheet_name(sheet_name, sheet_index))
        workbook_sheets.append(
            f"<sheet name=\"{sheet_safe_name}\" sheetId=\"{sheet_index}\" r:id=\"rId{sheet_index}\"/>"
        )
        workbook_rels.append(
            f"<Relationship Id=\"rId{sheet_index}\" "
            "Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" "
            f"Target=\"worksheets/sheet{sheet_index}.xml\"/>"
        )
        content_types.append(
            f"<Override PartName=\"/xl/worksheets/sheet{sheet_index}.xml\" "
            "ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/>"
        )

    with ZipFile(path, "w", ZIP_DEFLATED) as zip_file:
        zip_file.writestr(
            "_rels/.rels",
            (
                "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
                "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
                "<Relationship Id=\"rId1\" "
                "Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" "
                "Target=\"xl/workbook.xml\"/>"
                "<Relationship Id=\"rId2\" "
                "Type=\"http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties\" "
                "Target=\"docProps/core.xml\"/>"
                "<Relationship Id=\"rId3\" "
                "Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties\" "
                "Target=\"docProps/app.xml\"/>"
                "</Relationships>"
            ),
        )

        for sheet_index, (sheet_name, rows) in enumerate(sheets, start=1):
            zip_file.writestr(
                f"xl/worksheets/sheet{sheet_index}.xml",
                _build_sheet_xml(rows),
            )

        zip_file.writestr(
            "xl/workbook.xml",
            (
                "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
                "<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" "
                "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">"
                "<sheets>{sheets}</sheets>"
                "</workbook>"
            ).format(sheets="".join(workbook_sheets)),
        )
        zip_file.writestr(
            "xl/_rels/workbook.xml.rels",
            (
                "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
                "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
                "{relationships}"
                "<Relationship Id=\"rIdStyles\" "
                "Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles\" "
                "Target=\"styles.xml\"/>"
                "</Relationships>"
            ).format(relationships="".join(workbook_rels)),
        )
        zip_file.writestr(
            "xl/styles.xml",
            (
                "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
                "<styleSheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">"
                "<fonts count=\"1\"><font><sz val=\"11\"/><name val=\"Calibri\"/></font></fonts>"
                "<fills count=\"2\">"
                "<fill><patternFill patternType=\"none\"/></fill>"
                "<fill><patternFill patternType=\"gray125\"/></fill>"
                "</fills>"
                "<borders count=\"1\"><border/></borders>"
                "<cellStyleXfs count=\"1\"><xf/></cellStyleXfs>"
                "<cellXfs count=\"1\"><xf xfId=\"0\"/></cellXfs>"
                "<cellStyles count=\"1\"><cellStyle name=\"Normale\" xfId=\"0\" builtinId=\"0\"/></cellStyles>"
                "</styleSheet>"
            ),
        )
        zip_file.writestr(
            "docProps/core.xml",
            (
                "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
                "<cp:coreProperties xmlns:cp=\"http://schemas.openxmlformats.org/package/2006/metadata/core-properties\" "
                "xmlns:dc=\"http://purl.org/dc/elements/1.1/\" "
                "xmlns:dcterms=\"http://purl.org/dc/terms/\" "
                "xmlns:dcmitype=\"http://purl.org/dc/dcmitype/\" "
                "xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\">"
                "<dc:creator>Computo Metrico GIS</dc:creator>"
                "<cp:lastModifiedBy>Computo Metrico GIS</cp:lastModifiedBy>"
                f"<dcterms:created xsi:type=\"dcterms:W3CDTF\">{created}</dcterms:created>"
                f"<dcterms:modified xsi:type=\"dcterms:W3CDTF\">{created}</dcterms:modified>"
                "</cp:coreProperties>"
            ),
        )
        zip_file.writestr(
            "docProps/app.xml",
            (
                "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
                "<Properties xmlns=\"http://schemas.openxmlformats.org/officeDocument/2006/extended-properties\" "
                "xmlns:vt=\"http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes\">"
                "<Application>Computo Metrico GIS</Application>"
                "</Properties>"
            ),
        )
        zip_file.writestr(
            "[Content_Types].xml",
            (
                "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
                "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
                "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
                "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
                f"{''.join(content_types)}"
                "</Types>"
            ),
        )
