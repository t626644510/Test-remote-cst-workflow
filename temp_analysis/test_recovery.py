"""Test recovery DELETE+INSERT logic with temporary SQLite DB."""
import sys, os
sys.path.insert(0, 'src')
import sqlite3, tempfile
from cst_optimization.evaluation.evaluation_database_schema import schema_ddl_sqlite

tmpdir = tempfile.mkdtemp()
db_path = os.path.join(tmpdir, 'test_recovery.db')
conn = sqlite3.connect(db_path)

for stmt in schema_ddl_sqlite().split(';'):
    stmt = stmt.strip()
    if stmt:
        conn.execute(stmt)
conn.commit()

# Insert 3 fake failed records + 1 success
records = [
    ('key_a', '["x"]', '[1.0]', 'solver_failed', '{"freq":11.4}'),
    ('key_b', '["x"]', '[2.0]', 'solver_failed', '{"freq":11.5}'),
    ('key_c', '["x"]', '[3.0]', 'success', '{"freq":11.424}'),
    ('key_d', '["x"]', '[4.0]', 'solver_failed', None),
]
for r in records:
    conn.execute(
        'INSERT INTO evaluation_records (parameter_key, param_names, param_values, status, raw_metrics, retry_count) VALUES (?,?,?,?,?,?)',
        r + (0,)
    )
conn.commit()

# --- Recovery simulation ---
rows = conn.execute(
    "SELECT id, param_values, status FROM evaluation_records WHERE status != 'success'"
).fetchall()
print(f'Found {len(rows)} failed records (expected 3)')

for row in rows:
    old_id, param_values, old_status = row
    print(f'  Recovering id={old_id}')
    conn.execute('DELETE FROM evaluation_records WHERE id = ?', (old_id,))
    conn.execute(
        'INSERT INTO evaluation_records (parameter_key, param_names, param_values, status, raw_metrics, retry_count) VALUES (?,?,?,?,?,?)',
        (f'key_{old_id}', '["x"]', param_values, 'success', '{"freq":11.424}', 1)
    )
conn.commit()

# --- Verify ---
final = conn.execute(
    "SELECT id, status, retry_count FROM evaluation_records ORDER BY id"
).fetchall()
conn.close()

print(f'\nFinal state: {len(final)} records (expected 4)')
ids_seen = set()
for r in final:
    ids_seen.add(r[0])
    print(f'  id={r[0]} status={r[1]} retry_count={r[2]}')

dup = len(final) != len(ids_seen)
all_old_gone = all(r[0] not in (1,2,4) or r[1] == 'success' for r in final)
ok = len(final) == 4 and not dup and all_old_gone
print(f'\nAll checks: {"PASSED" if ok else "FAILED"}')
