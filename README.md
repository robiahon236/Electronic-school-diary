Электронный дневник (Django 4.2)

Установка и запуск:
  pip install -r requirements.txt
  cp .env.example .env
  python manage.py makemigrations diary
  python manage.py migrate
  python manage.py seed_demo
  python manage.py runserver

Тесты:
  python manage.py test diary -v 2   # 19 тестов

Демо-аккаунты:
  admin/admin123, teacher1/1234, parent1/1234, student_ivanov/1234
  (пароль всех демо-учеников — 1234)

seed_demo идемпотентен: повторный запуск не создаёт дубликаты.
