from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.db.models import Count, Sum
from django.utils import timezone
from django.views.decorators.http import require_GET
from datetime import date
from calendar import month_name

from apps.recipients.models import Recipient
from apps.services.models import ServiceLog, Service
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
        'recipients_active': recipients_qs.filter(status='active').count(),
        'services_total': Service.objects.count(),
        'services_this_month': ServiceLog.objects.filter(
            date__year=today.year,
            date__month=today.month
        ).aggregate(total=Sum('quantity'))['total'] or 0,
        'departments': Department.objects.count(),
    }
    
    # Отделения с количеством проживающих
    departments = Department.objects.annotate(
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
