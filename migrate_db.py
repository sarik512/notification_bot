"""
Database migration script for existing users
This script updates the old database schema to the new one
"""
import aiosqlite
import asyncio
from datetime import datetime


async def migrate_database():
    """Migrate old database to new schema"""
    db_name = 'bot_database.db'
    
    print("🔄 Starting database migration...")
    
    try:
        async with aiosqlite.connect(db_name) as db:
            # Check if migration is needed
            cursor = await db.execute("PRAGMA table_info(clients)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            print(f"📋 Current columns: {column_names}")
            
            # Add new columns if they don't exist
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
                    print(f"➕ Adding column: {col_name}")
                    await db.execute(f"ALTER TABLE clients ADD COLUMN {col_name} {col_def}")
                    await db.commit()
                else:
                    print(f"✅ Column already exists: {col_name}")
            
            # Create payment_history table if it doesn't exist
            print("📊 Creating payment_history table...")
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
            await db.commit()
            print("✅ payment_history table created")
            
            # Create indexes
            print("🔍 Creating indexes...")
            indexes = [
                ("idx_user_id", "CREATE INDEX IF NOT EXISTS idx_user_id ON clients(user_id)"),
                ("idx_next_payment_date", "CREATE INDEX IF NOT EXISTS idx_next_payment_date ON clients(next_payment_date)"),
                ("idx_payment_status", "CREATE INDEX IF NOT EXISTS idx_payment_status ON clients(payment_status)"),
                ("idx_payment_history_client", "CREATE INDEX IF NOT EXISTS idx_payment_history_client ON payment_history(client_id)")
            ]
            
            for idx_name, idx_sql in indexes:
                await db.execute(idx_sql)
                print(f"✅ Index created: {idx_name}")
            
            await db.commit()
            
            # Get statistics
            cursor = await db.execute("SELECT COUNT(*) FROM clients")
            client_count = (await cursor.fetchone())[0]
            
            print("\n" + "=" * 50)
            print("✅ Migration completed successfully!")
            print(f"📊 Total clients in database: {client_count}")
            print("=" * 50)
            
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        raise


if __name__ == "__main__":
    import sys
    import io
    
    # Fix Windows console encoding
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    print("=" * 50)
    print("Database Migration Tool")
    print("=" * 50)
    print("\nWARNING: This will modify your database.")
    print("Make sure you have a backup before proceeding!\n")
    
    response = input("Continue? (yes/no): ")
    
    if response.lower() in ['yes', 'y']:
        asyncio.run(migrate_database())
    else:
        print("\nMigration cancelled")
