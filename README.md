# Student-Attendance-Management-System

## Local development

1. Create and activate a virtual environment.
2. Install dependencies from [requirements.txt](./requirements.txt).
3. Use SQLite for local runs:

```powershell
$env:USE_SQLITE="1"
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

For deployment, terminate HTTPS at the application server or a trusted
reverse proxy and configure:

- `DJANGO_DEBUG=0`
- `DJANGO_SECRET_KEY` to a unique secret held outside the repository
- `DJANGO_ALLOWED_HOSTS` to a comma-separated list of deployment hostnames
- `TRUST_X_FORWARDED_PROTO=1` only when a trusted proxy sets/replaces the
  `X-Forwarded-Proto` header to `https`

With `DJANGO_DEBUG=0`, HTTPS redirects, secure session/CSRF cookies, and
one-year HSTS are enabled by default. Local development keeps these settings
off unless explicitly enabled.

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