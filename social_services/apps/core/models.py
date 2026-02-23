from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings


class Department(models.Model):
    """Отделение учреждения"""
    
    DEPARTMENT_TYPES = [
        ('residential', 'Проживания'),  # Обычное отделение (1, 2, 3, 4 и т.д.)
        ('mercy', 'Милосердие'),        # Отделение милосердия
        ('hospital', 'Больница'),       # Больница
        ('vacation', 'Отпуск'),         # Отпуск
        ('deceased', 'Умер'),           # Выбыл (умер)
    ]
    
    name = models.CharField('Название', max_length=100)
    code = models.CharField('Код', max_length=20, unique=True)
    department_type = models.CharField(
        'Тип отделения',
        max_length=20,
        choices=DEPARTMENT_TYPES,
        default='residential',
        help_text='Определяет статус проживающего'
    )
    is_mercy = models.BooleanField('Отделение милосердия', default=False)
    capacity = models.PositiveIntegerField('Количество мест', default=0, help_text='Максимальное количество проживающих')
    description = models.TextField('Описание', blank=True, default='')
    
    class Meta:
        verbose_name = 'Отделение'
        verbose_name_plural = 'Отделения'
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    @property
    def status_code(self):
        """Возвращает код статуса для проживающих в этом отделении"""
        type_to_status = {
            'residential': 'active',
            'mercy': 'active',
            'hospital': 'hospital',
            'vacation': 'vacation',
            'deceased': 'discharged',
        }
        return type_to_status.get(self.department_type, 'active')


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
