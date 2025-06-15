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
from django.db.models import Q, Count
from django.utils import timezone

from .models import (
    SessionAudit, ResultatAudit, ParametrageIA, ModeleIA,
    CorrectionUtilisateur
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
    """Détail d'une session d'audit avec résultats"""
    session = get_object_or_404(SessionAudit, pk=pk)

    # Vérification des permissions
    if not request.user.is_admin() and session.mission != request.user.mission:
        messages.error(request, "Vous n'avez pas accès à cette session.")
        return redirect('auditengine:session_list')

    # Récupérer les résultats avec filtres
    resultats = session.resultats.all()

    # Filtres
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

    # Pagination
    paginator = Paginator(resultats, 25)
    page_number = request.GET.get('page')
    resultats_page = paginator.get_page(page_number)

    # Statistiques détaillées par type
    stats_detail = {
        'salaires_anormaux': session.resultats.filter(type_anomalie='salaire_anormal').count(),
        'employes_fantomes': session.resultats.filter(type_anomalie='ghost_employee').count(),
        'primes_anormales': session.resultats.filter(type_anomalie='prime_anormale').count(),
        'heures_excessives': session.resultats.filter(type_anomalie='heures_excessives').count(),
        'rib_dupliques': session.resultats.filter(type_anomalie='duplicate_rib').count(),
        'aucune_anomalie': session.resultats.filter(type_anomalie='aucune').count(),
    }

    # Statistiques par niveau de risque
    stats_risque = {
        'critique': session.resultats.filter(niveau_risque='critique').count(),
        'eleve': session.resultats.filter(niveau_risque='eleve').count(),
        'moyen': session.resultats.filter(niveau_risque='moyen').count(),
        'faible': session.resultats.filter(niveau_risque='faible').count(),
    }

    context = {
        'session': session,
        'resultats_page': resultats_page,
        'stats_detail': stats_detail,
        'stats_risque': stats_risque,
        'type_choices': ResultatAudit.TYPE_ANOMALIE_CHOICES,
        'niveau_choices': ResultatAudit.NIVEAU_RISQUE_CHOICES,
        'current_filters': {
            'type': type_filter,
            'niveau': niveau_filter,
            'anomalie': anomalie_filter,
        },
        'can_process': session.status in ['pending', 'error'],
        'can_edit': request.user.is_admin() or session.utilisateur == request.user,
    }

    return render(request, 'auditengine/session_detail.html', context)


@login_required
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

    return JsonResponse({
        'status': session.status,
        'progress': {
            'nb_lignes_analysees': session.nb_lignes_analysees,
            'nb_anomalies_detectees': session.nb_anomalies_detectees,
            'taux_anomalies': session.get_taux_anomalies(),
            'duree_traitement': session.duree_traitement_secondes,
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
                'Score IF': resultat.score_anomalie_if,
                'Type Anomalie': resultat.get_type_anomalie_display(),
                'Score MLP': resultat.score_classification_mlp,
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

    return render(request, 'auditengine/dashboard.html', context)


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
        # Générer le rapport de recommandations
        rapport = RecommendationGenerator.generer_recommandations_session(session)

        log_user_action(
            user=request.user,
            action="generate_recommendations",
            feature="Audit IA",
            target="session",
            resource_id=str(session.id)
        )

        context = {
            'session': session,
            'rapport': rapport,
        }

        return render(request, 'auditengine/recommendations_report.html', context)

    except Exception as e:
        logger.error(f"Erreur génération recommandations: {str(e)}")
        messages.error(request, f"Erreur lors de la génération: {str(e)}")
        return redirect('auditengine:session_detail', pk=pk)


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
            engine = RetrainingEngine(mission=mission)
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
