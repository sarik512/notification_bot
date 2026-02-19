import aiosqlite
import datetime
from datetime import date, timedelta
from typing import List, Optional, Dict, Any
from config import Config
from logger import logger

DB_NAME = Config.DB_NAME


async def init_db():
    """Initialize database with all required tables and indexes"""
    try:
        async with aiosqlite.connect(DB_NAME) as db:
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
            await db.commit()
            
            # Check if we need to migrate existing table
            cursor = await db.execute("PRAGMA table_info(clients)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]
            
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
                    await db.commit()
            
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
            
            # Create indexes for better performance
            await db.execute('CREATE INDEX IF NOT EXISTS idx_user_id ON clients(user_id)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_next_payment_date ON clients(next_payment_date)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_payment_status ON clients(payment_status)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_payment_history_client ON payment_history(client_id)')
            
            await db.commit()
            logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise


async def add_client(user_id: int, name: str, amount: float, currency: str, 
                    start_date: str, interval_type: str, interval_value: int,
                    category: str = 'general', notes: str = '') -> Optional[int]:
    """Add a new client to the database"""
    try:
        # Calculate next payment date
        if isinstance(start_date, str):
            start_dt = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
        else:
            start_dt = start_date
        
        next_date = start_dt 
        
        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute('''
                INSERT INTO clients (user_id, name, amount, currency, start_date, 
                                   interval_type, interval_value, next_payment_date, 
                                   category, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, name, amount, currency, start_dt.isoformat(), 
                  interval_type, interval_value, next_date.isoformat(), 
                  category, notes))
            await db.commit()
            client_id = cursor.lastrowid
            logger.info(f"Added client: {name} (ID: {client_id}) for user {user_id}")
            return client_id
    except Exception as e:
        logger.error(f"Error adding client {name}: {e}")
        return None


async def get_clients(user_id: int) -> List[aiosqlite.Row]:
    """Get all clients for a specific user"""
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                'SELECT * FROM clients WHERE user_id = ? ORDER BY next_payment_date', 
                (user_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                logger.debug(f"Retrieved {len(rows)} clients for user {user_id}")
                return rows
    except Exception as e:
        logger.error(f"Error getting clients for user {user_id}: {e}")
        return []


async def get_client_by_id(client_id: int) -> Optional[aiosqlite.Row]:
    """Get a specific client by ID"""
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM clients WHERE id = ?', (client_id,)) as cursor:
                client = await cursor.fetchone()
                return client
    except Exception as e:
        logger.error(f"Error getting client {client_id}: {e}")
        return None


async def update_client(client_id: int, **kwargs) -> bool:
    """Update client fields"""
    try:
        if not kwargs:
            return False
        
        # Build dynamic UPDATE query
        fields = ', '.join([f"{key} = ?" for key in kwargs.keys()])
        values = list(kwargs.values())
        values.append(client_id)
        
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                f'UPDATE clients SET {fields}, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                values
            )
            await db.commit()
            logger.info(f"Updated client {client_id}: {kwargs}")
            return True
    except Exception as e:
        logger.error(f"Error updating client {client_id}: {e}")
        return False


async def delete_client(client_id: int) -> bool:
    """Delete a client and their payment history"""
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute('DELETE FROM clients WHERE id = ?', (client_id,))
            await db.commit()
            logger.info(f"Deleted client {client_id}")
            return True
    except Exception as e:
        logger.error(f"Error deleting client {client_id}: {e}")
        return False


async def get_due_payments() -> List[aiosqlite.Row]:
    """Get all payments that are due today or overdue"""
    try:
        today = date.today().isoformat()
        async with aiosqlite.connect(DB_NAME) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                'SELECT * FROM clients WHERE next_payment_date <= ?', 
                (today,)
            ) as cursor:
                rows = await cursor.fetchall()
                logger.debug(f"Found {len(rows)} due payments")
                return rows
    except Exception as e:
        logger.error(f"Error getting due payments: {e}")
        return []


async def get_upcoming_payments(days: int = 3) -> List[aiosqlite.Row]:
    """Get payments due in the next N days"""
    try:
        today = date.today()
        future_date = (today + timedelta(days=days)).isoformat()
        today_str = today.isoformat()
        
        async with aiosqlite.connect(DB_NAME) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                'SELECT * FROM clients WHERE next_payment_date > ? AND next_payment_date <= ?',
                (today_str, future_date)
            ) as cursor:
                rows = await cursor.fetchall()
                logger.debug(f"Found {len(rows)} upcoming payments in next {days} days")
                return rows
    except Exception as e:
        logger.error(f"Error getting upcoming payments: {e}")
        return []


async def update_next_payment_date(client_id: int, current_due_date_str: str, 
                                   interval_type: str, interval_value: int) -> bool:
    """Calculate and update the next payment date"""
    try:
        current_due_date = datetime.datetime.strptime(current_due_date_str, "%Y-%m-%d").date()
        
        if interval_type == 'monthly':
            # Add months
            month = current_due_date.month + interval_value
            year = current_due_date.year + (month - 1) // 12
            month = (month - 1) % 12 + 1
            day = min(current_due_date.day, [31,
                29 if year % 4 == 0 and not year % 100 == 0 or year % 400 == 0 else 28,
                31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month-1])
            new_date = date(year, month, day)
            
        elif interval_type == 'yearly':
            new_date = current_due_date.replace(year=current_due_date.year + interval_value)
            
        elif interval_type == 'weekly':
            new_date = current_due_date + timedelta(weeks=interval_value)
        else:
            # Fallback default
            new_date = current_due_date + timedelta(days=30)
            
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                'UPDATE clients SET next_payment_date = ?, payment_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?', 
                (new_date.isoformat(), 'pending', client_id)
            )
            await db.commit()
            logger.info(f"Updated next payment date for client {client_id} to {new_date}")
            return True
    except Exception as e:
        logger.error(f"Error updating next payment date for client {client_id}: {e}")
        return False


async def add_payment_history(client_id: int, payment_date: str, amount: float, 
                              currency: str, status: str, notes: str = '') -> bool:
    """Add a payment to history"""
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute('''
                INSERT INTO payment_history (client_id, payment_date, amount, currency, status, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (client_id, payment_date, amount, currency, status, notes))
            await db.commit()
            logger.info(f"Added payment history for client {client_id}: {status}")
            return True
    except Exception as e:
        logger.error(f"Error adding payment history for client {client_id}: {e}")
        return False


async def get_payment_history(client_id: int, limit: int = 10) -> List[aiosqlite.Row]:
    """Get payment history for a client"""
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                'SELECT * FROM payment_history WHERE client_id = ? ORDER BY payment_date DESC LIMIT ?',
                (client_id, limit)
            ) as cursor:
                rows = await cursor.fetchall()
                return rows
    except Exception as e:
        logger.error(f"Error getting payment history for client {client_id}: {e}")
        return []


async def mark_payment_status(client_id: int, status: str, days_to_postpone: int = 7) -> bool:
    """Mark payment as paid/unpaid and update next date if paid"""
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM clients WHERE id = ?', (client_id,)) as cursor:
                client = await cursor.fetchone()
            
            if not client:
                logger.warning(f"Client {client_id} not found")
                return False
            
            if status == 'paid':
                # Add to payment history
                await add_payment_history(
                    client_id,
                    date.today().isoformat(),
                    client['amount'],
                    client['currency'],
                    'paid',
                    'Payment marked as paid'
                )
                
                # Calculate next payment date
                await update_next_payment_date(
                    client_id,
                    client['next_payment_date'],
                    client['interval_type'],
                    client['interval_value']
                )
                logger.info(f"Marked payment as paid for client {client_id}")
                
            elif status == 'postpone':
                # Postpone by specified days
                current_date = datetime.datetime.strptime(client['next_payment_date'], "%Y-%m-%d").date()
                new_date = current_date + timedelta(days=days_to_postpone)
                await db.execute(
                    'UPDATE clients SET next_payment_date = ?, payment_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                    (new_date.isoformat(), 'pending', client_id)
                )
                await db.commit()
                logger.info(f"Postponed payment for client {client_id} by {days_to_postpone} days")
                
            else:
                # Just mark as unpaid
                await db.execute(
                    'UPDATE clients SET payment_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?', 
                    (status, client_id)
                )
                await db.commit()
                logger.info(f"Marked payment as {status} for client {client_id}")
            
            return True
    except Exception as e:
        logger.error(f"Error marking payment status for client {client_id}: {e}")
        return False


async def get_statistics(user_id: int) -> Dict[str, Any]:
    """Get statistics for a user"""
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            db.row_factory = aiosqlite.Row
            
            # Total clients
            async with db.execute(
                'SELECT COUNT(*) as count FROM clients WHERE user_id = ?', 
                (user_id,)
            ) as cursor:
                total_clients = (await cursor.fetchone())['count']
            
            # Overdue payments
            today = date.today().isoformat()
            async with db.execute(
                'SELECT COUNT(*) as count FROM clients WHERE user_id = ? AND next_payment_date < ?',
                (user_id, today)
            ) as cursor:
                overdue_count = (await cursor.fetchone())['count']
            
            # Total expected amount
            async with db.execute(
                'SELECT SUM(amount) as total, currency FROM clients WHERE user_id = ? GROUP BY currency',
                (user_id,)
            ) as cursor:
                amounts = await cursor.fetchall()
            
            # Payments this month
            first_day = date.today().replace(day=1).isoformat()
            last_day = (date.today().replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
            last_day_str = last_day.isoformat()
            
            async with db.execute(
                'SELECT COUNT(*) as count FROM clients WHERE user_id = ? AND next_payment_date >= ? AND next_payment_date <= ?',
                (user_id, first_day, last_day_str)
            ) as cursor:
                this_month_count = (await cursor.fetchone())['count']
            
            return {
                'total_clients': total_clients,
                'overdue_count': overdue_count,
                'expected_amounts': {row['currency']: row['total'] for row in amounts},
                'this_month_count': this_month_count
            }
    except Exception as e:
        logger.error(f"Error getting statistics for user {user_id}: {e}")
        return {}


async def create_backup() -> Optional[str]:
    """Create a backup of the database"""
    try:
        import shutil
        from pathlib import Path
        
        # Create backups directory
        backup_dir = Path("backups")
        backup_dir.mkdir(exist_ok=True)
        
        # Create backup filename with timestamp
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"bot_database_backup_{timestamp}.db"
        
        # Copy database
        shutil.copy2(DB_NAME, backup_file)
        logger.info(f"Created database backup: {backup_file}")
        
        # Cleanup old backups
        await cleanup_old_backups(30)
        
        return str(backup_file)
    except Exception as e:
        logger.error(f"Error creating backup: {e}")
        return None


async def cleanup_old_backups(days: int = 30) -> int:
    """Remove backups older than N days"""
    try:
        from pathlib import Path
        import time
        
        backup_dir = Path("backups")
        if not backup_dir.exists():
            return 0
            
        current_time = time.time()
        deleted_count = 0
        
        for backup_file in backup_dir.glob("bot_database_backup_*.db"):
            # Check modification time
            if current_time - backup_file.stat().st_mtime > days * 86400:
                backup_file.unlink()
                deleted_count += 1
                logger.info(f"Deleted old backup: {backup_file.name}")
                
        return deleted_count
    except Exception as e:
        logger.error(f"Error cleaning up backups: {e}")
        return 0


async def search_clients(user_id: int, query: str) -> List[aiosqlite.Row]:
    """Search clients by name or notes"""
    try:
        query = f"%{query}%"
        async with aiosqlite.connect(DB_NAME) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                'SELECT * FROM clients WHERE user_id = ? AND (name LIKE ? OR notes LIKE ?) ORDER BY next_payment_date', 
                (user_id, query, query)
            ) as cursor:
                rows = await cursor.fetchall()
                logger.debug(f"Found {len(rows)} clients matching '{query}' for user {user_id}")
                return rows
    except Exception as e:
        logger.error(f"Error searching clients for user {user_id}: {e}")
        return []


async def get_all_payment_history(user_id: int) -> List[aiosqlite.Row]:
    """Get all payment history for a user (for Excel export)"""
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('''
                SELECT ph.*, c.name as client_name 
                FROM payment_history ph
                JOIN clients c ON ph.client_id = c.id
                WHERE c.user_id = ? 
                ORDER BY ph.payment_date DESC
            ''', (user_id,)) as cursor:
                rows = await cursor.fetchall()
                return rows
    except Exception as e:
        logger.error(f"Error getting all payment history for user {user_id}: {e}")
        return []
