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
record totals, status counts, and `averagePercentage`.

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