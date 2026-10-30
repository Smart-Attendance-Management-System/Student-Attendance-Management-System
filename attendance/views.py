import json
import logging

from django.db import connection
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.models import User
from accounts.permissions import IsAdmin, IsStudentParent, IsTeacher

from . import services
from .exports import build_report_response
from .models import Attendance

logger = logging.getLogger("sams.attendance")


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
        logger.warning(
            "Attendance API request failed user_id=%s status=%s",
            getattr(request.user, "pk", None),
            err.status_code,
        )
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
    """GET /api/attendance/daily?classId=1&date=2026-10-23&studentId=2  (REQ4.1/4.4)"""
    try:
        data = services.get_daily_attendance(
            request.user,
            request.query_params.get("classId"),
            request.query_params.get("date"),
            request.query_params.get("studentId"),
        )
    except services.AttendanceError as err:
        return Response({"status": "error", "message": err.message}, status=err.status_code)
    return Response({"status": "success", **data})


@api_view(["GET"])
@permission_classes([IsAdmin])
def attendance_summary_api(request):
    """GET /api/attendance/summary?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD&classId=1&studentId=2"""
    try:
        data = services.get_attendance_summaries(
            request.query_params.get("startDate"),
            request.query_params.get("endDate"),
            request.query_params.get("classId"),
            request.query_params.get("studentId"),
        )
    except services.AttendanceError as err:
        return Response({"status": "error", "message": err.message}, status=err.status_code)
    return Response({"status": "success", **data})


@api_view(["GET"])
@permission_classes([IsAdmin | IsTeacher | IsStudentParent])
def attendance_report_export(request, report, file_format):
    """Download a displayed attendance report as Excel or PDF."""
    if file_format not in ("excel", "pdf"):
        return Response(
            {"status": "error", "message": "Format must be 'excel' or 'pdf'."},
            status=400,
        )

    try:
        if report == "summary":
            if request.user.role != User.Role.ADMIN:
                return Response(
                    {"status": "error", "message": "Only admins can export summaries."},
                    status=403,
                )
            data = services.get_attendance_summaries(
                request.query_params.get("startDate"),
                request.query_params.get("endDate"),
                request.query_params.get("classId"),
                request.query_params.get("studentId"),
            )
            metadata = [
                ("Period", f'{data["startDate"]} to {data["endDate"]}'),
            ]
            if not any(
                item["totalRecords"] for item in data["classes"] + data["grades"]
            ):
                metadata.append(("Note", "No attendance records in this period."))
            tables = [
                (
                    "By class",
                    ["Class", "Total", "Present", "Absent", "Late", "Excused", "Average attendance"],
                    [
                        [
                            item["className"],
                            item["totalRecords"],
                            item["present"],
                            item["absent"],
                            item["late"],
                            item["excused"],
                            f'{item["averagePercentage"]}%',
                        ]
                        for item in data["classes"]
                    ],
                ),
                (
                    "By grade",
                    ["Grade", "Total", "Present", "Absent", "Late", "Excused", "Average attendance"],
                    [
                        [
                            item["gradeName"],
                            item["totalRecords"],
                            item["present"],
                            item["absent"],
                            item["late"],
                            item["excused"],
                            f'{item["averagePercentage"]}%',
                        ]
                        for item in data["grades"]
                    ],
                ),
            ]
            title = "Attendance summaries"
        elif report == "daily":
            if request.user.role not in (User.Role.ADMIN, User.Role.TEACHER):
                return Response(
                    {"status": "error", "message": "You are not allowed to export this report."},
                    status=403,
                )
            data = services.get_daily_attendance(
                request.user,
                request.query_params.get("classId"),
                request.query_params.get("date"),
                request.query_params.get("studentId"),
            )
            metadata = [
                ("Class", data["className"]),
                ("Date", data["date"]),
                ("Marked", "Yes" if data["marked"] else "No"),
                *[(status, count) for status, count in data["counts"].items()],
            ]
            tables = [
                (
                    "Attendance records",
                    ["Roll no.", "Name", "Status", "Remarks"],
                    [
                        [item["rollNumber"], item["name"], item["status"], item["remarks"]]
                        for item in data["records"]
                    ],
                )
            ]
            title = "Daily attendance"
        elif report == "student":
            student_id = request.query_params.get("studentId")
            if not student_id or not student_id.isdigit():
                raise services.AttendanceError(
                    "studentId is required and must be a number.", 400
                )
            data = services.get_student_history(
                request.user,
                student_id,
                request.query_params.get("startDate"),
                request.query_params.get("endDate"),
                request.query_params.get("classId"),
            )
            student = data["student"]
            metadata = [
                ("Student", f'{student["name"]} (roll no. {student["rollNumber"]})'),
                ("Class", student["className"]),
                (
                    "Attendance",
                    f'{data["percentage"]}% ({data["presentDays"]} of {data["totalDays"]} school days)',
                ),
                *[(status, count) for status, count in data["counts"].items()],
            ]
            tables = [
                (
                    "Attendance history",
                    ["Date", "Status", "Remarks"],
                    [
                        [item["date"], item["status"], item["remarks"]]
                        for item in data["records"]
                    ],
                )
            ]
            title = "Student attendance"
        else:
            return Response(
                {"status": "error", "message": "Unknown attendance report."},
                status=404,
            )
    except services.AttendanceError as err:
        return Response({"status": "error", "message": err.message}, status=err.status_code)

    return build_report_response(
        file_format,
        title,
        metadata,
        tables,
        f"attendance-{report}",
    )


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
    """GET /api/attendance/student/<id>?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD&classId=1  (REQ4.2/4.4)"""
    try:
        data = services.get_student_history(
            request.user,
            student_id,
            request.query_params.get("startDate"),
            request.query_params.get("endDate"),
            request.query_params.get("classId"),
        )
    except services.AttendanceError as err:
        return Response({"status": "error", "message": err.message}, status=err.status_code)
    return Response({"status": "success", **data})