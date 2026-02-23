import json
import logging
from datetime import date, timedelta
from calendar import monthrange
from decimal import Decimal

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.db.models import Sum, Count
from django.db import transaction
from django.utils import timezone
from django_htmx.http import trigger_client_event

from apps.services.models import Service, ServiceCategory, ServiceLog, ServiceSchedule, TabelLock
from apps.recipients.models import Recipient, ContractService
from apps.core.models import Department

logger = logging.getLogger(__name__)


@login_required
def services_list_view(request):
    """Страница со списком всех услуг"""
    user = request.user
    
    # Получаем все категории с услугами
    categories = ServiceCategory.objects.all().order_by('order')
    
    # Функция для сортировки кодов услуг
    def sort_key(service):
        code = service.code
        parts = code.split('.')
        result = []
        for part in parts:
            num = ''.join(filter(str.isdigit, part))
            result.append(int(num) if num else 0)
        return result
    
    categories_with_services = []
    for category in categories:
        services = list(category.services.all().order_by('code'))
        services.sort(key=sort_key)
        if services:
            categories_with_services.append({
                'category': category,
                'services': services
            })
    
    context = {
        'categories_with_services': categories_with_services,
        'user': user,
    }
    
    return render(request, 'services/services_list.html', context)


@login_required
def tabel_view(request):
    """Представление табеля учета услуг"""
    user = request.user
    
    # Получаем параметры фильтрации
    year = int(request.GET.get('year', timezone.now().year))
    month = int(request.GET.get('month', timezone.now().month - 1))  # 0-indexed
    department_id = request.GET.get('department', '')
    recipient_id = request.GET.get('recipient', '')
    
    # Корректируем месяц (1-12 -> 0-11 для Python)
    if month < 0:
        month = 11
        year -= 1
    elif month > 11:
        month = 0
        year += 1
    
    # Количество дней в месяце
    days_in_month = monthrange(year, month + 1)[1]
    
    # Отделения (только реальные, без специальных)
    departments = Department.objects.filter(
        department_type__in=['residential', 'mercy']
    )
    
    # Фильтрация отделений по ролям
    if not user.is_admin_or_hr:
        departments = departments.filter(id=user.department.id) if user.department else Department.objects.none()
    
    # Проживающие - фильтруем по типу отделения (residential и mercy = активные)
    recipients = Recipient.objects.filter(
        department__department_type__in=['residential', 'mercy']
    ).select_related('department')
    if department_id:
        recipients = recipients.filter(department_id=department_id)
    if not user.is_admin_or_hr and user.department:
        recipients = recipients.filter(department=user.department)
    
    selected_recipient = None
    if recipient_id:
        selected_recipient = recipients.filter(id=recipient_id).first()
    
    # Доступные услуги для проживающего (из ИППСУ)
    available_services = set()
    service_limits = {}  # {service_id: max_quantity}
    if selected_recipient:
        contract_services = ContractService.objects.filter(
            contract__recipient=selected_recipient,
            contract__is_active=True
        ).select_related('service')
        available_services = set(cs.service_id for cs in contract_services)
        # Получаем лимиты напрямую из услуг
        for cs in contract_services:
            if cs.service.max_quantity_per_month:
                service_limits[cs.service_id] = cs.service.max_quantity_per_month
    
    # Функция для сортировки кодов услуг (учитывает точки, например 9.1, 9.2)
    def sort_key(service):
        code = service.code
        parts = code.split('.')
        result = []
        for part in parts:
            # Извлекаем числовую часть из каждой секции
            num = ''.join(filter(str.isdigit, part))
            result.append(int(num) if num else 0)
        return result
    
    # Категории и услуги - фильтруем по ИППСУ если выбран проживающий
    categories_with_services = []
    if selected_recipient and available_services:
        # Показываем только услуги из ИППСУ
        categories = ServiceCategory.objects.filter(
            services__id__in=available_services
        ).distinct().order_by('order')
        
        for category in categories:
            # Получаем услуги и сортируем в Python численно по коду
            services = list(category.services.filter(id__in=available_services))
            services.sort(key=sort_key)
            if services:
                categories_with_services.append({
                    'category': category,
                    'services': services
                })
    else:
        # Показываем все услуги если проживающий не выбран
        categories = ServiceCategory.objects.all().order_by('order')
        for category in categories:
            services = list(category.services.all())
            services.sort(key=sort_key)
            categories_with_services.append({
                'category': category,
                'services': services
            })
    
    # Данные табеля для выбранного проживающего
    service_logs = {}
    if selected_recipient:
        logs = ServiceLog.objects.filter(
            recipient=selected_recipient,
            date__year=year,
            date__month=month + 1
        ).values('service_id', 'date__day').annotate(
            total_quantity=Sum('quantity')
        )
        
        for log in logs:
            key = f"{log['service_id']}-{log['date__day']}"  # Используем дефис для совместимости с JavaScript
            # Преобразуем Decimal в int для JSON сериализации
            service_logs[key] = int(log['total_quantity'])
    
    # Месяцы для выбора
    months = [
        (0, 'Январь'), (1, 'Февраль'), (2, 'Март'),
        (3, 'Апрель'), (4, 'Май'), (5, 'Июнь'),
        (6, 'Июль'), (7, 'Август'), (8, 'Сентябрь'),
        (9, 'Октябрь'), (10, 'Ноябрь'), (11, 'Декабрь')
    ]
    
    # Годы для выбора
    years = list(range(2020, 2031))
    
    # Определяем выходные и праздничные дни
    weekends = []
    for day in range(1, days_in_month + 1):
        current_date = date(year, month + 1, day)
        # Суббота (5) и воскресенье (6)
        if current_date.weekday() in [5, 6]:
            weekends.append(day)
    
    # Праздничные дни России (фиксированные даты)
    holidays = [
        (1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (1, 6), (1, 7), (1, 8),  # Новогодние каникулы
        (2, 23),  # День защитника Отечества
        (3, 8),   # Международный женский день
        (5, 1),   # Праздник Весны и Труда
        (5, 9),   # День Победы
        (6, 12),  # День России
        (11, 4),  # День народного единства
    ]
    
    # Праздники в текущем месяце
    holiday_days = [d for m, d in holidays if m == month + 1]
    
    # Проверяем блокировку табеля
    is_locked = False
    if selected_recipient:
        lock = TabelLock.objects.filter(
            recipient=selected_recipient,
            year=year,
            month=month + 1  # month 0-indexed, в базе 1-12
        ).first()
        is_locked = lock.is_locked if lock else False
    
    context = {
        'year': year,
        'month': month,
        'years': years,
        'months': months,
        'departments': departments,
        'recipients': recipients,
        'selected_department': department_id,
        'selected_recipient': selected_recipient,
        'categories_with_services': categories_with_services,
        'service_logs': json.dumps(service_logs),
        'service_logs_dict': service_logs,  # Для использования в шаблоне
        'available_services': available_services,
        'service_limits': json.dumps(service_limits),
        'service_limits_dict': service_limits,  # Для использования в шаблоне
        'days_in_month': days_in_month,
        'weekends': weekends,  # Выходные дни
        'holiday_days': holiday_days,  # Праздничные дни
        'user': user,
        'is_locked': is_locked,
    }
    
    return render(request, 'services/tabel.html', context)


@login_required
@require_POST
def service_log_api(request):
    """API для сохранения записи табеля через HTMX"""
    try:
        # Поддерживаем как JSON, так и FormData
        content_type = request.content_type or ''
        if 'application/json' in content_type:
            data = json.loads(request.body)
        else:
            data = request.POST
        
        recipient_id = data.get('recipient_id')
        service_id = data.get('service_id')
        user = request.user
        
        # Проверяем права доступа
        recipient = get_object_or_404(Recipient, id=recipient_id)
        
        if not user.is_admin_or_hr and user.department != recipient.department:
            return JsonResponse({'error': 'Нет доступа'}, status=403)
        
        # Получаем год и месяц для проверки блокировки
        month = int(data.get('month'))
        year = int(data.get('year'))
        
        # Проверяем блокировку табеля
        lock = TabelLock.objects.filter(
            recipient=recipient,
            year=year,
            month=month,
            is_locked=True
        ).first()
        if lock:
            return JsonResponse({
                'error': f'Табель заблокирован. Редактирование невозможно.',
                'locked': True
            }, status=403)
        
        # Получаем услугу
        service = get_object_or_404(Service, id=service_id)
        
        # Проверяем batch-режим (заполнение всей строки)
        if data.get('batch') == 'true':
            days = json.loads(data.get('days', '[]'))
            month = int(data.get('month'))
            year = int(data.get('year'))
            quantity = Decimal(str(data.get('quantity', 0)))
            
            # Сохраняем все дни
            for day in days:
                service_date = date(year, month, day)
                
                if quantity > 0:
                    ServiceLog.objects.update_or_create(
                        recipient=recipient,
                        service=service,
                        date=service_date,
                        defaults={
                            'quantity': quantity,
                            'provider': user,
                            'price_at_service': service.price
                        }
                    )
                else:
                    ServiceLog.objects.filter(
                        recipient=recipient,
                        service=service,
                        date=service_date
                    ).delete()
            
            # Считаем итог по услуге за месяц
            total = ServiceLog.objects.filter(
                recipient=recipient,
                service=service,
                date__year=year,
                date__month=month
            ).aggregate(total=Sum('quantity'))['total'] or 0
            
            return JsonResponse({
                'success': True,
                'total': str(total),
                'days_saved': len(days)
            })
        
        # Обычный режим (одна ячейка)
        day = data.get('day')
        month = data.get('month')
        year = data.get('year')
        quantity = Decimal(str(data.get('quantity', 0)))
        
        # Преобразуем в int
        day = int(day)
        month = int(month)
        year = int(year)
        
        # Формируем дату (месяц приходит как 1-12 из JS)
        service_date = date(year, month, day)
        
        # Проверяем ограничение на количество услуг в месяц (теперь глобальное на услугу)
        max_quantity = service.max_quantity_per_month
        
        # Считаем текущее количество услуги за месяц (без текущей записи)
        current_total = ServiceLog.objects.filter(
            recipient=recipient,
            service=service,
            date__year=year,
            date__month=month
        ).exclude(date=service_date).aggregate(
            total=Sum('quantity')
        )['total'] or 0
        
        # Проверяем лимит
        if max_quantity is not None and (current_total + quantity) > max_quantity:
            return JsonResponse({
                'error': f'Превышен лимит: максимум {max_quantity} услуг в месяц, уже оказано {current_total}',
                'max_quantity': max_quantity,
                'current_total': str(current_total)
            }, status=400)
        
        if quantity > 0:
            # Создаём или обновляем запись
            log, created = ServiceLog.objects.update_or_create(
                recipient=recipient,
                service=service,
                date=service_date,
                defaults={
                    'quantity': quantity,
                    'provider': user,
                    'price_at_service': service.price
                }
            )
        else:
            # Удаляем запись если quantity = 0
            ServiceLog.objects.filter(
                recipient=recipient,
                service=service,
                date=service_date
            ).delete()
            log = None
        
        # Считаем итог по услуге за месяц
        total = ServiceLog.objects.filter(
            recipient=recipient,
            service=service,
            date__year=year,
            date__month=month
        ).aggregate(total=Sum('quantity'))['total'] or 0
        
        return JsonResponse({
            'success': True,
            'quantity': str(quantity) if quantity else '',
            'total': str(total),
            'max_quantity': max_quantity
        })
        
    except Exception as e:
        logger.exception("Error in service_log_api")
        return JsonResponse({'error': 'Внутренняя ошибка сервера'}, status=500)


@login_required
@require_GET
def get_service_log(request, recipient_id, service_id, date_str):
    """Получение данных об услуге за конкретную дату"""
    try:
        # Парсим дату (формат YYYY-MM-DD)
        year, month, day = map(int, date_str.split('-'))
        
        log = ServiceLog.objects.filter(
            recipient_id=recipient_id,
            service_id=service_id,
            date__year=year,
            date__month=month,
            date__day=day
        ).first()
        
        return JsonResponse({
            'quantity': str(log.quantity) if log else '0'
        })
        
    except Exception as e:
        logger.exception("Error in get_service_log")
        return JsonResponse({'error': 'Внутренняя ошибка сервера'}, status=500)


@login_required
@require_POST
def clear_month_api(request):
    """API для очистки всех услуг за месяц"""
    try:
        data = json.loads(request.body)
        recipient_id = data.get('recipient_id')
        year = int(data.get('year'))
        month = int(data.get('month'))  # 1-12
        
        # Проверяем права доступа
        recipient = get_object_or_404(Recipient, id=recipient_id)
        user = request.user
        
        if not user.is_admin_or_hr and user.department != recipient.department:
            return JsonResponse({'error': 'Нет доступа'}, status=403)
        
        # Проверяем блокировку табеля
        lock = TabelLock.objects.filter(
            recipient=recipient,
            year=year,
            month=month,
            is_locked=True
        ).first()
        if lock:
            return JsonResponse({
                'error': f'Табель заблокирован. Редактирование невозможно.',
                'locked': True
            }, status=403)
        
        # Удаляем все записи за месяц
        deleted_count, _ = ServiceLog.objects.filter(
            recipient=recipient,
            date__year=year,
            date__month=month
        ).delete()
        
        return JsonResponse({
            'success': True,
            'deleted_count': deleted_count
        })
        
    except Exception as e:
        logger.exception("Error in clear_month_api")
        return JsonResponse({'error': 'Внутренняя ошибка сервера'}, status=500)


@login_required
@require_POST
def clear_day_api(request):
    """API для очистки всех услуг за конкретный день"""
    try:
        data = json.loads(request.body)
        recipient_id = data.get('recipient_id')
        year = int(data.get('year'))
        month = int(data.get('month'))  # 1-12
        day = int(data.get('day'))
        service_ids = data.get('service_ids', [])
        
        # Проверяем права доступа
        recipient = get_object_or_404(Recipient, id=recipient_id)
        user = request.user
        
        if not user.is_admin_or_hr and user.department != recipient.department:
            return JsonResponse({'error': 'Нет доступа'}, status=403)
        
        # Проверяем блокировку табеля
        lock = TabelLock.objects.filter(
            recipient=recipient,
            year=year,
            month=month,
            is_locked=True
        ).first()
        if lock:
            return JsonResponse({
                'error': f'Табель заблокирован. Редактирование невозможно.',
                'locked': True
            }, status=403)
        
        # Формируем дату
        service_date = date(year, month, day)
        
        # Удаляем записи за указанный день
        deleted_count, _ = ServiceLog.objects.filter(
            recipient=recipient,
            date=service_date
        ).delete()
        
        return JsonResponse({
            'success': True,
            'deleted_count': deleted_count
        })
        
    except Exception as e:
        logger.exception("Error in clear_day_api")
        return JsonResponse({'error': 'Внутренняя ошибка сервера'}, status=500)


@login_required
def tabel_print_view(request):
    """Представление для печати табеля"""
    user = request.user
    
    # Получаем параметры
    year = int(request.GET.get('year', timezone.now().year))
    month = int(request.GET.get('month', timezone.now().month - 1))  # 0-indexed
    recipient_id = request.GET.get('recipient')
    
    # Корректируем месяц
    if month < 0:
        month = 11
        year -= 1
    elif month > 11:
        month = 0
        year += 1
    
    # Количество дней в месяце
    days_in_month = monthrange(year, month + 1)[1]
    
    # Получаем проживающего
    recipient = get_object_or_404(Recipient, id=recipient_id)
    
    # Проверяем права доступа
    if not user.is_admin_or_hr and user.department != recipient.department:
        return HttpResponse('Нет доступа', status=403)
    
    # Доступные услуги для проживающего (из ИППСУ)
    available_services = set()
    contract_services = ContractService.objects.filter(
        contract__recipient=recipient,
        contract__is_active=True
    )
    available_services = set(cs.service_id for cs in contract_services)
    
    # Функция для сортировки кодов услуг
    def sort_key(service):
        code = service.code
        parts = code.split('.')
        result = []
        for part in parts:
            num = ''.join(filter(str.isdigit, part))
            result.append(int(num) if num else 0)
        return result
    
    # Категории и услуги - показываем ВСЕ услуги, не только из ИППСУ
    categories_with_services = []
    categories = ServiceCategory.objects.all().order_by('order')
    
    for category in categories:
        services = list(category.services.all())
        services.sort(key=sort_key)
        if services:
            categories_with_services.append({
                'category': category,
                'services': services
            })
    
    # Данные табеля - вложенный словарь: service_logs[service_id][day] = count
    service_logs = {}
    logs = ServiceLog.objects.filter(
        recipient=recipient,
        date__year=year,
        date__month=month + 1
    ).values('service_id', 'date__day').annotate(
        total_quantity=Sum('quantity')
    )
    
    for log in logs:
        service_id = log['service_id']
        day = log['date__day']
        if service_id not in service_logs:
            service_logs[service_id] = {}
        service_logs[service_id][day] = int(log['total_quantity'])
    
    # Подсчет итогов по всем услугам (не только из ИППСУ)
    service_totals = {}
    all_logs = ServiceLog.objects.filter(
        recipient=recipient,
        date__year=year,
        date__month=month + 1
    ).values('service_id').annotate(
        total=Sum('quantity')
    )
    
    for log in all_logs:
        service_totals[log['service_id']] = int(log['total'])
    
    # Название месяца
    month_names = [
        'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
        'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
    ]
    month_name = month_names[month]
    
    context = {
        'recipient': recipient,
        'year': year,
        'month': month,
        'month_name': month_name,
        'days_in_month': days_in_month,
        'categories_with_services': categories_with_services,
        'service_logs': service_logs,
        'service_totals': service_totals,
        'available_services': available_services,
    }
    
    return render(request, 'services/tabel_print.html', context)


@login_required
@require_POST
def autofill_tabel(request):
    """API для автозаполнения табеля"""
    try:
        data = json.loads(request.body)
        recipient_id = data.get('recipient_id')
        year = int(data.get('year'))
        month = int(data.get('month'))  # 1-12
        
        user = request.user
        
        # Получаем проживающего
        recipient = get_object_or_404(Recipient, id=recipient_id)
        
        # Проверяем права доступа
        if not user.is_admin_or_hr and user.department != recipient.department:
            return JsonResponse({'error': 'Нет доступа'}, status=403)
        
        # Проверяем блокировку табеля
        lock = TabelLock.objects.filter(
            recipient=recipient,
            year=year,
            month=month,
            is_locked=True
        ).first()
        if lock:
            return JsonResponse({
                'error': f'Табель заблокирован. Редактирование невозможно.',
                'locked': True
            }, status=403)
        
        # Проверяем статус - если не активный, не заполняем
        if recipient.status != 'active':
            return JsonResponse({
                'error': f'Невозможно автозаполнение: статус проживающего "{recipient.status_display}"',
                'filled_count': 0
            })
        
        # Получаем услуги из ИППСУ
        contract_services = ContractService.objects.filter(
            contract__recipient=recipient,
            contract__is_active=True
        ).select_related('service')
        
        # Получаем расписание услуг для отделения
        schedules = ServiceSchedule.objects.filter(
            department=recipient.department
        ).select_related('service')
        
        # Создаём словарь расписания: {service_id: {day_of_week: quantity}}
        schedule_dict = {}
        for schedule in schedules:
            if schedule.service_id not in schedule_dict:
                schedule_dict[schedule.service_id] = {}
            schedule_dict[schedule.service_id][schedule.day_of_week] = schedule.quantity
        
        # Количество дней в месяце
        days_in_month = monthrange(year, month)[1]
        
        # Предварительно загружаем все существующие записи за месяц
        existing_logs = ServiceLog.objects.filter(
            recipient=recipient,
            date__year=year,
            date__month=month
        )
        
        # Словарь существующих записей: {(service_id, date): log}
        existing_logs_dict = {
            (log.service_id, log.date): log 
            for log in existing_logs
        }
        
        # Подсчитываем текущие количества по услугам
        current_totals = existing_logs.values('service_id').annotate(
            total=Sum('quantity')
        )
        service_totals = {item['service_id']: item['total'] or 0 for item in current_totals}
        
        # Списки для bulk операций
        logs_to_create = []
        logs_to_update = []
        
        # Проходим по всем услугам из ИППСУ
        for cs in contract_services:
            service = cs.service
            service_id = service.id
            
            # Инициализируем счётчик для услуги если нет
            if service_id not in service_totals:
                service_totals[service_id] = 0
            
            # Проверяем, есть ли расписание для этой услуги
            if service_id in schedule_dict:
                # Заполняем по расписанию
                for day in range(1, days_in_month + 1):
                    current_date = date(year, month, day)
                    day_of_week = current_date.weekday()  # 0=понедельник
                    
                    if day_of_week in schedule_dict[service_id]:
                        quantity = schedule_dict[service_id][day_of_week]
                        
                        # Проверяем лимит на месяц
                        max_quantity = service.max_quantity_per_month
                        if max_quantity:
                            # Учитываем уже добавленные в этом цикле
                            if service_totals[service_id] >= max_quantity:
                                continue
                        
                        # Проверяем существующую запись
                        key = (service_id, current_date)
                        if key in existing_logs_dict:
                            # Обновляем существующую
                            log = existing_logs_dict[key]
                            old_qty = log.quantity
                            log.quantity = quantity
                            log.provider = user
                            log.price_at_service = service.price
                            logs_to_update.append(log)
                            # Обновляем счётчик
                            service_totals[service_id] += quantity - old_qty
                        else:
                            # Создаём новую
                            logs_to_create.append(ServiceLog(
                                recipient=recipient,
                                service=service,
                                date=current_date,
                                quantity=quantity,
                                provider=user,
                                price_at_service=service.price
                            ))
                            service_totals[service_id] += quantity
            else:
                # Если расписания нет, заполняем ежедневно (для ежедневных услуг)
                if service.frequency and service.frequency.period_type == 'day':
                    # Получаем количество раз в день из периодичности
                    times_per_day = service.frequency.times_per_period or 1
                    
                    for day in range(1, days_in_month + 1):
                        current_date = date(year, month, day)
                        
                        # Проверяем лимит
                        max_quantity = service.max_quantity_per_month
                        if max_quantity:
                            if service_totals[service_id] >= max_quantity:
                                continue
                        
                        # Проверяем существующую запись
                        key = (service_id, current_date)
                        if key in existing_logs_dict:
                            # Обновляем существующую
                            log = existing_logs_dict[key]
                            old_qty = log.quantity
                            log.quantity = times_per_day
                            log.provider = user
                            log.price_at_service = service.price
                            logs_to_update.append(log)
                            service_totals[service_id] += times_per_day - old_qty
                        else:
                            # Создаём новую
                            logs_to_create.append(ServiceLog(
                                recipient=recipient,
                                service=service,
                                date=current_date,
                                quantity=times_per_day,
                                provider=user,
                                price_at_service=service.price
                            ))
                            service_totals[service_id] += times_per_day
        
        # Выполняем bulk операции в транзакции
        with transaction.atomic():
            if logs_to_create:
                ServiceLog.objects.bulk_create(logs_to_create, ignore_conflicts=True)
            if logs_to_update:
                ServiceLog.objects.bulk_update(
                    logs_to_update, 
                    ['quantity', 'provider', 'price_at_service']
                )
        
        filled_count = len(logs_to_create) + len(logs_to_update)
        
        return JsonResponse({
            'success': True,
            'filled_count': filled_count,
            'message': f'Заполнено {filled_count} записей'
        })
        
    except Exception as e:
        logger.exception("Error in autofill_tabel")
        return JsonResponse({'error': 'Внутренняя ошибка сервера'}, status=500)


@login_required
@require_GET
def get_service_logs_api(request):
    """API для получения всех логов услуг за месяц"""
    try:
        recipient_id = request.GET.get('recipient')
        year = int(request.GET.get('year'))
        month = int(request.GET.get('month'))  # 1-12
        
        # Проверяем права доступа
        recipient = get_object_or_404(Recipient, id=recipient_id)
        user = request.user
        
        if not user.is_admin_or_hr and user.department != recipient.department:
            return JsonResponse({'error': 'Нет доступа'}, status=403)
        
        # Получаем все логи за месяц
        logs = ServiceLog.objects.filter(
            recipient=recipient,
            date__year=year,
            date__month=month
        ).values('service_id', 'date__day').annotate(
            total_quantity=Sum('quantity')
        )
        
        # Формируем словарь
        service_logs = {}
        for log in logs:
            key = f"{log['service_id']}-{log['date__day']}"
            service_logs[key] = int(log['total_quantity'])
        
        return JsonResponse({
            'success': True,
            'logs': service_logs
        })
        
    except Exception as e:
        logger.exception("Error in get_service_logs_api")
        return JsonResponse({'error': 'Внутренняя ошибка сервера'}, status=500)


@login_required
@require_POST
def toggle_lock_api(request):
    """API для блокировки/разблокировки табеля"""
    try:
        data = json.loads(request.body)
        recipient_id = data.get('recipient_id')
        year = int(data.get('year'))
        month = int(data.get('month'))  # 1-12
        
        user = request.user
        
        # Получаем проживающего
        recipient = get_object_or_404(Recipient, id=recipient_id)
        
        # Проверяем права доступа
        if not user.is_admin_or_hr and user.department != recipient.department:
            return JsonResponse({'error': 'Нет доступа'}, status=403)
        
        # Получаем или создаём запись блокировки
        lock, created = TabelLock.objects.get_or_create(
            recipient=recipient,
            year=year,
            month=month,
            defaults={'is_locked': True, 'locked_by': user}
        )
        
        if not created:
            # Переключаем состояние
            lock.is_locked = not lock.is_locked
            lock.locked_by = user
            lock.save()
        
        return JsonResponse({
            'success': True,
            'is_locked': lock.is_locked,
            'message': 'Табель заблокирован' if lock.is_locked else 'Табель разблокирован'
        })
        
    except Exception as e:
        logger.exception("Error in toggle_lock_api")
        return JsonResponse({'error': 'Внутренняя ошибка сервера'}, status=500)
