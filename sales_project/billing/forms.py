from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.forms import inlineformset_factory
from .models import Brand, Invoice, InvoiceDetail
from shared.validators import validate_only_letters


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class': 'form-control'}))
    first_name = forms.CharField(
        max_length=100,
        validators=[validate_only_letters],
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    last_name = forms.CharField(
        max_length=100,
        validators=[validate_only_letters],
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields:
            self.fields[f].widget.attrs['class'] = 'form-control'


class BrandForm(forms.ModelForm):
    class Meta:
        model = Brand
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class InvoiceForm(forms.ModelForm):
    """Formulario para la cabecera de la factura (solo el cliente)."""
    class Meta:
        model = Invoice
        fields = ['customer']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
        }


# Formset para las líneas de detalle de la factura.
# extra=3 muestra 3 filas vacías; can_delete=True agrega checkbox para borrar filas.
InvoiceDetailFormSet = inlineformset_factory(
    Invoice,
    InvoiceDetail,
    fields=['product', 'quantity', 'unit_price'],
    extra=3,
    can_delete=True,
    widgets={
        'product': forms.Select(attrs={'class': 'form-select'}),
        'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
    }
)