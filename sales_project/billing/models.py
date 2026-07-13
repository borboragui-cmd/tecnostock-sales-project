# Create your models here.
from django.db import models
from django.core.exceptions import ValidationError
from shared.validators import validate_cedula_ec, validate_only_letters

class Brand(models.Model):
    """Marcas de productos."""
    name = models.CharField(max_length=100, unique=True, verbose_name='Nombre de la marca')
    description = models.TextField(blank=True, null=True, verbose_name='Descripción')
    is_active = models.BooleanField(default=True, verbose_name='Activo')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        verbose_name = 'Brand'
        verbose_name_plural = 'Brands'
        ordering = ['name']
    def __str__(self): return self.name

class ProductGroup(models.Model):
    """Grupos/categorías de productos."""
    name = models.CharField(max_length=100, unique=True, verbose_name='Nombre del grupo')
    is_active = models.BooleanField(default=True, verbose_name='Activo')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        verbose_name = 'Product Group'
        verbose_name_plural = 'Product Groups'
        ordering = ['name']
    def __str__(self): return self.name

class Supplier(models.Model):
    """Proveedores. M2M con Product."""
    name = models.CharField(max_length=200, verbose_name='Nombre de la empresa')
    contact_name = models.CharField(max_length=200, blank=True, null=True, verbose_name='Nombre de contacto')
    email = models.EmailField(blank=True, null=True, verbose_name='Correo electrónico')
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name='Teléfono')
    address = models.TextField(blank=True, null=True, verbose_name='Dirección')
    is_active = models.BooleanField(default=True, verbose_name='Activo')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        verbose_name = 'Supplier'
        verbose_name_plural = 'Suppliers'
        ordering = ['name']
    def __str__(self): return self.name

class Product(models.Model):
    """Productos. FK a Brand/Group, M2M a Supplier."""
    name = models.CharField(max_length=200, verbose_name='Product Name')
    description = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name='products')
    group = models.ForeignKey(ProductGroup, on_delete=models.PROTECT, related_name='products')
    suppliers = models.ManyToManyField(Supplier, related_name='products', blank=True)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    stock = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        ordering = ['name']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(stock__gte=0),
                name='product_stock_non_negative',
            )
        ]
    def __str__(self): return f'{self.name} ({self.brand.name})'

    @property  # Propiedad calculada, no se guarda en BD
    def balance(self):
        """Saldo en inventario = precio unitario * stock."""
        return self.unit_price * self.stock

class Customer(models.Model):
    """Clientes. OneToOne con CustomerProfile."""
    dni = models.CharField(
        max_length=13, 
        unique=True, 
        verbose_name='CI/RUC',
        validators=[validate_cedula_ec]  # ← MODIFICADO: agregado validador
    )
    first_name = models.CharField(max_length=100, verbose_name='Nombre', validators=[validate_only_letters])
    last_name = models.CharField(max_length=100, verbose_name='Apellido', validators=[validate_only_letters])
    email = models.EmailField(blank=True, null=True, verbose_name='Correo electrónico')
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name='Teléfono')
    address = models.TextField(blank=True, null=True, verbose_name='Dirección')
    is_active = models.BooleanField(default=True, verbose_name='Activo')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['last_name', 'first_name']
    def __str__(self): return f'{self.last_name}, {self.first_name}'
    @property
    def full_name(self): return f'{self.first_name} {self.last_name}'

class CustomerProfile(models.Model):
    """Perfil extendido. OneToOne con Customer."""
    TAXPAYER = [('final','Final Consumer'),('ruc','RUC'),('rise','RISE')]
    PAYMENT = [('cash','Cash'),('credit_15','15 days'),('credit_30','30 days'),('credit_60','60 days')]
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, related_name='profile')
    taxpayer_type = models.CharField(max_length=10, choices=TAXPAYER, default='final')
    payment_terms = models.CharField(max_length=15, choices=PAYMENT, default='cash')
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True, null=True)
    class Meta: verbose_name = 'Customer Profile'
    def __str__(self): return f'Profile: {self.customer}'

class Invoice(models.Model):
    """Cabecera de factura."""
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='invoices')
    invoice_date = models.DateTimeField(auto_now_add=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    class Meta: ordering = ['-invoice_date']
    def __str__(self): return f'Invoice #{self.id} - {self.customer}'

class InvoiceDetail(models.Model):
    """Líneas de factura."""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='details')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='invoice_details')
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    def __str__(self): return f'{self.product.name} x {self.quantity}'

    def clean(self):
        if not self.product_id or not self.quantity:
            return
        current_stock = Product.objects.values_list('stock', flat=True).get(pk=self.product_id)
        if self.quantity > current_stock:
            raise ValidationError({
                'quantity': (
                    f'"{self.product.name}" solo tiene {current_stock} '
                    f'unidad(es) en stock (pedido: {self.quantity}).'
                )
            })

    def save(self, *args, **kwargs):
        self.subtotal = self.quantity * self.unit_price
        super().save(*args, **kwargs)