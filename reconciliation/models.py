from django.db import models
from django.conf import settings
from uploads.models import FichierImporte
from accounts.models import Mission


class RapprochementSession(models.Model):
    """Session de rapprochement entre fichiers"""

    STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('processing', 'En cours'),
        ('completed', 'Terminé'),
        ('error', 'Erreur'),
    ]

    mission = models.ForeignKey(
        'accounts.Mission',
        on_delete=models.CASCADE,
        related_name='rapprochements',
        verbose_name="Mission"
    )
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='rapprochements_crees',
        verbose_name="Créé par"
    )

    # Fichiers à rapprocher
    fichier_liste_personnel = models.ForeignKey(
        FichierImporte,
        on_delete=models.CASCADE,
        related_name='rapprochements_comme_liste',
        verbose_name="Liste du personnel à payer",
        help_text="Fichier RH avec les employés qui doivent être payés"
    )
    fichier_paie = models.ForeignKey(
        FichierImporte,
        on_delete=models.CASCADE,
        related_name='rapprochements_comme_paie',
        verbose_name="Fichier de paie",
        help_text="Fichier avec les employés effectivement payés"
    )

    # Métadonnées
    nom_session = models.CharField(max_length=255, verbose_name="Nom de la session")
    description = models.TextField(blank=True, verbose_name="Description")

    # Statut et timing
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    date_creation = models.DateTimeField(auto_now_add=True)
    date_traitement = models.DateTimeField(null=True, blank=True)
    date_completion = models.DateTimeField(null=True, blank=True)

    # Résultats globaux
    nb_employes_rh = models.PositiveIntegerField(default=0, help_text="Employés dans la liste RH")
    nb_employes_payes = models.PositiveIntegerField(default=0, help_text="Employés payés")
    nb_matches_parfaits = models.PositiveIntegerField(default=0, help_text="Rapprochements parfaits")
    nb_matches_partiels = models.PositiveIntegerField(default=0, help_text="Rapprochements partiels")
    nb_non_payes = models.PositiveIntegerField(default=0, help_text="Employés RH non payés")
    nb_non_declares = models.PositiveIntegerField(default=0, help_text="Payés non déclarés en RH")
    nb_doublons = models.PositiveIntegerField(default=0, help_text="Paies multiples détectées")

    # Logs et erreurs
    logs_traitement = models.JSONField(default=list, help_text="Logs du traitement")
    erreurs = models.TextField(blank=True, help_text="Erreurs rencontrées")

    class Meta:
        ordering = ['-date_creation']
        verbose_name = "Session de rapprochement"
        verbose_name_plural = "Sessions de rapprochement"

    def __str__(self):
        return f"{self.nom_session} - {self.mission.name}"

    def get_taux_rapprochement(self):
        """Calcule le taux de rapprochement global"""
        if self.nb_employes_rh == 0:
            return 0
        return round((self.nb_matches_parfaits + self.nb_matches_partiels) / self.nb_employes_rh * 100, 2)


class ResultatRapprochement(models.Model):
    """Résultat individuel de rapprochement pour chaque employé"""

    TYPE_MATCH = [
        ('parfait', 'Match parfait'),
        ('partiel', 'Match partiel'),
        ('non_paye', 'Non payé'),
        ('non_declare', 'Non déclaré'),
        ('doublon', 'Doublon détecté'),
    ]

    CRITERE_MATCH = [
        ('matricule', 'Matricule'),
        ('nom_prenom_ddn', 'Nom + Prénom + Date naissance'),
        ('rib', 'RIB'),
        ('aucun', 'Aucun'),
    ]

    session = models.ForeignKey(
        RapprochementSession,
        on_delete=models.CASCADE,
        related_name='resultats',
        verbose_name="Session"
    )

    # Type de résultat
    type_match = models.CharField(max_length=20, choices=TYPE_MATCH)
    critere_match = models.CharField(max_length=20, choices=CRITERE_MATCH, default='aucun')
    score_confiance = models.FloatField(default=0.0, help_text="Score de 0 à 100")

    # Données employé RH (si existe)
    matricule_rh = models.CharField(max_length=50, blank=True)
    nom_rh = models.CharField(max_length=100, blank=True)
    prenom_rh = models.CharField(max_length=100, blank=True)
    poste_rh = models.CharField(max_length=100, blank=True)
    rib_rh = models.CharField(max_length=100, blank=True)
    salaire_prevu_rh = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Données employé Paie (si existe)
    matricule_paie = models.CharField(max_length=50, blank=True)
    nom_paie = models.CharField(max_length=100, blank=True)
    prenom_paie = models.CharField(max_length=100, blank=True)
    rib_paie = models.CharField(max_length=100, blank=True)
    salaire_brut_paie = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    montant_total_paie = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Analyse
    ecart_salaire = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Différence entre salaire prévu et payé"
    )
    commentaires = models.TextField(blank=True, help_text="Commentaires sur le rapprochement")

    # Métadonnées
    ligne_rh = models.PositiveIntegerField(null=True, blank=True, help_text="Numéro de ligne dans le fichier RH")
    ligne_paie = models.PositiveIntegerField(null=True, blank=True, help_text="Numéro de ligne dans le fichier paie")
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['type_match', 'nom_rh', 'nom_paie']
        verbose_name = "Résultat de rapprochement"
        verbose_name_plural = "Résultats de rapprochement"

    def __str__(self):
        nom = self.nom_rh or self.nom_paie or "Inconnu"
        return f"{nom} - {self.get_type_match_display()}"

    def get_status_icon(self):
        """Retourne l'icône CSS selon le type de match"""
        icons = {
            'parfait': 'bi-check-circle-fill text-success',
            'partiel': 'bi-exclamation-triangle-fill text-warning',
            'non_paye': 'bi-x-circle-fill text-danger',
            'non_declare': 'bi-question-circle-fill text-info',
            'doublon': 'bi-files text-warning'
        }
        return icons.get(self.type_match, 'bi-circle')


class RegleValidation(models.Model):
    """Règles de validation pour les rapprochements (pour évolutions futures)"""

    TYPE_REGLE = [
        ('matricule_obligatoire', 'Matricule obligatoire'),
        ('tolerance_salaire', 'Tolérance écart salaire'),
        ('format_rib', 'Validation format RIB'),
        ('doublon_rib', 'Détection doublons RIB'),
    ]

    mission = models.ForeignKey(
        'accounts.Mission',
        on_delete=models.CASCADE,
        related_name='regles_validation',
        verbose_name="Mission"
    )

    type_regle = models.CharField(max_length=50, choices=TYPE_REGLE)
    nom_regle = models.CharField(max_length=100, verbose_name="Nom de la règle")
    description = models.TextField(blank=True)

    # Configuration
    valeur_numerique = models.FloatField(null=True, blank=True, help_text="Valeur numérique si applicable")
    valeur_texte = models.CharField(max_length=500, blank=True, help_text="Valeur texte si applicable")
    est_active = models.BooleanField(default=True)

    # Métadonnées
    cree_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['mission', 'type_regle']
        verbose_name = "Règle de validation"
        verbose_name_plural = "Règles de validation"

    def __str__(self):
        return f"{self.nom_regle} - {self.mission.name}"
