from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.db.models import Count, Sum, DecimalField, Q
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.views.decorators.http import require_GET
from datetime import date, timedelta
from calendar import month_name
from decimal import Decimal

from apps.recipients.models import Recipient, RecipientHistory


def declension_years(age):
    """Склонение слова 'год' в зависимости от возраста"""
    if age % 100 in range(11, 20):
        return f"{age} лет"
    if age % 10 == 1:
        return f"{age} год"
    if age % 10 in range(2, 5):
        return f"{age} года"
    return f"{age} лет"
from apps.services.models import ServiceLog, Service, ServiceSchedule
from apps.core.models import Department
from apps.modules.models import MonthlyRequest, PensionAccount, PensionAccrual, PensionExpense, DigitalProfile


@require_GET
def logout_view(request):
    """Выход из системы"""
    logout(request)
    return redirect('login')


@login_required
def dashboard(request):
    """Главная страница дашборда"""
    user = request.user
    today = date.today()
    
    # Базовый queryset для проживающих
    recipients_qs = Recipient.objects.all()
    
    # Фильтрация по отделению для медиков/специалистов
    if not user.is_admin_or_hr and user.department:
        recipients_qs = recipients_qs.filter(department=user.department)
    
    # Статистика по проживающим
    recipients_total = recipients_qs.count()
    recipients_active = recipients_qs.filter(
        placement='internat'
    ).count()
    
    # Статистика по услугам
    services_total = Service.objects.filter(is_active=True).count()
    services_this_month = ServiceLog.objects.filter(
        date__year=today.year,
        date__month=today.month
    ).aggregate(total=Sum('quantity'))['total'] or 0
    
    # Сумма услуг за месяц в рублях
    services_amount_month = ServiceLog.objects.filter(
        date__year=today.year,
        date__month=today.month
    ).aggregate(
        total=Sum('quantity') * Sum('price_at_service')
    )['total'] or Decimal('0')
    
    # Подсчитаем сумму более точно
    from django.db.models import F
    services_amount_month = ServiceLog.objects.filter(
        date__year=today.year,
        date__month=today.month
    ).aggregate(
        total=Sum(F('quantity') * F('price_at_service'), output_field=DecimalField())
    )['total'] or Decimal('0')
    
    # Статистика по отделениям
    departments_count = Department.objects.count()
    
    # Статистика по заявкам на паёк
    food_requests_month = MonthlyRequest.objects.filter(
        year=today.year,
        month=today.month
    ).count()
    
    food_requests_pending = MonthlyRequest.objects.filter(
        year=today.year,
        month=today.month,
        status__in=['draft', 'submitted']
    ).count()
    
    food_requests_amount = MonthlyRequest.objects.filter(
        year=today.year,
        month=today.month
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
    
    # Статистика по пенсиям
    pension_accounts_total = PensionAccount.objects.count()
    
    pension_accruals_month = PensionAccrual.objects.filter(
        year=today.year,
        month=today.month
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    
    pension_expenses_month = PensionExpense.objects.filter(
        year=today.year,
        month=today.month
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    
    # Общий баланс пенсионных счетов
    pension_total_balance = PensionAccount.objects.aggregate(
        total=Sum('balance')
    )['total'] or Decimal('0')
    
    # Цифровые профили
    digital_profiles_total = DigitalProfile.objects.count()
    digital_profiles_public = DigitalProfile.objects.filter(is_public=True).count()
    
    # Юбилеи месяца (именинники)
    jubilees_this_month = recipients_qs.filter(
        birth_date__month=today.month
    ).order_by('birth_date__day')
    
    # Юбилеи года (80+, 85+, 90+ лет)
    jubilee_ages = []
    for recipient in recipients_qs.filter(
        placement='internat'
    ):
        age = recipient.age
        if age and age >= 80 and age % 5 == 0:  # 80, 85, 90, 95, 100
            jubilee_ages.append({
                'recipient': recipient,
                'age': age,
                'birth_date': recipient.birth_date
            })
    jubilee_ages = sorted(jubilee_ages, key=lambda x: x['birth_date'].month if x['birth_date'] else 0)[:10]
    
    # Основная статистика
    stats = {
        'recipients_total': recipients_total,
        'recipients_active': recipients_active,
        'services_total': services_total,
        'services_this_month': services_this_month,
        'services_amount_month': services_amount_month,
        'departments': departments_count,
        'food_requests_month': food_requests_month,
        'food_requests_pending': food_requests_pending,
        'food_requests_amount': food_requests_amount,
        'pension_accounts_total': pension_accounts_total,
        'pension_accruals_month': pension_accruals_month,
        'pension_expenses_month': pension_expenses_month,
        'pension_total_balance': pension_total_balance,
        'digital_profiles_total': digital_profiles_total,
        'digital_profiles_public': digital_profiles_public,
    }
    
    # Отделения с количеством проживающих
    departments = Department.objects.annotate(
        recipient_count=Count('recipients')
    ).all()
    
    # Последние записи в табеле
    recent_logs = ServiceLog.objects.select_related(
        'recipient', 'service'
    ).order_by('-created_at')[:10]
    
    # Последние заявки на паёк
    recent_food_requests = MonthlyRequest.objects.select_related(
        'recipient', 'recipient__department'
    ).order_by('-updated_at')[:5]
    
    # Последние операции с пенсиями
    recent_pension_operations = []
    recent_accruals = PensionAccrual.objects.select_related(
        'account', 'account__recipient'
    ).order_by('-created_at')[:3]
    recent_expenses = PensionExpense.objects.select_related(
        'account', 'account__recipient'
    ).order_by('-created_at')[:3]
    
    for accrual in recent_accruals:
        recent_pension_operations.append({
            'type': 'accrual',
            'date': accrual.created_at,
            'recipient': accrual.account.recipient,
            'amount': accrual.amount,
            'description': f"Начисление за {accrual.month_name} {accrual.year}"
        })
    
    for expense in recent_expenses:
        recent_pension_operations.append({
            'type': 'expense',
            'date': expense.created_at,
            'recipient': expense.account.recipient,
            'amount': expense.amount,
            'description': expense.get_category_display() or expense.description
        })
    
    # Сортируем по дате
    recent_pension_operations.sort(key=lambda x: x['date'], reverse=True)
    recent_pension_operations = recent_pension_operations[:5]
    
    # Последние изменения статусов и перемещений
    recent_history = RecipientHistory.objects.select_related(
        'recipient', 'old_department', 'new_department', 'changed_by'
    ).order_by('-date', '-created_at')[:10]
    
    # Название текущего месяца
    current_month_name = month_name[today.month]
    
    # Месяцы на русском
    months_ru = {
        1: 'Январь', 2: 'Февраль', 3: 'Март', 4: 'Апрель',
        5: 'Май', 6: 'Июнь', 7: 'Июль', 8: 'Август',
        9: 'Сентябрь', 10: 'Октябрь', 11: 'Ноябрь', 12: 'Декабрь'
    }
    current_month_name_ru = months_ru[today.month]
    
    context = {
        'stats': stats,
        'departments': departments,
        'recent_logs': recent_logs,
        'recent_food_requests': recent_food_requests,
        'recent_history': recent_history,
        'jubilees_this_month': jubilees_this_month,
        'jubilee_ages': jubilee_ages,
        'current_month_name': current_month_name,
        'current_month_name_ru': current_month_name_ru,
        'user': user,
        'today': today,
    }
    
    return render(request, 'core/dashboard.html', context)


@login_required
def departments_view(request):
    """Страница отделений с карточками"""
    user = request.user
    today = date.today()
    
    # Получаем все отделения
    departments = Department.objects.annotate(
        recipient_count=Count('recipients')
    ).all()
    
    # Для каждого отделения получаем дополнительную информацию
    departments_data = []
    total_recipients = 0
    total_capacity = 0
    
    for dept in departments:
        # Количество проживающих
        recipient_count = dept.recipient_count
        total_recipients += recipient_count
        
        # Количество мест (capacity)
        capacity = dept.capacity
        total_capacity += capacity
        
        # Заполненность в процентах
        occupancy = 0
        if capacity > 0:
            occupancy = round((recipient_count / capacity) * 100, 1)
        
        # Ближайшие именинники (дни рождения в ближайшие 30 дней)
        upcoming_birthdays = []
        
        # Получаем всех проживающих отделения
        recipients = Recipient.objects.filter(department=dept, placement='internat')
        
        for recipient in recipients:
            if recipient.birth_date:
                try:
                    # День рождения в этом году
                    birthday_this_year = date(today.year, recipient.birth_date.month, recipient.birth_date.day)
                    
                    # Если день рождения уже прошёл в этом году, проверяем следующий год
                    if birthday_this_year < today:
                        birthday_this_year = date(today.year + 1, recipient.birth_date.month, recipient.birth_date.day)
                    
                    # Считаем дней до дня рождения
                    days_until = (birthday_this_year - today).days
                    
                    # Если день рождения в ближайшие 30 дней
                    if 0 <= days_until <= 30:
                        age = today.year - recipient.birth_date.year
                        upcoming_birthdays.append({
                            'recipient': recipient,
                            'birth_date': birthday_this_year,
                            'days_until': days_until,
                            'age': declension_years(age)
                        })
                except ValueError:
                    # Некорректная дата (например, 30 февраля) - пропускаем
                    continue
        
        # Сортируем по количеству дней до дня рождения
        upcoming_birthdays.sort(key=lambda x: x['days_until'])
        
        departments_data.append({
            'department': dept,
            'recipient_count': recipient_count,
            'capacity': capacity,
            'occupancy': occupancy,
            'upcoming_birthdays': upcoming_birthdays[:3],  # Показываем только первых 3
        })
    
    # Общая заполненность учреждения
    total_occupancy = 0
    if total_capacity > 0:
        total_occupancy = round((total_recipients / total_capacity) * 100, 1)
    
    context = {
        'departments_data': departments_data,
        'user': user,
        'today': today,
        'total_recipients': total_recipients,
        'total_capacity': total_capacity,
        'total_occupancy': total_occupancy,
    }
    
    return render(request, 'core/departments.html', context)


@login_required
def department_residents_print(request, department_id):
    """Печать списка проживающих отделения с группировкой по комнатам"""
    user = request.user
    today = date.today()
    
    # Получаем отделение
    department = get_object_or_404(Department, id=department_id)
    
    # Получаем проживающих отделения
    recipients = Recipient.objects.filter(
        department=department
    ).select_related('department').order_by('room', 'last_name', 'first_name')
    
    # Группируем по комнатам
    rooms_data = {}
    for recipient in recipients:
        room = recipient.room or 'Без комнаты'
        if room not in rooms_data:
            rooms_data[room] = []
        rooms_data[room].append(recipient)
    
    # Сортируем комнаты (числовая сортировка если возможно)
    def room_sort_key(room):
        if room == 'Без комнаты':
            return (1, 0)  # В конце списка
        try:
            return (0, int(room))
        except (ValueError, TypeError):
            return (0, 0)
    
    sorted_rooms = sorted(rooms_data.items(), key=lambda x: room_sort_key(x[0]))
    
    # Общий список (отсортированный по ФИО)
    all_recipients = list(recipients.order_by('last_name', 'first_name', 'patronymic'))
    
    context = {
        'department': department,
        'rooms_data': sorted_rooms,
        'all_recipients': all_recipients,
        'total_recipients': recipients.count(),
        'today': today,
        'user': user,
    }
    
    return render(request, 'core/department_residents_print.html', context)


@login_required
def department_residents_print_only(request, department_id):
    """Только форма для печати списка проживающих (открывается в новом окне)"""
    today = date.today()
    
    # Получаем отделение
    department = get_object_or_404(Department, id=department_id)
    
    # Получаем режим отображения из параметров
    view_mode = request.GET.get('mode', 'grouped')
    
    # Получаем проживающих отделения
    recipients = Recipient.objects.filter(
        department=department
    ).select_related('department').order_by('room', 'last_name', 'first_name')
    
    # Группируем по комнатам
    rooms_data = {}
    for recipient in recipients:
        room = recipient.room or 'Без комнаты'
        if room not in rooms_data:
            rooms_data[room] = []
        rooms_data[room].append(recipient)
    
    # Сортируем комнаты (числовая сортировка если возможно)
    def room_sort_key(room):
        if room == 'Без комнаты':
            return (1, 0)  # В конце списка
        try:
            return (0, int(room))
        except (ValueError, TypeError):
            return (0, 0)
    
    sorted_rooms = sorted(rooms_data.items(), key=lambda x: room_sort_key(x[0]))
    
    # Общий список (отсортированный по ФИО)
    all_recipients = list(recipients.order_by('last_name', 'first_name', 'patronymic'))
    
    context = {
        'department': department,
        'rooms_data': sorted_rooms,
        'all_recipients': all_recipients,
        'total_recipients': recipients.count(),
        'today': today,
        'view_mode': view_mode,
    }
    
    return render(request, 'core/department_residents_print_only.html', context)


# =====================
# Исполнители (Организации и Сотрудники)
# =====================

from apps.core.models import Organization, Employee


@login_required
def organization_list(request):
    """Список организаций-исполнителей"""
    organizations = Organization.objects.all()
    
    # Фильтрация
    search = request.GET.get('search', '')
    if search:
        organizations = organizations.filter(
            Q(name__icontains=search) |
            Q(short_name__icontains=search) |
            Q(inn__icontains=search)
        )
    
    is_active = request.GET.get('is_active', '')
    if is_active:
        organizations = organizations.filter(is_active=is_active == 'true')
    
    # Подсчёт сотрудников для каждой организации
    organizations = organizations.annotate(
        employee_count=Count('employees')
    )
    
    context = {
        'organizations': organizations,
        'search': search,
        'is_active': is_active,
    }
    
    return render(request, 'core/organization_list.html', context)


@login_required
def organization_detail(request, pk):
    """Детальная информация об организации"""
    organization = get_object_or_404(Organization, pk=pk)
    employees = organization.employees.all()
    
    context = {
        'organization': organization,
        'employees': employees,
    }
    
    return render(request, 'core/organization_detail.html', context)


@login_required
def employee_list(request):
    """Список сотрудников-исполнителей"""
    employees = Employee.objects.select_related('organization', 'user').all()
    
    # Фильтрация
    search = request.GET.get('search', '')
    if search:
        employees = employees.filter(
            Q(last_name__icontains=search) |
            Q(first_name__icontains=search) |
            Q(patronymic__icontains=search) |
            Q(position__icontains=search)
        )
    
    organization_id = request.GET.get('organization', '')
    if organization_id:
        employees = employees.filter(organization_id=organization_id)
    
    is_active = request.GET.get('is_active', '')
    if is_active:
        employees = employees.filter(is_active=is_active == 'true')
    
    organizations = Organization.objects.filter(is_active=True)
    
    context = {
        'employees': employees,
        'organizations': organizations,
        'search': search,
        'organization_id': organization_id,
        'is_active': is_active,
    }
    
    return render(request, 'core/employee_list.html', context)


@login_required
def employee_detail(request, pk):
    """Детальная информация о сотруднике"""
    employee = get_object_or_404(Employee, pk=pk)
    
    context = {
        'employee': employee,
    }
    
    return render(request, 'core/employee_detail.html', context)
