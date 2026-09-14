# auditengine/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import ResultatAudit


@receiver(post_save, sender=ResultatAudit)
def recalculer_compteurs_session(sender, instance, **kwargs):
    """Maintient les compteurs dénormalisés de SessionAudit synchronisés.

    bulk_create() (utilisé par AuditEngine pour la création initiale des
    résultats) ne déclenche pas ce signal, donc il n'alourdit pas le
    traitement d'un audit complet. Il couvre les mises à jour individuelles
    postérieures — corriger_anomalie, valider_resultat — qui, avant ce
    correctif, désynchronisaient silencieusement les compteurs affichés sur
    les dashboards et nécessitaient des scripts de réparation manuels ad hoc.
    """
    instance.session.recalculer_compteurs()
