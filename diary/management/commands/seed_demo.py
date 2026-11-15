"""Наполнение БД демонстрационными данными для защиты проекта."""
import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from diary.models import (Attendance, ClassRoom, Grade, Homework,
                          ParentStudent, ScheduleItem, StudentProfile,
                          Subject, User)

SUBJECTS = ['Математика', 'Русский язык', 'Литература',
            'Физика', 'Информатика', 'История']
CLASSES = ['9А', '9Б', '10А']
STUDENTS = {
    '9А': ['Иванов Иван', 'Петрова Ольга', 'Сидоров Пётр'],
    '9Б': ['Кузнецова Анна', 'Смирнов Алексей'],
    '10А': ['Волков Дмитрий', 'Морозова Елена'],
}


class Command(BaseCommand):
    help = 'Создаёт демо-данные: учётки, классы, предметы, оценки, ДЗ, посещаемость'

    @transaction.atomic
    def handle(self, *args, **options):
        # Идемпотентность: удаляем служебные учётки и ВСЕ демо-учеников,
        # чтобы повторный запуск не падал с IntegrityError на student_*
        User.objects.filter(
            Q(username__in=['admin', 'teacher1', 'parent1']) |
            Q(username__startswith='student_')
        ).delete()

        # create_superuser принимает произвольные поля модели,
        # поэтому роль задаётся одним вызовом — без отдельного исправления
        User.objects.create_superuser(
            username='admin', password='admin123', role='admin',
            first_name='Админ', last_name='Системный')
        User.objects.create_user(
            username='teacher1', password='1234', role='teacher',
            first_name='Пётр', last_name='Учитель')
        parent = User.objects.create_user(
            username='parent1', password='1234', role='parent',
            first_name='Мария', last_name='Иванова')

        subjects = [Subject.objects.get_or_create(name=n)[0] for n in SUBJECTS]
        class_rooms = {name: ClassRoom.objects.get_or_create(name=name)[0]
                       for name in CLASSES}

        students = {}
        for class_name, names in STUDENTS.items():
            for full_name in names:
                last, first = full_name.split()
                user = User.objects.create_user(
                    username=f'student_{last.lower()}',
                    password='1234', role='student',
                    first_name=first, last_name=last)
                StudentProfile.objects.create(user=user,
                                              class_room=class_rooms[class_name])
                students.setdefault(class_name, []).append(user)

        # Родитель1 привязан ко всем ученикам 9А
        for child in students['9А']:
            ParentStudent.objects.create(parent=parent, student=child)

        # Расписание 9А
        for i, subject in enumerate(subjects[:4]):
            ScheduleItem.objects.get_or_create(
                day='mon', lesson_number=i + 1,
                class_room=class_rooms['9А'],
                defaults={'subject': subject, 'room': f'20{i + 1}'})

        # Оценки за последние 20 дней
        today = date.today()
        for offset in range(20):
            d = today - timedelta(days=offset)
            for student_list in students.values():
                for student in student_list:
                    for subject in random.sample(subjects, 3):
                        Grade.objects.get_or_create(
                            student=student, subject=subject, date=d,
                            defaults={'value': random.randint(3, 5)})

        # Домашние задания
        for class_name, room in class_rooms.items():
            for subject in subjects[:3]:
                Homework.objects.get_or_create(
                    subject=subject, class_room=room,
                    due_date=today + timedelta(days=7),
                    defaults={'description':
                              f'Повторить материал по предмету '
                              f'«{subject.name}», подготовиться к контрольной'})

        # Посещаемость
        for offset in range(10):
            d = today - timedelta(days=offset)
            for student_list in students.values():
                for student in student_list:
                    Attendance.objects.get_or_create(
                        student=student, subject=subjects[0], date=d,
                        defaults={'status': random.choices(
                            ['present', 'absent', 'late', 'sick'],
                            weights=[85, 5, 5, 5])[0]})

        self.stdout.write(self.style.SUCCESS(
            'Демо-данные созданы. Учётки: admin/admin123, teacher1/1234, '
            'parent1/1234, student_ivanov/1234 (остальные ученики — 1234)'))
