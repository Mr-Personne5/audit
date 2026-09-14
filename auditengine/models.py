# auditengine/models.py
import os
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from uploads.models import FichierImporte
from reconciliation.models import RapprochementSession
from accounts.models import Mission
from django.utils import timezone
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)


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
    nb_anomalies_max_tableau_de_bord = models.PositiveIntegerField(
        default=50,
        help_text="Nombre maximum d'anomalies à afficher sur le tableau de bord"
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
        ('anomalie_non_classifiee', 'Anomalie non classifiée'),
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
        max_length=25,
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


class TacheAction(models.Model):
    """Tâches d'action générées à partir des recommandations d'audit"""

    STATUT_CHOICES = [
        ('a_creer', 'À créer'),
        ('en_cours', 'En cours'),
        ('terminee', 'Terminée'),
        ('annulee', 'Annulée'),
    ]

    PRIORITE_CHOICES = [
        ('critique', 'Critique'),
        ('elevee', 'Élevée'),
        ('moyenne', 'Moyenne'),
        ('faible', 'Faible'),
    ]

    # Relations
    session_audit = models.ForeignKey(
        SessionAudit,
        on_delete=models.CASCADE,
        related_name='taches_actions',
        verbose_name="Session d'audit"
    )
    type_anomalie = models.CharField(
        max_length=50,
        choices=ResultatAudit.TYPE_ANOMALIE_CHOICES,
        verbose_name="Type d'anomalie"
    )

    # Détails de la tâche
    titre = models.CharField(max_length=200, verbose_name="Titre de la tâche")
    description = models.TextField(verbose_name="Description détaillée")
    action_requise = models.TextField(verbose_name="Action à effectuer")
    
    # Gestion
    responsable = models.CharField(max_length=100, verbose_name="Responsable")
    priorite = models.CharField(max_length=20, choices=PRIORITE_CHOICES, default='moyenne')
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='a_creer')
    
    # Échéances
    delai = models.CharField(max_length=50, verbose_name="Délai recommandé")
    date_creation = models.DateTimeField(auto_now_add=True)
    date_debut = models.DateTimeField(null=True, blank=True)
    date_fin_prevue = models.DateTimeField(null=True, blank=True)
    date_fin_reelle = models.DateTimeField(null=True, blank=True)
    
    # Métriques
    nb_cas_concernes = models.PositiveIntegerField(default=0, verbose_name="Nombre de cas concernés")
    impact_financier_estime = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0,
        verbose_name="Impact financier estimé (€)"
    )
    
    # Suivi
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='taches_crees',
        verbose_name="Créé par"
    )
    assigne_a = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='taches_assignees',
        verbose_name="Assigné à"
    )
    notes = models.TextField(blank=True, verbose_name="Notes de suivi")

    class Meta:
        ordering = ['-priorite', '-date_creation']
        verbose_name = "Tâche d'action"
        verbose_name_plural = "Tâches d'action"

    def __str__(self):
        return f"{self.titre} ({self.get_statut_display()})"

    def get_progression(self):
        """Calcule la progression en pourcentage"""
        if self.statut == 'terminee':
            return 100
        elif self.statut == 'en_cours':
            return 50
        elif self.statut == 'a_creer':
            return 0
        else:
            return 0

    @classmethod
    def creer_depuis_plan_action(cls, session_audit, plan_action, utilisateur):
        """Crée des tâches à partir du plan d'action d'une session"""
        taches_crees = []
        
        for action in plan_action:
            tache = cls.objects.create(
                session_audit=session_audit,
                type_anomalie=action.get('type_code', 'salaire_anormal'),
                titre=f"Corriger {action.get('type', 'anomalies')}",
                description=action.get('action', ''),
                action_requise=action.get('action', ''),
                responsable=action.get('responsable', 'À définir'),
                delai=action.get('delai', 'À définir'),
                nb_cas_concernes=action.get('count', 0),
                impact_financier_estime=action.get('impact_estime', 0),
                cree_par=utilisateur,
                priorite='critique' if 'immédiat' in action.get('delai', '').lower() else 'elevee'
            )
            taches_crees.append(tache)
        
        return taches_crees


class AuditLog(models.Model):
    """Journal d'audit pour tracer toutes les actions utilisateur"""
    ACTION_CHOICES = [
        # Actions d'audit
        ('create_session', 'Création de session'),
        ('start_analysis', 'Démarrage analyse'),
        ('complete_analysis', 'Analyse terminée'),
        ('view_results', 'Consultation résultats'),
        ('export_results', 'Export résultats'),
        
        # Actions sur les anomalies
        ('view_anomaly', 'Consultation anomalie'),
        ('correct_anomaly', 'Correction anomalie'),
        ('validate_anomaly', 'Validation anomalie'),
        ('mark_false_alert', 'Marquage fausse alerte'),
        
        # Actions sur les recommandations
        ('generate_recommendations', 'Génération recommandations'),
        ('view_recommendations', 'Consultation recommandations'),
        ('export_recommendations', 'Export recommandations'),
        
        # Actions sur les tâches
        ('create_task', 'Création tâche'),
        ('assign_task', 'Assignation tâche'),
        ('complete_task', 'Tâche terminée'),
        ('view_tasks', 'Consultation tâches'),
        
        # Actions système
        ('login', 'Connexion'),
        ('logout', 'Déconnexion'),
        ('access_denied', 'Accès refusé'),
        ('error', 'Erreur système'),
    ]
    
    SEVERITY_CHOICES = [
        ('info', 'Information'),
        ('warning', 'Avertissement'),
        ('error', 'Erreur'),
        ('critical', 'Critique'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='audit_logs', verbose_name="Utilisateur")
    action = models.CharField(max_length=50, choices=ACTION_CHOICES, verbose_name="Action")
    feature = models.CharField(max_length=50, verbose_name="Fonctionnalité")
    target = models.CharField(max_length=50, verbose_name="Cible")
    resource_id = models.CharField(max_length=100, blank=True, verbose_name="ID Ressource")
    resource_type = models.CharField(max_length=50, blank=True, verbose_name="Type Ressource")
    
    # Détails de l'action
    description = models.TextField(blank=True, verbose_name="Description")
    old_value = models.TextField(blank=True, verbose_name="Ancienne valeur")
    new_value = models.TextField(blank=True, verbose_name="Nouvelle valeur")
    
    # Métadonnées
    ip_address = models.GenericIPAddressField(blank=True, null=True, verbose_name="Adresse IP")
    user_agent = models.TextField(blank=True, verbose_name="User Agent")
    session_id = models.CharField(max_length=100, blank=True, verbose_name="ID Session")
    
    # Sécurité
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='info', verbose_name="Sévérité")
    is_suspicious = models.BooleanField(default=False, verbose_name="Suspect")
    
    # Horodatage
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Horodatage")
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Journal d'audit"
        verbose_name_plural = "Journaux d'audit"
        indexes = [
            models.Index(fields=['user', 'action', 'timestamp']),
            models.Index(fields=['action', 'timestamp']),
            models.Index(fields=['resource_type', 'resource_id']),
            models.Index(fields=['severity', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.user} - {self.get_action_display()} - {self.timestamp}"

    @classmethod
    def log_action(cls, user, action, feature, target, **kwargs):
        """Méthode utilitaire pour enregistrer une action"""
        try:
            # Détection automatique d'activité suspecte
            is_suspicious = cls._detect_suspicious_activity(user, action, **kwargs)
            
            log_entry = cls.objects.create(
                user=user,
                action=action,
                feature=feature,
                target=target,
                description=kwargs.get('description', ''),
                old_value=kwargs.get('old_value', ''),
                new_value=kwargs.get('new_value', ''),
                resource_id=kwargs.get('resource_id', ''),
                resource_type=kwargs.get('resource_type', ''),
                ip_address=kwargs.get('ip_address', ''),
                user_agent=kwargs.get('user_agent', ''),
                session_id=kwargs.get('session_id', ''),
                severity=kwargs.get('severity', 'info'),
                is_suspicious=is_suspicious
            )
            
            # Alerte si activité suspecte
            if is_suspicious:
                cls._trigger_security_alert(log_entry)
                
            return log_entry
            
        except Exception as e:
            # En cas d'erreur, on log quand même pour éviter la perte d'information
            logger.error(f"Erreur lors de la journalisation: {str(e)}")
            return None

    @classmethod
    def _detect_suspicious_activity(cls, user, action, **kwargs):
        """Détecte les activités suspectes"""
        suspicious_patterns = [
            # Trop d'actions en peu de temps
            lambda u, a, **kw: cls.objects.filter(
                user=u, 
                timestamp__gte=timezone.now() - timedelta(minutes=5)
            ).count() > 50,
            
            # Actions sensibles en dehors des heures normales
            lambda u, a, **kw: a in ['correct_anomaly', 'validate_anomaly'] and 
                              timezone.now().hour not in range(8, 20),
            
            # Tentatives d'accès à des ressources non autorisées
            lambda u, a, **kw: a == 'access_denied',
            
            # Modifications de valeurs sensibles
            lambda u, a, **kw: a in ['correct_anomaly', 'validate_anomaly'] and 
                              kw.get('new_value') != kw.get('old_value'),
        ]
        
        return any(pattern(user, action, **kwargs) for pattern in suspicious_patterns)

    @classmethod
    def _trigger_security_alert(cls, log_entry):
        """Déclenche une alerte de sécurité"""
        try:
            # Ici on pourrait envoyer une notification, un email, etc.
            logger.warning(f"Activité suspecte détectée: {log_entry}")
            
            # Optionnel: Créer une alerte dans le système
            from django.contrib import messages
            # messages.warning(log_entry.user, "Activité suspecte détectée")
            
        except Exception as e:
            logger.error(f"Erreur lors de la création d'alerte: {str(e)}")

    @classmethod
    def get_user_activity_summary(cls, user, days=30):
        """Récupère un résumé de l'activité d'un utilisateur"""
        from django.db.models import Count
        from datetime import timedelta
        
        start_date = timezone.now() - timedelta(days=days)
        
        return cls.objects.filter(
            user=user,
            timestamp__gte=start_date
        ).values('action').annotate(
            count=Count('id')
        ).order_by('-count')

    @classmethod
    def get_security_alerts(cls, days=7):
        """Récupère les alertes de sécurité récentes"""
        from datetime import timedelta
        
        start_date = timezone.now() - timedelta(days=days)
        
        return cls.objects.filter(
            is_suspicious=True,
            timestamp__gte=start_date
        ).order_by('-timestamp')
