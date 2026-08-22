#!/usr/bin/env python3
"""Report what is actually in the database — accounts, kasten and any leftovers.

For when the app says one thing and you want to see the rows for yourself.
Read-only: it never changes anything.

Run it against the container's database:

    docker compose exec kledingkast python - < scripts/check_db.py

or locally, pointing at your own data directory:

    python scripts/check_db.py /path/to/wardrobe.db
"""

import sys

import sqlite3

DB = sys.argv[1] if len(sys.argv) > 1 else "/data/wardrobe.db"
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
def has(t):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone()
print(f"Database: {DB}\n")
print("ACCOUNTS die nog bestaan:")
for r in con.execute("SELECT id, username, display_name, is_admin FROM users ORDER BY id"):
    print(f"  id={r['id']:<4} @{r['username']:<15} {r['display_name']}{'  (beheerder)' if r['is_admin'] else ''}")
print("\nKASTEN:")
for r in con.execute("SELECT w.id, w.owner_id, w.name, (SELECT COUNT(*) FROM items i WHERE i.wardrobe_id=w.id) n FROM wardrobes w ORDER BY w.id"):
    owner = con.execute("SELECT username FROM users WHERE id=?", (r["owner_id"],)).fetchone()
    tag = f"@{owner['username']}" if owner else ">>> EIGENAAR BESTAAT NIET (wees) <<<"
    print(f"  kast {r['id']:<3} eigenaar {r['owner_id']:<4} {tag:<38} {r['n']} kledingstukken")
print("\nWEZEN (zou 0 moeten zijn na v0.4.1):")
checks = [
 ("kasten zonder eigenaar", "SELECT COUNT(*) FROM wardrobes WHERE owner_id NOT IN (SELECT id FROM users)"),
 ("kledingstukken zonder kast", "SELECT COUNT(*) FROM items WHERE wardrobe_id IS NOT NULL AND wardrobe_id NOT IN (SELECT id FROM wardrobes)"),
 ("beoordelingen zonder gebruiker", "SELECT COUNT(*) FROM matches WHERE user_id NOT IN (SELECT id FROM users)"),
 ("beoordelingen zonder kledingstuk", "SELECT COUNT(*) FROM matches WHERE item_a_id NOT IN (SELECT id FROM items) OR item_b_id NOT IN (SELECT id FROM items)"),
 ("gedeelde toegang zonder gebruiker", "SELECT COUNT(*) FROM wardrobe_members WHERE user_id NOT IN (SELECT id FROM users)"),
]
if has("match_skips"):
    checks.append(("overslagen zonder gebruiker", "SELECT COUNT(*) FROM match_skips WHERE user_id NOT IN (SELECT id FROM users)"))
if has("invitations"):
    checks.append(("uitnodigingen zonder maker", "SELECT COUNT(*) FROM invitations WHERE created_by_id NOT IN (SELECT id FROM users)"))
for label, sql in checks:
    print(f"  {label:<36}: {con.execute(sql).fetchone()[0]}")

print(
    "\nStaat er iets bij de wezen hoger dan 0? Herstart dan de container:"
    " de opruiming draait bij het opstarten."
)
