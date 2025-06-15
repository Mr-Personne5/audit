# reconciliation/views.py

import json
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.db import transaction
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Count

from django.utils import timezone

from .models import RapprochementSession, ResultatRapprochement, RegleValidation
from .forms import RapprochementSessionForm, FilterResultsForm
from .engine import RapprochementEngine
from uploads.models import FichierImporte
from accounts.utils import log_user_action

logger = logging.getLogger('auditia')


# ==================== VUES PRINCIPALES ====================

@login_required
def session_list(request):
    """Liste des sessions de rapprochement"""
    if request.user.is_admin():
        sessions = RapprochementSession.objects.all()
    else:
        sessions = RapprochementSession.objects.filter(
            mission=request.user.mission
        )

    # Filtres
    status = request.GET.get('status')
    search = request.GET.get('search')

    if status:
        sessions = sessions.filter(status=status)
    if search:
        sessions = sessions.filter(
            Q(nom_session__icontains=search) |
            Q(description__icontains=search)
        )

    # Pagination
    paginator = Paginator(sessions, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Statistiques
    stats = {
        'total_sessions': sessions.count(),
        'sessions_completed': sessions.filter(status='completed').count(),
        'sessions_pending': sessions.filter(status='pending').count(),
        'sessions_error': sessions.filter(status='error').count(),
    }

    context = {
        'page_obj': page_obj,
        'stats': stats,
        'status_choices': RapprochementSession.STATUS_CHOICES,
        'current_filters': {
            'status': status,
            'search': search,
        }
    }

    return render(request, 'reconciliation/session_list.html', context)


@login_required
def create_session(request):
    """Créer une nouvelle session de rapprochement"""
    if request.method == 'POST':
        form = RapprochementSessionForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                with transaction.atomic():
                    session = form.save(commit=False)
                    session.utilisateur = request.user

                    # Auto-assigner la mission si pas définie
                    if not session.mission and request.user.mission:
                        session.mission = request.user.mission
                    elif not session.mission:
                        messages.error(request, "Vous devez être assigné à une mission.")
                        return render(request, 'reconciliation/create_session.html', {'form': form})

                    session.save()

                    log_user_action(
                        user=request.user,
                        action="create",
                        feature="Rapprochement",
                        target="session",
                        resource_id=str(session.id),
                        new_value=session.nom_session
                    )

                    messages.success(request, f"Session '{session.nom_session}' créée avec succès!")
                    return redirect('reconciliation:session_detail', pk=session.pk)

            except Exception as e:
                logger.error(f"Erreur création session: {str(e)}")
                messages.error(request, f"Erreur lors de la création: {str(e)}")
    else:
        form = RapprochementSessionForm(user=request.user)

    return render(request, 'reconciliation/create_session.html', {'form': form})


@login_required
def session_detail(request, pk):
    """Détail d'une session de rapprochement"""
    session = get_object_or_404(RapprochementSession, pk=pk)

    # Vérification des permissions
    if not request.user.is_admin() and session.mission != request.user.mission:
        messages.error(request, "Vous n'avez pas accès à cette session.")
        return redirect('reconciliation:session_list')

    # Récupérer les résultats avec filtres
    resultats = session.resultats.all()

    # Filtres
    type_filter = request.GET.get('type')
    if type_filter:
        resultats = resultats.filter(type_match=type_filter)

    # Pagination
    paginator = Paginator(resultats, 20)
    page_number = request.GET.get('page')
    resultats_page = paginator.get_page(page_number)

    # Statistiques détaillées
    stats_detail = {
        'parfaits': session.resultats.filter(type_match='parfait').count(),
        'partiels': session.resultats.filter(type_match='partiel').count(),
        'non_payes': session.resultats.filter(type_match='non_paye').count(),
        'non_declares': session.resultats.filter(type_match='non_declare').count(),
        'doublons': session.resultats.filter(type_match='doublon').count(),
    }

    context = {
        'session': session,
        'resultats_page': resultats_page,
        'stats_detail': stats_detail,
        'type_choices': ResultatRapprochement.TYPE_MATCH,
        'current_filter': type_filter,
        'can_process': session.status in ['pending', 'error'],
        'can_edit': request.user.is_admin() or session.utilisateur == request.user,
    }

    return render(request, 'reconciliation/session_detail.html', context)


@login_required
def process_session(request, pk):
    """Lancer le traitement d'une session"""
    session = get_object_or_404(RapprochementSession, pk=pk)

    # Vérifications
    if not request.user.is_admin() and session.utilisateur != request.user:
        return JsonResponse({'success': False, 'error': 'Permission refusée'})

    if session.status not in ['pending', 'error']:
        return JsonResponse({'success': False, 'error': 'Session non traitable'})

    try:
        # Lancer le moteur de rapprochement
        engine = RapprochementEngine(session)
        success = engine.executer_rapprochement()

        log_user_action(
            user=request.user,
            action="process",
            feature="Rapprochement",
            target="session",
            resource_id=str(session.id),
            status='success' if success else 'error'
        )

        if success:
            return JsonResponse({
                'success': True,
                'message': 'Rapprochement terminé avec succès',
                'status': session.status,
                'taux_rapprochement': session.get_taux_rapprochement(),
                'redirect_url': reverse('reconciliation:session_detail', args=[session.pk])
            })
        else:
            return JsonResponse({
                'success': False,
                'error': session.erreurs or 'Erreur inconnue'
            })

    except Exception as e:
        logger.error(f"Erreur traitement session {pk}: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def delete_session(request, pk):
    """Supprimer une session"""
    session = get_object_or_404(RapprochementSession, pk=pk)

    if not request.user.is_admin() and session.utilisateur != request.user:
        messages.error(request, "Vous ne pouvez pas supprimer cette session.")
        return redirect('reconciliation:session_detail', pk=pk)

    if request.method == 'POST':
        nom_session = session.nom_session

        log_user_action(
            user=request.user,
            action="delete",
            feature="Rapprochement",
            target="session",
            resource_id=str(session.id),
            old_value=nom_session
        )

        session.delete()
        messages.success(request, f"Session '{nom_session}' supprimée avec succès.")
        return redirect('reconciliation:session_list')

    return render(request, 'reconciliation/confirm_delete_session.html', {'session': session})


# ==================== VUES API/AJAX ====================

@login_required
@require_http_methods(["GET"])
def session_status(request, pk):
    """API pour récupérer le statut d'une session"""
    session = get_object_or_404(RapprochementSession, pk=pk)

    if not request.user.is_admin() and session.mission != request.user.mission:
        return JsonResponse({'error': 'Permission refusée'}, status=403)

    return JsonResponse({
        'status': session.status,
        'progress': {
            'nb_employes_rh': session.nb_employes_rh,
            'nb_employes_payes': session.nb_employes_payes,
            'nb_matches_parfaits': session.nb_matches_parfaits,
            'nb_matches_partiels': session.nb_matches_partiels,
            'nb_non_payes': session.nb_non_payes,
            'nb_non_declares': session.nb_non_declares,
            'nb_doublons': session.nb_doublons,
            'taux_rapprochement': session.get_taux_rapprochement(),
        },
        'last_logs': session.logs_traitement[-5:] if session.logs_traitement else [],
        'errors': session.erreurs
    })


@login_required
def export_results(request, pk):
    """Exporter les résultats d'une session"""
    session = get_object_or_404(RapprochementSession, pk=pk)

    if not request.user.is_admin() and session.mission != request.user.mission:
        return JsonResponse({'error': 'Permission refusée'}, status=403)

    format_export = request.GET.get('format', 'csv')
    type_filter = request.GET.get('type', '')

    try:
        import pandas as pd

        # Récupérer les résultats
        resultats = session.resultats.all()
        if type_filter:
            resultats = resultats.filter(type_match=type_filter)

        # Préparer les données
        data = []
        for resultat in resultats:
            data.append({
                'Type Match': resultat.get_type_match_display(),
                'Critère': resultat.get_critere_match_display(),
                'Score Confiance': resultat.score_confiance,
                'Matricule RH': resultat.matricule_rh,
                'Nom RH': resultat.nom_rh,
                'Prénom RH': resultat.prenom_rh,
                'Poste RH': resultat.poste_rh,
                'Salaire Prévu': resultat.salaire_prevu_rh,
                'Matricule Paie': resultat.matricule_paie,
                'Nom Paie': resultat.nom_paie,
                'Prénom Paie': resultat.prenom_paie,
                'Salaire Brut': resultat.salaire_brut_paie,
                'Montant Total': resultat.montant_total_paie,
                'Écart Salaire': resultat.ecart_salaire,
                'Commentaires': resultat.commentaires,
            })

        df = pd.DataFrame(data)

        # Export selon le format
        if format_export == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="{session.nom_session}_resultats.csv"'
            df.to_csv(response, index=False)

        elif format_export == 'excel':
            response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = f'attachment; filename="{session.nom_session}_resultats.xlsx"'
            df.to_excel(response, index=False)

        else:
            return JsonResponse({'error': 'Format non supporté'}, status=400)

        log_user_action(
            user=request.user,
            action="export",
            feature="Rapprochement",
            target="resultats",
            resource_id=str(session.id),
            new_value=format_export
        )

        return response

    except Exception as e:
        logger.error(f"Erreur export session {pk}: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


# ==================== VUES D'ANALYSE ====================

@login_required
def analysis_dashboard(request):
    """Dashboard d'analyse des rapprochements"""
    if not request.user.is_admin():
        sessions = RapprochementSession.objects.filter(mission=request.user.mission)
    else:
        sessions = RapprochementSession.objects.all()

    # Filtres
    mission_id = request.GET.get('mission')
    if mission_id and request.user.is_admin():
        sessions = sessions.filter(mission_id=mission_id)

    sessions_completed = sessions.filter(status='completed')

    # Statistiques globales
    stats = {
        'total_sessions': sessions.count(),
        'sessions_completed': sessions_completed.count(),
        'total_employes_rh': sum(s.nb_employes_rh for s in sessions_completed),
        'total_employes_payes': sum(s.nb_employes_payes for s in sessions_completed),
        'total_matches_parfaits': sum(s.nb_matches_parfaits for s in sessions_completed),
        'total_non_payes': sum(s.nb_non_payes for s in sessions_completed),
        'total_non_declares': sum(s.nb_non_declares for s in sessions_completed),
        'total_doublons': sum(s.nb_doublons for s in sessions_completed),
    }

    # Taux de rapprochement moyen
    if stats['total_employes_rh'] > 0:
        stats['taux_rapprochement_moyen'] = round(
            (stats['total_matches_parfaits'] / stats['total_employes_rh']) * 100, 2
        )
    else:
        stats['taux_rapprochement_moyen'] = 0

    # Données pour graphiques
    sessions_recentes = sessions_completed.order_by('-date_completion')[:10]

    # Évolution du taux de rapprochement
    evolution_data = []
    for session in sessions_recentes:
        evolution_data.append({
            'nom': session.nom_session[:20],
            'date': session.date_completion.strftime('%d/%m'),
            'taux': session.get_taux_rapprochement()
        })

    # Top des problèmes
    problemes_data = [
        {'type': 'Non payés', 'count': stats['total_non_payes']},
        {'type': 'Non déclarés', 'count': stats['total_non_declares']},
        {'type': 'Doublons', 'count': stats['total_doublons']},
    ]

    context = {
        'stats': stats,
        'sessions_recentes': sessions_recentes,
        'evolution_data': evolution_data,
        'problemes_data': problemes_data,
    }

    if request.user.is_admin():
        from accounts.models import Mission
        context['missions'] = Mission.objects.all()
        context['current_mission'] = mission_id

    return render(request, 'reconciliation/analysis_dashboard.html', context)


@login_required
def detailed_analysis(request, pk):
    """Analyse détaillée d'une session"""
    session = get_object_or_404(RapprochementSession, pk=pk)

    if not request.user.is_admin() and session.mission != request.user.mission:
        messages.error(request, "Vous n'avez pas accès à cette analyse.")
        return redirect('reconciliation:session_list')

    # Analyse des écarts salariaux
    resultats_avec_ecart = session.resultats.filter(
        ecart_salaire__isnull=False
    ).exclude(ecart_salaire=0)

    # Grouper par tranches d'écart
    ecarts_positifs = resultats_avec_ecart.filter(ecart_salaire__gt=0)
    ecarts_negatifs = resultats_avec_ecart.filter(ecart_salaire__lt=0)

    # Analyse des critères de match
    criteres_stats = {}
    for critere_code, critere_label in ResultatRapprochement.CRITERE_MATCH:
        count = session.resultats.filter(critere_match=critere_code).count()
        criteres_stats[critere_label] = count

    # Analyse des scores de confiance
    scores_ranges = {
        'Très élevé (95-100%)': session.resultats.filter(score_confiance__gte=95).count(),
        'Élevé (85-94%)': session.resultats.filter(score_confiance__gte=85, score_confiance__lt=95).count(),
        'Moyen (70-84%)': session.resultats.filter(score_confiance__gte=70, score_confiance__lt=85).count(),
        'Faible (<70%)': session.resultats.filter(score_confiance__lt=70).count(),
    }

    context = {
        'session': session,
        'ecarts_positifs': ecarts_positifs[:10],  # Top 10
        'ecarts_negatifs': ecarts_negatifs[:10],  # Top 10
        'criteres_stats': criteres_stats,
        'scores_ranges': scores_ranges,
        'nb_ecarts_significatifs': resultats_avec_ecart.count(),
    }

    return render(request, 'reconciliation/detailed_analysis.html', context)


# ==================== UTILS ====================

@login_required
def get_available_files(request):
    """API pour récupérer les fichiers disponibles pour rapprochement"""
    mission = request.user.mission
    if not mission:
        return JsonResponse({'error': 'Aucune mission assignée'}, status=400)

    fichiers_rh = FichierImporte.objects.filter(
        mission=mission,
        type_fichier='liste_personnel',
        status='approved'
    ).values('id', 'nom_fichier', 'date_import')

    fichiers_paie = FichierImporte.objects.filter(
        mission=mission,
        type_fichier='paie',
        status='approved'
    ).values('id', 'nom_fichier', 'date_import')

    return JsonResponse({
        'fichiers_rh': list(fichiers_rh),
        'fichiers_paie': list(fichiers_paie)
    })


@login_required
def session_logs(request, pk):
    """Récupérer les logs d'une session"""
    session = get_object_or_404(RapprochementSession, pk=pk)

    if not request.user.is_admin() and session.mission != request.user.mission:
        return JsonResponse({'error': 'Permission refusée'}, status=403)

    return JsonResponse({
        'logs': session.logs_traitement or [],
        'status': session.status,
        'errors': session.erreurs
    })

@login_required
def rules_admin(request):
    """Administration des règles de validation (lecture seule pour l'instant)"""
    if not request.user.is_admin():
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('reconciliation:session_list')

    # Règles par mission
    if request.user.mission:
        regles = RegleValidation.objects.filter(mission=request.user.mission)
    else:
        regles = RegleValidation.objects.all()

    # Règles par défaut codées en dur (pour information)
    regles_par_defaut = [
        {
            'nom': 'Rapprochement par matricule',
            'description': 'Priorité 1: Correspondance exacte sur le matricule',
            'type': 'Codé en dur',
            'valeur': '99% de confiance'
        },
        {
            'nom': 'Rapprochement par nom/prénom',
            'description': 'Priorité 2: Similarité >= 85% sur nom+prénom',
            'type': 'Codé en dur',
            'valeur': 'Seuil: 85%'
        },
        {
            'nom': 'Détection des doublons',
            'description': 'Plusieurs paies pour un même matricule',
            'type': 'Codé en dur',
            'valeur': 'Automatique'
        },
        {
            'nom': 'Employés non payés',
            'description': 'Présents en RH mais absents de la paie',
            'type': 'Codé en dur',
            'valeur': 'Automatique'
        }
    ]

    context = {
        'regles_configurables': regles,
        'regles_par_defaut': regles_par_defaut,
        'can_edit': False,  # Pour l'instant en lecture seule
    }

    return render(request, 'reconciliation/rules_admin.html', context)
