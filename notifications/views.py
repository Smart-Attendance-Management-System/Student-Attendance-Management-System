from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import render
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.models import User
from accounts.permissions import IsAdmin
from students.models import AcademicClass

from .services import (
    AuditLogFilterError,
    audit_entry_to_dict,
    describe_audit_entries,
    search_audit_log,
)

PAGE_SIZE = 50
API_MAX_RESULTS = 500


@login_required(login_url="login")
def audit_log_page(request):
    """REQ5.3: admin screen to search the attendance audit log."""
    if request.user.role != User.Role.ADMIN:
        raise PermissionDenied("Only admins can view the audit log.")

    filters = {
        "class_id": request.GET.get("classId", ""),
        "date": request.GET.get("date", ""),
        "user_id": request.GET.get("userId", ""),
    }
    error = ""
    page = None
    try:
        entries = search_audit_log(**filters)
        page = Paginator(entries, PAGE_SIZE).get_page(request.GET.get("page"))
        page.object_list = describe_audit_entries(page.object_list)
    except AuditLogFilterError as exc:
        error = str(exc)

    query = request.GET.copy()
    query.pop("page", None)
    return render(
        request,
        "notifications/audit_log.html",
        {
            "page": page,
            "error": error,
            "filters": filters,
            "query": query.urlencode(),
            "classes": AcademicClass.objects.all(),
            "editors": User.objects.filter(
                role__in=[User.Role.ADMIN, User.Role.TEACHER]
            ).order_by("username"),
        },
    )


@api_view(["GET"])
@permission_classes([IsAdmin])
def audit_log_api(request):
    """GET /api/audit-log?classId=1&date=2026-10-27&userId=2  (REQ5.3, admin only)"""
    try:
        entries = search_audit_log(
            request.query_params.get("classId"),
            request.query_params.get("date"),
            request.query_params.get("userId"),
        )
    except AuditLogFilterError as exc:
        return Response({"status": "error", "message": str(exc)}, status=400)
    total = entries.count()
    results = describe_audit_entries(entries[:API_MAX_RESULTS])
    return Response(
        {
            "status": "success",
            "count": total,
            "truncated": total > API_MAX_RESULTS,
            "results": [audit_entry_to_dict(e) for e in results],
        }
    )
