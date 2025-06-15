from django import forms
from django.core.exceptions import ValidationError
from .models import FichierImporte, MappingColonne
import pandas as pd
import os


class FichierImporteForm(forms.ModelForm):
    class Meta:
        model = FichierImporte
        fields = ['type_fichier', 'fichier', 'nom_fichier']
        widgets = {
            'type_fichier': forms.Select(attrs={
                'class': 'form-select',
                'required': True
            }),
            'fichier': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.csv,.xlsx,.xls',
                'required': True
            }),
            'nom_fichier': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nom du fichier (optionnel - auto-détecté)',
                'maxlength': 255
            })
        }
        labels = {
            'type_fichier': 'Type de fichier',
            'fichier': 'Sélectionner le fichier',
            'nom_fichier': 'Nom du fichier'
        }

    def clean_fichier(self):
        fichier = self.cleaned_data.get('fichier')
        if not fichier:
            return fichier

        # Validation de l'extension
        ext = os.path.splitext(fichier.name)[1].lower()
        if ext not in ['.csv', '.xlsx', '.xls']:
            raise ValidationError("Format de fichier non autorisé. Utilisez CSV ou Excel.")

        # Validation de la taille
        if fichier.size > 30 * 1024 * 1024:  # 30MB
            raise ValidationError("Le fichier ne peut pas dépasser 30MB.")

        # Tentative de lecture pour validation basique
        try:
            if ext == '.csv':
                df = pd.read_csv(fichier, nrows=5)
            else:
                df = pd.read_excel(fichier, nrows=5)

            if df.empty:
                raise ValidationError("Le fichier semble vide.")

            # Reset file pointer
            fichier.seek(0)

        except Exception as e:
            raise ValidationError(f"Impossible de lire le fichier: {str(e)}")

        return fichier

    def clean(self):
        cleaned_data = super().clean()
        fichier = cleaned_data.get('fichier')
        nom_fichier = cleaned_data.get('nom_fichier')

        # Auto-générer le nom si pas fourni
        if fichier and not nom_fichier:
            cleaned_data['nom_fichier'] = os.path.splitext(fichier.name)[0]

        return cleaned_data


class ApprovalForm(forms.ModelForm):
    """Formulaire pour approuver/rejeter un fichier"""
    commentaire = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Commentaire sur la validation...'
        }),
        required=False,
        label="Commentaire"
    )

    class Meta:
        model = FichierImporte
        fields = ['est_valide']
        widgets = {
            'est_valide': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }
        labels = {
            'est_valide': 'Approuver ce fichier'
        }


class MappingForm(forms.ModelForm):
    """Formulaire pour le mapping des colonnes"""

    class Meta:
        model = MappingColonne
        fields = ['colonne_fichier', 'colonne_attendue']
        widgets = {
            'colonne_fichier': forms.Select(attrs={'class': 'form-select'}),
            'colonne_attendue': forms.HiddenInput(),
        }


class FileSearchForm(forms.Form):
    """Formulaire de recherche et filtrage"""
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Rechercher par nom de fichier...'
        }),
        label="Recherche"
    )

    type_fichier = forms.ChoiceField(
        required=False,
        choices=[('', 'Tous les types')] + FichierImporte.TYPES_FICHIER,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Type de fichier"
    )

    status = forms.ChoiceField(
        required=False,
        choices=[('', 'Tous les statuts')] + FichierImporte.STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Statut"
    )

    date_debut = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        label="Date de début"
    )

    date_fin = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        label="Date de fin"
    )
