from django.db import models
from django.conf import settings
from apps.recipients.models import Recipient
import uuid
import qrcode
from io import BytesIO
from django.core.files.base import ContentFile


class Product(models.Model):
    """Продукт для пайка"""
    
    name = models.CharField('Наименование', max_length=200)
    unit = models.CharField('Единица измерения', max_length=50, default='шт.')
    price = models.DecimalField(
        'Цена за единицу',
        max_digits=10,
        decimal_places=2,
        help_text='Цена в рублях'
    )
    is_active = models.BooleanField('Активен', default=True)
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)
    
    class Meta:
        verbose_name = 'Продукт'
        verbose_name_plural = 'Продукты'
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.price} руб./{self.unit})"


class MonthlyRequest(models.Model):
    """Ежемесячная заявка на паёк"""
    
    STATUS_CHOICES = [
        ('draft', 'Черновик'),
        ('submitted', 'Подана'),
        ('approved', 'Утверждена'),
        ('completed', 'Выполнена'),
    ]
    
    recipient = models.ForeignKey(
        Recipient,
        on_delete=models.CASCADE,
        related_name='food_requests',
        verbose_name='Получатель услуг'
    )
    year = models.IntegerField('Год')
    month = models.IntegerField('Месяц')
    status = models.CharField(
        'Статус',
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft'
    )
    total_amount = models.DecimalField(
        'Общая сумма',
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text='Общая стоимость заявки'
    )
    notes = models.TextField('Примечания', blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_food_requests',
        verbose_name='Создал'
    )
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)
    
    class Meta:
        verbose_name = 'Заявка на паёк'
        verbose_name_plural = 'Заявки на паёк'
        ordering = ['-year', '-month', 'recipient']
        unique_together = ['recipient', 'year', 'month']
    
    def __str__(self):
        return f"Заявка {self.recipient} - {self.month:02d}.{self.year}"
    
    def calculate_total(self):
        """Пересчитывает общую сумму"""
        total = sum(
            item.quantity * item.price for item in self.items.all()
        )
        self.total_amount = total
        self.save(update_fields=['total_amount'])
        return total
    
    @property
    def month_name(self):
        """Название месяца"""
        months = {
            1: 'Январь', 2: 'Февраль', 3: 'Март', 4: 'Апрель',
            5: 'Май', 6: 'Июнь', 7: 'Июль', 8: 'Август',
            9: 'Сентябрь', 10: 'Октябрь', 11: 'Ноябрь', 12: 'Декабрь'
        }
        return months.get(self.month, str(self.month))


class RequestItem(models.Model):
    """Позиция в заявке на паёк"""
    
    request = models.ForeignKey(
        MonthlyRequest,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Заявка'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='request_items',
        verbose_name='Продукт'
    )
    quantity = models.DecimalField(
        'Количество',
        max_digits=10,
        decimal_places=2,
        default=1
    )
    price = models.DecimalField(
        'Цена за единицу',
        max_digits=10,
        decimal_places=2,
        help_text='Цена на момент добавления'
    )
    
    class Meta:
        verbose_name = 'Позиция заявки'
        verbose_name_plural = 'Позиции заявок'
        unique_together = ['request', 'product']
    
    def __str__(self):
        return f"{self.product.name} x {self.quantity}"
    
    @property
    def total(self):
        """Сумма позиции"""
        from decimal import Decimal
        return Decimal(str(self.quantity)) * self.price
    
    def save(self, *args, **kwargs):
        # Сохраняем текущую цену продукта при создании
        if not self.pk and not self.price:
            self.price = self.product.price
        super().save(*args, **kwargs)


class DigitalProfile(models.Model):
    """Цифровой профиль жителя"""
    
    recipient = models.OneToOneField(
        Recipient,
        on_delete=models.CASCADE,
        related_name='digital_profile',
        verbose_name='Получатель услуг'
    )
    unique_id = models.UUIDField(
        'Уникальный идентификатор',
        default=uuid.uuid4,
        editable=False,
        unique=True
    )
    qr_code = models.ImageField(
        'QR-код',
        upload_to='qr_codes/',
        blank=True,
        null=True
    )
    bio = models.TextField('Биография', blank=True, help_text='Краткая биография жителя')
    hobbies = models.CharField('Увлечения', max_length=500, blank=True)
    favorite_activities = models.TextField('Любимые занятия', blank=True)
    special_needs = models.TextField('Особые потребности', blank=True)
    dietary_restrictions = models.CharField('Диетические ограничения', max_length=500, blank=True)
    emergency_contact = models.CharField('Экстренный контакт', max_length=200, blank=True)
    emergency_phone = models.CharField('Телефон экстренного контакта', max_length=20, blank=True)
    medical_notes = models.TextField('Медицинские заметки', blank=True)
    is_public = models.BooleanField(
        'Публичный профиль',
        default=False,
        help_text='Доступен ли профиль для просмотра по QR-коду'
    )
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)
    
    class Meta:
        verbose_name = 'Цифровой профиль'
        verbose_name_plural = 'Цифровые профили'
    
    def __str__(self):
        return f"Профиль: {self.recipient}"
    
    def get_public_url(self, request=None):
        """Возвращает публичный URL профиля"""
        from django.urls import reverse
        url = reverse('modules:public_profile', kwargs={'profile_id': self.unique_id})
        if request:
            return request.build_absolute_uri(url)
        return url
    
    def generate_qr_code(self, request=None):
        """Генерирует QR-код для профиля"""
        url = self.get_public_url(request)
        
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Сохраняем в буфер
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        
        # Создаем файл
        filename = f'qr_{self.unique_id}.png'
        self.qr_code.save(
            filename,
            ContentFile(buffer.getvalue()),
            save=True
        )
        
        return self.qr_code
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Генерируем QR-код при создании, если его нет
        if not self.qr_code:
            self.generate_qr_code()


# ==================== Pension Models ====================

class PensionAccount(models.Model):
    """Пенсионный счёт проживающего"""
    
    recipient = models.OneToOneField(
        Recipient,
        on_delete=models.CASCADE,
        related_name='pension_account',
        verbose_name='Получатель услуг'
    )
    pension_type = models.CharField(
        'Тип пенсии',
        max_length=100,
        blank=True,
        help_text='Например: страховая, социальная, по инвалидности'
    )
    pension_number = models.CharField(
        'Номер пенсионного дела',
        max_length=50,
        blank=True
    )
    monthly_pension_amount = models.DecimalField(
        'Ежемесячная сумма пенсии',
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text='Базовая ежемесячная сумма пенсии'
    )
    balance = models.DecimalField(
        'Текущий баланс',
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text='Накопленная сумма на счёте'
    )
    notes = models.TextField('Примечания', blank=True)
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)
    
    class Meta:
        verbose_name = 'Пенсионный счёт'
        verbose_name_plural = 'Пенсионные счета'
    
    def __str__(self):
        return f"Пенсионный счёт: {self.recipient}"
    
    def get_monthly_accrual(self, year, month):
        """Получить начисление за месяц"""
        return self.accruals.filter(year=year, month=month).first()
    
    def get_monthly_expenses(self, year, month):
        """Получить расходы за месяц"""
        return self.expenses.filter(year=year, month=month)
    
    def get_monthly_expenses_total(self, year, month):
        """Общая сумма расходов за месяц"""
        return self.expenses.filter(year=year, month=month).aggregate(
            total=models.Sum('amount')
        )['total'] or 0
    
    def recalculate_balance(self):
        """Пересчитать баланс на основе всех операций"""
        from decimal import Decimal
        total_accruals = self.accruals.aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0')
        total_expenses = self.expenses.aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0')
        self.balance = total_accruals - total_expenses
        self.save(update_fields=['balance'])
        return self.balance


class PensionAccrual(models.Model):
    """Начисление пенсии"""
    
    account = models.ForeignKey(
        PensionAccount,
        on_delete=models.CASCADE,
        related_name='accruals',
        verbose_name='Пенсионный счёт'
    )
    year = models.IntegerField('Год')
    month = models.IntegerField('Месяц')
    amount = models.DecimalField(
        'Сумма начисления',
        max_digits=10,
        decimal_places=2,
        help_text='Сумма начисленной пенсии'
    )
    accrued_date = models.DateField(
        'Дата начисления',
        null=True,
        blank=True,
        help_text='Дата фактического начисления'
    )
    source = models.CharField(
        'Источник',
        max_length=100,
        blank=True,
        help_text='Например: ПФР, СФР'
    )
    notes = models.TextField('Примечания', blank=True)
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)
    
    class Meta:
        verbose_name = 'Начисление пенсии'
        verbose_name_plural = 'Начисления пенсий'
        unique_together = ['account', 'year', 'month']
        ordering = ['-year', '-month']
    
    def __str__(self):
        return f"Начисление {self.amount} руб. - {self.account.recipient} ({self.month:02d}.{self.year})"
    
    @property
    def month_name(self):
        """Название месяца"""
        months = {
            1: 'Январь', 2: 'Февраль', 3: 'Март', 4: 'Апрель',
            5: 'Май', 6: 'Июнь', 7: 'Июль', 8: 'Август',
            9: 'Сентябрь', 10: 'Октябрь', 11: 'Ноябрь', 12: 'Декабрь'
        }
        return months.get(self.month, str(self.month))
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Пересчитываем баланс счёта
        self.account.recalculate_balance()


class PensionExpense(models.Model):
    """Расход из пенсии"""
    
    CATEGORY_CHOICES = [
        ('food', 'Продукты питания'),
        ('medicine', 'Лекарства'),
        ('clothing', 'Одежда'),
        ('hygiene', 'Средства гигиены'),
        ('services', 'Услуги'),
        ('request', 'Исполнение заявки'),
        ('other', 'Прочее'),
    ]
    
    account = models.ForeignKey(
        PensionAccount,
        on_delete=models.CASCADE,
        related_name='expenses',
        verbose_name='Пенсионный счёт'
    )
    year = models.IntegerField('Год')
    month = models.IntegerField('Месяц')
    amount = models.DecimalField(
        'Сумма расхода',
        max_digits=10,
        decimal_places=2,
        help_text='Сумма списания'
    )
    category = models.CharField(
        'Категория',
        max_length=20,
        choices=CATEGORY_CHOICES,
        default='other'
    )
    description = models.TextField('Описание', blank=True)
    expense_date = models.DateField(
        'Дата расхода',
        null=True,
        blank=True
    )
    related_request = models.ForeignKey(
        MonthlyRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pension_expenses',
        verbose_name='Связанная заявка',
        help_text='Заявка на паёк, если расход связан с ней'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Создал'
    )
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)
    
    class Meta:
        verbose_name = 'Расход пенсии'
        verbose_name_plural = 'Расходы пенсий'
        ordering = ['-year', '-month', '-created_at']
    
    def __str__(self):
        return f"Расход {self.amount} руб. - {self.account.recipient} ({self.month:02d}.{self.year})"
    
    @property
    def month_name(self):
        """Название месяца"""
        months = {
            1: 'Январь', 2: 'Февраль', 3: 'Март', 4: 'Апрель',
            5: 'Май', 6: 'Июнь', 7: 'Июль', 8: 'Август',
            9: 'Сентябрь', 10: 'Октябрь', 11: 'Ноябрь', 12: 'Декабрь'
        }
        return months.get(self.month, str(self.month))
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Пересчитываем баланс счёта
        self.account.recalculate_balance()


class PensionSavings(models.Model):
    """Накопления пенсии (отложенные средства)"""
    
    account = models.ForeignKey(
        PensionAccount,
        on_delete=models.CASCADE,
        related_name='savings',
        verbose_name='Пенсионный счёт'
    )
    year = models.IntegerField('Год')
    month = models.IntegerField('Месяц')
    amount = models.DecimalField(
        'Сумма накопления',
        max_digits=10,
        decimal_places=2,
        help_text='Отложенная сумма'
    )
    purpose = models.CharField(
        'Цель накопления',
        max_length=200,
        blank=True,
        help_text='На что копятся средства'
    )
    notes = models.TextField('Примечания', blank=True)
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)
    
    class Meta:
        verbose_name = 'Накопление пенсии'
        verbose_name_plural = 'Накопления пенсий'
        unique_together = ['account', 'year', 'month']
        ordering = ['-year', '-month']
    
    def __str__(self):
        return f"Накопление {self.amount} руб. - {self.account.recipient} ({self.month:02d}.{self.year})"