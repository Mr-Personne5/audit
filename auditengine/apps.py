from django.apps import AppConfig


class AuditengineConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'auditengine'

    def ready(self):
        from . import signals  # noqa: F401
