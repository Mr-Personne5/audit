# auditengine/forms.py
from django import forms
from django.core.exceptions import ValidationError

from .models import (
    SessionAudit, CorrectionUtilisateur, ParametrageIA,
    ResultatAudit
)
from uploads.models import FichierImporte


class SessionAuditForm(forms.ModelForm):
    """Formulaire pour créer une session d'audit IA"""

    class Meta:
        model = SessionAudit
        fields = [
            'nom_session', 'description', 'mission', 'fichier_paie'
        ]
        widgets = {
            'nom_session': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nom de la session d\'audit IA',
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
            'fichier_paie': forms.Select(attrs={
                'class': 'form-select',
                'required': True
            })
        }
        labels = {
            'nom_session': 'Nom de la session',
            'description': 'Description',
            'mission': 'Mission',
            'fichier_paie': 'Fichier de paie à analyser'
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

            # Fichiers de paie approuvés
            queryset_paie = FichierImporte.objects.filter(
                type_fichier='paie',
                status='approved'
            )
            if mission:
                queryset_paie = queryset_paie.filter(mission=mission)

            self.fields['fichier_paie'].queryset = queryset_paie
            self.fields['fichier_paie'].empty_label = "Sélectionner un fichier de paie..."

    def clean(self):
        cleaned_data = super().clean()
        fichier_paie = cleaned_data.get('fichier_paie')
        mission = cleaned_data.get('mission')

        # Vérifier que le fichier appartient à la mission
        if fichier_paie and mission:
            if fichier_paie.mission != mission:
                raise ValidationError({
                    'fichier_paie': 'Ce fichier n\'appartient pas à la mission sélectionnée.'
                })

        return cleaned_data


class CorrectionForm(forms.ModelForm):
    """Formulaire pour corriger une anomalie détectée"""

    class Meta:
        model = CorrectionUtilisateur
        fields = [
            'type_correction', 'nouveau_est_anomalie', 'nouveau_type_anomalie',
            'nouveau_niveau_risque', 'justification', 'confiance_utilisateur'
        ]
        widgets = {
            'type_correction': forms.Select(attrs={
                'class': 'form-select',
                'required': True
            }),
            'nouveau_est_anomalie': forms.Select(
                choices=[(None, '--- Garder la valeur actuelle ---'), (True, 'Oui'), (False, 'Non')],
                attrs={'class': 'form-select'}
            ),
            'nouveau_type_anomalie': forms.Select(attrs={
                'class': 'form-select'
            }),
            'nouveau_niveau_risque': forms.Select(attrs={
                'class': 'form-select'
            }),
            'justification': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Expliquez votre correction pour améliorer l\'IA...',
                'required': True
            }),
            'confiance_utilisateur': forms.Select(
                choices=[(i, f'{i}/10') for i in range(1, 11)],
                attrs={'class': 'form-select'}
            )
        }
        labels = {
            'type_correction': 'Type de correction',
            'nouveau_est_anomalie': 'Est-ce vraiment une anomalie ?',
            'nouveau_type_anomalie': 'Nouveau type d\'anomalie',
            'nouveau_niveau_risque': 'Nouveau niveau de risque',
            'justification': 'Justification de la correction',
            'confiance_utilisateur': 'Votre niveau de confiance'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Choix dynamiques pour les nouveaux types/niveaux
        type_choices = [('', '--- Garder le type actuel ---')] + list(ResultatAudit.TYPE_ANOMALIE_CHOICES)
        niveau_choices = [('', '--- Garder le niveau actuel ---')] + list(ResultatAudit.NIVEAU_RISQUE_CHOICES)

        self.fields['nouveau_type_anomalie'].choices = type_choices
        self.fields['nouveau_niveau_risque'].choices = niveau_choices

    def clean(self):
        cleaned_data = super().clean()
        type_correction = cleaned_data.get('type_correction')

        # Validations spécifiques selon le type de correction
        if type_correction == 'fausse_alerte':
            cleaned_data['nouveau_est_anomalie'] = False
            cleaned_data['nouveau_type_anomalie'] = 'aucune'

        elif type_correction == 'vraie_anomalie':
            cleaned_data['nouveau_est_anomalie'] = True
            if not cleaned_data.get('nouveau_type_anomalie'):
                raise ValidationError({
                    'nouveau_type_anomalie': 'Vous devez spécifier le type d\'anomalie.'
                })

        return cleaned_data


class ParametrageIAForm(forms.ModelForm):
    """Formulaire pour configurer les paramètres IA"""

    class Meta:
        model = ParametrageIA
        fields = [
            'seuil_isolation_forest', 'score_minimum_classification',
            'utiliser_modele_global', 'reentrainement_auto',
            'nb_anomalies_max_tableau_de_bord', 'afficher_explications'
        ]
        widgets = {
            'seuil_isolation_forest': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'max': '1'
            }),
            'score_minimum_classification': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'max': '1'
            }),
            'utiliser_modele_global': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'reentrainement_auto': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'nb_anomalies_max_tableau_de_bord': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '10',
                'max': '200'
            }),
            'afficher_explications': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }
        labels = {
            'seuil_isolation_forest': 'Seuil Isolation Forest (0-1)',
            'score_minimum_classification': 'Score minimum MLP (0-1)',
            'utiliser_modele_global': 'Utiliser le modèle global',
            'reentrainement_auto': 'Réentraînement automatique',
            'nb_anomalies_max_tableau_de_bord': 'Nb max anomalies tableau de bord',
            'afficher_explications': 'Afficher les explications IA'
        }
        help_texts = {
            'seuil_isolation_forest': 'Plus la valeur est faible, plus le modèle sera strict',
            'score_minimum_classification': 'Score minimum pour valider une classification MLP',
            'utiliser_modele_global': 'Si désactivé, privilégier les modèles spécifiques par mission',
            'reentrainement_auto': 'Réentraîner automatiquement avec les corrections',
            'nb_anomalies_max_tableau_de_bord': 'Nombre maximum d\'anomalies à afficher sur le tableau de bord',
            'afficher_explications': 'Afficher les explications des décisions IA'
        }


class FilterResultsForm(forms.Form):
    """Formulaire pour filtrer les résultats d'audit"""

    type_anomalie = forms.ChoiceField(
        required=False,
        choices=[('', 'Tous les types')] + ResultatAudit.TYPE_ANOMALIE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Type d'anomalie"
    )

    niveau_risque = forms.ChoiceField(
        required=False,
        choices=[('', 'Tous les niveaux')] + ResultatAudit.NIVEAU_RISQUE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Niveau de risque"
    )

    anomalie_detectee = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'Tous'),
            ('oui', 'Anomalies seulement'),
            ('non', 'Normaux seulement')
        ],
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Anomalie détectée"
    )

    score_if_min = forms.FloatField(
        required=False,
        min_value=0,
        max_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Score IF minimum...',
            'step': '0.01'
        }),
        label="Score IF minimum"
    )

    score_mlp_min = forms.FloatField(
        required=False,
        min_value=0,
        max_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Score MLP minimum...',
            'step': '0.01'
        }),
        label="Score MLP minimum"
    )

    valide_seulement = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Validés par humain seulement"
    )

    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Rechercher nom, prénom, matricule...'
        }),
        label="Recherche"
    )


class BulkCorrectionForm(forms.Form):
    """Formulaire pour correction en lot d'anomalies"""

    resultats_ids = forms.CharField(
        widget=forms.HiddenInput(),
        help_text="IDs des résultats sélectionnés (séparés par des virgules)"
    )

    action_globale = forms.ChoiceField(
        choices=[
            ('marquer_fausse_alerte', 'Marquer comme fausses alertes'),
            ('valider_anomalies', 'Valider comme vraies anomalies'),
            ('changer_type', 'Changer le type d\'anomalie'),
            ('changer_niveau', 'Changer le niveau de risque'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Action à effectuer"
    )

    nouveau_type_global = forms.ChoiceField(
        required=False,
        choices=ResultatAudit.TYPE_ANOMALIE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Nouveau type (si applicable)"
    )

    nouveau_niveau_global = forms.ChoiceField(
        required=False,
        choices=ResultatAudit.NIVEAU_RISQUE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Nouveau niveau (si applicable)"
    )

    justification_globale = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Justification pour la correction en lot...'
        }),
        label="Justification"
    )

    confiance_globale = forms.ChoiceField(
        choices=[(i, f'{i}/10') for i in range(1, 11)],
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Niveau de confiance"
    )

    def clean_resultats_ids(self):
        """Valide et convertit les IDs en liste d'entiers"""
        ids_str = self.cleaned_data['resultats_ids']
        if not ids_str:
            raise ValidationError("Aucun résultat sélectionné")

        try:
            ids_list = [int(id_str.strip()) for id_str in ids_str.split(',') if id_str.strip()]
            if not ids_list:
                raise ValidationError("Aucun résultat valide sélectionné")
            return ids_list
        except ValueError:
            raise ValidationError("Format d'IDs invalide")

    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get('action_globale')

        # Validations spécifiques selon l'action
        if action == 'changer_type' and not cleaned_data.get('nouveau_type_global'):
            raise ValidationError({
                'nouveau_type_global': 'Vous devez spécifier le nouveau type.'
            })

        if action == 'changer_niveau' and not cleaned_data.get('nouveau_niveau_global'):
            raise ValidationError({
                'nouveau_niveau_global': 'Vous devez spécifier le nouveau niveau.'
            })

        return cleaned_data


class RetrainModelForm(forms.Form):
    """Formulaire pour lancer le réentraînement des modèles"""

    type_modele = forms.ChoiceField(
        choices=[
            ('both', 'Les deux modèles (IF + MLP)'),
            ('isolation_forest', 'Isolation Forest seulement'),
            ('mlp_classifier', 'MLP Classifier seulement'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Modèles à réentraîner"
    )

    mission = forms.ModelChoiceField(
        queryset=None,  # Sera défini dans __init__
        required=False,
        empty_label="Modèle global (toutes missions)",
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Mission spécifique"
    )

    confirmation = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Je confirme vouloir lancer le réentraînement"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Charger les missions disponibles
        from accounts.models import Mission
        self.fields['mission'].queryset = Mission.objects.all()


class ModelEvaluationForm(forms.Form):
    """Formulaire pour évaluer un modèle"""

    modele = forms.ModelChoiceField(
        queryset=None,  # Sera défini dans __init__
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Modèle à évaluer"
    )

    utiliser_donnees_test = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Utiliser les données de test (validées par humains)"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Charger les modèles disponibles
        from .models import ModeleIA
        self.fields['modele'].queryset = ModeleIA.objects.filter(est_actif=True)
