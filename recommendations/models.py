# recommendations/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.urls import reverse

from datetime import datetime, timedelta
import json

from accounts.models import Mission



class Recommandation(models.Model):
    """Recommandation principale avec cycle de vie complet"""

    TYPE_CHOICES = [
        ('correctif', 'Action corrective'),
        ('preventif', 'Action préventive'),
        ('amelioration', 'Amélioration processus'),
        ('formation', 'Formation/Sensibilisation'),
        ('controle', 'Renforcement contrôles'),
        ('organisationnel', 'Changement organisationnel'),
        ('technique', 'Amélioration technique'),
    ]

    PRIORITE_CHOICES = [
        ('critique', '🔴 Critique'),
        ('haute', '🟠 Haute'),
        ('moyenne', '🟡 Moyenne'),
        ('basse', '🟢 Basse'),
    ]

    STATUT_CHOICES = [
        ('draft', 'Brouillon'),
        ('pending', 'En attente validation'),
        ('approved', 'Approuvée'),
        ('assigned', 'Assignée'),
        ('in_progress', 'En cours'),
        ('completed', 'Terminée'),
        ('rejected', 'Rejetée'),
        ('overdue', 'En retard'),
        ('cancelled', 'Annulée'),
    ]

    SOURCE_CHOICES = [
        ('auto_audit', 'Génération automatique - Audit IA'),
        ('auto_reconciliation', 'Génération automatique - Rapprochement'),
        ('auto_pattern', 'Génération automatique - Pattern'),
        ('manual_auditor', 'Saisie manuelle - Auditeur'),
        ('manual_manager', 'Saisie manuelle - Manager'),
        ('manual_rh', 'Saisie manuelle - RH'),
    ]

    # Identification
    code_recommandation = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="Code recommandation",
        help_text="Code unique auto-généré (ex: REC-2024-001)"
    )
    titre = models.CharField(max_length=255, verbose_name="Titre")
    description = models.TextField(verbose_name="Description détaillée")

    # Classification
    type_recommandation = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        verbose_name="Type"
    )
    priorite = models.CharField(
        max_length=10,
        choices=PRIORITE_CHOICES,
        verbose_name="Priorité"
    )
    statut = models.CharField(
        max_length=15,
        choices=STATUT_CHOICES,
        default='draft',
        verbose_name="Statut"
    )

    # Origine et contexte
    source = models.CharField(
        max_length=25,
        choices=SOURCE_CHOICES,
        verbose_name="Source de création"
    )
    mission = models.ForeignKey(
        Mission,
        on_delete=models.CASCADE,
        related_name='recommandations',
        verbose_name="Mission"
    )

    # Liens avec autres modules
    anomalie_liee = models.ForeignKey(
        'auditengine.ResultatAudit',  # ✅ Utiliser string au lieu d'import
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='recommandations',
        verbose_name="Anomalie liée"
    )
    session_audit_liee = models.ForeignKey(
        'auditengine.SessionAudit',  # ✅ Utiliser string
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='recommandations',
        verbose_name="Session d'audit liée"
    )
    session_rapprochement_liee = models.ForeignKey(
        'reconciliation.RapprochementSession',  # ✅ Utiliser string
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='recommandations',
        verbose_name="Session de rapprochement liée"
    )

    # Responsabilités
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='recommandations_creees',
        verbose_name="Créé par"
    )
    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='recommandations_validees',
        verbose_name="Validé par"
    )
    assigne_a = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='recommandations_assignees',
        verbose_name="Assigné à"
    )

    # Planification
    date_echeance = models.DateField(
        null=True, blank=True,
        verbose_name="Date d'échéance"
    )
    date_debut_prevue = models.DateField(
        null=True, blank=True,
        verbose_name="Date de début prévue"
    )
    duree_estimee_jours = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name="Durée estimée (jours)"
    )

    # Suivi
    pourcentage_avancement = models.PositiveIntegerField(
        default=0,
        verbose_name="Avancement (%)",
        help_text="Pourcentage d'avancement de 0 à 100"
    )
    impact_estime = models.CharField(
        max_length=10,
        choices=[
            ('faible', 'Faible'),
            ('moyen', 'Moyen'),
            ('fort', 'Fort'),
            ('critique', 'Critique')
        ],
        default='moyen',
        verbose_name="Impact estimé"
    )

    # Validation et clôture
    date_validation = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Date de validation"
    )
    date_assignation = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Date d'assignation"
    )
    date_debut_reel = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Date de début réel"
    )
    date_cloture = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Date de clôture"
    )

    # Efficacité (post-clôture)
    efficacite_realisee = models.CharField(
        max_length=20,
        choices=[
            ('non_evaluee', 'Non évaluée'),
            ('insuffisante', 'Insuffisante'),
            ('partielle', 'Partielle'),
            ('satisfaisante', 'Satisfaisante'),
            ('excellente', 'Excellente')
        ],
        default='non_evaluee',
        verbose_name="Efficacité réalisée"
    )
    commentaire_cloture = models.TextField(
        blank=True,
        verbose_name="Commentaire de clôture"
    )

    # Métadonnées
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    donnees_contexte = models.JSONField(
        default=dict,
        blank=True,
        help_text="Données contextuelles JSON (scores IA, métriques, etc.)"
    )
    tags = models.JSONField(
        default=list,
        blank=True,
        help_text="Tags pour catégorisation (ex: ['urgent', 'paie', 'formation'])"
    )

    class Meta:
        ordering = ['-date_creation']
        verbose_name = "Recommandation"
        verbose_name_plural = "Recommandations"
        indexes = [
            models.Index(fields=['statut', 'priorite']),
            models.Index(fields=['date_echeance']),
            models.Index(fields=['assigne_a', 'statut']),
        ]

    def __str__(self):
        return f"{self.code_recommandation} - {self.titre}"

    def save(self, *args, **kwargs):
        # Génération automatique du code si nouveau
        if not self.code_recommandation:
            self.code_recommandation = self._generer_code()

        # Mise à jour automatique des dates selon le statut
        self._mettre_a_jour_dates()

        super().save(*args, **kwargs)

    def _generer_code(self):
        """Génère un code unique pour la recommandation"""
        annee = timezone.now().year
        dernier_numero = Recommandation.objects.filter(
            code_recommandation__startswith=f"REC-{annee}-"
        ).count() + 1
        return f"REC-{annee}-{dernier_numero:03d}"

    def _mettre_a_jour_dates(self):
        """Met à jour les dates selon les changements de statut"""
        now = timezone.now()

        if self.statut == 'approved' and not self.date_validation:
            self.date_validation = now
        elif self.statut == 'assigned' and not self.date_assignation:
            self.date_assignation = now
        elif self.statut == 'in_progress' and not self.date_debut_reel:
            self.date_debut_reel = now
        elif self.statut in ['completed', 'rejected', 'cancelled'] and not self.date_cloture:
            self.date_cloture = now

    def get_absolute_url(self):
        return reverse('recommendations:detail', kwargs={'pk': self.pk})

    def is_overdue(self):
        """Vérifie si la recommandation est en retard"""
        if not self.date_echeance:
            return False
        return (
                self.date_echeance < timezone.now().date() and
                self.statut not in ['completed', 'rejected', 'cancelled']
        )

    def get_duree_reelle(self):
        """Calcule la durée réelle de traitement"""
        if self.date_debut_reel and self.date_cloture:
            return (self.date_cloture.date() - self.date_debut_reel.date()).days
        return None

    def get_jours_restants(self):
        """Calcule le nombre de jours restants avant échéance"""
        if not self.date_echeance:
            return None
        return (self.date_echeance - timezone.now().date()).days

    def can_edit(self, user):
        """Vérifie si l'utilisateur peut modifier la recommandation"""
        if user.is_admin():
            return True
        if self.cree_par == user and self.statut == 'draft':
            return True
        if self.assigne_a == user and self.statut in ['assigned', 'in_progress']:
            return True
        return False

    def can_validate(self, user):
        """Vérifie si l'utilisateur peut valider la recommandation"""
        return (
            user.is_admin() or user.role == 'user'  # ✅ Changer 'auditor' en 'user'
        ) and self.statut == 'pending'

    def get_priorite_color(self):
        """Retourne la couleur CSS selon la priorité"""
        colors = {
            'critique': 'danger',
            'haute': 'warning',
            'moyenne': 'info',
            'basse': 'success'
        }
        return colors.get(self.priorite, 'secondary')

    def get_statut_color(self):
        """Retourne la couleur CSS selon le statut"""
        colors = {
            'draft': 'secondary',
            'pending': 'warning',
            'approved': 'info',
            'assigned': 'primary',
            'in_progress': 'warning',
            'completed': 'success',
            'rejected': 'danger',
            'overdue': 'danger',
            'cancelled': 'dark'
        }
        return colors.get(self.statut, 'secondary')


class ActionPlan(models.Model):
    """Plan d'action détaillé pour chaque recommandation"""

    recommandation = models.ForeignKey(
        Recommandation,
        on_delete=models.CASCADE,
        related_name='actions',
        verbose_name="Recommandation"
    )

    # Détail de l'action
    nom_action = models.CharField(max_length=255, verbose_name="Nom de l'action")
    description_action = models.TextField(verbose_name="Description détaillée")
    ordre = models.PositiveIntegerField(
        default=1,
        verbose_name="Ordre d'exécution"
    )

    # Planification
    date_debut_prevue = models.DateField(
        null=True, blank=True,
        verbose_name="Date de début prévue"
    )
    date_fin_prevue = models.DateField(
        null=True, blank=True,
        verbose_name="Date de fin prévue"
    )
    duree_estimee_heures = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name="Durée estimée (heures)"
    )

    # Responsabilité
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='actions_responsable',
        verbose_name="Responsable"
    )
    contributeurs = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='actions_contributeur',
        verbose_name="Contributeurs"
    )

    # Statut et suivi
    statut = models.CharField(
        max_length=15,
        choices=[
            ('non_commencee', 'Non commencée'),
            ('en_cours', 'En cours'),
            ('terminee', 'Terminée'),
            ('bloquee', 'Bloquée'),
            ('annulee', 'Annulée')
        ],
        default='non_commencee',
        verbose_name="Statut"
    )
    pourcentage_completion = models.PositiveIntegerField(
        default=0,
        verbose_name="Completion (%)"
    )

    # Réalisation
    date_debut_reelle = models.DateField(
        null=True, blank=True,
        verbose_name="Date de début réelle"
    )
    date_fin_reelle = models.DateField(
        null=True, blank=True,
        verbose_name="Date de fin réelle"
    )
    commentaires = models.TextField(
        blank=True,
        verbose_name="Commentaires"
    )

    # Métadonnées
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['recommandation', 'ordre']
        verbose_name = "Action du plan"
        verbose_name_plural = "Actions du plan"

    def __str__(self):
        return f"{self.recommandation.code_recommandation} - {self.nom_action}"


class SuiviAvancement(models.Model):
    """Historique et suivi des actions sur les recommandations"""

    TYPE_EVENEMENT_CHOICES = [
        ('creation', 'Création'),
        ('modification', 'Modification'),
        ('validation', 'Validation'),
        ('rejet', 'Rejet'),
        ('assignation', 'Assignation'),
        ('debut_travaux', 'Début des travaux'),
        ('mise_a_jour', 'Mise à jour avancement'),
        ('commentaire', 'Ajout commentaire'),
        ('cloture', 'Clôture'),
        ('rouverture', 'Réouverture'),
    ]

    recommandation = models.ForeignKey(
        Recommandation,
        on_delete=models.CASCADE,
        related_name='suivis',
        verbose_name="Recommandation"
    )

    # Événement
    type_evenement = models.CharField(
        max_length=20,
        choices=TYPE_EVENEMENT_CHOICES,
        verbose_name="Type d'événement"
    )
    description = models.TextField(verbose_name="Description")
    commentaire_utilisateur = models.TextField(
        blank=True,
        verbose_name="Commentaire utilisateur"
    )

    # Auteur et timing
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name="Utilisateur"
    )
    date_evenement = models.DateTimeField(auto_now_add=True)

    # Données avant/après pour traçabilité
    donnees_avant = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Données avant modification"
    )
    donnees_apres = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Données après modification"
    )

    # Fichiers joints
    fichiers_joints = models.JSONField(
        default=list,
        blank=True,
        help_text="URLs des fichiers joints (preuves, captures, etc.)"
    )

    class Meta:
        ordering = ['-date_evenement']
        verbose_name = "Suivi d'avancement"
        verbose_name_plural = "Suivis d'avancement"

    def __str__(self):
        return f"{self.recommandation.code_recommandation} - {self.get_type_evenement_display()}"


class NotificationRecommandation(models.Model):
    """Notifications liées aux recommandations"""

    TYPE_NOTIFICATION_CHOICES = [
        ('nouvelle', 'Nouvelle recommandation'),
        ('assignation', 'Assignation'),
        ('echeance_proche', 'Échéance proche'),
        ('retard', 'Retard détecté'),
        ('validation_requise', 'Validation requise'),
        ('completion', 'Recommandation terminée'),
    ]

    recommandation = models.ForeignKey(
        Recommandation,
        on_delete=models.CASCADE,
        related_name='notifications'
    )

    type_notification = models.CharField(
        max_length=20,
        choices=TYPE_NOTIFICATION_CHOICES
    )
    destinataire = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications_recommandations'
    )

    titre = models.CharField(max_length=255)
    message = models.TextField()

    # Statut
    lue = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_lecture = models.DateTimeField(null=True, blank=True)

    # Intégration email
    email_envoye = models.BooleanField(default=False)
    date_envoi_email = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-date_creation']
        verbose_name = "Notification recommandation"
        verbose_name_plural = "Notifications recommandations"

    def __str__(self):
        return f"{self.destinataire.username} - {self.titre}"

    def marquer_comme_lue(self):
        """Marque la notification comme lue"""
        if not self.lue:
            self.lue = True
            self.date_lecture = timezone.now()
            self.save()


class KPIRecommandation(models.Model):
    """KPIs et métriques des recommandations par période"""

    # Période
    mission = models.ForeignKey(Mission, on_delete=models.CASCADE)
    periode_debut = models.DateField()
    periode_fin = models.DateField()

    # Compteurs globaux
    nb_recommandations_creees = models.PositiveIntegerField(default=0)
    nb_recommandations_terminees = models.PositiveIntegerField(default=0)
    nb_recommandations_en_retard = models.PositiveIntegerField(default=0)

    # Répartition par type
    nb_correctifs = models.PositiveIntegerField(default=0)
    nb_preventifs = models.PositiveIntegerField(default=0)
    nb_ameliorations = models.PositiveIntegerField(default=0)
    nb_formations = models.PositiveIntegerField(default=0)

    # Répartition par priorité
    nb_critiques = models.PositiveIntegerField(default=0)
    nb_hautes = models.PositiveIntegerField(default=0)
    nb_moyennes = models.PositiveIntegerField(default=0)
    nb_basses = models.PositiveIntegerField(default=0)

    # Métriques de performance
    duree_moyenne_traitement = models.FloatField(
        null=True, blank=True,
        help_text="Durée moyenne en jours"
    )
    taux_respect_echeances = models.FloatField(
        null=True, blank=True,
        help_text="Pourcentage (0-100)"
    )
    taux_completion = models.FloatField(
        null=True, blank=True,
        help_text="Pourcentage (0-100)"
    )

    # Efficacité
    score_efficacite_moyen = models.FloatField(
        null=True, blank=True,
        help_text="Score d'efficacité moyen (1-5)"
    )

    # Métadonnées
    date_calcul = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['mission', 'periode_debut', 'periode_fin']
        ordering = ['-periode_fin']
        verbose_name = "KPI Recommandations"
        verbose_name_plural = "KPIs Recommandations"

    def __str__(self):
        return f"KPI {self.mission.name} - {self.periode_debut} à {self.periode_fin}"
