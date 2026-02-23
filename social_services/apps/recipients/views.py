from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q
from django.db import transaction
from django.utils import timezone
from datetime import date

from apps.recipients.models import Recipient, StatusHistory, PlacementHistory
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
    
    # Фильтрация по типу отделения (вместо статуса)
    dept_type = request.GET.get('dept_type')
    if dept_type:
        recipients = recipients.filter(department__department_type=dept_type)
    
    search = request.GET.get('search')
    
    # Получаем все записи для Python-фильтрации и сортировки
    # (SQLite не поддерживает icontains и Lower() для кириллицы)
    all_recipients = list(recipients.select_related('department'))
    
    if search:
        # Регистронезависимый поиск для кириллицы
        search_lower = search.lower()
        all_recipients = [
            r for r in all_recipients
            if search_lower in (r.last_name or '').lower()
            or search_lower in (r.first_name or '').lower()
            or search_lower in (r.patronymic or '').lower()
        ]
    
    # Сортировка
    sort_field = request.GET.get('sort', 'last_name')  # По умолчанию по фамилии
    sort_direction = request.GET.get('dir', 'asc')  # По умолчанию по возрастанию
    
    # Допустимые поля для сортировки
    valid_sort_fields = ['last_name', 'first_name', 'birth_date', 'department__name', 'room']
    if sort_field not in valid_sort_fields:
        sort_field = 'last_name'
    
    # Регистронезависимая сортировка для текстовых полей (кириллица)
    text_fields = ['last_name', 'first_name', 'department__name', 'room']
    
    def get_sort_key(recipient):
        """Получить ключ сортировки для проживающего"""
        if sort_field == 'department__name':
            value = recipient.department.name if recipient.department else ''
        else:
            value = getattr(recipient, sort_field, '') or ''
        
        # Для текстовых полей - регистронезависимая сортировка
        if sort_field in text_fields:
            return value.lower()
        return value
    
    # Выполняем сортировку
    all_recipients.sort(key=get_sort_key, reverse=(sort_direction == 'desc'))
    
    # Присваиваем обратно переменной recipients для совместимости
    recipients = all_recipients
    
    # Только реальные отделения для выпадающего списка фильтров
    departments = Department.objects.filter(
        department_type__in=['residential', 'mercy']
    )
    
    # Все отделения для модального окна изменения статуса
    all_departments = Department.objects.all()
    
    context = {
        'recipients': recipients,
        'departments': departments,
        'all_departments': all_departments,
        'selected_dept': department_id,
        'selected_dept_type': dept_type,
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
        old_department = recipient.department
        old_room = recipient.room
        old_status = old_department.status_code if old_department else None
        
        recipient.last_name = request.POST.get('last_name', recipient.last_name)
        recipient.first_name = request.POST.get('first_name', recipient.first_name)
        recipient.patronymic = request.POST.get('patronymic', '')
        recipient.birth_date = request.POST.get('birth_date') or recipient.birth_date
        recipient.room = request.POST.get('room', '')
        
        dept_id = request.POST.get('department')
        if dept_id:
            new_department = Department.objects.get(id=dept_id)
            recipient.department = new_department
        else:
            new_department = None
            recipient.department = None
        
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
        
        new_status = recipient.department.status_code if recipient.department else None
        reason = request.POST.get('status_reason', '')
        
        # Используем транзакцию для атомарного обновления
        with transaction.atomic():
            recipient.save()
            
            # Создаем запись в истории статусов если отделение изменилось
            if old_department != recipient.department:
                StatusHistory.objects.create(
                    recipient=recipient,
                    old_department=old_department,
                    new_department=recipient.department,
                    old_status=old_status,
                    new_status=new_status,
                    changed_by=user,
                    reason=reason
                )
            
            # Создаем запись в истории перемещений если отделение или комната изменились
            if old_department != recipient.department or old_room != recipient.room:
                PlacementHistory.objects.create(
                    recipient=recipient,
                    old_department=old_department,
                    new_department=recipient.department,
                    old_room=old_room,
                    new_room=recipient.room,
                    old_status=old_status,
                    new_status=new_status,
                    reason=reason,
                    date=date.today(),
                    changed_by=user
                )
        
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
    
    # История статусов
    status_history = recipient.status_history.all()[:10]
    
    # История перемещений
    placement_history = recipient.placement_history.all()[:10]
    
    # Все отделения для выпадающего списка (включая специальные статусы)
    departments = Department.objects.all()
    
    # Проживающие для переключения
    recipients = Recipient.objects.select_related('department').filter(
        department__department_type__in=['residential', 'mercy', 'hospital', 'vacation']
    )
    
    # Фильтрация по отделению пользователя
    if not user.is_admin_or_hr and user.department:
        recipients = recipients.filter(department=user.department)
    
    context = {
        'recipient': recipient,
        'contracts': contracts,
        'departments': departments,
        'recipients': recipients,
        'stats': {
            'total_services': total_stats['total_services'] or 0,
            'total_amount': total_stats['total_amount'] or 0,
            'current_month_services': current_month_stats['current_month_services'] or 0,
            'current_month_amount': current_month_stats['current_month_amount'] or 0,
        },
        'recent_services': recent_services,
        'status_history': status_history,
        'placement_history': placement_history,
    }
    
    return render(request, 'recipients/recipient_edit.html', context)


@login_required
def recipients_by_department(request, department_id):
    """API: Список проживающих по отделению"""
    user = request.user
    
    # Проверка доступа
    if not user.is_admin_or_hr and user.department_id != department_id:
        return JsonResponse({'error': 'Нет доступа'}, status=403)
    
    # Фильтруем по отделениям проживания (не больница, не отпуск, не умер)
    recipients = Recipient.objects.filter(
        department_id=department_id,
        department__department_type__in=['residential', 'mercy']
    ).values('id', 'last_name', 'first_name', 'patronymic', 'room')
    
    return JsonResponse({
        'recipients': list(recipients)
    })


@login_required
def change_status(request, pk):
    """API: Изменение статуса/размещения проживающего"""
    recipient = get_object_or_404(Recipient, pk=pk)
    user = request.user
    
    # Проверка доступа
    if not user.is_admin_or_hr and user.department != recipient.department:
        return JsonResponse({'error': 'Нет доступа'}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Только POST запросы'}, status=405)
    
    import json
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Неверный формат данных'}, status=400)
    
    old_department = recipient.department
    old_room = recipient.room
    old_status = old_department.status_code if old_department else None
    
    # Получаем новые данные
    new_department_id = data.get('department_id')
    new_room = data.get('room', '')
    reason = data.get('reason', '')
    
    if new_department_id:
        try:
            new_department = Department.objects.get(id=new_department_id)
            recipient.department = new_department
        except Department.DoesNotExist:
            return JsonResponse({'error': 'Отделение не найдено'}, status=400)
    else:
        recipient.department = None
    
    recipient.room = new_room
    
    # Обновляем даты
    admission_date = data.get('admission_date')
    if admission_date:
        recipient.admission_date = admission_date
    
    discharge_date = data.get('discharge_date')
    if discharge_date:
        recipient.discharge_date = discharge_date
    
    new_status = recipient.department.status_code if recipient.department else None
    
    # Используем транзакцию для атомарного обновления
    with transaction.atomic():
        recipient.save()
        
        # Создаем запись в истории статусов если отделение изменилось
        if old_department != recipient.department:
            StatusHistory.objects.create(
                recipient=recipient,
                old_department=old_department,
                new_department=recipient.department,
                old_status=old_status,
                new_status=new_status,
                changed_by=user,
                reason=reason
            )
        
        # Создаем запись в истории перемещений если отделение или комната изменились
        if old_department != recipient.department or old_room != recipient.room:
            PlacementHistory.objects.create(
                recipient=recipient,
                old_department=old_department,
                new_department=recipient.department,
                old_room=old_room,
                new_room=recipient.room,
                old_status=old_status,
                new_status=new_status,
                reason=reason,
                date=date.today(),
                changed_by=user
            )
    
    return JsonResponse({
        'success': True,
        'recipient': {
            'id': recipient.id,
            'department': recipient.department.name if recipient.department else '',
            'room': recipient.room,
            'status': recipient.status,
            'status_display': recipient.status_display
        }
    })


@login_required
def edit_contract(request, pk):
    """Редактирование ИППСУ проживающего"""
    recipient = get_object_or_404(Recipient, pk=pk)
    user = request.user
    
    # Проверка доступа
    if not user.is_admin_or_hr and user.department != recipient.department:
        return HttpResponseForbidden('Нет доступа к данному проживающему')
    
    from apps.recipients.models import Contract, ContractService
    from apps.services.models import Service, ServiceCategory
    
    # Получаем или создаём активный договор
    contract = recipient.contracts.filter(is_active=True).first()
    
    if request.method == 'POST':
        # Обработка сохранения
        with transaction.atomic():
            if not contract:
                # Создаём новый договор
                contract = Contract.objects.create(
                    recipient=recipient,
                    number=f"ИППСУ-{recipient.id}-{date.today().year}",
                    date_start=date.today(),
                    is_active=True
                )
            
            # Получаем выбранные услуги
            selected_services = request.POST.getlist('services')
            
            # Удаляем услуги, которые не выбраны
            ContractService.objects.filter(contract=contract).exclude(
                service_id__in=selected_services
            ).delete()
            
            # Добавляем новые услуги
            existing_services = set(ContractService.objects.filter(
                contract=contract
            ).values_list('service_id', flat=True))
            
            for service_id in selected_services:
                if int(service_id) not in existing_services:
                    ContractService.objects.create(
                        contract=contract,
                        service_id=service_id
                    )
            
            # Обновляем номер и даты договора
            contract.number = request.POST.get('number', contract.number)
            contract.date_start = request.POST.get('date_start') or contract.date_start
            contract.date_end = request.POST.get('date_end') or None
            contract.save()
        
        return redirect('recipients:contract', pk=recipient.id)
    
    # Получаем все активные услуги, сгруппированные по категориям
    categories = ServiceCategory.objects.prefetch_related(
        'services'
    ).filter(services__is_active=True).distinct()
    
    # Получаем ID выбранных услуг
    selected_service_ids = []
    if contract:
        selected_service_ids = list(contract.services.values_list('service_id', flat=True))
    
    # Отделения для фильтра
    departments = Department.objects.filter(
        department_type__in=['residential', 'mercy']
    )
    
    # Проживающие для переключения
    recipients = Recipient.objects.select_related('department').filter(
        department__department_type__in=['residential', 'mercy', 'hospital', 'vacation']
    )
    
    # Фильтрация по отделению пользователя
    if not user.is_admin_or_hr and user.department:
        recipients = recipients.filter(department=user.department)
    
    context = {
        'recipient': recipient,
        'contract': contract,
        'categories': categories,
        'selected_service_ids': selected_service_ids,
        'departments': departments,
        'recipients': recipients,
    }
    
    return render(request, 'recipients/contract_edit.html', context)


@login_required
def contract_list(request):
    """Страница выбора проживающего для редактирования ИППСУ"""
    user = request.user
    
    # Получаем параметры фильтрации
    department_id = request.GET.get('department')
    recipient_id = request.GET.get('recipient')
    
    # Если выбран проживающий - перенаправляем на страницу редактирования
    if recipient_id:
        return redirect('recipients:contract', pk=recipient_id)
    
    # Отделения для фильтра
    departments = Department.objects.filter(
        department_type__in=['residential', 'mercy']
    )
    
    # Проживающие
    recipients = Recipient.objects.select_related('department').all()
    
    # Фильтрация по отделению
    if not user.is_admin_or_hr and user.department:
        recipients = recipients.filter(department=user.department)
    
    if department_id:
        recipients = recipients.filter(department_id=department_id)
    
    # Фильтруем только проживающих (не выбывших)
    recipients = recipients.filter(
        department__department_type__in=['residential', 'mercy', 'hospital', 'vacation']
    )
    
    context = {
        'departments': departments,
        'recipients': recipients,
        'selected_department': department_id,
    }
    
    return render(request, 'recipients/contract_select.html', context)


@login_required
def lists_page(request):
    """Страница генерации различных списков"""
    return render(request, 'recipients/lists.html')


@login_required
def jubilees_list(request):
    """Список юбиляров"""
    user = request.user
    
    # Получаем параметры месяца и года
    month = request.GET.get('month')
    year = request.GET.get('year')
    
    jubilees = []
    
    if month and year:
        month = int(month)
        year = int(year)
        
        # Получаем всех проживающих
        recipients = Recipient.objects.select_related('department').filter(
            department__department_type__in=['residential', 'mercy']
        )
        
        # Фильтрация по отделению пользователя
        if not user.is_admin_or_hr and user.department:
            recipients = recipients.filter(department=user.department)
        
        # Находим юбиляров (возраст кратен 5 или 10)
        for recipient in recipients:
            if recipient.birth_date:
                # Вычисляем возраст на указанный месяц/год
                birth_day = recipient.birth_date.day
                birth_month = recipient.birth_date.month
                birth_year = recipient.birth_date.year
                
                # Возраст в году рождения юбилея
                age = year - birth_year
                
                # Проверяем, что месяц рождения совпадает
                if birth_month == month:
                    # Проверяем, что возраст кратен 5 (юбилей)
                    if age > 0 and age % 5 == 0:
                        jubilees.append({
                            'recipient': recipient,
                            'birth_date': recipient.birth_date,
                            'age': age,
                            'department': recipient.department,
                            'room': recipient.room,
                        })
        
        # Сортируем по дате рождения
        jubilees.sort(key=lambda x: x['birth_date'].day)
    
    # Месяцы для выбора
    months = [
        (1, 'Январь'),
        (2, 'Февраль'),
        (3, 'Март'),
        (4, 'Апрель'),
        (5, 'Май'),
        (6, 'Июнь'),
        (7, 'Июль'),
        (8, 'Август'),
        (9, 'Сентябрь'),
        (10, 'Октябрь'),
        (11, 'Ноябрь'),
        (12, 'Декабрь'),
    ]
    
    # Название выбранного месяца
    month_name = ''
    if month:
        month_name = dict(months).get(int(month), '')
    
    # Года для выбора (текущий и следующие 2 года)
    import datetime
    current_year = datetime.date.today().year
    years = list(range(current_year, current_year + 3))
    
    context = {
        'jubilees': jubilees,
        'months': months,
        'month_name': month_name,
        'years': years,
        'selected_month': month,
        'selected_year': year,
    }
    
    return render(request, 'recipients/jubilees.html', context)


@login_required
def residents_list_page(request):
    """Страница выбора отделения для печати списка проживающих"""
    user = request.user
    
    # Получаем отделения
    departments = Department.objects.filter(
        department_type__in=['residential', 'mercy']
    ).annotate(
        recipient_count=Count('recipients')
    ).all()
    
    context = {
        'departments': departments,
    }
    
    return render(request, 'recipients/residents_list_select.html', context)


@login_required
def residents_list_print(request):
    """Печать списка проживающих по отделениям"""
    user = request.user
    today = date.today()
    
    # Получаем выбранные отделения
    department_ids = request.GET.getlist('departments')
    
    # Получаем режим отображения
    view_mode = request.GET.get('mode', 'grouped')
    
    if department_ids and 'all' not in department_ids:
        departments = Department.objects.filter(
            id__in=department_ids,
            department_type__in=['residential', 'mercy']
        )
    else:
        # Все отделения
        departments = Department.objects.filter(
            department_type__in=['residential', 'mercy']
        )
    
    # Собираем данные по отделениям
    departments_data = []
    total_recipients = 0
    
    for dept in departments:
        recipients = Recipient.objects.filter(
            department=dept
        ).select_related('department').order_by('room', 'last_name', 'first_name')
        
        # Группируем по комнатам
        rooms_data = {}
        for recipient in recipients:
            room = recipient.room or 'Без комнаты'
            if room not in rooms_data:
                rooms_data[room] = []
            rooms_data[room].append(recipient)
        
        # Сортируем комнаты
        def room_sort_key(room):
            if room == 'Без комнаты':
                return (1, 0)
            try:
                return (0, int(room))
            except (ValueError, TypeError):
                return (0, 0)
        
        sorted_rooms = sorted(rooms_data.items(), key=lambda x: room_sort_key(x[0]))
        
        # Общий список
        all_recipients = list(recipients.order_by('last_name', 'first_name', 'patronymic'))
        
        departments_data.append({
            'department': dept,
            'rooms_data': sorted_rooms,
            'all_recipients': all_recipients,
            'recipient_count': recipients.count(),
        })
        
        total_recipients += recipients.count()
    
    context = {
        'departments_data': departments_data,
        'total_recipients': total_recipients,
        'today': today,
        'is_all': 'all' in department_ids or not department_ids,
        'view_mode': view_mode,
    }
    
    return render(request, 'recipients/residents_list_print.html', context)
