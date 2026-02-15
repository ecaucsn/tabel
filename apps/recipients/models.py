from django.db import models
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
    status = models.CharField(
        'Статус',
        max_length=20,
        choices=STATUS_CHOICES,
        default='active'
    )
    admission_date = models.DateField('Дата заселения', null=True, blank=True)
    discharge_date = models.DateField('Дата выбытия', null=True, blank=True)
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
    max_quantity_per_month = models.PositiveIntegerField(
        'Макс. кол-во в месяц',
        null=True,
        blank=True,
        help_text='Ограничение на количество оказаний услуги в месяц. Оставьте пустым для снятия ограничения.'
    )
    
    class Meta:
        verbose_name = 'Услуга в ИППСУ'
        verbose_name_plural = 'Услуги в ИППСУ'
        unique_together = ['contract', 'service']
    
    def __str__(self):
        limit = f" (макс. {self.max_quantity_per_month}/мес)" if self.max_quantity_per_month else ""
        return f"{self.contract} - {self.service}{limit}"
