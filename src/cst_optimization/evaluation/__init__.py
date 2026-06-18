"""CST-free evaluation database and retry infrastructure.

These modules were consolidated from ``workflows/rfgun_sao/`` in Phase 10.
They are pure Python with zero CST dependencies and provide shared
persistent evaluation storage, deduplication, retry loops, and
failure-skip logic.

Core modules
------------
- ``evaluation_database_schema`` — ``EvaluationDatabaseRecord``, ``ParameterIdentity``, DDL
- ``evaluation_database_storage`` — SQLite adapter (open, insert, query, migration)
- ``evaluation_database_dedup`` — in-memory dedup index (avoid re-running known parameters)
- ``evaluation_database_warm_start`` — build GP prior from stored evaluation records

Retry infrastructure
--------------------
- ``retry_runtime`` — configurable multi-tier retry loop (pure Python)
- ``retry_runtime_cst`` — adapts CST evaluator output to database records
- ``retry_taxonomy`` — failure classification and retry eligibility policies
- ``extreme_recovery_safety`` — process-kill / cleanup helpers (no CST)

Skip / reuse logic
------------------
- ``evaluation_success_reuse`` — reuse SUCCESS results from previous identical evaluations
- ``failure_skip_candidates`` — classify known-failure parameters for skipping
- ``failure_skip_dry_run`` — diagnose what would be skipped (without skipping)
- ``failure_skip_enforce`` — enforce skips at runtime
- ``evaluation_database_skip_records`` — data model for skip records
- ``evaluation_database_skip_storage`` — SQLite writer for skip records
"""
