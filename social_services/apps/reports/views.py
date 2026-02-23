import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from calendar import monthrange

from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.template.loader import render_to_string
from django.utils import timezone

from apps.recipients.models import Recipient, ContractService, MonthlyRecipientData
from apps.services.models import ServiceLog, Service, ServiceCategory
from apps.core.models import Department

logger = logging.getLogger(__name__)


def update_monthly_data(monthly_data, income, pension_payment):
    """Обновляет месячные данные получателя.
    
    Args:
        monthly_data: Объект MonthlyRecipientData
        income: Строковое значение дохода (может быть пустым)
        pension_payment: Строковое значение пенсии (может быть пустым)
    
    Returns:
        bool: True если данные были обновлены
    """
    updated = False
    
    if income:
        try:
            monthly_data.income = Decimal(income.replace(',', '.'))
            updated = True
        except (ValueError, InvalidOperation) as e:
            logger.warning(f"Invalid income value '{income}': {e}")
    
    if pension_payment:
        try:
            monthly_data.pension_payment = Decimal(pension_payment.replace(',', '.'))
            updated = True
        except (ValueError, InvalidOperation) as e:
            logger.warning(f"Invalid pension_payment value '{pension_payment}': {e}")
    
    if updated:
        monthly_data.save()
    
    return updated


@login_required
def act_generator(request):
    """Страница генерации актов - подобно странице табеля"""
    user = request.user
    
    # Получаем параметры
    year = int(request.GET.get('year', timezone.now().year))
    month = int(request.GET.get('month', timezone.now().month))
    department_id = request.GET.get('department', '')
    recipient_id = request.GET.get('recipient', '')
    income = request.GET.get('income', '')
    pension_payment = request.GET.get('pension', '')
    
    # Отделения (только реальные, без специальных)
    departments = Department.objects.filter(
        department_type__in=['residential', 'mercy']
    )
    if not user.is_admin_or_hr and user.department:
        departments = departments.filter(id=user.department.id)
    
    # Проживающие (только активные - в отделениях проживания)
    recipients = Recipient.objects.filter(
        department__department_type__in=['residential', 'mercy']
    )
    if department_id:
        recipients = recipients.filter(department_id=department_id)
    if not user.is_admin_or_hr and user.department:
        recipients = recipients.filter(department=user.department)
    
    selected_recipient = None
    services_data = []
    categories_with_services = []
    total_sum = Decimal('0')
    
    # Вычисляемые значения
    income_value = Decimal('0')
    limit_75 = Decimal('0')
    pension_value = Decimal('0')
    difference = Decimal('0')
    monthly_data = None
    
    if recipient_id:
        selected_recipient = recipients.filter(id=recipient_id).first()
        
        if selected_recipient:
            # Получаем или создаём запись месячных данных
            monthly_data, created = MonthlyRecipientData.objects.get_or_create(
                recipient=selected_recipient,
                year=year,
                month=month,
                defaults={'income': None, 'pension_payment': None}
            )
            
            # Сохраняем значения income и pension_payment, если они переданы
            update_monthly_data(monthly_data, income, pension_payment)
        
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
                    'max_quantity': service.max_quantity_per_month,
                })
            
            # Функция для сортировки по коду услуги
            def sort_key(item):
                code = item['service'].code
                parts = code.split('.')
                result = []
                for part in parts:
                    num = ''.join(filter(str.isdigit, part))
                    result.append(int(num) if num else 0)
                return result
            
            # Группируем услуги по категориям (как в печатной форме)
            categories = ServiceCategory.objects.all().order_by('order')
            
            for category in categories:
                # Фильтруем услуги по категории
                category_services = [item for item in services_data if item['service'].category_id == category.id]
                if category_services:
                    # Сортируем услуги внутри категории по коду
                    category_services.sort(key=sort_key)
                    categories_with_services.append({
                        'category': category,
                        'services': category_services
                    })
            
            # Присваиваем сквозную нумерацию
            row_number = 0
            for cat_item in categories_with_services:
                for item in cat_item['services']:
                    row_number += 1
                    item['row_number'] = row_number
            
            # Итоговая сумма
            total_sum = sum(item['total'] for item in services_data)
            
            # Для отображения используем значения из месячных данных
            income_value = monthly_data.income or Decimal('0')
            limit_75 = income_value * Decimal('0.75')
            pension_value = monthly_data.pension_payment or Decimal('0')
            difference = pension_value - total_sum
    
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
        'monthly_data': monthly_data if selected_recipient else None,
        'services_data': services_data,
        'categories_with_services': categories_with_services,
        'total_sum': total_sum,
        'month_name': month_names.get(month - 1, ''),
        'income': income,
        'pension_payment': pension_payment,
        'income_value': income_value,
        'limit_75': limit_75,
        'pension_value': pension_value,
        'difference': difference,
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
    from apps.services.models import ServiceCategory
    
    user = request.user
    recipient = get_object_or_404(Recipient, id=recipient_id)
    
    # Получаем параметр income из GET-запроса
    income = request.GET.get('income', '')
    pension_payment = request.GET.get('pension', '')
    
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
    
    # Функция для сортировки по коду услуги
    def sort_key(item):
        code = item['service'].code
        parts = code.split('.')
        result = []
        for part in parts:
            num = ''.join(filter(str.isdigit, part))
            result.append(int(num) if num else 0)
        return result
    
    # Группируем услуги по категориям (как в табеле)
    categories_with_services = []
    categories = ServiceCategory.objects.all().order_by('order')
    
    for category in categories:
        # Фильтруем услуги по категории
        category_services = [item for item in services_data if item['service'].category_id == category.id]
        if category_services:
            # Сортируем услуги внутри категории по коду
            category_services.sort(key=sort_key)
            categories_with_services.append({
                'category': category,
                'services': category_services
            })
    
    # Присваиваем сквозную нумерацию
    row_number = 0
    for cat_item in categories_with_services:
        for item in cat_item['services']:
            row_number += 1
            item['row_number'] = row_number
    
    total_sum = sum(item['total'] for item in services_data)
    
    # Получаем месячные данные
    monthly_data, created = MonthlyRecipientData.objects.get_or_create(
        recipient=recipient,
        year=year,
        month=month,
        defaults={'income': None, 'pension_payment': None}
    )
    
    # Если переданы GET-параметры, обновляем значения
    update_monthly_data(monthly_data, income, pension_payment)
    
    # Вычисляем значения для таблицы из месячных данных
    income_value = monthly_data.income or Decimal('0')
    limit_75 = income_value * Decimal('0.75')
    pension_value = monthly_data.pension_payment or Decimal('0')
    difference = pension_value - total_sum  # Переплата/недоплата
    
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
        'categories_with_services': categories_with_services,
        'total_sum': total_sum,
        'today': date.today(),
        'income': income_value,
        'limit_75': limit_75,
        'pension_payment': pension_value,
        'difference': difference,
    }
    
    return render(request, 'reports/act_print.html', context)
