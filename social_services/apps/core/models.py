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


class Organization(models.Model):
    """Организация-исполнитель услуг"""
    
    name = models.CharField('Название', max_length=200)
    short_name = models.CharField('Краткое название', max_length=100, blank=True)
    inn = models.CharField('ИНН', max_length=12, blank=True)
    kpp = models.CharField('КПП', max_length=9, blank=True)
    ogrn = models.CharField('ОГРН', max_length=15, blank=True)
    address = models.TextField('Адрес', blank=True)
    phone = models.CharField('Телефон', max_length=20, blank=True)
    email = models.EmailField('Email', blank=True)
    director = models.ForeignKey(
        'Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Руководитель',
        related_name='managed_organizations'
    )
    is_active = models.BooleanField('Активна', default=True)
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)
    
    class Meta:
        verbose_name = 'Организация'
        verbose_name_plural = 'Организации'
        ordering = ['name']
    
    def __str__(self):
        return self.short_name or self.name


class Employee(models.Model):
    """Сотрудник-исполнитель услуг"""
    
    GENDER_CHOICES = [
        ('male', 'Мужской'),
        ('female', 'Женский'),
    ]
    
    last_name = models.CharField('Фамилия', max_length=100)
    first_name = models.CharField('Имя', max_length=100)
    patronymic = models.CharField('Отчество', max_length=100, blank=True)
    gender = models.CharField('Пол', max_length=10, choices=GENDER_CHOICES, blank=True)
    birth_date = models.DateField('Дата рождения', null=True, blank=True)
    phone = models.CharField('Телефон', max_length=20, blank=True)
    email = models.EmailField('Email', blank=True)
    position = models.CharField('Должность', max_length=150, blank=True)
    
    # Адрес
    address = models.TextField('Адрес регистрации', blank=True)
    
    # Паспортные данные
    passport_series = models.CharField('Серия паспорта', max_length=4, blank=True)
    passport_number = models.CharField('Номер паспорта', max_length=6, blank=True)
    passport_issued_by = models.CharField('Кем выдан паспорт', max_length=255, blank=True)
    passport_issue_date = models.DateField('Дата выдачи паспорта', null=True, blank=True)
    passport_department_code = models.CharField('Код подразделения', max_length=7, blank=True)
    
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Организация',
        related_name='employees'
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Пользователь системы',
        related_name='employee_profile'
    )
    is_active = models.BooleanField('Активен', default=True)
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)
    
    class Meta:
        verbose_name = 'Сотрудник'
        verbose_name_plural = 'Сотрудники'
        ordering = ['last_name', 'first_name']
    
    def __str__(self):
        return self.get_full_name()
    
    def get_full_name(self):
        """Возвращает ФИО полностью"""
        parts = [self.last_name, self.first_name, self.patronymic]
        return ' '.join(filter(None, parts))
    
    @property
    def short_name(self):
        """Возвращает Фамилию И.О."""
        if self.first_name:
            initials = self.first_name[0] + '.'
            if self.patronymic:
                initials += self.patronymic[0] + '.'
            return f"{self.last_name} {initials}"
        return self.last_name


class SystemSettings(models.Model):
    """Глобальные настройки системы (singleton)"""
    
    executor_organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='executor_settings',
        verbose_name='Организация-исполнитель'
    )
    executor_signatory = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='executor_signatory_settings',
        verbose_name='Подписант от исполнителя',
        help_text='Сотрудник, подписывающий акты от имени исполнителя'
    )
    customer_organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customer_settings',
        verbose_name='Организация-заказчик'
    )
    customer_signatory = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customer_signatory_settings',
        verbose_name='Подписант от заказчика',
        help_text='Сотрудник, подписывающий акты от имени заказчика'
    )
    
    class Meta:
        verbose_name = 'Настройки системы'
        verbose_name_plural = 'Настройки системы'
    
    def __str__(self):
        return 'Настройки системы'
    
    @classmethod
    def get_settings(cls):
        """Возвращает единственный экземпляр настроек"""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
    
    def save(self, *args, **kwargs):
        # Всегда сохраняем с pk=1 (singleton)
        self.pk = 1
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        # Запрещаем удаление настроек
        pass
