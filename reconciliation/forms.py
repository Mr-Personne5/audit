# reconciliation/forms.py
from django import forms
from django.core.exceptions import ValidationError

from .models import RapprochementSession, RegleValidation
from uploads.models import FichierImporte


class RapprochementSessionForm(forms.ModelForm):
    """Formulaire pour créer une session de rapprochement"""

    class Meta:
        model = RapprochementSession
        fields = [
            'nom_session', 'description', 'mission',
            'fichier_liste_personnel', 'fichier_paie'
        ]
        widgets = {
            'nom_session': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nom de la session de rapprochement',
                'required': True
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Description optionnelle...'
            }),
            'mission': forms.Select(attrs={
                'class': 'form-select'
            }),
            'fichier_liste_personnel': forms.Select(attrs={
                'class': 'form-select',
                'required': True
            }),
            'fichier_paie': forms.Select(attrs={
                'class': 'form-select',
                'required': True
            })
        }
        labels = {
            'nom_session': 'Nom de la session',
            'description': 'Description',
            'mission': 'Mission',
            'fichier_liste_personnel': 'Fichier liste du personnel (RH)',
            'fichier_paie': 'Fichier de paie'
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user:
            # Filtrer les missions selon les permissions
            if user.is_admin():
                # Admin voit toutes les missions
                pass  # Garder le queryset par défaut
            else:
                # Utilisateur normal ne voit que sa mission
                if user.mission:
                    self.fields['mission'].queryset = self.fields['mission'].queryset.filter(
                        id=user.mission.id
                    )
                    self.fields['mission'].initial = user.mission
                else:
                    self.fields['mission'].queryset = self.fields['mission'].queryset.none()

            # Filtrer les fichiers selon la mission
            mission = user.mission if not user.is_admin() else None

            # Fichiers RH (liste personnel)
            queryset_rh = FichierImporte.objects.filter(
                type_fichier='liste_personnel',
                status='approved'
            )
            if mission:
                queryset_rh = queryset_rh.filter(mission=mission)

            self.fields['fichier_liste_personnel'].queryset = queryset_rh
            self.fields['fichier_liste_personnel'].empty_label = "Sélectionner un fichier RH..."

            # Fichiers Paie
            queryset_paie = FichierImporte.objects.filter(
                type_fichier='paie',
                status='approved'
            )
            if mission:
                queryset_paie = queryset_paie.filter(mission=mission)

            self.fields['fichier_paie'].queryset = queryset_paie
            self.fields['fichier_paie'].empty_label = "Sélectionner un fichier paie..."

    def clean(self):
        cleaned_data = super().clean()
        fichier_rh = cleaned_data.get('fichier_liste_personnel')
        fichier_paie = cleaned_data.get('fichier_paie')
        mission = cleaned_data.get('mission')

        # Vérifier que les fichiers appartiennent à la même mission
        if fichier_rh and fichier_paie and mission:
            if fichier_rh.mission != mission:
                raise ValidationError({
                    'fichier_liste_personnel': 'Ce fichier n\'appartient pas à la mission sélectionnée.'
                })
            if fichier_paie.mission != mission:
                raise ValidationError({
                    'fichier_paie': 'Ce fichier n\'appartient pas à la mission sélectionnée.'
                })

        # Vérifier que les fichiers sont différents
        if fichier_rh and fichier_paie and fichier_rh == fichier_paie:
            raise ValidationError('Vous devez sélectionner deux fichiers différents.')

        return cleaned_data


class FilterResultsForm(forms.Form):
    """Formulaire pour filtrer les résultats de rapprochement"""

    type_match = forms.ChoiceField(
        required=False,
        choices=[('', 'Tous les types')] + RapprochementSession.STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Type de match"
    )

    critere_match = forms.ChoiceField(
        required=False,
        choices=[('', 'Tous les critères')] + [
            ('matricule', 'Matricule'),
            ('nom_prenom_ddn', 'Nom + Prénom'),
            ('rib', 'RIB'),
            ('aucun', 'Aucun')
        ],
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Critère de match"
    )

    score_min = forms.FloatField(
        required=False,
        min_value=0,
        max_value=100,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Score minimum...',
            'step': '0.1'
        }),
        label="Score minimum"
    )

    ecart_salaire = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'Tous'),
            ('positif', 'Écart positif'),
            ('negatif', 'Écart négatif'),
            ('nul', 'Pas d\'écart')
        ],
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Écart salarial"
    )

    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Rechercher nom, prénom, matricule...'
        }),
        label="Recherche"
    )


class RegleValidationForm(forms.ModelForm):
    """Formulaire pour configurer les règles de validation (futur)"""

    class Meta:
        model = RegleValidation
        fields = [
            'type_regle', 'nom_regle', 'description',
            'valeur_numerique', 'valeur_texte', 'est_active'
        ]
        widgets = {
            'type_regle': forms.Select(attrs={'class': 'form-select'}),
            'nom_regle': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'valeur_numerique': forms.NumberInput(attrs={'class': 'form-control'}),
            'valeur_texte': forms.TextInput(attrs={'class': 'form-control'}),
            'est_active': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }
