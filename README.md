# Student-Attendance-Management-System

## Local development

1. Create and activate a virtual environment.
2. Install dependencies from [requirements.txt](./requirements.txt).
3. Configure the environment in the same PowerShell window (repeat this step
   whenever you open a new window):

```powershell
$env:USE_SQLITE="1"
$env:DJANGO_DEBUG="1"
$env:DJANGO_SECRET_KEY = python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
$env:DJANGO_ALLOWED_HOSTS="localhost,127.0.0.1,testserver"
```

4. Run migrations and start the server:

```powershell
python manage.py migrate
python manage.py runserver
```

## Application structure and maintainability

The project follows Django's MVC-style boundaries:

- `models.py` files define database entities, relationships, indexes, and
  constraints.
- `views.py` files handle authentication, HTTP input/output, redirects, and
  API response formatting.
- Reusable business rules belong in app services, especially
  `attendance/services.py` and `notifications/services.py`.
- URL modules only map routes to views; they do not contain business logic.
- Management commands are reserved for explicit operational or maintenance
  tasks, such as the database backup command described below.

The durable attendance edit history remains `notifications.AuditLog`. It
records who changed an attendance entry, what changed, and when. Application
logs are separate diagnostic records and must not be used as a replacement for
that audit trail.

## Application logging

Logging is configured centrally in `sams_project/settings.py`. The `sams`
logger writes timestamped records with level and logger name to the console at
`INFO` by default. Change the diagnostic threshold with
`SAMS_LOG_LEVEL=WARNING` (or another standard Python level).

For deployments that need a rotating file, set `SAMS_LOG_FILE` to a
directory/file owned by the service account and outside the repository:

```powershell
$env:SAMS_LOG_LEVEL="INFO"
$env:SAMS_LOG_FILE="C:\var\log\sams\application.log"
python manage.py runserver
```

Attendance submissions, rejected submissions, attendance edits, student
profile actions, class/section/subject catalog actions, imports, and backup or
restore operations are logged. Messages use user and record identifiers rather
than student contact details, passwords, session tokens, or request bodies.
Configure log rotation and access permissions at the deployment boundary.

## Database backup and restore

The supported backends are SQLite for local development/testing and MySQL for
deployment. Backups must be stored outside the repository, such as
`C:\var\backups\sams` or `/var/backups/sams`; the repository ignores common
backup and log extensions.

### SQLite

Prerequisites: the configured SQLite database must be accessible to the
service account. Create a backup without replacing an existing file:

```powershell
$env:USE_SQLITE="1"
python manage.py backup_database backup --output C:\var\backups\sams\attendance-2026-10-30.sqlite3
```

Restore only after selecting the backup and confirming the live database is
the intended target:

```powershell
$env:USE_SQLITE="1"
python manage.py backup_database restore `
  --input C:\var\backups\sams\attendance-2026-10-30.sqlite3 `
  --confirm-restore
```

The command refuses to overwrite an existing backup unless `--force` is
provided. Restore always requires `--confirm-restore`; it does not happen
automatically. After a restore, verify the result with:

```powershell
$env:USE_SQLITE="1"
python manage.py check
python manage.py showmigrations
python manage.py shell -c "from attendance.models import Attendance; print(Attendance.objects.count())"
```

SQLite backups use SQLite's online backup API rather than copying a live file
blindly.

### MySQL

Prerequisites: `mysqldump` and `mysql` must be installed and available on
`PATH`. Configure `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and
`DB_PORT` as deployment environment variables; never place credentials in a
backup command or committed file:

```powershell
python manage.py backup_database backup --output C:\var\backups\sams\attendance-2026-10-30.sql
python manage.py backup_database restore `
  --input C:\var\backups\sams\attendance-2026-10-30.sql `
  --confirm-restore
```

The MySQL path uses `mysqldump --single-transaction --routines --triggers`
and streams restore input to `mysql`. It does not support replacing a live
database implicitly; the explicit confirmation flag is required. Verify the
restored data with `python manage.py check` and a read-only Django shell query
as shown above. Test restoration against a disposable database first when
operationally possible.

## Login API

`POST /api/auth/login` accepts a JSON body with `username` and `password`.
A successful login returns the user's role and the Django session key as
`session_token`; invalid credentials return HTTP 401.

```json
{
  "username": "teacher1",
  "password": "your-password"
}
```

Run the login integration tests with:

```powershell
$env:USE_SQLITE="1"
python manage.py test accounts.tests.LoginAPITests
```

## Session inactivity timeout

Authenticated sessions expire after 15 minutes without a request. Each request
refreshes the session expiry, so active sessions remain valid.

Run the session timeout tests with:

```powershell
$env:USE_SQLITE="1"
python manage.py test pages.tests.SessionInactivityTests
```

## Role-based access

Users have one of three roles: Admin, Teacher, or Student/Parent. Reusable
Django REST Framework permission classes are available from
`accounts.permissions`: `IsAdmin`, `IsTeacher`, and `IsStudentParent`.
Admin-only student and academic-structure management and role-specific pages
enforce these role checks.

Run the permission and Admin-endpoint access tests with:

```powershell
$env:USE_SQLITE="1"
python manage.py test accounts.tests.RolePermissionTests students.tests.StudentProfileTests.test_teacher_receives_403_from_admin_only_endpoint
```

## Student data protection (TC-10)

New passwords are stored using Django's BCrypt-SHA256 hasher. Existing PBKDF2
passwords remain verifiable and are upgraded to bcrypt after a successful
login. Student history access reuses `attendance.services.can_view_student`,
so parents can only access children linked to their account; the integration
test verifies a request for another parent's student returns HTTP 403.

## Deployment configuration

[.env.example](./.env.example) lists the settings used by the project. It is a
reference only; Django does not load it automatically. Set deployment values
in the service environment or a secret manager, and never commit a populated
`.env` file.

Set `DJANGO_DEBUG=0`, generate a unique `DJANGO_SECRET_KEY` with Django's
`get_random_secret_key()`, and set `DJANGO_ALLOWED_HOSTS` to a comma-separated
list of exact deployment hostnames. A missing key or host list, or a wildcard
host, stops startup. For MySQL, set `DB_NAME`, `DB_USER`, and `DB_PASSWORD`;
configure `SAMS_SMTP_HOST` and any required SMTP credentials because the
console email backend is development-only.

With `DJANGO_DEBUG=0`, HTTPS redirects, secure session/CSRF cookies, and
one-year HSTS are enabled by default. Terminate HTTPS at the application
server or a trusted reverse proxy. Set `TRUST_X_FORWARDED_PROTO=1` only when
that proxy overwrites `X-Forwarded-Proto`. Set
`SECURE_HSTS_INCLUDE_SUBDOMAINS=1` and `SECURE_HSTS_PRELOAD=1` only after
confirming every subdomain uses HTTPS and you intend to opt into browser
preloading.

Run the deployment check with deployment-equivalent hostnames and SMTP
settings. This placeholder setup is for validation only:

```powershell
$env:USE_SQLITE="1"
$env:DJANGO_DEBUG="0"
$env:DJANGO_SECRET_KEY = python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
$env:DJANGO_ALLOWED_HOSTS="deployment.example.invalid"
$env:SAMS_SMTP_HOST="smtp.example.invalid"
$env:SECURE_HSTS_INCLUDE_SUBDOMAINS="1"
$env:SECURE_HSTS_PRELOAD="1"
python manage.py check --deploy
```

## User account management

Admins can manage accounts at `/accounts/users/`: create accounts with a
username, email, role, and password; edit account details or role; and delete
accounts. Passwords are validated using the configured Django password
validators. Non-admin users receive HTTP 403.

Run the TC-02 account management tests with:

```powershell
$env:USE_SQLITE="1"
python manage.py test accounts.tests.UserAccountManagementTests
```

Role changes take effect on the user's next request, including in an existing
login session. Verify this with:

```powershell
$env:USE_SQLITE="1"
python manage.py test accounts.tests.UserAccountManagementTests.test_role_change_updates_permissions_for_existing_session
```

## Student profile management

Student profiles are managed under `/students/`.
Only users with role `ADMIN` can create, update, or delete profiles.
Admins can bulk import students from `/students/import/`.
Imports accept UTF-8 `.csv` and `.xlsx` files up to 5 MB.
Required columns are `name`, `class`, `roll_number`, and `contact_details`;
`section` is optional and must belong to the specified class.
Each data row is validated independently. Invalid rows are skipped and reported
with their physical file row number (the header is row 1), while valid rows
from the same file are saved. Structural file errors, such as missing required
columns or malformed Excel files, reject the upload.

## Attendance summaries

Admins can review attendance totals and average percentages by class section
and academic grade at `/pages/attendance-summary/`. Select an inclusive start
and end date. Percentages count both Present and Late records as attended;
unmarked days are not included. Classes and grades with no attendance in the
selected period are shown with zero totals.

The admin-only `GET /api/attendance/summary` endpoint accepts `startDate` and
`endDate` in `YYYY-MM-DD` format and returns `classes` and `grades` arrays with
record totals, status counts, and `averagePercentage`. Reports support these
optional filters, which can be combined with AND semantics:

- `classId`: numeric academic class identifier.
- `studentId`: numeric student identifier.
- `startDate` and `endDate`: inclusive date range in `YYYY-MM-DD` format.

Examples:

```text
GET /api/attendance/summary?startDate=2026-10-01&endDate=2026-10-31&classId=3&studentId=12
GET /api/attendance/student/12?startDate=2026-10-01&endDate=2026-10-31&classId=3
GET /api/attendance/daily?classId=3&date=2026-10-15&studentId=12
```

The extended report endpoints are `GET /api/attendance/summary` (REQ4.3),
`GET /api/attendance/student/<studentId>` (REQ4.2), and
`GET /api/attendance/daily` (REQ4.1). Their existing response formats and
authorization rules are unchanged when filters are omitted. The summary remains
admin-only; daily reports remain available to admins and assigned class
teachers; student history remains restricted to admins, assigned class
teachers, and the student's parent. Missing or malformed dates and identifiers
return a validation error, while valid filters with no matching attendance
return zero totals and percentages.

Daily attendance, student history, and attendance summary reports can be
downloaded as PDF or Excel from their respective pages. The export endpoints
use the same date, class, and student selections as the on-screen reports and
preserve empty reports with their column headers and a no-records message.

## Academic structure management

Admins can manage academic classes, sections, and subjects under:

- `/classes/`
- `/sections/`
- `/subjects/`

Sections belong to an academic class and cannot be deleted while students
reference them. Student profiles can select a managed section while retaining
support for existing class values.
## Parent absence emails (REQ5.1)

When a teacher marks a student **Absent** (on submission or by editing a
record to Absent), SAMS emails the parent account linked to the student
(`Student.parent.email`) and saves a `notifications.Notification` record.
Present, Late, and Excused never send an email. If the student has no parent
email, the record is still saved with status `skipped`. A failed send never
blocks saving attendance; the record is marked `failed`.

Local runs print emails to the console. To use a real mail server, set these
in the deployment environment (never commit credentials):

- `SAMS_SMTP_HOST`, `SAMS_SMTP_PORT` (default 587)
- `SAMS_SMTP_USER`, `SAMS_SMTP_PASSWORD`
- `SAMS_SMTP_USE_TLS` (default `1`), `SAMS_SMTP_TIMEOUT` (seconds, default 10)
- `DEFAULT_FROM_EMAIL`

Run the TC-08 tests with:

```powershell
$env:USE_SQLITE="1"
python manage.py test notifications.tests.AbsenceNotificationIntegrationTests
```

### Retrying failed notifications (REQ5.4)

Each notification is tried up to 3 times. Every attempt is stored as a
`NotificationAttempt` (attempt number, success, error) and each failure is
written to the `sams.notifications` log with record ids only. While retries
remain the status stays `pending`; after the third failure it becomes
`failed`. Both are visible in Django admin under Notifications. An optional
pause between attempts can be set with `SAMS_NOTIFICATION_RETRY_DELAY`
(seconds, default 0) in settings.

```powershell
$env:USE_SQLITE="1"
python manage.py test notifications.tests.NotificationRetryTests
```

## Audit log search (REQ5.3)

Admins can search attendance edits at `/audit-log/` (linked as **Audit log**
in the admin navigation). Filters are optional and combine with AND:

- **Class** (`classId`): the class of the edited record.
- **Attendance date** (`date`, `YYYY-MM-DD`): the date of the attendance
  record that was changed.
- **Edited by** (`userId`): the teacher or admin who made the change.

The same search is available as JSON from the admin-only
`GET /api/audit-log?classId=3&date=2026-10-27&userId=5` (up to 500 newest
entries; `count` and `truncated` report the full total). Teachers and
Student/Parent users receive HTTP 403 from both. Malformed filter values
return HTTP 400 from the API and an error message on the page.

```powershell
$env:USE_SQLITE="1"
python manage.py test notifications.tests.AuditLogViewTests
```

## Usability and browser support (NFR4 / TC-12)

All role pages use the shared Bootstrap layout in `pages/base.html`: a
viewport meta tag, a navigation bar that collapses behind a menu button below
992px, and tables that scroll inside their own container instead of the page.
On the Mark attendance page every student starts as Present, so a teacher
taps once only for each Absent, Late, or Excused student and once to submit.
On phones the four status buttons are shown as a 2x2 grid of 44px touch
targets, and the Submit bar stays visible at the bottom while scrolling.

Supported browsers: current Chrome, Firefox, Safari (macOS and iPadOS/iOS),
and Edge. The manual device and browser checklist is recorded on issue #18.

```powershell
$env:USE_SQLITE="1"
python manage.py test pages.tests.UsabilityCompatibilityTests
```
