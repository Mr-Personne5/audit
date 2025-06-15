# accounts/forms.py - VERSION FINALE CORRIGÉE
from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import CustomUser, Mission


class CustomUserCreationForm(UserCreationForm):
    """Formulaire de création d'utilisateur avec styling moderne"""
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    phone = forms.CharField(max_length=20, required=False)

    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'first_name', 'last_name', 'phone', 'role', 'mission')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Classes CSS modernes pour tous les champs
        field_classes = {
            'username': 'form-control-modern border-start-0',
            'email': 'form-control-modern border-start-0',
            'first_name': 'form-control-modern border-start-0',
            'last_name': 'form-control-modern border-start-0',
            'phone': 'form-control-modern border-start-0',
            'role': 'form-select form-control-modern',
            'mission': 'form-select form-control-modern',
            'password1': 'form-control-modern border-start-0',
            'password2': 'form-control-modern border-start-0',
        }

        for field_name, css_class in field_classes.items():
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update({
                    'class': css_class,
                    'style': 'border-radius: 0 12px 12px 0;' if 'border-start-0' in css_class else 'border-radius: 12px;'
                })

        # Missions actives seulement
        self.fields['mission'].queryset = Mission.objects.filter(is_active=True)
        self.fields['mission'].empty_label = "Sélectionner une mission (optionnel)"

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.phone = self.cleaned_data['phone']
        if commit:
            user.save()
        return user


class CustomUserChangeForm(UserChangeForm):
    """Formulaire de modification d'utilisateur"""

    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'first_name', 'last_name', 'phone', 'role', 'mission', 'is_active')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Retirer le champ password
        if 'password' in self.fields:
            del self.fields['password']

        # Classes CSS modernes
        field_classes = {
            'username': 'form-control-modern border-start-0',
            'email': 'form-control-modern border-start-0',
            'first_name': 'form-control-modern border-start-0',
            'last_name': 'form-control-modern border-start-0',
            'phone': 'form-control-modern border-start-0',
            'role': 'form-select form-control-modern',
            'mission': 'form-select form-control-modern',
        }

        for field_name, css_class in field_classes.items():
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update({
                    'class': css_class,
                    'style': 'border-radius: 0 12px 12px 0;' if 'border-start-0' in css_class else 'border-radius: 12px;'
                })

        self.fields['mission'].queryset = Mission.objects.filter(is_active=True)
        self.fields['mission'].empty_label = "Sélectionner une mission (optionnel)"


class MissionForm(forms.ModelForm):
    """Formulaire pour créer/modifier une mission"""

    class Meta:
        model = Mission
        fields = ['name', 'client', 'description', 'start_date', 'end_date', 'is_active']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Classes CSS modernes pour tous les champs
        field_classes = {
            'name': 'form-control-modern',
            'client': 'form-control-modern',
            'description': 'form-control-modern',
            'start_date': 'form-control-modern',
            'end_date': 'form-control-modern',
        }

        for field_name, css_class in field_classes.items():
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update({
                    'class': css_class,
                    'style': 'border-radius: 12px;'
                })
