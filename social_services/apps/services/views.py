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

from apps.services.models import Service, ServiceCategory, ServiceLog, ServiceSchedule, TabelLock, ServiceRecipient
from apps.recipients.models import Recipient, ContractService, RecipientHistory, Contract
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
    
    # Отделения
    departments = Department.objects.all()
    
    # Фильтрация отделений по ролям
    if not user.is_admin_or_hr:
        departments = departments.filter(id=user.department.id) if user.department else Department.objects.none()
    
    # Проживающие - только те, кто в интернате
    recipients = Recipient.objects.filter(
        placement='internat'
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
        'weekends': weekends,  # Выходные дни (для шаблона Django)
        'weekends_json': json.dumps(weekends),  # Выходные дни (JSON для JS)
        'holiday_days': holiday_days,  # Праздничные дни (для шаблона Django)
        'holiday_days_json': json.dumps(holiday_days),  # Праздничные дни (JSON для JS)
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
def get_category_services_api(request):
    """API для получения услуг категории с данными табеля (ленивая загрузка)"""
    try:
        category_id = request.GET.get('category_id')
        recipient_id = request.GET.get('recipient_id')
        year = int(request.GET.get('year', timezone.now().year))
        month = int(request.GET.get('month', timezone.now().month))  # 1-12
        
        if not category_id or not recipient_id:
            return JsonResponse({'error': 'Не указаны category_id или recipient_id'}, status=400)
        
        recipient = get_object_or_404(Recipient, id=recipient_id)
        category = get_object_or_404(ServiceCategory, id=category_id)
        
        # Получаем услуги из ИППСУ для этой категории
        contract_services = ContractService.objects.filter(
            contract__recipient=recipient,
            contract__is_active=True,
            service__category=category
        ).select_related('service')
        
        available_service_ids = set(cs.service_id for cs in contract_services)
        
        # Функция сортировки по коду
        def sort_key(service):
            parts = service.code.split('.')
            result = []
            for part in parts:
                num = ''.join(filter(str.isdigit, part))
                result.append(int(num) if num else 0)
            return result
        
        services = list(category.services.filter(id__in=available_service_ids))
        services.sort(key=sort_key)
        
        # Получаем данные табеля для этих услуг
        days_in_month = monthrange(year, month)[1]
        
        service_logs = ServiceLog.objects.filter(
            recipient=recipient,
            service__in=services,
            date__year=year,
            date__month=month
        ).values('service_id', 'date__day').annotate(
            total_quantity=Sum('quantity')
        )
        
        # Формируем словарь логов
        logs_dict = {}
        for log in service_logs:
            key = f"{log['service_id']}-{log['date__day']}"
            logs_dict[key] = int(log['total_quantity'])
        
        # Формируем данные услуг
        services_data = []
        for service in services:
            service_data = {
                'id': service.id,
                'code': service.code,
                'name': service.name,
                'max_quantity_per_month': service.max_quantity_per_month,
                'logs': {}
            }
            # Добавляем логи для этой услуги
            for day in range(1, days_in_month + 1):
                key = f"{service.id}-{day}"
                if key in logs_dict:
                    service_data['logs'][day] = logs_dict[key]
            
            # Считаем итог
            total = sum(service_data['logs'].values())
            service_data['total'] = total
            
            services_data.append(service_data)
        
        return JsonResponse({
            'success': True,
            'services': services_data,
            'days_in_month': days_in_month
        })
        
    except Exception as e:
        logger.exception("Error in get_category_services_api")
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
def get_recipient_status_on_date(recipient, target_date):
    """
    Определяет статус проживающего на конкретную дату на основе истории изменений.
    Возвращает 'active', 'vacation', 'hospital', 'discharged' или None.
    
    Логика:
    - Загружаем все записи истории до target_date включительно
    - Определяем статус на основе последнего изменения
    - Если истории нет - возвращаем текущий статус
    """
    from apps.recipients.models import RecipientHistory
    
    # Статусы, при которых проживающий считается "за пределами отделений"
    # (услуги не оказываются)
    INACTIVE_STATUSES = ['vacation', 'hospital', 'discharged']
    ACTIVE_STATUSES = ['active']
    
    # Получаем все записи истории до указанной даты (включительно)
    history_records = RecipientHistory.objects.filter(
        recipient=recipient,
        date__lte=target_date
    ).order_by('-date', '-created_at')
    
    if not history_records.exists():
        # Если истории нет, возвращаем текущий статус
        return recipient.status
    
    # Берём последнюю запись по дате
    last_record = history_records.first()
    
    # Определяем статус на основе нового статуса из записи
    # new_status - это статус, который установился после изменения
    if last_record.new_status:
        return last_record.new_status
    
    # Если new_status не указан, определяем по отделению
    if last_record.new_department:
        return last_record.new_department.status_code
    
    # Если ничего не указано, считаем активным
    return 'active'


def get_inactive_days_in_month(recipient, year, month):
    """
    Возвращает множество дней месяца, в которые проживающий был неактивен
    (в отпуске, больнице или выбыл).
    
    Использует поле placement для определения размещения.
    
    Returns:
        set: множество номеров дней (1-31), в которые услуги не должны проставляться
    """
    from apps.recipients.models import RecipientHistory
    
    # Неактивные размещения - услуги не оказываются
    INACTIVE_PLACEMENTS = ['vacation', 'hospital', 'discharged']
    
    days_in_month = monthrange(year, month)[1]
    inactive_days = set()
    
    # Получаем все записи истории за месяц и ранее
    history_records = RecipientHistory.objects.filter(
        recipient=recipient,
        date__lte=date(year, month, days_in_month)
    ).order_by('date', 'created_at')
    
    if not history_records.exists():
        # Если истории нет, проверяем текущее размещение
        if recipient.placement in INACTIVE_PLACEMENTS:
            return set(range(1, days_in_month + 1))
        return set()
    
    # Строим хронологию размещений
    # Для каждого дня определяем размещение
    current_placement = 'internat'  # По умолчанию считаем проживающим
    
    # Создаём словарь: день -> размещение после изменения
    placement_changes = {}
    
    for record in history_records:
        record_date = record.date
        # Нас интересуют только записи до или в целевом месяце
        if record_date.year == year and record_date.month == month:
            day = record_date.day
            # Приоритет: new_placement -> new_status (для совместимости)
            if record.new_placement:
                placement_changes[day] = record.new_placement
            elif record.new_status:
                # Маппинг старых статусов на размещения
                status_to_placement = {
                    'active': 'internat',
                    'vacation': 'vacation',
                    'hospital': 'hospital',
                    'discharged': 'discharged',
                }
                placement_changes[day] = status_to_placement.get(record.new_status, 'internat')
    
    # Определяем размещение на начало месяца
    # Ищем последнюю запись до начала месяца
    before_month = RecipientHistory.objects.filter(
        recipient=recipient,
        date__lt=date(year, month, 1)
    ).order_by('-date', '-created_at').first()
    
    if before_month:
        if before_month.new_placement:
            current_placement = before_month.new_placement
        elif before_month.new_status:
            status_to_placement = {
                'active': 'internat',
                'vacation': 'vacation',
                'hospital': 'hospital',
                'discharged': 'discharged',
            }
            current_placement = status_to_placement.get(before_month.new_status, 'internat')
    else:
        # Если истории до месяца нет, используем текущее размещение
        current_placement = recipient.placement
    
    # Проходим по всем дням месяца
    for day in range(1, days_in_month + 1):
        # Если в этот день было изменение размещения, обновляем
        if day in placement_changes:
            current_placement = placement_changes[day]
        
        # Если размещение неактивное, добавляем день в список
        if current_placement in INACTIVE_PLACEMENTS:
            inactive_days.add(day)
    
    return inactive_days


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
        
        # Получаем дни, в которые проживающий был неактивен (в отпуске, больнице, выбыл)
        # Это позволяет корректно заполнять табель за прошлые периоды, даже если текущий статус неактивный
        inactive_days = get_inactive_days_in_month(recipient, year, month)
        
        # Если все дни месяца неактивны, сообщаем об этом
        days_in_month = monthrange(year, month)[1]
        if len(inactive_days) == days_in_month:
            return JsonResponse({
                'error': f'Проживающий был неактивен весь месяц (отпуск, больница или выбыл)',
                'filled_count': 0
            })
        
        # Получаем услуги из ИППСУ
        contract_services = ContractService.objects.filter(
            contract__recipient=recipient,
            contract__is_active=True
        ).select_related('service')
        
        # Получаем назначенные услуги для получателя
        assigned_services = ServiceRecipient.objects.filter(
            recipient=recipient,
            is_active=True
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
                    # Пропускаем неактивные дни (отпуск, больница, выбыл)
                    if day in inactive_days:
                        continue
                    
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
                        # Пропускаем неактивные дни (отпуск, больница, выбыл)
                        if day in inactive_days:
                            continue
                        
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
        
        # Обрабатываем назначенные услуги из модуля "Назначение услуг"
        for assigned in assigned_services:
            service = assigned.service
            service_id = service.id
            
            # Пропускаем, если услуга уже обработана через ИППСУ
            if service_id in service_totals:
                continue
            
            # Инициализируем счётчик для услуги
            service_totals[service_id] = 0
            
            # Проверяем, есть ли расписание для этой услуги
            if service_id in schedule_dict:
                # Заполняем по расписанию отделения
                for day in range(1, days_in_month + 1):
                    # Пропускаем неактивные дни (отпуск, больница, выбыл)
                    if day in inactive_days:
                        continue
                    
                    current_date = date(year, month, day)
                    day_of_week = current_date.weekday()  # 0=понедельник
                    
                    if day_of_week in schedule_dict[service_id]:
                        quantity = schedule_dict[service_id][day_of_week]
                        
                        # Проверяем лимит на месяц
                        max_quantity = service.max_quantity_per_month
                        if max_quantity:
                            if service_totals[service_id] >= max_quantity:
                                continue
                        
                        # Проверяем существующую запись
                        key = (service_id, current_date)
                        if key in existing_logs_dict:
                            log = existing_logs_dict[key]
                            old_qty = log.quantity
                            log.quantity = quantity
                            log.provider = user
                            log.price_at_service = service.price
                            logs_to_update.append(log)
                            service_totals[service_id] += quantity - old_qty
                        else:
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
                # Заполняем по периодичности назначения
                if freq == 'daily':
                    # Ежедневно
                    for day in range(1, days_in_month + 1):
                        # Пропускаем неактивные дни (отпуск, больница, выбыл)
                        if day in inactive_days:
                            continue
                        
                        current_date = date(year, month, day)
                        
                        max_quantity = service.max_quantity_per_month
                        if max_quantity and service_totals[service_id] >= max_quantity:
                            continue
                        
                        key = (service_id, current_date)
                        if key not in existing_logs_dict:
                            logs_to_create.append(ServiceLog(
                                recipient=recipient,
                                service=service,
                                date=current_date,
                                quantity=1,
                                provider=user,
                                price_at_service=service.price
                            ))
                            service_totals[service_id] += 1
                
                elif freq == 'weekly':
                    # Еженедельно - проставляем в первый понедельник месяца
                    for day in range(1, days_in_month + 1):
                        # Пропускаем неактивные дни (отпуск, больница, выбыл)
                        if day in inactive_days:
                            continue
                        
                        current_date = date(year, month, day)
                        if current_date.weekday() == 0:  # Понедельник
                            key = (service_id, current_date)
                            if key not in existing_logs_dict:
                                logs_to_create.append(ServiceLog(
                                    recipient=recipient,
                                    service=service,
                                    date=current_date,
                                    quantity=1,
                                    provider=user,
                                    price_at_service=service.price
                                ))
                                service_totals[service_id] += 1
                            break
                
                elif freq == 'biweekly':
                    # Раз в 2 недели - проставляем в 1-й и 15-й день
                    for target_day in [1, 15]:
                        if target_day <= days_in_month:
                            # Пропускаем неактивные дни (отпуск, больница, выбыл)
                            if target_day in inactive_days:
                                continue
                            
                            current_date = date(year, month, target_day)
                            key = (service_id, current_date)
                            if key not in existing_logs_dict:
                                logs_to_create.append(ServiceLog(
                                    recipient=recipient,
                                    service=service,
                                    date=current_date,
                                    quantity=1,
                                    provider=user,
                                    price_at_service=service.price
                                ))
                                service_totals[service_id] += 1
                
                elif freq == 'monthly':
                    # Ежемесячно - проставляем в первый день месяца
                    # Пропускаем если день неактивный
                    if 1 not in inactive_days:
                        current_date = date(year, month, 1)
                        key = (service_id, current_date)
                        if key not in existing_logs_dict:
                            logs_to_create.append(ServiceLog(
                                recipient=recipient,
                                service=service,
                                date=current_date,
                                quantity=1,
                                provider=user,
                                price_at_service=service.price
                            ))
                            service_totals[service_id] += 1
                
                elif freq == 'quarterly':
                    # Ежеквартально - проставляем если месяц кратен 3 (март, июнь, сентябрь, декабрь)
                    if month % 3 == 0:
                        # Пропускаем если день неактивный
                        if 1 not in inactive_days:
                            current_date = date(year, month, 1)
                            key = (service_id, current_date)
                            if key not in existing_logs_dict:
                                logs_to_create.append(ServiceLog(
                                    recipient=recipient,
                                    service=service,
                                    date=current_date,
                                    quantity=1,
                                    provider=user,
                                    price_at_service=service.price
                                ))
                                service_totals[service_id] += 1
                
                elif freq == 'custom':
                    # Индивидуальный график - пока проставляем в первый день
                    # В будущем можно добавить парсинг custom_frequency
                    # Пропускаем если день неактивный
                    if 1 not in inactive_days:
                        current_date = date(year, month, 1)
                        key = (service_id, current_date)
                        if key not in existing_logs_dict:
                            logs_to_create.append(ServiceLog(
                                recipient=recipient,
                                service=service,
                                date=current_date,
                                quantity=1,
                                provider=user,
                                price_at_service=service.price
                            ))
                            service_totals[service_id] += 1
        
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


@login_required
def service_recipients_tabel_view(request):
    """
    Страница назначения услуг получателям в формате табеля.
    Таблица: сверху дни месяца, слева получатели услуг.
    """
    from calendar import monthrange
    
    user = request.user
    
    # Получаем параметры фильтрации
    year = int(request.GET.get('year', timezone.now().year))
    month = int(request.GET.get('month', timezone.now().month))  # 1-12
    service_id = request.GET.get('service')
    
    # Корректируем месяц
    if month < 1:
        month = 12
        year -= 1
    elif month > 12:
        month = 1
        year += 1
    
    # Количество дней в месяце
    days_in_month = monthrange(year, month)[1]
    
    # Получаем выбранную услугу
    selected_service = None
    if service_id:
        selected_service = Service.objects.filter(id=service_id).first()
    
    # Категории с услугами для выбора
    def sort_key(service):
        code = service.code
        parts = code.split('.')
        result = []
        for part in parts:
            num = ''.join(filter(str.isdigit, part))
            result.append(int(num) if num else 0)
        return result
    
    categories_with_services = []
    categories = ServiceCategory.objects.all().order_by('order')
    for category in categories:
        services = list(category.services.filter(is_active=True).order_by('code'))
        services.sort(key=sort_key)
        if services:
            categories_with_services.append({
                'category': category,
                'services': services
            })
    
    # Получатели услуги (назначенные)
    assigned_recipients = []
    service_logs = {}  # {recipient_id: {day: quantity}}
    
    if selected_service:
        # Получаем всех получателей, которым назначена эта услуга
        assignments = ServiceRecipient.objects.filter(
            service=selected_service,
            is_active=True
        ).select_related('recipient', 'recipient__department').order_by(
            'recipient__last_name', 'recipient__first_name'
        )
        
        # Фильтрация по отделению
        department_id = request.GET.get('department', '')
        if department_id:
            assignments = assignments.filter(recipient__department_id=department_id)
        
        if not user.is_admin_or_hr and user.department:
            assignments = assignments.filter(recipient__department=user.department)
        
        assigned_recipients = list(assignments)
        
        # Получаем данные об оказанных услугах за месяц
        recipient_ids = [a.recipient_id for a in assigned_recipients]
        logs = ServiceLog.objects.filter(
            recipient_id__in=recipient_ids,
            service=selected_service,
            date__year=year,
            date__month=month
        ).values('recipient_id', 'date__day').annotate(
            total_quantity=Sum('quantity')
        )
        
        for log in logs:
            recipient_id = log['recipient_id']
            day = log['date__day']
            if recipient_id not in service_logs:
                service_logs[recipient_id] = {}
            service_logs[recipient_id][day] = int(log['total_quantity'])
    
    # Отделения для фильтра
    departments = Department.objects.all()
    
    # Месяцы для выбора
    months = [
        (1, 'Январь'), (2, 'Февраль'), (3, 'Март'),
        (4, 'Апрель'), (5, 'Май'), (6, 'Июнь'),
        (7, 'Июль'), (8, 'Август'), (9, 'Сентябрь'),
        (10, 'Октябрь'), (11, 'Ноябрь'), (12, 'Декабрь')
    ]
    
    # Годы для выбора
    years = list(range(2020, 2031))
    
    # Определяем выходные и праздничные дни
    weekends = []
    for day in range(1, days_in_month + 1):
        current_date = date(year, month, day)
        if current_date.weekday() in [5, 6]:
            weekends.append(day)
    
    # Праздничные дни России
    holidays = [
        (1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (1, 6), (1, 7), (1, 8),
        (2, 23), (3, 8), (5, 1), (5, 9), (6, 12), (11, 4),
    ]
    holiday_days = [d for m, d in holidays if m == month]
    
    # Обработка POST запросов
    if request.method == 'POST':
        action = request.POST.get('action')
        
        # Вспомогательная функция для проверки блокировки табеля
        def check_tabel_lock(recipient, year, month):
            """Проверяет, заблокирован ли табель для получателя"""
            return TabelLock.objects.filter(
                recipient=recipient,
                year=year,
                month=month,
                is_locked=True
            ).exists()
        
        # Вспомогательная функция для проверки наличия услуги в ИППСУ
        def check_service_in_contract(recipient, service):
            """Проверяет, есть ли услуга в активном ИППСУ получателя"""
            return ContractService.objects.filter(
                contract__recipient=recipient,
                contract__is_active=True,
                service=service
            ).exists()
        
        if action == 'toggle_service':
            # Переключение услуги в ячейке
            recipient_id = request.POST.get('recipient_id')
            day = int(request.POST.get('day'))
            quantity = int(request.POST.get('quantity', 1))
            
            if selected_service and recipient_id:
                service_date = date(year, month, day)
                recipient = Recipient.objects.get(id=recipient_id)
                
                # Проверяем блокировку табеля
                if check_tabel_lock(recipient, year, month):
                    return JsonResponse({
                        'success': False,
                        'error': 'Табель заблокирован. Редактирование невозможно.',
                        'locked': True
                    }, status=403)
                
                # Получаем лимит услуги на месяц
                max_per_month = selected_service.max_quantity_per_month
                
                # Получаем текущее количество услуг за месяц (без текущего дня)
                current_total = ServiceLog.objects.filter(
                    recipient=recipient,
                    service=selected_service,
                    date__year=year,
                    date__month=month
                ).exclude(date=service_date).aggregate(
                    total=Sum('quantity')
                )['total'] or 0
                
                if quantity > 0:
                    # Проверяем лимит
                    if max_per_month and (current_total + quantity) > max_per_month:
                        return JsonResponse({
                            'success': False,
                            'error': f'Превышен лимит услуги ({max_per_month} раз в месяц). Уже проставлено: {current_total}',
                            'current_total': current_total,
                            'max_per_month': max_per_month
                        })
                    
                    ServiceLog.objects.update_or_create(
                        recipient=recipient,
                        service=selected_service,
                        date=service_date,
                        defaults={
                            'quantity': quantity,
                            'provider': user,
                            'price_at_service': selected_service.price
                        }
                    )
                else:
                    ServiceLog.objects.filter(
                        recipient=recipient,
                        service=selected_service,
                        date=service_date
                    ).delete()
                
                # Возвращаем обновленные данные
                total = ServiceLog.objects.filter(
                    recipient=recipient,
                    service=selected_service,
                    date__year=year,
                    date__month=month
                ).aggregate(total=Sum('quantity'))['total'] or 0
                
                return JsonResponse({
                    'success': True,
                    'total': str(total),
                    'max_per_month': max_per_month
                })
        
        elif action == 'add_recipients':
            # Добавление получателей
            recipient_ids = request.POST.getlist('recipients')
            
            if selected_service and recipient_ids:
                # Проверяем блокировку табеля для каждого получателя
                locked_recipients = []
                # Проверяем наличие услуги в ИППСУ для каждого получателя
                no_contract_recipients = []
                
                for recipient_id in recipient_ids:
                    recipient = Recipient.objects.filter(id=recipient_id).first()
                    if recipient:
                        if check_tabel_lock(recipient, year, month):
                            locked_recipients.append(recipient.full_name)
                        elif not check_service_in_contract(recipient, selected_service):
                            no_contract_recipients.append(recipient.full_name)
                
                if locked_recipients:
                    return JsonResponse({
                        'success': False,
                        'error': f'Табель заблокирован для: {", ".join(locked_recipients)}',
                        'locked': True
                    }, status=403)
                
                if no_contract_recipients:
                    return JsonResponse({
                        'success': False,
                        'error': f'Услуга отсутствует в ИППСУ: {", ".join(no_contract_recipients[:5])}' + ('...' if len(no_contract_recipients) > 5 else ''),
                        'no_contract': True,
                        'recipients_without_contract': no_contract_recipients[:10]
                    }, status=400)
                
                added_count = 0
                for recipient_id in recipient_ids:
                    # Проверяем, не назначен ли уже этот получатель
                    obj, created = ServiceRecipient.objects.get_or_create(
                        service=selected_service,
                        recipient_id=recipient_id,
                        defaults={
                            'created_by': user
                        }
                    )
                    if not created:
                        # Если уже существует - активируем
                        obj.is_active = True
                        obj.save()
                    added_count += 1
                
                return JsonResponse({
                    'success': True,
                    'added_count': added_count,
                    'message': f'Добавлено {added_count} получателей'
                })
            
            return JsonResponse({'success': False, 'error': 'Не выбраны получатели'})
        
        elif action == 'remove_recipient':
            # Удаление получателя
            assignment_id = request.POST.get('assignment_id')
            if assignment_id:
                # Получаем назначение и проверяем блокировку
                assignment = ServiceRecipient.objects.filter(id=assignment_id).select_related('recipient').first()
                if assignment and check_tabel_lock(assignment.recipient, year, month):
                    return JsonResponse({
                        'success': False,
                        'error': 'Табель заблокирован. Редактирование невозможно.',
                        'locked': True
                    }, status=403)
                ServiceRecipient.objects.filter(id=assignment_id).delete()
                return JsonResponse({'success': True})
            return JsonResponse({'success': False, 'error': 'Не указан ID назначения'})
        
        elif action == 'update_recipients':
            # Добавление и удаление получателей одним запросом
            add_ids = request.POST.getlist('add_recipients')
            remove_ids = request.POST.getlist('remove_recipients')
            
            logger.info(f"update_recipients: add={add_ids}, remove={remove_ids}, service={selected_service}")
            
            if selected_service:
                # Проверяем блокировку для всех получателей
                all_recipient_ids = list(set(add_ids + remove_ids))
                locked_recipients = []
                # Проверяем наличие услуги в ИППСУ для добавляемых получателей
                no_contract_recipients = []
                
                for recipient_id in all_recipient_ids:
                    recipient = Recipient.objects.filter(id=recipient_id).first()
                    if recipient:
                        if check_tabel_lock(recipient, year, month):
                            locked_recipients.append(recipient.full_name)
                        # Проверяем ИППСУ только для добавляемых
                        elif recipient_id in add_ids and not check_service_in_contract(recipient, selected_service):
                            no_contract_recipients.append(recipient.full_name)
                
                if locked_recipients:
                    return JsonResponse({
                        'success': False,
                        'error': f'Табель заблокирован для: {", ".join(locked_recipients)}',
                        'locked': True
                    }, status=403)
                
                if no_contract_recipients:
                    return JsonResponse({
                        'success': False,
                        'error': f'Услуга отсутствует в ИППСУ: {", ".join(no_contract_recipients[:5])}' + ('...' if len(no_contract_recipients) > 5 else ''),
                        'no_contract': True,
                        'recipients_without_contract': no_contract_recipients[:10]
                    }, status=400)
                
                with transaction.atomic():
                    # Добавляем новых получателей
                    for recipient_id in add_ids:
                        obj, created = ServiceRecipient.objects.get_or_create(
                            service=selected_service,
                            recipient_id=recipient_id,
                            defaults={
                                'created_by': user
                            }
                        )
                        if not created:
                            obj.is_active = True
                            obj.save()
                    
                    # Удаляем получателей
                    if remove_ids:
                        deleted_count = ServiceRecipient.objects.filter(
                            service=selected_service,
                            recipient_id__in=remove_ids
                        ).delete()
                        logger.info(f"Deleted: {deleted_count}")
            
            return JsonResponse({'success': True, 'added': len(add_ids), 'removed': len(remove_ids)})
        
        elif action == 'toggle_status':
            # Переключение статуса получателя
            assignment_id = request.POST.get('assignment_id')
            is_active = request.POST.get('is_active') == 'true'
            
            if assignment_id:
                # Получаем назначение и проверяем блокировку
                assignment = ServiceRecipient.objects.filter(id=assignment_id).select_related('recipient').first()
                if assignment and check_tabel_lock(assignment.recipient, year, month):
                    return JsonResponse({
                        'success': False,
                        'error': 'Табель заблокирован. Редактирование невозможно.',
                        'locked': True
                    }, status=403)
                ServiceRecipient.objects.filter(id=assignment_id).update(
                    is_active=not is_active
                )
                return JsonResponse({'success': True})
            return JsonResponse({'success': False, 'error': 'Не указан ID назначения'})
        
        elif action == 'clear_column':
            # Очистка столбца (всех услуг за определённый день)
            day = request.POST.get('day')
            if not selected_service:
                return JsonResponse({'success': False, 'error': 'Услуга не выбрана'})
            if not day:
                return JsonResponse({'success': False, 'error': 'День не указан'})
            
            # Разделяем на заблокированных и незаблокированных
            locked_recipients = []
            unlocked_recipient_ids = []
            
            for assignment in assigned_recipients:
                if check_tabel_lock(assignment.recipient, year, month):
                    locked_recipients.append(assignment.recipient.full_name)
                else:
                    unlocked_recipient_ids.append(assignment.recipient_id)
            
            # Удаляем записи только для незаблокированных
            if unlocked_recipient_ids:
                ServiceLog.objects.filter(
                    recipient_id__in=unlocked_recipient_ids,
                    service=selected_service,
                    date__year=year,
                    date__month=month,
                    date__day=day
                ).delete()
            
            return JsonResponse({
                'success': True,
                'cleared_count': len(unlocked_recipient_ids),
                'locked_count': len(locked_recipients),
                'locked_recipients': locked_recipients[:5],
                'message': f'Очищено {len(unlocked_recipient_ids)} получателей' + (f', пропущено {len(locked_recipients)} (заблокированы)' if locked_recipients else '')
            })
        
        elif action == 'clear_all':
            # Очистка всей таблицы (всех услуг за месяц)
            if not selected_service:
                return JsonResponse({'success': False, 'error': 'Услуга не выбрана'})
            
            # Разделяем на заблокированных и незаблокированных
            locked_recipients = []
            unlocked_recipient_ids = []
            
            for assignment in assigned_recipients:
                if check_tabel_lock(assignment.recipient, year, month):
                    locked_recipients.append(assignment.recipient.full_name)
                else:
                    unlocked_recipient_ids.append(assignment.recipient_id)
            
            # Удаляем записи только для незаблокированных
            if unlocked_recipient_ids:
                ServiceLog.objects.filter(
                    recipient_id__in=unlocked_recipient_ids,
                    service=selected_service,
                    date__year=year,
                    date__month=month
                ).delete()
            
            return JsonResponse({
                'success': True,
                'cleared_count': len(unlocked_recipient_ids),
                'locked_count': len(locked_recipients),
                'locked_recipients': locked_recipients[:5],
                'message': f'Очищено {len(unlocked_recipient_ids)} получателей' + (f', пропущено {len(locked_recipients)} (заблокированы)' if locked_recipients else '')
            })
        
        elif action == 'autofill_month':
            # Автозаполнение с учётом расписания, периодичности и уже проставленных услуг
            import random
            
            if not selected_service:
                return JsonResponse({'success': False, 'error': 'Услуга не выбрана'})
            
            filled_cells = {}
            total_filled = 0
            skipped_count = 0
            locked_recipients = []
            
            # Получаем расписание услуги для отделений
            schedules = ServiceSchedule.objects.filter(service=selected_service)
            schedule_by_department = {}
            for schedule in schedules:
                if schedule.department_id not in schedule_by_department:
                    schedule_by_department[schedule.department_id] = []
                schedule_by_department[schedule.department_id].append({
                    'day_of_week': schedule.day_of_week,
                    'quantity': schedule.quantity
                })
            
            # Определяем лимит из периодичности услуги
            max_per_month = selected_service.max_quantity_per_month
            frequency = selected_service.frequency
            
            # Получаем периодичность назначения для каждого получателя
            for assignment in assigned_recipients:
                recipient_id = assignment.recipient_id
                recipient = assignment.recipient
                
                # Проверяем блокировку - пропускаем заблокированных
                if check_tabel_lock(recipient, year, month):
                    locked_recipients.append(recipient.full_name)
                    continue
                
                filled_cells[recipient_id] = {}
                
                # Получаем уже проставленные услуги за месяц
                existing_logs = ServiceLog.objects.filter(
                    recipient_id=recipient_id,
                    service=selected_service,
                    date__year=year,
                    date__month=month
                ).values_list('date__day', flat=True)
                existing_days = set(existing_logs)
                existing_count = len(existing_days)
                
                # Определяем лимит для этого получателя из норматива услуги
                target_count = max_per_month if max_per_month else 1
                
                # Ограничиваем лимитом из услуги
                if max_per_month and target_count > max_per_month:
                    target_count = max_per_month
                
                # Если уже проставлено достаточно - пропускаем
                if existing_count >= target_count:
                    skipped_count += 1
                    # Добавляем существующие записи в ответ для отображения
                    for day in existing_days:
                        filled_cells[recipient_id][day] = 1
                    continue
                
                # Сколько ещё нужно проставить
                remaining = target_count - existing_count
                
                # Проверяем расписание для отделения получателя
                dept_id = recipient.department_id if recipient.department else None
                has_schedule = dept_id and dept_id in schedule_by_department
                
                if has_schedule:
                    # Заполняем по расписанию
                    dept_schedules = schedule_by_department[dept_id]
                    filled_count = existing_count
                    
                    for day in range(1, days_in_month + 1):
                        if filled_count >= target_count:
                            break
                        
                        # Пропускаем уже заполненные дни
                        if day in existing_days:
                            filled_cells[recipient_id][day] = 1
                            continue
                        
                        current_date = date(year, month, day)
                        day_of_week = current_date.weekday()
                        
                        # Ищем расписание на этот день
                        for sched in dept_schedules:
                            if sched['day_of_week'] == day_of_week:
                                ServiceLog.objects.update_or_create(
                                    recipient_id=recipient_id,
                                    service=selected_service,
                                    date=current_date,
                                    defaults={
                                        'quantity': sched['quantity'],
                                        'provider': user,
                                        'price_at_service': selected_service.price
                                    }
                                )
                                filled_cells[recipient_id][day] = sched['quantity']
                                filled_count += sched['quantity']
                                total_filled += 1
                                break
                else:
                    # Нет расписания - заполняем случайным образом
                    # Выбираем случайные рабочие дни (исключая уже заполненные)
                    working_days = [d for d in range(1, days_in_month + 1)
                                   if d not in weekends and d not in existing_days]
                    
                    # Перемешиваем для случайного распределения
                    random.shuffle(working_days)
                    
                    # Выбираем нужное количество дней
                    selected_days = working_days[:remaining]
                    
                    for day in selected_days:
                        current_date = date(year, month, day)
                        ServiceLog.objects.update_or_create(
                            recipient_id=recipient_id,
                            service=selected_service,
                            date=current_date,
                            defaults={
                                'quantity': 1,
                                'provider': user,
                                'price_at_service': selected_service.price
                            }
                        )
                        filled_cells[recipient_id][day] = 1
                        total_filled += 1
                    
                    # Добавляем существующие записи в ответ
                    for day in existing_days:
                        filled_cells[recipient_id][day] = 1
            
            message = f'Заполнено {total_filled} записей'
            if skipped_count > 0:
                message += f', пропущено {skipped_count} получателей (уже заполнено)'
            if locked_recipients:
                message += f', пропущено {len(locked_recipients)} (заблокированы)'
            
            return JsonResponse({
                'success': True,
                'filled_cells': filled_cells,
                'total_filled': total_filled,
                'skipped_count': skipped_count,
                'locked_count': len(locked_recipients),
                'locked_recipients': locked_recipients[:5],
                'message': message
            })
    
    # Все проживающие для выбора в модальном окне
    # Фильтруем только тех, у кого выбранная услуга есть в активном ИППСУ
    all_recipients = Recipient.objects.filter(
        placement='internat'
    ).select_related('department').order_by('last_name', 'first_name')
    
    # Фильтрация по отделению
    if not user.is_admin_or_hr and user.department:
        all_recipients = all_recipients.filter(department=user.department)
    
    # Если выбрана услуга, фильтруем только получателей с этой услугой в ИППСУ
    recipients_with_service_ids = []
    if selected_service:
        recipients_with_service_ids = ContractService.objects.filter(
            contract__is_active=True,
            service=selected_service
        ).values_list('contract__recipient_id', flat=True)
        all_recipients = all_recipients.filter(id__in=recipients_with_service_ids)
    
    # ID уже назначенных получателей
    assigned_recipient_ids = [ar.recipient_id for ar in assigned_recipients]
    
    context = {
        'year': year,
        'month': month,
        'years': years,
        'months': months,
        'departments': departments,
        'selected_department': request.GET.get('department', ''),
        'categories_with_services': categories_with_services,
        'selected_service': selected_service,
        'assigned_recipients': assigned_recipients,
        'service_logs': service_logs,
        'days_in_month': days_in_month,
        'weekends': weekends,
        'holiday_days': holiday_days,
        'user': user,
        'max_per_month': selected_service.max_quantity_per_month if selected_service else None,
        'all_recipients': all_recipients,
        'assigned_recipient_ids': assigned_recipient_ids,
    }
    
    return render(request, 'services/assign_service_tabel.html', context)
