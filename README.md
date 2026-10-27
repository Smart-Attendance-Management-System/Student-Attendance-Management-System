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

## Academic structure management

Admins can manage academic classes, sections, and subjects under:

- `/classes/`
- `/sections/`
- `/subjects/`

Sections belong to an academic class and cannot be deleted while students
reference them. Student profiles can select a managed section while retaining
support for existing class values.