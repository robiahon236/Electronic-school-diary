import csv
import logging
from functools import wraps

import requests
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (AttendanceFilterForm, AttendanceForm, GradeFilterForm,
                    GradeForm, HomeworkFilterForm, HomeworkForm, ScheduleForm)
from .integrations.schedule_api import ScheduleImportError, import_schedule_data
from .models import (Attendance, ClassRoom, Grade, Homework, ScheduleItem,
                     StudentProfile, User)

logger = logging.getLogger(__name__)

GRADE_SORT = {'date', '-date', 'value', '-value',
              'student__last_name', 'subject__name'}
HOMEWORK_SORT = {'due_date', '-due_date', 'subject__name', 'class_room__name'}
ATTENDANCE_SORT = {'date', '-date', 'student__last_name',
                   'subject__name', 'status'}


def role_required(*roles):
    """Декоратор проверки роли: при несовпадении — ошибка 403."""
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(request, *args, **kwargs):
            if request.user.role not in roles:
                raise PermissionDenied('Недостаточно прав')
            return view(request, *args, **kwargs)
        return wrapper
    return decorator


def _user_class_ids(user):
    """ID классов, доступных пользователю по роли.

    None — ограничений нет (учитель/админ), [] — доступ запрещён
    (ученик без профиля), список — только указанные классы.
    """
    if user.role == 'student':
        profile = getattr(user, 'student_profile', None)
        return [profile.class_room_id] if profile and profile.class_room else []
    if user.role == 'parent':
        return list(StudentProfile.objects.filter(
            user__parent_links__parent=user
        ).exclude(class_room__isnull=True).values_list('class_room_id', flat=True))
    return None


def home(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return redirect('login')


@login_required
def dashboard(request):
    user = request.user
    ctx = {}
    if user.role == 'student':
        ctx['grades'] = Grade.objects.filter(student=user).select_related(
            'subject').order_by('-date')[:5]
        ctx['attendance'] = Attendance.objects.filter(student=user).select_related(
            'subject').order_by('-date')[:5]
        profile = getattr(user, 'student_profile', None)
        if profile and profile.class_room:
            ctx['homework'] = Homework.objects.filter(
                class_room=profile.class_room).order_by('due_date')[:5]
            ctx['schedule'] = ScheduleItem.objects.filter(
                class_room=profile.class_room).order_by('day', 'lesson_number')
    elif user.role == 'parent':
        child_ids = user.children_links.values_list('student_id', flat=True)
        ctx['children'] = User.objects.filter(id__in=child_ids)
        ctx['grades'] = Grade.objects.filter(
            student_id__in=child_ids).select_related(
            'student', 'subject').order_by('-date')[:10]
        ctx['attendance'] = Attendance.objects.filter(
            student_id__in=child_ids).select_related(
            'student', 'subject').order_by('-date')[:10]
    elif user.role in ('teacher', 'admin'):
        ctx['recent_grades'] = Grade.objects.select_related(
            'student', 'subject').order_by('-date')[:10]
        ctx['students_count'] = User.objects.filter(role='student').count()
    return render(request, 'diary/dashboard.html', ctx)


# ------------------------------ ОЦЕНКИ ------------------------------

@login_required
def grades_list(request):
    qs = Grade.objects.select_related('student', 'subject')
    if request.user.role == 'student':
        qs = qs.filter(student=request.user)
    elif request.user.role == 'parent':
        qs = qs.filter(student__parent_links__parent=request.user)

    form = GradeFilterForm(request.GET or None)
    if form.is_valid():
        cd = form.cleaned_data
        if cd['search']:
            qs = qs.filter(student__last_name__icontains=cd['search'])
        if cd['student']:
            qs = qs.filter(student=cd['student'])
        if cd['subject']:
            qs = qs.filter(subject=cd['subject'])
        if cd['date_from']:
            qs = qs.filter(date__gte=cd['date_from'])
        if cd['date_to']:
            qs = qs.filter(date__lte=cd['date_to'])

    sort = request.GET.get('sort', '-date')
    if sort not in GRADE_SORT:
        sort = '-date'
    qs = qs.order_by(sort)
    return render(request, 'diary/grades.html',
                  {'grades': qs, 'form': form, 'sort': sort})


@role_required('teacher', 'admin')
def add_grade(request):
    form = GradeForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Оценка выставлена')
        return redirect('grades')
    return render(request, 'diary/add_grade.html', {'form': form, 'edit': False})


@role_required('teacher', 'admin')
def grade_edit(request, pk):
    grade = get_object_or_404(Grade, pk=pk)
    form = GradeForm(request.POST or None, instance=grade)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Оценка изменена')
        return redirect('grades')
    return render(request, 'diary/add_grade.html', {'form': form, 'edit': True})


@role_required('teacher', 'admin')
@require_POST
def grade_delete(request, pk):
    get_object_or_404(Grade, pk=pk).delete()
    messages.success(request, 'Оценка удалена')
    return redirect('grades')


# --------------------------- ДОМАШНИЕ ЗАДАНИЯ ---------------------------

@login_required
def homework_list(request):
    qs = Homework.objects.select_related('subject', 'class_room')
    class_ids = _user_class_ids(request.user)
    if class_ids is not None:
        qs = qs.filter(class_room_id__in=class_ids)

    form = HomeworkFilterForm(request.GET or None)
    if form.is_valid():
        cd = form.cleaned_data
        if cd['search']:
            qs = qs.filter(
                Q(subject__name__icontains=cd['search']) |
                Q(description__icontains=cd['search']))
        if cd['class_room']:
            qs = qs.filter(class_room=cd['class_room'])
        if cd['subject']:
            qs = qs.filter(subject=cd['subject'])
        if cd['due_from']:
            qs = qs.filter(due_date__gte=cd['due_from'])
        if cd['due_to']:
            qs = qs.filter(due_date__lte=cd['due_to'])

    sort = request.GET.get('sort', 'due_date')
    if sort not in HOMEWORK_SORT:
        sort = 'due_date'
    qs = qs.order_by(sort)
    return render(request, 'diary/homework.html',
                  {'homework': qs, 'form': form, 'sort': sort})


@role_required('teacher', 'admin')
def add_homework(request):
    form = HomeworkForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Задание добавлено')
        return redirect('homework')
    return render(request, 'diary/add_homework.html', {'form': form, 'edit': False})


@role_required('teacher', 'admin')
def homework_edit(request, pk):
    hw = get_object_or_404(Homework, pk=pk)
    form = HomeworkForm(request.POST or None, instance=hw)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Задание изменено')
        return redirect('homework')
    return render(request, 'diary/add_homework.html', {'form': form, 'edit': True})


@role_required('teacher', 'admin')
@require_POST
def homework_delete(request, pk):
    get_object_or_404(Homework, pk=pk).delete()
    messages.success(request, 'Задание удалено')
    return redirect('homework')


# ------------------------------ ПОСЕЩАЕМОСТЬ ------------------------------

@login_required
def attendance_list(request):
    qs = Attendance.objects.select_related('student', 'subject')
    if request.user.role == 'student':
        qs = qs.filter(student=request.user)
    elif request.user.role == 'parent':
        qs = qs.filter(student__parent_links__parent=request.user)

    form = AttendanceFilterForm(request.GET or None)
    if form.is_valid():
        cd = form.cleaned_data
        if cd['search']:
            qs = qs.filter(student__last_name__icontains=cd['search'])
        if cd['student']:
            qs = qs.filter(student=cd['student'])
        if cd['subject']:
            qs = qs.filter(subject=cd['subject'])
        if cd['status']:
            qs = qs.filter(status=cd['status'])
        if cd['date_from']:
            qs = qs.filter(date__gte=cd['date_from'])
        if cd['date_to']:
            qs = qs.filter(date__lte=cd['date_to'])

    sort = request.GET.get('sort', '-date')
    if sort not in ATTENDANCE_SORT:
        sort = '-date'
    qs = qs.order_by(sort)
    return render(request, 'diary/attendance.html',
                  {'attendance': qs, 'form': form, 'sort': sort})


@role_required('teacher', 'admin')
def attendance_add(request):
    form = AttendanceForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        cd = form.cleaned_data
        # Повторная отметка обновляет существующую запись, а не создаёт дубль
        obj, created = Attendance.objects.update_or_create(
            student=cd['student'], subject=cd['subject'], date=cd['date'],
            defaults={'status': cd['status'], 'comment': cd['comment']},
        )
        if created:
            messages.success(request, 'Посещаемость отмечена')
        else:
            messages.warning(request, 'Существующая запись обновлена')
        return redirect('attendance')
    return render(request, 'diary/add_attendance.html',
                  {'form': form, 'edit': False})


@role_required('teacher', 'admin')
def attendance_edit(request, pk):
    att = get_object_or_404(Attendance, pk=pk)
    form = AttendanceForm(request.POST or None, instance=att)
    if request.method == 'POST' and form.is_valid():
        cd = form.cleaned_data
        replaced = False
        with transaction.atomic():
            if (cd['student'].pk, cd['subject'].pk,
                    cd['date'].isoformat()) != (att.student_id, att.subject_id,
                                                att.date.isoformat()):
                att.delete()
                replaced = True
            Attendance.objects.update_or_create(
                student=cd['student'], subject=cd['subject'], date=cd['date'],
                defaults={'status': cd['status'], 'comment': cd['comment']},
            )
        if replaced:
            messages.warning(request, 'Существующая запись на эту дату заменена')
        else:
            messages.success(request, 'Запись посещаемости изменена')
        return redirect('attendance')
    return render(request, 'diary/add_attendance.html', {'form': form, 'edit': True})


@role_required('teacher', 'admin')
@require_POST
def attendance_delete(request, pk):
    get_object_or_404(Attendance, pk=pk).delete()
    messages.success(request, 'Запись посещаемости удалена')
    return redirect('attendance')


# ------------------------------ РАСПИСАНИЕ ------------------------------

@login_required
def schedule_view(request):
    items = ScheduleItem.objects.select_related('class_room', 'subject')
    class_ids = _user_class_ids(request.user)
    if class_ids is not None:
        items = items.filter(class_room_id__in=class_ids)

    day = request.GET.get('day', '')
    valid_days = [code for code, _ in ScheduleItem.WEEKDAYS]
    if day in valid_days:
        items = items.filter(day=day)

    items = items.order_by('day', 'lesson_number')
    return render(request, 'diary/schedule.html',
                  {'items': items, 'days': ScheduleItem.WEEKDAYS, 'day': day})


@role_required('teacher', 'admin')
def schedule_add(request):
    form = ScheduleForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Урок добавлен в расписание')
        return redirect('schedule')
    return render(request, 'diary/add_schedule.html', {'form': form, 'edit': False})


@role_required('teacher', 'admin')
def schedule_edit(request, pk):
    item = get_object_or_404(ScheduleItem, pk=pk)
    form = ScheduleForm(request.POST or None, instance=item)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Расписание изменено')
        return redirect('schedule')
    return render(request, 'diary/add_schedule.html', {'form': form, 'edit': True})


@role_required('teacher', 'admin')
@require_POST
def schedule_delete(request, pk):
    get_object_or_404(ScheduleItem, pk=pk).delete()
    messages.success(request, 'Урок удалён из расписания')
    return redirect('schedule')


# --------------------------- ИНТЕГРАЦИЯ (HTTP) ---------------------------

@role_required('teacher', 'admin')
@require_POST
def import_schedule(request):
    try:
        count, source = import_schedule_data()
        msg = f'Загружено записей: {count}'
        if source == 'fallback':
            msg += ' (использован резервный файл)'
        messages.success(request, msg)
    except requests.RequestException:
        logger.error('HTTP-ошибка импорта расписания', exc_info=True)
        messages.error(request, 'Не удалось получить расписание (сеть или сервер)')
    except ScheduleImportError as exc:
        logger.error('Ошибка данных расписания: %s', exc)
        messages.error(request, f'Ошибка данных: {exc}')
    return redirect('schedule')


@role_required('teacher', 'admin')
@require_POST
def import_schedule_ajax(request):
    try:
        count, source = import_schedule_data()
    except requests.RequestException:
        logger.error('HTTP-ошибка импорта расписания (AJAX)', exc_info=True)
        return JsonResponse(
            {'status': 'error', 'message': 'Не удалось получить расписание'},
            status=502)
    except ScheduleImportError as exc:
        logger.error('Ошибка данных расписания: %s', exc)
        return JsonResponse(
            {'status': 'error', 'message': f'Ошибка данных: {exc}'}, status=400)
    return JsonResponse({'status': 'ok', 'count': count, 'source': source})


# -------------------------------- ОТЧЁТЫ --------------------------------

@role_required('teacher', 'admin')
def report_grades(request):
    qs = Grade.objects.select_related(
        'student', 'subject', 'student__student_profile__class_room')
    class_id = request.GET.get('class')
    if class_id:
        qs = qs.filter(student__student_profile__class_room_id=class_id)

    rows = {}
    for g in qs:
        profile = getattr(g.student, 'student_profile', None)
        cls = profile.class_room.name if profile and profile.class_room else '—'
        name = g.student.get_full_name() or g.student.username
        key = (name, cls, g.subject.name)
        agg = rows.setdefault(key, {'total': 0, 'cnt': 0})
        agg['total'] += g.value
        agg['cnt'] += 1

    report = [
        {'student': k[0], 'class_room': k[1], 'subject': k[2],
         'avg': round(v['total'] / v['cnt'], 2), 'cnt': v['cnt']}
        for k, v in sorted(rows.items())
    ]
    return render(request, 'diary/report_grades.html',
                  {'report': report, 'classes': ClassRoom.objects.all(),
                   'class_id': class_id})


@role_required('teacher', 'admin')
def report_attendance(request):
    # Сводка: одна строка на ученика, счётчики по статусам
    stats = {}
    for a in Attendance.objects.select_related('student').order_by(
            'student__last_name'):
        name = a.student.get_full_name() or a.student.username
        row = stats.setdefault(name, {'present': 0, 'absent': 0,
                                      'late': 0, 'sick': 0, 'total': 0})
        row[a.status] += 1
        row['total'] += 1
    report = [{'student': name, **row} for name, row in stats.items()]
    return render(request, 'diary/report_attendance.html', {'report': report})


@login_required
def report_homework(request):
    qs = Homework.objects.select_related('subject', 'class_room').filter(
        due_date__gte=timezone.now().date()).order_by('due_date')
    class_ids = _user_class_ids(request.user)
    if class_ids is not None:
        qs = qs.filter(class_room_id__in=class_ids)
    return render(request, 'diary/report_homework.html', {'homework': qs})


@role_required('teacher', 'admin')
def export_report(request, kind):
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="{kind}.csv"'
    writer = csv.writer(response, delimiter=';')

    if kind == 'grades':
        writer.writerow(['Ученик', 'Предмет', 'Оценка', 'Дата'])
        qs = Grade.objects.select_related('student', 'subject')
        subject_id = request.GET.get('subject')
        if subject_id:
            qs = qs.filter(subject_id=subject_id)
        for g in qs:
            writer.writerow([g.student.get_full_name() or g.student.username,
                             g.subject.name, g.value, g.date])
    elif kind == 'attendance':
        writer.writerow(['Ученик', 'Предмет', 'Дата', 'Статус'])
        qs = Attendance.objects.select_related('student', 'subject')
        subject_id = request.GET.get('subject')
        if subject_id:
            qs = qs.filter(subject_id=subject_id)
        status = request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        for a in qs:
            writer.writerow([a.student.get_full_name() or a.student.username,
                             a.subject.name, a.date, a.get_status_display()])
    elif kind == 'homework':
        writer.writerow(['Предмет', 'Класс', 'Задание', 'Дедлайн'])
        qs = Homework.objects.select_related('subject', 'class_room')
        class_id = request.GET.get('class')
        if class_id:
            qs = qs.filter(class_room_id=class_id)
        for h in qs:
            writer.writerow([h.subject.name, h.class_room.name,
                             h.description.replace('\n', ' '), h.due_date])
    else:
        messages.error(request, 'Неизвестный тип отчёта')
        return redirect('dashboard')
    return response
