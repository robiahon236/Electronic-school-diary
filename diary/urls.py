from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/',
         auth_views.LoginView.as_view(template_name='diary/login.html'),
         name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),

    path('grades/', views.grades_list, name='grades'),
    path('grades/add/', views.add_grade, name='add_grade'),
    path('grades/<int:pk>/edit/', views.grade_edit, name='grade_edit'),
    path('grades/<int:pk>/delete/', views.grade_delete, name='grade_delete'),

    path('attendance/', views.attendance_list, name='attendance'),
    path('attendance/add/', views.attendance_add, name='attendance_add'),
    path('attendance/<int:pk>/edit/', views.attendance_edit, name='attendance_edit'),
    path('attendance/<int:pk>/delete/', views.attendance_delete,
         name='attendance_delete'),

    path('homework/', views.homework_list, name='homework'),
    path('homework/add/', views.add_homework, name='add_homework'),
    path('homework/<int:pk>/edit/', views.homework_edit, name='homework_edit'),
    path('homework/<int:pk>/delete/', views.homework_delete,
         name='homework_delete'),

    path('schedule/', views.schedule_view, name='schedule'),
    path('schedule/add/', views.schedule_add, name='schedule_add'),
    path('schedule/<int:pk>/edit/', views.schedule_edit, name='schedule_edit'),
    path('schedule/<int:pk>/delete/', views.schedule_delete,
         name='schedule_delete'),
    path('schedule/import/', views.import_schedule, name='import_schedule'),
    path('schedule/import-ajax/', views.import_schedule_ajax,
         name='import_schedule_ajax'),

    path('reports/grades/', views.report_grades, name='report_grades'),
    path('reports/attendance/', views.report_attendance, name='report_attendance'),
    path('reports/homework/', views.report_homework, name='report_homework'),
    path('reports/export/<str:kind>/', views.export_report, name='export_report'),
]
