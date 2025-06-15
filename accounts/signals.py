# accounts/signals.py - VERSION CORRIGÉE
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_logged_out
from .models import CustomUser, Mission, UserLog
from .utils import log_user_action

@receiver(post_save, sender=CustomUser)
def user_saved(sender, instance, created, **kwargs):
    """Signal déclenché lors de la sauvegarde d'un utilisateur"""
    _ = sender, kwargs
    if created:
        UserLog.objects.create(
            user=instance,
            action="creation_auto",
            feature="Système",
            target=instance.username,
            resource_id=str(instance.id),
            new_value=f"Utilisateur créé: {instance.get_full_name()}",
            status="success"
        )

@receiver(post_save, sender=Mission)
def mission_saved(sender, instance, created, **kwargs):
    """Signal déclenché lors de la sauvegarde d'une mission"""
    _ = sender, kwargs
    if created:
        UserLog.objects.create(
            user=None,
            action="creation_auto",
            feature="Système",
            target=instance.name,
            resource_id=str(instance.id),
            new_value=f"Mission créée: {instance.name} - {instance.client}",
            status="success"
        )

@receiver(user_logged_in)
def user_logged_in_handler(sender, request, user, **kwargs):
    """Signal déclenché lors de la connexion"""
    _ = sender, request, kwargs  # ✅ Marquer request comme non utilisé
    if isinstance(user, CustomUser):
        user.update_last_activity()

@receiver(user_logged_out)
def user_logged_out_handler(sender, request, user, **kwargs):
    """Signal déclenché lors de la déconnexion"""
    _ = sender, kwargs  # ✅ Request est utilisé ici donc pas besoin de le marquer
    if isinstance(user, CustomUser):
        log_user_action(
            user=user,
            action="deconnexion_auto",
            feature="Authentification",
            status="success",
            request=request
        )
