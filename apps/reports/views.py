from datetime import date
from decimal import Decimal
from calendar import monthrange

from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.template.loader import render_to_string
from django.utils import timezone

from apps.recipients.models import Recipient, ContractService
from apps.services.models import ServiceLog, Service, ServiceCategory
from apps.core.models import Department


@login_required
def act_generator(request):
    """Страница генерации актов - подобно странице табеля"""
    user = request.user
    
    # Получаем параметры
    year = int(request.GET.get('year', timezone.now().year))
    month = int(request.GET.get('month', timezone.now().month))
    department_id = request.GET.get('department', '')
    recipient_id = request.GET.get('recipient', '')
    
    # Отделения
    departments = Department.objects.all()
    if not user.is_admin_or_hr and user.department:
        departments = departments.filter(id=user.department.id)
    
    # Проживающие
    recipients = Recipient.objects.filter(status='active')
    if department_id:
        recipients = recipients.filter(department_id=department_id)
    if not user.is_admin_or_hr and user.department:
        recipients = recipients.filter(department=user.department)
    
    selected_recipient = None
    services_data = []
    total_sum = Decimal('0')
    
    if recipient_id:
        selected_recipient = recipients.filter(id=recipient_id).first()
        
        if selected_recipient:
            # Получаем услуги из ИППСУ (договора)
            contract_services = ContractService.objects.filter(
                contract__recipient=selected_recipient,
                contract__is_active=True
            ).select_related('service', 'service__category')
            
            # Получаем записи услуг за месяц
            logs = ServiceLog.objects.filter(
                recipient=selected_recipient,
                date__year=year,
                date__month=month
            ).select_related('service')
            
            # Группируем по услугам
            logs_by_service = {}
            for log in logs:
                service_id = log.service_id
                if service_id not in logs_by_service:
                    logs_by_service[service_id] = {
                        'quantity': Decimal('0'),
                        'price': log.price_at_service,
                        'total': Decimal('0'),
                    }
                logs_by_service[service_id]['quantity'] += log.quantity
                logs_by_service[service_id]['total'] += log.quantity * log.price_at_service
            
            # Формируем данные по услугам из ИППСУ
            for cs in contract_services:
                service = cs.service
                log_data = logs_by_service.get(service.id, {'quantity': Decimal('0'), 'price': service.price, 'total': Decimal('0')})
                
                services_data.append({
                    'service': service,
                    'quantity': log_data['quantity'],
                    'price': log_data['price'],
                    'total': log_data['total'],
                    'max_quantity': cs.max_quantity_per_month,
                })
            
            # Сортируем по коду услуги
            services_data = sorted(services_data, key=lambda x: x['service'].code)
            
            # Итоговая сумма
            total_sum = sum(item['total'] for item in services_data)
    
    # Месяцы (0-indexed для совместимости с tabel)
    months = [
        (0, 'Январь'), (1, 'Февраль'), (2, 'Март'),
        (3, 'Апрель'), (4, 'Май'), (5, 'Июнь'),
        (6, 'Июль'), (7, 'Август'), (8, 'Сентябрь'),
        (9, 'Октябрь'), (10, 'Ноябрь'), (11, 'Декабрь')
    ]
    
    years = list(range(2020, 2031))
    
    # Название месяца
    month_names = {
        0: 'Январь', 1: 'Февраль', 2: 'Март', 3: 'Апрель',
        4: 'Май', 5: 'Июнь', 6: 'Июль', 7: 'Август',
        8: 'Сентябрь', 9: 'Октябрь', 10: 'Ноябрь', 11: 'Декабрь'
    }
    
    context = {
        'year': year,
        'month': month,  # Реальный номер месяца (1-12) для PDF ссылки
        'month_index': month - 1,  # 0-indexed для селекта
        'years': years,
        'months': months,
        'departments': departments,
        'recipients': recipients,
        'selected_department': department_id,
        'selected_recipient': selected_recipient,
        'services_data': services_data,
        'total_sum': total_sum,
        'month_name': month_names.get(month - 1, ''),
    }
    
    return render(request, 'reports/act_generator.html', context)


@login_required
def generate_act(request, recipient_id, year, month):
    """Генерация акта оказанных услуг"""
    user = request.user
    recipient = get_object_or_404(Recipient, id=recipient_id)
    
    # Проверка доступа
    if not user.is_admin_or_hr and user.department != recipient.department:
        return HttpResponse('Нет доступа', status=403)
    
    # Получаем услуги из ИППСУ
    contract_services = ContractService.objects.filter(
        contract__recipient=recipient,
        contract__is_active=True
    ).select_related('service', 'service__category')
    
    # Получаем записи услуг за месяц
    logs = ServiceLog.objects.filter(
        recipient=recipient,
        date__year=year,
        date__month=month
    ).select_related('service')
    
    # Группируем по услугам
    logs_by_service = {}
    for log in logs:
        service_id = log.service_id
        if service_id not in logs_by_service:
            logs_by_service[service_id] = {
                'quantity': Decimal('0'),
                'price': log.price_at_service,
                'total': Decimal('0'),
            }
        logs_by_service[service_id]['quantity'] += log.quantity
        logs_by_service[service_id]['total'] += log.quantity * log.price_at_service
    
    # Формируем данные по услугам из ИППСУ
    services_data = []
    for cs in contract_services:
        service = cs.service
        log_data = logs_by_service.get(service.id, {'quantity': Decimal('0'), 'price': service.price, 'total': Decimal('0')})
        
        services_data.append({
            'service': service,
            'quantity': log_data['quantity'],
            'price': log_data['price'],
            'total': log_data['total'],
            'max_quantity': cs.max_quantity_per_month,
        })
    
    # Сортируем по коду услуги
    services_data = sorted(services_data, key=lambda x: x['service'].code)
    
    # Итоговая сумма
    total_sum = sum(item['total'] for item in services_data)
    
    # Количество дней в месяце
    days_in_month = monthrange(year, month)[1]
    
    # Название месяца
    month_names = {
        1: 'Январь', 2: 'Февраль', 3: 'Март', 4: 'Апрель',
        5: 'Май', 6: 'Июнь', 7: 'Июль', 8: 'Август',
        9: 'Сентябрь', 10: 'Октябрь', 11: 'Ноябрь', 12: 'Декабрь'
    }
    
    context = {
        'recipient': recipient,
        'year': year,
        'month': month,
        'month_name': month_names.get(month, ''),
        'days_in_month': days_in_month,
        'services_data': services_data,
        'total_sum': total_sum,
        'today': date.today(),
    }
    
    return render(request, 'reports/act.html', context)


@login_required
def print_act(request, recipient_id, year, month):
    """Страница печати акта"""
    user = request.user
    recipient = get_object_or_404(Recipient, id=recipient_id)
    
    # Проверка доступа
    if not user.is_admin_or_hr and user.department != recipient.department:
        return HttpResponse('Нет доступа', status=403)
    
    # Получаем услуги из ИППСУ
    contract_services = ContractService.objects.filter(
        contract__recipient=recipient,
        contract__is_active=True
    ).select_related('service', 'service__category')
    
    # Получаем записи услуг за месяц
    logs = ServiceLog.objects.filter(
        recipient=recipient,
        date__year=year,
        date__month=month
    ).select_related('service')
    
    # Группируем по услугам
    logs_by_service = {}
    for log in logs:
        service_id = log.service_id
        if service_id not in logs_by_service:
            logs_by_service[service_id] = {
                'quantity': Decimal('0'),
                'price': log.price_at_service,
                'total': Decimal('0'),
            }
        logs_by_service[service_id]['quantity'] += log.quantity
        logs_by_service[service_id]['total'] += log.quantity * log.price_at_service
    
    # Формируем данные по услугам из ИППСУ
    services_data = []
    for cs in contract_services:
        service = cs.service
        log_data = logs_by_service.get(service.id, {'quantity': Decimal('0'), 'price': service.price, 'total': Decimal('0')})
        
        services_data.append({
            'service': service,
            'quantity': log_data['quantity'],
            'price': log_data['price'],
            'total': log_data['total'],
        })
    
    services_data = sorted(services_data, key=lambda x: x['service'].code)
    total_sum = sum(item['total'] for item in services_data)
    
    month_names = {
        1: 'Январь', 2: 'Февраль', 3: 'Март', 4: 'Апрель',
        5: 'Май', 6: 'Июнь', 7: 'Июль', 8: 'Август',
        9: 'Сентябрь', 10: 'Октябрь', 11: 'Ноябрь', 12: 'Декабрь'
    }
    
    context = {
        'recipient': recipient,
        'year': year,
        'month': month,
        'month_name': month_names.get(month, ''),
        'services_data': services_data,
        'total_sum': total_sum,
        'today': date.today(),
    }
    
    return render(request, 'reports/act_print.html', context)
