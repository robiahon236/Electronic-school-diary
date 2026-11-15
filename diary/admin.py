from django.contrib import admin

from .models import (Attendance, ClassRoom, Grade, Homework, ParentStudent,
                     ScheduleItem, StudentProfile, Subject, User)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'last_name', 'first_name', 'role')
    list_filter = ('role',)
    search_fields = ('username', 'last_name')


@admin.register(ClassRoom)
class ClassRoomAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'class_room')
    list_filter = ('class_room',)


@admin.register(ParentStudent)
class ParentStudentAdmin(admin.ModelAdmin):
    list_display = ('parent', 'student')


@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = ('student', 'subject', 'value', 'date')
    list_filter = ('subject', 'value')
    search_fields = ('student__username',)


@admin.register(Homework)
class HomeworkAdmin(admin.ModelAdmin):
    list_display = ('subject', 'class_room', 'due_date')
    list_filter = ('subject', 'class_room')


@admin.register(ScheduleItem)
class ScheduleItemAdmin(admin.ModelAdmin):
    list_display = ('class_room', 'day', 'lesson_number', 'subject', 'room')
    list_filter = ('class_room', 'day')


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('student', 'subject', 'date', 'status')
    list_filter = ('status', 'subject')
    search_fields = ('student__username',)
