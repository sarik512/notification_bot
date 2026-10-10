import asyncio
import calendar
import datetime
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

import aiosqlite

from config import Config
from logger import logger

DB_NAME = Config.DB_NAME
BACKUP_DIR = Path("backups")

# Columns that update_client() is allowed to touch
_UPDATABLE_FIELDS = frozenset({
    'name', 'amount', 'currency', 'start_date', 'interval_type',
    'interval_value', 'next_payment_date', 'category', 'notes',
})

# One connection for the whole process: opening a connection means starting a
# thread, which is wasteful to repeat for every query. Writes are serialized by
# _write_lock so that transactions from concurrent handlers never interleave.
_conn: Optional[aiosqlite.Connection] = None
_conn_lock = asyncio.Lock()
_write_lock = asyncio.Lock()


def _casefold(value):
    """SQL helper: SQLite's lower()/LIKE only fold ASCII, so Cyrillic needs Python"""
    return value.casefold() if isinstance(value, str) else value


async def _get_conn() -> aiosqlite.Connection:
    global _conn
    if _conn is None:
        async with _conn_lock:
            if _conn is None:
                conn = await aiosqlite.connect(DB_NAME)
                conn.row_factory = aiosqlite.Row
                # Off by default in SQLite; without it ON DELETE CASCADE does nothing
                await conn.execute("PRAGMA foreign_keys = ON")
                await conn.create_function("py_casefold", 1, _casefold, deterministic=True)
                _conn = conn
    return _conn


async def close_db() -> None:
    """Close the shared connection (call on shutdown)"""
    global _conn
    if _conn is not None:
        conn, _conn = _conn, None
        await conn.close()


@asynccontextmanager
async def _transaction():
    """Exclusive write transaction: commits on success, rolls back on any error"""
    conn = await _get_conn()
    async with _write_lock:
        try:
            yield conn
            await conn.commit()
        except BaseException:
            await conn.rollback()
            raise


async def _fetchall(sql: str, params: Tuple = ()) -> List[aiosqlite.Row]:
    conn = await _get_conn()
    async with conn.execute(sql, params) as cursor:
        return await cursor.fetchall()


async def _fetchone(sql: str, params: Tuple = ()) -> Optional[aiosqlite.Row]:
    conn = await _get_conn()
    async with conn.execute(sql, params) as cursor:
        return await cursor.fetchone()


async def init_db():
    """Initialize database with all required tables and indexes"""
    try:
        async with _transaction() as db:
            # Clients table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS clients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    amount REAL NOT NULL,
                    currency TEXT DEFAULT 'RUB',
                    start_date TEXT NOT NULL,
                    interval_type TEXT NOT NULL,
                    interval_value INTEGER DEFAULT 1,
                    next_payment_date TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    payment_status TEXT DEFAULT 'pending',
                    category TEXT DEFAULT 'general',
                    notes TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Check if we need to migrate existing table
            async with db.execute("PRAGMA table_info(clients)") as cursor:
                column_names = [col[1] for col in await cursor.fetchall()]

            # Add missing columns if they don't exist
            # Note: SQLite doesn't support CURRENT_TIMESTAMP in ALTER TABLE, so we use NULL
            new_columns = {
                'payment_status': "TEXT DEFAULT 'pending'",
                'category': "TEXT DEFAULT 'general'",
                'notes': "TEXT",
                'created_at': "TEXT",
                'updated_at': "TEXT"
            }

            for col_name, col_def in new_columns.items():
                if col_name not in column_names:
                    logger.info(f"Adding missing column: {col_name}")
                    await db.execute(f"ALTER TABLE clients ADD COLUMN {col_name} {col_def}")

            # Payment history table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS payment_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER NOT NULL,
                    payment_date TEXT NOT NULL,
                    amount REAL NOT NULL,
                    currency TEXT NOT NULL,
                    status TEXT NOT NULL,
                    notes TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE
                )
            ''')

            # Composite indexes match the actual queries (filter by user, sort by date).
            # The old single-column ones are redundant now (idx_payment_status was never used).
            await db.execute('CREATE INDEX IF NOT EXISTS idx_clients_user_next ON clients(user_id, next_payment_date)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_next_payment_date ON clients(next_payment_date)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_history_client_date ON payment_history(client_id, payment_date)')
            for old_index in ('idx_user_id', 'idx_payment_status', 'idx_payment_history_client'):
                await db.execute(f'DROP INDEX IF EXISTS {old_index}')

        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise


async def add_client(user_id: int, name: str, amount: float, currency: str,
                    start_date: str, interval_type: str, interval_value: int,
                    category: str = 'general', notes: str = '') -> Optional[int]:
    """Add a new client to the database"""
    try:
        if isinstance(start_date, str):
            start_dt = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
        else:
            start_dt = start_date

        async with _transaction() as db:
            cursor = await db.execute('''
                INSERT INTO clients (user_id, name, amount, currency, start_date,
                                   interval_type, interval_value, next_payment_date,
                                   category, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, name, amount, currency, start_dt.isoformat(),
                  interval_type, interval_value, start_dt.isoformat(),
                  category, notes))
            client_id = cursor.lastrowid
        logger.info(f"Added client: {name} (ID: {client_id}) for user {user_id}")
        return client_id
    except Exception as e:
        logger.error(f"Error adding client {name}: {e}")
        return None


async def get_clients(user_id: int) -> List[aiosqlite.Row]:
    """Get all clients for a specific user"""
    try:
        rows = await _fetchall(
            'SELECT * FROM clients WHERE user_id = ? ORDER BY next_payment_date',
            (user_id,)
        )
        logger.debug(f"Retrieved {len(rows)} clients for user {user_id}")
        return rows
    except Exception as e:
        logger.error(f"Error getting clients for user {user_id}: {e}")
        return []


async def get_client_by_id(client_id: int, user_id: int) -> Optional[aiosqlite.Row]:
    """Get a client by ID. Returns None unless it belongs to user_id."""
    try:
        return await _fetchone(
            'SELECT * FROM clients WHERE id = ? AND user_id = ?',
            (client_id, user_id)
        )
    except Exception as e:
        logger.error(f"Error getting client {client_id}: {e}")
        return None


async def update_client(client_id: int, user_id: int, **fields) -> bool:
    """Update fields of a client owned by user_id"""
    try:
        if not fields:
            return False
        unknown = set(fields) - _UPDATABLE_FIELDS
        if unknown:
            raise ValueError(f"Unknown client fields: {sorted(unknown)}")

        assignments = ', '.join(f"{key} = ?" for key in fields)
        params = (*fields.values(), client_id, user_id)

        async with _transaction() as db:
            cursor = await db.execute(
                f'UPDATE clients SET {assignments}, updated_at = CURRENT_TIMESTAMP '
                'WHERE id = ? AND user_id = ?',
                params
            )
            updated = cursor.rowcount > 0
        if updated:
            logger.info(f"Updated client {client_id}: {fields}")
        else:
            logger.warning(f"Client {client_id} not found for user {user_id}, nothing updated")
        return updated
    except Exception as e:
        logger.error(f"Error updating client {client_id}: {e}")
        return False


async def delete_client(client_id: int, user_id: int) -> bool:
    """Delete a client owned by user_id; payment history goes with it (FK cascade)"""
    try:
        async with _transaction() as db:
            cursor = await db.execute(
                'DELETE FROM clients WHERE id = ? AND user_id = ?',
                (client_id, user_id)
            )
            deleted = cursor.rowcount > 0
        if deleted:
            logger.info(f"Deleted client {client_id}")
        else:
            logger.warning(f"Client {client_id} not found for user {user_id}, nothing deleted")
        return deleted
    except Exception as e:
        logger.error(f"Error deleting client {client_id}: {e}")
        return False


async def get_due_payments() -> List[aiosqlite.Row]:
    """Get all payments that are due today or overdue"""
    try:
        rows = await _fetchall(
            'SELECT * FROM clients WHERE next_payment_date <= ?',
            (date.today().isoformat(),)
        )
        logger.debug(f"Found {len(rows)} due payments")
        return rows
    except Exception as e:
        logger.error(f"Error getting due payments: {e}")
        return []


async def get_upcoming_payments(days: int = 3) -> List[aiosqlite.Row]:
    """Get payments due in the next N days"""
    try:
        today = date.today()
        rows = await _fetchall(
            'SELECT * FROM clients WHERE next_payment_date > ? AND next_payment_date <= ?',
            (today.isoformat(), (today + timedelta(days=days)).isoformat())
        )
        logger.debug(f"Found {len(rows)} upcoming payments in next {days} days")
        return rows
    except Exception as e:
        logger.error(f"Error getting upcoming payments: {e}")
        return []


def _add_months(d: date, months: int, anchor_day: Optional[int] = None) -> date:
    """Add calendar months, clamping to the end of a shorter month.

    anchor_day is the day-of-month the schedule was created on. Without it a
    payment on the 31st would drift to the 28th after February and stay there.
    It is only applied while d is still on schedule (i.e. d is the anchor day,
    clamped to its month); a postponed or hand-edited date keeps its own day.
    """
    day = d.day
    if anchor_day and d.day == min(anchor_day, calendar.monthrange(d.year, d.month)[1]):
        day = anchor_day
    year, month = divmod(d.year * 12 + d.month - 1 + months, 12)
    month += 1
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def calculate_next_date(current_due: date, interval_type: str, interval_value: int,
                        anchor_day: Optional[int] = None) -> date:
    """Calculate the payment date following current_due"""
    if interval_type == 'monthly':
        return _add_months(current_due, interval_value, anchor_day)
    if interval_type == 'yearly':
        return _add_months(current_due, 12 * interval_value, anchor_day)
    if interval_type == 'weekly':
        return current_due + timedelta(weeks=interval_value)
    # Fallback default
    return current_due + timedelta(days=30)


async def mark_payment_status(client_id: int, user_id: int, status: str,
                              days_to_postpone: int = 7) -> bool:
    """Mark payment as paid/unpaid/postponed for a client owned by user_id.

    The history entry and the new due date are written in one transaction, so a
    failure can't leave a payment recorded without the schedule advancing.
    """
    if status not in ('paid', 'unpaid', 'postpone'):
        logger.warning(f"Unknown payment status '{status}' for client {client_id}")
        return False

    try:
        async with _transaction() as db:
            async with db.execute(
                'SELECT * FROM clients WHERE id = ? AND user_id = ?', (client_id, user_id)
            ) as cursor:
                client = await cursor.fetchone()

            if not client:
                logger.warning(f"Client {client_id} not found for user {user_id}")
                return False

            due = datetime.datetime.strptime(client['next_payment_date'], "%Y-%m-%d").date()

            if status == 'paid':
                try:
                    anchor_day = datetime.datetime.strptime(client['start_date'], "%Y-%m-%d").day
                except (TypeError, ValueError):
                    anchor_day = None
                next_date = calculate_next_date(
                    due, client['interval_type'], client['interval_value'], anchor_day
                )
                await db.execute('''
                    INSERT INTO payment_history (client_id, payment_date, amount, currency, status, notes)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (client_id, date.today().isoformat(), client['amount'], client['currency'],
                      'paid', 'Payment marked as paid'))
                await db.execute(
                    'UPDATE clients SET next_payment_date = ?, payment_status = ?, '
                    'updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                    (next_date.isoformat(), 'pending', client_id)
                )
            elif status == 'postpone':
                # Count from today if the payment is already overdue: "postpone by
                # 3 days" must mean a reminder in 3 days, not one that is still late.
                new_date = max(due, date.today()) + timedelta(days=days_to_postpone)
                await db.execute(
                    'UPDATE clients SET next_payment_date = ?, payment_status = ?, '
                    'updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                    (new_date.isoformat(), 'pending', client_id)
                )
            else:
                await db.execute(
                    'UPDATE clients SET payment_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                    (status, client_id)
                )

        logger.info(f"Marked payment as {status} for client {client_id}")
        return True
    except Exception as e:
        logger.error(f"Error marking payment status for client {client_id}: {e}")
        return False


async def add_payment_history(client_id: int, payment_date: str, amount: float,
                              currency: str, status: str, notes: str = '') -> bool:
    """Add a payment to history"""
    try:
        async with _transaction() as db:
            await db.execute('''
                INSERT INTO payment_history (client_id, payment_date, amount, currency, status, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (client_id, payment_date, amount, currency, status, notes))
        logger.info(f"Added payment history for client {client_id}: {status}")
        return True
    except Exception as e:
        logger.error(f"Error adding payment history for client {client_id}: {e}")
        return False


async def get_payment_history(client_id: int, limit: int = 10) -> List[aiosqlite.Row]:
    """Get payment history for a client"""
    try:
        return await _fetchall(
            'SELECT * FROM payment_history WHERE client_id = ? ORDER BY payment_date DESC, id DESC LIMIT ?',
            (client_id, limit)
        )
    except Exception as e:
        logger.error(f"Error getting payment history for client {client_id}: {e}")
        return []


async def get_statistics(user_id: int) -> Dict[str, Any]:
    """Get statistics for a user"""
    try:
        today = date.today()
        today_str = today.isoformat()
        month_start = today.replace(day=1).isoformat()
        month_end = today.replace(day=calendar.monthrange(today.year, today.month)[1]).isoformat()
        horizon = (today + timedelta(days=30)).isoformat()

        counts = await _fetchone('''
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(next_payment_date < ?), 0) AS overdue,
                   COALESCE(SUM(next_payment_date BETWEEN ? AND ?), 0) AS this_month
            FROM clients WHERE user_id = ?
        ''', (today_str, month_start, month_end, user_id))

        amounts = await _fetchall('''
            SELECT currency,
                   SUM(amount) AS expected,
                   SUM(CASE WHEN next_payment_date < ? THEN amount END) AS overdue,
                   SUM(CASE WHEN next_payment_date BETWEEN ? AND ? THEN amount END) AS upcoming
            FROM clients WHERE user_id = ? GROUP BY currency
        ''', (today_str, today_str, horizon, user_id))

        nearest_payments = await _fetchall('''
            SELECT name, amount, currency, next_payment_date FROM clients
            WHERE user_id = ? AND next_payment_date >= ?
            ORDER BY next_payment_date LIMIT 5
        ''', (user_id, today_str))

        return {
            'total_clients': counts['total'],
            'overdue_count': counts['overdue'],
            'expected_amounts': {row['currency']: row['expected'] for row in amounts},
            'overdue_amounts': {row['currency']: row['overdue'] for row in amounts if row['overdue']},
            'upcoming_amounts': {row['currency']: row['upcoming'] for row in amounts if row['upcoming']},
            'nearest_payments': nearest_payments,
            'this_month_count': counts['this_month']
        }
    except Exception as e:
        logger.error(f"Error getting statistics for user {user_id}: {e}")
        return {}


async def create_backup() -> Optional[str]:
    """Create a consistent backup of the database"""
    try:
        BACKUP_DIR.mkdir(exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = BACKUP_DIR / f"bot_database_backup_{timestamp}.db"
        suffix = 0
        while backup_file.exists():  # VACUUM INTO refuses to overwrite
            suffix += 1
            backup_file = BACKUP_DIR / f"bot_database_backup_{timestamp}_{suffix}.db"

        # Copying the file of a live database can capture a half-written state;
        # VACUUM INTO takes a consistent snapshot. It can't run inside a
        # transaction, hence the write lock.
        conn = await _get_conn()
        async with _write_lock:
            await conn.execute("VACUUM INTO ?", (str(backup_file),))
        logger.info(f"Created database backup: {backup_file}")

        await cleanup_old_backups(30)

        return str(backup_file)
    except Exception as e:
        logger.error(f"Error creating backup: {e}")
        return None


def _cleanup_old_backups_sync(days: int) -> int:
    if not BACKUP_DIR.exists():
        return 0

    cutoff = datetime.datetime.now().timestamp() - days * 86400
    deleted_count = 0
    for backup_file in BACKUP_DIR.glob("bot_database_backup_*.db"):
        if backup_file.stat().st_mtime < cutoff:
            backup_file.unlink()
            deleted_count += 1
            logger.info(f"Deleted old backup: {backup_file.name}")
    return deleted_count


async def cleanup_old_backups(days: int = 30) -> int:
    """Remove backups older than N days"""
    try:
        return await asyncio.to_thread(_cleanup_old_backups_sync, days)
    except Exception as e:
        logger.error(f"Error cleaning up backups: {e}")
        return 0


async def search_clients(user_id: int, query: str) -> List[aiosqlite.Row]:
    """Search clients by name or notes (case-insensitive, including Cyrillic)"""
    try:
        # Escape LIKE wildcards so '%' and '_' in the query match literally
        escaped = query.casefold().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        pattern = f"%{escaped}%"
        rows = await _fetchall(
            "SELECT * FROM clients WHERE user_id = ? "
            "AND (py_casefold(name) LIKE ? ESCAPE '\\' OR py_casefold(notes) LIKE ? ESCAPE '\\') "
            "ORDER BY next_payment_date",
            (user_id, pattern, pattern)
        )
        logger.debug(f"Found {len(rows)} clients matching '{query}' for user {user_id}")
        return rows
    except Exception as e:
        logger.error(f"Error searching clients for user {user_id}: {e}")
        return []


async def get_all_payment_history(user_id: int) -> List[aiosqlite.Row]:
    """Get all payment history for a user (for Excel export)"""
    try:
        return await _fetchall('''
            SELECT ph.*, c.name as client_name
            FROM payment_history ph
            JOIN clients c ON ph.client_id = c.id
            WHERE c.user_id = ?
            ORDER BY ph.payment_date DESC, ph.id DESC
        ''', (user_id,))
    except Exception as e:
        logger.error(f"Error getting all payment history for user {user_id}: {e}")
        return []
