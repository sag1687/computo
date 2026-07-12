import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .models import (
    ImportedPriceList,
    MeasurementItem,
    PriceItem,
    ReportMetadata,
    ReportProfile,
    ReportReference,
)


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS price_lists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_path TEXT,
    source_url TEXT,
    imported_at TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS price_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    price_list_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    description TEXT NOT NULL,
    unit TEXT NOT NULL,
    unit_price REAL NOT NULL,
    category TEXT,
    notes TEXT,
    UNIQUE(price_list_id, code),
    FOREIGN KEY(price_list_id) REFERENCES price_lists(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_price_items_lookup
    ON price_items(price_list_id, code);

CREATE TABLE IF NOT EXISTS download_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    region TEXT,
    url TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS measurement_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    layer_name TEXT NOT NULL,
    price_list_id INTEGER NOT NULL,
    crs_authid TEXT,
    generated_at TEXT NOT NULL,
    notes TEXT,
    FOREIGN KEY(price_list_id) REFERENCES price_lists(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS measurement_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    layer_name TEXT NOT NULL,
    feature_id INTEGER NOT NULL,
    geometry_type TEXT NOT NULL,
    price_code TEXT NOT NULL,
    description TEXT NOT NULL,
    unit TEXT NOT NULL,
    quantity REAL NOT NULL,
    unit_price REAL NOT NULL,
    total_price REAL NOT NULL,
    category TEXT,
    note TEXT,
    FOREIGN KEY(run_id) REFERENCES measurement_runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_measurement_items_run
    ON measurement_items(run_id, price_code);

CREATE TABLE IF NOT EXISTS sal_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    sal_number INTEGER NOT NULL,
    sal_date TEXT NOT NULL,
    security_costs REAL NOT NULL DEFAULT 0,
    retention_percent REAL NOT NULL DEFAULT 0,
    vat_percent REAL NOT NULL DEFAULT 22,
    previous_paid REAL NOT NULL DEFAULT 0,
    notes TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES measurement_runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sal_documents_run
    ON sal_documents(run_id, sal_number);

CREATE TABLE IF NOT EXISTS journal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    work_date TEXT NOT NULL,
    title TEXT NOT NULL,
    weather TEXT,
    workers TEXT,
    description TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES measurement_runs(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_journal_entries_run
    ON journal_entries(run_id, work_date);
"""


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class DatabaseManager:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.path))
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def set_setting(self, key: str, value: str | int | float | None) -> None:
        with self.connect() as connection:
            connection.execute(
                "REPLACE INTO settings(key, value) VALUES(?, ?)",
                (key, "" if value is None else str(value)),
            )

    def get_setting(self, key: str, default: str = "") -> str:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,),
            ).fetchone()
        return row["value"] if row else default

    def save_report_profile(self, profile: ReportProfile) -> None:
        payload = {
            "title": profile.title,
            "subtitle": profile.subtitle,
            "organization": profile.organization,
            "logo_path": profile.logo_path,
            "footer_text": profile.footer_text,
            "include_map": profile.include_map,
            "map_title": profile.map_title,
            "references": [
                {"label": reference.label, "value": reference.value}
                for reference in profile.references
            ],
        }
        self.set_setting("report_profile_json", json.dumps(payload, ensure_ascii=False))

    def load_report_profile(self) -> ReportProfile:
        raw = self.get_setting("report_profile_json", "")
        if not raw:
            return ReportProfile()

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return ReportProfile()

        references = [
            ReportReference(
                label=str(item.get("label", "")).strip(),
                value=str(item.get("value", "")).strip(),
            )
            for item in payload.get("references", [])
            if str(item.get("label", "")).strip() or str(item.get("value", "")).strip()
        ]
        return ReportProfile(
            title=str(payload.get("title", "")).strip() or "Computo metrico estimativo",
            subtitle=str(payload.get("subtitle", "")).strip(),
            organization=str(payload.get("organization", "")).strip(),
            logo_path=str(payload.get("logo_path", "")).strip(),
            footer_text=str(payload.get("footer_text", "")).strip(),
            include_map=bool(payload.get("include_map", True)),
            map_title=str(payload.get("map_title", "")).strip() or "Mappa di inquadramento",
            references=references,
        )

    def import_price_list(self, price_list: ImportedPriceList) -> int:
        if not price_list.items:
            raise ValueError("Il prezziario non contiene righe valide.")

        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO price_lists(name, source_type, source_path, source_url, imported_at, notes)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    price_list.name,
                    price_list.source_type,
                    price_list.source_path,
                    price_list.source_url,
                    now_iso(),
                    price_list.notes,
                ),
            )
            price_list_id = int(cursor.lastrowid)

            connection.executemany(
                """
                INSERT INTO price_items(
                    price_list_id, code, description, unit, unit_price, category, notes
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        price_list_id,
                        item.code,
                        item.description,
                        item.unit,
                        item.unit_price,
                        item.category,
                        item.notes,
                    )
                    for item in price_list.items
                ],
            )

        self.set_setting("active_price_list_id", price_list_id)
        return price_list_id

    def list_price_lists(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT pl.*,
                       COUNT(pi.id) AS items_count
                FROM price_lists pl
                LEFT JOIN price_items pi ON pi.price_list_id = pl.id
                GROUP BY pl.id
                ORDER BY pl.imported_at DESC, pl.id DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def list_price_items(self, price_list_id: int, limit: int | None = None) -> list[dict]:
        sql = """
            SELECT code, description, unit, unit_price, category, notes
            FROM price_items
            WHERE price_list_id = ?
            ORDER BY code
        """
        params: list[object] = [price_list_id]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        with self.connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_price_lookup(self, price_list_id: int) -> dict[str, PriceItem]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT code, description, unit, unit_price, category, notes
                FROM price_items
                WHERE price_list_id = ?
                """,
                (price_list_id,),
            ).fetchall()

        return {
            row["code"]: PriceItem(
                code=row["code"],
                description=row["description"],
                unit=row["unit"],
                unit_price=float(row["unit_price"]),
                category=row["category"] or "",
                notes=row["notes"] or "",
            )
            for row in rows
        }

    def add_download_link(self, label: str, url: str, region: str = "", notes: str = "") -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO download_links(label, region, url, notes, created_at)
                VALUES(?, ?, ?, ?, ?)
                """,
                (label, region, url, notes, now_iso()),
            )
            return int(cursor.lastrowid)

    def list_download_links(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, label, region, url, notes, created_at
                FROM download_links
                ORDER BY created_at DESC, id DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_download_link(self, link_id: int) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM download_links WHERE id = ?", (link_id,))

    def create_measurement_run(
        self,
        layer_name: str,
        price_list_id: int,
        crs_authid: str,
        items: list[MeasurementItem],
        notes: str = "",
    ) -> int:
        if not items:
            raise ValueError("Nessuna misurazione da salvare.")

        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO measurement_runs(layer_name, price_list_id, crs_authid, generated_at, notes)
                VALUES(?, ?, ?, ?, ?)
                """,
                (layer_name, price_list_id, crs_authid, now_iso(), notes),
            )
            run_id = int(cursor.lastrowid)

            connection.executemany(
                """
                INSERT INTO measurement_items(
                    run_id, layer_name, feature_id, geometry_type, price_code,
                    description, unit, quantity, unit_price, total_price, category, note
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        item.layer_name,
                        item.feature_id,
                        item.geometry_type,
                        item.price_code,
                        item.description,
                        item.unit,
                        item.quantity,
                        item.unit_price,
                        item.total_price,
                        item.category,
                        item.note,
                    )
                    for item in items
                ],
            )

        self.set_setting("active_run_id", run_id)
        return run_id

    def list_runs(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT mr.id,
                       mr.layer_name,
                       mr.crs_authid,
                       mr.generated_at,
                       mr.notes,
                       pl.name AS price_list_name,
                       COUNT(mi.id) AS items_count,
                       ROUND(COALESCE(SUM(mi.total_price), 0), 2) AS grand_total
                FROM measurement_runs mr
                JOIN price_lists pl ON pl.id = mr.price_list_id
                LEFT JOIN measurement_items mi ON mi.run_id = mr.id
                GROUP BY mr.id
                ORDER BY mr.generated_at DESC, mr.id DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def _resolve_run_id(self, run_id: int | None) -> int:
        if run_id is not None:
            return run_id
        active = self.get_setting("active_run_id", "")
        if not active:
            raise ValueError("Nessun computo disponibile.")
        return int(active)

    def get_run_metadata(self, run_id: int | None = None) -> ReportMetadata:
        resolved_run_id = self._resolve_run_id(run_id)
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT mr.id,
                       mr.layer_name,
                       mr.crs_authid,
                       mr.generated_at,
                       mr.notes,
                       pl.name AS price_list_name
                FROM measurement_runs mr
                JOIN price_lists pl ON pl.id = mr.price_list_id
                WHERE mr.id = ?
                """,
                (resolved_run_id,),
            ).fetchone()

        if not row:
            raise ValueError("Run di computo non trovato.")

        return ReportMetadata(
            run_id=int(row["id"]),
            layer_name=row["layer_name"],
            price_list_name=row["price_list_name"],
            crs_authid=row["crs_authid"] or "",
            generated_at=row["generated_at"],
            notes=row["notes"] or "",
        )

    def get_run_summary(self, run_id: int | None = None) -> list[dict]:
        resolved_run_id = self._resolve_run_id(run_id)
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT price_code AS code,
                       MAX(description) AS description,
                       unit,
                       ROUND(SUM(quantity), 4) AS quantity,
                       ROUND(unit_price, 4) AS unit_price,
                       ROUND(SUM(total_price), 2) AS total_price,
                       MAX(category) AS category
                FROM measurement_items
                WHERE run_id = ?
                GROUP BY price_code, unit, unit_price
                ORDER BY category, code
                """,
                (resolved_run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_run_details(self, run_id: int | None = None) -> list[dict]:
        resolved_run_id = self._resolve_run_id(run_id)
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT layer_name, feature_id, geometry_type, price_code, description,
                       unit, ROUND(quantity, 4) AS quantity,
                       ROUND(unit_price, 4) AS unit_price,
                       ROUND(total_price, 2) AS total_price,
                       category, note
                FROM measurement_items
                WHERE run_id = ?
                ORDER BY category, price_code, feature_id
                """,
                (resolved_run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_sal_document(
        self,
        run_id: int,
        sal_number: int,
        sal_date: str,
        security_costs: float = 0.0,
        retention_percent: float = 0.0,
        vat_percent: float = 22.0,
        previous_paid: float = 0.0,
        notes: str = "",
    ) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO sal_documents(
                    run_id, sal_number, sal_date, security_costs, retention_percent,
                    vat_percent, previous_paid, notes, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    sal_number,
                    sal_date,
                    security_costs,
                    retention_percent,
                    vat_percent,
                    previous_paid,
                    notes,
                    now_iso(),
                ),
            )
            return int(cursor.lastrowid)

    def list_sal_documents(self, run_id: int | None = None) -> list[dict]:
        sql = """
            SELECT sd.*,
                   mr.layer_name,
                   pl.name AS price_list_name
            FROM sal_documents sd
            JOIN measurement_runs mr ON mr.id = sd.run_id
            JOIN price_lists pl ON pl.id = mr.price_list_id
        """
        params: list[object] = []
        if run_id is not None:
            sql += " WHERE sd.run_id = ?"
            params.append(run_id)
        sql += " ORDER BY sd.sal_date DESC, sd.sal_number DESC, sd.id DESC"

        with self.connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_sal_document(self, sal_id: int) -> dict:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT sd.*,
                       mr.layer_name,
                       mr.crs_authid,
                       mr.generated_at AS run_generated_at,
                       pl.name AS price_list_name
                FROM sal_documents sd
                JOIN measurement_runs mr ON mr.id = sd.run_id
                JOIN price_lists pl ON pl.id = mr.price_list_id
                WHERE sd.id = ?
                """,
                (sal_id,),
            ).fetchone()
        if not row:
            raise ValueError("SAL non trovato.")
        return dict(row)

    def add_journal_entry(
        self,
        work_date: str,
        title: str,
        description: str,
        weather: str = "",
        workers: str = "",
        run_id: int | None = None,
    ) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO journal_entries(
                    run_id, work_date, title, weather, workers, description, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, work_date, title, weather, workers, description, now_iso()),
            )
            return int(cursor.lastrowid)

    def list_journal_entries(self, run_id: int | None = None) -> list[dict]:
        sql = """
            SELECT id, run_id, work_date, title, weather, workers, description, created_at
            FROM journal_entries
        """
        params: list[object] = []
        if run_id is not None:
            sql += " WHERE run_id = ? OR run_id IS NULL"
            params.append(run_id)
        sql += " ORDER BY work_date DESC, id DESC"
        with self.connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def delete_journal_entry(self, entry_id: int) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM journal_entries WHERE id = ?", (entry_id,))
