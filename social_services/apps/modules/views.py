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