"""Модуль интеграции: загрузка расписания из внешнего JSON API.

Основной путь — HTTP GET к адресу из настройки SCHEDULE_API_URL
с таймаутом и проверкой кода ответа (raise_for_status).
Резервный путь — чтение локального файла (SCHEDULE_FALLBACK_PATH),
включается настройкой SCHEDULE_FALLBACK ('1' — включён).
"""
import json
import logging

import requests
from django.conf import settings
from django.db import transaction

from ..models import ClassRoom, ScheduleItem, Subject

logger = logging.getLogger(__name__)

VALID_DAYS = {code for code, _ in ScheduleItem.WEEKDAYS}
REQUIRED_FIELDS = ('class', 'subject', 'day', 'room', 'lesson_number')
MIN_LESSON, MAX_LESSON = 1, 10


class ScheduleImportError(Exception):
    """Ошибка данных расписания (невалидная структура или значения)."""


def validate_item(item):
    """Проверяет структуру и значения одной записи расписания."""
    if not isinstance(item, dict):
        raise ScheduleImportError('Запись расписания должна быть объектом')
    for field in REQUIRED_FIELDS:
        if field not in item:
            raise ScheduleImportError(f'Отсутствует поле {field}')
    if item['day'] not in VALID_DAYS:
        raise ScheduleImportError(f'Недопустимый день недели: {item["day"]!r}')
    lesson = item['lesson_number']
    if not isinstance(lesson, int) or not MIN_LESSON <= lesson <= MAX_LESSON:
        raise ScheduleImportError(f'Некорректный номер урока: {lesson!r}')


def fetch_data():
    """Возвращает (список_записей, источник): 'http' или 'fallback'.

    При сетевой ошибке или невалидном JSON (ValueError от resp.json())
    и включённом fallback читает локальный файл; при выключенном —
    конвертирует ошибку в ScheduleImportError, чтобы views вернули
    понятное сообщение, а не 500. Если API вернул валидный JSON, но
    структура не массив — fallback не используется (это ошибка данных,
    а не недоступность API).
    """
    try:
        resp = requests.get(settings.SCHEDULE_API_URL, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            raise ScheduleImportError('Ожидался массив записей')
        return data, 'http'
    except ScheduleImportError:
        raise
    except (requests.RequestException, ValueError) as exc:
        logger.warning('HTTP-источник недоступен: %s', exc)
        if getattr(settings, 'SCHEDULE_FALLBACK', '1') != '1':
            raise ScheduleImportError(f'API недоступен: {exc}') from exc
        return _load_fallback(), 'fallback'


def _load_fallback():
    path = getattr(settings, 'SCHEDULE_FALLBACK_PATH', 'schedule.json')
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.error('Fallback-файл не найден: %s', path)
        raise ScheduleImportError('API недоступен, fallback-файл не найден')
    except (ValueError, OSError) as exc:
        logger.error('Ошибка чтения fallback-файла: %s', exc)
        raise ScheduleImportError('Ошибка чтения fallback-файла')
    if not isinstance(data, list):
        raise ScheduleImportError('Ожидался массив записей')
    logger.info('Использован fallback-файл %s', path)
    return data


def import_schedule_data():
    """Импортирует расписание атомарно и идемпотентно.

    Возвращает кортеж (количество_записей, источник).
    """
    data, source = fetch_data()
    count = 0
    try:
        with transaction.atomic():
            for item in data:
                validate_item(item)
                class_room, _ = ClassRoom.objects.get_or_create(
                    name=item['class'])
                subject, _ = Subject.objects.get_or_create(
                    name=item['subject'])
                ScheduleItem.objects.update_or_create(
                    day=item['day'],
                    lesson_number=item['lesson_number'],
                    class_room=class_room,
                    defaults={'subject': subject, 'room': item['room']},
                )
                count += 1
    except ScheduleImportError as exc:
        logger.error('Ошибка данных расписания: %s', exc)
        raise
    logger.info('Импорт расписания: %s записей (источник: %s)', count, source)
    return count, source
