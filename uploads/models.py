import os
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


def validate_file_extension(value):
    """Valide l'extension du fichier uploadé"""
    ext = os.path.splitext(value.name)[1].lower()
    valid_extensions = ['.csv', '.xlsx', '.xls']
    if ext not in valid_extensions:
        raise ValidationError(f'Extension non autorisée. Formats acceptés: {", ".join(valid_extensions)}')


def validate_file_size(value):
    """Valide la taille du fichier (max 30MB)"""
    limit = 30 * 1024 * 1024  # 30MB
    if value.size > limit:
        raise ValidationError('Le fichier ne peut pas dépasser 30MB.')


def upload_to_mission_folder(instance, filename):
    """Organise les fichiers par mission, utilisateur et type"""
    # Protection contre les attributs None
    mission_name = "no_mission"
    if hasattr(instance, 'mission') and instance.mission:
        # Utilisation sécurisée des attributs de mission
        mission_name = str(instance.mission.id)
        if hasattr(instance.mission, 'nom'):
            mission_name = instance.mission.nom
        elif hasattr(instance.mission, 'name'):
            mission_name = instance.mission.name
        elif hasattr(instance.mission, 'title'):
            mission_name = instance.mission.title

    user_name = "unknown_user"
    if hasattr(instance, 'utilisateur') and instance.utilisateur:
        user_name = instance.utilisateur.username

    type_fichier = getattr(instance, 'type_fichier', 'unknown_type')

    return f'uploads/{mission_name}/{user_name}/{type_fichier}/{filename}'


class FichierImporte(models.Model):
    """Modèle pour stocker les fichiers importés par mission"""

    TYPES_FICHIER = [
        ('paie', 'Fichier de paie'),
        ('liste_personnel', 'Liste du personnel à payer'),
        ('grille', 'Grille salariale'),
        ('convention', 'Convention collective'),
        ('procedure', 'Procédure interne'),
    ]

    STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('processing', 'En cours de traitement'),
        ('processed', 'Traité'),
        ('error', 'Erreur'),
        ('approved', 'Approuvé'),
    ]

    # Relations
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='fichiers_importes',
        verbose_name="Utilisateur"
    )
    mission = models.ForeignKey(
        'accounts.Mission',
        on_delete=models.CASCADE,
        related_name='fichiers',
        verbose_name="Mission"
    )

    # Informations du fichier
    type_fichier = models.CharField(
        max_length=30,
        choices=TYPES_FICHIER,
        verbose_name="Type de fichier"
    )
    fichier = models.FileField(
        upload_to=upload_to_mission_folder,
        validators=[validate_file_extension, validate_file_size],
        verbose_name="Fichier"
    )
    nom_fichier = models.CharField(max_length=255, verbose_name="Nom du fichier")
    nom_original = models.CharField(max_length=255, verbose_name="Nom original")
    taille_fichier = models.PositiveIntegerField(help_text="Taille en bytes")

    # Dates
    date_import = models.DateTimeField(auto_now_add=True, verbose_name="Date d'import")
    date_modification = models.DateTimeField(auto_now=True, verbose_name="Dernière modification")

    # Traitement et analyse
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name="Statut"
    )
    nb_lignes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Nombre de lignes détectées"
    )
    colonnes_detectees = models.JSONField(
        default=list,
        help_text="Liste des colonnes détectées"
    )
    erreurs_processing = models.TextField(
        blank=True,
        help_text="Erreurs lors du traitement"
    )

    # Validation et approbation
    est_valide = models.BooleanField(default=False, verbose_name="Fichier validé")
    approuve_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fichiers_approuves',
        verbose_name="Approuvé par"
    )
    date_approbation = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date d'approbation"
    )

    # Historique/versioning
    version = models.PositiveIntegerField(default=1, verbose_name="Version")
    fichier_precedent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Version précédente de ce fichier",
        verbose_name="Fichier précédent"
    )

    class Meta:
        ordering = ['-date_import']
        verbose_name = "Fichier importé"
        verbose_name_plural = "Fichiers importés"
        unique_together = ['mission', 'type_fichier', 'version']

    def __str__(self):
        # Gestion sécurisée du nom de la mission
        mission_display = self.get_mission_display()
        return f"{self.get_type_fichier_display()} - {self.nom_fichier} ({mission_display})"

    def get_mission_display(self):
        """Retourne le nom d'affichage de la mission"""
        if not self.mission:
            return "Aucune mission"

        # Essayer différents attributs possibles
        if hasattr(self.mission, 'nom') and self.mission.nom:
            return self.mission.nom
        elif hasattr(self.mission, 'name') and self.mission.name:
            return self.mission.name
        elif hasattr(self.mission, 'title') and self.mission.title:
            return self.mission.title
        elif hasattr(self.mission, 'libelle') and self.mission.libelle:
            return self.mission.libelle
        else:
            return f"Mission #{self.mission.id}"

    def save(self, *args, **kwargs):
        """Override save pour auto-remplir certains champs"""
        if self.fichier:
            self.nom_original = self.fichier.name
            self.taille_fichier = self.fichier.size
            if not self.nom_fichier:
                self.nom_fichier = os.path.splitext(self.nom_original)[0]

        # Auto-assigner la mission de l'utilisateur si pas définie
        if not self.mission_id and self.utilisateur and self.utilisateur.mission:
            self.mission = self.utilisateur.mission

        super().save(*args, **kwargs)

    def get_file_extension(self):
        """Retourne l'extension du fichier"""
        return os.path.splitext(self.nom_original)[1].lower()

    def get_file_size_mb(self):
        """Retourne la taille en MB"""
        return round(self.taille_fichier / (1024 * 1024), 2)

    def peut_etre_modifie_par(self, user):
        """Vérifie si un utilisateur peut modifier ce fichier (avec paramètre user)"""
        if user.is_admin():
            return True
        return self.utilisateur == user

    @property
    def peut_etre_modifie(self):
        """Propriété pour vérifier si le fichier peut être modifié (pour le template)"""
        return self.status in ['pending', 'error', 'processing']

    def user_can_modify(self, user):
        """Méthode helper pour vérifier les permissions d'un utilisateur spécifique"""
        return self.peut_etre_modifie and self.peut_etre_modifie_par(user)

    def get_colonnes_manquantes(self):
        """Retourne les colonnes manquantes selon le type de fichier"""
        colonnes_obligatoires = {
            'paie': ['matricule', 'nom', 'prenom', 'salaire_brut', 'montant_total'],
            'liste_personnel': ['matricule', 'nom', 'prenom', 'poste'],
            'grille': ['poste', 'niveau', 'salaire_min', 'salaire_max'],
            'convention': ['type_prime', 'montant', 'condition'],
            'procedure': ['regle', 'description']
        }

        obligatoires = colonnes_obligatoires.get(self.type_fichier, [])
        colonnes_detectees_lower = [col.lower() for col in self.colonnes_detectees]

        return [col for col in obligatoires if col not in colonnes_detectees_lower]


class PreviewData(models.Model):
    """Stocke un aperçu des données du fichier pour prévisualisation"""

    fichier = models.OneToOneField(
        FichierImporte,
        on_delete=models.CASCADE,
        related_name='preview',
        verbose_name="Fichier"
    )
    colonnes = models.JSONField(
        help_text="Liste des colonnes du fichier",
        verbose_name="Colonnes"
    )
    donnees_echantillon = models.JSONField(
        help_text="Premières lignes pour prévisualisation",
        verbose_name="Données échantillon"
    )
    nb_total_lignes = models.PositiveIntegerField(verbose_name="Nombre total de lignes")
    date_creation = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")

    class Meta:
        verbose_name = "Aperçu des données"
        verbose_name_plural = "Aperçus des données"

    def __str__(self):
        return f"Aperçu - {self.fichier.nom_fichier}"

    def get_sample_data(self, nb_lignes=5):
        """Retourne un échantillon limité des données"""
        return self.donnees_echantillon[:nb_lignes]


class MappingColonne(models.Model):
    """Modèle pour mapper les colonnes du fichier aux colonnes attendues"""

    fichier = models.ForeignKey(
        FichierImporte,
        on_delete=models.CASCADE,
        related_name='mappings',
        verbose_name="Fichier"
    )
    colonne_fichier = models.CharField(
        max_length=100,
        verbose_name="Colonne du fichier"
    )
    colonne_attendue = models.CharField(
        max_length=100,
        verbose_name="Colonne attendue"
    )
    est_confirme = models.BooleanField(
        default=False,
        verbose_name="Mapping confirmé"
    )
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mapping de colonne"
        verbose_name_plural = "Mappings de colonnes"
        unique_together = ['fichier', 'colonne_attendue']

    def __str__(self):
        return f"{self.colonne_fichier} → {self.colonne_attendue}"
