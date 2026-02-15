import json
from datetime import date, timedelta
from calendar import monthrange
from decimal import Decimal

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.db.models import Sum
from django.utils import timezone
from django_htmx.http import trigger_client_event

from apps.services.models import Service, ServiceCategory, ServiceLog
from apps.recipients.models import Recipient, ContractService
from apps.core.models import Department


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
    
    # Проживающие
    recipients = Recipient.objects.filter(status='active')
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
        )
        available_services = set(cs.service_id for cs in contract_services)
        for cs in contract_services:
            if cs.max_quantity_per_month:
                service_limits[cs.service_id] = cs.max_quantity_per_month
    
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
        
        # Проверяем ограничение на количество услуг в месяц
        from apps.recipients.models import ContractService
        try:
            contract_service = ContractService.objects.get(
                contract__recipient=recipient,
                contract__is_active=True,
                service=service
            )
            max_quantity = contract_service.max_quantity_per_month
        except ContractService.DoesNotExist:
            max_quantity = None
        
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
        return JsonResponse({'error': str(e)}, status=400)


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
        return JsonResponse({'error': str(e)}, status=400)


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
        return JsonResponse({'error': str(e)}, status=400)


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
        return JsonResponse({'error': str(e)}, status=400)


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
