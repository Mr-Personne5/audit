# auditengine/views.py
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
from django.db.models import Q, Count, Avg, Sum
from django.utils import timezone
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.core.cache import cache
from decimal import Decimal
import tempfile

from .models import (
    SessionAudit, ResultatAudit, ParametrageIA, ModeleIA,
    CorrectionUtilisateur, TacheAction, AuditLog
)
from .forms import (
    SessionAuditForm, CorrectionForm, ParametrageIAForm,
    FilterResultsForm
)
from .engine import AuditEngine
RetrainingEngine = AuditEngine.RetrainingEngine
ModelEvaluator = AuditEngine.ModelEvaluator
RecommendationGenerator = AuditEngine.RecommendationGenerator
from uploads.models import FichierImporte
from accounts.utils import log_user_action

logger = logging.getLogger('auditia')


# ==================== VUES PRINCIPALES ====================

@login_required
def session_list(request):
    """Liste des sessions d'audit IA"""
    if request.user.is_admin():
        sessions = SessionAudit.objects.all()
    else:
        sessions = SessionAudit.objects.filter(
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
        'total_anomalies': sum(s.nb_anomalies_detectees for s in sessions.filter(status='completed')),
    }

    context = {
        'page_obj': page_obj,
        'stats': stats,
        'status_choices': SessionAudit.STATUS_CHOICES,
        'current_filters': {
            'status': status,
            'search': search,
        }
    }

    return render(request, 'auditengine/session_list.html', context)


@login_required
def create_session(request):
    """Créer une nouvelle session d'audit IA"""
    if request.method == 'POST':
        form = SessionAuditForm(request.POST, user=request.user)
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
                        return render(request, 'auditengine/create_session.html', {'form': form})

                    session.save()

                    log_user_action(
                        user=request.user,
                        action="create",
                        feature="Audit IA",
                        target="session",
                        resource_id=str(session.id),
                        new_value=session.nom_session
                    )

                    messages.success(request, f"Session d'audit '{session.nom_session}' créée avec succès!")
                    return redirect('auditengine:session_detail', pk=session.pk)

            except Exception as e:
                logger.error(f"Erreur création session audit: {str(e)}")
                messages.error(request, f"Erreur lors de la création: {str(e)}")
    else:
        form = SessionAuditForm(user=request.user)

    return render(request, 'auditengine/create_session.html', {'form': form})


@login_required
def session_detail(request, pk):
    """Détail d'une session d'audit"""
    session = get_object_or_404(SessionAudit, pk=pk)
    
    # Vérifier les permissions
    if not request.user.is_admin() and session.mission != request.user.mission:
        messages.error(request, "Vous n'avez pas accès à cette session.")
        return redirect('auditengine:session_list')
    
    # Récupération des filtres
    type_filter = request.GET.get('type')
    niveau_risque_filter = request.GET.get('niveau_risque')
    anomalie_filter = request.GET.get('anomalie')
    fausse_alerte_filter = request.GET.get('fausse_alerte')
    search_filter = request.GET.get('search')
    ordering = request.GET.get('ordering')  # ex: -score_if, score_mlp, nom
    show = request.GET.get('show')
    
    # Construction de la requête de base
    base_qs = session.resultats.all()
    
    # Application du filtre anomalie
    if anomalie_filter == 'oui':
        base_qs = base_qs.filter(est_anomalie=True)
    elif anomalie_filter == 'non':
        base_qs = base_qs.filter(est_anomalie=False)
    elif not show:  # Par défaut, montrer seulement les anomalies si aucun filtre spécifique
        base_qs = base_qs.filter(est_anomalie=True)
    
    # Application des autres filtres
    if type_filter:
        base_qs = base_qs.filter(type_anomalie=type_filter)
    if niveau_risque_filter:
        base_qs = base_qs.filter(niveau_risque=niveau_risque_filter)
    if fausse_alerte_filter == 'oui':
        base_qs = base_qs.filter(est_fausse_alerte=True)
    elif fausse_alerte_filter == 'non':
        base_qs = base_qs.filter(est_fausse_alerte=False)
    if search_filter:
        base_qs = base_qs.filter(
            Q(nom__icontains=search_filter) |
            Q(prenom__icontains=search_filter) |
            Q(matricule__icontains=search_filter)
        )
    
    # Tri
    if ordering in ['score_if', '-score_if', 'score_mlp', '-score_mlp', 'nom', '-nom']:
        ordering_map = {
            'score_if': 'score_anomalie_if',
            '-score_if': '-score_anomalie_if',
            'score_mlp': 'score_classification_mlp',
            '-score_mlp': '-score_classification_mlp',
            'nom': 'nom',
            '-nom': '-nom',
        }
        resultats = base_qs.order_by(ordering_map[ordering])
    else:
        resultats = base_qs.order_by('-score_anomalie_if')
    paginator = Paginator(resultats, 20)
    page_number = request.GET.get('page')
    resultats_page = paginator.get_page(page_number)
    
    # Statistiques détaillées (calculées sur les données filtrées)
    # Agrégées pour éviter N requêtes
    type_counts = {row['type_anomalie']: row['c'] for row in base_qs.values('type_anomalie').annotate(c=Count('id'))}
    stats_detail = {
        'salaires_anormaux': type_counts.get('salaire_anormal', 0),
        'employes_fantomes': type_counts.get('ghost_employee', 0),
        'primes_anormales': type_counts.get('prime_anormale', 0),
        'heures_excessives': type_counts.get('heures_excessives', 0),
        'rib_dupliques': type_counts.get('duplicate_rib', 0),
        # Toujours compter les cas normaux sur l'ensemble de la session
        # (sinon, avec l'affichage par défaut limité aux anomalies, on obtiendrait 0)
        'aucune_anomalie': session.resultats.filter(est_anomalie=False).count(),
    }
    
    # Statistiques par niveau de risque (calculées sur les données filtrées)
    risk_counts = {row['niveau_risque']: row['c'] for row in base_qs.values('niveau_risque').annotate(c=Count('id'))}
    stats_risque = {
        'critique': risk_counts.get('critique', 0),
        'eleve': risk_counts.get('eleve', 0),
        'moyen': risk_counts.get('moyen', 0),
        'faible': risk_counts.get('faible', 0),
    }

    # Statistiques globales (sur toute la session) pour comparer
    anomalies_qs = session.resultats.filter(est_anomalie=True)
    risk_counts_global = {row['niveau_risque']: row['c'] for row in anomalies_qs.values('niveau_risque').annotate(c=Count('id'))}
    stats_risque_global = {
        'critique': risk_counts_global.get('critique', 0),
        'eleve': risk_counts_global.get('eleve', 0),
        'moyen': risk_counts_global.get('moyen', 0),
        'faible': risk_counts_global.get('faible', 0),
    }

    # Taux global et filtré
    total_global = session.nb_lignes_analysees or session.resultats.count()
    taux_global = round((session.nb_anomalies_detectees / total_global) * 100, 2) if total_global else 0
    total_filtre = base_qs.count()
    anomalies_filtre = base_qs.filter(est_anomalie=True).count()
    taux_filtre = round((anomalies_filtre / total_filtre) * 100, 2) if total_filtre else 0
    
    context = {
        'session': session,
        'resultats_page': resultats_page,
        'stats_detail': stats_detail,
        'stats_risque': stats_risque,
        'stats_risque_global': stats_risque_global,
        'type_choices': ResultatAudit.TYPE_ANOMALIE_CHOICES,
        'niveau_risque_choices': ResultatAudit.NIVEAU_RISQUE_CHOICES,
        'current_filters': {
            'type': type_filter,
            'niveau_risque': niveau_risque_filter,
            'anomalie': anomalie_filter,
            'fausse_alerte': fausse_alerte_filter,
            'search': search_filter,
            'ordering': ordering,
        },
        'taux_global': taux_global,
        'taux_filtre': taux_filtre,
        'show': show or 'anomalies',
        'can_process': session.status in ['pending', 'error'],
        'can_edit': request.user.is_admin() or session.mission == request.user.mission,
    }
    
    return render(request, 'auditengine/session_detail.html', context)


@login_required
@require_http_methods(["POST"])
def process_session(request, pk):
    """Lancer le traitement IA d'une session"""
    session = get_object_or_404(SessionAudit, pk=pk)

    # Vérifications
    if not request.user.is_admin() and session.utilisateur != request.user:
        return JsonResponse({'success': False, 'error': 'Permission refusée'})

    if session.status not in ['pending', 'error']:
        return JsonResponse({'success': False, 'error': 'Session non traitable'})

    try:
        # Lancer le moteur d'audit IA
        engine = AuditEngine(session)
        success = engine.executer_audit()

        log_user_action(
            user=request.user,
            action="process",
            feature="Audit IA",
            target="session",
            resource_id=str(session.id),
            status='success' if success else 'error'
        )

        if success:
            return JsonResponse({
                'success': True,
                'message': 'Audit IA terminé avec succès',
                'status': session.status,
                'taux_anomalies': session.get_taux_anomalies(),
                'nb_anomalies': session.nb_anomalies_detectees,
                'redirect_url': reverse('auditengine:session_detail', args=[session.pk])
            })
        else:
            return JsonResponse({
                'success': False,
                'error': session.erreurs or 'Erreur inconnue'
            })

    except Exception as e:
        logger.error(f"Erreur traitement session audit {pk}: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def delete_session(request, pk):
    """Supprimer une session d'audit"""
    session = get_object_or_404(SessionAudit, pk=pk)

    if not request.user.is_admin() and session.utilisateur != request.user:
        messages.error(request, "Vous ne pouvez pas supprimer cette session.")
        return redirect('auditengine:session_detail', pk=pk)

    if request.method == 'POST':
        nom_session = session.nom_session

        log_user_action(
            user=request.user,
            action="delete",
            feature="Audit IA",
            target="session",
            resource_id=str(session.id),
            old_value=nom_session
        )

        session.delete()
        messages.success(request, f"Session d'audit '{nom_session}' supprimée avec succès.")
        return redirect('auditengine:session_list')

    return render(request, 'auditengine/confirm_delete_session.html', {'session': session})


# ==================== GESTION DES ANOMALIES ====================

@login_required
def anomalie_detail(request, pk):
    """Détail d'une anomalie spécifique"""
    resultat = get_object_or_404(ResultatAudit, pk=pk)

    # Vérification des permissions
    if not request.user.is_admin() and resultat.session.mission != request.user.mission:
        messages.error(request, "Vous n'avez pas accès à cette anomalie.")
        return redirect('auditengine:session_list')

    # Récupérer les corrections existantes
    corrections = resultat.corrections.all().order_by('-date_correction')

    context = {
        'resultat': resultat,
        'corrections': corrections,
        'can_correct': request.user.is_admin() or resultat.session.mission == request.user.mission,
    }

    return render(request, 'auditengine/anomalie_detail.html', context)


@login_required
def corriger_anomalie(request, pk):
    """Corriger/valider une anomalie"""
    resultat = get_object_or_404(ResultatAudit, pk=pk)

    # Vérification des permissions
    if not request.user.is_admin() and resultat.session.mission != request.user.mission:
        messages.error(request, "Vous n'avez pas accès à cette anomalie.")
        return redirect('auditengine:session_list')

    if request.method == 'POST':
        form = CorrectionForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Vérifier s'il y a déjà une correction de cet utilisateur
                    correction_existante = CorrectionUtilisateur.objects.filter(
                        resultat_audit=resultat,
                        utilisateur=request.user
                    ).first()

                    if correction_existante:
                        # Mettre à jour la correction existante
                        for field, value in form.cleaned_data.items():
                            setattr(correction_existante, field, value)
                        correction_existante.date_correction = timezone.now()
                        correction_existante.save()
                        correction = correction_existante
                    else:
                        # Créer une nouvelle correction
                        correction = form.save(commit=False)
                        correction.resultat_audit = resultat
                        correction.utilisateur = request.user
                        correction.save()

                    # Appliquer les corrections au résultat si confiance élevée
                    if correction.confiance_utilisateur >= 8:
                        resultat.valide_par_humain = True
                        resultat.valide_par = request.user
                        resultat.date_validation = timezone.now()

                        # Appliquer les nouvelles valeurs
                        if correction.nouveau_est_anomalie is not None:
                            resultat.est_anomalie = correction.nouveau_est_anomalie
                        if correction.nouveau_type_anomalie:
                            resultat.type_anomalie = correction.nouveau_type_anomalie
                        if correction.nouveau_niveau_risque:
                            resultat.niveau_risque = correction.nouveau_niveau_risque
                        if correction.type_correction == 'fausse_alerte':
                            resultat.est_fausse_alerte = True

                        resultat.commentaire_utilisateur = correction.justification
                        resultat.save()

                    log_user_action(
                        user=request.user,
                        action="correct",
                        feature="Audit IA",
                        target="anomalie",
                        resource_id=str(resultat.id),
                        new_value=correction.type_correction
                    )

                    messages.success(request, "Correction enregistrée avec succès.")
                    return redirect('auditengine:anomalie_detail', pk=resultat.pk)

            except Exception as e:
                logger.error(f"Erreur correction anomalie: {str(e)}")
                messages.error(request, f"Erreur lors de la correction: {str(e)}")
    else:
        # Pré-remplir le formulaire avec les valeurs actuelles
        initial_data = {
            'ancien_est_anomalie': resultat.est_anomalie,
            'ancien_type_anomalie': resultat.type_anomalie,
            'ancien_niveau_risque': resultat.niveau_risque,
        }
        form = CorrectionForm(initial=initial_data)

    context = {
        'form': form,
        'resultat': resultat,
    }

    return render(request, 'auditengine/corriger_anomalie.html', context)


# ==================== VUES API/AJAX ====================

@login_required
@require_http_methods(["GET"])
def session_status(request, pk):
    """API pour récupérer le statut d'une session"""
    session = get_object_or_404(SessionAudit, pk=pk)

    if not request.user.is_admin() and session.mission != request.user.mission:
        return JsonResponse({'error': 'Permission refusée'}, status=403)

    # Obtenir le nombre total de lignes depuis le fichier de paie
    nb_total_lignes = None
    if session.fichier_paie:
        # Essayer d'abord le champ nb_lignes du fichier
        if session.fichier_paie.nb_lignes:
            nb_total_lignes = session.fichier_paie.nb_lignes
        # Sinon essayer via la relation preview
        elif hasattr(session.fichier_paie, 'preview') and session.fichier_paie.preview:
            nb_total_lignes = session.fichier_paie.preview.nb_total_lignes
        # Fallback: utiliser le nombre de lignes analysées si le traitement est terminé
        elif session.status == 'completed':
            nb_total_lignes = session.nb_lignes_analysees

    return JsonResponse({
        'status': session.status,
        'progress': {
            'nb_lignes_analysees': session.nb_lignes_analysees,
            'nb_anomalies_detectees': session.nb_anomalies_detectees,
            'taux_anomalies': session.get_taux_anomalies(),
            'duree_traitement': session.duree_traitement_secondes,
            'nb_total_lignes': nb_total_lignes,
        },
        'stats_detail': {
            'salaires_anormaux': session.nb_salaires_anormaux,
            'employes_fantomes': session.nb_employes_fantomes,
            'primes_anormales': session.nb_primes_anormales,
            'heures_excessives': session.nb_heures_excessives,
            'rib_dupliques': session.nb_rib_dupliques,
        },
        'last_logs': session.logs_traitement[-5:] if session.logs_traitement else [],
        'errors': session.erreurs
    })


@login_required
def export_results(request, pk):
    """Exporter les résultats d'une session d'audit"""
    session = get_object_or_404(SessionAudit, pk=pk)

    if not request.user.is_admin() and session.mission != request.user.mission:
        return JsonResponse({'error': 'Permission refusée'}, status=403)

    format_export = request.GET.get('format', 'csv')
    type_filter = request.GET.get('type', '')
    anomalies_only = request.GET.get('anomalies_only', 'false') == 'true'

    try:
        import pandas as pd

        # Récupérer les résultats
        resultats = session.resultats.all()
        if type_filter:
            resultats = resultats.filter(type_anomalie=type_filter)
        if anomalies_only:
            resultats = resultats.filter(est_anomalie=True)

        # Préparer les données
        data = []
        for resultat in resultats:
            score_if_pct = f"{resultat.score_anomalie_if * 100:.1f}%" if resultat.score_anomalie_if is not None else ''
            score_mlp_pct = f"{resultat.score_classification_mlp * 100:.1f}%" if resultat.score_classification_mlp is not None else ''
            data.append({
                'Ligne Fichier': resultat.ligne_fichier,
                'Matricule': resultat.matricule,
                'Nom': resultat.nom,
                'Prénom': resultat.prenom,
                'Poste': resultat.poste,
                'RIB': resultat.rib,
                'Salaire Brut': resultat.salaire_brut,
                'Montant Total': resultat.montant_total,
                'Heures Travaillées': resultat.heures_travaillees,
                'Montant Primes': resultat.montant_primes,
                'Est Anomalie': 'Oui' if resultat.est_anomalie else 'Non',
                'Score IF': score_if_pct,
                'Type Anomalie': resultat.get_type_anomalie_display(),
                'Score MLP': score_mlp_pct,
                'Niveau Risque': resultat.get_niveau_risque_display(),
                'Explication IF': resultat.explication_if,
                'Explication MLP': resultat.explication_mlp,
                'Recommandation': resultat.recommandation_auto,
                'Validé': 'Oui' if resultat.valide_par_humain else 'Non',
                'Fausse Alerte': 'Oui' if resultat.est_fausse_alerte else 'Non',
                'Commentaire': resultat.commentaire_utilisateur,
            })

        df = pd.DataFrame(data)

        # Export selon le format
        if format_export == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="{session.nom_session}_audit_resultats.csv"'
            df.to_csv(response, index=False)

        elif format_export == 'excel':
            response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = f'attachment; filename="{session.nom_session}_audit_resultats.xlsx"'
            df.to_excel(response, index=False)

        else:
            return JsonResponse({'error': 'Format non supporté'}, status=400)

        log_user_action(
            user=request.user,
            action="export",
            feature="Audit IA",
            target="resultats",
            resource_id=str(session.id),
            new_value=format_export
        )

        return response

    except Exception as e:
        logger.error(f"Erreur export session audit {pk}: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


# ==================== DASHBOARD ET ANALYSES ====================

@login_required
def dashboard(request):
    """Dashboard principal de l'audit IA"""
    if not request.user.is_admin():
        sessions = SessionAudit.objects.filter(mission=request.user.mission)
    else:
        sessions = SessionAudit.objects.all()

    # Filtres
    mission_id = request.GET.get('mission')
    if mission_id and request.user.is_admin():
        sessions = sessions.filter(mission_id=mission_id)

    sessions_completed = sessions.filter(status='completed')

    # Statistiques globales
    stats = {
        'total_sessions': sessions.count(),
        'sessions_completed': sessions_completed.count(),
        'total_employes_analyses': sum(s.nb_lignes_analysees for s in sessions_completed),
        'total_anomalies_detectees': sum(s.nb_anomalies_detectees for s in sessions_completed),
        'total_salaires_anormaux': sum(s.nb_salaires_anormaux for s in sessions_completed),
        'total_employes_fantomes': sum(s.nb_employes_fantomes for s in sessions_completed),
        'total_rib_dupliques': sum(s.nb_rib_dupliques for s in sessions_completed),
    }

    # Taux de détection moyen
    if stats['total_employes_analyses'] > 0:
        stats['taux_detection_moyen'] = round(
            (stats['total_anomalies_detectees'] / stats['total_employes_analyses']) * 100, 2
        )
    else:
        stats['taux_detection_moyen'] = 0

    # Sessions récentes
    sessions_recentes = sessions_completed.order_by('-date_completion')[:10]

    # Évolution du taux de détection
    evolution_data = []
    for session in sessions_recentes:
        evolution_data.append({
            'nom': session.nom_session[:20],
            'date': session.date_completion.strftime('%d/%m'),
            'taux': session.get_taux_anomalies()
        })

    # Distribution des types d'anomalies
    types_data = [
        {'type': 'Salaires anormaux', 'count': stats['total_salaires_anormaux']},
        {'type': 'Employés fantômes', 'count': stats['total_employes_fantomes']},
        {'type': 'RIB dupliqués', 'count': stats['total_rib_dupliques']},
    ]

    context = {
        'stats': stats,
        'sessions_recentes': sessions_recentes,
        'evolution_data': evolution_data,
        'types_data': types_data,
    }

    if request.user.is_admin():
        from accounts.models import Mission
        context['missions'] = Mission.objects.all()
        context['current_mission'] = mission_id

    log_user_action(request.user, "consultation", "Tableau de bord", request=request)

    return render(request, 'auditengine/dashboard.html', context)


def _build_recommendations_context(session):
    """Construit (ou récupère depuis le cache) le contexte de recommandations d'une session.

    Partagé par la vue HTML (generate_recommendations) et l'export PDF
    (export_recommendations_pdf) pour éviter de dupliquer le calcul et les logs.
    """
    # OPTIMISATION: Cache simple pour éviter les recalculs
    cache_key = f"recommendations_{session.id}_{session.date_completion.isoformat() if session.date_completion else 'none'}"

    # Vérifier si on a déjà calculé ces recommandations
    cached_result = cache.get(cache_key)
    if cached_result:
        context = dict(cached_result)
        context['session'] = session  # Toujours mettre à jour la session
        return context

    # OPTIMISATION: Une seule requête pour récupérer toutes les anomalies avec leurs données
    anomalies = session.resultats.filter(est_anomalie=True).select_related('session')

    # Résumé exécutif
    total_lignes = session.nb_lignes_analysees or session.resultats.count()
    total_anomalies = anomalies.count()
    taux_anomalies = round((total_anomalies / total_lignes) * 100, 1) if total_lignes else 0

    # OPTIMISATION: Répartition par type en une seule requête
    type_map = dict(ResultatAudit.TYPE_ANOMALIE_CHOICES)
    type_stats = (
        anomalies
        .exclude(type_anomalie='aucune')
        .values('type_anomalie')
        .annotate(
            count=Count('id'),
            total_salaire=Sum('salaire_brut'),
            total_heures=Sum('heures_travaillees'),
            total_primes=Sum('montant_primes')
        )
        .order_by('-count')
    )

    repartition_types = []
    impact_financier_total = Decimal('0')
    impact_par_type = {}
    exemples_par_type = {}

    # OPTIMISATION: Traitement en une seule boucle
    for stat in type_stats:
        type_code = stat['type_anomalie']
        count = stat['count']

        # Calculer l'impact financier
        if type_code == 'salaire_anormal':
            impact = Decimal(str(stat['total_salaire'] or 0))
        elif type_code == 'heures_excessives':
            impact = Decimal(str(stat['total_heures'] or 0)) * Decimal('25')
        elif type_code == 'prime_anormale':
            impact = Decimal(str(stat['total_primes'] or 0))
        elif type_code == 'ghost_employee':
            impact = Decimal(str(count)) * Decimal('2500')
        elif type_code == 'duplicate_rib':
            impact = Decimal(str(count)) * Decimal('5000')
        else:
            impact = Decimal(str(count)) * Decimal('1000')

        impact_financier_total += impact

        # Répartition types
        repartition_types.append({
            'code': type_code,
            'label': type_map.get(type_code, type_code).capitalize(),
            'count': count,
            'percent': round((count / total_anomalies) * 100, 1) if total_anomalies else 0
        })

        # Impact par type
        impact_par_type[type_code] = {
            'montant': impact,
            'count': count,
            'label': type_map.get(type_code, type_code).capitalize()
        }

    # OPTIMISATION: Répartition par risque en une seule requête
    risk_map = dict(ResultatAudit.NIVEAU_RISQUE_CHOICES)
    risk_stats = (
        anomalies
        .values('niveau_risque')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    repartition_risques = [
        {
            'code': row['niveau_risque'],
            'label': risk_map.get(row['niveau_risque'], row['niveau_risque']).capitalize(),
            'count': row['count'],
        }
        for row in risk_stats
    ]

    # OPTIMISATION: Exemples en une seule requête par type
    for type_code in impact_par_type.keys():
        exemples = (
            anomalies
            .filter(type_anomalie=type_code)
            .values('id', 'nom', 'salaire_brut', 'montant_primes', 'niveau_risque')[:3]
        )

        exemples_par_type[type_code] = [
            {
                'id': ex['id'],
                'nom': ex['nom'],
                'salaire_brut': ex['salaire_brut'],
                'montant_primes': ex['montant_primes'],
                'niveau_risque': ex['niveau_risque'],
                'url': f'/auditengine/anomalies/{ex["id"]}/'
            }
            for ex in exemples
        ]

    # OPTIMISATION: Générer le rapport seulement si nécessaire
    rapport = RecommendationGenerator.generer_recommandations_session(session)
    recommandations_prioritaires = rapport.get('recommandations_prioritaires', [])

    # Construire le contexte optimisé
    recos_context = {
        'resume': {
            'total_lignes': total_lignes,
            'total_anomalies': total_anomalies,
            'taux_anomalies': taux_anomalies,
            'taux_conformite': round(100 - taux_anomalies, 1),
            'mission': getattr(session.mission, 'nom', ''),
            'session_nom': session.nom_session,
            'date_completion': session.date_completion,
        },
        'repartition_types': repartition_types,
        'repartition_risques': repartition_risques,
        'recommandations_prioritaires': recommandations_prioritaires,
        'plan_action': rapport.get('plan_action', []),
        'impact_financier': {
            'total': impact_financier_total,
            'par_type': impact_par_type,
        },
        'exemples': exemples_par_type,
    }

    context = {
        'session': session,
        'rapport': rapport,
        'recos': recos_context,
    }

    # OPTIMISATION: Mettre en cache pour 30 minutes
    cache.set(cache_key, context, 1800)

    return context


@login_required
def generate_recommendations(request, pk):
    """Générer un rapport de recommandations pour une session"""
    session = get_object_or_404(SessionAudit, pk=pk)

    if not request.user.is_admin() and session.mission != request.user.mission:
        messages.error(request, "Vous n'avez pas accès à cette session.")
        return redirect('auditengine:session_list')

    if session.status != 'completed':
        messages.error(request, "La session doit être terminée pour générer des recommandations.")
        return redirect('auditengine:session_detail', pk=pk)

    try:
        context = _build_recommendations_context(session)

        log_user_action(
            user=request.user,
            action="generate_recommendations",
            feature="Audit IA",
            target="session",
            resource_id=str(session.id)
        )

        return render(request, 'auditengine/recommendations_report.html', context)

    except Exception as e:
        logger.error(f"Erreur génération recommandations: {str(e)}")
        messages.error(request, f"Erreur lors de la génération: {str(e)}")
        return redirect('auditengine:session_detail', pk=pk)


@login_required
def export_recommendations_pdf(request, pk):
    session = get_object_or_404(SessionAudit, pk=pk)
    if not request.user.is_admin() and session.mission != request.user.mission:
        return HttpResponse('Accès refusé', status=403)

    if session.status != 'completed':
        return HttpResponse('La session doit être terminée pour générer des recommandations.', status=400)

    try:
        context = _build_recommendations_context(session)
    except Exception as e:
        logger.error(f"Erreur génération recommandations (export PDF) session {pk}: {str(e)}")
        return HttpResponse(f"Erreur lors de la génération: {e}", status=500)

    context['pdf_export'] = True

    log_user_action(
        user=request.user,
        action="export",
        feature="Audit IA",
        target="recommandations",
        resource_id=str(session.id)
    )

    # Utiliser un template minimaliste pour le PDF
    template_pdf = 'auditengine/recommendations_report_pdf.html'
    template_html = 'auditengine/recommendations_report.html'
    html = render_to_string(template_pdf, context)
    try:
        try:
            from weasyprint import HTML
            with tempfile.NamedTemporaryFile(delete=True, suffix='.pdf') as output:
                HTML(string=html, base_url=request.build_absolute_uri('/')).write_pdf(output.name)
                output.seek(0)
                pdf = output.read()
                response = HttpResponse(pdf, content_type='application/pdf')
                response['Content-Disposition'] = f'attachment; filename="rapport_recommandations_{session.pk}.pdf"'
                return response
        except (ImportError, OSError, Exception):
            # Fallback xhtml2pdf
            try:
                from xhtml2pdf import pisa
                import io
                pdf_file = io.BytesIO()
                pisa_status = pisa.CreatePDF(html, dest=pdf_file, encoding='utf-8')
                if not pisa_status.err:
                    response = HttpResponse(pdf_file.getvalue(), content_type='application/pdf')
                    response['Content-Disposition'] = f'attachment; filename="rapport_recommandations_{session.pk}.pdf"'
                    return response
                else:
                    # Si xhtml2pdf échoue, fallback HTML classique
                    html_fallback = render_to_string(template_html, context)
                    return HttpResponse(html_fallback)
            except Exception:
                html_fallback = render_to_string(template_html, context)
                return HttpResponse(html_fallback)
    except Exception:
        html_fallback = render_to_string(template_html, context)
        return HttpResponse(html_fallback)


# ==================== ADMINISTRATION IA ====================

@login_required
def parametrage_ia(request):
    """Configuration des paramètres IA (admin seulement)"""
    if not request.user.is_admin():
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('auditengine:dashboard')

    config = ParametrageIA.get_config()

    if request.method == 'POST':
        form = ParametrageIAForm(request.POST, instance=config)
        if form.is_valid():
            config = form.save(commit=False)
            config.modifie_par = request.user
            config.save()

            log_user_action(
                user=request.user,
                action="update_config",
                feature="Paramétrage IA",
                target="config",
                resource_id="1"
            )

            messages.success(request, "Configuration IA mise à jour avec succès.")
            return redirect('auditengine:parametrage_ia')
    else:
        form = ParametrageIAForm(instance=config)

    # Statistiques des modèles
    modeles_stats = {
        'if_global': ModeleIA.objects.filter(type_modele='isolation_forest', scope='global').count(),
        'mlp_global': ModeleIA.objects.filter(type_modele='mlp_classifier', scope='global').count(),
        'if_mission': ModeleIA.objects.filter(type_modele='isolation_forest', scope='mission').count(),
        'mlp_mission': ModeleIA.objects.filter(type_modele='mlp_classifier', scope='mission').count(),
    }

    context = {
        'form': form,
        'config': config,
        'modeles_stats': modeles_stats,
    }

    return render(request, 'auditengine/parametrage_ia.html', context)


@login_required
def modeles_ia(request):
    """Gestion des modèles IA (admin seulement)"""
    if not request.user.is_admin():
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('auditengine:dashboard')

    modeles = ModeleIA.objects.all().order_by('-date_creation')

    # Filtres
    type_filter = request.GET.get('type')
    scope_filter = request.GET.get('scope')

    if type_filter:
        modeles = modeles.filter(type_modele=type_filter)
    if scope_filter:
        modeles = modeles.filter(scope=scope_filter)

    # Pagination
    paginator = Paginator(modeles, 15)
    page_number = request.GET.get('page')
    modeles_page = paginator.get_page(page_number)

    context = {
        'modeles_page': modeles_page,
        'type_choices': ModeleIA.TYPE_MODELE_CHOICES,
        'scope_choices': ModeleIA.SCOPE_CHOICES,
        'current_filters': {
            'type': type_filter,
            'scope': scope_filter,
        }
    }

    return render(request, 'auditengine/modeles_ia.html', context)


@login_required
def reentrainer_modeles(request):
    """Lancer le réentraînement des modèles (admin seulement)"""
    if not request.user.is_admin():
        return JsonResponse({'success': False, 'error': 'Permission refusée'})

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            type_modele = data.get('type_modele', 'both')
            mission_id = data.get('mission_id')

            mission = None
            if mission_id:
                from accounts.models import Mission
                mission = Mission.objects.get(id=mission_id)

            # Lancer le réentraînement
            engine = RetrainingEngine(mission=mission, utilisateur=request.user)
            success = engine.reentrainer_modeles(type_modele)

            log_user_action(
                user=request.user,
                action="retrain",
                feature="Modèles IA",
                target=type_modele,
                resource_id=str(mission_id) if mission_id else "global",
                status='success' if success else 'error'
            )

            if success:
                return JsonResponse({
                    'success': True,
                    'message': 'Réentraînement terminé avec succès',
                    'logs': engine.logs
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Pas assez de corrections pour réentraîner',
                    'logs': engine.logs
                })

        except Exception as e:
            logger.error(f"Erreur réentraînement: {str(e)}")
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Méthode non autorisée'})


@login_required
def evaluer_modele(request, modele_id):
    """Évaluer les performances d'un modèle (admin seulement)"""
    if not request.user.is_admin():
        return JsonResponse({'success': False, 'error': 'Permission refusée'})

    try:
        evaluator = ModelEvaluator()
        metriques = evaluator.evaluer_modele(modele_id)

        log_user_action(
            user=request.user,
            action="evaluate",
            feature="Modèles IA",
            target="modele",
            resource_id=str(modele_id)
        )

        return JsonResponse({
            'success': True,
            'metriques': metriques,
            'logs': evaluator.logs
        })

    except Exception as e:
        logger.error(f"Erreur évaluation modèle {modele_id}: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})


# ==================== UTILS ====================

@login_required
def get_available_paie_files(request):
    """API pour récupérer les fichiers de paie disponibles"""
    mission = request.user.mission
    if not mission:
        return JsonResponse({'error': 'Aucune mission assignée'}, status=400)

    fichiers_paie = FichierImporte.objects.filter(
        mission=mission,
        type_fichier='paie',
        status='approved'
    ).values('id', 'nom_fichier', 'date_import', 'nb_lignes')

    return JsonResponse({
        'fichiers_paie': list(fichiers_paie)
    })


@login_required
def session_logs(request, pk):
    """Récupérer les logs d'une session d'audit"""
    session = get_object_or_404(SessionAudit, pk=pk)

    if not request.user.is_admin() and session.mission != request.user.mission:
        return JsonResponse({'error': 'Permission refusée'}, status=403)

    return JsonResponse({
        'logs': session.logs_traitement or [],
        'status': session.status,
        'errors': session.erreurs,
        'duree': session.duree_traitement_secondes
    })


@login_required
def corrections_stats(request):
    """Statistiques des corrections utilisateur (admin seulement)"""
    if not request.user.is_admin():
        return JsonResponse({'error': 'Permission refusée'}, status=403)

    # Statistiques globales des corrections
    corrections = CorrectionUtilisateur.objects.all()

    stats = {
        'total_corrections': corrections.count(),
        'corrections_utilisees': corrections.filter(utilisee_pour_entrainement=True).count(),
        'corrections_en_attente': corrections.filter(utilisee_pour_entrainement=False).count(),
        'corrections_par_type': {},
        'corrections_par_confiance': {},
    }

    # Répartition par type
    for type_code, type_label in CorrectionUtilisateur.TYPE_CORRECTION_CHOICES:
        count = corrections.filter(type_correction=type_code).count()
        stats['corrections_par_type'][type_label] = count

    # Répartition par niveau de confiance
    for niveau in range(1, 11):
        count = corrections.filter(confiance_utilisateur=niveau).count()
        stats['corrections_par_confiance'][f'Niveau {niveau}'] = count

    return JsonResponse(stats)


@login_required
def dashboard_auditengine_stats_api(request):
    # Moyenne du taux de détection IA sur toutes les sessions
    taux_detection_moyen = SessionAudit.objects.aggregate(avg=Avg('nb_anomalies_detectees'))['avg'] or 0
    # Nombre de sessions terminées
    sessions_completed = SessionAudit.objects.filter(status='completed').count()
    # Nombre total d'anomalies détectées
    total_anomalies_detectees = ResultatAudit.objects.filter(est_anomalie=True).count()
    # Nombre total d'employés analysés (lignes analysées)
    total_employes_analyses = ResultatAudit.objects.count()
    stats = {
        'taux_detection_moyen': round(taux_detection_moyen, 1),
        'sessions_completed': sessions_completed,
        'total_anomalies_detectees': total_anomalies_detectees,
        'total_employes_analyses': total_employes_analyses,
    }
    return JsonResponse(stats)


@login_required
def api_session_stats(request, pk):
    try:
        session = get_object_or_404(SessionAudit, pk=pk)
        
        # Log de debug
        logger.info(f"API session stats - User: {request.user.username}, Session: {session.nom_session}, Mission: {session.mission}")
        logger.info(f"User is admin: {request.user.is_superuser}, User mission: {getattr(request.user, 'mission', None)}")
        
        # Vérification des permissions - permettre l'accès à tous les utilisateurs connectés
        # car ce sont juste des statistiques publiques
        if not request.user.is_authenticated:
            logger.warning(f"Utilisateur non connecté")
            return JsonResponse({'error': 'Utilisateur non connecté'}, status=401)
        
        # Appliquer les mêmes filtres que le tableau
        resultats = session.resultats.all()
        type_filter = request.GET.get('type')
        niveau_filter = request.GET.get('niveau')
        anomalie_filter = request.GET.get('anomalie')
        
        if type_filter:
            resultats = resultats.filter(type_anomalie=type_filter)
        if niveau_filter:
            resultats = resultats.filter(niveau_risque=niveau_filter)
        if anomalie_filter == 'oui':
            resultats = resultats.filter(est_anomalie=True)
        elif anomalie_filter == 'non':
            resultats = resultats.filter(est_anomalie=False)
        
        # Statistiques détaillées par type (sur le sous-ensemble filtré)
        stats_detail = {
            'salaires_anormaux': resultats.filter(type_anomalie='salaire_anormal').count(),
            'employes_fantomes': resultats.filter(type_anomalie='ghost_employee').count(),
            'primes_anormales': resultats.filter(type_anomalie='prime_anormale').count(),
            'heures_excessives': resultats.filter(type_anomalie='heures_excessives').count(),
            'rib_dupliques': resultats.filter(type_anomalie='duplicate_rib').count(),
            'aucune_anomalie': resultats.filter(type_anomalie='aucune').count(),
        }
        
        # Statistiques par niveau de risque (sur le sous-ensemble filtré)
        stats_risque = {
            'critique': resultats.filter(niveau_risque='critique').count(),
            'eleve': resultats.filter(niveau_risque='eleve').count(),
            'moyen': resultats.filter(niveau_risque='moyen').count(),
            'faible': resultats.filter(niveau_risque='faible').count(),
        }
        
        logger.info(f"API session stats - Stats calculées: {stats_detail}")
        return JsonResponse({'stats_detail': stats_detail, 'stats_risque': stats_risque})
        
    except Exception as e:
        logger.error(f"Erreur API session stats {pk}: {str(e)}")
        return JsonResponse({
            'error': 'Erreur lors du calcul des statistiques',
            'stats_detail': {
                'salaires_anormaux': 0,
                'employes_fantomes': 0,
                'primes_anormales': 0,
                'heures_excessives': 0,
                'rib_dupliques': 0,
                'aucune_anomalie': 0,
            },
            'stats_risque': {
                'critique': 0,
                'eleve': 0,
                'moyen': 0,
                'faible': 0,
            }
        }, status=500)


@login_required
def api_session_results(request, pk):
    from .models import SessionAudit, ResultatAudit
    session = get_object_or_404(SessionAudit, pk=pk)
    resultats = session.resultats.all()
    # Filtres
    type_filter = request.GET.get('type')
    niveau_filter = request.GET.get('niveau')
    anomalie_filter = request.GET.get('anomalie')
    fausse_alerte_filter = request.GET.get('fausse_alerte')
    ordering = request.GET.get('ordering')
    search = request.GET.get('search')
    if type_filter:
        resultats = resultats.filter(type_anomalie=type_filter)
    if niveau_filter:
        resultats = resultats.filter(niveau_risque=niveau_filter)
    if anomalie_filter == 'oui':
        resultats = resultats.filter(est_anomalie=True)
    elif anomalie_filter == 'non':
        resultats = resultats.filter(est_anomalie=False)
    if search:
        resultats = resultats.filter(
            Q(nom__icontains=search) |
            Q(prenom__icontains=search) |
            Q(matricule__icontains=search)
        )
    if fausse_alerte_filter == 'oui':
        resultats = resultats.filter(est_fausse_alerte=True)
    elif fausse_alerte_filter == 'non':
        resultats = resultats.filter(est_fausse_alerte=False)

    # Tri
    if ordering in ['score_if', '-score_if', 'score_mlp', '-score_mlp', 'nom', '-nom']:
        ordering_map = {
            'score_if': 'score_anomalie_if',
            '-score_if': '-score_anomalie_if',
            'score_mlp': 'score_classification_mlp',
            '-score_mlp': '-score_classification_mlp',
            'nom': 'nom',
            '-nom': '-nom',
        }
        resultats = resultats.order_by(ordering_map[ordering])
    # Pagination
    page_number = request.GET.get('page', 1)
    paginator = Paginator(resultats, 25)
    page = paginator.get_page(page_number)
    # Format JSON
    data = []
    for r in page:
        data.append({
            'id': r.id,
            'ligne_fichier': r.ligne_fichier,
            'matricule': r.matricule,
            'nom': r.nom,
            'prenom': r.prenom,
            'poste': r.poste,
            'rib': r.rib,
            'salaire_brut': str(r.salaire_brut) if r.salaire_brut is not None else '',
            'montant_total': str(r.montant_total) if r.montant_total is not None else '',
            'heures_travaillees': r.heures_travaillees,
            'montant_primes': str(r.montant_primes) if r.montant_primes is not None else '',
            'est_anomalie': r.est_anomalie,
            'est_fausse_alerte': r.est_fausse_alerte,
            'type_anomalie': r.get_type_anomalie_display(),
            'niveau_risque': r.get_niveau_risque_display(),
            'explication_if': r.explication_if,
            'explication_mlp': r.explication_mlp,
            'recommandation_auto': r.recommandation_auto,
            'valide_par_humain': r.valide_par_humain,
            'commentaire_utilisateur': r.commentaire_utilisateur,
        })
    return JsonResponse({
        'results': data,
        'has_next': page.has_next(),
        'has_previous': page.has_previous(),
        'num_pages': paginator.num_pages,
        'current_page': page.number,
        'total_results': paginator.count,
    })


@login_required
@require_http_methods(["POST"])
def valider_resultat(request, resultat_id):
    """Valider un résultat d'audit"""
    resultat = get_object_or_404(ResultatAudit, pk=resultat_id)
    
    # Vérification des permissions
    if not request.user.is_admin() and resultat.session.mission != request.user.mission:
        return JsonResponse({'success': False, 'error': 'Permission refusée'}, status=403)
    
    try:
        resultat.valide_par_humain = True
        resultat.valide_par = request.user
        resultat.date_validation = timezone.now()
        resultat.save()
        
        log_user_action(
            user=request.user,
            action="validate",
            feature="Audit IA",
            target="resultat",
            resource_id=str(resultat.id)
        )
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        logger.error(f"Erreur validation résultat {resultat_id}: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def dashboard_anomalies_stats_api(request):
    """API pour les totaux d'anomalies par type (tableau de bord)"""
    if not request.user.is_admin():
        sessions = SessionAudit.objects.filter(mission=request.user.mission, status='completed')
    else:
        sessions = SessionAudit.objects.filter(status='completed')

    total_employes_fantomes = sum(s.nb_employes_fantomes for s in sessions)
    total_salaires_anormaux = sum(s.nb_salaires_anormaux for s in sessions)
    total_rib_dupliques = sum(s.nb_rib_dupliques for s in sessions)

    return JsonResponse({
        'total_employes_fantomes': total_employes_fantomes,
        'total_salaires_anormaux': total_salaires_anormaux,
        'total_rib_dupliques': total_rib_dupliques,
    })


# ==================== GESTION DES TÂCHES D'ACTION ====================

@login_required
@require_http_methods(["POST"])
def creer_taches_action(request, session_id):
    """Créer des tâches d'action à partir du plan d'action d'une session"""
    session = get_object_or_404(SessionAudit, pk=session_id)
    
    # Vérification des permissions
    if not request.user.is_admin() and session.mission != request.user.mission:
        return JsonResponse({'success': False, 'error': 'Permission refusée'}, status=403)
    
    try:
        # Générer le plan d'action
        rapport = RecommendationGenerator.generer_recommandations_session(session)
        plan_action = rapport.get('plan_action', [])
        
        # Créer les tâches
        taches_crees = TacheAction.creer_depuis_plan_action(
            session_audit=session,
            plan_action=plan_action,
            utilisateur=request.user
        )
        
        log_user_action(
            user=request.user,
            action="create_tasks",
            feature="Audit IA",
            target="session",
            resource_id=str(session.id)
        )
        
        return JsonResponse({
            'success': True,
            'message': f'{len(taches_crees)} tâches créées avec succès',
            'nb_taches': len(taches_crees)
        })
        
    except Exception as e:
        logger.error(f"Erreur création tâches session {session_id}: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def assigner_tache(request, tache_id):
    """Assigner une tâche à un utilisateur"""
    tache = get_object_or_404(TacheAction, pk=tache_id)
    
    # Vérification des permissions
    if not request.user.is_admin() and tache.session_audit.mission != request.user.mission:
        return JsonResponse({'success': False, 'error': 'Permission refusée'}, status=403)
    
    try:
        assigne_a_id = request.POST.get('assigne_a')
        if assigne_a_id:
            from accounts.models import CustomUser
            assigne_a = CustomUser.objects.get(pk=assigne_a_id)
            tache.assigne_a = assigne_a
        else:
            tache.assigne_a = None
            
        tache.save()
        
        log_user_action(
            user=request.user,
            action="assign_task",
            feature="Audit IA",
            target="tache",
            resource_id=str(tache.id)
        )
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        logger.error(f"Erreur assignation tâche {tache_id}: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def marquer_tache_faite(request, tache_id):
    """Marquer une tâche comme terminée"""
    tache = get_object_or_404(TacheAction, pk=tache_id)
    
    # Vérification des permissions
    if not request.user.is_admin() and tache.session_audit.mission != request.user.mission:
        return JsonResponse({'success': False, 'error': 'Permission refusée'}, status=403)
    
    try:
        tache.statut = 'terminee'
        tache.date_fin_reelle = timezone.now()
        tache.save()
        
        log_user_action(
            user=request.user,
            action="complete_task",
            feature="Audit IA",
            target="tache",
            resource_id=str(tache.id)
        )
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        logger.error(f"Erreur marquage tâche {tache_id}: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def liste_taches_action(request, session_id):
    """Liste des tâches d'action d'une session"""
    session = get_object_or_404(SessionAudit, pk=session_id)
    
    # Vérification des permissions
    if not request.user.is_admin() and session.mission != request.user.mission:
        messages.error(request, "Vous n'avez pas accès à cette session.")
        return redirect('auditengine:session_list')
    
    taches = TacheAction.objects.filter(session_audit=session)
    
    # Filtres
    statut = request.GET.get('statut')
    priorite = request.GET.get('priorite')
    
    if statut:
        taches = taches.filter(statut=statut)
    if priorite:
        taches = taches.filter(priorite=priorite)
    
    # Statistiques pour les cartes
    taches_en_cours = TacheAction.objects.filter(session_audit=session, statut='en_cours')
    taches_terminees = TacheAction.objects.filter(session_audit=session, statut='terminee')
    taches_critiques = TacheAction.objects.filter(session_audit=session, priorite='critique')
    
    context = {
        'session': session,
        'taches': taches,
        'taches_en_cours': taches_en_cours,
        'taches_terminees': taches_terminees,
        'taches_critiques': taches_critiques,
        'statut_choices': TacheAction.STATUT_CHOICES,
        'priorite_choices': TacheAction.PRIORITE_CHOICES,
    }
    
    return render(request, 'auditengine/liste_taches_action.html', context)


@login_required
def audit_logs(request):
    """Vue pour consulter les journaux d'audit"""
    # Vérification des permissions (admin seulement)
    if not request.user.is_admin():
        messages.error(request, "Accès refusé. Droits administrateur requis.")
        return redirect('auditengine:dashboard')
    
    from .models import AuditLog
    from django.db.models import Q
    from datetime import datetime, timedelta
    
    # Filtres
    user_filter = request.GET.get('user')
    action_filter = request.GET.get('action')
    severity_filter = request.GET.get('severity')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    suspicious_only = request.GET.get('suspicious') == 'on'
    search = request.GET.get('search')
    
    # Query de base
    logs = AuditLog.objects.all()
    
    # Application des filtres
    if user_filter:
        logs = logs.filter(user__username__icontains=user_filter)
    
    if action_filter:
        logs = logs.filter(action=action_filter)
    
    if severity_filter:
        logs = logs.filter(severity=severity_filter)
    
    if suspicious_only:
        logs = logs.filter(is_suspicious=True)
    
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            logs = logs.filter(timestamp__date__gte=date_from_obj.date())
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            logs = logs.filter(timestamp__date__lte=date_to_obj.date())
        except ValueError:
            pass
    
    if search:
        logs = logs.filter(
            Q(description__icontains=search) |
            Q(user__username__icontains=search) |
            Q(resource_id__icontains=search) |
            Q(ip_address__icontains=search)
        )
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(logs, 50)  # 50 logs par page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Statistiques
    total_logs = logs.count()
    suspicious_count = logs.filter(is_suspicious=True).count()
    error_count = logs.filter(severity__in=['error', 'critical']).count()
    
    # Actions récentes par utilisateur
    recent_actions = AuditLog.objects.filter(
        timestamp__gte=timezone.now() - timedelta(days=7)
    ).values('user__username', 'action').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    context = {
        'page_obj': page_obj,
        'total_logs': total_logs,
        'suspicious_count': suspicious_count,
        'error_count': error_count,
        'recent_actions': recent_actions,
        'action_choices': AuditLog.ACTION_CHOICES,
        'severity_choices': AuditLog.SEVERITY_CHOICES,
        'filters': {
            'user': user_filter,
            'action': action_filter,
            'severity': severity_filter,
            'date_from': date_from,
            'date_to': date_to,
            'suspicious': suspicious_only,
            'search': search,
        }
    }
    
    return render(request, 'auditengine/audit_logs.html', context)


@login_required
def security_dashboard(request):
    """Tableau de bord de sécurité"""
    # Vérification des permissions (admin seulement)
    if not request.user.is_admin():
        messages.error(request, "Accès refusé. Droits administrateur requis.")
        return redirect('auditengine:dashboard')
    
    from .models import AuditLog
    from django.db.models import Count
    from datetime import datetime, timedelta
    
    # Période d'analyse (7 jours par défaut)
    days = int(request.GET.get('days', 7))
    start_date = timezone.now() - timedelta(days=days)
    
    # Statistiques générales
    total_actions = AuditLog.objects.filter(timestamp__gte=start_date).count()
    suspicious_actions = AuditLog.objects.filter(
        timestamp__gte=start_date, 
        is_suspicious=True
    ).count()
    error_actions = AuditLog.objects.filter(
        timestamp__gte=start_date,
        severity__in=['error', 'critical']
    ).count()
    
    # Actions par type
    actions_by_type = AuditLog.objects.filter(
        timestamp__gte=start_date
    ).values('action').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    # Actions par utilisateur
    actions_by_user = AuditLog.objects.filter(
        timestamp__gte=start_date
    ).values('user__username').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    # Alertes de sécurité récentes
    security_alerts = AuditLog.get_security_alerts(days=days)
    
    # Tentatives d'accès suspectes
    suspicious_access = AuditLog.objects.filter(
        timestamp__gte=start_date,
        action='access_denied'
    ).order_by('-timestamp')[:20]
    
    # Activité par heure
    hourly_activity = []
    for hour in range(24):
        count = AuditLog.objects.filter(
            timestamp__gte=start_date,
            timestamp__hour=hour
        ).count()
        hourly_activity.append({'hour': hour, 'count': count})
    
    context = {
        'days': days,
        'total_actions': total_actions,
        'suspicious_actions': suspicious_actions,
        'error_actions': error_actions,
        'actions_by_type': actions_by_type,
        'actions_by_user': actions_by_user,
        'security_alerts': security_alerts,
        'suspicious_access': suspicious_access,
        'hourly_activity': hourly_activity,
    }
    
    return render(request, 'auditengine/security_dashboard.html', context)
