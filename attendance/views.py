import json

from django.db import connection
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import IsAdmin, IsStudentParent, IsTeacher

from . import services
from .models import Attendance


def _read_json(request):
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise services.AttendanceError("Request body must be valid JSON.", 400)


def _error(err):
    return JsonResponse({"status": "error", "message": err.message}, status=err.status_code)


@require_POST
def mark_attendance_api(request):
    """POST /api/attendance  {classId, date, records: [{studentId, status, remarks}]}"""
    if not request.user.is_authenticated:
        return JsonResponse({"status": "error", "message": "Login required."}, status=401)
    try:
        data = _read_json(request)
        if not isinstance(data, dict) or "classId" not in data or "date" not in data:
            raise services.AttendanceError("classId and date are required.", 400)
        entries = services.mark_attendance(
            request.user, data["classId"], data["date"], data.get("records", [])
        )
    except services.AttendanceError as err:
        return _error(err)
    return JsonResponse(
        {
            "status": "success",
            "savedCount": len(entries),
            "timestamp": entries[0].created_at.isoformat(),
        },
        status=201,
    )


@require_POST
def edit_attendance_api(request, pk):
    """POST /api/attendance/<id>  {status, remarks}"""
    if not request.user.is_authenticated:
        return JsonResponse({"status": "error", "message": "Login required."}, status=401)
    attendance = get_object_or_404(Attendance, pk=pk)
    try:
        data = _read_json(request)
        if not isinstance(data, dict):
            raise services.AttendanceError("Request body must be a JSON object.", 400)
        attendance = services.edit_attendance(
            request.user, attendance, data.get("status"), data.get("remarks")
        )
    except services.AttendanceError as err:
        return _error(err)
    return JsonResponse(
        {
            "status": "success",
            "newStatus": attendance.status,
            "timestamp": attendance.updated_at.isoformat(),
        }
    )

@api_view(["GET"])
@permission_classes([IsAdmin | IsTeacher])
def daily_attendance_api(request):
    """GET /api/attendance/daily?classId=1&date=2026-10-23  (REQ4.1)"""
    try:
        data = services.get_daily_attendance(
            request.user,
            request.query_params.get("classId"),
            request.query_params.get("date"),
        )
    except services.AttendanceError as err:
        return Response({"status": "error", "message": err.message}, status=err.status_code)
    return Response({"status": "success", **data})

@require_GET
def health_check(request):
    """GET /health/  (NFR3) Simple uptime check an uptime monitor can ping."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return JsonResponse({"status": "error", "database": "down"}, status=503)
    return JsonResponse({"status": "ok", "database": "up"})

@api_view(["GET"])
@permission_classes([IsAdmin | IsTeacher | IsStudentParent])
def student_history_api(request, student_id):
    """GET /api/attendance/student/<id>  (REQ4.2)"""
    try:
        data = services.get_student_history(request.user, student_id)
    except services.AttendanceError as err:
        return Response({"status": "error", "message": err.message}, status=err.status_code)
    return Response({"status": "success", **data})