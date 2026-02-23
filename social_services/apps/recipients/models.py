from django.db import models
from django.conf import settings
from apps.core.models import Department


def recipient_photo_path(instance, filename):
    """Путь для сохранения фото получателя"""
    return f'recipients/photos/{instance.id}/{filename}'


class Recipient(models.Model):
    """Получатель социальных услуг (ПСУ)"""
    
    STATUS_CHOICES = [
        ('active', 'Проживает'),
        ('vacation', 'Отпуск'),
        ('hospital', 'Больница'),
        ('discharged', 'Выбыл'),
    ]
    
    last_name = models.CharField('Фамилия', max_length=100)
    first_name = models.CharField('Имя', max_length=100)
    patronymic = models.CharField('Отчество', max_length=100, blank=True)
    birth_date = models.DateField('Дата рождения')
    photo = models.ImageField(
        'Фотография',
        upload_to=recipient_photo_path,
        blank=True,
        null=True,
        help_text='Фотография получателя услуг'
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        related_name='recipients',
        verbose_name='Отделение'
    )
    room = models.CharField('Комната', max_length=20, blank=True)
    admission_date = models.DateField('Дата заселения', null=True, blank=True)
    discharge_date = models.DateField('Дата смены статуса', null=True, blank=True)
    income = models.DecimalField(
        'Среднедушевой доход',
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
        help_text='Среднедушевой доход получателя социальных услуг'
    )
    pension_payment = models.DecimalField(
        'Перечислено ПФ',
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
        help_text='Фактически перечислено Пенсионным фондом в ДСО'
    )
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)
    
    class Meta:
        verbose_name = 'Получатель социальных услуг'
        verbose_name_plural = 'Получатели социальных услуг'
        ordering = ['last_name', 'first_name', 'patronymic']
    
    def __str__(self):
        return self.full_name
    
    @property
    def full_name(self):
        """Полное ФИО"""
        parts = [self.last_name, self.first_name, self.patronymic]
        return ' '.join(filter(None, parts))
    
    @property
    def short_name(self):
        """Фамилия И.О."""
        initials = ''
        if self.first_name:
            initials += f' {self.first_name[0]}.'
        if self.patronymic:
            initials += f'{self.patronymic[0]}.'
        return f'{self.last_name}{initials}'
    
    @property
    def age(self):
        """Возраст"""
        from datetime import date
        if not self.birth_date:
            return None
        today = date.today()
        age = today.year - self.birth_date.year
        if (today.month, today.day) < (self.birth_date.month, self.birth_date.day):
            age -= 1
        return age
    
    @property
    def status(self):
        """Статус определяется отделением"""
        if self.department:
            return self.department.status_code
        return 'active'
    
    @property
    def status_display(self):
        """Отображение статуса"""
        status_dict = dict(self.STATUS_CHOICES)
        return status_dict.get(self.status, 'Проживает')
    
    def get_status_display(self):
        """Отображение статуса (для совместимости)"""
        return self.status_display
    
    def set_department(self, new_department, user=None, reason=''):
        """Меняет отделение и записывает историю"""
        old_department = self.department
        old_status = self.status
        old_room = self.room
        
        self.department = new_department
        self.save()
        
        # Создаем запись в истории статусов
        StatusHistory.objects.create(
            recipient=self,
            old_department=old_department,
            new_department=new_department,
            old_status=old_status,
            new_status=self.status,
            changed_by=user,
            reason=reason
        )
        
        # Создаем запись в истории перемещений
        from datetime import date
        PlacementHistory.objects.create(
            recipient=self,
            old_department=old_department,
            new_department=new_department,
            old_room=old_room,
            new_room=self.room,
            old_status=old_status,
            new_status=self.status,
            reason=reason,
            date=date.today(),
            changed_by=user
        )
    
    def register_placement_change(self, old_department=None, new_department=None, 
                                   old_room=None, new_room=None, 
                                   old_status=None, new_status=None, 
                                   reason='', date=None, user=None):
        """Регистрирует изменение размещения"""
        if date is None:
            from datetime import date as date_module
            date = date_module.today()
        
        PlacementHistory.objects.create(
            recipient=self,
            old_department=old_department,
            new_department=new_department,
            old_room=old_room,
            new_room=new_room,
            old_status=old_status,
            new_status=new_status,
            reason=reason,
            date=date,
            changed_by=user
        )


class StatusHistory(models.Model):
    """История изменений статусов и отделений"""
    
    recipient = models.ForeignKey(
        Recipient,
        on_delete=models.CASCADE,
        related_name='status_history',
        verbose_name='Получатель услуг'
    )
    old_department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='departures',
        verbose_name='Предыдущее отделение'
    )
    new_department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='arrivals',
        verbose_name='Новое отделение'
    )
    old_status = models.CharField(
        'Предыдущий статус',
        max_length=20,
        choices=Recipient.STATUS_CHOICES,
        null=True,
        blank=True
    )
    new_status = models.CharField(
        'Новый статус',
        max_length=20,
        choices=Recipient.STATUS_CHOICES
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Кто изменил'
    )
    reason = models.TextField('Причина/Комментарий', blank=True)
    created_at = models.DateTimeField('Дата изменения', auto_now_add=True)
    
    class Meta:
        verbose_name = 'История статуса'
        verbose_name_plural = 'История статусов'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.recipient} - {self.get_new_status_display()} ({self.created_at:%d.%m.%Y %H:%M})"


class PlacementHistory(models.Model):
    """История перемещений внутри учреждения"""
    
    recipient = models.ForeignKey(
        Recipient,
        on_delete=models.CASCADE,
        related_name='placement_history',
        verbose_name='Получатель услуг'
    )
    old_department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='placement_departures',
        verbose_name='Предыдущее отделение'
    )
    new_department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='placement_arrivals',
        verbose_name='Новое отделение'
    )
    old_room = models.CharField('Предыдущая комната', max_length=20, blank=True, null=True)
    new_room = models.CharField('Новая комната', max_length=20, blank=True, null=True)
    old_status = models.CharField(
        'Предыдущий статус',
        max_length=20,
        choices=Recipient.STATUS_CHOICES,
        null=True,
        blank=True
    )
    new_status = models.CharField(
        'Новый статус',
        max_length=20,
        choices=Recipient.STATUS_CHOICES,
        null=True,
        blank=True
    )
    reason = models.TextField('Причина/Комментарий', blank=True)
    date = models.DateField('Дата перемещения')
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Кто изменил'
    )
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    
    class Meta:
        verbose_name = 'История перемещения'
        verbose_name_plural = 'История перемещений'
        ordering = ['-date', '-created_at']
    
    def __str__(self):
        return f"{self.recipient} - {self.date:%d.%m.%Y}"
    
    @property
    def movement_type(self):
        """Тип перемещения"""
        if self.old_department != self.new_department:
            if self.old_department is None:
                return 'Заселение'
            elif self.new_department is None:
                return 'Выбытие'
            else:
                return 'Перевод между отделениями'
        elif self.old_room != self.new_room:
            return 'Перемещение внутри отделения'
        elif self.old_status != self.new_status:
            return 'Изменение статуса'
        return 'Изменение'


class Contract(models.Model):
    """Индивидуальный план предоставления социальных услуг (ИППСУ)"""
    
    recipient = models.ForeignKey(
        Recipient,
        on_delete=models.CASCADE,
        related_name='contracts',
        verbose_name='Получатель услуг'
    )
    number = models.CharField('Номер договора', max_length=50)
    date_start = models.DateField('Дата начала')
    date_end = models.DateField('Дата окончания', null=True, blank=True)
    is_active = models.BooleanField('Действует', default=True)
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    
    class Meta:
        verbose_name = 'ИППСУ (Договор)'
        verbose_name_plural = 'ИППСУ (Договоры)'
        ordering = ['-date_start']
    
    def __str__(self):
        return f"ИППСУ №{self.number} - {self.recipient}"


class ContractService(models.Model):
    """Услуга в составе ИППСУ"""
    
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name='services',
        verbose_name='Договор'
    )
    service = models.ForeignKey(
        'services.Service',
        on_delete=models.CASCADE,
        related_name='contract_services',
        verbose_name='Услуга'
    )
    
    class Meta:
        verbose_name = 'Услуга в ИППСУ'
        verbose_name_plural = 'Услуги в ИППСУ'
        unique_together = ['contract', 'service']
    
    def __str__(self):
        limit = f" (макс. {self.service.max_quantity_per_month}/мес)" if self.service.max_quantity_per_month else ""
        return f"{self.contract} - {self.service}{limit}"


class MonthlyRecipientData(models.Model):
    """Данные проживающего по месяцам (доход, пенсия)"""
    
    recipient = models.ForeignKey(
        Recipient,
        on_delete=models.CASCADE,
        related_name='monthly_data',
        verbose_name='Получатель услуг'
    )
    year = models.IntegerField('Год')
    month = models.IntegerField('Месяц')
    income = models.DecimalField(
        'Среднедушевой доход',
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
        help_text='Среднедушевой доход получателя социальных услуг'
    )
    pension_payment = models.DecimalField(
        'Перечислено ПФ',
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
        help_text='Фактически перечислено Пенсионным фондом в ДСО'
    )
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)
    
    class Meta:
        verbose_name = 'Данные проживающего по месяцам'
        verbose_name_plural = 'Данные проживающих по месяцам'
        unique_together = ['recipient', 'year', 'month']
        ordering = ['-year', '-month', 'recipient']
    
    def __str__(self):
        return f"{self.recipient} - {self.month:02d}.{self.year}"
