# recommendations/views.py - CORRIGER l'indentation des fonctions

import json
import logging
from datetime import datetime, timedelta
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.db import transaction
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Count
from django.utils import timezone
from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied

from .models import (
    Recommandation, ActionPlan, SuiviAvancement,
    NotificationRecommandation, KPIRecommandation
)
from .forms import (
    RecommandationForm, FilterRecommandationsForm, AssignationForm,
    ActionPlanForm, SuiviAvancementForm
)
from .engine import RecommendationEngine, KPICalculator, NotificationManager
from accounts.utils import log_user_action
from accounts.models import CustomUser as User

logger = logging.getLogger('auditia.recommendations')


# ==================== DECORATEURS ====================

def admin_or_auditor_required(function):
    """Décorateur pour vérifier les permissions admin ou auditeur"""

    def check_perms(user):
        return user.is_admin() or user.role == 'user'

    actual_decorator = user_passes_test(check_perms)
    if function:
        return actual_decorator(function)
    return actual_decorator


# ==================== VUES PRINCIPALES ====================

@login_required
def dashboard(request):
    """Dashboard principal des recommandations"""

    mission = request.user.mission
    if not mission:
        messages.error(request, "Vous devez être assigné à une mission.")
        return redirect('accounts:dashboard')

    # Filtres temporels
    periode = request.GET.get('periode', '30')
    try:
        jours = int(periode)
    except ValueError:
        jours = 30

    date_limite = timezone.now() - timedelta(days=jours)

    # Requête de base
    recommandations_qs = Recommandation.objects.filter(mission=mission)

    if not request.user.is_admin():
        recommandations_qs = recommandations_qs.filter(
            Q(cree_par=request.user) |
            Q(assigne_a=request.user) |
            Q(statut__in=['approved', 'assigned', 'in_progress', 'completed'])
        )

    # Statistiques globales
    stats_globales = recommandations_qs.aggregate(
        total=Count('id'),
        en_cours=Count('id', filter=Q(statut__in=['assigned', 'in_progress'])),
        terminees=Count('id', filter=Q(statut='completed')),
        en_retard=Count('id', filter=Q(
            date_echeance__lt=timezone.now().date(),
            statut__in=['assigned', 'in_progress']
        )),
        critiques=Count('id', filter=Q(priorite='critique')),
        hautes=Count('id', filter=Q(priorite='haute'))
    )

    # Répartition par statut
    repartition_statut = list(recommandations_qs.filter(
        date_creation__gte=date_limite
    ).values('statut').annotate(
        count=Count('id')
    ).order_by('statut'))

    # Répartition par type
    repartition_type = list(recommandations_qs.filter(
        date_creation__gte=date_limite
    ).values('type_recommandation').annotate(
        count=Count('id')
    ).order_by('type_recommandation'))

    # Recommandations urgentes
    recommandations_urgentes = recommandations_qs.filter(
        date_echeance__lte=timezone.now().date() + timedelta(days=7),
        statut__in=['assigned', 'in_progress']
    ).order_by('date_echeance')[:10]

    # Recommandations récentes
    recommandations_recentes = recommandations_qs.filter(
        date_creation__gte=date_limite
    ).order_by('-date_creation')[:10]

    # Notifications non lues
    notifications_non_lues = NotificationRecommandation.objects.filter(
        destinataire=request.user,
        lue=False
    ).count()

    context = {
        'stats_globales': stats_globales,
        'repartition_statut': json.dumps(repartition_statut),
        'repartition_type': json.dumps(repartition_type),
        'recommandations_urgentes': recommandations_urgentes,
        'recommandations_recentes': recommandations_recentes,
        'notifications_non_lues': notifications_non_lues,
        'periode_selectionnee': periode,
        'can_create': request.user.is_admin() or request.user.role == 'user',
        'can_manage': request.user.is_admin()
    }

    return render(request, 'recommendations/dashboard.html', context)


@login_required
def list_recommandations(request):
    """Liste des recommandations avec filtres"""

    mission = request.user.mission
    if not mission:
        messages.error(request, "Vous devez être assigné à une mission.")
        return redirect('accounts:dashboard')

    # Requête de base
    recommandations = Recommandation.objects.filter(mission=mission)

    if not request.user.is_admin():
        recommandations = recommandations.filter(
            Q(cree_par=request.user) |
            Q(assigne_a=request.user) |
            Q(statut__in=['approved', 'assigned', 'in_progress', 'completed'])
        )

    # Filtres
    form = FilterRecommandationsForm(request.GET, mission=mission)
    if form.is_valid():
        if form.cleaned_data['statut']:
            recommandations = recommandations.filter(statut=form.cleaned_data['statut'])

        if form.cleaned_data['priorite']:
            recommandations = recommandations.filter(priorite=form.cleaned_data['priorite'])

        if form.cleaned_data['type_recommandation']:
            recommandations = recommandations.filter(type_recommandation=form.cleaned_data['type_recommandation'])

        if form.cleaned_data['assigne_a']:
            recommandations = recommandations.filter(assigne_a=form.cleaned_data['assigne_a'])

        if form.cleaned_data['recherche']:
            recherche = form.cleaned_data['recherche']
            recommandations = recommandations.filter(
                Q(titre__icontains=recherche) |
                Q(description__icontains=recherche) |
                Q(code_recommandation__icontains=recherche)
            )

        if form.cleaned_data['date_creation_debut']:
            recommandations = recommandations.filter(
                date_creation__date__gte=form.cleaned_data['date_creation_debut']
            )

        if form.cleaned_data['date_creation_fin']:
            recommandations = recommandations.filter(
                date_creation__date__lte=form.cleaned_data['date_creation_fin']
            )

        if form.cleaned_data['date_echeance_debut']:
            recommandations = recommandations.filter(
                date_echeance__gte=form.cleaned_data['date_echeance_debut']
            )

        if form.cleaned_data['date_echeance_fin']:
            recommandations = recommandations.filter(
                date_echeance__lte=form.cleaned_data['date_echeance_fin']
            )

    # Tri
    sort_by = request.GET.get('sort', '-date_creation')
    valid_sorts = [
        'date_creation', '-date_creation',
        'date_echeance', '-date_echeance',
        'priorite', '-priorite',
        'statut', '-statut',
        'titre', '-titre'
    ]
    if sort_by in valid_sorts:
        recommandations = recommandations.order_by(sort_by)
    else:
        recommandations = recommandations.order_by('-date_creation')

    # Pagination
    page_size = request.GET.get('page_size', '20')
    try:
        page_size = int(page_size)
        if page_size not in [10, 20, 50, 100]:
            page_size = 20
    except ValueError:
        page_size = 20

    paginator = Paginator(recommandations, page_size)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Statistiques pour la vue
    stats = {
        'total': recommandations.count(),
        'en_cours': recommandations.filter(statut__in=['assigned', 'in_progress']).count(),
        'urgentes': recommandations.filter(
            priorite__in=['critique', 'haute'],
            statut__in=['assigned', 'in_progress']
        ).count(),
        'en_retard': recommandations.filter(
            date_echeance__lt=timezone.now().date(),
            statut__in=['assigned', 'in_progress']
        ).count()
    }

    context = {
        'page_obj': page_obj,
        'form': form,
        'stats': stats,
        'current_sort': sort_by,
        'current_page_size': page_size,
        'can_create': request.user.is_admin() or request.user.role == 'user',
        'can_manage': request.user.is_admin()
    }

    return render(request, 'recommendations/recommandation_list.html', context)


@login_required
def detail_recommandation(request, pk):
    """Détail d'une recommandation"""

    recommandation = get_object_or_404(Recommandation, pk=pk)

    # Vérification des permissions
    if not request.user.is_admin() and recommandation.mission != request.user.mission:
        raise PermissionDenied("Vous n'avez pas accès à cette recommandation.")

    if not request.user.is_admin():
        if (recommandation.statut == 'draft' and
                recommandation.cree_par != request.user):
            raise PermissionDenied("Vous n'avez pas accès à cette recommandation.")

    # Actions du plan
    actions = recommandation.actions.all().order_by('ordre')

    # Historique des suivis
    suivis = recommandation.suivis.all().order_by('-date_evenement')

    # Notifications liées
    notifications = recommandation.notifications.filter(
        destinataire=request.user
    ).order_by('-date_creation')

    # Marquer les notifications comme lues
    notifications.filter(lue=False).update(
        lue=True,
        date_lecture=timezone.now()
    )

    # Vérifier les permissions d'action
    can_edit = recommandation.can_edit(request.user)
    can_validate = recommandation.can_validate(request.user)
    can_assign = request.user.is_admin() or request.user.role == 'user'
    can_close = (
            request.user.is_admin() or
            recommandation.assigne_a == request.user
    )

    # Données pour les graphiques
    progression_data = []
    if actions.exists():
        for action in actions:
            progression_data.append({
                'nom': action.nom_action,
                'completion': action.pourcentage_completion
            })

    context = {
        'recommandation': recommandation,
        'actions': actions,
        'suivis': suivis,
        'notifications': notifications,
        'can_edit': can_edit,
        'can_validate': can_validate,
        'can_assign': can_assign,
        'can_close': can_close,
        'progression_data': json.dumps(progression_data)
    }

    return render(request, 'recommendations/recommandation_detail.html', context)


@login_required
@admin_or_auditor_required
def create_recommandation(request):
    """Créer une nouvelle recommandation"""

    if request.method == 'POST':
        form = RecommandationForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                with transaction.atomic():
                    reco = form.save(commit=False)
                    reco.cree_par = request.user

                    if not reco.mission and request.user.mission:
                        reco.mission = request.user.mission
                    elif not reco.mission:
                        messages.error(request, "Vous devez être assigné à une mission.")
                        return render(request, 'recommendations/recommandation_create.html', {'form': form})

                    reco.save()

                    # Créer le premier suivi
                    SuiviAvancement.objects.create(
                        recommandation=reco,
                        type_evenement='creation',
                        description=f"Recommandation créée par {request.user.get_full_name()}",
                        utilisateur=request.user
                    )

                    # Notification
                    NotificationManager.notifier_nouvelle_recommandation(reco)

                    # Log
                    log_user_action(
                        user=request.user,
                        action="create",
                        feature="Recommandation",
                        target="recommandation",
                        resource_id=str(reco.id),
                        new_value=reco.titre,
                        request=request
                    )

                    messages.success(request, f"Recommandation '{reco.code_recommandation}' créée avec succès!")
                    return redirect('recommendations:detail', pk=reco.pk)

            except Exception as e:
                logger.error(f"Erreur création recommandation: {str(e)}")
                messages.error(request, f"Erreur lors de la création: {str(e)}")
    else:
        form = RecommandationForm(user=request.user)

    return render(request, 'recommendations/recommandation_create.html', {'form': form})


@login_required
def edit_recommandation(request, pk):
    """Modifier une recommandation"""

    reco = get_object_or_404(Recommandation, pk=pk)

    if not reco.can_edit(request.user):
        messages.error(request, "Vous n'avez pas les permissions pour modifier cette recommandation.")
        return redirect('recommendations:detail', pk=pk)

    if request.method == 'POST':
        # Sauvegarder l'état avant modification
        donnees_avant = {
            'titre': reco.titre,
            'description': reco.description,
            'priorite': reco.priorite,
            'statut': reco.statut,
            'date_echeance': reco.date_echeance.isoformat() if reco.date_echeance else None
        }

        form = RecommandationForm(request.POST, instance=reco, user=request.user)
        if form.is_valid():
            try:
                with transaction.atomic():
                    reco_modifiee = form.save()

                    # Données après modification
                    donnees_apres = {
                        'titre': reco_modifiee.titre,
                        'description': reco_modifiee.description,
                        'priorite': reco_modifiee.priorite,
                        'statut': reco_modifiee.statut,
                        'date_echeance': reco_modifiee.date_echeance.isoformat() if reco_modifiee.date_echeance else None
                    }

                    # Créer le suivi
                    SuiviAvancement.objects.create(
                        recommandation=reco_modifiee,
                        type_evenement='modification',
                        description=f"Recommandation modifiée par {request.user.get_full_name()}",
                        utilisateur=request.user,
                        donnees_avant=donnees_avant,
                        donnees_apres=donnees_apres
                    )

                    # Log
                    log_user_action(
                        user=request.user,
                        action="update",
                        feature="Recommandation",
                        target="recommandation",
                        resource_id=str(reco.id),
                        old_value=donnees_avant.get('titre'),
                        new_value=donnees_apres.get('titre'),
                        request=request
                    )

                    messages.success(request, "Recommandation modifiée avec succès!")
                    return redirect('recommendations:detail', pk=reco.pk)

            except Exception as e:
                logger.error(f"Erreur modification recommandation {pk}: {str(e)}")
                messages.error(request, f"Erreur lors de la modification: {str(e)}")
    else:
        form = RecommandationForm(instance=reco, user=request.user)

    ctx = {
        'form': form,
        'recommandation': reco,
        'is_edit': True
    }

    return render(request, 'recommendations/recommandation_create.html', ctx)


@login_required
def delete_recommandation(request, pk):
    """Supprimer une recommandation"""

    reco = get_object_or_404(Recommandation, pk=pk)

    if not (request.user.is_admin() or reco.cree_par == request.user):
        messages.error(request, "Vous n'avez pas les permissions pour supprimer cette recommandation.")
        return redirect('recommendations:detail', pk=pk)

    if reco.statut not in ['draft', 'rejected', 'cancelled']:
        messages.error(request,
                       "Seules les recommandations en brouillon, rejetées ou annulées peuvent être supprimées.")
        return redirect('recommendations:detail', pk=pk)

    if request.method == 'POST':
        code_recommandation = reco.code_recommandation
        titre = reco.titre

        log_user_action(
            user=request.user,
            action="delete",
            feature="Recommandation",
            target="recommandation",
            resource_id=str(reco.id),
            old_value=f"{code_recommandation} - {titre}",
            request=request
        )

        reco.delete()
        messages.success(request, f"Recommandation '{code_recommandation}' supprimée avec succès.")
        return redirect('recommendations:list')

    return render(request, 'recommendations/recommandation_confirm_delete.html', {
        'recommandation': reco
    })


@login_required
@admin_or_auditor_required
def assign_recommandation(request, pk):
    """Assigner une recommandation"""

    reco = get_object_or_404(Recommandation, pk=pk)

    if reco.mission != request.user.mission and not request.user.is_admin():
        raise PermissionDenied("Vous n'avez pas accès à cette recommandation.")

    if request.method == 'POST':
        form = AssignationForm(request.POST, mission=reco.mission)
        if form.is_valid():
            try:
                with transaction.atomic():
                    ancien_assigne = reco.assigne_a
                    nouveau_assigne = form.cleaned_data['assigne_a']
                    commentaire = form.cleaned_data['commentaire']

                    reco.assigne_a = nouveau_assigne
                    if reco.statut == 'approved':
                        reco.statut = 'assigned'
                    reco.save()

                    # Créer le suivi
                    description = f"Recommandation assignée à {nouveau_assigne.get_full_name()}"
                    if ancien_assigne:
                        description += f" (précédemment assignée à {ancien_assigne.get_full_name()})"

                    SuiviAvancement.objects.create(
                        recommandation=reco,
                        type_evenement='assignation',
                        description=description,
                        commentaire_utilisateur=commentaire,
                        utilisateur=request.user,
                        donnees_avant={'assigne_a': ancien_assigne.id if ancien_assigne else None},
                        donnees_apres={'assigne_a': nouveau_assigne.id}
                    )

                    # Notification
                    NotificationManager.notifier_assignation(reco)

                    # Log
                    log_user_action(
                        user=request.user,
                        action="assign",
                        feature="Recommandation",
                        target="recommandation",
                        resource_id=str(reco.id),
                        old_value=ancien_assigne.username if ancien_assigne else None,
                        new_value=nouveau_assigne.username,
                        request=request
                    )

                    messages.success(request, f"Recommandation assignée à {nouveau_assigne.get_full_name()}!")
                    return redirect('recommendations:detail', pk=reco.pk)

            except Exception as e:
                logger.error(f"Erreur assignation recommandation {pk}: {str(e)}")
                messages.error(request, f"Erreur lors de l'assignation: {str(e)}")
    else:
        form = AssignationForm(mission=reco.mission)

    ctx = {
        'form': form,
        'recommandation': reco
    }

    return render(request, 'recommendations/recommandation_assign.html', ctx)


@login_required
@require_http_methods(["POST"])
def change_status_recommandation(request, pk):
    """Changer le statut d'une recommandation (AJAX)"""

    reco = get_object_or_404(Recommandation, pk=pk)

    if reco.mission != request.user.mission and not request.user.is_admin():
        return JsonResponse({'success': False, 'error': 'Permission refusée'})

    nouveau_statut = request.POST.get('statut')
    commentaire = request.POST.get('commentaire', '')

    # Dictionnaire des choix valides
    statuts_valides = dict(Recommandation.STATUT_CHOICES)
    if nouveau_statut not in statuts_valides:
        return JsonResponse({'success': False, 'error': 'Statut invalide'})

    # Vérifier les transitions autorisées
    transitions_autorisees = {
        'draft': ['pending'],
        'pending': ['approved', 'rejected'],
        'approved': ['assigned'],
        'assigned': ['in_progress', 'rejected'],
        'in_progress': ['completed', 'rejected'],
        'completed': ['in_progress'],
        'rejected': ['pending'],
        'overdue': ['in_progress', 'completed'],
        'cancelled': []
    }

    if nouveau_statut not in transitions_autorisees.get(reco.statut, []):
        return JsonResponse({
            'success': False,
            'error': f'Transition non autorisée de {reco.get_statut_display()} vers {statuts_valides[nouveau_statut]}'
        })

    # Vérifier les permissions pour certains statuts
    if nouveau_statut == 'approved' and not reco.can_validate(request.user):
        return JsonResponse({'success': False, 'error': 'Permission insuffisante pour valider'})

    try:
        with transaction.atomic():
            ancien_statut = reco.statut
            reco.statut = nouveau_statut
            reco.save()

            # Créer le suivi
            type_evenement_map = {
                'approved': 'validation',
                'rejected': 'rejet',
                'completed': 'cloture',
                'in_progress': 'debut_travaux' if ancien_statut == 'assigned' else 'rouverture'
            }
            type_evenement = type_evenement_map.get(nouveau_statut, 'modification')

            SuiviAvancement.objects.create(
                recommandation=reco,
                type_evenement=type_evenement,
                description=f"Statut changé de {statuts_valides[ancien_statut]} vers {statuts_valides[nouveau_statut]}",
                commentaire_utilisateur=commentaire,
                utilisateur=request.user,
                donnees_avant={'statut': ancien_statut},
                donnees_apres={'statut': nouveau_statut}
            )

            # Log
            log_user_action(
                user=request.user,
                action="change_status",
                feature="Recommandation",
                target="recommandation",
                resource_id=str(reco.id),
                old_value=ancien_statut,
                new_value=nouveau_statut,
                request=request
            )

            return JsonResponse({
                'success': True,
                'message': f'Statut changé vers {statuts_valides[nouveau_statut]}',
                'nouveau_statut': nouveau_statut,
                'nouveau_statut_display': statuts_valides[nouveau_statut],
                'color_class': reco.get_statut_color()
            })

    except Exception as e:
        logger.error(f"Erreur changement statut recommandation {pk}: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})


# ==================== GESTION PLAN D'ACTION ====================

@login_required
def create_action_plan(request, recommandation_pk):
    """Créer une action dans le plan"""

    reco = get_object_or_404(Recommandation, pk=recommandation_pk)

    if not reco.can_edit(request.user):
        messages.error(request, "Vous n'avez pas les permissions pour modifier cette recommandation.")
        return redirect('recommendations:detail', pk=recommandation_pk)

    if request.method == 'POST':
        form = ActionPlanForm(request.POST, recommandation=reco)
        if form.is_valid():
            try:
                action_plan = form.save(commit=False)
                action_plan.recommandation = reco

                # Définir l'ordre automatiquement
                dernier_ordre = reco.actions.count()
                action_plan.ordre = dernier_ordre + 1

                action_plan.save()

                # Créer suivi
                SuiviAvancement.objects.create(
                    recommandation=reco,
                    type_evenement='modification',
                    description=f"Action ajoutée au plan: {action_plan.nom_action}",
                    utilisateur=request.user
                )

                messages.success(request, "Action ajoutée au plan avec succès!")
                return redirect('recommendations:detail', pk=recommandation_pk)

            except Exception as e:
                logger.error(f"Erreur création action plan: {str(e)}")
                messages.error(request, f"Erreur lors de la création: {str(e)}")
    else:
        form = ActionPlanForm(recommandation=reco)

    ctx = {
        'form': form,
        'recommandation': reco,
        'is_create': True
    }

    return render(request, 'recommendations/action_plan_form.html', ctx)


@login_required
@require_http_methods(["POST"])
def update_progress_action_plan(request, pk):
    """Mettre à jour le pourcentage de completion d'une action (AJAX)"""

    action_plan = get_object_or_404(ActionPlan, pk=pk)

    if not action_plan.recommandation.can_edit(request.user):
        return JsonResponse({'success': False, 'error': 'Permission refusée'})

    try:
        pourcentage = int(request.POST.get('pourcentage', 0))
        if not 0 <= pourcentage <= 100:
            return JsonResponse({'success': False, 'error': 'Pourcentage invalide'})

        ancien_pourcentage = action_plan.pourcentage_completion
        action_plan.pourcentage_completion = pourcentage

        # Mettre à jour le statut selon le pourcentage
        if pourcentage == 0:
            action_plan.statut = 'non_commencee'
        elif pourcentage == 100:
            action_plan.statut = 'terminee'
            if not action_plan.date_fin_reelle:
                action_plan.date_fin_reelle = timezone.now().date()
        else:
            action_plan.statut = 'en_cours'
            if not action_plan.date_debut_reelle:
                action_plan.date_debut_reelle = timezone.now().date()

        action_plan.save()

        # Recalculer l'avancement global de la recommandation
        actions_recommandation = action_plan.recommandation.actions.all()
        if actions_recommandation.exists():
            avancement_global = sum(
                a.pourcentage_completion for a in actions_recommandation) / actions_recommandation.count()
            action_plan.recommandation.pourcentage_avancement = int(avancement_global)
            action_plan.recommandation.save()

        # Créer suivi si changement significatif
        if abs(pourcentage - ancien_pourcentage) >= 10:
            SuiviAvancement.objects.create(
                recommandation=action_plan.recommandation,
                type_evenement='mise_a_jour',
                description=f"Avancement action '{action_plan.nom_action}': {ancien_pourcentage}% → {pourcentage}%",
                utilisateur=request.user
            )

        return JsonResponse({
            'success': True,
            'message': f'Avancement mis à jour: {pourcentage}%',
            'avancement_global': action_plan.recommandation.pourcentage_avancement,
            'nouveau_statut': action_plan.get_statut_display()
        })

    except Exception as e:
        logger.error(f"Erreur mise à jour avancement action {pk}: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})


# ==================== GENERATION AUTOMATIQUE ====================
# ✅ CORRIGER l'indentation - ces fonctions étaient mal placées !

@login_required
@admin_or_auditor_required
@require_http_methods(["POST"])
def generate_recommendations_audit(request, session_audit_id):
    """Générer des recommandations depuis une session d'audit"""

    from django.apps import apps
    SessionAudit = apps.get_model('auditengine', 'SessionAudit')

    session_audit = get_object_or_404(SessionAudit, pk=session_audit_id)

    if session_audit.mission != request.user.mission and not request.user.is_admin():
        return JsonResponse({'success': False, 'error': 'Permission refusée'})

    try:
        engine = RecommendationEngine(session_audit.mission, request.user)
        recommandations = engine.generer_recommandations_audit(session_audit)

        log_user_action(
            user=request.user,
            action="generate",
            feature="Recommandation",
            target="batch",
            resource_id=str(session_audit.id),
            new_value=f"{len(recommandations)} recommandations générées",
            request=request
        )

        return JsonResponse({
            'success': True,
            'message': f'{len(recommandations)} recommandation(s) générée(s) avec succès',
            'count': len(recommandations),
            'recommandations': [
                {
                    'id': r.id,
                    'code': r.code_recommandation,
                    'titre': r.titre,
                    'priorite': r.get_priorite_display()
                } for r in recommandations
            ]
        })

    except Exception as e:
        logger.error(f"Erreur génération recommandations audit {session_audit_id}: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})


# ==================== EXPORTS ET RAPPORTS ====================

@login_required
def export_recommendations(request):
    """Exporter les recommandations en CSV/Excel"""

    mission = request.user.mission
    if not mission:
        return redirect('accounts:dashboard')

    # Paramètres d'export
    format_export = request.GET.get('format', 'csv')
    statut_filter = request.GET.get('statut', '')
    priorite_filter = request.GET.get('priorite', '')

    try:
        import pandas as pd
        from io import BytesIO

        # Requête de base
        recommandations = Recommandation.objects.filter(mission=mission)

        if not request.user.is_admin():
            recommandations = recommandations.filter(
                Q(cree_par=request.user) |
                Q(assigne_a=request.user) |
                Q(statut__in=['approved', 'assigned', 'in_progress', 'completed'])
            )

        # Filtres
        if statut_filter:
            recommandations = recommandations.filter(statut=statut_filter)
        if priorite_filter:
            recommandations = recommandations.filter(priorite=priorite_filter)

        # Préparer les données
        data = []
        for reco in recommandations.select_related('cree_par', 'assigne_a'):
            data.append({
                'Code': reco.code_recommandation,
                'Titre': reco.titre,
                'Type': reco.get_type_recommandation_display(),
                'Priorité': reco.get_priorite_display(),
                'Statut': reco.get_statut_display(),
                'Source': reco.get_source_display(),
                'Créé par': reco.cree_par.get_full_name() if reco.cree_par else '',
                'Assigné à': reco.assigne_a.get_full_name() if reco.assigne_a else '',
                'Date création': reco.date_creation.strftime('%d/%m/%Y %H:%M'),
                'Date échéance': reco.date_echeance.strftime('%d/%m/%Y') if reco.date_echeance else '',
                'Avancement (%)': reco.pourcentage_avancement,
                'Impact estimé': reco.get_impact_estime_display(),
                'Description': reco.description,
            })

        df = pd.DataFrame(data)

        if format_export == 'excel':
            # Export Excel
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Recommandations', index=False)

            output.seek(0)

            response = HttpResponse(
                output.read(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            filename = f"recommandations_{mission.name}_{timezone.now().strftime('%Y%m%d_%H%M')}.xlsx"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'

        else:
            # Export CSV
            response = HttpResponse(content_type='text/csv; charset=utf-8')
            filename = f"recommandations_{mission.name}_{timezone.now().strftime('%Y%m%d_%H%M')}.csv"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'

            df.to_csv(response, index=False, encoding='utf-8', sep=';')

        # Log
        log_user_action(
            user=request.user,
            action="export",
            feature="Recommandation",
            target="list",
            resource_id=str(mission.id),
            new_value=f"Export {format_export} - {len(data)} recommandations",
            request=request
        )

        return response

    except Exception as e:
        logger.error(f"Erreur export recommandations: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})


# ==================== API/AJAX ====================

@login_required
@require_http_methods(["GET"])
def api_stats_recommendations(request):
    """API pour récupérer les statistiques en temps réel"""

    mission = request.user.mission
    if not mission:
        return JsonResponse({'error': 'Mission non définie'}, status=400)

    recommandations = Recommandation.objects.filter(mission=mission)

    if not request.user.is_admin():
        recommandations = recommandations.filter(
            Q(cree_par=request.user) |
            Q(assigne_a=request.user) |
            Q(statut__in=['approved', 'assigned', 'in_progress', 'completed'])
        )

    stats = {
        'total': recommandations.count(),
        'en_cours': recommandations.filter(statut__in=['assigned', 'in_progress']).count(),
        'terminees': recommandations.filter(statut='completed').count(),
        'en_retard': recommandations.filter(
            date_echeance__lt=timezone.now().date(),
            statut__in=['assigned', 'in_progress']
        ).count(),
        'critiques': recommandations.filter(priorite='critique').count(),
        'assignees_a_moi': recommandations.filter(assigne_a=request.user).count(),
        'creees_par_moi': recommandations.filter(cree_par=request.user).count(),
    }

    # Échéances proches (7 jours)
    echeances_proches = list(recommandations.filter(
        date_echeance__lte=timezone.now().date() + timedelta(days=7),
        date_echeance__gte=timezone.now().date(),
        statut__in=['assigned', 'in_progress']
    ).values(
        'id', 'code_recommandation', 'titre', 'date_echeance', 'priorite'
    )[:5])

    return JsonResponse({
        'stats': stats,
        'echeances_proches': echeances_proches,
        'timestamp': timezone.now().isoformat()
    })

@login_required
def dashboard_recommendations_stats_api(request):
    mission = request.user.mission
    if not mission:
        return JsonResponse({'error': 'Mission non définie'}, status=400)

    recommandations = Recommandation.objects.filter(mission=mission)
    if not request.user.is_admin():
        recommandations = recommandations.filter(
            Q(cree_par=request.user) |
            Q(assigne_a=request.user) |
            Q(statut__in=['approved', 'assigned', 'in_progress', 'completed'])
        )

    stats = {
        'total': recommandations.count(),
        'en_cours': recommandations.filter(statut__in=['assigned', 'in_progress']).count(),
        'terminees': recommandations.filter(statut='completed').count(),
        'en_retard': recommandations.filter(
            date_echeance__lt=timezone.now().date(),
            statut__in=['assigned', 'in_progress']
        ).count(),
    }
    return JsonResponse(stats)
