from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


class User(AbstractUser):
    ROLE_CHOICES = [
        ('student', 'Ученик'),
        ('parent', 'Родитель'),
        ('teacher', 'Учитель'),
        ('admin', 'Администратор'),
    ]
    role = models.CharField('Роль', max_length=20,
                            choices=ROLE_CHOICES, default='student')

    class Meta:
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return f'{self.last_name} {self.first_name} ({self.role})'


class ClassRoom(models.Model):
    name = models.CharField('Класс', max_length=10, unique=True)

    def __str__(self):
        return self.name


class Subject(models.Model):
    name = models.CharField('Предмет', max_length=50, unique=True)

    def __str__(self):
        return self.name


class StudentProfile(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='student_profile',
        limit_choices_to={'role': 'student'}, verbose_name='Ученик')
    class_room = models.ForeignKey(
        ClassRoom, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='students', verbose_name='Класс')

    def __str__(self):
        return f'{self.user} — {self.class_room}'


class ParentStudent(models.Model):
    parent = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='children_links',
        limit_choices_to={'role': 'parent'}, verbose_name='Родитель')
    student = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='parent_links',
        limit_choices_to={'role': 'student'}, verbose_name='Ученик')

    class Meta:
        unique_together = ('parent', 'student')

    def clean(self):
        super().clean()
        if self.parent_id and self.parent.role != 'parent':
            raise ValidationError('Родитель должен иметь роль parent.')
        if self.student_id and self.student.role != 'student':
            raise ValidationError('Ученик должен иметь роль student.')

    def save(self, *args, **kwargs):
        # Проверка ролей работает и при программном создании (не только в формах)
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.parent} → {self.student}'


class Grade(models.Model):
    VALUE_CHOICES = [(v, str(v)) for v in range(2, 6)]

    student = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='grades',
        limit_choices_to={'role': 'student'}, verbose_name='Ученик')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE,
                                verbose_name='Предмет')
    value = models.PositiveSmallIntegerField('Оценка', choices=VALUE_CHOICES)
    date = models.DateField('Дата')

    class Meta:
        ordering = ['-date']
        constraints = [
            models.CheckConstraint(
                check=models.Q(value__gte=2, value__lte=5),
                name='grade_value_range'),
        ]

    def __str__(self):
        return f'{self.student} — {self.subject}: {self.value}'


class Homework(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE,
                                verbose_name='Предмет')
    class_room = models.ForeignKey(ClassRoom, on_delete=models.CASCADE,
                                   verbose_name='Класс')
    description = models.TextField('Задание')
    due_date = models.DateField('Срок сдачи')

    class Meta:
        ordering = ['due_date']

    def __str__(self):
        return f'{self.subject} ({self.class_room}) до {self.due_date}'


class ScheduleItem(models.Model):
    WEEKDAYS = [
        ('mon', 'Понедельник'), ('tue', 'Вторник'), ('wed', 'Среда'),
        ('thu', 'Четверг'), ('fri', 'Пятница'), ('sat', 'Суббота'),
    ]
    day = models.CharField('День недели', max_length=3, choices=WEEKDAYS)
    lesson_number = models.PositiveSmallIntegerField('Номер урока', default=1)
    class_room = models.ForeignKey(ClassRoom, on_delete=models.CASCADE,
                                   verbose_name='Класс')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE,
                                verbose_name='Предмет')
    room = models.CharField('Кабинет', max_length=10)

    class Meta:
        ordering = ['day', 'lesson_number']
        unique_together = ('day', 'lesson_number', 'class_room')

    def __str__(self):
        return (f'{self.class_room}: {self.get_day_display()}, '
                f'урок {self.lesson_number} — {self.subject}')


class Attendance(models.Model):
    STATUS_CHOICES = [
        ('present', 'Присутствовал'),
        ('absent', 'Отсутствовал'),
        ('late', 'Опоздал'),
        ('sick', 'Болел'),
    ]
    student = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='attendance',
        limit_choices_to={'role': 'student'}, verbose_name='Ученик')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE,
                                verbose_name='Предмет')
    date = models.DateField('Дата')
    status = models.CharField('Статус', max_length=10, choices=STATUS_CHOICES)
    comment = models.CharField('Комментарий', max_length=200, blank=True)

    class Meta:
        ordering = ['-date']
        unique_together = ('student', 'subject', 'date')

    def __str__(self):
        return f'{self.student} — {self.date}: {self.get_status_display()}'
