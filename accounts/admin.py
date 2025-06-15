from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Mission, UserLog


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """Interface d'administration pour les utilisateurs personnalisés"""
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'mission', 'is_active', 'last_activity')
    list_filter = ('role', 'is_active', 'mission', 'date_joined')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    ordering = ('-date_joined',)

    fieldsets = UserAdmin.fieldsets + (
        ('Informations AuditIA', {
            'fields': ('role', 'mission', 'phone', 'last_activity')
        }),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Informations AuditIA', {
            'fields': ('role', 'mission', 'phone')
        }),
    )


@admin.register(Mission)
class MissionAdmin(admin.ModelAdmin):
    """Interface d'administration pour les missions"""
    list_display = ('name', 'client', 'start_date', 'end_date', 'is_active', 'users_count', 'created_at')
    list_filter = ('is_active', 'start_date', 'created_at')
    search_fields = ('name', 'client', 'description')
    date_hierarchy = 'start_date'
    ordering = ('-created_at',)

    def users_count(self, obj):
        """Nombre d'utilisateurs assignés"""
        return obj.customuser_set.count()

    users_count.short_description = 'Nb Utilisateurs'


@admin.register(UserLog)
class UserLogAdmin(admin.ModelAdmin):
    """Interface d'administration pour les logs"""
    list_display = ('timestamp', 'user', 'action', 'feature', 'target', 'status', 'ip_address')
    list_filter = ('action', 'feature', 'status', 'timestamp')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'action', 'feature', 'target')
    date_hierarchy = 'timestamp'
    ordering = ('-timestamp',)
    readonly_fields = ('timestamp', 'user', 'action', 'feature', 'target', 'resource_id',
                       'old_value', 'new_value', 'status', 'ip_address', 'user_agent')

    def has_add_permission(self, request):
        """Empêcher l'ajout manuel de logs"""
        return False

    def has_change_permission(self, request, obj=None):
        """Empêcher la modification des logs"""
        return False


# Configuration des titres de l'admin
admin.site.site_header = "AuditIA Administration"
admin.site.site_title = "AuditIA Admin"
admin.site.index_title = "Tableau de bord administrateur"
