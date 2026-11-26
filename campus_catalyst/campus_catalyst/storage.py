import csv
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .log import get_logger
from .models import VolunteerRecord
from .validators import validate_record_payload

REQUIRED_CSV_COLUMNS = {"volunteer_name", "activity", "category", "service_date", "start_time", "end_time"}


log = get_logger("storage")


class StorageError(Exception):
    pass


class VolunteerStorage:
    def __init__(self, path="data/volunteers.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Filled in by load() when a damaged data file had to be set aside.
        self.recovery_message = ""

    def _quarantine(self, reason):
        """Move a damaged data file aside (never delete it) and start clean."""
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = self.path.with_name(f"{self.path.name}.corrupt-{stamp}.bak")
        try:
            self.path.replace(backup)
        except OSError as exc:
            raise StorageError(f"Data file is damaged ({reason}) and could not be backed up: {exc}") from exc
        log.warning("Data file quarantined as %s (%s)", backup.name, reason)
        self.recovery_message = (f"The saved data file was damaged ({reason}). It was backed up as "
                                 f"{backup.name} and a clean data file has been started.")
        return []

    def load(self):
        self.recovery_message = ""
        if not self.path.exists():
            return []
        try:
            text = self.path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return self._quarantine("unreadable text encoding")
        except OSError as exc:
            raise StorageError(f"Could not read data file: {exc}") from exc
        if not text.strip():
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            return self._quarantine(f"invalid JSON at line {exc.lineno}")
        if not isinstance(data, list):
            return self._quarantine("expected a list of records")
        try:
            return [VolunteerRecord.from_dict(item) for item in data]
        except (TypeError, KeyError, AttributeError):
            return self._quarantine("a record is missing required fields")

    def save(self, records):
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            temp.write_text(json.dumps([r.to_dict() for r in records], indent=2, ensure_ascii=False),
                            encoding="utf-8")
            temp.replace(self.path)
        except OSError as exc:
            temp.unlink(missing_ok=True)
            log.error("Save failed: %s", exc)
            raise StorageError(f"Could not save data: {exc}") from exc

    def import_csv(self, csv_path):
        """Read a CSV file. Returns (valid_records, row_error_messages)."""
        imported, errors = [], []
        path = Path(str(csv_path).strip())
        if not path.is_file():
            raise StorageError(f"CSV file not found: {path}")
        try:
            with path.open("r", newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames:
                    reader.fieldnames = [str(h).strip().lower() for h in reader.fieldnames]
                if not reader.fieldnames or not REQUIRED_CSV_COLUMNS.issubset(reader.fieldnames):
                    missing = sorted(REQUIRED_CSV_COLUMNS - set(reader.fieldnames or []))
                    raise StorageError("CSV missing required columns: " + ", ".join(missing))
                for number, row in enumerate(reader, 2):
                    try:
                        imported.append(validate_record_payload(row))
                    except (ValueError, TypeError) as exc:
                        errors.append(f"Row {number}: {exc}")
        except (OSError, UnicodeDecodeError, csv.Error) as exc:
            raise StorageError(f"Could not read CSV: {exc}") from exc
        return imported, errors

    @staticmethod
    def export_csv(records, destination):
        fields = list(VolunteerRecord.__dataclass_fields__)
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        with Path(destination).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(r.to_dict() for r in records)


class SQLiteStorage(VolunteerStorage):
    """SQLite backend with the same interface as VolunteerStorage.

    Benefits over a JSON file: ACID transactions (a crash mid-save rolls back), indexed
    queries (see `query`), and no need to rewrite the whole file. On first run an existing
    JSON data file next to the database is migrated automatically.
    """
    COLUMNS = list(VolunteerRecord.__dataclass_fields__)

    def __init__(self, path="data/volunteers.db", legacy_json=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.recovery_message = ""
        self._init_schema()
        legacy = Path(legacy_json) if legacy_json else self.path.with_suffix(".json")
        if self._count() == 0 and legacy.is_file():
            self._migrate(legacy)

    def _connect(self):
        try:
            return sqlite3.connect(self.path, timeout=10)
        except sqlite3.Error as exc:
            raise StorageError(f"Could not open database: {exc}") from exc

    def _init_schema(self):
        try:
            with self._connect() as db:
                db.execute("""CREATE TABLE IF NOT EXISTS records (
                    record_id TEXT PRIMARY KEY, volunteer_name TEXT NOT NULL, activity TEXT NOT NULL,
                    category TEXT NOT NULL, service_date TEXT NOT NULL, start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL, hours REAL NOT NULL, status TEXT NOT NULL DEFAULT 'Pending',
                    supervisor TEXT DEFAULT '', notes TEXT DEFAULT '', deadline TEXT DEFAULT '')""")
                for col in ("volunteer_name COLLATE NOCASE", "status", "service_date", "category"):
                    name = col.split()[0]
                    db.execute(f"CREATE INDEX IF NOT EXISTS idx_records_{name} ON records({col})")
        except sqlite3.Error as exc:
            raise StorageError(f"Could not prepare database: {exc}") from exc

    def _count(self):
        with self._connect() as db:
            return db.execute("SELECT COUNT(*) FROM records").fetchone()[0]

    def _migrate(self, legacy):
        old = VolunteerStorage(legacy)
        records = old.load()
        if records:
            self.save(records)
            log.info("Migrated %d record(s) from %s to %s", len(records), legacy.name, self.path.name)
        self.recovery_message = old.recovery_message

    def load(self):
        self.recovery_message = getattr(self, "recovery_message", "")
        try:
            with self._connect() as db:
                rows = db.execute(f"SELECT {', '.join(self.COLUMNS)} FROM records ORDER BY rowid").fetchall()
        except sqlite3.Error as exc:
            raise StorageError(f"Could not read database: {exc}") from exc
        return [VolunteerRecord(**dict(zip(self.COLUMNS, row))) for row in rows]

    def save(self, records):
        """Atomically make the table match `records` (all-or-nothing transaction)."""
        marks = ", ".join("?" * len(self.COLUMNS))
        try:
            with self._connect() as db:     # commits on success, rolls back on error
                db.execute("DELETE FROM records")
                db.executemany(f"INSERT INTO records ({', '.join(self.COLUMNS)}) VALUES ({marks})",
                               [tuple(r.to_dict()[c] for c in self.COLUMNS) for r in records])
        except sqlite3.Error as exc:
            log.error("Database save failed: %s", exc)
            raise StorageError(f"Could not save data: {exc}") from exc
        log.info("Saved %d record(s)", len(records))

    def query(self, status=None, category=None, volunteer=None, date_from=None, date_to=None):
        """Indexed lookup (O(log n) on the filtered column) instead of scanning every record."""
        clauses, args = [], []
        for column, value in (("status", status), ("category", category)):
            if value and value != "All":
                clauses.append(f"{column} = ?"); args.append(value)
        if volunteer:
            clauses.append("volunteer_name = ? COLLATE NOCASE"); args.append(volunteer)
        if date_from:
            clauses.append("service_date >= ?"); args.append(date_from)
        if date_to:
            clauses.append("service_date <= ?"); args.append(date_to)
        sql = f"SELECT {', '.join(self.COLUMNS)} FROM records"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        try:
            with self._connect() as db:
                rows = db.execute(sql + " ORDER BY service_date DESC", args).fetchall()
        except sqlite3.Error as exc:
            raise StorageError(f"Query failed: {exc}") from exc
        return [VolunteerRecord(**dict(zip(self.COLUMNS, row))) for row in rows]


def merge_records(existing, imported):
    """Append imported records to `existing` (in place).

    Sessions that already exist (same volunteer, activity, date and times) are skipped,
    and any clashing record ID is replaced with a fresh one.
    Returns (added_records, duplicate_count).
    """
    ids = {r.record_id for r in existing}
    seen = {r.fingerprint for r in existing}
    added, duplicates = [], 0
    for record in imported:
        if record.fingerprint in seen:
            duplicates += 1
            continue
        while record.record_id in ids:
            record.record_id = VolunteerRecord.new_id()
        ids.add(record.record_id)
        seen.add(record.fingerprint)
        added.append(record)
    existing.extend(added)
    return added, duplicates
