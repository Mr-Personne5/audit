from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone



class Mission(models.Model):
    """Modèle pour isoler les données par mission d'audit"""
    name = models.CharField(max_length=200, verbose_name="Nom de la mission")
    client = models.CharField(max_length=200, verbose_name="Client", blank=True)
    description = models.TextField(blank=True, verbose_name="Description")
    start_date = models.DateField(verbose_name="Date de début")
    end_date = models.DateField(null=True, blank=True, verbose_name="Date de fin")
    assigned_auditor = models.ForeignKey(
        'CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Auditeur assigné",
        related_name='assigned_missions',
        limit_choices_to={'role': 'user'}
    )
    is_active = models.BooleanField(default=True, verbose_name="Mission active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.client}"


class CustomUser(AbstractUser):
    """Utilisateur personnalisé avec rôles et mission assignée"""
    ROLE_CHOICES = [
        ('admin', 'Administrateur'),
        ('user', 'Auditeur'),
    ]

    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default='user',
        verbose_name="Rôle"
    )
    mission = models.ForeignKey(
        Mission,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Mission assignée"
    )
    phone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_activity = models.DateTimeField(null=True, blank=True)

    def is_admin(self):
        return self.role == 'admin'

    def is_auditor(self):
        return self.role == 'user'

    def update_last_activity(self):
        self.last_activity = timezone.now()
        self.save(update_fields=['last_activity'])

    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"


# accounts/models.py - CORRIGER la classe UserLog

class UserLog(models.Model):
    """Modèle pour traçabilité complète des actions"""
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,  # ✅ Changer CASCADE en SET_NULL
        null=True, blank=True,      # ✅ AJOUTER null=True, blank=True
        verbose_name="Utilisateur"
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=100, verbose_name="Action")
    feature = models.CharField(max_length=100, verbose_name="Fonctionnalité")
    target = models.CharField(max_length=100, blank=True, verbose_name="Cible")
    resource_id = models.CharField(max_length=50, blank=True, verbose_name="ID Ressource")
    old_value = models.TextField(blank=True, verbose_name="Ancienne valeur")
    new_value = models.TextField(blank=True, verbose_name="Nouvelle valeur")
    status = models.CharField(max_length=20, default='success', verbose_name="Statut")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Log utilisateur"
        verbose_name_plural = "Logs utilisateurs"

    def __str__(self):
        user_display = self.user.username if self.user else "Système"
        return f"{user_display} - {self.action} - {self.feature}"

    def to_json(self):
        """Conversion en format JSON pour les logs externes"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "user_id": self.user.id if self.user else None,  # ✅ AJOUTER protection si user est None
            "user_name": self.user.username if self.user else "Système",  # ✅ AJOUTER protection
            "role": self.user.get_role_display() if self.user else "Système",  # ✅ AJOUTER protection
            "action": self.action,
            "feature": self.feature,
            "target": self.target,
            "resource_id": self.resource_id,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "status": self.status,
            "ip": self.ip_address,
            "user_agent": self.user_agent
        }
