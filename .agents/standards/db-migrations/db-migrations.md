---
domain: db-migrations
description: Conventions for schema migration immutability, tracking keys, backfill predicates, Postgres function identity, and adjudicating schema disputes.
---

# Database Migrations

> **Scope**: Dev-plane standard for skills and agents that author or review
> schema migrations, backfills, or migration runners.

## Rules

| Area | Rule |
| --- | --- |
| Shipped migrations are immutable | A migration runner executes each file exactly once; editing a previously shipped file has no effect on already-migrated environments and silently diverges dev from staging/production. Every change — including a backfill that corrects data written by an earlier migration — is a new numbered migration file. |
| Tracking key | Applied-migration tracking keys on the filename basename (`WHERE name = '<basename>'`), not on an integer version column. Two files sharing a version number (branching mistake) would collide on a version key; a name key also survives reordering and renumbering. |
| Backfill predicates | A DELETE/UPDATE backfill targeting sentinel-stamped rows uses exact equality (`WHERE org_id = 'admin'`), never `LIKE` or substring matching — substrings silently hit real IDs that contain the sentinel (e.g. `admin-112`, `xisynet-admin`). |
| Postgres function identity | Postgres identifies a function by (schema-qualified name, argument type list) — not return type. `CREATE OR REPLACE` with a changed argument list creates a separate overload or errors; prior signatures stay live and make calls ambiguous ("function ... is not unique"). Numeric aliases are distinct types (`REAL`/float4 vs `FLOAT`/float8). Idempotent scripts `DROP FUNCTION IF EXISTS` each historical signature explicitly before `CREATE`. |
| Schema archaeology | The true evolution of a function or table signature comes from `git log -S <symbol>` (pickaxe) on the defining file, and fully deleted schema definitions are recovered from the historical commit (`<commit>^`) rather than reverse-engineered from current code. Memory and quick reads of current state undercount historical signatures. |
| Dispute adjudication | A suspected migration/DDL defect (overload resolution, implicit casts, DEFAULT-argument interaction) is settled by live reproduction in a disposable database container — create the legacy state, run the migration battery, observe the actual error. Static reasoning about these semantics is error-prone even for careful reviewers; a live repro cheaply confirms the bug or closes the false positive. |
