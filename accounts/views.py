from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.http import JsonResponse

from .forms import CustomUserCreationForm, CustomUserChangeForm, MissionForm
from .models import CustomUser, Mission, UserLog
from .utils import log_user_action, log_authentication
from uploads.models import FichierImporte
from auditengine.models import ResultatAudit


# === HELPERS ===
def is_admin(user):
    """Vérifier si l'utilisateur est admin"""
    return user.is_authenticated and user.is_admin()


# === AUTH VIEWS ===
def login_view(request):
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            user.update_last_activity()
            log_authentication(user, "connexion", "success", request)
            messages.success(request, f"Bienvenue {user.get_full_name()} 👋")
            return redirect('accounts:dashboard')
        else:
            messages.error(request, "Nom d'utilisateur ou mot de passe incorrect")

    return render(request, 'accounts/login.html')


@login_required
def logout_view(request):
    log_authentication(request.user, "deconnexion", "success", request)
    logout(request)
    messages.info(request, "Vous avez été déconnecté avec succès")
    return redirect('accounts:login')


# === TABLEAU DE BORD VIEWS ===
@login_required
def dashboard(request):
    user = request.user
    user.update_last_activity()

    context = {
        'user': user,
        'current_mission': user.mission
    }

    if user.is_admin():
        today = timezone.now().date()
        context.update({
            'active_users_count': CustomUser.objects.filter(is_active=True).count(),
            'active_missions_count': Mission.objects.filter(is_active=True).count(),
            'actions_today_count': FichierImporte.objects.filter(date_import__date=today).count(),
            'imported_files_count': FichierImporte.objects.count(),
            'fichiers_en_attente': FichierImporte.objects.filter(status='pending')
                .select_related('utilisateur', 'mission').order_by('-date_import'),
            'recent_logs': UserLog.objects.select_related('user').order_by('-timestamp')[:8],
        })
        template = 'accounts/dashboard_admin.html'
    else:
        template = 'accounts/dashboard_user.html'

    log_user_action(user, "consultation", "Tableau de bord", request=request)
    return render(request, template, context)


@login_required
@user_passes_test(is_admin)
def dashboard_advanced(request):
    """Vue du tableau de bord avancé avec métriques en temps réel"""
    return render(request, 'accounts/dashboard_advanced.html')


@login_required
@user_passes_test(is_admin)
def mission_supervision(request):
    """Vue de supervision des missions avec vue d'ensemble complète"""
    missions = Mission.objects.filter(is_active=True).order_by('-created_at')
    
    context = {
        'missions': missions,
    }
    
    return render(request, 'accounts/mission_supervision.html', context)


@login_required
def dashboard_admin_stats_api(request):
    today = timezone.now().date()
    stats = {
        'active_users_count': CustomUser.objects.filter(is_active=True).count(),
        'active_missions_count': Mission.objects.filter(is_active=True).count(),
        'actions_today_count': FichierImporte.objects.filter(date_import__date=today).count(),
        'imported_files_count': FichierImporte.objects.count(),
    }
    return JsonResponse(stats)


@login_required
def dashboard_user_stats_api(request):
    user = request.user
    # Fichiers traités par l'utilisateur
    fichiers_traite_count = FichierImporte.objects.filter(utilisateur=user, status='processed').count()
    # Anomalies trouvées sur ses fichiers (via sessions qu'il a lancées)
    anomalies_count = ResultatAudit.objects.filter(session__utilisateur=user).count()
    # Taux de précision (exemple : % de fichiers sans erreur)
    total = FichierImporte.objects.filter(utilisateur=user).count()
    taux_precision = round(100 * fichiers_traite_count / total, 1) if total else 0
    stats = {
        'fichiers_traite_count': fichiers_traite_count,
        'anomalies_count': anomalies_count,
        'taux_precision': taux_precision,
    }
    return JsonResponse(stats)


# === USER MANAGEMENT VIEWS ===
@login_required
@user_passes_test(is_admin)
def user_list(request):
    all_users = CustomUser.objects.select_related('mission').order_by('first_name', 'last_name')
    search = request.GET.get('search', '')
    role_filter = request.GET.get('role', '')

    users = all_users
    if search:
        users = users.filter(
            Q(username__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search)
        )

    if role_filter:
        users = users.filter(role=role_filter)

    paginator = Paginator(users, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'accounts/user_list.html', {
        'page_obj': page_obj,
        'search': search,
        'role_filter': role_filter,
        'role_choices': CustomUser.ROLE_CHOICES,
        'stats': {
            'total': all_users.count(),
            'actifs': all_users.filter(is_active=True).count(),
            'admins': all_users.filter(role='admin').count(),
            'auditeurs': all_users.filter(role='user').count(),
        },
    })


@login_required
@user_passes_test(is_admin)
def user_create(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            log_user_action(request.user, "creation", "Utilisateur",
                            target=user.username, resource_id=str(user.id))
            messages.success(request, f"Utilisateur {user.get_full_name()} créé avec succès")
            return redirect('accounts:user_list')
    else:
        form = CustomUserCreationForm()

    return render(request, 'accounts/user_form.html', {
        'form': form,
        'title': 'Créer un utilisateur'
    })


@login_required
@user_passes_test(is_admin)
def user_edit(request, user_id):
    user_obj = get_object_or_404(CustomUser, id=user_id)

    if request.method == 'POST':
        form = CustomUserChangeForm(request.POST, instance=user_obj)
        if form.is_valid():
            user = form.save()
            log_user_action(request.user, "modification", "Utilisateur",
                            target=user.username, resource_id=str(user.id))
            messages.success(request, f"Utilisateur {user.get_full_name()} modifié avec succès")
            return redirect('accounts:user_list')
    else:
        form = CustomUserChangeForm(instance=user_obj)

    return render(request, 'accounts/user_form.html', {
        'form': form,
        'title': f'Modifier {user_obj.get_full_name()}'
    })


@login_required
@user_passes_test(is_admin)
def user_delete(request, user_id):
    user_obj = get_object_or_404(CustomUser, id=user_id)

    if request.method == 'POST':
        user_obj.is_active = False
        user_obj.save()
        log_user_action(request.user, "suppression", "Utilisateur",
                        target=user_obj.username, resource_id=str(user_obj.id))
        messages.success(request, f"Utilisateur {user_obj.get_full_name()} désactivé avec succès")
        return redirect('accounts:user_list')

    return render(request, 'accounts/user_confirm_delete.html', {'user_obj': user_obj})


@login_required
@user_passes_test(is_admin)
def user_update(request, user_id):
    user_obj = get_object_or_404(CustomUser, id=user_id)

    if request.method == 'POST':
        form = CustomUserChangeForm(request.POST, instance=user_obj)
        if form.is_valid():
            user = form.save()
            log_user_action(request.user, "mise_a_jour", "Utilisateur",
                            target=user.username, resource_id=str(user.id))
            messages.success(request, f"Utilisateur {user.get_full_name()} mis à jour avec succès")
            return redirect('accounts:user_list')
    else:
        form = CustomUserChangeForm(instance=user_obj)

    return render(request, 'accounts/user_form.html', {
        'form': form,
        'title': f'Mettre à jour {user_obj.get_full_name()}'
    })


# === MISSION MANAGEMENT VIEWS ===
@login_required
@user_passes_test(is_admin)
def mission_list(request):
    missions = Mission.objects.all().order_by('-created_at')
    
    # Calculer les statistiques correctement
    total_missions = missions.count()
    missions_actives = missions.filter(is_active=True).count()
    missions_terminees = missions.filter(is_active=False).count()
    
    # Compter les utilisateurs assignés (un utilisateur peut être assigné à une seule mission)
    utilisateurs_assignes = CustomUser.objects.filter(mission__isnull=False).count()
    
    # Compter les missions avec auditeur assigné
    missions_avec_auditeur = missions.filter(assigned_auditor__isnull=False).count()
    
    context = {
        'missions': missions,
        'today': timezone.now().date(),
        'stats': {
            'total_missions': total_missions,
            'missions_actives': missions_actives,
            'missions_terminees': missions_terminees,
            'utilisateurs_assignes': utilisateurs_assignes,
            'missions_avec_auditeur': missions_avec_auditeur,
        }
    }
    
    return render(request, 'accounts/mission_list.html', context)


@login_required
@user_passes_test(is_admin)
def mission_create(request):
    if request.method == 'POST':
        form = MissionForm(request.POST)
        if form.is_valid():
            mission = form.save()
            log_user_action(request.user, "creation", "Mission",
                            target=mission.name, resource_id=str(mission.id))
            messages.success(request, f"Mission {mission.name} créée avec succès")
            return redirect('accounts:mission_list')
    else:
        form = MissionForm()

    return render(request, 'accounts/mission_form.html', {
        'form': form,
        'title': 'Créer une mission'
    })


@login_required
@user_passes_test(is_admin)
def mission_edit(request, mission_id):
    mission = get_object_or_404(Mission, id=mission_id)

    if request.method == 'POST':
        form = MissionForm(request.POST, instance=mission)
        if form.is_valid():
            mission = form.save()
            log_user_action(request.user, "modification", "Mission",
                            target=mission.name, resource_id=str(mission.id))
            messages.success(request, f"Mission {mission.name} modifiée avec succès")
            return redirect('accounts:mission_list')
    else:
        form = MissionForm(instance=mission)

    return render(request, 'accounts/mission_form.html', {
        'form': form,
        'title': f'Modifier {mission.name}'
    })


@login_required
@user_passes_test(is_admin)
def mission_delete(request, mission_id):
    mission = get_object_or_404(Mission, id=mission_id)

    if request.method == 'POST':
        mission.is_active = False
        mission.save()
        log_user_action(request.user, "suppression", "Mission",
                        target=mission.name, resource_id=str(mission.id))
        messages.success(request, f"Mission {mission.name} désactivée avec succès")
        return redirect('accounts:mission_list')

    return render(request, 'accounts/mission_confirm_delete.html', {'mission': mission})


@login_required
@user_passes_test(is_admin)
def mission_update(request, mission_id):
    mission = get_object_or_404(Mission, id=mission_id)

    if request.method == 'POST':
        form = MissionForm(request.POST, instance=mission)
        if form.is_valid():
            mission = form.save()
            log_user_action(request.user, "mise_a_jour", "Mission",
                            target=mission.name, resource_id=str(mission.id))
            messages.success(request, f"Mission {mission.name} mise à jour avec succès")
            return redirect('accounts:mission_list')
    else:
        form = MissionForm(instance=mission)

    return render(request, 'accounts/mission_form.html', {
        'form': form,
        'title': f'Mettre à jour {mission.name}'
    })


# === LOGS VIEW ===
@login_required
@user_passes_test(is_admin)
def logs_view(request):
    logs = UserLog.objects.select_related('user').all()
    paginator = Paginator(logs, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'accounts/logs.html', {
        'page_obj': page_obj,
        'users_list': CustomUser.objects.all()
    })


# === USER PROFILE VIEWS ===
@login_required
def user_profile(request):
    """Vue pour afficher et modifier le profil de l'utilisateur connecté"""
    user = request.user
    
    if request.method == 'POST':
        form = CustomUserChangeForm(request.POST, instance=user)
        if form.is_valid():
            user = form.save()
            log_user_action(user, "modification", "Profil utilisateur", request=request)
            messages.success(request, "Votre profil a été mis à jour avec succès")
            return redirect('accounts:user_profile')
    else:
        form = CustomUserChangeForm(instance=user)
    
    # Statistiques personnelles
    stats = {
        'fichiers_importes': FichierImporte.objects.filter(utilisateur=user).count(),
        'sessions_audit': ResultatAudit.objects.filter(session__utilisateur=user).values('session').distinct().count(),
        'anomalies_detectees': ResultatAudit.objects.filter(session__utilisateur=user).count(),
        'derniere_activite': user.last_activity,
    }
    
    # Logs récents de l'utilisateur
    logs_recents = UserLog.objects.filter(user=user).order_by('-timestamp')[:10]
    
    context = {
        'form': form,
        'stats': stats,
        'logs_recents': logs_recents,
    }
    
    return render(request, 'accounts/user_profile.html', context)


@login_required
def user_settings(request):
    """Vue pour les paramètres de l'utilisateur"""
    user = request.user
    
    if request.method == 'POST':
        # Traitement des paramètres (à implémenter selon les besoins)
        messages.success(request, "Vos paramètres ont été mis à jour")
        return redirect('accounts:user_settings')
    
    # Paramètres actuels
    settings = {
        'notifications_email': True,  # À connecter avec un modèle de préférences
        'notifications_browser': True,
        'theme': 'light',  # light/dark
        'language': 'fr',
    }
    
    context = {
        'settings': settings,
    }
    
    return render(request, 'accounts/user_settings.html', context)


@login_required
def user_logs_personal(request):
    """Vue pour afficher les logs personnels de l'utilisateur"""
    user = request.user
    logs = UserLog.objects.filter(user=user).order_by('-timestamp')
    
    paginator = Paginator(logs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
    }
    
    return render(request, 'accounts/user_logs_personal.html', context)


# === ADMIN API VIEWS ===
@login_required
@user_passes_test(is_admin)
def admin_alerts_api(request):
    """API pour récupérer les alertes administratives dynamiquement"""
    from datetime import datetime, timedelta
    
    # Calculer les vraies statistiques
    today = timezone.now().date()
    yesterday = today - timedelta(days=1)
    
    # Alertes basées sur différents critères
    alerts = {
        'total_alerts': 0,
        'new_users_today': 0,
        'failed_logins': 0,
        'system_errors': 0,
        'pending_actions': 0,
        'security_alerts': 0,
    }
    
    # Nouveaux utilisateurs aujourd'hui
    new_users_today = CustomUser.objects.filter(date_joined__date=today).count()
    alerts['new_users_today'] = new_users_today
    
    # Tentatives de connexion échouées récentes (simulation)
    # En production, vous auriez un modèle pour tracker les tentatives de connexion
    failed_logins = 0  # À implémenter avec un vrai système de tracking
    alerts['failed_logins'] = failed_logins
    
    # Erreurs système (simulation)
    # En production, vous auriez un système de logging d'erreurs
    system_errors = 0  # À implémenter avec un vrai système de monitoring
    alerts['system_errors'] = system_errors
    
    # Actions en attente (utilisateurs inactifs, missions expirées, etc.)
    inactive_users = CustomUser.objects.filter(
        is_active=True,
        last_activity__lt=timezone.now() - timedelta(days=30)
    ).count()
    
    expired_missions = Mission.objects.filter(
        is_active=True,
        created_at__lt=timezone.now() - timedelta(days=90)
    ).count()
    
    alerts['pending_actions'] = inactive_users + expired_missions
    
    # Alertes de sécurité (simulation)
    # En production, vous auriez des vérifications de sécurité
    security_alerts = 0  # À implémenter avec un vrai système de sécurité
    alerts['security_alerts'] = security_alerts
    
    # Total des alertes
    alerts['total_alerts'] = (
        alerts['new_users_today'] + 
        alerts['failed_logins'] + 
        alerts['system_errors'] + 
        alerts['pending_actions'] + 
        alerts['security_alerts']
    )
    
    # Statistiques générales pour le menu
    stats = {
        'total_users': CustomUser.objects.filter(is_active=True).count(),
        'total_missions': Mission.objects.filter(is_active=True).count(),
        'recent_logs': UserLog.objects.filter(timestamp__date=today).count(),
        'system_status': 'OK' if alerts['total_alerts'] == 0 else 'WARNING',
    }
    
    return JsonResponse({
        'alerts': alerts,
        'stats': stats,
        'timestamp': timezone.now().isoformat(),
    })


@login_required
@user_passes_test(is_admin)
def dashboard_advanced_metrics_api(request):
    """API pour les métriques avancées du tableau de bord"""
    try:
        from datetime import timedelta

        # Paramètres de filtrage temporel
        time_range = request.GET.get('time_range', 'today')
        today = timezone.now().date()
        
        if time_range == 'week':
            start_date = today - timedelta(days=7)
        elif time_range == 'month':
            start_date = today - timedelta(days=30)
        else:  # today
            start_date = today
        
        # Métriques d'anomalies calculées sur la période sélectionnée
        resultats_periode = ResultatAudit.objects.filter(date_creation__date__gte=start_date)
        total_lignes = resultats_periode.count()
        total_anomalies = resultats_periode.filter(est_anomalie=True).count()
        detection_rate = round((total_anomalies / total_lignes) * 100, 1) if total_lignes else 0

        # Taux de confirmation des anomalies validées par un humain (proxy de la précision du modèle)
        anomalies_validees = resultats_periode.filter(est_anomalie=True, valide_par_humain=True)
        nb_validees = anomalies_validees.count()
        nb_confirmees = anomalies_validees.filter(est_fausse_alerte=False).count()
        accuracy_rate = round((nb_confirmees / nb_validees) * 100, 1) if nb_validees else 0

        # Calcul des tendances par rapport à la période précédente de même durée
        duree_periode = max((today - start_date).days, 1)
        debut_periode_precedente = start_date - timedelta(days=duree_periode)
        resultats_periode_precedente = ResultatAudit.objects.filter(
            date_creation__date__gte=debut_periode_precedente,
            date_creation__date__lt=start_date
        )
        total_lignes_precedent = resultats_periode_precedente.count()
        total_anomalies_precedent = resultats_periode_precedente.filter(est_anomalie=True).count()
        detection_rate_precedent = round(
            (total_anomalies_precedent / total_lignes_precedent) * 100, 1
        ) if total_lignes_precedent else 0

        anomalies_trend = (
            ((total_anomalies - total_anomalies_precedent) / total_anomalies_precedent) * 100
        ) if total_anomalies_precedent else 0
        detection_trend = detection_rate - detection_rate_precedent

        # Actions aujourd'hui
        today_actions = UserLog.objects.filter(timestamp__date=today).count()
        
        # Fichiers en attente d'approbation
        pending_approvals = FichierImporte.objects.filter(status='pending').count()
        
        # Missions actives avec progression
        active_missions = Mission.objects.filter(is_active=True).count()
        
        # Alertes intelligentes
        alerts = []
        
        # Alerte pour fichiers en attente
        if pending_approvals > 5:
            alerts.append({
                'level': 'warning',
                'title': 'Fichiers en attente',
                'message': f'{pending_approvals} fichiers nécessitent votre approbation'
            })
        
        # Alerte pour missions sans auditeur
        missions_without_auditor = Mission.objects.filter(
            is_active=True, 
            assigned_auditor__isnull=True
        ).count()
        
        if missions_without_auditor > 0:
            alerts.append({
                'level': 'info',
                'title': 'Missions non assignées',
                'message': f'{missions_without_auditor} missions actives sans auditeur assigné'
            })
        
        # Alerte pour taux de détection élevé
        if detection_rate > 95:
            alerts.append({
                'level': 'success',
                'title': 'Performance excellente',
                'message': f'Taux de détection de {detection_rate}% - Très bon résultat !'
            })
        
        # Statut des missions avec progression
        mission_status = []
        missions = Mission.objects.filter(is_active=True)[:5]  # Limiter à 5 missions
        
        for mission in missions:
            # Progression réelle basée sur les activités terminées (fichiers, analyses, rapprochements)
            files_total = mission.fichiers.count()
            files_done = mission.fichiers.filter(status='processed').count()
            analyses_total = mission.sessions_audit.count()
            analyses_done = mission.sessions_audit.filter(status='completed').count()
            reconciliations_total = mission.rapprochements.count()
            reconciliations_done = mission.rapprochements.filter(status='completed').count()

            total_activities = files_total + analyses_total + reconciliations_total
            completed_activities = files_done + analyses_done + reconciliations_done
            progress = min(100, int((completed_activities / total_activities) * 100)) if total_activities else 0

            # Détermination du statut
            if progress >= 90:
                status = 'completed'
            elif progress >= 50:
                status = 'active'
            else:
                status = 'pending'
            
            mission_status.append({
                'name': mission.name,
                'client': mission.client,
                'status': status,
                'progress': progress
            })
        
        return JsonResponse({
            'total_anomalies': total_anomalies,
            'detection_rate': detection_rate,
            'accuracy_rate': accuracy_rate,
            'active_missions': active_missions,
            'pending_approvals': pending_approvals,
            'today_actions': today_actions,
            'anomalies_trend': round(anomalies_trend, 1),
            'detection_trend': round(detection_trend, 1),
            'alerts': alerts,
            'mission_status': mission_status,
            'time_range': time_range
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@user_passes_test(is_admin)
def mission_supervision_data_api(request):
    """API pour les données de supervision des missions"""
    try:
        from django.db.models import Count, Q
        from datetime import datetime, timedelta
        
        # Récupérer toutes les missions actives avec leurs statistiques
        missions = Mission.objects.filter(is_active=True).prefetch_related(
            'fichiers',
            'sessions_audit',
            'rapprochements'
        )
        
        missions_data = []
        
        for mission in missions:
            # Compter les fichiers importés avec différents statuts
            files_stats = mission.fichiers.aggregate(
                total=Count('id'),
                pending=Count('id', filter=Q(status='pending')),
                processed=Count('id', filter=Q(status='processed')),
                error=Count('id', filter=Q(status='error'))
            )
            
            # Compter les analyses (sessions d'audit) avec leurs résultats
            analyses_stats = mission.sessions_audit.aggregate(
                total=Count('id'),
                completed=Count('id', filter=Q(status='completed')),
                running=Count('id', filter=Q(status='running')),
                error=Count('id', filter=Q(status='error'))
            )
            
            # Compter les anomalies détectées pour cette mission
            anomalies_count = ResultatAudit.objects.filter(
                session__mission=mission
            ).count()
            
            # Compter les rapprochements
            reconciliations_stats = mission.rapprochements.aggregate(
                total=Count('id'),
                completed=Count('id', filter=Q(status='completed')),
                running=Count('id', filter=Q(status='running')),
                error=Count('id', filter=Q(status='error'))
            )
            
            # Calculer la progression basée sur les activités réelles
            total_activities = (
                files_stats['total'] + 
                analyses_stats['total'] + 
                reconciliations_stats['total']
            )
            
            if total_activities > 0:
                # Progression basée sur les activités complétées
                completed_activities = (
                    files_stats['processed'] + 
                    analyses_stats['completed'] + 
                    reconciliations_stats['completed']
                )
                progress = min(100, int((completed_activities / total_activities) * 100))
            else:
                progress = 0
            
            # Calculer les statistiques de performance
            performance_stats = {
                'files_success_rate': (
                    round((files_stats['processed'] / files_stats['total']) * 100, 1) 
                    if files_stats['total'] > 0 else 0
                ),
                'analyses_success_rate': (
                    round((analyses_stats['completed'] / analyses_stats['total']) * 100, 1) 
                    if analyses_stats['total'] > 0 else 0
                ),
                'reconciliations_success_rate': (
                    round((reconciliations_stats['completed'] / reconciliations_stats['total']) * 100, 1) 
                    if reconciliations_stats['total'] > 0 else 0
                )
            }
            
            # Calculer les tendances (activité récente)
            today = timezone.now().date()
            week_ago = today - timedelta(days=7)
            
            recent_files = mission.fichiers.filter(date_import__date__gte=week_ago).count()
            recent_analyses = mission.sessions_audit.filter(date_creation__date__gte=week_ago).count()
            recent_reconciliations = mission.rapprochements.filter(date_creation__date__gte=week_ago).count()
            
            missions_data.append({
                'id': mission.id,
                'name': mission.name,
                'client': mission.client,
                'description': mission.description,
                'is_active': mission.is_active,
                
                # Statistiques de base
                'files_count': files_stats['total'],
                'analyses_count': analyses_stats['total'],
                'reconciliations_count': reconciliations_stats['total'],
                'anomalies_count': anomalies_count,
                
                # Statistiques détaillées
                'files_stats': files_stats,
                'analyses_stats': analyses_stats,
                'reconciliations_stats': reconciliations_stats,
                
                # Performance
                'performance_stats': performance_stats,
                'progress': progress,
                
                # Activité récente
                'recent_activity': {
                    'files': recent_files,
                    'analyses': recent_analyses,
                    'reconciliations': recent_reconciliations
                },
                
                # Informations de base
                'start_date': mission.start_date,
                'end_date': mission.end_date,
                'assigned_auditor': mission.assigned_auditor.get_full_name() if mission.assigned_auditor else None,
                'created_at': mission.created_at,
                'updated_at': mission.updated_at
            })
        
        # Ajouter des statistiques globales
        global_stats = {
            'total_missions': missions.count(),
            'total_files': sum(m['files_count'] for m in missions_data),
            'total_analyses': sum(m['analyses_count'] for m in missions_data),
            'total_reconciliations': sum(m['reconciliations_count'] for m in missions_data),
            'total_anomalies': sum(m['anomalies_count'] for m in missions_data),
            'average_progress': round(sum(m['progress'] for m in missions_data) / len(missions_data), 1) if missions_data else 0
        }
        
        return JsonResponse({
            'missions': missions_data,
            'global_stats': global_stats,
            'timestamp': timezone.now().isoformat()
        })
        
    except Exception as e:
        import traceback
        print(f"Erreur dans mission_supervision_data_api: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@user_passes_test(is_admin)
def mission_details_api(request, mission_id):
    """API pour les détails d'une mission spécifique"""
    try:
        mission = get_object_or_404(Mission, id=mission_id)
        
        mission_data = {
            'id': mission.id,
            'name': mission.name,
            'client': mission.client,
            'description': mission.description,
            'start_date': mission.start_date,
            'end_date': mission.end_date,
            'is_active': mission.is_active,
            'assigned_auditor': mission.assigned_auditor.get_full_name() if mission.assigned_auditor else None,
            'created_at': mission.created_at,
            'updated_at': mission.updated_at
        }
        
        return JsonResponse({
            'mission': mission_data
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@user_passes_test(is_admin)
def mission_category_data_api(request, mission_id, category):
    """API pour les données d'une catégorie spécifique d'une mission"""
    try:
        mission = get_object_or_404(Mission, id=mission_id)
        
        if category == 'files':
            files = mission.fichiers.select_related('utilisateur').order_by('-date_import')
            data = {
                'files': [{
                    'id': file.id,
                    'nom_fichier': file.nom_fichier,
                    'description': file.description,
                    'status': file.status,
                    'date_import': file.date_import,
                    'utilisateur': {
                        'get_full_name': file.utilisateur.get_full_name()
                    }
                } for file in files]
            }
            
        elif category == 'analyses':
            analyses = mission.sessions_audit.select_related('utilisateur').order_by('-date_creation')
            data = {
                'analyses': [{
                    'id': analysis.id,
                    'description': analysis.description,
                    'status': analysis.status,
                    'date_creation': analysis.date_creation,
                    'utilisateur': {
                        'get_full_name': analysis.utilisateur.get_full_name()
                    },
                    'anomalies_detectees': ResultatAudit.objects.filter(session=analysis).count()
                } for analysis in analyses]
            }
            
        elif category == 'reconciliations':
            reconciliations = mission.rapprochements.select_related('utilisateur').order_by('-date_creation')
            data = {
                'reconciliations': [{
                    'id': reconciliation.id,
                    'description': reconciliation.description,
                    'status': reconciliation.status,
                    'date_creation': reconciliation.date_creation,
                    'utilisateur': {
                        'get_full_name': reconciliation.utilisateur.get_full_name()
                    },
                    'taux_correspondance': getattr(reconciliation, 'taux_correspondance', 85)  # Valeur par défaut
                } for reconciliation in reconciliations]
            }
            
        elif category == 'recommendations':
            # À adapter selon votre modèle de recommandations
            data = {
                'recommendations': []
            }
            
        elif category == 'logs':
            # UserLog n'a pas de champ resource_type/description : on relie les logs à la
            # mission via les sessions (audit + rapprochement) qui lui appartiennent.
            session_ids = [str(sid) for sid in mission.sessions_audit.values_list('id', flat=True)]
            session_ids += [str(sid) for sid in mission.rapprochements.values_list('id', flat=True)]

            logs = UserLog.objects.filter(
                target='session',
                resource_id__in=session_ids
            ).select_related('user').order_by('-timestamp')[:50]

            data = {
                'logs': [{
                    'id': log.id,
                    'action': log.action,
                    'description': f"{log.action} - {log.feature}",
                    'timestamp': log.timestamp,
                    'user': {
                        'get_full_name': log.user.get_full_name() if log.user else 'Système'
                    }
                } for log in logs]
            }
            
        else:
            return JsonResponse({'error': 'Catégorie non reconnue'}, status=400)
        
        return JsonResponse(data)
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)