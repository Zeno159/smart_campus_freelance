import sqlite3
import os
from backend.auth_utils import hash_password

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "marketplace.db")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            email         TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            contact       TEXT NOT NULL,
            wallet_balance REAL DEFAULT 0 CHECK (wallet_balance >= 0),
            is_admin      INTEGER DEFAULT 0 CHECK (is_admin IN (0,1)),
            join_date     TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS categories (
            category_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            category_name        TEXT NOT NULL,
            commission_percentage REAL DEFAULT 1.0
        );

        CREATE TABLE IF NOT EXISTS services (
            service_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            category_id   INTEGER REFERENCES categories(category_id),
            title         TEXT NOT NULL,
            base_price    REAL NOT NULL CHECK (base_price > 0),
            description   TEXT,
            active_status TEXT DEFAULT 'Y' CHECK (active_status IN ('Y','N')),
            created_date  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS job_requests (
            job_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id     INTEGER NOT NULL REFERENCES users(user_id),
            category_id   INTEGER REFERENCES categories(category_id),
            title         TEXT NOT NULL,
            status        TEXT DEFAULT 'open' CHECK (status IN ('open','assigned','in_progress','submitted','completed','cancelled')),
            description   TEXT,
            budget        REAL NOT NULL CHECK (budget > 0),
            expected_date TEXT NOT NULL,
            created_date  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS applications (
            application_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id         INTEGER NOT NULL REFERENCES job_requests(job_id),
            freelancer_id  INTEGER NOT NULL REFERENCES users(user_id),
            proposed_price REAL NOT NULL CHECK (proposed_price > 0),
            status         TEXT DEFAULT 'pending' CHECK (status IN ('pending','accepted','rejected')),
            applied_date   TEXT DEFAULT (datetime('now')),
            UNIQUE (job_id, freelancer_id)
        );

        CREATE TABLE IF NOT EXISTS contracts (
            contract_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id          INTEGER NOT NULL REFERENCES job_requests(job_id),
            freelancer_id   INTEGER NOT NULL REFERENCES users(user_id),
            agreed_price    REAL NOT NULL,
            status          TEXT DEFAULT 'active' CHECK (status IN ('active','submitted','completed','disputed')),
            start_date      TEXT DEFAULT (datetime('now')),
            completion_date TEXT
        );

        CREATE TABLE IF NOT EXISTS payments (
            payment_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_id       INTEGER NOT NULL REFERENCES contracts(contract_id),
            total_amount      REAL NOT NULL,
            commission_amount REAL NOT NULL,
            freelancer_amount REAL NOT NULL,
            payment_date      TEXT,
            payment_status    TEXT DEFAULT 'pending' CHECK (payment_status IN ('pending','released','refunded'))
        );

        CREATE TABLE IF NOT EXISTS ratings (
            rating_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_id  INTEGER NOT NULL UNIQUE REFERENCES contracts(contract_id),
            rating_score REAL NOT NULL CHECK (rating_score BETWEEN 1 AND 5),
            review_text  TEXT,
            rating_date  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS freelancer_stats (
            freelancer_id  INTEGER PRIMARY KEY REFERENCES users(user_id),
            avg_rating     REAL DEFAULT 0,
            total_jobs     INTEGER DEFAULT 0,
            total_earnings REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS work_submissions (
            submission_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_id    INTEGER NOT NULL REFERENCES contracts(contract_id),
            file_path      TEXT NOT NULL,
            file_type      TEXT NOT NULL CHECK (file_type IN ('pdf','jpeg','jpg','png','docx')),
            submitted_date TEXT DEFAULT (datetime('now')),
            notes          TEXT
        );

        CREATE TABLE IF NOT EXISTS wallet_transactions (
            txn_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(user_id),
            amount      REAL NOT NULL,
            txn_type    TEXT NOT NULL CHECK (txn_type IN ('credit','debit','hold','release')),
            description TEXT,
            txn_date    TEXT DEFAULT (datetime('now'))
        );
    """)

    # Seed categories if empty
    count = cursor.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
    if count == 0:
        cats = [
            ("Web Development", 1.0),
            ("Graphic Design", 1.0),
            ("Content Writing", 1.0),
            ("Video Editing", 1.0),
            ("Data Analysis", 1.0),
            ("Mobile Development", 1.0),
            ("Digital Marketing", 1.0),
            ("UI/UX Design", 1.0),
            ("Photography", 1.0),
            ("Translation", 1.0),
        ]
        cursor.executemany(
            "INSERT INTO categories (category_name, commission_percentage) VALUES (?,?)", cats
        )

    # Ensure older databases without an admin flag still have the column
    existing_columns = [row[1] for row in cursor.execute("PRAGMA table_info(users)").fetchall()]
    if "is_admin" not in existing_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0 CHECK (is_admin IN (0,1))")
        conn.commit()

    # Seed a dedicated admin user if none exists
    admin_count = cursor.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1").fetchone()[0]
    if admin_count == 0:
        cursor.execute(
            "INSERT INTO users (name, email, password_hash, contact, wallet_balance, is_admin) VALUES (?, ?, ?, ?, ?, 1)",
            ("Marketplace Admin", "admin@campusmarketplace.local", hash_password("Admin@123"), "0000000000", 0),
        )
        conn.commit()

    conn.commit()
    conn.close()
