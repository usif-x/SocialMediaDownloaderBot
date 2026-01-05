"""
Database migration script to add new columns for history/restore feature.
Run this once to update existing database.
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from database.database import engine


def migrate():
    """Add new columns to downloads table"""

    migrations = [
        "ALTER TABLE downloads ADD COLUMN IF NOT EXISTS format_type VARCHAR(20)",
        "ALTER TABLE downloads ADD COLUMN IF NOT EXISTS message_id BIGINT",
        "ALTER TABLE downloads ADD COLUMN IF NOT EXISTS file_id VARCHAR(255)",
    ]

    with engine.connect() as conn:
        for migration in migrations:
            try:
                conn.execute(text(migration))
                print(f"✅ Executed: {migration[:50]}...")
            except Exception as e:
                print(f"⚠️ Migration note: {e}")

        conn.commit()

    print("\n✅ Migration completed!")


if __name__ == "__main__":
    migrate()
