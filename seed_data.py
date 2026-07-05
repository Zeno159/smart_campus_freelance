"""
Seed script — inserts ~100+ fake records into marketplace.db.
Run: python seed_data.py
All fake users have password: password123
"""

import sqlite3
import os
import random
from datetime import datetime, date, timedelta
from passlib.context import CryptContext
from backend.database import init_db, DB_PATH

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
PWD_HASH = pwd_context.hash("password123")


# ── Helpers ──────────────────────────────────────────────────────────────────

def dt(days_ago=0, hours=0):
    return (datetime.now() - timedelta(days=days_ago, hours=hours)).strftime("%Y-%m-%d %H:%M:%S")

def future_date(days_ahead):
    return (date.today() + timedelta(days=days_ahead)).isoformat()

def past_date(days_ago):
    return (date.today() - timedelta(days=days_ago)).isoformat()

REVIEWS = {
    5.0: [
        "Outstanding work, delivered exactly what was needed. Highly recommend.",
        "Exceeded all expectations. Will definitely hire again.",
        "Perfect quality and timely submission. 10/10.",
        "Absolutely flawless. One of the best freelancers on the platform.",
    ],
    4.5: [
        "Very good work, just a couple of minor adjustments needed.",
        "Great communication throughout and solid final output.",
        "Really happy with the result. Quick turnaround too.",
    ],
    4.0: [
        "Good work overall, requirements were met satisfactorily.",
        "Decent quality, needed one round of revisions but final result was fine.",
        "Job done correctly. Communication was acceptable.",
    ],
    3.5: [
        "Average output, required more revisions than expected.",
        "Work was okay but took longer than the deadline.",
    ],
}

def pick_review(score):
    bucket = min(REVIEWS.keys(), key=lambda k: abs(k - score))
    return random.choice(REVIEWS[bucket])


# ── Main seed function ────────────────────────────────────────────────────────

def seed():
    init_db()
    print(f"Seeding database at: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    c = conn.cursor()

    existing = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if existing > 2:
        print(f"Already seeded ({existing} users found). Delete backend/marketplace.db and re-run to reset.")
        conn.close()
        return

    print("Seeding database...")

    # ── Categories ──
    cats_raw = c.execute("SELECT category_id, category_name FROM categories").fetchall()
    cats = {name: cid for cid, name in cats_raw}

    # ── 1. Users ──────────────────────────────────────────────────────────────
    USER_COUNT = 200
    first_names = [
        "Aarav", "Ishaan", "Vihaan", "Arjun", "Krishna", "Sai", "Advait", "Rohan", "Aditya", "Ravi",
        "Priya", "Ananya", "Kavya", "Shruti", "Tanvi", "Sanya", "Riya", "Neha", "Ishita", "Meera",
        "Tanya", "Aditi", "Simran", "Anika", "Shreya", "Nisha", "Pooja", "Aisha", "Rhea", "Saira",
        "Rajat", "Kunal", "Sahil", "Nikhil", "Ramesh", "Anand", "Divya", "Shanaya", "Yash", "Naveen"
    ]
    last_names = [
        "Patel", "Singh", "Sharma", "Nair", "Kumar", "Gupta", "Reddy", "Joshi", "Mehta", "Desai",
        "Chopra", "Bhattacharya", "Iyer", "Rao", "Nair", "Jain", "Kapoor", "Pillai", "Mukherjee", "Saxena"
    ]

    USER_DATA = []
    used_names = set()
    for idx in range(USER_COUNT):
        first = random.choice(first_names)
        last = random.choice(last_names)
        name_base = f"{first} {last}"
        name = name_base
        suffix = 1
        while name in used_names:
            suffix += 1
            name = f"{name_base} {suffix}"
        used_names.add(name)

        email = f"{first.lower()}.{last.lower()}{idx+1}@campus.edu"
        contact = str(9000000000 + idx)
        USER_DATA.append((name, email, contact))

    # Everyone starts with Rs.12000 — deductions/credits applied later
    U = []
    for name, email, contact in USER_DATA:
        already = c.execute("SELECT user_id FROM users WHERE email = ?", (email,)).fetchone()
        if already:
            U.append(already[0])
            continue
        c.execute(
            "INSERT INTO users (name, email, password_hash, contact, wallet_balance) VALUES (?,?,?,?,?)",
            (name, email, PWD_HASH, contact, 12000.00),
        )
        uid = c.lastrowid
        U.append(uid)
        c.execute("INSERT OR IGNORE INTO freelancer_stats (freelancer_id) VALUES (?)", (uid,))

    conn.commit()
    print(f"  Inserted {len(U)} users.")

    # ── Wallet top-ups (before any projects) ───────────────────────────────────
    for uid in U:
        topup = random.choice([1500, 2500, 3500, 4500, 5500])
        c.execute(
            """INSERT INTO wallet_transactions (user_id, amount, txn_type, description, txn_date)
               VALUES (?,?,'credit','Initial wallet top-up',?)""",
            (uid, topup, dt(days_ago=60, hours=0)),
        )
    c.execute("UPDATE users SET wallet_balance = 20000")
    conn.commit()
    print(f"  Inserted wallet top-ups for {len(U)} users.")

    # ── 2. Services ───────────────────────────────────────────────────────────
    CATEGORY_TEMPLATES = {
        "Web Development":      ((1500, 5000), "Responsive website with modern UI, fast loading and mobile-friendly experience."),
        "Graphic Design":       ((700, 2600), "Creative branding and visual design assets tailored for student projects."),
        "Content Writing":      ((400, 1800), "High-quality content for blogs, websites, and marketing collateral."),
        "Video Editing":        ((600, 3200), "Professional video editing with transitions, color correction and music."),
        "Data Analysis":        ((1200, 4200), "Data insights, dashboards and reports powered by Python or Excel."),
        "Mobile Development":   ((2500, 6200), "Mobile app prototype or simple app with polished screens and basic features."),
        "Digital Marketing":    ((900, 2800), "Campaign strategy, social media content and analytics recommendations."),
        "UI/UX Design":         ((1500, 5200), "Wireframes, mockups and UI design for apps and web dashboards."),
        "Photography":         ((1800, 4200), "Event photography and photo editing with final image delivery."),
        "Translation":          ((300, 1200), "Accurate translation for documents, articles and assignments."),
    }

    service_titles = [
        "Portfolio Site", "Brand Identity", "Product Copy", "Social Media Kit", "Dashboard Design",
        "Mobile App UI", "Explainer Video", "Research Report", "Campaign Strategy", "Photo Coverage",
    ]

    SERVICES = []
    for idx, uid in enumerate(U):
        category = random.choice(list(cats.keys()))
        cat_id = cats[category]
        title = f"{random.choice(service_titles)} for {category}"
        price = random.randint(*CATEGORY_TEMPLATES[category][0])
        desc = CATEGORY_TEMPLATES[category][1]
        SERVICES.append((uid, cat_id, title, price, desc))

    for uid, cat_id, title, price, desc in SERVICES:
        c.execute(
            "INSERT OR IGNORE INTO services (user_id, category_id, title, base_price, description) VALUES (?,?,?,?,?)",
            (uid, cat_id, title, price, desc),
        )
    conn.commit()
    print(f"  Inserted {len(SERVICES)} services.")

    # ── 3. Completed Contracts ─────────────────────────────────────────────────
    completed_contracts = []
    for idx, freelancer_id in enumerate(U):
        client_id = random.choice([uid for uid in U if uid != freelancer_id])
        category = random.choice(list(cats.keys()))
        cat_id = cats[category]
        budget = random.randint(1200, 5200)
        agreed_price = budget - random.randint(50, 300)
        rating = random.choice([4.0, 4.5, 5.0])
        days_ago = random.randint(20, 70)

        title = f"{category} project #{idx + 1}"
        desc = f"Completed {category.lower()} work with quality review and final delivery."
        exp_date = past_date(days_ago - 2)
        created_at = dt(days_ago + 8)
        start_at = dt(days_ago + 4)
        completed_at = dt(days_ago)

        c.execute(
            """INSERT INTO job_requests
               (client_id, category_id, title, description, budget, expected_date, status, created_date)
               VALUES (?,?,?,?,?,?,'completed',?)""",
            (client_id, cat_id, title, desc, budget, exp_date, created_at),
        )
        job_id = c.lastrowid

        c.execute(
            "INSERT INTO applications (job_id, freelancer_id, proposed_price, status, applied_date) VALUES (?,?,?,'accepted',?)",
            (job_id, freelancer_id, agreed_price, dt(days_ago + 5)),
        )

        for other_id in random.sample([uid for uid in U if uid not in (client_id, freelancer_id)], k=2):
            other_price = agreed_price + random.randint(-150, 250)
            c.execute(
                "INSERT OR IGNORE INTO applications (job_id, freelancer_id, proposed_price, status, applied_date) VALUES (?,?,?,'rejected',?)",
                (job_id, other_id, max(100, other_price), dt(days_ago + 4)),
            )

        c.execute(
            "INSERT INTO contracts (job_id, freelancer_id, agreed_price, status, start_date, completion_date) VALUES (?,?,?,'completed',?,?)",
            (job_id, freelancer_id, agreed_price, start_at, completed_at),
        )
        contract_id = c.lastrowid
        completed_contracts.append(contract_id)

        commission = round(agreed_price * 0.01, 2)
        freelancer_amt = round(agreed_price - commission, 2)

        c.execute(
            "INSERT INTO payments (contract_id, total_amount, commission_amount, freelancer_amount, payment_date, payment_status) VALUES (?,?,?,?,?,'released')",
            (contract_id, agreed_price, commission, freelancer_amt, completed_at),
        )

        c.execute(
            "INSERT INTO work_submissions (contract_id, file_path, file_type, submitted_date, notes) VALUES (?,?,?,?,?)",
            (contract_id, f"/uploads/work_{contract_id}_final.pdf", "pdf", dt(days_ago - 1), "Final deliverable completed and uploaded."),
        )

        c.execute(
            "INSERT INTO ratings (contract_id, rating_score, review_text, rating_date) VALUES (?,?,?,?)",
            (contract_id, rating, pick_review(rating), completed_at),
        )

        c.execute(
            "INSERT INTO wallet_transactions (user_id, amount, txn_type, description, txn_date) VALUES (?,?,'hold',?,?)",
            (client_id, agreed_price, f"Wallet hold for: {title}", start_at),
        )
        c.execute(
            "INSERT INTO wallet_transactions (user_id, amount, txn_type, description, txn_date) VALUES (?,?,'credit',?,?)",
            (freelancer_id, freelancer_amt, f"Payment for completed contract #{contract_id}", completed_at),
        )

        c.execute("UPDATE users SET wallet_balance = wallet_balance - ? WHERE user_id = ?", (agreed_price, client_id))
        c.execute("UPDATE users SET wallet_balance = wallet_balance + ? WHERE user_id = ?", (freelancer_amt, freelancer_id))

    conn.commit()
    print(f"  Inserted {len(completed_contracts)} completed jobs.")

    # ── 4. Active Contracts ───────────────────────────────────────────────────
    active_contracts = []
    for idx, client_id in enumerate(U):
        freelancer_id = random.choice([uid for uid in U if uid != client_id])
        category = random.choice(list(cats.keys()))
        cat_id = cats[category]
        budget = random.randint(1400, 5400)
        agreed_price = budget - random.randint(50, 300)
        days_ago = random.randint(2, 18)

        title = f"{category} active job #{idx + 1}"
        desc = f"Ongoing {category.lower()} assignment with active deliverables and review." 
        exp_date = future_date(random.randint(7, 25))
        created_at = dt(days_ago + 3)
        start_at = dt(days_ago)

        c.execute(
            """INSERT INTO job_requests
               (client_id, category_id, title, description, budget, expected_date, status, created_date)
               VALUES (?,?,?,?,?,?,'assigned',?)""",
            (client_id, cat_id, title, desc, budget, exp_date, created_at),
        )
        job_id = c.lastrowid

        c.execute(
            "INSERT INTO applications (job_id, freelancer_id, proposed_price, status, applied_date) VALUES (?,?,?,'accepted',?)",
            (job_id, freelancer_id, agreed_price, dt(days_ago + 1)),
        )

        for other_id in random.sample([uid for uid in U if uid not in (client_id, freelancer_id)], k=1):
            c.execute(
                "INSERT OR IGNORE INTO applications (job_id, freelancer_id, proposed_price, status, applied_date) VALUES (?,?,?,'rejected',?)",
                (job_id, other_id, agreed_price + 150, dt(days_ago + 1)),
            )

        c.execute(
            "INSERT INTO contracts (job_id, freelancer_id, agreed_price, status, start_date) VALUES (?,?,?,'active',?)",
            (job_id, freelancer_id, agreed_price, start_at),
        )
        contract_id = c.lastrowid
        active_contracts.append(contract_id)

        commission = round(agreed_price * 0.01, 2)
        freelancer_amt = round(agreed_price - commission, 2)

        c.execute(
            "INSERT INTO payments (contract_id, total_amount, commission_amount, freelancer_amount, payment_status) VALUES (?,?,?,?,'pending')",
            (contract_id, agreed_price, commission, freelancer_amt),
        )

        c.execute(
            "INSERT INTO wallet_transactions (user_id, amount, txn_type, description, txn_date) VALUES (?,?,'hold',?,?)",
            (client_id, agreed_price, f"Wallet hold for active job: {title}", start_at),
        )
        c.execute("UPDATE users SET wallet_balance = wallet_balance - ? WHERE user_id = ?", (agreed_price, client_id))

    conn.commit()
    print(f"  Inserted {len(active_contracts)} active jobs.")

    # ── 5. Open Jobs ─────────────────────────────────────────────────────────
    open_jobs = []
    for idx, client_id in enumerate(U):
        freelancer_ids = [uid for uid in U if uid != client_id]
        if not freelancer_ids:
            continue
        category = random.choice(list(cats.keys()))
        cat_id = cats[category]
        budget = random.randint(1000, 5200)
        title = f"{category} job request #{idx + 1}"
        desc = f"Looking for a freelancer to complete {category.lower()} work with quality output and clear communication."
        exp_date = future_date(random.randint(7, 30))
        created_at = dt(random.randint(1, 15))

        c.execute(
            """INSERT INTO job_requests
               (client_id, category_id, title, description, budget, expected_date, status, created_date)
               VALUES (?,?,?,?,?,?,'open',?)""",
            (client_id, cat_id, title, desc, budget, exp_date, created_at),
        )
        job_id = c.lastrowid
        open_jobs.append(job_id)

        # Add 1-4 pending applications from other users
        applicants = random.sample(freelancer_ids, k=min(4, len(freelancer_ids)))
        for freelancer_id in applicants:
            proposed = max(100, budget - random.randint(0, 400))
            c.execute(
                "INSERT OR IGNORE INTO applications (job_id, freelancer_id, proposed_price, status, applied_date) VALUES (?,?,?,'pending',?)",
                (job_id, freelancer_id, proposed, dt(random.randint(0, 10))),
            )

    conn.commit()
    print(f"  Inserted {len(open_jobs)} open jobs.")

    # ── 6. Update freelancer stats for all users ──────────────────────────────
    for uid in U:
        row = c.execute(
            """SELECT AVG(r.rating_score), COUNT(r.rating_id), COALESCE(SUM(p.freelancer_amount), 0)
               FROM ratings r
               JOIN contracts ct ON r.contract_id = ct.contract_id
               JOIN payments p ON p.contract_id = ct.contract_id
               WHERE ct.freelancer_id = ? AND p.payment_status = 'released'""",
            (uid,),
        ).fetchone()

        avg_r = round(row[0] or 0, 2)
        total_jobs = row[1] or 0
        total_earn = round(row[2] or 0, 2)

        c.execute(
            """INSERT INTO freelancer_stats (freelancer_id, avg_rating, total_jobs, total_earnings)
               VALUES (?,?,?,?)
               ON CONFLICT(freelancer_id) DO UPDATE SET
                   avg_rating     = excluded.avg_rating,
                   total_jobs     = excluded.total_jobs,
                   total_earnings = excluded.total_earnings""",
            (uid, avg_r, total_jobs, total_earn),
        )

    conn.commit()

    # ── 6. Summary ────────────────────────────────────────────────────────────
    counts = {
        "users":        c.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "services":     c.execute("SELECT COUNT(*) FROM services").fetchone()[0],
        "jobs":         c.execute("SELECT COUNT(*) FROM job_requests").fetchone()[0],
        "applications": c.execute("SELECT COUNT(*) FROM applications").fetchone()[0],
        "contracts":    c.execute("SELECT COUNT(*) FROM contracts").fetchone()[0],
        "payments":     c.execute("SELECT COUNT(*) FROM payments").fetchone()[0],
        "submissions":  c.execute("SELECT COUNT(*) FROM work_submissions").fetchone()[0],
        "ratings":      c.execute("SELECT COUNT(*) FROM ratings").fetchone()[0],
        "txns":         c.execute("SELECT COUNT(*) FROM wallet_transactions").fetchone()[0],
    }

    conn.close()

    print("\nSeed complete. Record counts:")
    for k, v in counts.items():
        print(f"  {k:<16} {v}")
    print("\nAll fake users have password: password123")
    print("Login at: http://localhost:8000")


if __name__ == "__main__":
    seed()
