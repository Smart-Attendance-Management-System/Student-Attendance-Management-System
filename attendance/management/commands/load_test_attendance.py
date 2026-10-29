"""NFR1 load test: many teachers mark attendance at the same moment.

The server must already be running and using the same database as this command.

    python manage.py load_test_attendance --users 100 --url http://127.0.0.1:8000

It creates temporary teachers, classes and students (named "loadtest" or
"LoadTest"), logs every teacher in, then makes all of them submit attendance at
the same moment. It prints how many requests worked and how long they took,
then removes the temporary data again.
"""

import http.cookiejar
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from accounts.models import User
from attendance.models import Attendance
from students.models import AcademicClass, Section, Student

USERNAME_PREFIX = "loadtest"
CLASS_PREFIX = "LoadTest"
PASSWORD = "LoadTest#12345"
FIRST_ROLL_NUMBER = 900000
TIME_LIMIT_SECONDS = 5
RETRIES = 5


def remove_test_data():
    """Delete everything this command created (safe to run when there is none)."""
    Student.objects.filter(section__academic_class__name__startswith=CLASS_PREFIX).delete()
    Section.objects.filter(academic_class__name__startswith=CLASS_PREFIX).delete()
    AcademicClass.objects.filter(name__startswith=CLASS_PREFIX).delete()
    User.objects.filter(username__startswith=USERNAME_PREFIX).delete()


def create_test_data(users, students_per_class):
    """One teacher per simulated user, each with their own class and students."""
    teachers = []
    for index in range(users):
        username = f"{USERNAME_PREFIX}{index:03d}"
        teacher = User.objects.create_user(
            username=username, password=PASSWORD, role=User.Role.TEACHER
        )
        academic_class = AcademicClass.objects.create(
            name=f"{CLASS_PREFIX} {index:03d}", class_teacher=teacher
        )
        section = Section.objects.create(academic_class=academic_class, name="A")
        first_roll = FIRST_ROLL_NUMBER + index * 1000
        Student.objects.bulk_create(
            [
                Student(
                    name=f"{CLASS_PREFIX} student {index:03d}-{n}",
                    student_class=academic_class.name,
                    roll_number=first_roll + n,
                    contact_details=f"{username}-{n}@example.com",
                    section=section,
                )
                for n in range(students_per_class)
            ]
        )
        student_ids = list(Student.objects.filter(section=section).values_list("pk", flat=True))
        teachers.append((username, academic_class.pk, student_ids))
    return teachers


def open_with_retry(opener, request):
    """Open a request. If the server drops the connection, wait and try again.

    The Django development server only queues a few connections at a time, so a
    burst of 100 users can see a dropped connection before the request is read.
    A dropped connection means nothing was processed, so trying again is safe.
    Returns (response, number_of_retries_used).
    """
    for attempt in range(RETRIES + 1):
        try:
            return opener.open(request, timeout=120), attempt
        except urllib.error.HTTPError:
            raise
        except (ConnectionError, urllib.error.URLError):
            if attempt == RETRIES:
                raise
            time.sleep(0.2 * (attempt + 1))


def login(opener, cookie, base_url, username):
    """Log in the way a browser does. Returns True when a session was created."""
    response, _ = open_with_retry(opener, urllib.request.Request(base_url + "/accounts/login/"))
    response.read()
    form = urllib.parse.urlencode(
        {
            "username": username,
            "password": PASSWORD,
            "csrfmiddlewaretoken": cookie("csrftoken"),
            "next": "/",
        }
    ).encode()
    response, _ = open_with_retry(
        opener, urllib.request.Request(base_url + "/accounts/login/", data=form)
    )
    response.read()
    return bool(cookie("sessionid"))


def simulate_teacher(base_url, teacher, date_text, barrier, login_slots, results):
    """Log in, wait for everyone else, then submit a full class at once."""
    username, class_id, student_ids = teacher
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def cookie(name):
        return next((c.value for c in jar if c.name == name), "")

    with login_slots:  # logins are slow (password hashing), so only a few at a time
        try:
            logged_in = login(opener, cookie, base_url, username)
        except Exception:
            logged_in = False

    try:
        barrier.wait(timeout=600)  # everyone submits at the same moment
    except threading.BrokenBarrierError:
        pass

    if not logged_in:
        results.append(("login failed", 0.0, 0))
        return

    payload = json.dumps(
        {
            "classId": class_id,
            "date": date_text,
            "records": [{"studentId": pk, "status": "Present"} for pk in student_ids],
        }
    ).encode()
    request = urllib.request.Request(
        base_url + "/api/attendance",
        data=payload,
        headers={"Content-Type": "application/json", "X-CSRFToken": cookie("csrftoken")},
    )
    started = time.perf_counter()
    retries_used = 0
    try:
        response, retries_used = open_with_retry(opener, request)
        outcome = response.status
    except urllib.error.HTTPError as err:
        outcome = err.code
    except Exception as err:
        outcome = f"error: {err}"
    results.append((outcome, time.perf_counter() - started, retries_used))


class Command(BaseCommand):
    help = "NFR1 load test: simulate many teachers marking attendance at once."

    def add_arguments(self, parser):
        parser.add_argument("--users", type=int, default=100, help="simulated teachers")
        parser.add_argument("--students", type=int, default=30, help="students per class")
        parser.add_argument("--url", default="http://127.0.0.1:8000", help="running server")
        parser.add_argument("--logins-at-once", type=int, default=10, help="parallel logins")
        parser.add_argument("--keep", action="store_true", help="keep the test data")

    def handle(self, *args, **options):
        users, per_class = options["users"], options["students"]
        base_url = options["url"].rstrip("/")

        remove_test_data()
        self.stdout.write(f"Creating {users} teachers with {per_class} students each...")
        teachers = create_test_data(users, per_class)

        results = []
        barrier = threading.Barrier(users)
        login_slots = threading.Semaphore(options["logins_at_once"])
        date_text = date.today().isoformat()
        threads = [
            threading.Thread(
                target=simulate_teacher,
                args=(base_url, teacher, date_text, barrier, login_slots, results),
            )
            for teacher in teachers
        ]
        self.stdout.write(f"Logging in, then submitting {users} classes at the same moment...")
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        saved = Attendance.objects.filter(academic_class__name__startswith=CLASS_PREFIX).count()
        if not options["keep"]:
            remove_test_data()

        succeeded = sorted(seconds for outcome, seconds, _ in results if outcome == 201)
        failures = [outcome for outcome, _, _ in results if outcome != 201]
        retried = sum(1 for _, _, retries in results if retries)
        expected = users * per_class

        self.stdout.write("")
        self.stdout.write(f"Simulated users:   {users}")
        self.stdout.write(f"Successful (201):  {len(succeeded)}")
        self.stdout.write(f"Failed:            {len(failures)} {sorted(set(map(str, failures)))}")
        self.stdout.write(f"Needed a retry:    {retried} (connection dropped while the server was busy)")
        self.stdout.write(f"Rows saved:        {saved} (expected {expected})")
        if succeeded:
            p95 = succeeded[max(int(len(succeeded) * 0.95) - 1, 0)]
            self.stdout.write(f"Average time:      {sum(succeeded) / len(succeeded):.2f} s")
            self.stdout.write(f"95th percentile:   {p95:.2f} s")
            self.stdout.write(f"Slowest:           {succeeded[-1]:.2f} s (limit {TIME_LIMIT_SECONDS} s)")

        if failures or saved != expected:
            raise CommandError("Load test FAILED: some requests did not succeed.")
        self.stdout.write(self.style.SUCCESS("Load test PASSED: no errors."))
        if succeeded[-1] >= TIME_LIMIT_SECONDS:
            self.stdout.write(
                self.style.WARNING(
                    f"Note: the slowest request took longer than {TIME_LIMIT_SECONDS} s. "
                    "This test runs on the Django development server with SQLite on one "
                    "laptop; a real server with MySQL handles this load faster."
                )
            )