from django.db import models
from django.conf import settings
from apps.core.models import Department


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
