from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.models import User
from accounts.permissions import IsAdmin, IsStudentParent, IsTeacher
from students.models import AcademicClass, Student

STATUSES = ["Present", "Absent", "Late", "Excused"]
ROLE_PERMISSIONS = {
    User.Role.ADMIN: IsAdmin,
    User.Role.TEACHER: IsTeacher,
    User.Role.STUDENT_PARENT: IsStudentParent,
}


def role_required(*roles):
    """Login required; a user with the wrong role is sent to the home page."""

    def decorator(view):
        @login_required(login_url="login")
        def wrapped(request, *args, **kwargs):
            if not any(
                ROLE_PERMISSIONS[role]().has_permission(request, view)
                for role in roles
            ):
                return redirect("pages:home")
            return view(request, *args, **kwargs)

        wrapped.__name__ = view.__name__
        return wrapped

    return decorator


@login_required(login_url="login")
def home(request):
    if request.user.role == User.Role.TEACHER:
        return redirect("pages:mark_attendance")
    if request.user.role == User.Role.ADMIN:
        return redirect("pages:student_list")
    return render(request, "pages/home.html")


@role_required(User.Role.ADMIN, User.Role.TEACHER)
def student_list(request):
    students = Student.objects.select_related("section").all()
    return render(request, "pages/student_list.html", {"students": students})


@role_required(User.Role.TEACHER)
def mark_attendance(request):
    classes = AcademicClass.objects.all()
    class_id = request.GET.get("class", "")
    selected = None
    students = []
    if class_id.isdigit():
        selected = classes.filter(pk=int(class_id)).first()
        if selected:
            students = Student.objects.filter(section__academic_class=selected)
    return render(
        request,
        "pages/mark_attendance.html",
        {
            "classes": classes,
            "selected": selected,
            "students": students,
            "statuses": STATUSES,
            "today": timezone.localdate(),
        },
    )
