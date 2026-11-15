import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import requests
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from diary.models import (Attendance, ClassRoom, Grade, Homework,
                          ParentStudent, ScheduleItem, StudentProfile,
                          Subject, User)

SAMPLE = [
    {'class': '9А', 'subject': 'Математика', 'day': 'mon',
     'room': '201', 'lesson_number': 1},
    {'class': '9А', 'subject': 'Физика', 'day': 'mon',
     'room': '305', 'lesson_number': 2},
]


def _create_base_data():
    """Класс, предметы, пользователи и связи для демо-сценария."""
    class_room = ClassRoom.objects.create(name='9А')
    subject = Subject.objects.create(name='Математика')
    teacher = User.objects.create_user(
        username='teacher1', password='1234', role='teacher',
        first_name='Пётр', last_name='Учитель')
    student = User.objects.create_user(
        username='student1', password='1234', role='student',
        first_name='Иван', last_name='Иванов')
    parent = User.objects.create_user(
        username='parent1', password='1234', role='parent',
        first_name='Мария', last_name='Иванова')
    StudentProfile.objects.create(user=student, class_room=class_room)
    ParentStudent.objects.create(parent=parent, student=student)
    return class_room, subject, teacher, student, parent


class AuthAndAccessTests(TestCase):
    def setUp(self):
        (self.class_room, self.subject, self.teacher,
         self.student, self.parent) = _create_base_data()
        self.other_student = User.objects.create_user(
            username='student2', password='1234', role='student',
            first_name='Ольга', last_name='Петрова')

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get(reverse('grades'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp.url)

    def test_student_sees_only_own_grades(self):
        Grade.objects.create(student=self.student, subject=self.subject,
                             value=5, date='2026-01-10')
        Grade.objects.create(student=self.other_student, subject=self.subject,
                             value=3, date='2026-01-11')
        self.client.login(username='student1', password='1234')
        resp = self.client.get(reverse('grades'))
        self.assertEqual(len(resp.context['grades']), 1)
        # Поиск по фрагменту фамилии: своя фамилия находит оценку,
        # чужая — пусто
        resp = self.client.get(reverse('grades') + '?search=иван')
        self.assertEqual(len(resp.context['grades']), 1)
        resp = self.client.get(reverse('grades') + '?search=петров')
        self.assertEqual(len(resp.context['grades']), 0)

    def test_parent_sees_only_child_grades(self):
        Grade.objects.create(student=self.student, subject=self.subject,
                             value=4, date='2026-01-10')
        Grade.objects.create(student=self.other_student, subject=self.subject,
                             value=2, date='2026-01-11')
        self.client.login(username='parent1', password='1234')
        resp = self.client.get(reverse('grades'))
        self.assertEqual(len(resp.context['grades']), 1)
        self.assertEqual(resp.context['grades'][0].student, self.student)

    def test_student_cannot_add_grade(self):
        self.client.login(username='student1', password='1234')
        resp = self.client.get(reverse('add_grade'))
        self.assertEqual(resp.status_code, 403)


class ModelConstraintTests(TestCase):
    def setUp(self):
        (self.class_room, self.subject, self.teacher,
         self.student, self.parent) = _create_base_data()

    def test_grade_value_check_constraint(self):
        with self.assertRaises(IntegrityError):
            Grade.objects.create(student=self.student, subject=self.subject,
                                 value=6, date='2026-01-10')

    def test_attendance_repeat_marks_update(self):
        Attendance.objects.create(student=self.student, subject=self.subject,
                                  date='2026-01-10', status='present')
        Attendance.objects.update_or_create(
            student=self.student, subject=self.subject, date='2026-01-10',
            defaults={'status': 'absent', 'comment': 'Уважительная причина'})
        self.assertEqual(Attendance.objects.count(), 1)
        self.assertEqual(Attendance.objects.first().status, 'absent')


class ImportScheduleTests(TestCase):
    def setUp(self):
        (self.class_room, self.subject, self.teacher,
         self.student, self.parent) = _create_base_data()

    def _login_teacher(self):
        self.client.login(username='teacher1', password='1234')

    @patch('diary.integrations.schedule_api.requests.get')
    def test_import_success(self, mock_get):
        mock_get.return_value = MagicMock(
            json=lambda: SAMPLE, raise_for_status=lambda: None)
        self._login_teacher()
        resp = self.client.post(reverse('import_schedule'))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(ScheduleItem.objects.count(), 2)
        self.assertEqual(mock_get.call_args.kwargs.get('timeout'), 5)

    @patch('diary.integrations.schedule_api.requests.get',
           side_effect=requests.ConnectionError('network down'))
    def test_import_fallback_used(self, mock_get):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'schedule.json')
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(SAMPLE, f)
            with self.settings(SCHEDULE_FALLBACK='1',
                               SCHEDULE_FALLBACK_PATH=path):
                self._login_teacher()
                self.client.post(reverse('import_schedule'))
        self.assertEqual(ScheduleItem.objects.count(), 2)

    @patch('diary.integrations.schedule_api.requests.get',
           side_effect=requests.ConnectionError('network down'))
    def test_import_fallback_disabled(self, mock_get):
        self._login_teacher()
        with self.settings(SCHEDULE_FALLBACK='0'):
            resp = self.client.post(reverse('import_schedule'), follow=True)
        self.assertEqual(ScheduleItem.objects.count(), 0)
        self.assertContains(resp, 'Ошибка данных')

    @patch('diary.integrations.schedule_api.requests.get')
    def test_import_invalid_json_no_fallback(self, mock_get):
        mock_get.return_value = MagicMock(raise_for_status=lambda: None)
        mock_get.return_value.json.side_effect = ValueError('not json')
        self._login_teacher()
        with self.settings(SCHEDULE_FALLBACK='0'):
            resp = self.client.post(reverse('import_schedule'), follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Ошибка данных')

    @patch('diary.integrations.schedule_api.requests.get')
    def test_import_invalid_day_rejected(self, mock_get):
        bad = [{'class': '9А', 'subject': 'Химия', 'day': 'sunday',
                'room': '1', 'lesson_number': 1}]
        mock_get.return_value = MagicMock(
            json=lambda: bad, raise_for_status=lambda: None)
        self._login_teacher()
        self.client.post(reverse('import_schedule'))
        self.assertEqual(ScheduleItem.objects.count(), 0)

    @patch('diary.integrations.schedule_api.requests.get')
    def test_import_is_idempotent(self, mock_get):
        mock_get.return_value = MagicMock(
            json=lambda: SAMPLE, raise_for_status=lambda: None)
        self._login_teacher()
        self.client.post(reverse('import_schedule'))
        self.client.post(reverse('import_schedule'))
        self.assertEqual(ScheduleItem.objects.count(), 2)

    def test_import_requires_post(self):
        self._login_teacher()
        resp = self.client.get(reverse('import_schedule'))
        self.assertEqual(resp.status_code, 405)


class ViewsTests(TestCase):
    def setUp(self):
        (self.class_room, self.subject, self.teacher,
         self.student, self.parent) = _create_base_data()
        self.other_class = ClassRoom.objects.create(name='10Б')

    def test_student_sees_only_own_schedule(self):
        ScheduleItem.objects.create(day='mon', lesson_number=1,
                                    class_room=self.class_room,
                                    subject=self.subject, room='201')
        ScheduleItem.objects.create(day='mon', lesson_number=2,
                                    class_room=self.other_class,
                                    subject=self.subject, room='301')
        self.client.login(username='student1', password='1234')
        resp = self.client.get(reverse('schedule'))
        items = resp.context['items']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].class_room, self.class_room)

    def test_homework_filter_by_class(self):
        Homework.objects.create(subject=self.subject, class_room=self.class_room,
                                description='Задание по математике',
                                due_date='2026-02-01')
        Homework.objects.create(subject=self.subject, class_room=self.other_class,
                                description='Задание для десятого класса',
                                due_date='2026-02-02')
        self.client.login(username='teacher1', password='1234')
        resp = self.client.get(reverse('homework') +
                               f'?class_room={self.class_room.pk}')
        self.assertEqual(len(resp.context['homework']), 1)
        # Поиск по фрагменту описания находит нужное задание
        resp = self.client.get(reverse('homework') + '?search=десятого')
        self.assertEqual(len(resp.context['homework']), 1)

    def test_admin_can_add_grade(self):
        admin = User.objects.create_user(
            username='admin1', password='1234', role='admin')
        self.client.login(username='admin1', password='1234')
        resp = self.client.post(reverse('add_grade'), data={
            'student': self.student.pk, 'subject': self.subject.pk,
            'value': 5, 'date': '2026-01-10'})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Grade.objects.count(), 1)

    def test_schedule_duplicate_shows_form_error(self):
        ScheduleItem.objects.create(day='mon', lesson_number=1,
                                    class_room=self.class_room,
                                    subject=self.subject, room='201')
        self.client.login(username='teacher1', password='1234')
        resp = self.client.post(reverse('schedule_add'), data={
            'day': 'mon', 'lesson_number': 1,
            'class_room': self.class_room.pk,
            'subject': self.subject.pk, 'room': '202'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['form'].errors)

    def test_report_attendance_pivot(self):
        Attendance.objects.create(student=self.student, subject=self.subject,
                                  date='2026-01-10', status='present')
        Attendance.objects.create(student=self.student, subject=self.subject,
                                  date='2026-01-11', status='late')
        self.client.login(username='teacher1', password='1234')
        resp = self.client.get(reverse('report_attendance'))
        self.assertEqual(len(resp.context['report']), 1)
        row = resp.context['report'][0]
        self.assertEqual(row['present'], 1)
        self.assertEqual(row['late'], 1)
        self.assertEqual(row['total'], 2)

    def test_export_csv_grades(self):
        Grade.objects.create(student=self.student, subject=self.subject,
                             value=5, date='2026-01-10')
        self.client.login(username='teacher1', password='1234')
        resp = self.client.get(reverse('export_report', args=['grades']))
        self.assertEqual(resp['Content-Type'], 'text/csv; charset=utf-8-sig')
        first_line = resp.content.decode('utf-8-sig').splitlines()[0]
        self.assertEqual(first_line, 'Ученик;Предмет;Оценка;Дата')
