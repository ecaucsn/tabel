from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from datetime import date
from .models import Product, MonthlyRequest, RequestItem, DigitalProfile
from apps.recipients.models import Recipient


# ==================== Views for Food Requests ====================

class RequestsListView(LoginRequiredMixin, ListView):
    """List of food requests"""
    model = MonthlyRequest
    template_name = 'modules/requests_list.html'
    context_object_name = 'requests'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = MonthlyRequest.objects.select_related('recipient', 'recipient__department')
        
        # Filter by year and month
        year = self.request.GET.get('year')
        month = self.request.GET.get('month')
        
        if year:
            queryset = queryset.filter(year=year)
        if month:
            queryset = queryset.filter(month=month)
            
        # Filter by status
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
            
        # Filter by recipient
        recipient_id = self.request.GET.get('recipient')
        if recipient_id:
            queryset = queryset.filter(recipient_id=recipient_id)
            
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_year'] = date.today().year
        context['current_month'] = date.today().month
        context['years'] = range(2024, date.today().year + 2)
        context['months'] = [
            (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
            (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
            (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December')
        ]
        context['status_choices'] = MonthlyRequest.STATUS_CHOICES
        context['recipients'] = Recipient.objects.filter(department__isnull=False).order_by('last_name')
        return context


class RequestCreateView(LoginRequiredMixin, CreateView):
    """Create a new food request"""
    model = MonthlyRequest
    template_name = 'modules/request_form.html'
    fields = ['recipient', 'year', 'month', 'notes']
    
    def get_initial(self):
        initial = super().get_initial()
        initial['year'] = date.today().year
        initial['month'] = date.today().month
        return initial
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, 'Request created successfully')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('modules:request_detail', kwargs={'pk': self.object.pk})


class RequestDetailView(LoginRequiredMixin, DetailView):
    """Detail view of a food request"""
    model = MonthlyRequest
    template_name = 'modules/request_detail.html'
    context_object_name = 'request'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['products'] = Product.objects.filter(is_active=True)
        context['items'] = self.object.items.select_related('product')
        return context


class RequestUpdateView(LoginRequiredMixin, UpdateView):
    """Update a food request"""
    model = MonthlyRequest
    template_name = 'modules/request_form.html'
    fields = ['recipient', 'year', 'month', 'notes', 'status']
    
    def form_valid(self, form):
        messages.success(self.request, 'Request updated successfully')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('modules:request_detail', kwargs={'pk': self.object.pk})


class RequestDeleteView(LoginRequiredMixin, DeleteView):
    """Delete a food request"""
    model = MonthlyRequest
    success_url = reverse_lazy('modules:requests')
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Request deleted successfully')
        return super().delete(request, *args, **kwargs)


@require_POST
def add_request_item(request, request_id):
    """Add an item to a food request via AJAX"""
    food_request = get_object_or_404(MonthlyRequest, pk=request_id)
    
    product_id = request.POST.get('product_id')
    quantity = request.POST.get('quantity', 1)
    
    if not product_id:
        return JsonResponse({'success': False, 'error': 'Product not selected'})
    
    try:
        product = Product.objects.get(pk=product_id, is_active=True)
    except Product.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Product not found'})
    
    try:
        quantity = float(quantity)
        if quantity <= 0:
            return JsonResponse({'success': False, 'error': 'Quantity must be positive'})
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Invalid quantity'})
    
    # Create or update item
    item, created = RequestItem.objects.get_or_create(
        request=food_request,
        product=product,
        defaults={'quantity': quantity, 'price': product.price}
    )
    
    if not created:
        item.quantity = quantity
        item.price = product.price
        item.save()
    
    # Recalculate total
    food_request.calculate_total()
    
    return JsonResponse({
        'success': True,
        'item': {
            'id': item.id,
            'product': product.name,
            'quantity': float(item.quantity),
            'price': float(item.price),
            'total': float(item.total)
        },
        'request_total': float(food_request.total_amount)
    })


@require_POST
def remove_request_item(request, request_id, item_id):
    """Remove an item from a food request"""
    food_request = get_object_or_404(MonthlyRequest, pk=request_id)
    item = get_object_or_404(RequestItem, pk=item_id, request=food_request)
    
    item.delete()
    food_request.calculate_total()
    
    return JsonResponse({
        'success': True,
        'request_total': float(food_request.total_amount)
    })


@require_POST
def submit_request(request, pk):
    """Submit a request (change status to submitted)"""
    food_request = get_object_or_404(MonthlyRequest, pk=pk)
    
    if food_request.status != 'draft':
        return JsonResponse({'success': False, 'error': 'Only draft requests can be submitted'})
    
    if food_request.items.count() == 0:
        return JsonResponse({'success': False, 'error': 'Add at least one item'})
    
    food_request.status = 'submitted'
    food_request.save()
    
    messages.success(request, 'Request submitted successfully')
    return JsonResponse({'success': True})


# ==================== Views for Digital Profile ====================

class DigitalProfileListView(LoginRequiredMixin, ListView):
    """List of digital profiles"""
    model = DigitalProfile
    template_name = 'modules/profile_list.html'
    context_object_name = 'profiles'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = DigitalProfile.objects.select_related('recipient', 'recipient__department')
        
        # Search
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                recipient__last_name__icontains=search
            ) | queryset.filter(
                recipient__first_name__icontains=search
            )
            
        return queryset


class DigitalProfileCreateView(LoginRequiredMixin, CreateView):
    """Create a digital profile"""
    model = DigitalProfile
    template_name = 'modules/profile_form.html'
    fields = ['recipient', 'bio', 'hobbies', 'favorite_activities', 
              'special_needs', 'dietary_restrictions', 'medical_notes',
              'emergency_contact', 'emergency_phone', 'is_public']
    
    def get_initial(self):
        initial = super().get_initial()
        recipient_id = self.request.GET.get('recipient')
        if recipient_id:
            initial['recipient'] = recipient_id
        return initial
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Recipients without profile
        context['available_recipients'] = Recipient.objects.filter(
            digital_profile__isnull=True,
            department__isnull=False
        ).order_by('last_name')
        return context
    
    def form_valid(self, form):
        messages.success(self.request, 'Digital profile created successfully')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('modules:digital_profile_detail', kwargs={'pk': self.object.pk})


class DigitalProfileDetailView(LoginRequiredMixin, DetailView):
    """Detail view of a digital profile"""
    model = DigitalProfile
    template_name = 'modules/profile_detail.html'
    context_object_name = 'profile'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['recipient'] = self.object.recipient
        return context


class DigitalProfileUpdateView(LoginRequiredMixin, UpdateView):
    """Update a digital profile"""
    model = DigitalProfile
    template_name = 'modules/profile_form.html'
    fields = ['bio', 'hobbies', 'favorite_activities', 
              'special_needs', 'dietary_restrictions', 'medical_notes',
              'emergency_contact', 'emergency_phone', 'is_public']
    
    def form_valid(self, form):
        messages.success(self.request, 'Digital profile updated successfully')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('modules:digital_profile_detail', kwargs={'pk': self.object.pk})


def generate_qr(request, pk):
    """Generate QR code for a profile"""
    profile = get_object_or_404(DigitalProfile, pk=pk)
    profile.generate_qr_code(request)
    messages.success(request, 'QR code generated successfully')
    return redirect('modules:digital_profile_detail', pk=pk)


def public_profile(request, profile_id):
    """Public view of a digital profile (mobile-friendly)"""
    profile = get_object_or_404(DigitalProfile, unique_id=profile_id, is_public=True)
    
    return render(request, 'modules/public_profile.html', {
        'profile': profile,
        'recipient': profile.recipient
    })


# ==================== Views for Pensions ====================

from .models import PensionAccount, PensionAccrual, PensionExpense, PensionSavings
from decimal import Decimal
from django.db.models import Sum


class PensionListView(LoginRequiredMixin, ListView):
    """Список пенсионных счетов"""
    model = PensionAccount
    template_name = 'modules/pension_list.html'
    context_object_name = 'accounts'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = PensionAccount.objects.select_related('recipient', 'recipient__department')
        
        # Фильтр по отделению
        department_id = self.request.GET.get('department')
        if department_id:
            queryset = queryset.filter(recipient__department_id=department_id)
        
        # Поиск по ФИО
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                recipient__last_name__icontains=search
            ) | queryset.filter(
                recipient__first_name__icontains=search
            )
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.core.models import Department
        context['departments'] = Department.objects.all()
        
        # Общая статистика
        total_balance = PensionAccount.objects.aggregate(
            total=Sum('balance')
        )['total'] or Decimal('0')
        context['total_balance'] = total_balance
        
        return context


class PensionDetailView(LoginRequiredMixin, DetailView):
    """Детальный просмотр пенсионного счёта"""
    model = PensionAccount
    template_name = 'modules/pension_detail.html'
    context_object_name = 'account'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        account = self.object
        
        # Получаем год и месяц из параметров или текущие
        year = int(self.request.GET.get('year', date.today().year))
        month = int(self.request.GET.get('month', date.today().month))
        
        context['current_year'] = year
        context['current_month'] = month
        context['years'] = range(2024, date.today().year + 2)
        context['months'] = [
            (1, 'Январь'), (2, 'Февраль'), (3, 'Март'), (4, 'Апрель'),
            (5, 'Май'), (6, 'Июнь'), (7, 'Июль'), (8, 'Август'),
            (9, 'Сентябрь'), (10, 'Октябрь'), (11, 'Ноябрь'), (12, 'Декабрь')
        ]
        
        # Начисления за выбранный месяц
        context['accrual'] = account.get_monthly_accrual(year, month)
        
        # Расходы за выбранный месяц
        context['expenses'] = account.get_monthly_expenses(year, month)
        context['expenses_total'] = account.get_monthly_expenses_total(year, month)
        
        # Накопления
        context['savings'] = account.savings.filter(year=year, month=month).first()
        
        # История операций (последние 12 месяцев)
        from django.db.models import Q
        from datetime import datetime
        from dateutil.relativedelta import relativedelta
        
        history = []
        for i in range(12):
            d = date.today() - relativedelta(months=i)
            accrual = account.accruals.filter(year=d.year, month=d.month).first()
            expenses_total = account.get_monthly_expenses_total(d.year, d.month)
            history.append({
                'year': d.year,
                'month': d.month,
                'accrual': accrual.amount if accrual else Decimal('0'),
                'expenses': expenses_total,
                'balance': (accrual.amount if accrual else Decimal('0')) - expenses_total
            })
        context['history'] = history
        
        # Связанные заявки
        completed_requests = MonthlyRequest.objects.filter(
            recipient=account.recipient,
            status='completed'
        ).order_by('-year', '-month')[:6]
        context['completed_requests'] = completed_requests
        
        return context


class PensionAccountCreateView(LoginRequiredMixin, CreateView):
    """Создание пенсионного счёта"""
    model = PensionAccount
    template_name = 'modules/pension_account_form.html'
    fields = ['recipient', 'pension_type', 'pension_number', 'monthly_pension_amount', 'balance', 'notes']
    
    def get_initial(self):
        initial = super().get_initial()
        recipient_id = self.request.GET.get('recipient')
        if recipient_id:
            initial['recipient'] = recipient_id
        return initial
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Получатели без пенсионного счёта
        context['available_recipients'] = Recipient.objects.filter(
            pension_account__isnull=True,
            department__isnull=False
        ).order_by('last_name')
        return context
    
    def form_valid(self, form):
        messages.success(self.request, 'Пенсионный счёт создан')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('modules:pension_detail', kwargs={'pk': self.object.pk})


class PensionAccountUpdateView(LoginRequiredMixin, UpdateView):
    """Редактирование пенсионного счёта"""
    model = PensionAccount
    template_name = 'modules/pension_account_form.html'
    fields = ['pension_type', 'pension_number', 'monthly_pension_amount', 'balance', 'notes']
    
    def form_valid(self, form):
        messages.success(self.request, 'Пенсионный счёт обновлён')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('modules:pension_detail', kwargs={'pk': self.object.pk})


class PensionAccrualCreateView(LoginRequiredMixin, CreateView):
    """Создание начисления пенсии"""
    model = PensionAccrual
    template_name = 'modules/pension_accrual_form.html'
    fields = ['account', 'year', 'month', 'amount', 'accrued_date', 'source', 'notes']
    
    def get_initial(self):
        initial = super().get_initial()
        account_id = self.request.GET.get('account')
        if account_id:
            initial['account'] = account_id
        initial['year'] = date.today().year
        initial['month'] = date.today().month
        initial['accrued_date'] = date.today()
        return initial
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['accounts'] = PensionAccount.objects.select_related('recipient').all()
        return context
    
    def form_valid(self, form):
        messages.success(self.request, 'Начисление добавлено')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('modules:pension_detail', kwargs={'pk': self.object.account.pk})


class PensionExpenseCreateView(LoginRequiredMixin, CreateView):
    """Создание расхода пенсии"""
    model = PensionExpense
    template_name = 'modules/pension_expense_form.html'
    fields = ['account', 'year', 'month', 'amount', 'category', 'description', 'expense_date', 'related_request']
    
    def get_initial(self):
        initial = super().get_initial()
        account_id = self.request.GET.get('account')
        if account_id:
            initial['account'] = account_id
        initial['year'] = date.today().year
        initial['month'] = date.today().month
        initial['expense_date'] = date.today()
        return initial
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['accounts'] = PensionAccount.objects.select_related('recipient').all()
        context['categories'] = PensionExpense.CATEGORY_CHOICES
        
        # Заявки для связи
        account_id = self.request.GET.get('account')
        if account_id:
            account = PensionAccount.objects.get(pk=account_id)
            context['requests'] = MonthlyRequest.objects.filter(
                recipient=account.recipient,
                status='completed'
            ).order_by('-year', '-month')[:10]
        else:
            context['requests'] = MonthlyRequest.objects.filter(
                status='completed'
            ).order_by('-year', '-month')[:20]
        
        return context
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, 'Расход добавлен')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('modules:pension_detail', kwargs={'pk': self.object.account.pk})


class PensionSavingsCreateView(LoginRequiredMixin, CreateView):
    """Создание накопления"""
    model = PensionSavings
    template_name = 'modules/pension_savings_form.html'
    fields = ['account', 'year', 'month', 'amount', 'purpose', 'notes']
    
    def get_initial(self):
        initial = super().get_initial()
        account_id = self.request.GET.get('account')
        if account_id:
            initial['account'] = account_id
        initial['year'] = date.today().year
        initial['month'] = date.today().month
        return initial
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['accounts'] = PensionAccount.objects.select_related('recipient').all()
        return context
    
    def form_valid(self, form):
        messages.success(self.request, 'Накопление добавлено')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('modules:pension_detail', kwargs={'pk': self.object.account.pk})


@require_POST
def add_pension_accrual(request, account_id):
    """Добавление начисления через AJAX"""
    account = get_object_or_404(PensionAccount, pk=account_id)
    
    year = request.POST.get('year')
    month = request.POST.get('month')
    amount = request.POST.get('amount')
    source = request.POST.get('source', 'ПФР')
    notes = request.POST.get('notes', '')
    
    if not year or not month or not amount:
        return JsonResponse({'success': False, 'error': 'Заполните все обязательные поля'})
    
    try:
        year = int(year)
        month = int(month)
        amount = Decimal(amount)
        if amount <= 0:
            return JsonResponse({'success': False, 'error': 'Сумма должна быть положительной'})
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Некорректные данные'})
    
    # Проверяем, есть ли уже начисление за этот месяц
    accrual, created = PensionAccrual.objects.update_or_create(
        account=account,
        year=year,
        month=month,
        defaults={
            'amount': amount,
            'source': source,
            'notes': notes,
            'accrued_date': date.today()
        }
    )
    
    return JsonResponse({
        'success': True,
        'accrual': {
            'id': accrual.id,
            'year': accrual.year,
            'month': accrual.month,
            'amount': float(accrual.amount),
            'source': accrual.source
        },
        'balance': float(account.balance)
    })


@require_POST
def add_pension_expense(request, account_id):
    """Добавление расхода через AJAX"""
    account = get_object_or_404(PensionAccount, pk=account_id)
    
    year = request.POST.get('year')
    month = request.POST.get('month')
    amount = request.POST.get('amount')
    category = request.POST.get('category', 'other')
    description = request.POST.get('description', '')
    related_request_id = request.POST.get('related_request')
    
    if not year or not month or not amount:
        return JsonResponse({'success': False, 'error': 'Заполните все обязательные поля'})
    
    try:
        year = int(year)
        month = int(month)
        amount = Decimal(amount)
        if amount <= 0:
            return JsonResponse({'success': False, 'error': 'Сумма должна быть положительной'})
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Некорректные данные'})
    
    related_request = None
    if related_request_id:
        try:
            related_request = MonthlyRequest.objects.get(pk=related_request_id)
        except MonthlyRequest.DoesNotExist:
            pass
    
    expense = PensionExpense.objects.create(
        account=account,
        year=year,
        month=month,
        amount=amount,
        category=category,
        description=description,
        expense_date=date.today(),
        related_request=related_request,
        created_by=request.user
    )
    
    return JsonResponse({
        'success': True,
        'expense': {
            'id': expense.id,
            'year': expense.year,
            'month': expense.month,
            'amount': float(expense.amount),
            'category': expense.get_category_display()
        },
        'balance': float(account.balance)
    })


# ==================== Views for Monthly Purchase ====================

import json
from apps.core.models import Department


def monthly_purchase_create(request):
    """Создание ежемесячной заявки на продукты питания (массовое)"""
    from datetime import date
    
    # Получаем параметры фильтрации
    year = int(request.GET.get('year', date.today().year))
    month = int(request.GET.get('month', date.today().month))
    department_id = request.GET.get('department', '')
    set_type = request.GET.get('set_type', 'full')
    
    # Получаем отделения
    departments = Department.objects.all().order_by('name')
    
    # Получаем продукты
    products = Product.objects.filter(is_active=True).order_by('name')
    
    # Получаем проживающих для выбранного отделения
    recipients = Recipient.objects.none()
    if department_id:
        recipients = Recipient.objects.filter(
            department_id=department_id
        ).select_related('department').order_by('last_name', 'first_name')
    
    # Получаем существующие данные
    existing_data = {}
    if department_id:
        # Получаем все заявки для данного отделения за выбранный период
        existing_requests = MonthlyRequest.objects.filter(
            recipient__department_id=department_id,
            year=year,
            month=month
        ).prefetch_related('items')
        
        for req in existing_requests:
            recipient_id = str(req.recipient_id)
            existing_data[recipient_id] = {}
            for item in req.items.all():
                existing_data[recipient_id][str(item.product_id)] = float(item.quantity)
    
    # Подготовка данных для JavaScript
    products_json = json.dumps([
        {'id': p.id, 'name': p.name, 'unit': p.unit, 'price': float(p.price)}
        for p in products
    ])
    
    existing_data_json = json.dumps(existing_data)
    
    context = {
        'year': year,
        'month': month,
        'years': range(2024, date.today().year + 2),
        'months': [
            (1, 'Январь'), (2, 'Февраль'), (3, 'Март'), (4, 'Апрель'),
            (5, 'Май'), (6, 'Июнь'), (7, 'Июль'), (8, 'Август'),
            (9, 'Сентябрь'), (10, 'Октябрь'), (11, 'Ноябрь'), (12, 'Декабрь')
        ],
        'departments': departments,
        'selected_department': department_id,
        'set_type': set_type,
        'products': products,
        'recipients': recipients,
        'products_json': products_json,
        'existing_data': existing_data_json,
    }
    
    return render(request, 'modules/monthly_purchase_create.html', context)


@require_POST
def monthly_purchase_save(request):
    """Сохранение массовой заявки на продукты"""
    try:
        data = json.loads(request.body)
        
        year = data.get('year')
        month = data.get('month')
        department_id = data.get('department_id')
        items = data.get('items', [])
        
        if not year or not month:
            return JsonResponse({'success': False, 'error': 'Не указан период'})
        
        if not items:
            return JsonResponse({'success': False, 'error': 'Нет данных для сохранения'})
        
        created_count = 0
        updated_count = 0
        
        for item in items:
            recipient_id = item.get('recipient_id')
            product_id = item.get('product_id')
            quantity = item.get('quantity', 0)
            
            if not recipient_id or not product_id or quantity <= 0:
                continue
            
            # Получаем или создаем заявку
            request_obj, created = MonthlyRequest.objects.get_or_create(
                recipient_id=recipient_id,
                year=year,
                month=month,
                defaults={
                    'created_by': request.user,
                    'status': 'draft'
                }
            )
            
            if created:
                created_count += 1
            else:
                updated_count += 1
            
            # Получаем продукт
            try:
                product = Product.objects.get(id=product_id)
            except Product.DoesNotExist:
                continue
            
            # Создаем или обновляем позицию
            RequestItem.objects.update_or_create(
                request=request_obj,
                product_id=product_id,
                defaults={
                    'quantity': quantity,
                    'price': product.price
                }
            )
            
            # Пересчитываем итоговую сумму
            request_obj.calculate_total()
        
        return JsonResponse({
            'success': True,
            'created_count': created_count,
            'updated_count': updated_count,
            'message': f'Сохранено заявок: {created_count + updated_count}'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Некорректный формат данных'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})