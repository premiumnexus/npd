# Migration baseline

`development/migrations/0001_baseline.py` replaces the original 42 application migrations. It was generated from the current models with `makemigrations`, then given the required setup defaults and Django replacement metadata. `__init__.py` remains as the migration package marker. Django's built-in apps keep their own migrations.

## New empty PostgreSQL database

Set the connection environment variables as described in [PostgreSQL setup](postgresql.md), then run:

```bash
python manage.py migrate --plan
python manage.py migrate
python manage.py createsuperuser
```

The baseline creates the final tables, relationships, constraints and indexes without intermediate legacy tables or backfills. It also creates the 10 workflow groups, 50 gate-access defaults, 30 Gate 0 dropdown options and the default VAT setting. It creates no demo users, products, ingredients or suppliers.

## Fully migrated existing database

A database with all original development migrations from `0001_initial` through `0042_remove_obsolete_launch_fields` applied is recognized through the baseline's `replaces` list. Django treats the baseline schema as already applied. Running `migrate` records the replacement without recreating the application's tables or changing business records.

Back up the database and media first, then inspect `python manage.py migrate --plan`. For a fully migrated database at this baseline, there should be no application schema operations to run. Do not delete `django_migrations` rows or use `--fake` to hide a schema mismatch. The existing local SQLite database was left intact; transition was rehearsed on a copy.

## Partially migrated legacy database

The intermediate migration files are no longer in the active tree. A partially upgraded database must first use the previous Git revision to apply the complete original history through `0042`, including its data conversions, before switching to the baseline revision. Alternatively, create a new empty database. Do not run the new baseline over legacy tables or treat it as a data-conversion tool.

## Future model changes

```bash
python manage.py makemigrations development
python manage.py migrate
```

New changes should be committed as incremental migrations after `0001_baseline`. Do not repeatedly delete migration history once databases depend on it. Keep the baseline's `replaces` metadata while existing databases may still carry the original history.

The removed migration-specific tests were tied to intermediate schemas that no longer exist. Current workflow, storage and file-history tests remain; baseline tests verify fresh setup defaults, preservation of customized defaults and complete schema recreation. The old files and tests are available in Git history and in the local `.store/backups/migration-baseline-*/legacy-migrations-and-tests.zip` archive created during consolidation.

Reference: [Django migration squashing and replacement metadata](https://docs.djangoproject.com/en/4.2/topics/migrations/#squashing-migrations).
