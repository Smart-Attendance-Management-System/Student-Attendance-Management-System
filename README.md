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

## Student profile management

Student profiles are managed under `/students/`.
Only users with role `ADMIN` can create, update, or delete profiles.

## Academic structure management

Admins can manage academic classes, sections, and subjects under:

- `/classes/`
- `/sections/`
- `/subjects/`

Sections belong to an academic class and cannot be deleted while students
reference them. Student profiles can select a managed section while retaining
support for existing class values.