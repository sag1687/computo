from collections import defaultdict
from html import escape
from pathlib import Path

from .models import ReportMetadata, ReportProfile
from .xlsx_utils import write_workbook


def format_number(value: float, decimals: int = 2) -> str:
    formatted = f"{value:,.{decimals}f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def _file_uri(path: str) -> str:
    return Path(path).expanduser().resolve().as_uri()


_SAL_STYLE = """
          body { font-family: Arial, sans-serif; color: #1c2735; margin: 24px;
          }
          h1 { color: #14365c; margin: 0 0 6px 0; }
          h2 { color: #1f2933; margin-top: 28px; }
          .header { width: 100%; border-collapse: collapse; margin-bottom:
          18px; }
          .header td { border: none; vertical-align: top; padding: 0; }
          .logo { max-width: 140px; max-height: 90px; }
          .subtitle { margin: 0; color: #45607d; }
          .meta { background: #eef4fb; border: 1px solid #c7d8eb; padding:
          12px; border-radius: 8px; }
          .badge { display: inline-block; background: #14365c; color: white;
          padding: 4px 10px; border-radius: 999px; font-size: 11px;
          margin-right: 6px; }
          table { width: 100%; border-collapse: collapse; margin-top: 12px; }
          th, td { border: 1px solid #d6dee5; padding: 8px; font-size: 11px;
          vertical-align: top; }
          th { background: #e8f0fa; text-align: left; }
          td.num { text-align: right; white-space: nowrap; }
          .refs th { width: 28%; background: #f4f7fb; }
          .sal-grid td { width: 50%; }
          .map-box { margin-top: 14px; text-align: center; }
          .map { width: 100%; max-width: 760px; border: 1px solid #cfd8e3; }
          .footer-note { margin-top: 22px; color: #415468; }
          .page-break { page-break-before: always; }
        """


def build_category_summary(summary_rows: list[dict]) -> list[dict]:
    totals: dict[str, float] = defaultdict(float)
    for row in summary_rows:
        category = (
            str(row.get("category") or "Senza categoria").strip()
            or "Senza categoria"
        )
        totals[category] += float(row.get("total_price") or 0.0)

    return [
        {
            "category": category,
            "total_price": round(total, 2),
        }
        for category, total in sorted(
            totals.items(), key=lambda item: item[0].lower()
        )
    ]


def compute_sal_totals(
    summary_rows: list[dict],
    security_costs: float = 0.0,
    retention_percent: float = 0.0,
    vat_percent: float = 22.0,
    previous_paid: float = 0.0,
) -> dict[str, float]:
    works_total = round(
        sum(float(row.get("total_price") or 0.0) for row in summary_rows), 2
    )
    gross_total = round(works_total + security_costs, 2)
    retention_amount = round(gross_total * (retention_percent / 100.0), 2)
    certified_to_date = round(gross_total - retention_amount, 2)
    due_before_vat = round(max(certified_to_date - previous_paid, 0.0), 2)
    vat_due = round(due_before_vat * (vat_percent / 100.0), 2)
    total_due = round(due_before_vat + vat_due, 2)
    return {
        "works_total": works_total,
        "security_costs": round(security_costs, 2),
        "gross_total": gross_total,
        "retention_percent": round(retention_percent, 4),
        "retention_amount": retention_amount,
        "certified_to_date": certified_to_date,
        "previous_paid": round(previous_paid, 2),
        "due_before_vat": due_before_vat,
        "vat_percent": round(vat_percent, 4),
        "vat_due": vat_due,
        "total_due": total_due,
    }


def build_accounting_html(
    metadata: ReportMetadata,
    summary_rows: list[dict],
    detail_rows: list[dict],
    sal_record: dict,
    journal_entries: list[dict],
    profile: ReportProfile | None = None,
    map_image_path: str = "",
) -> str:
    profile = profile or ReportProfile()
    totals = compute_sal_totals(
        summary_rows,
        security_costs=float(sal_record.get("security_costs") or 0.0),
        retention_percent=float(sal_record.get("retention_percent") or 0.0),
        vat_percent=float(sal_record.get("vat_percent") or 22.0),
        previous_paid=float(sal_record.get("previous_paid") or 0.0),
    )
    category_rows = build_category_summary(summary_rows)

    logo_html = ""
    if profile.logo_path:
        try:
            logo_html = (
                f'<img class="logo" src="{_file_uri(profile.logo_path)}" />'
            )
        except Exception:
            logo_html = ""

    references_html = ""
    if profile.references:
        references_html = "".join(
            f"<tr><th>{escape(reference.label)}</th>"
            f"<td>{escape(reference.value)}</td></tr>"
            for reference in profile.references
        )

    libretto_rows = "".join(
        (
            "<tr>"
            f"<td>{index}</td>"
            f"<td>{escape(str(row['layer_name']))}</td>"
            f"<td>{escape(str(row['feature_id']))}</td>"
            f"<td>{escape(str(row['price_code']))}</td>"
            f"<td>{escape(str(row['description']))}</td>"
            f"<td>{escape(str(row['unit']))}</td>"
            f"<td class='num'>{format_number(float(row['quantity']), 4)}</td>"
            f"<td class='num'>{format_number(float(row['unit_price']))}</td>"
            f"<td class='num'>{format_number(float(row['total_price']))}</td>"
            "</tr>"
        )
        for index, row in enumerate(detail_rows, start=1)
    )
    registro_rows = "".join(
        (
            "<tr>"
            f"<td>{index}</td>"
            f"<td>{escape(str(row['code']))}</td>"
            f"<td>{escape(str(row['description']))}</td>"
            f"<td>{escape(str(row.get('category') or ''))}</td>"
            f"<td>{escape(str(row['unit']))}</td>"
            f"<td class='num'>{format_number(float(row['quantity']), 4)}</td>"
            f"<td class='num'>{format_number(float(row['unit_price']))}</td>"
            f"<td class='num'>{format_number(float(row['total_price']))}</td>"
            "</tr>"
        )
        for index, row in enumerate(summary_rows, start=1)
    )
    sommario_rows = "".join(
        (
            "<tr>"
            f"<td>{escape(str(row['category']))}</td>"
            f"<td class='num'>{format_number(float(row['total_price']))}</td>"
            "</tr>"
        )
        for row in category_rows
    )
    journal_rows = "".join(
        (
            "<tr>"
            f"<td>{escape(str(row['work_date']))}</td>"
            f"<td>{escape(str(row['title']))}</td>"
            f"<td>{escape(str(row.get('weather') or ''))}</td>"
            f"<td>{escape(str(row.get('workers') or ''))}</td>"
            f"<td>{escape(str(row.get('description') or ''))}</td>"
            "</tr>"
        )
        for row in journal_entries
    )
    journal_section = (
        (
            "<div class='page-break'></div><h2>Giornale lavori</h2>"
            "<table><thead><tr><th>Data</th><th>Titolo</th>"
            "<th>Meteo</th><th>Maestranze</th><th>Descrizione</th>"
            "</tr></thead><tbody>" + journal_rows + "</tbody></table>"
        )
        if journal_rows
        else ""
    )
    map_html = ""
    if map_image_path:
        try:
            map_html = (
                "<div class='page-break'></div>"
                f"<h2>{escape(profile.map_title)}</h2>"
                f"<div class='map-box'><img class='map' width='720' "
                f"src='{_file_uri(map_image_path)}' /></div>"
            )
        except Exception:
            map_html = ""

    footer_line = (
        f"<p class='footer-note'>{escape(profile.footer_text)}</p>"
        if profile.footer_text
        else ""
    )
    subtitle_default = "Libretto, registro, SAL e certificato di pagamento"
    subtitle_line = (
        f'<p class="subtitle">'
        f'{escape(profile.subtitle or subtitle_default)}</p>'
    )
    sal_number_line = (
        "<span class=\"badge\">SAL n. "
        f"{escape(str(sal_record.get('sal_number') or 1))}</span>"
    )
    references_section = (
        "<h2>Riferimenti</h2><table class='refs'><tbody>"
        + references_html
        + "</tbody></table>"
        if references_html
        else ""
    )
    sal_grid_rows = "".join(
        f'<tr><th>{label}</th><td class="num">{value}</td></tr>'
        for label, value in (
            ("Importo lavori", format_number(totals["works_total"])),
            ("Oneri sicurezza", format_number(totals["security_costs"])),
            ("Importo lordo SAL", format_number(totals["gross_total"])),
            (
                "Ritenuta "
                f"{format_number(totals['retention_percent'], 2)}%",
                format_number(totals["retention_amount"]),
            ),
            (
                "Certificato a tutto il SAL",
                format_number(totals["certified_to_date"]),
            ),
            (
                "Già certificato / pagato",
                format_number(totals["previous_paid"]),
            ),
            (
                "Da liquidare imponibile",
                format_number(totals["due_before_vat"]),
            ),
            (
                f"IVA {format_number(totals['vat_percent'], 2)}%",
                format_number(totals["vat_due"]),
            ),
            (
                "Totale certificato",
                f"<b>{format_number(totals['total_due'])}</b>",
            ),
        )
    )

    return f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <style>{_SAL_STYLE}</style>
      </head>
      <body>
        <table class="header">
          <tr>
            <td style="width:160px">{logo_html}</td>
            <td>
              <h1>{escape(profile.title or 'Contabilità lavori')}</h1>
              {subtitle_line}
            </td>
          </tr>
        </table>
        <div class="meta">
          <span class="badge">Run #{metadata.run_id}</span>
          {sal_number_line}
          <p><b>Layer:</b> {escape(metadata.layer_name)}</p>
          <p><b>Prezziario:</b> {escape(metadata.price_list_name)}</p>
          <p><b>Data SAL:</b>
          {escape(str(sal_record.get('sal_date') or ''))}</p>
          <p><b>Note SAL:</b>
          {escape(str(sal_record.get('notes') or 'Nessuna'))}</p>
        </div>

        {references_section}

        <h2>Certificato di pagamento</h2>
        <table class="sal-grid">
          <tbody>{sal_grid_rows}</tbody>
        </table>

        <h2>Sommario per categoria</h2>
        <table>
          <thead><tr><th>Categoria</th><th>Importo</th></tr></thead>
          <tbody>{sommario_rows}</tbody>
        </table>

        <div class="page-break"></div>
        <h2>Registro di contabilità</h2>
        <table>
          <thead>
            <tr>
              <th>N.</th><th>Codice</th><th>Descrizione</th><th>Categoria</th><th>UM</th>
              <th>Quantità</th><th>Prezzo unitario</th><th>Importo</th>
            </tr>
          </thead>
          <tbody>{registro_rows}</tbody>
        </table>

        <div class="page-break"></div>
        <h2>Libretto delle misure</h2>
        <table>
          <thead>
            <tr>
              <th>N.</th><th>Layer</th><th>FID</th><th>Codice</th><th>Descrizione</th><th>UM</th>
              <th>Quantità</th><th>Prezzo unitario</th><th>Importo</th>
            </tr>
          </thead>
          <tbody>{libretto_rows}</tbody>
        </table>

        {journal_section}
        {map_html}
        {footer_line}
      </body>
    </html>
    """


def export_accounting_xlsx(
    path: str,
    metadata: ReportMetadata,
    summary_rows: list[dict],
    detail_rows: list[dict],
    sal_record: dict,
    journal_entries: list[dict],
    profile: ReportProfile | None = None,
) -> None:
    profile = profile or ReportProfile()
    category_rows = build_category_summary(summary_rows)
    totals = compute_sal_totals(
        summary_rows,
        security_costs=float(sal_record.get("security_costs") or 0.0),
        retention_percent=float(sal_record.get("retention_percent") or 0.0),
        vat_percent=float(sal_record.get("vat_percent") or 22.0),
        previous_paid=float(sal_record.get("previous_paid") or 0.0),
    )

    sal_sheet = [
        [profile.title or "Contabilità lavori"],
        ["Run", metadata.run_id],
        ["Layer", metadata.layer_name],
        ["Prezziario", metadata.price_list_name],
        ["SAL n.", sal_record.get("sal_number") or 1],
        ["Data SAL", sal_record.get("sal_date") or ""],
        ["Note", sal_record.get("notes") or ""],
        [],
        ["Voce", "Valore"],
        ["Importo lavori", totals["works_total"]],
        ["Oneri sicurezza", totals["security_costs"]],
        ["Importo lordo SAL", totals["gross_total"]],
        ["Ritenuta %", totals["retention_percent"]],
        ["Ritenuta importo", totals["retention_amount"]],
        ["Certificato a tutto il SAL", totals["certified_to_date"]],
        ["Già certificato / pagato", totals["previous_paid"]],
        ["Da liquidare imponibile", totals["due_before_vat"]],
        ["IVA %", totals["vat_percent"]],
        ["IVA importo", totals["vat_due"]],
        ["Totale certificato", totals["total_due"]],
    ]

    libretto_sheet = [
        [
            "N.",
            "Layer",
            "Feature ID",
            "Codice",
            "Descrizione",
            "UM",
            "Quantità",
            "Prezzo unitario",
            "Importo",
        ]
    ]
    for index, row in enumerate(detail_rows, start=1):
        libretto_sheet.append(
            [
                index,
                row["layer_name"],
                row["feature_id"],
                row["price_code"],
                row["description"],
                row["unit"],
                float(row["quantity"]),
                float(row["unit_price"]),
                float(row["total_price"]),
            ]
        )

    registro_sheet = [
        [
            "N.",
            "Codice",
            "Descrizione",
            "Categoria",
            "UM",
            "Quantità",
            "Prezzo unitario",
            "Importo",
        ]
    ]
    for index, row in enumerate(summary_rows, start=1):
        registro_sheet.append(
            [
                index,
                row["code"],
                row["description"],
                row.get("category") or "",
                row["unit"],
                float(row["quantity"]),
                float(row["unit_price"]),
                float(row["total_price"]),
            ]
        )

    sommario_sheet = [["Categoria", "Importo"]]
    for row in category_rows:
        sommario_sheet.append([row["category"], float(row["total_price"])])

    giornale_sheet = [["Data", "Titolo", "Meteo", "Maestranze", "Descrizione"]]
    for row in journal_entries:
        giornale_sheet.append(
            [
                row["work_date"],
                row["title"],
                row.get("weather") or "",
                row.get("workers") or "",
                row.get("description") or "",
            ]
        )

    write_workbook(
        path,
        [
            ("SAL", sal_sheet),
            ("Registro", registro_sheet),
            ("Libretto", libretto_sheet),
            ("Sommario", sommario_sheet),
            ("Giornale", giornale_sheet),
        ],
    )
