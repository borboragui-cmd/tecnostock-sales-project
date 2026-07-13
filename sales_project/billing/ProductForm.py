from django import forms
from .models import Product

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'description', 'image', 'brand', 'group', 'suppliers', 'unit_price', 'stock', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter product name',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Enter a short product description',
            }),
            'brand': forms.Select(attrs={
                'class': 'form-select',
            }),
            'group': forms.Select(attrs={
                'class': 'form-select',
            }),
            'suppliers': forms.SelectMultiple(attrs={
                'class': 'form-select',
                'size': 5,
            }),
            'unit_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0.01',
            }),
            'stock': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0',
                'min': '0',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'image': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
            }),
        }

    def clean_unit_price(self):
        unit_price = self.cleaned_data.get('unit_price')
        if unit_price is not None and unit_price <= 0:
            raise forms.ValidationError('Unit price must be greater than 0.')
        return unit_price
