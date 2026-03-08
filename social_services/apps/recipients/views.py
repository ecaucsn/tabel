from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q
from django.db import transaction
from django.utils import timezone
from datetime import date

from apps.recipients.models import Recipient, RecipientHistory
from apps.core.models import Department
from apps.services.models import ServiceLog


from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

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
    
    # Оптимизация: загружаем актуальные записи истории одним запросом
    # Получаем ID всех проживающих
    recipient_ids = [r.id for r in all_recipients]
    
    # Получаем последние записи истории для каждого проживающего
    # Используем подзапрос для получения максимальной даты
    from django.db.models import Max, OuterRef, Subquery
    
    # Получаем все записи истории с максимальной датой для каждого получателя
    latest_history = {}
    history_records = RecipientHistory.objects.filter(
        recipient_id__in=recipient_ids,
        date__lte=date.today()
    ).select_related('new_department', 'old_department').order_by('recipient_id', '-date')
    
    # Берём только последнюю запись для каждого получателя
    seen_recipients = set()
    for h in history_records:
        if h.recipient_id not in seen_recipients:
            latest_history[h.recipient_id] = h
            seen_recipients.add(h.recipient_id)
    
    # Добавляем актуальные данные к каждому проживающему
    for r in all_recipients:
        h = latest_history.get(r.id)
        if h:
            # Используем new_placement как основной источник статуса
            r.current_placement = h.new_placement if h.new_placement else r.placement
            r.current_department = h.new_department if h.new_department else r.department
            r.current_room = h.new_room if h.new_room else r.room
        else:
            r.current_placement = r.placement
            r.current_department = r.department
            r.current_room = r.room
        # Для совместимости со старым кодом
        r.current_status = r.current_placement
    
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
    
    # Пагинация - 50 проживающих на страницу
    paginator = Paginator(all_recipients, 50)
    page = request.GET.get('page', 1)
    
    try:
        recipients_page = paginator.page(page)
    except PageNotAnInteger:
        recipients_page = paginator.page(1)
    except EmptyPage:
        recipients_page = paginator.page(paginator.num_pages)
    
    # Все отделения для выпадающего списка фильтров
    departments = Department.objects.all()
    
    # Все отделения для модального окна изменения статуса
    all_departments = Department.objects.all()
    
    context = {
        'recipients': recipients_page,
        'page_obj': recipients_page,
        'paginator': paginator,
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
        # Берём актуальные значения из истории (как в модальном окне)
        old_department = recipient.get_current_department()
        old_room = recipient.get_current_room()
        old_placement = recipient.get_current_placement()
        
        recipient.last_name = request.POST.get('last_name', recipient.last_name)
        recipient.first_name = request.POST.get('first_name', recipient.first_name)
        recipient.patronymic = request.POST.get('patronymic', '')
        recipient.birth_date = request.POST.get('birth_date') or recipient.birth_date
        
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
        
        # Паспортные данные (только для HR)
        if user.role == 'hr' or user.is_superuser:
            recipient.passport_series = request.POST.get('passport_series', '')
            recipient.passport_number = request.POST.get('passport_number', '')
            recipient.passport_issued_by = request.POST.get('passport_issued_by', '')
            recipient.passport_department_code = request.POST.get('passport_department_code', '')
            recipient.phone = request.POST.get('phone', '')
            
            passport_issue_date = request.POST.get('passport_issue_date')
            if passport_issue_date:
                recipient.passport_issue_date = passport_issue_date
            else:
                recipient.passport_issue_date = None
        
        # Обработка фото
        if request.FILES.get('photo'):
            recipient.photo = request.FILES['photo']
        
        reason = request.POST.get('status_reason', '')
        
        # Получаем дату изменения из формы
        status_change_date_str = request.POST.get('status_change_date')
        status_change_date = date.today()  # По умолчанию сегодня
        if status_change_date_str:
            try:
                from datetime import datetime
                status_change_date = datetime.strptime(status_change_date_str, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                pass  # Если дата некорректна, используем сегодняшнюю
        
        # Получаем новое размещение из формы
        new_placement = request.POST.get('placement')
        
        # Получаем новое отделение (только для internat)
        if new_placement == 'internat':
            dept_id = request.POST.get('department')
            if dept_id:
                try:
                    new_department = Department.objects.get(id=dept_id)
                except Department.DoesNotExist:
                    new_department = old_department
            else:
                new_department = old_department
            new_room = request.POST.get('room', '')
        else:
            # Для не-internat отделение не требуется
            new_department = None
            new_room = ''
        
        # Определяем, нужно ли менять текущие поля
        today = date.today()
        should_update_current = status_change_date >= today
        
        # Используем транзакцию для атомарного обновления
        with transaction.atomic():
            # Обновляем текущие поля только если дата - сегодня или позже
            if should_update_current:
                recipient.placement = new_placement
                recipient.department = new_department
                recipient.room = new_room
            
            recipient.save()
            
            # Создаем запись в истории если размещение, отделение или комната изменились
            if (old_placement != new_placement or
                old_department != new_department or
                old_room != new_room):
                
                # Удаляем существующие записи с той же датой для этого получателя
                RecipientHistory.objects.filter(
                    recipient=recipient,
                    date=status_change_date
                ).delete()
                
                RecipientHistory.objects.create(
                    recipient=recipient,
                    old_placement=old_placement,
                    new_placement=new_placement,
                    old_department=old_department,
                    new_department=new_department,
                    old_room=old_room,
                    new_room=new_room,
                    old_status=old_placement,  # Для совместимости
                    new_status=new_placement,  # Для совместимости
                    reason=reason,
                    date=status_change_date,
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
    
    # Единая история изменений
    history = recipient.history.all()[:10]
    
    # Дата последнего изменения статуса (из истории)
    last_status_change = recipient.history.first()
    last_status_change_date = last_status_change.date if last_status_change else None
    
    # Все отделения для выпадающего списка (включая специальные статусы)
    departments = Department.objects.all()
    
    # Проживающие для переключения (все, кроме выбывших)
    recipients = Recipient.objects.select_related('department').exclude(
        placement='discharged'
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
        'history': history,
        'last_status_change_date': last_status_change_date,
    }
    
    return render(request, 'recipients/recipient_edit.html', context)


@login_required
def recipients_by_department(request, department_id):
    """API: Список проживающих по отделению"""
    user = request.user
    
    # Проверка доступа
    if not user.is_admin_or_hr and user.department_id != department_id:
        return JsonResponse({'error': 'Нет доступа'}, status=403)
    
    # Фильтруем по отделению (только проживающие в интернате)
    recipients = Recipient.objects.filter(
        department_id=department_id,
        placement='internat'
    ).values('id', 'last_name', 'first_name', 'patronymic', 'room')
    
    return JsonResponse({
        'recipients': list(recipients)
    })


@login_required
def change_status(request, pk):
    """API: Изменение размещения проживающего"""
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
    
    # Берём актуальные значения из истории
    old_department = recipient.get_current_department()
    old_room = recipient.get_current_room()
    old_placement = recipient.get_current_placement()
    
    # Получаем новые данные
    new_placement = data.get('placement')  # Новое размещение
    new_department_id = data.get('department_id')
    new_room = data.get('room', '')
    reason = data.get('reason', '')
    change_date_str = data.get('change_date')
    
    # Парсим дату изменения если передана
    change_date = date.today()
    if change_date_str:
        try:
            from datetime import datetime
            change_date = datetime.strptime(change_date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            pass
    
    # Определяем новое размещение
    if not new_placement:
        # Если размещение не указано, определяем по отделению
        if new_department_id:
            try:
                dept = Department.objects.get(id=new_department_id)
                dept_to_placement = {
                    'residential': 'internat',
                    'mercy': 'internat',
                    'vacation': 'vacation',
                    'hospital': 'hospital',
                    'deceased': 'discharged',
                }
                new_placement = dept_to_placement.get(dept.department_type, 'internat')
            except Department.DoesNotExist:
                new_placement = 'internat'
        else:
            new_placement = recipient.placement
    
    # Получаем новое отделение (только для internat)
    if new_placement == 'internat':
        if new_department_id:
            try:
                new_department = Department.objects.get(id=new_department_id)
            except Department.DoesNotExist:
                return JsonResponse({'error': 'Отделение не найдено'}, status=400)
        else:
            new_department = recipient.department
    else:
        # Для не-internat отделение не требуется
        new_department = None
        new_room = ''
    
    # Определяем, нужно ли менять текущие поля
    today = date.today()
    should_update_current = change_date >= today
    
    # Используем транзакцию для атомарного обновления
    with transaction.atomic():
        # Обновляем текущие поля только если дата - сегодня или позже
        if should_update_current:
            recipient.placement = new_placement
            recipient.department = new_department
            recipient.room = new_room
        
        # Обновляем даты
        admission_date = data.get('admission_date')
        if admission_date:
            recipient.admission_date = admission_date
        
        discharge_date = data.get('discharge_date')
        if discharge_date:
            recipient.discharge_date = discharge_date
        
        recipient.save()
        
        # Создаем запись в истории
        if (old_placement != new_placement or
            old_department != new_department or
            old_room != new_room):
            
            RecipientHistory.objects.filter(
                recipient=recipient,
                date=change_date
            ).delete()
            
            RecipientHistory.objects.create(
                recipient=recipient,
                old_placement=old_placement,
                new_placement=new_placement,
                old_department=old_department,
                new_department=new_department,
                old_room=old_room,
                new_room=new_room,
                old_status=old_placement,  # Для совместимости
                new_status=new_placement,  # Для совместимости
                reason=reason,
                date=change_date,
                changed_by=user
            )
    
    return JsonResponse({
        'success': True,
        'recipient': {
            'id': recipient.id,
            'placement': recipient.placement,
            'placement_display': recipient.placement_display,
            'department': recipient.department.name if recipient.department else '',
            'room': recipient.room,
            'status': recipient.status,  # Для совместимости
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
    departments = Department.objects.all()
    
    # Проживающие для переключения (все, кроме выбывших)
    recipients = Recipient.objects.select_related('department').exclude(
        placement='discharged'
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
    departments = Department.objects.all()
    
    # Проживающие
    recipients = Recipient.objects.select_related('department').all()
    
    # Фильтрация по отделению
    if not user.is_admin_or_hr and user.department:
        recipients = recipients.filter(department=user.department)
    
    if department_id:
        recipients = recipients.filter(department_id=department_id)
    
    # Фильтруем только проживающих (не выбывших)
    recipients = recipients.exclude(
        placement='discharged'
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
        
        # Получаем всех проживающих в интернате
        recipients = Recipient.objects.select_related('department').filter(
            placement='internat'
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
    departments = Department.objects.annotate(
        recipient_count=Count('recipients')
    ).all()
    
    context = {
        'departments': departments,
    }
    
    return render(request, 'recipients/residents_list_select.html', context)


@login_required
def residents_list_data(request):
    """API: Данные списка проживающих для отображения на странице"""
    user = request.user
    today = date.today()
    
    # Получаем выбранные отделения
    department_ids = request.GET.getlist('departments')
    
    # Получаем режим отображения
    view_mode = request.GET.get('mode', 'grouped')
    
    if department_ids and 'all' not in department_ids:
        departments = Department.objects.filter(
            id__in=department_ids
        )
    else:
        # Все отделения
        departments = Department.objects.all()
    
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
    
    return render(request, 'recipients/residents_list_content.html', context)


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
            id__in=department_ids
        )
    else:
        # Все отделения
        departments = Department.objects.all()
    
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


@login_required
def consent_opd_page(request):
    """Страница выбора проживающего для формирования согласия на ОПД"""
    user = request.user
    today = date.today()
    
    # Получаем всех проживающих
    recipients = Recipient.objects.select_related('department').all()
    
    # Фильтрация по отделению для не-админов
    if not user.is_admin_or_hr and user.department:
        recipients = recipients.filter(department=user.department)
    
    # Получаем выбранное отделение
    selected_department = request.GET.get('department', '')
    
    # Получаем выбранного проживающего
    recipient_id = request.GET.get('recipient')
    selected_recipient = None
    
    if recipient_id:
        try:
            selected_recipient = Recipient.objects.select_related('department').get(pk=recipient_id)
        except Recipient.DoesNotExist:
            pass
    
    # Получаем отделения для фильтра
    departments = Department.objects.all()
    
    context = {
        'recipients': recipients,
        'selected_recipient': selected_recipient,
        'selected_department': selected_department,
        'departments': departments,
        'today': today,
    }
    
    return render(request, 'recipients/consent_opd_select.html', context)


@login_required
def consent_opd_print(request, pk):
    """Печать согласия на обработку персональных данных"""
    from apps.core.models import SystemSettings
    
    recipient = get_object_or_404(Recipient, pk=pk)
    today = date.today()
    settings = SystemSettings.get_settings()
    
    # Директор организации (для блока "Я, ..." и подписи)
    director = None
    if settings.executor_organization:
        director = settings.executor_organization.director
    
    context = {
        'recipient': recipient,
        'today': today,
        'organization': settings.executor_organization,
        'director': director,
    }
    
    return render(request, 'recipients/consent_opd_print.html', context)
