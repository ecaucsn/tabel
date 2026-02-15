from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count
from django.utils import timezone
from datetime import date

from apps.recipients.models import Recipient
from apps.core.models import Department
from apps.services.models import ServiceLog


@login_required
def recipient_list(request):
    """Список проживающих"""
    user = request.user
    
    # Сбрасываем дефолтную сортировку из модели
    recipients = Recipient.objects.select_related('department').all().order_by()
    
    # Фильтрация по отделению
    if not user.is_admin_or_hr and user.department:
        recipients = recipients.filter(department=user.department)
    
    department_id = request.GET.get('department')
    if department_id:
        recipients = recipients.filter(department_id=department_id)
    
    status = request.GET.get('status')
    if status:
        recipients = recipients.filter(status=status)
    
    search = request.GET.get('search')
    if search:
        recipients = recipients.filter(
            last_name__icontains=search
        ) | recipients.filter(
            first_name__icontains=search
        ) | recipients.filter(
            patronymic__icontains=search
        )
    
    # Сортировка
    sort_field = request.GET.get('sort', 'last_name')  # По умолчанию по фамилии
    sort_direction = request.GET.get('dir', 'asc')  # По умолчанию по возрастанию
    
    # Допустимые поля для сортировки
    valid_sort_fields = ['last_name', 'first_name', 'birth_date', 'department__name', 'status', 'room']
    if sort_field not in valid_sort_fields:
        sort_field = 'last_name'
    
    # Применяем направление сортировки
    if sort_direction == 'desc':
        sort_field = f'-{sort_field}'
    
    recipients = recipients.order_by(sort_field)
    
    departments = Department.objects.all()
    
    context = {
        'recipients': recipients,
        'departments': departments,
        'selected_dept': department_id,
        'selected_status': status,
        'search_query': search or '',
        'sort_field': request.GET.get('sort', 'last_name'),
        'sort_direction': sort_direction,
    }
    
    return render(request, 'recipients/recipient_list.html', context)


@login_required
def recipient_detail(request, pk):
    """Детальная информация о проживающем и редактирование"""
    recipient = get_object_or_404(Recipient, pk=pk)
    
    # Проверка доступа
    user = request.user
    if not user.is_admin_or_hr and user.department != recipient.department:
        return HttpResponseForbidden('Нет доступа к данному проживающему')
    
    # Обработка POST запроса - сохранение изменений
    if request.method == 'POST':
        recipient.last_name = request.POST.get('last_name', recipient.last_name)
        recipient.first_name = request.POST.get('first_name', recipient.first_name)
        recipient.patronymic = request.POST.get('patronymic', '')
        recipient.birth_date = request.POST.get('birth_date') or recipient.birth_date
        recipient.room = request.POST.get('room', '')
        recipient.status = request.POST.get('status', 'active')
        
        dept_id = request.POST.get('department')
        if dept_id:
            recipient.department_id = dept_id
        
        admission_date = request.POST.get('admission_date')
        if admission_date:
            recipient.admission_date = admission_date
        else:
            recipient.admission_date = None
            
        discharge_date = request.POST.get('discharge_date')
        if discharge_date:
            recipient.discharge_date = discharge_date
        else:
            recipient.discharge_date = None
        
        # Обработка фото
        if request.FILES.get('photo'):
            recipient.photo = request.FILES['photo']
        
        recipient.save()
        return redirect('recipients:detail', pk=recipient.id)
    
    # Получение договоров
    contracts = recipient.contracts.prefetch_related('services__service').all()
    
    # Статистика услуг
    today = date.today()
    current_month_start = date(today.year, today.month, 1)
    
    service_logs = ServiceLog.objects.filter(recipient=recipient)
    
    # Общая статистика
    total_stats = service_logs.aggregate(
        total_services=Sum('quantity'),
        total_amount=Sum('price_at_service')
    )
    
    # Статистика за текущий месяц
    current_month_stats = service_logs.filter(
        date__gte=current_month_start,
        date__lte=today
    ).aggregate(
        current_month_services=Sum('quantity'),
        current_month_amount=Sum('price_at_service')
    )
    
    # Последние оказанные услуги
    recent_services = service_logs.select_related('service').order_by('-date')[:5]
    
    departments = Department.objects.all()
    
    context = {
        'recipient': recipient,
        'contracts': contracts,
        'departments': departments,
        'stats': {
            'total_services': total_stats['total_services'] or 0,
            'total_amount': total_stats['total_amount'] or 0,
            'current_month_services': current_month_stats['current_month_services'] or 0,
            'current_month_amount': current_month_stats['current_month_amount'] or 0,
        },
        'recent_services': recent_services,
    }
    
    return render(request, 'recipients/recipient_edit.html', context)


@login_required
def recipients_by_department(request, department_id):
    """API: Список проживающих по отделению"""
    user = request.user
    
    # Проверка доступа
    if not user.is_admin_or_hr and user.department_id != department_id:
        return JsonResponse({'error': 'Нет доступа'}, status=403)
    
    recipients = Recipient.objects.filter(
        department_id=department_id,
        status='active'
    ).values('id', 'last_name', 'first_name', 'patronymic', 'room')
    
    return JsonResponse({
        'recipients': list(recipients)
    })
