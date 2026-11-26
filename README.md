# CU Food development

A Django application for CU food development, recipe costing, gate approvals and post-launch checks. The interface uses Mongolian labels, MNT amounts and the Asia/Ulaanbaatar time zone.

## Run locally

The local demo uses SQLite and the pinned dependencies in `requirements-local.txt`:

```powershell
python -m pip install -r requirements-local.txt
.\start-demo.ps1
```

The script applies migrations, runs `seed_demo` and starts http://127.0.0.1:8000. On first use, choose a password for the `demo` administrator. Later runs preserve the database and existing password. Demo products, suppliers and prices are sample data.

To run an existing local database without seeding demo records:

```powershell
$env:CUFOOD_SQLITE = '1'
$env:DEBUG = '1'
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

## Run with Docker Compose

Install and start [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) with Linux containers, or use Docker Engine with the Compose plugin on Linux. From this project directory, run:

```powershell
docker compose up --build -d
docker compose logs -f web
```

Open http://127.0.0.1:8000 after migrations finish. Press Ctrl+C to leave the log stream; the containers keep running. Compose starts the Django app on Python 3.12 and a PostgreSQL 17 database, waits for the database health check, and applies migrations before starting the app.

Create your first administrator in a separate terminal:

```powershell
docker compose exec web python manage.py createsuperuser
```

The database starts empty apart from Django and workflow configuration. If you want sample products and a demo administrator instead, run `docker compose exec web python manage.py seed_demo` and choose a password when prompted.

Database records and uploaded files live in the `postgres_data` and `media_data` Docker volumes. This creates a separate PostgreSQL database; it does not import the local `db.sqlite3` or existing `.store/media` files. To stop the stack while preserving its data:

```powershell
docker compose down
```

`docker compose down --volumes` deletes the stack's database and uploads. Rebuild with `docker compose up --build -d` after changing application code or dependencies; source files are copied into the image.

No `.env` file is required for local use. To customize settings, copy `.env.example` to `.env` and edit `DB_NAME`, `DB_USER`, `DB_PASSWORD` and `SECRET_KEY`. Compose reads `.env` for substitution and always connects the app to the `db` service on port 5432. Set `WEB_PORT=8001` in `.env` if host port 8000 is already in use, then open http://127.0.0.1:8001. Database initialization settings apply when the database volume is first created; editing credentials later does not change the existing PostgreSQL account.

This Compose setup is for local development: it uses Django's development server, `DEBUG=1` and local default credentials, exposes the website only on this computer, and keeps PostgreSQL off host ports. Production requires the deployment changes described below. Containers have not been built or started in this workspace because Docker is not installed.

Useful checks against the running PostgreSQL stack:

```powershell
docker compose config --quiet
docker compose exec web python manage.py check
docker compose exec web python manage.py test
```

The database readiness check follows [Docker's Compose startup guidance](https://docs.docker.com/compose/how-tos/startup-order/). PostgreSQL 17 uses `/var/lib/postgresql/data` for its persistent volume, as documented by the [official PostgreSQL image](https://hub.docker.com/_/postgres).

## Workflow and access

| Stage | Purpose | Default submitter | Review path |
| --- | --- | --- | --- |
| Gate 0 | Idea, product brief, target costing and launch targets | Category Manager (MD) | Fresh Food Manager; director if escalated |
| Gate 1 | Concept, tasting, recipe and feasibility | NPD / Product Developer | Fresh Food Manager; director if escalated or COGS is Red |
| Gate 2 | Production and launch readiness | NPD / Product Developer | QA acceptance, Fresh Food Manager, Merchandising Director |
| Launch GO | Day 7 and Day 14 quality and APSD checks | FF Planning | Gate 3 opens at launch +45 days |
| Gate 3 | Day-45 performance review and lessons | Category Manager (MD) | Fresh Food Manager, Merchandising Director; final completion |

The ten official role groups and their initial gate access are created by migrations. Configure editing, submission and decision rights through Gate Access in Django admin, and assign users to the appropriate groups. Model permissions control admin access; gate access controls the application workflow. Ownership alone does not grant editing rights.

Current-gate inputs are editable in draft by authorized users. Submission locks them until returned for corrections. Reviewers return to the same gate's draft; authorized draft submitters can return to the previous gate. Returns and escalations require a reason. Completed developments and other-gate views are read-only. Superusers follow the approval sequence and Launch time restrictions.

Authenticated users can browse developments, comment and download files. Uploading requires the relevant gate or checkpoint edit rights. Purchasing / Supply Chain and superusers can create suppliers and ingredients.

## Gate inputs and costing

Draft inputs are optional, but supplied numbers, dates and choices must be valid. Gate 0 requires product name, new/improvement, category, subcategory, product role, customer segment, at least one daypart, shelf price, CU margin, rebate, vendor margin, target APSD, producer, new supplier status, new raw material status, allergens and high-risk ingredients before submission or approval. Product fields appear together as 1.1–1.6; planned launch date stays optional. The next section, Хэрэглэгч ба нотолгоо, contains customer segment (2.1), optional customer/occasion description (2.2), dayparts (2.3) and optional evidence rows with attachments (2.4). Required fields have an asterisk. Other Gate 0–3 inputs are optional. Repeat rows may be partial. Gate 0's new/improvement route locks after its first submission. Product category is independently FF or ISF. Dropdowns use configured options and supported user-added choices.

The third Gate 0 section, Үнэ ба ашиг, contains competitor benchmark rows with a per-row image/price attachment column (3.1), required shelf price (3.2), configured VAT (3.3), required CU margin (3.4), required rebate including zero (3.5), required vendor margin (3.6), and calculated outputs (3.7–3.10). Drafts may omit these inputs, but submission and approval require all four pricing values.

The fourth Gate 0 section, Борлуулалтын зорилт, contains optional analog SKU rows with a current-SKU attachment column for each row (4.1), required target APSD (4.2), store scope (4.3), cluster (4.4), store count (4.5), cannibalisation rows (4.6), writeoff percentage (4.7) and calculated margin after writeoff (4.8 = 3.9 − 4.7). SKU attachments use G0-F4 storage and stay linked when rows are edited or renumbered. Earlier section-level uploads remain available in SKU file history. The margin updates while editing and is recalculated on the server; missing source values leave it blank.

The fifth Gate 0 section, Үйлдвэрлэл ба нийлүүлэлт, contains required producer (5.1), new supplier yes/no (5.2), new raw materials yes/no (5.3), optional seasonal price swing (5.4), MOQ (5.5), supplier capacity assessment (5.6) and supplier units/day capacity (5.7). A No answer satisfies the required yes/no fields. Partial drafts remain allowed; submission and approval require 5.1–5.3.

The sixth Gate 0 section, Хүнсний аюулгүй байдал, requires at least one allergen selection (6.1) and one high-risk ingredient selection (6.2) before submission or approval. Shelf life in hours (6.3) and technological risk notes (6.4) are optional. Existing Gate 0 shelf-life values in days are converted to hours, while Gate 2's approved shelf life retains its existing day unit.

Gate 0 uploads live in their corresponding rows: Хэрэглэгчийн нотолгоо for evidence (2.4), Жишиг бүтээгдэхүүний зураг, үнэ for each competitor (3.1), and current-SKU information for each analog SKU (4.1). The bottom upload cards are removed, and G0-F3 is retired from new uploads. Previously saved files remain downloadable, with unassigned evidence and competitor files shown in their section histories.

Gate 0 calculates target costs from shelf price, CU margin, rebate, vendor margin and configured VAT. VAT is configured through Target Costing Settings, with a 10% fallback. Missing source inputs leave the affected calculated values unknown.

```text
Price excluding VAT = shelf price / (1 + VAT / 100)
Maximum invoice price = price excluding VAT * (1 - CU margin / 100)
COGS limit = maximum invoice price * (1 - rebate / 100) * (1 - vendor margin / 100)
```

Gate 1's Жор ба өртөг section has repeatable trial records with individual files (1.1), recipe version (1.2), required ingredient rows (1.4), packaging cost (1.5), calculated COGS (1.6), Gate 0 section 3.10 limit (1.7), gap (1.8), status (1.9), manual COGS and reason (1.10), Amber/Red reason (1.11), action (1.12), and the inline supplier cost/quote file history (1.13). Drafts may be partial; submission and approval require at least one saved ingredient row with positive net weight and a valid yield. Trial decisions are Үргэлжлүүлэх, Батлагдсан and Зогсоох.

Gate 1's Амт ба хэрэглэгч section contains required taster count of at least five (2.1), required internal tasting score from 1–5 (2.2), tasting record files (2.3), optional consumer test participant count (2.4), consumer liking from 1–9 (2.5), would-buy percentage (2.6) and consumer test result files (2.7). If participants are entered, 2.5 and 2.6 become required before submission or approval; a zero would-buy percentage is valid. Stars update as participants are entered or cleared. Partial draft saves remain available, and the G1-F1/G1-F2 file histories appear in this section.

Gate 1's Түүхий эд section contains the repeatable material records as 3.1, with a Түүхий эдийн техникийн тодорхойлолт file column on every row. Each file stays linked to its material through edits and row removals. G1-F4 uploads are stored with the existing file history; older uploads without a row link remain visible in the material section.

Gate 1's Үйлдвэрлэл section contains required production line (4.1), daily capacity (4.2), a required Yes/No constraint choice (4.3) and constraint details (4.4), required only for Yes. Missing capacity is prefilled from Gate 0 section 5.7 on display and remains editable; saving confirms the Gate 1 value before advancement. Confirmed values are not overwritten when Gate 0 changes. Historical constraint categories are preserved in the description for review.

Gate 1's Савлагаа section replaces the old packaging type field with required packaging selection (5.1). Unit price (5.2) is the canonical Food packaging cost and automatically updates the read-only 1.5 display and calculated COGS. Material (5.3) and size (5.4) use shared dropdowns with + Нэмэх, preserving older text values. Certificate status (5.5) is required; new-packaging supplier, MOQ and lead days are optional details under 5.6. G1-F7 mock-up files and their history appear as 5.7.

Gate 1's Хүнсний аюулгүй байдал ба хадгалалт section contains required prohibited-ingredient check (6.1), process flow/CCP requirements check (6.2), storage test result (6.3), actual-packaging check (6.4) and test date (6.5). Gate 0 section 6.3 shelf-life hours appear read-only beside the storage result. Test record/photo files (6.6), laboratory (6.7), test duration in days (6.8), result due date (6.9) and QA risk assessment files (6.10) are optional. G1-F5 and G1-F6 histories are displayed in the section, and partial draft saves remain allowed.

Gate 1's Нэвтрүүлэлтийн маркетинг section contains campaign name (7.1), key message (7.2), launch marketing idea (7.3) and its file history (7.4). Product photos also live in marketing, while COGS Excel uploads live in the recipe-cost section. All Gate 1 fields and uploads are shown in their sections once; no standalone bottom field or upload area is rendered. Empty field subsets remain empty rather than falling back to the whole form.

The shared recipe editor is in Gate 1 section 1.4 and Gate 2 section 2.2. It stores ingredient quantities per finished product, ingredient yield, captured price per kg and per-product packaging cost:

```text
Ingredient cost = net grams / 1000 / ingredient yield * price per kg
Unit COGS = sum(ingredient costs) + packaging per product
```

Draft editors can add, update and remove lines and edit packaging. An omitted line price uses the ingredient catalog price; saved lines retain their captured prices. Each successful recipe or packaging save increments the recipe version and records an activity. The API and CSV export use the same unit-cost calculation. Legacy batch size, batch yield, labor and overhead do not enter this calculation.

When recipe lines exist, recipe COGS takes precedence. Otherwise the comparison uses Gate 1's optional typed COGS, then nonzero packaging cost. Gate 2 uses the shared recipe and Gate 1 fallback. Derived values are recalculated server-side and cannot be overridden by posted read-only values.

Both Gate 1 and Gate 2 show COGS status against the Gate 0 limit:

- Green: COGS is at or below the limit.
- Amber: above the limit, within the configured percentage allowance (5% fallback).
- Red: above that allowance.
- Pending: required source values are missing or the limit is not positive.

Gate 1's `amber_band` and `send_to_director` fields remain stored and calculated, but are hidden in the frontend.

Gate 2 opens with the Масс туршилт section: mass trial batch (1.1), trial date (1.2), trial yield (1.3), taste score (1.4), weight target (1.5), lower and upper weight limits (1.6–1.7), mass trial mean unit weight (1.8), technology transfer document version (1.9) and document date (1.10). All ten are required, marked with a red asterisk: drafts may be saved partially, but submission and final approval require every value. The weight target must lie within the limits. Section 2.10 keeps unit weight variation and the quality-standard upload. Section 2.11 defaults to the Gate 0 section 0.21 targets and allows a changed target; its reason box appears for the changed option and remains optional. Section 2.12 copies the planned date from Gate 0 section 0.22 and calculates actual launch date minus planned date: positive means delayed, negative means earlier. ISF Manual is available only for ISF developments. Invoice-based margins are calculated from the available pricing inputs.

## Launch GO and Gate 3

Launch timing starts at `development_food.launched_at`, which is retained across returns and re-entry. Day 7 unlocks after seven elapsed days and Day 14 after fourteen. Food Science edits check date and sample result; FF Planning edits actual APSD; QA edits the Day 14 complaint count. Each role also requires Launch edit permission.

Target APSD is read-only from Gate 2 section 2.11. Achievement is actual APSD / target APSD * 100: Green at 100% or above, Amber from 80% to below 100%, and Red below 80%. Missing or zero targets produce no percentage. An action, owner and deadline are required only for conditional or outside-limit sample results. Each day has one report/photo slot with upload history. Gate 2 quality standards remain available as reference documents.

Gate 3 unlocks at launch +45 elapsed days. Dashboard/detail access automatically opens due Gate 3 reviews. For external scheduling, use:

```powershell
python manage.py open_due_gate3
```

No background scheduler is installed. Gate 3 compares actual sales, write-offs and margin with Gate 0 targets, reads Day 7/14 sample results, and captures complaints, feedback, root causes and lessons. Handover checks recognize Gate 2 values and relevant Gate 2 file records. The Recipes and Lessons pages expose the corresponding saved information.

Structured gate transitions retain action, actor, timestamp and linked audit events. Ordinary saves and uploads do not reset gate timing. Historical timestamps remain unknown when there is no recorded source.

## Database structure

Each process has one permanent `development_food.id` (`Food.pk`). Gate 0-3 use `development_gate0` through `development_gate3`, with that same `development_id` as both primary key and foreign key. Gate fields use individual typed columns; selections and repeating rows use child tables. Active gate records are not JSON payloads.

`development_launchcheckpoint` stores one row per `development_id` and `day` (7 or 14). Its foreign key was renamed from `food_id` to `development_id`. Check dates, results, actual APSD, actions and complaints use individual columns. Target APSD is read from Gate 2 and achievement percentages are calculated.

| Upload | Current storage |
| --- | --- |
| G0-F1 through G0-F4 | `development_gate0_files` |
| G1-F1 through G1-F9 | `development_gate1_files` |
| G1-F10 marketing idea | Latest reference in `development_gate1.marketing_idea_file`; versions in activities |
| G2-F1 through G2-F11 | `development_gate2_files` |
| G2-F12 ISF Manual | `development_activity` |
| G2-F13 quality standard, section 2.10 | Latest reference in `development_gate2.quality_standard_file`; versions in activities |
| G3-F1 through G3-F3 | `development_gate3_files` |
| Launch Day 7 / Day 14 reports | `development_activity`, slots `L7F8` and `L14F10` |

Gate file tables store `development_id`, slot code, file path, original filename, uploader, upload time and an optional audit-event link. Direct gate file references also have filename, uploader and upload-time columns. Saving ordinary gate fields preserves these managed upload fields.

File contents remain under `.store/media/activities/<development_id>/`. Downloads require authentication. Dedicated gate file URLs and previous activity download URLs remain supported, including earlier versions.

The baseline schema excludes these unused Launch checkpoint columns: `sample_weight`, `sample_texture`, `sample_taste`, `sample_notes`, `sales_notes` and `complaints_details`.

When present, original gate JSON is retained in `development_gate_data_archive`, and the application reads its legacy values and conversion issues. The authorized test-data reset cleared the local developments, their related records, legacy archives and orphan records. Accounts, catalogs and workflow configuration were retained. New installations start with empty process and archive tables.

The application now has one migration, `development/migrations/0001_baseline.py`, generated from the current models. It includes workflow groups/access defaults, dropdown defaults and the VAT setting. Its replacement metadata recognizes databases with all 42 original migrations applied. Fresh databases create the final schema directly. Partially migrated legacy databases must finish the original migration history before using this baseline; see [migration baseline](docs/migration-baseline.md).

See [the database guide](docs/database.md) for relationships and SQL examples. Keep future incremental migrations and back up the database and media before schema changes. SQLite decimal snapshots have precision limits; use the application's Decimal calculations for full intermediate precision.

## Configuration and deployment

See [production handoff](docs/production-handoff.md) for the ordered developer and sysadmin steps, remaining release work and acceptance checks for the LAN-only Linux deployment.

The stack is Django 4.2.30 and Django REST Framework 3.15.2. PostgreSQL is the default database; its Psycopg driver is in `requirements.txt`. Local SQLite dependencies are in `requirements-local.txt`. The application uses server-rendered templates, static CSS/JavaScript, Django sessions and Django admin.

For PostgreSQL, create a separate application database and user, install `requirements.txt`, and set environment variables. See [PostgreSQL setup](docs/postgresql.md) for Linux installation and empty-database initialization. `.env.example` documents the settings; the application does not automatically load that file.

```powershell
Remove-Item Env:CUFOOD_SQLITE -ErrorAction SilentlyContinue
$env:DB_NAME = 'cu_food'
$env:DB_USER = 'cu_food'
$env:DB_PASSWORD = '<your database password>'
$env:DB_HOST = '127.0.0.1'
$env:DB_PORT = '5432'
$env:DEBUG = '1'
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

For production, set `DEBUG=0`, a non-default random `SECRET_KEY`, explicit `ALLOWED_HOSTS` and the production database credentials. Run migrations and `collectstatic`, configure a WSGI server and static asset serving, and use HTTPS. Preserve authenticated application downloads for uploaded files. Start with an empty PostgreSQL database; do not run `seed_demo` or import `db.sqlite3`. Production hosting and live PostgreSQL execution have not been verified in this workspace. Upgrade Python and Django to supported versions and validate the application before production use; Django 4.2 security support ended in April 2026.

## Verification and API

```powershell
$env:CUFOOD_SQLITE = '1'
$env:DEBUG = '1'
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

Tests cover gate forms, costing, role and time restrictions, approval sequencing, Launch checkpoints, file histories, authenticated downloads, API responses, baseline schema creation and setup defaults. Automated checks in this workspace use SQLite.

Authenticated read endpoints:

- `GET /api/foods/`
- `GET /api/foods/<id>/cost/`


Application writes use CSRF-protected server-rendered forms.

```text
config/                 settings, URLs and WSGI
development/           models, forms, workflow, views and APIs
  migrations/           schema and historical data migrations
  management/commands/  seed_demo and open_due_gate3
templates/             server-rendered screens
static/                logo, styles and browser behavior
docs/                  database guide
```
