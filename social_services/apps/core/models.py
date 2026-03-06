from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings


class LocationType(models.Model):
    """Тип местоположения проживающего"""
    
    code = models.CharField('Код', max_length=20, unique=True)
    name = models.CharField('Название', max_length=100)
    is_active_status = models.BooleanField(
        'Активный статус',
        default=True,
        help_text='Активен ли проживающий в этом статусе'
    )
    requires_department = models.BooleanField(
        'Требует отделения',
        default=True,
        help_text='Нужно ли выбирать отделение для этого типа размещения'
    )
    order = models.PositiveIntegerField('Порядок', default=0)
    
    class Meta:
        verbose_name = 'Тип местоположения'
        verbose_name_plural = 'Типы местоположения'
        ordering = ['order', 'name']
    
    def __str__(self):
        return self.name


class Department(models.Model):
    """Отделение учреждения (только реальные отделения)"""
    
    DEPARTMENT_TYPES = [
        ('residential', 'Проживания'),  # Обычное отделение (1, 2, 3, 4 и т.д.)
        ('mercy', 'Милосердие'),        # Отделение милосердия
    ]
    
    name = models.CharField('Название', max_length=100)
    code = models.CharField('Код', max_length=20, unique=True)
    department_type = models.CharField(
        'Тип отделения',
        max_length=20,
        choices=DEPARTMENT_TYPES,
        default='residential',
        help_text='Тип отделения'
    )
    capacity = models.PositiveIntegerField('Количество мест', default=0, help_text='Максимальное количество проживающих')
    description = models.TextField('Описание', blank=True, default='')
    
    class Meta:
        verbose_name = 'Отделение'
        verbose_name_plural = 'Отделения'
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    @property
    def is_mercy(self):
        """Является ли отделением милосердия"""
        return self.department_type == 'mercy'


class User(AbstractUser):
    """Пользователь системы с ролями"""
    ROLE_CHOICES = settings.ROLES
    
    role = models.CharField(
        'Роль',
        max_length=20,
        choices=ROLE_CHOICES,
        default=settings.ROLE_SPECIALIST
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Отделение',
        help_text='Отделение, к которому привязан сотрудник (для медиков/специалистов)'
    )
    patronymic = models.CharField('Отчество', max_length=150, blank=True)
    
    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'
        ordering = ['last_name', 'first_name']
    
    def __str__(self):
        return self.get_full_name() or self.username
    
    def get_full_name(self):
        """Возвращает ФИО полностью"""
        parts = [self.last_name, self.first_name, self.patronymic]
        return ' '.join(filter(None, parts))
    
    @property
    def is_admin_or_hr(self):
        """Проверяет, является ли пользователь администратором или кадровиком"""
        return self.role in [settings.ROLE_ADMIN, settings.ROLE_HR]
    
    @property
    def can_edit_all(self):
        """Может редактировать все записи"""
        return self.is_admin_or_hr
    
    @property
    def can_edit_services(self):
        """Может редактировать справочник услуг"""
        return self.is_admin_or_hr
