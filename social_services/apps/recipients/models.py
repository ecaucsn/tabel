from django.db import models
from django.conf import settings
from apps.core.models import Department, LocationType


def recipient_photo_path(instance, filename):
    """Путь для сохранения фото получателя"""
    return f'recipients/photos/{instance.id}/{filename}'


class Recipient(models.Model):
    """Получатель социальных услуг (ПСУ)"""
    
    PLACEMENT_CHOICES = [
        ('internat', 'Интернат'),
        ('vacation', 'Отпуск'),
        ('hospital', 'Больница'),
        ('discharged', 'Выбыл'),
    ]
    
    # Поля для совместимости со старым кодом
    STATUS_CHOICES = PLACEMENT_CHOICES  # Алиас для обратной совместимости
    
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
    
    # Тип местоположения (новое поле)
    location_type = models.ForeignKey(
        LocationType,
        on_delete=models.PROTECT,
        related_name='recipients',
        verbose_name='Местоположение',
        null=True,
        blank=True,
        help_text='Текущее местоположение проживающего'
    )
    
    # Актуальное размещение - сохраняем для совместимости
    placement = models.CharField(
        'Размещение (устарело)',
        max_length=20,
        choices=PLACEMENT_CHOICES,
        default='internat',
        help_text='Используйте location_type'
    )
    
    # Отделение и комната - только для размещения "Интернат"
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
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
        """Статус для совместимости - возвращает placement"""
        return self.placement
    
    @property
    def placement_display(self):
        """Отображение размещения"""
        placement_dict = dict(self.PLACEMENT_CHOICES)
        return placement_dict.get(self.placement, 'Проживает')
    
    @property
    def status_display(self):
        """Отображение статуса для совместимости"""
        return self.placement_display
    
    def get_status_display(self):
        """Отображение статуса (для совместимости)"""
        return self.placement_display
    
    def get_placement_display(self):
        """Отображение размещения (для шаблонов)"""
        return self.placement_display
    
    def get_current_placement(self):
        """
        Возвращает актуальное размещение на основе самой поздней даты в истории.
        Если записей истории нет - возвращает текущее поле placement.
        """
        from datetime import date
        
        latest_history = self.history.filter(date__lte=date.today()).order_by('-date').first()
        
        if latest_history and latest_history.new_placement:
            return latest_history.new_placement
        
        return self.placement
    
    def get_current_department(self):
        """
        Возвращает актуальное отделение на основе самой поздней даты в истории.
        Только для размещения 'internat'.
        """
        from datetime import date
        
        # Если текущее размещение не интернат - отделения нет
        current_placement = self.get_current_placement()
        if current_placement != 'internat':
            return None
        
        latest_history = self.history.filter(date__lte=date.today()).order_by('-date').first()
        
        if latest_history and latest_history.new_department:
            return latest_history.new_department
        
        return self.department
    
    def get_current_room(self):
        """
        Возвращает актуальную комнату на основе самой поздней даты в истории.
        Только для размещения 'internat'.
        """
        from datetime import date
        
        # Если текущее размещение не интернат - комнаты нет
        current_placement = self.get_current_placement()
        if current_placement != 'internat':
            return ''
        
        latest_history = self.history.filter(date__lte=date.today()).order_by('-date').first()
        
        if latest_history and latest_history.new_room is not None:
            return latest_history.new_room
        
        return self.room
    
    def set_department(self, new_department, user=None, reason=''):
        """Меняет отделение и записывает историю"""
        from datetime import date
        old_department = self.department
        old_status = self.status
        old_room = self.room
        
        self.department = new_department
        self.save()
        
        today = date.today()
        # Удаляем существующие записи с той же датой (принцип "одна запись - одна дата")
        RecipientHistory.objects.filter(
            recipient=self,
            date=today
        ).delete()
        
        # Создаем единую запись в истории
        RecipientHistory.objects.create(
            recipient=self,
            old_department=old_department,
            new_department=new_department,
            old_room=old_room,
            new_room=self.room,
            old_status=old_status,
            new_status=self.status,
            reason=reason,
            date=today,
            changed_by=user
        )
    
    def register_placement_change(self, old_department=None, new_department=None,
                                   old_room=None, new_room=None,
                                   old_status=None, new_status=None,
                                   reason='', date=None, user=None):
        """Регистрирует изменение размещения"""
        from datetime import date as date_module
        if date is None:
            date = date_module.today()
        
        # Удаляем существующие записи с той же датой (принцип "одна запись - одна дата")
        RecipientHistory.objects.filter(
            recipient=self,
            date=date
        ).delete()
        
        RecipientHistory.objects.create(
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


class RecipientHistory(models.Model):
    """Единая история изменений получателя услуг (размещение, отделения, комнаты)"""
    
    CHANGE_TYPE_CHOICES = [
        ('placement_change', 'Изменение размещения'),
        ('transfer', 'Перевод между отделениями'),
        ('room_change', 'Смена комнаты'),
        ('admission', 'Заселение'),
        ('discharge', 'Выбытие'),
    ]
    
    recipient = models.ForeignKey(
        Recipient,
        on_delete=models.CASCADE,
        related_name='history',
        verbose_name='Получатель услуг'
    )
    
    # Размещение - основное поле
    old_placement = models.CharField(
        'Предыдущее размещение',
        max_length=20,
        choices=Recipient.PLACEMENT_CHOICES,
        null=True,
        blank=True
    )
    new_placement = models.CharField(
        'Новое размещение',
        max_length=20,
        choices=Recipient.PLACEMENT_CHOICES,
        null=True,
        blank=True
    )
    
    # Отделение и комната - только для internat
    old_department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='history_departures',
        verbose_name='Предыдущее отделение'
    )
    new_department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='history_arrivals',
        verbose_name='Новое отделение'
    )
    old_room = models.CharField('Предыдущая комната', max_length=20, blank=True, null=True)
    new_room = models.CharField('Новая комната', max_length=20, blank=True, null=True)
    
    # Поля для совместимости со старыми данными
    old_status = models.CharField(
        'Предыдущий статус (устарело)',
        max_length=20,
        choices=Recipient.STATUS_CHOICES,
        null=True,
        blank=True
    )
    new_status = models.CharField(
        'Новый статус (устарело)',
        max_length=20,
        choices=Recipient.STATUS_CHOICES,
        null=True,
        blank=True
    )
    
    reason = models.TextField('Причина/Комментарий', blank=True)
    date = models.DateField('Дата изменения')
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Кто изменил'
    )
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    
    class Meta:
        verbose_name = 'История изменений'
        verbose_name_plural = 'История изменений'
        ordering = ['-date', '-created_at']
    
    def __str__(self):
        return f"{self.recipient} - {self.date:%d.%m.%Y} ({self.change_type_display})"
    
    @property
    def change_type(self):
        """Определяет тип изменения"""
        # Приоритет: размещение -> отделение -> комната
        if self.old_placement != self.new_placement and self.old_placement is not None:
            if self.new_placement == 'discharged':
                return 'discharge'
            elif self.old_placement == 'discharged' or self.old_placement is None:
                return 'admission'
            return 'placement_change'
        
        if self.old_department != self.new_department and self.old_department is not None:
            if self.new_department is None:
                return 'discharge'
            return 'transfer'
        
        if self.old_room != self.new_room and self.old_room is not None:
            return 'room_change'
        
        return 'placement_change'
    
    @property
    def change_type_display(self):
        """Отображение типа изменения"""
        return dict(self.CHANGE_TYPE_CHOICES).get(self.change_type, 'Изменение')
    
    def get_placement_display_value(self, placement_code):
        """Возвращает отображаемое значение размещения"""
        return dict(Recipient.PLACEMENT_CHOICES).get(placement_code, placement_code or '')


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
        verbose_name = 'Финансовые записи в акте'
        verbose_name_plural = 'Финансовые записи в акте'
        unique_together = ['recipient', 'year', 'month']
        ordering = ['-year', '-month', 'recipient']
    
    def __str__(self):
        return f"{self.recipient} - {self.month:02d}.{self.year}"
