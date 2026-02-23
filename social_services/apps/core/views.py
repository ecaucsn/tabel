from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.db.models import Count, Sum
from django.utils import timezone
from django.views.decorators.http import require_GET
from datetime import date, timedelta
from calendar import month_name

from apps.recipients.models import Recipient
from apps.services.models import ServiceLog, Service, ServiceSchedule
from apps.core.models import Department


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
    
    # Статистика
    stats = {
        'recipients_total': recipients_qs.count(),
        'recipients_active': recipients_qs.filter(
            department__department_type__in=['residential', 'mercy']
        ).count(),
        'services_total': Service.objects.count(),
        'services_this_month': ServiceLog.objects.filter(
            date__year=today.year,
            date__month=today.month
        ).aggregate(total=Sum('quantity'))['total'] or 0,
        'departments': Department.objects.filter(
            department_type__in=['residential', 'mercy']
        ).count(),
    }
    
    # Отделения с количеством проживающих (только реальные отделения)
    departments = Department.objects.filter(
        department_type__in=['residential', 'mercy']
    ).annotate(
        recipient_count=Count('recipients')
    ).all()
    
    # Последние записи в табеле
    recent_logs = ServiceLog.objects.select_related(
        'recipient', 'service'
    ).order_by('-created_at')[:10]
    
    # Название текущего месяца
    current_month_name = month_name[today.month]
    
    context = {
        'stats': stats,
        'departments': departments,
        'recent_logs': recent_logs,
        'current_month_name': current_month_name,
        'user': user,
    }
    
    return render(request, 'core/dashboard.html', context)


@login_required
def departments_view(request):
    """Страница отделений с карточками"""
    user = request.user
    today = date.today()
    
    # Получаем только отделения проживания и милосердия
    departments = Department.objects.filter(
        department_type__in=['residential', 'mercy']
    ).annotate(
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
        
        # Ближайшие мероприятия (услуги по расписанию на ближайшие 7 дней)
        today_weekday = today.weekday()  # 0 = понедельник
        upcoming_services = []
        
        # Получаем расписание услуг для отделения на ближайшие 7 дней
        for days_ahead in range(7):
            check_date = today + timedelta(days=days_ahead)
            check_weekday = check_date.weekday()
            
            # Получаем услуги на этот день недели
            schedules = ServiceSchedule.objects.filter(
                department=dept,
                day_of_week=check_weekday
            ).select_related('service')
            
            for schedule in schedules:
                upcoming_services.append({
                    'date': check_date,
                    'service': schedule.service,
                    'quantity': schedule.quantity,
                    'is_today': days_ahead == 0
                })
        
        departments_data.append({
            'department': dept,
            'recipient_count': recipient_count,
            'capacity': capacity,
            'occupancy': occupancy,
            'upcoming_services': upcoming_services[:5],  # Показываем только первые 5
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
