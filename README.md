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

Gate 0-3 inputs are optional, but supplied numbers, dates and choices must be valid. Repeat rows may be partial. Gate 0's new/improvement route locks after its first submission. Product category is independently FF or ISF. Dropdowns use configured options and supported user-added choices.

Gate 0 calculates target costs from shelf price, CU margin, rebate, vendor margin and configured VAT. VAT is configured through Target Costing Settings, with a 10% fallback. Missing source inputs leave the affected calculated values unknown.

```text
Price excluding VAT = shelf price / (1 + VAT / 100)
Maximum invoice price = price excluding VAT * (1 - CU margin / 100)
COGS limit = maximum invoice price * (1 - rebate / 100) * (1 - vendor margin / 100)
```

The shared recipe editor is in Gate 1 section 1.3 and Gate 2 section 2.2. It stores ingredient quantities per finished product, ingredient yield, captured price per kg and per-product packaging cost:

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

Gate 2 section 2.10 groups weight measurements and the quality-standard upload. Section 2.11 defaults to the Gate 0 section 0.21 targets and allows a changed target; its reason box appears for the changed option and remains optional. Section 2.12 copies the planned date from Gate 0 section 0.22 and calculates actual launch date minus planned date: positive means delayed, negative means earlier. ISF Manual is available only for ISF developments. Invoice-based margins are calculated from the available pricing inputs.

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

Migration `0042_remove_obsolete_launch_fields` removes these unused Launch checkpoint columns: `sample_weight`, `sample_texture`, `sample_taste`, `sample_notes`, `sales_notes` and `complaints_details`. Existing rows and remaining field values are preserved.

Original gate JSON is retained in `development_gate_data_archive`. The application still reads archived legacy values and conversion issues; this table is not disposable. The local cleanup audit identified orphan records. Their cleanup is a separate data-maintenance task from the schema changes described here.

See [the database guide](docs/database.md) for relationships and SQL examples. Preserve migration history and back up the database and media before schema changes. SQLite decimal snapshots have precision limits; use the application's Decimal calculations for full intermediate precision.

## Configuration and deployment

The stack is Django 4.2.30 and Django REST Framework 3.15.2. MySQL dependencies are in `requirements.txt`; local SQLite dependencies are in `requirements-local.txt`. The application uses server-rendered templates, static CSS/JavaScript, Django sessions and Django admin.

For MySQL, create a separate application database and user, install `requirements.txt`, and set environment variables. `.env.example` documents them; the application does not automatically load that file.

```powershell
Remove-Item Env:CUFOOD_SQLITE -ErrorAction SilentlyContinue
$env:DB_NAME = 'cu_food'
$env:DB_USER = 'cu_food'
$env:DB_PASSWORD = '<your database password>'
$env:DB_HOST = 'localhost'
$env:DB_PORT = '3306'
$env:DEBUG = '1'
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

For production, set `DEBUG=0`, a non-default random `SECRET_KEY`, explicit `ALLOWED_HOSTS` and the production database credentials. Run migrations and `collectstatic`, configure a WSGI server and static asset serving, and use HTTPS. Preserve authenticated application downloads for uploaded files. Demo setup is optional and should not be used to seed a production database. Production hosting and MySQL execution have not been verified in this workspace.

## Verification and API

```powershell
$env:CUFOOD_SQLITE = '1'
$env:DEBUG = '1'
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

Tests cover gate forms, costing, role and time restrictions, approval sequencing, Launch checkpoints, file histories, authenticated downloads, API responses and schema/data migrations. Automated checks in this workspace use SQLite.

Authenticated read endpoints:

- `GET /api/foods/`
- `GET /api/foods/<id>/cost/`

12312321321321321

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
