# CU Food development MVP

A working Django application for taking CU food ideas through development and calculating the finished cost per unit in MNT.

## Database structure

Each development has one permanent `Food.id`. Gate 0–3 use separate typed tables, each keyed by that same `development_id`. Product names, categories, dates and numeric inputs are individual columns; selections and repeating rows use linked tables. Existing JSON payloads are retained only in a read-only migration archive. See [the database guide](docs/database.md) for the schema, relationships and SQL examples.

## Run the local demo (PowerShell)

```powershell
python -m pip install -r requirements-local.txt
.\start-demo.ps1
```

On the first run, choose a password for the `demo` administrator. Open http://127.0.0.1:8000 and sign in. Subsequent runs preserve your database and password. Demo suppliers, recipes and prices are illustrative. The demo administrator can exercise every role; real users should receive only their assigned group in `/admin/`.

## Official five-gate workflow

| Gate | Purpose | Submitter | Review order |
| --- | --- | --- | --- |
| Gate 0 | Idea and brief | Category Manager (MD) | Fresh Food Manager; director if escalated |
| Gate 1 | Concept and recipe | NPD / Product Developer | Fresh Food Manager; director if escalated |
| Gate 2 | Industrialisation and launch readiness | NPD / Product Developer | QA acceptance ? Fresh Food Manager ? Merchandising Director |
| Launch GO | Day 7 / Day 14 quality and APSD checks | FF Planning | Completion sends development to Gate 3 |
| Gate 3 | Day-45 review | Category Manager (MD) | Fresh Food Manager ? Merchandising Director; final completion |

FF Planning is the configurable default Launch GO submitter. Gate inputs remain optional except the Day 7 / Day 14 action/owner/deadline text, which is required for conditional or outside-limit sample results. Day 7, Day 14 and Day 45 access enforce their elapsed-time conditions.

All ten official parties have per-gate access records under **Admin ? ?? ????? ??????**. Edit the checkboxes for editing, submission, QA acceptance, manager decision and director decision there. Assign existing official groups to users under Users ? Groups. Django's model permissions govern Admin access; gate access records govern the website workflow. Changes to group memberships or gate access take effect on the next request. Old Product/R&D/Procurement/Quality/Finance groups no longer grant website workflow access.

Editing is available only while a gate is in draft and the user's group has edit access. Submission locks inputs until a reviewer returns the gate for corrections. Owners do not bypass group permissions. Reviewers return to the same gate's draft; a submitter returning a draft moves to the preceding gate. Returns and escalations require reasons. Each review decision is recorded in the activity log. All authenticated users can view developments, comment, upload and download attachments, including after final completion. Superusers can perform all workflow actions but must follow the review sequence.

Supplier and ingredient catalog creation is available to Purchasing / Supply Chain and superusers. Gate editor rights apply to the current combined recipe and costing form; separate scientific, marketing and production forms are not implemented.

Existing stages migrate as follows: concept ? Gate 0; recipe ? Gate 1; sourcing/quality/costing ? Gate 2; approved ? Launch GO. Attachment stage metadata also migrates. Existing activity text and uploaded files are preserved. Earlier approvals are not fabricated: migrated Gate 2 developments begin in draft. Gate 3 completion is a separate flag so the dashboard continues to show exactly five gates.

## Legacy cost calculation (retained records only)

```text
Effective finished units = batch units × yield percent / 100
Ingredient batch cost = sum(batch quantity × captured ingredient price)
Cost per finished unit = ingredient batch cost / effective finished units
                       + packaging per unit + labor per unit + overhead per unit
Gross margin % = (selling price − cost per unit) / selling price × 100
```

Enter quantities in the ingredient's purchase unit (kg, L or each); convert grams to kg before entry. Yield applies to batch output. Prices are copied to recipe lines when added, so catalog changes do not silently change existing costings. Re-add a line to capture a new price. Decimal arithmetic is used; display and export totals round to two decimal places. Tax, freight and distribution are excluded unless included in overhead. The legacy recipe calculator is no longer part of the process. Gate submission does not require ingredient records or calculated margins.

## Architecture and Potential Point parity

Reference inspected: `C:/Users/bilguun.e/Desktop/cupp_system`.

| Concern | CU Food implementation |
| --- | --- |
| Application | Django monolith, `manage.py`, WSGI entry point |
| Backend | Django models, ModelForms, views and URL routes |
| Database | MySQL by default, migrations through Django ORM |
| Frontend | Server-rendered Django templates and static CSS |
| Authentication | Django database sessions, users and groups |
| Authorization | Server-side group checks and ownership checks |
| Administration | Django admin |
| APIs | Django REST Framework, session authentication |
| Storage | `.store/static` and `.store/media` configuration |

Potential Point pins Django 2.1.7; this MVP runs on the installed Django 4.2.30 and DRF 3.15.2. It reproduces the architectural pattern, not exact legacy dependency versions. Its interface has custom CSS and standard HTML forms; Potential Point's Limitless, Tailwind and jQuery assets were not copied. Local demo mode explicitly uses SQLite. No deployment server, reverse proxy configuration, production database, shared login or live integrations have been copied or provisioned. The reference contained no verified production hosting definition.

```text
config/                 settings, URLs, WSGI
development/            food, sourcing, costing, approvals, APIs
  migrations/           database schema
  management/commands/  repeatable demo data
templates/              shared layout and server-rendered screens
static/                 application stylesheet
```

## MySQL configuration

Install `requirements.txt` in your environment, create a separate MySQL database and user, and set shell environment variables from `.env.example`. The example file is documentation and is not automatically loaded.

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

Database migrations create and reuse the ten official role groups and their gate access defaults. Assign users to these groups in Django admin. The optional `python manage.py seed_demo` command adds sample data. Use an independent CU Food database; do not point the app at Potential Point's database.

For deployment, set `DEBUG=0`, a random `SECRET_KEY`, explicit `ALLOWED_HOSTS`, and MySQL credentials; run migrations and `collectstatic`, serve `config.wsgi:application` with your WSGI server and serve static assets through your web server. HTTPS is required for production session cookies. Production deployment is not configured or verified here.

## Verification and API

```powershell
$env:CUFOOD_SQLITE = '1'
$env:DEBUG = '1'
python manage.py check
python manage.py test
```

Tests cover costing, snapshots, all five gates, submission and ordered approvals, escalation, Red COGS routing, access configuration, dashboard counts, completed record locking, attachments, rendered screens and authenticated APIs. Tests use SQLite; MySQL and browser rendering have not been verified.

Authenticated read endpoints:

- `GET /api/foods/`
- `GET /api/foods/<id>/cost/`

Writes use CSRF-protected server-rendered forms. No external service credentials or Potential Point data are required.

The process detail pages no longer show the legacy recipe/ingredients, unit-cost card, production/market-launch date panel or combined costing editor. Their write actions are retired. Existing database records are retained. Numeric cost APIs/exports remain legacy records and are not derived from the new free-text gate fields.

## Gate 1 and Gate 2 ingredient calculator

The shared recipe calculator appears in Gate 1 section 1.3 and Gate 2 section 2.2. Draft editors for the current gate can add, update and remove ingredient lines and save per-unit packaging cost. Each line stores net grams per product, ingredient yield and its captured price per kg. An omitted line price defaults to the ingredient catalog price. Existing lines retain their captured prices. Every successful recipe or packaging save increments the recipe version and records the current gate in the activity log. Inputs lock during gate review, and browsing another gate is read-only.

The calculated result is unit COGS: the sum of each line's net grams / 1000 / ingredient yield × price per kg, plus packaging per unit. Gate 2's final recipe version, final COGS and invoice-based margin calculations use the updated recipe. Derived values are recomputed server-side when the gate form is displayed or saved.

## Current Gate 1 formula (per product)

Quantity is now the amount of each ingredient in ONE finished product. Unit ingredient cost is the sum of quantity times captured purchase-unit price. Batch size, yield, packaging, labor and overhead do not affect this result and are no longer editable in the calculator. For example, 0.1 kg chicken at 14,500 MNT/kg costs 1,450 MNT per product. Existing quantities are preserved; review any previously entered batch quantities and change them to per-product quantities. The API and CSV export use the same per-product formula. This supersedes the previous batch/yield calculation descriptions above.

## Gate 0 typed brief

Gate 0 now uses typed controls. A new/improvement choice is required when creating a project and is shown first. Drafts may be incomplete, but supplied numbers and enum choices must be valid. Submission validates the complete brief, including 2?3 analogous SKU rows. Improvement requires an existing SKU code, at least one R01?R11 code and a description of what changes and why. The route is locked by `Food.gate0_submitted_at` on first successful submission and remains locked after returns. FF/ISF is a separate category; no relationship between that category and the new/improvement route is assumed.

Whole-tugrik shelf price must be positive. CU margin is 0?60% with one decimal place; rebate is 0?30%, including zero; vendor margin is 0?60%. Benchmarks contain product/price/weight rows. Analogues contain SKU and units/store/day, with a separate target. Cannibalisation contains affected SKU and sales-taken percentage rows. Segment, daypart and evidence level are choices. Store scope is All/Cluster/Pilot plus store count, with a required cluster for Cluster submissions. Supply risk uses yes/no selections and numeric MOQ. Capacity uses Yes/No/Unknown and units/day. Allergens and high-risk ingredients are multi-select lists. Shelf life uses days. Launch date is a date and raises a non-blocking warning for the next 30 days.

Admin ? Gate 0 ????????? ??????????? manages product roles, subcategories (with FF/ISF parent category), reason codes, customer segments, clusters, allergens and high-risk ingredients. The default product roles and screenshot-specified allergens/high-risk inputs are seeded. R01?R11 are seeded as codes without invented descriptions. Producer choices include Central Foods and the supplier directory. The official subcategory, segment, cluster lists and reason-code descriptions are awaiting confirmation; no fabricated business list is supplied. Submissions require configured subcategory/segment choices.

COGS limit (0.13) is disabled and blank while the referenced section 8 formula is unavailable. No COGS formula or VAT rate has been inferred. Gate 0 percentages are stored but are not applied to the independent Gate 1 ingredient calculator. Earlier free-text values are shown for manual conversion when incompatible, and original values are archived in `_legacy_free_text` on conversion. The repeat-row widget supports adding rows and marking rows for deletion. Existing file slots and permissions are unchanged.

## Gate 0 optional-field update

All Gate 0 fields are optional, both at creation and submission. Empty or partial repeat rows, blank improvement details, missing cluster selection and missing evidence references do not block submission. Analogous SKU rows have no minimum (maximum three remains). Supplied values still follow their data types, numeric bounds and configured enum choices. The new/improvement route remains locked after first submission. This supersedes earlier statements about mandatory Gate 0 fields.

## Gate 1 typed fields

Gate 1 fields now use numeric inputs, enum choices, dates and repeatable rows. All are optional. Supplied tasting scores must be 1?5, supplied taster counts at least five, consumer liking scores 1?9 and buying percentages 0?100. The material table stores each new/changed material's specification status, price/kg, MOQ and second-source status. Capacity contains line, units/day, shifts and a constraint choice. The 0-hour and 72-hour checks each record texture, taste, appearance, water release and Pass/Fail. Lab planning includes lab, days and result date. QA and certificate choices use Yes/No. Packaging types are configured in Admin; no unofficial options are seeded. Marketing has separate name, key-message and launch-idea fields.

Each Gate 1 ingredient-editor save increments the recipe version. The version field reads that version when available; otherwise a version number may be typed. Estimated COGS uses an optional typed amount when supplied, otherwise the ingredient calculator. Gate 0's saved COGS limit is the comparison basis. Admin ? Gate 1 COGS ????? defines the maximum Green/Amber percentages of that limit; amounts above Amber are Red. No thresholds have been assumed. Missing limit, ingredients/typed COGS or thresholds produces Pending. Reason and action fields are provided for Amber/Red but remain optional per the user's instruction. The missing section 8 Gate 0 formula is still required for an automatically derived limit.

Derived values are read-only and recomputed server-side, not trusted from submitted values. Gate 1 submission validates supplied types without requiring blank fields. Existing free-text entries remain visible for manual conversion and are archived on the first typed save. Existing gate permissions, file slots and review ordering remain in force.

## Gate 2 typed fields

All Gate 2 inputs remain optional. Supplied values are validated for their types and ranges: trial batch kg, yield percentage, mean unit weight and variation, taste 1?5 and trial date; final recipe version, optional typed COGS and vendor invoice price; microbial/chemical Pass/Fail and approved shelf-life days; technology-transfer version/date and three separate Yes/No signatures; label name, ingredients, allergen declaration, weight, date information, lot code and check status; barcode text and SKU/POS checks; store/first-order counts and units/store/day; two-week supply readiness, delivery slot and cold-chain temperature; marketing channels, promotion and start/end dates; weight targets/min/max plus text texture/taste ranges.

Recipe version comes from the editor when available, with manual fallback. Final COGS uses Gate 2's typed value when supplied, otherwise Gate 1's typed COGS, otherwise the ingredient editor. Derived values ignore forged submitted values. Front margin and implied vendor margin remain read-only Pending until the referenced section 8.5 formulas are provided; no formula or tax rate is invented.

Day-45 targets can be copied from Gate 0 section 0.21 or changed. Original launch date comes from Gate 0 section 0.22, and the signed day difference is calculated server-side (positive means delay, negative means earlier); the browser also previews it. Both change-reason fields remain optional per the user's no-mandatory-fields instruction. The form rejects supplied inverted weight ranges and marketing end dates before start dates. Legacy free text is shown for conversion and archived on first typed save. Gate 2 still follows QA ? manager ? director review; fields lock during review.

## Gate 3 typed review and checkpoint sources

All Gate 3 fields remain optional. The launch-date comparison reads planned date from Gate 0 (0.22) and launch date from Gate 2 (2.12); late days are nonnegative, and a delay above seven days without a reason produces a non-blocking save warning. Sales units/store/day are compared to Gate 0 (0.14), with difference and attainment percent (only when target is positive). Typed after-write-off margin and write-off percentage are compared to Gate 0 (0.21), with differences in percentage points. Availability is explicitly the percentage of store-days OUT of stock. Values and calculated sources are recomputed on the server and ignore forged read-only fields.

Launch GO records separate Day 7 and Day 14 check dates, sample results, actual APSD and conditional action plans. Day 14 also records a QA-owned complaint count. Both results feed Gate 3's read-only sample assessments. Historical results and attachments remain available; each new checkpoint has one report/photo slot. Gate 2's quality baseline remains the review reference.

Complaints include integer count, type text and closed Yes/No. CSAT is a nonnegative numeric score plus comment text; no unspecified scale maximum or normalization is assumed. Root cause is demand/price/quality/availability/placement/none with evidence. Lessons have keep/stop/change texts and ingredient/format/vendor/issue tags; the Lessons sidebar page displays all three notes and tags.

Handover status checks final COGS (the Gate 2 derived value or G2-F11), technology transfer (Gate 2 version or G2-F5), label (Gate 2 label name or G2-F7) and marketing plan (Gate 2 plan text or G2-F9). The overall flag is Yes only when all four are present. This is a presence check, not an additional gate-blocking validation or signature verification. Previous free-text data is retained in the legacy archive on typed save. Existing role review sequencing, read-only browsing and gate-specific file slots remain in place.

## Gate and review timing

Successful creation, submission, QA acceptance, approval, escalation, return and final completion now create structured GateTransition records linked to their activity entry. Ordinary field saves, comments and file uploads do not reset timing. Gate tabs show the latest recorded gate entry and elapsed duration. The sidebar separates time in the current gate from time since the current review handoff, and shows the responsible groups. Elapsed displays update each minute in the browser. Completed gates freeze their elapsed time; returns preserve earlier visits and start a new visit when a gate is re-entered.

The transition-history table shows action, actor, timestamp and time since the previous handoff. Dates are displayed in Asia/Ulaanbaatar and durations are wall-clock elapsed time, not working hours or an SLA. Existing structured activity messages are backfilled using their actual stored creation timestamps. Missing historical timestamps are shown as unrecorded rather than using migration time. GateTransition is read-only in Admin. All authenticated project viewers can see timing without additional permissions.

## Timed Launch GO tasks and Day 45 opening

The first recorded entry into Launch GO is stored as `Food.launched_at`, matching the gate-transition timestamp. It is not reset by returns or re-entry. Known historical timestamps are recovered from the transition log; unknown start times are not fabricated. Administrators can enter the actual Launch GO start time for records without a usable historical transition.

Day 7 unlocks at launch +7 elapsed days for Food Science and FF Planning. Day 14 unlocks at +14 days for those roles plus QA, which owns its nonnegative integer complaint count. Launch edit access is also required for each role. Food Science edits the check date and sample result (within limits, conditional, or outside limits); FF Planning edits actual APSD. Target APSD is read-only from Gate 2 section 2.11. Achievement is actual / target × 100: Green at 100% or above, Amber from 80% to below 100%, and Red below 80%. A missing or zero target produces no percentage. The action/owner/deadline text is shown and required only for conditional or outside-limit results; participating editors can update this text and their checkpoint's single quality report/photo upload slot. Other fields remain optional. Each day keeps independent values, actor/timestamp and upload history. Backend field ownership and exact time checks apply to crafted requests; superusers bypass role checks but not early time locks.

Gate 3 editing, submission and decisions remain locked until launch +45 days. Everyone can still browse the gate read-only. On dashboard/detail access, due projects advance automatically from Launch GO to Gate 3, owned for submission by Category Manager (MD), using existing Gate 3 permissions and review ordering. A system activity and transition record the effective Day 45 opening time. `python manage.py open_due_gate3` performs the same idempotent update for external scheduling. No background scheduler is installed; page access processes due openings without one.

Once Gate 3 opens, Launch GO is read-only under the existing past-gate rules. Returning to Launch GO for corrections does not reset launch time or repeatedly auto-open Gate 3; the existing authorized submitter can return to Gate 3 after corrections, with the Day 45 time condition already satisfied. Deadlines are measured from launch, not data-entry dates. Days are elapsed calendar days (24 hours), not working days. Deadlines display in Asia/Ulaanbaatar.
