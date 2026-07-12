from pathlib import Path
from html import escape

from .models import ReportMetadata, ReportProfile
from .qt_compat import PRINTER_HIGH_RESOLUTION, PRINTER_PDF_FORMAT, QPrinter, QTextDocument
from .xlsx_utils import write_workbook


def format_number(value: float, decimals: int = 2) -> str:
    formatted = f"{value:,.{decimals}f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def _file_uri(path: str) -> str:
    return Path(path).expanduser().resolve().as_uri()


def build_report_html(
    metadata: ReportMetadata,
    summary_rows: list[dict],
    detail_rows: list[dict],
    profile: ReportProfile | None = None,
    map_image_path: str = "",
) -> str:
    profile = profile or ReportProfile()
    total_amount = sum(float(row["total_price"]) for row in summary_rows)

    summary_table = "".join(
        (
            "<tr>"
            f"<td>{escape(str(row['code']))}</td>"
            f"<td>{escape(str(row['description']))}</td>"
            f"<td>{escape(str(row['unit']))}</td>"
            f"<td class=\"num\">{format_number(float(row['quantity']), 4)}</td>"
            f"<td class=\"num\">{format_number(float(row['unit_price']))}</td>"
            f"<td class=\"num\">{format_number(float(row['total_price']))}</td>"
            f"<td>{escape(str(row.get('category') or ''))}</td>"
            "</tr>"
        )
        for row in summary_rows
    )

    detail_table = "".join(
        (
            "<tr>"
            f"<td>{escape(str(row['layer_name']))}</td>"
            f"<td>{escape(str(row['feature_id']))}</td>"
            f"<td>{escape(str(row['price_code']))}</td>"
            f"<td>{escape(str(row['description']))}</td>"
            f"<td>{escape(str(row['unit']))}</td>"
            f"<td class=\"num\">{format_number(float(row['quantity']), 4)}</td>"
            f"<td class=\"num\">{format_number(float(row['unit_price']))}</td>"
            f"<td class=\"num\">{format_number(float(row['total_price']))}</td>"
            f"<td>{escape(str(row.get('note') or ''))}</td>"
            "</tr>"
        )
        for row in detail_rows
    )

    logo_html = ""
    if profile.logo_path and Path(profile.logo_path).exists():
        logo_html = (
            f'<div class="logo-box"><img class="logo" src="{_file_uri(profile.logo_path)}" /></div>'
        )

    references_html = ""
    if profile.references:
        references_rows = "".join(
            (
                "<tr>"
                f"<th>{escape(reference.label)}</th>"
                f"<td>{escape(reference.value)}</td>"
                "</tr>"
            )
            for reference in profile.references
        )
        references_html = (
            "<h2>Riferimenti</h2>"
            f'<table class="refs"><tbody>{references_rows}</tbody></table>'
        )

    map_html = ""
    if map_image_path and Path(map_image_path).exists():
        map_html = (
            "<div class=\"page-break\"></div>"
            f"<h2>{escape(profile.map_title)}</h2>"
            f'<div class="map-box"><img class="map" width="720" src="{_file_uri(map_image_path)}" /></div>'
        )

    organization_html = f"<p class=\"org\">{escape(profile.organization)}</p>" if profile.organization else ""
    subtitle_html = f"<p class=\"subtitle\">{escape(profile.subtitle)}</p>" if profile.subtitle else ""
    footer_html = f"<p class=\"footer-note\">{escape(profile.footer_text)}</p>" if profile.footer_text else ""

    return f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <style>
          body {{ font-family: Arial, sans-serif; color: #1c2735; margin: 24px; }}
          h1 {{ color: #14365c; margin: 0 0 6px 0; }}
          h2 {{ color: #1f2933; margin-top: 28px; }}
          .header {{ width: 100%; border-collapse: collapse; margin-bottom: 18px; }}
          .header td {{ border: none; vertical-align: top; padding: 0; }}
          .logo-box {{ width: 150px; }}
          .logo {{ max-width: 140px; max-height: 90px; }}
          .subtitle {{ margin: 0; color: #45607d; }}
          .org {{ margin: 6px 0 0 0; color: #27415e; font-weight: bold; }}
          .meta {{ background: #eef4fb; border: 1px solid #c7d8eb; padding: 12px; border-radius: 8px; }}
          .badge {{ display: inline-block; background: #14365c; color: white; padding: 4px 10px; border-radius: 999px; font-size: 11px; margin-right: 6px; }}
          table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
          th, td {{ border: 1px solid #d6dee5; padding: 8px; font-size: 11px; vertical-align: top; }}
          th {{ background: #e8f0fa; text-align: left; }}
          td.num {{ text-align: right; white-space: nowrap; }}
          .total {{ margin-top: 14px; font-size: 16px; font-weight: bold; text-align: right; }}
          .refs th {{ width: 28%; background: #f4f7fb; }}
          .map-box {{ margin-top: 14px; text-align: center; }}
          .map {{ width: 100%; max-width: 760px; border: 1px solid #cfd8e3; }}
          .footer-note {{ margin-top: 22px; color: #415468; }}
          .page-break {{ page-break-before: always; }}
        </style>
      </head>
      <body>
        <table class="header">
          <tr>
            <td style="width:160px">{logo_html}</td>
            <td>
              <h1>{escape(profile.title)}</h1>
              {subtitle_html}
              {organization_html}
            </td>
          </tr>
        </table>
        <div class="meta">
          <span class="badge">Run #{metadata.run_id}</span>
          <span class="badge">CRS {escape(metadata.crs_authid or 'n.d.')}</span>
          <p><b>Layer:</b> {escape(metadata.layer_name)}</p>
          <p><b>Prezziario:</b> {escape(metadata.price_list_name)}</p>
          <p><b>Generato il:</b> {escape(metadata.generated_at)}</p>
          <p><b>Note:</b> {escape(metadata.notes or 'Nessuna')}</p>
        </div>
        {references_html}

        <h2>Riepilogo computo</h2>
        <table>
          <thead>
            <tr>
              <th>Codice</th>
              <th>Descrizione</th>
              <th>UM</th>
              <th>Quantità</th>
              <th>Prezzo unitario</th>
              <th>Totale</th>
              <th>Categoria</th>
            </tr>
          </thead>
          <tbody>{summary_table}</tbody>
        </table>
        <div class="total">Totale complessivo: € {format_number(total_amount)}</div>

        <h2>Dettaglio elementi</h2>
        <table>
          <thead>
            <tr>
              <th>Layer</th>
              <th>Feature ID</th>
              <th>Codice</th>
              <th>Descrizione</th>
              <th>UM</th>
              <th>Quantità</th>
              <th>Prezzo unitario</th>
              <th>Totale</th>
              <th>Note</th>
            </tr>
          </thead>
          <tbody>{detail_table}</tbody>
        </table>
        {map_html}
        {footer_html}
      </body>
    </html>
    """


def export_pdf(path: str, html: str) -> None:
    document = QTextDocument()
    document.setHtml(html)
    document.setDocumentMargin(18)

    printer = QPrinter(PRINTER_HIGH_RESOLUTION)
    printer.setOutputFormat(PRINTER_PDF_FORMAT)
    printer.setOutputFileName(path)
    printer.setDocName("Computo Metrico GIS")

    print_method = getattr(document, "print_", None) or getattr(document, "print")
    print_method(printer)


def export_xlsx(
    path: str,
    metadata: ReportMetadata,
    summary_rows: list[dict],
    detail_rows: list[dict],
    profile: ReportProfile | None = None,
) -> None:
    profile = profile or ReportProfile()
    rows: list[list[object]] = [
        [profile.title or "Computo Metrico GIS", "", "", "", "", ""],
        ["Sottotitolo", profile.subtitle],
        ["Organizzazione", profile.organization],
        ["Run", metadata.run_id],
        ["Layer", metadata.layer_name],
        ["Prezziario", metadata.price_list_name],
        ["CRS", metadata.crs_authid],
        ["Generato il", metadata.generated_at],
        ["Logo", profile.logo_path],
        ["Piè di pagina", profile.footer_text],
        [],
        ["Riferimenti"],
        ["Etichetta", "Valore"],
    ]

    for reference in profile.references:
        rows.append([reference.label, reference.value])

    rows.extend(
        [
            [],
            ["Riepilogo computo"],
            ["Codice", "Descrizione", "UM", "Quantità", "Prezzo unitario", "Totale", "Categoria"],
        ]
    )

    for row in summary_rows:
        rows.append(
            [
                row["code"],
                row["description"],
                row["unit"],
                float(row["quantity"]),
                float(row["unit_price"]),
                float(row["total_price"]),
                row.get("category") or "",
            ]
        )

    rows.extend(
        [
            [],
            ["Dettaglio elementi"],
            ["Layer", "Feature ID", "Geometria", "Codice", "Descrizione", "UM", "Quantità", "Prezzo unitario", "Totale", "Note"],
        ]
    )

    for row in detail_rows:
        rows.append(
            [
                row["layer_name"],
                row["feature_id"],
                row["geometry_type"],
                row["price_code"],
                row["description"],
                row["unit"],
                float(row["quantity"]),
                float(row["unit_price"]),
                float(row["total_price"]),
                row.get("note") or "",
            ]
        )

    write_workbook(path, [("Computo", rows)])
