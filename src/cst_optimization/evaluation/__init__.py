"""CST-free evaluation database and retry infrastructure.

These modules were promoted from ``workflows/rfgun_sao/`` in Phase 2.
They are pure Python with zero CST dependencies and are intended to be
reused by any workflow that needs persistent evaluation storage,
deduplication, retry loops, and failure-skip logic.

Core modules
------------
- ``schema`` — ``EvaluationDatabaseRecord``, ``ParameterIdentity``, DDL
- ``storage`` — SQLite adapter (open, insert, query, migration)
- ``dedup`` — in-memory dedup index (avoid re-running known parameters)
- ``warm_start`` — build GP prior from stored evaluation records

Retry infrastructure
--------------------
- ``retry_loop`` — configurable multi-tier retry loop (pure Python)
- ``retry_cst_adapter`` — adapts CST evaluator output to database records
- ``retry_taxonomy`` — failure classification and retry eligibility policies
- ``recovery_safety`` — process-kill / cleanup helpers (no CST)

Skip / reuse logic
------------------
- ``success_reuse`` — reuse SUCCESS results from previous identical evaluations
- ``failure_skip`` — classify known-failure parameters for skipping
- ``failure_skip_dry_run`` — diagnose what would be skipped (without skipping)
- ``failure_skip_enforce`` — enforce skips at runtime
- ``skip_records`` — data model for skip records
- ``skip_storage`` — SQLite writer for skip records
"""
