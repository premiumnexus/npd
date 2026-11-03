# CU Food development MVP

A working Django application for taking CU food ideas through development and calculating the finished cost per unit in MNT.

## Run the local demo (PowerShell)

```powershell
python -m pip install -r requirements-local.txt
.\start-demo.ps1
```

On the first run, choose a password for the `demo` administrator. Open http://127.0.0.1:8000 and sign in. Subsequent runs preserve your database and password. Demo suppliers, recipes and prices are illustrative. The demo administrator can exercise every role; real users should receive only their assigned group in `/admin/`.

## Workflow

| Stage | Responsible Django group | Next action |
| --- | --- | --- |
| Concept | Product | Define brief, owner, target date and batch |
| Recipe development | R&D | Add ingredients and batch quantities |
| Supplier sourcing | Procurement | Register suppliers and ingredient prices |
| Quality review | Quality | Record review decision |
| Cost approval | Finance | Check finished cost and positive gross margin |
| Ready for launch | Approved record | Read-only recipe and costing |

Each stage accepts a decision note. Returning work requires a reason. Only the current stage's group or a superuser can approve or return work. Owners and the current stage group can edit an unapproved development. All authenticated team members can read records and post notes. The activity log records application edits and handoffs; Django administrators retain administrative access. This is a shared internal workspace, not a multi-tenant system.

The MVP includes development search and stage filters, supplier and ingredient creation, recipe line addition/removal, editable batch and cost inputs, approval history, CSV cost export and authenticated read APIs. Manage users, groups and catalog corrections in Django admin. Quality review is a recorded human decision; attachments, structured laboratory testing and notifications are outside this MVP.

## Cost calculation

```text
Effective finished units = batch units × yield percent / 100
Ingredient batch cost = sum(batch quantity × captured ingredient price)
Cost per finished unit = ingredient batch cost / effective finished units
                       + packaging per unit + labor per unit + overhead per unit
Gross margin % = (selling price − cost per unit) / selling price × 100
```

Enter quantities in the ingredient's purchase unit (kg, L or each); convert grams to kg before entry. Yield applies to batch output. Prices are copied to recipe lines when added, so catalog changes do not silently change existing costings. Re-add a line to capture a new price. Decimal arithmetic is used; display and export totals round to two decimal places. Tax, freight and distribution are excluded unless included in overhead. Final approval requires at least one ingredient and a selling price above cost.

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

Use Django admin to create the Product, R&D, Procurement, Quality and Finance groups and assign users, or run `python manage.py seed_demo` to create the groups and sample data. Use an independent CU Food database; do not point the app at Potential Point's database.

For deployment, set `DEBUG=0`, a random `SECRET_KEY`, explicit `ALLOWED_HOSTS`, and MySQL credentials; run migrations and `collectstatic`, serve `config.wsgi:application` with your WSGI server and serve static assets through your web server. HTTPS is required for production session cookies. Production deployment is not configured or verified here.

## Verification and API

```powershell
$env:CUFOOD_SQLITE = '1'
$env:DEBUG = '1'
python manage.py check
python manage.py test
```

Eight tests cover yield-adjusted costing, ingredient price snapshots, role-gated handoffs, approved record locking, rendered screens, API/CSV access, anonymous denial, invalid quantities and final approval margin checks. Tests use SQLite; MySQL and browser rendering have not been verified.

Authenticated read endpoints:

- `GET /api/foods/`
- `GET /api/foods/<id>/cost/`

Writes use CSRF-protected server-rendered forms. No external service credentials or Potential Point data are required.
