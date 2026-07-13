from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from .models import Purchase, PurchaseDetail


class PurchaseForm(forms.ModelForm):
    class Meta:
        model = Purchase
        fields = ['supplier', 'document_number']
        widgets = {
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'document_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: FAC-001',
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        supplier = cleaned_data.get('supplier')
        document_number = cleaned_data.get('document_number')

        if supplier and document_number:
            qs = Purchase.objects.filter(supplier=supplier, document_number=document_number)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(
                    f'Ya existe una compra con el N° "{document_number}" '
                    f'para el proveedor "{supplier}". Verifique el número de documento.'
                )
        return cleaned_data


PurchaseDetailFormSet = inlineformset_factory(
    Purchase,
    PurchaseDetail,
    fields=['product', 'quantity', 'unit_cost'],
    extra=3,
    can_delete=True,
    widgets={
        'product': forms.Select(attrs={'class': 'form-select'}),
        'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        'unit_cost': forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'min': '0.01',
            'placeholder': 'Ej: 12.50',
        }),
    }
)
