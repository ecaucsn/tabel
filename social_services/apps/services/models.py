from django.db import models
from django.conf import settings
from apps.core.models import Department


class ServiceSchedule(models.Model):
    """Расписание оказания услуг по дням недели для отделений"""
    
    DAYS_OF_WEEK = [
        (0, 'Понедельник'),
        (1, 'Вторник'),
        (2, 'Среда'),
        (3, 'Четверг'),
        (4, 'Пятница'),
        (5, 'Суббота'),
        (6, 'Воскресенье'),
    ]
    
    service = models.ForeignKey(
        'Service',
        on_delete=models.CASCADE,
        related_name='schedules',
        verbose_name='Услуга'
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='service_schedules',
        verbose_name='Отделение'
    )
    day_of_week = models.IntegerField(
        'День недели',
        choices=DAYS_OF_WEEK,
        help_text='День недели, в который оказывается услуга'
    )
    quantity = models.PositiveIntegerField(
        'Количество',
        default=1,
        help_text='Количество оказаний услуги в этот день'
    )
    
    class Meta:
        verbose_name = 'Расписание услуги'
        verbose_name_plural = 'Расписания услуг'
        ordering = ['department', 'day_of_week', 'service']
        unique_together = ['service', 'department', 'day_of_week']
    
    def __str__(self):
        return f"{self.service} - {self.department} - {self.get_day_of_week_display()}"


class ServiceFrequency(models.Model):
    """Периодичность оказания услуги (норматив)"""
    
    PERIOD_TYPES = [
        ('day', 'В день'),
        ('week', 'В неделю'),
        ('month', 'В месяц'),
        ('year', 'В год'),
    ]
    
    name = models.CharField('Название', max_length=100, help_text='Например: "ежедневно", "1 в месяц"')
    short_name = models.CharField('Краткое название', max_length=30, help_text='Для отображения в таблицах')
    period_type = models.CharField(
        'Тип периода',
        max_length=10,
        choices=PERIOD_TYPES,
        default='month',
        help_text='Период, за который считается количество оказаний'
    )
    times_per_period = models.PositiveIntegerField(
        'Раз за период',
        null=True,
        blank=True,
        help_text='Количество раз за указанный период. Оставьте пустым для снятия ограничения.'
    )
    is_approximate = models.BooleanField(
        'Приблизительный норматив',
        default=False,
        help_text='Отмечает нормативы типа "до N раз" (жёлтый цвет в интерфейсе)'
    )
    order = models.PositiveIntegerField('Порядок', default=0)
    
    class Meta:
        verbose_name = 'Периодичность услуги'
        verbose_name_plural = 'Периодичности услуг'
        ordering = ['order', 'period_type', 'times_per_period']
    
    def __str__(self):
        return self.name
    
    @property
    def css_class(self):
        """CSS класс для отображения"""
        if self.is_approximate:
            return 'frequency-approximate'
        if self.times_per_period is None:
            return 'frequency-unlimited'
        return 'frequency-exact'
    
    def get_times_per_month(self):
        """Вычисляет количество раз в месяц на основе типа периода"""
        if self.times_per_period is None:
            return None
        
        if self.period_type == 'day':
            # Ежедневные услуги — без лимита (разное кол-во дней в месяце)
            return None
        elif self.period_type == 'week':
            # Неделя × 4 (приблизительно 4 недели в месяце)
            return self.times_per_period * 4
        elif self.period_type == 'month':
            return self.times_per_period
        elif self.period_type == 'year':
            # Год / 12 (округляем вверх для запаса)
            import math
            return math.ceil(self.times_per_period / 12)
        
        return None


class ServiceCategory(models.Model):
    """Категория социальных услуг"""
    name = models.CharField('Название категории', max_length=255)
    order = models.PositiveIntegerField('Порядок', default=0)
    
    class Meta:
        verbose_name = 'Категория услуг'
        verbose_name_plural = 'Категории услуг'
        ordering = ['order', 'name']
    
    def __str__(self):
        return self.name


class Service(models.Model):
    """Социальная услуга"""
    code = models.CharField('Код услуги', max_length=20, unique=True)
    name = models.CharField('Наименование услуги', max_length=500)
    category = models.ForeignKey(
        ServiceCategory,
        on_delete=models.CASCADE,
        related_name='services',
        verbose_name='Категория'
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='sub_services',
        verbose_name='Родительская услуга'
    )
    price = models.DecimalField(
        'Цена (руб.)',
        max_digits=10,
        decimal_places=2,
        default=0
    )
    frequency = models.ForeignKey(
        ServiceFrequency,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='services',
        verbose_name='Периодичность (норматив)',
        help_text='Норматив оказания услуги. Определяет лимит в месяц.'
    )
    max_quantity_per_month = models.PositiveIntegerField(
        'Макс. кол-во в месяц',
        null=True,
        blank=True,
        help_text='Ограничение на количество оказаний услуги в месяц. Заполняется автоматически из периодичности или вручную.'
    )
    order = models.PositiveIntegerField('Порядок', default=0)
    is_active = models.BooleanField('Активна', default=True)
    
    class Meta:
        verbose_name = 'Услуга'
        verbose_name_plural = 'Услуги'
        ordering = ['code', 'order']
    
    def __str__(self):
        return f"{self.code}. {self.name}"
    
    @property
    def is_sub_service(self):
        """Является ли подуслугой"""
        return self.parent is not None
    
    def get_full_code(self):
        """Возвращает полный код с учётом родителя"""
        if self.parent:
            return f"{self.parent.code}.{self.code}"
        return self.code
    
    def save(self, *args, **kwargs):
        # Автоматически заполняем max_quantity_per_month из периодичности
        if self.frequency:
            self.max_quantity_per_month = self.frequency.get_times_per_month()
        super().save(*args, **kwargs)
    
    @property
    def frequency_display(self):
        """Отображение периодичности для интерфейса"""
        if self.frequency:
            return self.frequency.short_name
        if self.max_quantity_per_month:
            return f"{self.max_quantity_per_month}/мес"
        return "без огр."


class ServiceLog(models.Model):
    """Запись в табеле об оказанной услуге"""
    recipient = models.ForeignKey(
        'recipients.Recipient',
        on_delete=models.CASCADE,
        related_name='service_logs',
        verbose_name='Получатель услуги'
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name='logs',
        verbose_name='Услуга'
    )
    provider = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='provided_services',
        verbose_name='Кто оказал услугу'
    )
    date = models.DateField('Дата оказания')
    quantity = models.DecimalField(
        'Количество',
        max_digits=5,
        decimal_places=0,
        default=1
    )
    # Цена копируется в момент записи для сохранения истории
    price_at_service = models.DecimalField(
        'Цена на момент оказания',
        max_digits=10,
        decimal_places=2,
        default=0
    )
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)
    
    class Meta:
        verbose_name = 'Запись табеля'
        verbose_name_plural = 'Записи табеля'
        ordering = ['-date', 'recipient', 'service']
        unique_together = ['recipient', 'service', 'date']
    
    def __str__(self):
        return f"{self.recipient} - {self.service} - {self.date}"
    
    def save(self, *args, **kwargs):
        # Копируем цену услуги в момент сохранения
        if not self.price_at_service and self.service:
            self.price_at_service = self.service.price
        super().save(*args, **kwargs)
    
    @property
    def total(self):
        """Итоговая сумма"""
        return self.quantity * self.price_at_service


class TabelLock(models.Model):
    """Блокировка редактирования табеля"""
    recipient = models.ForeignKey(
        'recipients.Recipient',
        on_delete=models.CASCADE,
        related_name='tabel_locks',
        verbose_name='Получатель услуги'
    )
    year = models.IntegerField('Год')
    month = models.IntegerField('Месяц')
    is_locked = models.BooleanField('Заблокировано', default=True)
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tabel_locks',
        verbose_name='Заблокировал'
    )
    locked_at = models.DateTimeField('Дата блокировки', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)
    
    class Meta:
        verbose_name = 'Блокировка табеля'
        verbose_name_plural = 'Блокировки табеля'
        unique_together = ['recipient', 'year', 'month']
        ordering = ['-year', '-month', 'recipient']
    
    def __str__(self):
        status = "🔒" if self.is_locked else "🔓"
        return f"{status} {self.recipient} - {self.month}.{self.year}"


class ServiceRecipient(models.Model):
    """Назначение услуги получателю"""
    
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name='service_recipients',
        verbose_name='Услуга'
    )
    recipient = models.ForeignKey(
        'recipients.Recipient',
        on_delete=models.CASCADE,
        related_name='assigned_services',
        verbose_name='Получатель услуги'
    )
    is_active = models.BooleanField(
        'Активно',
        default=True,
        help_text='Отключите, если получатель временно не получает услугу'
    )
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_service_recipients',
        verbose_name='Создал'
    )
    
    class Meta:
        verbose_name = 'Назначение услуги'
        verbose_name_plural = 'Назначения услуг'
        unique_together = ['service', 'recipient']
        ordering = ['service__code', 'recipient__last_name']
    
    def __str__(self):
        return f"{self.service.code} - {self.recipient.short_name}"


class ServiceRecipientLock(models.Model):
    """Блокировка конкретной услуги для получателя на месяц"""
    
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name='recipient_locks',
        verbose_name='Услуга'
    )
    recipient = models.ForeignKey(
        'recipients.Recipient',
        on_delete=models.CASCADE,
        related_name='service_locks',
        verbose_name='Получатель услуги'
    )
    year = models.IntegerField('Год')
    month = models.IntegerField('Месяц')
    is_locked = models.BooleanField('Заблокировано', default=True)
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='service_recipient_locks',
        verbose_name='Заблокировал'
    )
    locked_at = models.DateTimeField('Дата блокировки', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)
    
    class Meta:
        verbose_name = 'Блокировка услуги получателя'
        verbose_name_plural = 'Блокировки услуг получателей'
        unique_together = ['service', 'recipient', 'year', 'month']
        ordering = ['-year', '-month', 'service', 'recipient']
    
    def __str__(self):
        status = "🔒" if self.is_locked else "🔓"
        return f"{status} {self.service.code} - {self.recipient.short_name} - {self.month}.{self.year}"
