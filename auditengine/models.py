# auditengine/models.py
import os
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from uploads.models import FichierImporte
from reconciliation.models import RapprochementSession
from accounts.models import Mission


class ParametrageIA(models.Model):
    """Configuration des paramètres de l'IA pour la détection d'anomalies"""

    # Seuils de détection
    seuil_isolation_forest = models.FloatField(
        default=0.75,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Seuil pour considérer une observation comme anomalie (0-1)"
    )
    score_minimum_classification = models.FloatField(
        default=0.8,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Score minimum pour valider une classification MLP (0-1)"
    )

    # Configuration des modèles
    utiliser_modele_global = models.BooleanField(
        default=True,
        help_text="Utiliser le modèle global ou permettre l'affinage par mission"
    )
    reentrainement_auto = models.BooleanField(
        default=False,
        help_text="Réentraînement automatique avec les corrections utilisateur"
    )

    # Paramètres d'affichage
    nb_anomalies_max_dashboard = models.PositiveIntegerField(
        default=50,
        help_text="Nombre maximum d'anomalies à afficher sur le dashboard"
    )
    afficher_explications = models.BooleanField(
        default=True,
        help_text="Afficher les explications des décisions IA"
    )

    # Métadonnées
    modifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="Modifié par"
    )
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Paramétrage IA"
        verbose_name_plural = "Paramétrage IA"

    def __str__(self):
        return f"Config IA - IF:{self.seuil_isolation_forest} MLP:{self.score_minimum_classification}"

    @classmethod
    def get_config(cls):
        """Récupère la configuration active (crée une par défaut si inexistante)"""
        config, created = cls.objects.get_or_create(
            pk=1,
            defaults={
                'modifie_par_id': 1  # Premier admin
            }
        )
        return config


class SessionAudit(models.Model):
    """Session de détection d'anomalies par IA"""

    STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('processing', 'Traitement en cours'),
        ('completed', 'Terminé'),
        ('error', 'Erreur'),
    ]

    # Relations
    mission = models.ForeignKey(
        Mission,
        on_delete=models.CASCADE,
        related_name='sessions_audit',
        verbose_name="Mission"
    )
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='audits_crees',
        verbose_name="Lancé par"
    )

    # Source des données
    fichier_paie = models.ForeignKey(
        FichierImporte,
        on_delete=models.CASCADE,
        related_name='audits_comme_source',
        verbose_name="Fichier de paie analysé"
    )
    session_rapprochement = models.ForeignKey(
        RapprochementSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audits_generes',
        verbose_name="Session de rapprochement associée"
    )

    # Métadonnées
    nom_session = models.CharField(max_length=255, verbose_name="Nom de la session")
    description = models.TextField(blank=True, verbose_name="Description")

    # Statut et timing
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    date_creation = models.DateTimeField(auto_now_add=True)
    date_traitement = models.DateTimeField(null=True, blank=True)
    date_completion = models.DateTimeField(null=True, blank=True)

    # Configuration utilisée
    seuil_if_utilise = models.FloatField(null=True, blank=True)
    seuil_mlp_utilise = models.FloatField(null=True, blank=True)
    modele_utilise = models.CharField(
        max_length=100,
        blank=True,
        help_text="Nom du modèle utilisé (global ou spécifique mission)"
    )

    # Résultats globaux
    nb_lignes_analysees = models.PositiveIntegerField(default=0)
    nb_anomalies_detectees = models.PositiveIntegerField(default=0)
    nb_salaires_anormaux = models.PositiveIntegerField(default=0)
    nb_employes_fantomes = models.PositiveIntegerField(default=0)
    nb_primes_anormales = models.PositiveIntegerField(default=0)
    nb_heures_excessives = models.PositiveIntegerField(default=0)
    nb_rib_dupliques = models.PositiveIntegerField(default=0)
    nb_aucune_anomalie = models.PositiveIntegerField(default=0)

    # Performance et logs
    duree_traitement_secondes = models.FloatField(null=True, blank=True)
    logs_traitement = models.JSONField(default=list, help_text="Logs détaillés du traitement")
    erreurs = models.TextField(blank=True, help_text="Erreurs rencontrées")

    class Meta:
        ordering = ['-date_creation']
        verbose_name = "Session d'audit IA"
        verbose_name_plural = "Sessions d'audit IA"

    def __str__(self):
        return f"{self.nom_session} - {self.mission.name}"

    def get_taux_anomalies(self):
        """Calcule le pourcentage d'anomalies détectées"""
        if self.nb_lignes_analysees == 0:
            return 0
        return round((self.nb_anomalies_detectees / self.nb_lignes_analysees) * 100, 2)


class ResultatAudit(models.Model):
    """Résultat individuel de détection d'anomalie"""

    TYPE_ANOMALIE_CHOICES = [
        ('salaire_anormal', 'Salaire anormal'),
        ('ghost_employee', 'Employé fantôme'),
        ('prime_anormale', 'Prime anormale'),
        ('heures_excessives', 'Heures excessives'),
        ('duplicate_rib', 'RIB dupliqué'),
        ('aucune', 'Aucune anomalie'),
    ]

    NIVEAU_RISQUE_CHOICES = [
        ('faible', 'Risque faible'),
        ('moyen', 'Risque moyen'),
        ('eleve', 'Risque élevé'),
        ('critique', 'Risque critique'),
    ]

    # Relations
    session = models.ForeignKey(
        SessionAudit,
        on_delete=models.CASCADE,
        related_name='resultats',
        verbose_name="Session d'audit"
    )

    # Données de l'employé analysé
    ligne_fichier = models.PositiveIntegerField(help_text="Numéro de ligne dans le fichier")
    matricule = models.CharField(max_length=50, blank=True)
    nom = models.CharField(max_length=100, blank=True)
    prenom = models.CharField(max_length=100, blank=True)
    poste = models.CharField(max_length=100, blank=True)
    rib = models.CharField(max_length=100, blank=True)

    # Données financières
    salaire_brut = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    montant_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    heures_travaillees = models.FloatField(null=True, blank=True)
    montant_primes = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Résultats IA
    est_anomalie = models.BooleanField(default=False, verbose_name="Anomalie détectée")
    score_anomalie_if = models.FloatField(
        null=True,
        blank=True,
        help_text="Score Isolation Forest (0-1, plus proche de 1 = plus anormal)"
    )
    type_anomalie = models.CharField(
        max_length=20,
        choices=TYPE_ANOMALIE_CHOICES,
        default='aucune'
    )
    score_classification_mlp = models.FloatField(
        null=True,
        blank=True,
        help_text="Score de confiance MLP pour la classification (0-1)"
    )
    niveau_risque = models.CharField(
        max_length=20,
        choices=NIVEAU_RISQUE_CHOICES,
        default='faible'
    )

    # Explications et recommandations
    explication_if = models.TextField(
        blank=True,
        help_text="Explication de la détection Isolation Forest"
    )
    explication_mlp = models.TextField(
        blank=True,
        help_text="Explication de la classification MLP"
    )
    recommandation_auto = models.TextField(
        blank=True,
        help_text="Recommandation générée automatiquement"
    )

    # Validation humaine
    valide_par_humain = models.BooleanField(
        default=False,
        help_text="Résultat validé par un utilisateur"
    )
    est_fausse_alerte = models.BooleanField(
        default=False,
        help_text="Marqué comme fausse alerte par utilisateur"
    )
    commentaire_utilisateur = models.TextField(
        blank=True,
        help_text="Commentaire de validation"
    )
    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='anomalies_validees',
        verbose_name="Validé par"
    )
    date_validation = models.DateTimeField(null=True, blank=True)

    # Métadonnées
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-score_anomalie_if', '-score_classification_mlp']
        verbose_name = "Résultat d'audit"
        verbose_name_plural = "Résultats d'audit"
        indexes = [
            models.Index(fields=['est_anomalie', 'type_anomalie']),
            models.Index(fields=['session', 'niveau_risque']),
        ]

    def __str__(self):
        nom_complet = f"{self.nom} {self.prenom}".strip() or f"Ligne {self.ligne_fichier}"
        return f"{nom_complet} - {self.get_type_anomalie_display()}"

    def get_score_global(self):
        """Calcule un score global combinant IF et MLP"""
        if self.score_anomalie_if and self.score_classification_mlp:
            return round((self.score_anomalie_if + self.score_classification_mlp) / 2, 3)
        return self.score_anomalie_if or self.score_classification_mlp or 0

    def get_couleur_risque(self):
        """Retourne la couleur CSS selon le niveau de risque"""
        couleurs = {
            'faible': 'success',
            'moyen': 'warning',
            'eleve': 'danger',
            'critique': 'dark'
        }
        return couleurs.get(self.niveau_risque, 'secondary')

    def get_icone_anomalie(self):
        """Retourne l'icône Bootstrap selon le type d'anomalie"""
        icones = {
            'salaire_anormal': 'bi-currency-euro',
            'ghost_employee': 'bi-person-x',
            'prime_anormale': 'bi-gift',
            'heures_excessives': 'bi-clock',
            'duplicate_rib': 'bi-credit-card-2-front',
            'aucune': 'bi-check-circle'
        }
        return icones.get(self.type_anomalie, 'bi-question-circle')


class CorrectionUtilisateur(models.Model):
    """Corrections et feedbacks des utilisateurs pour améliorer les modèles"""

    TYPE_CORRECTION_CHOICES = [
        ('fausse_alerte', 'Fausse alerte'),
        ('vraie_anomalie', 'Vraie anomalie non détectée'),
        ('reclassification', 'Reclassification du type'),
        ('validation', 'Validation positive'),
    ]

    # Relations
    resultat_audit = models.ForeignKey(
        ResultatAudit,
        on_delete=models.CASCADE,
        related_name='corrections',
        verbose_name="Résultat corrigé"
    )
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='corrections_apportees',
        verbose_name="Utilisateur"
    )

    # Type de correction
    type_correction = models.CharField(max_length=20, choices=TYPE_CORRECTION_CHOICES)

    # Anciennes valeurs (avant correction)
    ancien_est_anomalie = models.BooleanField(null=True, blank=True)
    ancien_type_anomalie = models.CharField(max_length=20, blank=True)
    ancien_niveau_risque = models.CharField(max_length=20, blank=True)

    # Nouvelles valeurs (après correction)
    nouveau_est_anomalie = models.BooleanField(null=True, blank=True)
    nouveau_type_anomalie = models.CharField(max_length=20, blank=True)
    nouveau_niveau_risque = models.CharField(max_length=20, blank=True)

    # Justification
    justification = models.TextField(
        help_text="Explication de la correction pour l'apprentissage"
    )
    confiance_utilisateur = models.PositiveIntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Niveau de confiance de l'utilisateur (1-10)"
    )

    # Métadonnées
    date_correction = models.DateTimeField(auto_now_add=True)
    utilisee_pour_entrainement = models.BooleanField(
        default=False,
        help_text="Cette correction a été utilisée pour réentraîner le modèle"
    )

    class Meta:
        ordering = ['-date_correction']
        verbose_name = "Correction utilisateur"
        verbose_name_plural = "Corrections utilisateurs"
        unique_together = ['resultat_audit', 'utilisateur']  # Une correction par utilisateur par résultat

    def __str__(self):
        return f"{self.get_type_correction_display()} par {self.utilisateur.username}"


class ModeleIA(models.Model):
    """Gestion des modèles IA (global et spécifiques par mission)"""

    TYPE_MODELE_CHOICES = [
        ('isolation_forest', 'Isolation Forest'),
        ('mlp_classifier', 'MLP Classifier'),
    ]

    SCOPE_CHOICES = [
        ('global', 'Modèle global'),
        ('mission', 'Modèle spécifique mission'),
    ]

    # Identification
    nom_modele = models.CharField(max_length=100, verbose_name="Nom du modèle")
    type_modele = models.CharField(max_length=20, choices=TYPE_MODELE_CHOICES)
    scope = models.CharField(max_length=10, choices=SCOPE_CHOICES, default='global')

    # Relations
    mission = models.ForeignKey(
        Mission,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='modeles_ia',
        help_text="Mission spécifique (null pour modèle global)"
    )

    # Fichier et métadonnées
    fichier_modele = models.CharField(
        max_length=255,
        help_text="Chemin vers le fichier .pkl du modèle"
    )
    version = models.CharField(max_length=20, default="1.0")
    description = models.TextField(blank=True)

    # Métriques de performance
    precision = models.FloatField(null=True, blank=True)
    recall = models.FloatField(null=True, blank=True)
    f1_score = models.FloatField(null=True, blank=True)
    accuracy = models.FloatField(null=True, blank=True)

    # Données d'entraînement
    nb_echantillons_entrainement = models.PositiveIntegerField(null=True, blank=True)
    date_entrainement = models.DateTimeField(null=True, blank=True)
    entrainement_base_sur = models.TextField(
        blank=True,
        help_text="Sources de données utilisées pour l'entraînement"
    )

    # Statut
    est_actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='modeles_crees'
    )

    class Meta:
        ordering = ['-date_creation']
        verbose_name = "Modèle IA"
        verbose_name_plural = "Modèles IA"
        unique_together = ['type_modele', 'scope', 'mission']  # Un modèle par type et scope

    def __str__(self):
        scope_str = f" - {self.mission.name}" if self.mission else " - Global"
        return f"{self.get_type_modele_display()}{scope_str} v{self.version}"

    def get_chemin_complet(self):
        """Retourne le chemin complet vers le fichier du modèle"""
        return os.path.join(settings.BASE_DIR, 'ml_models', self.fichier_modele)

    @classmethod
    def get_modele_actif(cls, type_modele, mission=None):
        """Récupère le modèle actif pour un type donné"""
        # Priorité au modèle spécifique mission si disponible
        if mission:
            modele_mission = cls.objects.filter(
                type_modele=type_modele,
                scope='mission',
                mission=mission,
                est_actif=True
            ).first()
            if modele_mission:
                return modele_mission

        # Fallback sur le modèle global
        return cls.objects.filter(
            type_modele=type_modele,
            scope='global',
            est_actif=True
        ).first()
