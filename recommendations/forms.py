# recommendations/forms.py - CORRIGER les imports et références

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Q  # ✅ AJOUTER l'import Q

from datetime import date, timedelta

from .models import Recommandation, ActionPlan, SuiviAvancement
from accounts.models import CustomUser as User, Mission  # ✅ CORRIGER l'import User


class RecommandationForm(forms.ModelForm):
    """Formulaire de création/modification de recommandation"""

    class Meta:
        model = Recommandation
        fields = [
            'titre', 'description', 'type_recommandation', 'priorite',
            'mission', 'date_echeance', 'date_debut_prevue',
            'duree_estimee_jours', 'impact_estime', 'tags'
        ]
        widgets = {
            'titre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Titre de la recommandation...',
                'maxlength': 255
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 6,
                'placeholder': 'Description détaillée de la recommandation...'
            }),
            'type_recommandation': forms.Select(attrs={
                'class': 'form-select'
            }),
            'priorite': forms.Select(attrs={
                'class': 'form-select'
            }),
            'mission': forms.Select(attrs={
                'class': 'form-select'
            }),
            'date_echeance': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'date_debut_prevue': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'duree_estimee_jours': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 365,
                'placeholder': 'Nombre de jours...'
            }),
            'impact_estime': forms.Select(attrs={
                'class': 'form-select'
            }),
            'tags': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Tags séparés par des virgules (ex: urgent, paie, formation)'
            })
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Filtrer les missions selon les permissions
        if self.user:
            if self.user.is_admin():
                self.fields['mission'].queryset = Mission.objects.all()
            else:
                if self.user.mission:  # ✅ Vérifier que l'utilisateur a une mission
                    self.fields['mission'].queryset = Mission.objects.filter(id=self.user.mission.id)
                    # Pré-sélectionner la mission de l'utilisateur
                    if not self.instance.pk:
                        self.fields['mission'].initial = self.user.mission
                else:
                    self.fields['mission'].queryset = Mission.objects.none()

        # Personnaliser les labels et help_text
        self.fields['titre'].help_text = "Titre concis et explicite de la recommandation"
        self.fields[
            'description'].help_text = "Description détaillée incluant le contexte, les actions à mener et les résultats attendus"
        self.fields['date_echeance'].help_text = "Date limite pour la réalisation de cette recommandation"
        self.fields[
            'duree_estimee_jours'].help_text = "Estimation du nombre de jours nécessaires pour réaliser cette recommandation"

        # Valeurs par défaut
        if not self.instance.pk:
            self.fields['priorite'].initial = 'moyenne'
            self.fields['impact_estime'].initial = 'moyen'

            # Date d'échéance par défaut selon la priorité
            today = timezone.now().date()
            self.fields['date_echeance'].initial = today + timedelta(days=30)

    def clean_date_echeance(self):
        date_echeance = self.cleaned_data.get('date_echeance')

        if date_echeance and date_echeance < timezone.now().date():
            raise ValidationError("La date d'échéance ne peut pas être dans le passé.")

        return date_echeance

    def clean_date_debut_prevue(self):
        date_debut_prevue = self.cleaned_data.get('date_debut_prevue')
        date_echeance = self.cleaned_data.get('date_echeance')

        if date_debut_prevue:
            if date_debut_prevue < timezone.now().date():
                raise ValidationError("La date de début ne peut pas être dans le passé.")

            if date_echeance and date_debut_prevue > date_echeance:
                raise ValidationError("La date de début ne peut pas être postérieure à l'échéance.")

        return date_debut_prevue

    def clean_tags(self):
        tags_str = self.cleaned_data.get('tags', '')

        if isinstance(tags_str, str):
            # Convertir la chaîne en liste
            tags_list = [tag.strip().lower() for tag in tags_str.split(',') if tag.strip()]
            return tags_list

        return tags_str or []


# recommendations/forms.py - AJOUTER les méthodes manquantes

class FilterRecommandationsForm(forms.Form):
    """Formulaire de filtres pour la liste des recommandations"""

    statut = forms.ChoiceField(
        choices=[('', 'Tous les statuts')] + Recommandation.STATUT_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    priorite = forms.ChoiceField(
        choices=[('', 'Toutes les priorités')] + Recommandation.PRIORITE_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    type_recommandation = forms.ChoiceField(
        choices=[('', 'Tous les types')] + Recommandation.TYPE_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    assigne_a = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label="Tous les assignés",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    date_creation_debut = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        label="Créé après le"
    )

    date_creation_fin = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        label="Créé avant le"
    )

    date_echeance_debut = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        label="Échéance après le"
    )

    date_echeance_fin = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        label="Échéance avant le"
    )

    recherche = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Rechercher dans titre, description, code...'
        }),
        label="Recherche"
    )

    def __init__(self, *args, **kwargs):
        mission = kwargs.pop('mission', None)
        super().__init__(*args, **kwargs)

        # Filtrer les utilisateurs selon la mission
        if mission:
            self.fields['assigne_a'].queryset = User.objects.filter(
                Q(mission=mission) | Q(role='admin')
            ).order_by('first_name', 'last_name')


class AssignationForm(forms.Form):
    """Formulaire d'assignation d'une recommandation"""

    assigne_a = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=True,
        empty_label="Sélectionner un utilisateur",
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Assigner à"
    )

    commentaire = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Commentaire sur l\'assignation (optionnel)...'
        }),
        label="Commentaire"
    )

    def __init__(self, *args, **kwargs):
        mission = kwargs.pop('mission', None)
        super().__init__(*args, **kwargs)

        if mission:
            self.fields['assigne_a'].queryset = User.objects.filter(
                Q(mission=mission) | Q(role='admin')  # ✅ Adapter selon votre modèle
            ).order_by('first_name', 'last_name')


class ActionPlanForm(forms.ModelForm):
    """Formulaire pour les actions du plan"""

    class Meta:
        model = ActionPlan
        fields = [
            'nom_action', 'description_action', 'date_debut_prevue',
            'date_fin_prevue', 'duree_estimee_heures', 'responsable'
        ]
        widgets = {
            'nom_action': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nom de l\'action...',
                'maxlength': 255
            }),
            'description_action': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Description détaillée de l\'action...'
            }),
            'date_debut_prevue': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'date_fin_prevue': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'duree_estimee_heures': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 1000,
                'placeholder': 'Heures...'
            }),
            'responsable': forms.Select(attrs={
                'class': 'form-select'
            })
        }

    def __init__(self, *args, **kwargs):
        recommandation = kwargs.pop('recommandation', None)
        super().__init__(*args, **kwargs)

        # Filtrer les responsables selon la mission
        if recommandation and recommandation.mission:
            self.fields['responsable'].queryset = User.objects.filter(
                Q(mission=recommandation.mission) | Q(role='admin')  # ✅ Adapter selon votre modèle
            ).order_by('first_name', 'last_name')

        self.fields['responsable'].empty_label = "Sélectionner un responsable"

    def clean(self):
        cleaned_data = super().clean()
        date_debut = cleaned_data.get('date_debut_prevue')
        date_fin = cleaned_data.get('date_fin_prevue')

        if date_debut and date_fin:
            if date_debut > date_fin:
                raise ValidationError("La date de début ne peut pas être postérieure à la date de fin.")

        return cleaned_data


class SuiviAvancementForm(forms.ModelForm):
    """Formulaire pour ajouter un suivi d'avancement"""

    class Meta:
        model = SuiviAvancement
        fields = ['description', 'commentaire_utilisateur']
        widgets = {
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Description de l\'événement...'
            }),
            'commentaire_utilisateur': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Commentaire (optionnel)...'
            })
        }


class ChangeStatutForm(forms.Form):
    """Formulaire pour changer le statut d'une recommandation"""

    nouveau_statut = forms.ChoiceField(
        choices=Recommandation.STATUT_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Nouveau statut"
    )

    commentaire = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Commentaire sur le changement de statut (optionnel)...'
        }),
        label="Commentaire"
    )

    def __init__(self, *args, **kwargs):
        recommandation = kwargs.pop('recommandation', None)
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if recommandation:
            # Filtrer les statuts selon les transitions autorisées
            transitions_autorisees = {
                'draft': [('pending', 'En attente validation')],
                'pending': [('approved', 'Approuvée'), ('rejected', 'Rejetée')],
                'approved': [('assigned', 'Assignée')],
                'assigned': [('in_progress', 'En cours'), ('rejected', 'Rejetée')],
                'in_progress': [('completed', 'Terminée'), ('rejected', 'Rejetée')],
                'completed': [('in_progress', 'En cours')],  # Réouverture
                'rejected': [('pending', 'En attente validation')],
                'overdue': [('in_progress', 'En cours'), ('completed', 'Terminée')],
                'cancelled': []
            }

            choix_autorises = transitions_autorisees.get(recommandation.statut, [])

            # Filtrer selon les permissions utilisateur
            if user and not user.is_admin():
                if recommandation.statut == 'pending' and not recommandation.can_validate(user):
                    # Enlever l'option d'approbation si pas les permissions
                    choix_autorises = [(k, v) for k, v in choix_autorises if k != 'approved']

            self.fields['nouveau_statut'].choices = choix_autorises
            self.fields['nouveau_statut'].initial = recommandation.statut


# ✅ AJOUTER tous les autres formulaires manqués mais simplifiés

class BulkActionForm(forms.Form):
    """Formulaire pour les actions en lot sur les recommandations"""

    ACTION_CHOICES = [
        ('', 'Sélectionner une action'),
        ('assign', 'Assigner en lot'),
        ('change_priorite', 'Changer la priorité'),
        ('export', 'Exporter la sélection'),
    ]

    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Action à effectuer"
    )

    assigne_a = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label="Sélectionner un utilisateur",
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Assigner à"
    )

    nouvelle_priorite = forms.ChoiceField(
        choices=Recommandation.PRIORITE_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Nouvelle priorité"
    )

    recommandation_ids = forms.CharField(
        widget=forms.HiddenInput(),
        label="IDs des recommandations"
    )

    def __init__(self, *args, **kwargs):
        mission = kwargs.pop('mission', None)
        super().__init__(*args, **kwargs)

        if mission:
            self.fields['assigne_a'].queryset = User.objects.filter(
                Q(mission=mission) | Q(role='admin')  # ✅ Adapter selon votre modèle
            ).order_by('first_name', 'last_name')


class GenerationAutomatiqueForm(forms.Form):
    """Formulaire pour la génération automatique de recommandations"""

    SOURCE_CHOICES = [
        ('audit', 'Depuis session d\'audit IA'),
        ('rapprochement', 'Depuis session de rapprochement'),
        ('preventif', 'Recommandations préventives'),
    ]

    source = forms.ChoiceField(
        choices=SOURCE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Source de génération"
    )

    inclure_anomalies_critiques = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Inclure les anomalies critiques"
    )

    inclure_patterns = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Inclure les patterns récurrents"
    )
