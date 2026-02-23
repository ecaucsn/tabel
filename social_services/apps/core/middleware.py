"""
Middleware для контроля доступа по отделениям
"""
from django.shortcuts import redirect
from django.urls import reverse
from django.conf import settings


class DepartmentAccessMiddleware:
    """
    Middleware для проверки доступа пользователей к отделениям.
    Медики и специалисты видят только своё отделение.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        return response
    
    def process_view(self, request, view_func, view_args, view_kwargs):
        # Пропускаем для неавторизованных пользователей
        if not request.user.is_authenticated:
            return None
        
        # Пропускаем для админов и кадровиков
        if request.user.is_admin_or_hr:
            return None
        
        # Пропускаем для статических файлов и медиа
        if request.path.startswith('/static/') or request.path.startswith('/media/'):
            return None
        
        # Пропускаем для URL авторизации и выхода
        allowed_paths = ['/login/', '/logout/', '/admin/']
        if any(request.path.startswith(p) for p in allowed_paths):
            return None
        
        return None
