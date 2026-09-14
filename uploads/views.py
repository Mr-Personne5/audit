import json
import logging
import os
import shutil

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction, IntegrityError
from django.db.models import Q
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from accounts.utils import log_user_action
from .forms import FichierImporteForm, ApprovalForm
from .models import FichierImporte, PreviewData, MappingColonne
from .utils import FileProcessor

logger = logging.getLogger('auditia')


# ==================== VUES PRINCIPALES ====================

@login_required
def upload_list(request):
    """Liste des fichiers uploadés par l'utilisateur ou tous si admin"""
    if request.user.is_admin():
        fichiers = FichierImporte.objects.all()
    else:
        fichiers = FichierImporte.objects.filter(utilisateur=request.user)

    # Filtres
    type_fichier = request.GET.get('type')
    status = request.GET.get('status')
    search = request.GET.get('search')

    if type_fichier:
        fichiers = fichiers.filter(type_fichier=type_fichier)
    if status:
        fichiers = fichiers.filter(status=status)
    if search:
        fichiers = fichiers.filter(
            Q(nom_fichier__icontains=search) |
            Q(nom_original__icontains=search)
        )

    # Pagination
    paginator = Paginator(fichiers, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Statistiques pour le tableau de bord
    stats = {
        'total': fichiers.count(),
        'processed': fichiers.filter(status='processed').count(),
        'pending': fichiers.filter(status='pending').count(),
        'errors': fichiers.filter(status='error').count(),
    }

    # Ajout des stats_cards pour le template
    stats_cards = [
        {
            'key': 'pending',
            'label': 'En attente',
            'icon': 'clock-history',
            'color': 'warning',
            'value': stats.get('pending', 0)
        },
        {
            'key': 'processed',
            'label': 'Traités',
            'icon': 'check-circle',
            'color': 'info',
            'value': stats.get('processed', 0)
        },
        {
            'key': 'total',
            'label': 'Total',
            'icon': 'files',
            'color': 'success',
            'value': stats.get('total', 0)
        },
        {
            'key': 'errors',
            'label': 'Erreurs',
            'icon': 'exclamation-triangle',
            'color': 'danger',
            'value': stats.get('errors', 0)
        }
    ]

    context = {
        'page_obj': page_obj,
        'stats': stats,
        'stats_cards': stats_cards,  # Ajouté pour le template
        'types_fichier': FichierImporte.TYPES_FICHIER,
        'status_choices': FichierImporte.STATUS_CHOICES,
        'current_filters': {
            'type': type_fichier,
            'status': status,
            'search': search,
        }
    }

    return render(request, 'uploads/upload_list.html', context)


@login_required
def upload_file(request):
    """Upload d'un nouveau fichier"""
    if request.method == 'POST':
        form = FichierImporteForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            try:
                with transaction.atomic():
                    fichier = form.save(commit=False)
                    fichier.utilisateur = request.user
                    fichier.save()

                    # Log de l'action
                    log_user_action(
                        user=request.user,
                        action="upload",
                        feature="Gestion fichiers",
                        target=fichier.type_fichier,
                        resource_id=str(fichier.id),
                        new_value=fichier.nom_fichier
                    )

                    # Traitement automatique du fichier
                    success, message = FileProcessor.analyser_fichier(fichier)

                    if success:
                        messages.success(request, f"Fichier '{fichier.nom_fichier}' uploadé et analysé avec succès!")
                        return redirect('uploads:file_detail', pk=fichier.pk)
                    else:
                        messages.warning(request, f"Fichier uploadé mais erreur d'analyse: {message}")
                        return redirect('uploads:file_detail', pk=fichier.pk)

            except IntegrityError as e:
                # Gestion de la contrainte d'unicité
                if 'unique' in str(e).lower():
                    # Récupérer les infos du formulaire
                    mission_id = form.cleaned_data['mission'].id
                    type_fichier = form.cleaned_data['type_fichier']
                    version = form.cleaned_data.get('version', 1)
                    nom_fichier = form.cleaned_data.get('nom_fichier', '')
                    # Stocker temporairement le fichier uploadé
                    fichier_temp = request.FILES['fichier']
                    # Sauvegarder le fichier temporairement dans /tmp ou media/tmp
                    import os, uuid
                    from django.core.files.storage import default_storage
                    tmp_dir = 'media/tmp_uploads/'
                    os.makedirs(tmp_dir, exist_ok=True)
                    tmp_filename = f"{uuid.uuid4()}_{fichier_temp.name}"
                    tmp_path = os.path.join(tmp_dir, tmp_filename)
                    with open(tmp_path, 'wb+') as destination:
                        for chunk in fichier_temp.chunks():
                            destination.write(chunk)
                    # Récupérer la mission pour affichage
                    from accounts.models import Mission
                    mission = Mission.objects.get(pk=mission_id)
                    # Calculer la version suivante
                    from uploads.models import FichierImporte
                    max_version = FichierImporte.objects.filter(mission_id=mission_id, type_fichier=type_fichier).order_by('-version').first()
                    version_suivante = max_version.version + 1 if max_version else 1
                    # Afficher la page de confirmation
                    return render(request, 'uploads/confirm_replace.html', {
                        'mission': mission,
                        'mission_id': mission_id,
                        'type_fichier': type_fichier,
                        'version': version,
                        'version_suivante': version_suivante,
                        'nom_fichier': nom_fichier,
                        'fichier_temp': tmp_path,
                    })
                else:
                    logger.error(f"Erreur lors de l'upload: {str(e)}")
                    messages.error(request, f"Erreur lors de l'upload: {str(e)}")
            except Exception as e:
                logger.error(f"Erreur lors de l'upload: {str(e)}")
                messages.error(request, f"Erreur lors de l'upload: {str(e)}")
    else:
        form = FichierImporteForm(user=request.user)

    return render(request, 'uploads/upload_form.html', {'form': form})


@login_required
def file_detail(request, pk):
    """Détail d'un fichier avec prévisualisation"""
    fichier = get_object_or_404(FichierImporte, pk=pk)

    # Vérification des permissions
    if not fichier.peut_etre_modifie_par(request.user) and not request.user.is_admin():
        messages.error(request, "Vous n'avez pas accès à ce fichier.")
        return redirect('uploads:upload_list')

    # Alternative avec hasattr - PLUS PROPRE ✅
    preview = getattr(fichier, 'preview', None)

    # Récupérer les mappings
    mappings = fichier.mappings.all()

    # Colonnes manquantes
    colonnes_manquantes = fichier.get_colonnes_manquantes()

    context = {
        'fichier': fichier,
        'preview': preview,
        'mappings': mappings,
        'colonnes_manquantes': colonnes_manquantes,
        'can_approve': request.user.is_admin() or fichier.utilisateur == request.user,
        'can_edit': fichier.peut_etre_modifie_par(request.user),
    }

    return render(request, 'uploads/file_detail.html', context)


@login_required
def reprocess_file(request, pk):
    """Retraiter un fichier"""
    fichier = get_object_or_404(FichierImporte, pk=pk)

    if not fichier.peut_etre_modifie_par(request.user):
        return JsonResponse({'success': False, 'error': 'Permission refusée'})

    try:
        success, message = FileProcessor.analyser_fichier(fichier)

        log_user_action(
            user=request.user,
            action="reprocess",
            feature="Gestion fichiers",
            target=fichier.type_fichier,
            resource_id=str(fichier.id),
            status='success' if success else 'error'
        )

        return JsonResponse({
            'success': success,
            'message': message,
            'status': fichier.status,
            'nb_lignes': fichier.nb_lignes,
            'colonnes': fichier.colonnes_detectees
        })

    except Exception as e:
        logger.error(f"Erreur lors du retraitement: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def approve_file(request, pk):
    """Approuver/rejeter un fichier (admin ou propriétaire du fichier)"""
    fichier = get_object_or_404(FichierImporte, pk=pk)
    
    # Vérifier les permissions : admin ou propriétaire du fichier
    if not request.user.is_admin() and fichier.utilisateur != request.user:
        messages.error(request, "Vous n'avez pas la permission d'approuver ce fichier.")
        return redirect('uploads:file_detail', pk=pk)

    if request.method == 'POST':
        form = ApprovalForm(request.POST, instance=fichier)
        if form.is_valid():
            fichier = form.save(commit=False)
            if fichier.est_valide:
                fichier.status = 'approved'
                fichier.approuve_par = request.user
                fichier.date_approbation = timezone.now()
                action = "approve"
                msg = "approuvé"
            else:
                fichier.status = 'error'
                action = "reject"
                msg = "rejeté"

            fichier.save()

            log_user_action(
                user=request.user,
                action=action,
                feature="Validation fichiers",
                target=fichier.type_fichier,
                resource_id=str(fichier.id),
                new_value=form.cleaned_data.get('commentaire', '')
            )

            messages.success(request, f"Fichier {msg} avec succès.")
            return redirect('uploads:file_detail', pk=pk)
    else:
        form = ApprovalForm(instance=fichier)

    return render(request, 'uploads/approve_form.html', {
        'form': form,
        'fichier': fichier
    })


@login_required
def delete_file(request, pk):
    """Supprimer un fichier"""
    fichier = get_object_or_404(FichierImporte, pk=pk)

    if not fichier.peut_etre_modifie_par(request.user):
        messages.error(request, "Vous ne pouvez pas supprimer ce fichier.")
        return redirect('uploads:file_detail', pk=pk)

    if request.method == 'POST':
        nom_fichier = fichier.nom_fichier

        log_user_action(
            user=request.user,
            action="delete",
            feature="Gestion fichiers",
            target=fichier.type_fichier,
            resource_id=str(fichier.id),
            old_value=nom_fichier
        )

        fichier.delete()
        messages.success(request, f"Fichier '{nom_fichier}' supprimé avec succès.")
        return redirect('uploads:upload_list')

    return render(request, 'uploads/confirm_delete.html', {'fichier': fichier})


# ==================== VUES AJAX ====================

@login_required
@require_http_methods(["GET"])
def preview_data(request, pk):
    """API pour récupérer les données de prévisualisation"""
    fichier = get_object_or_404(FichierImporte, pk=pk)

    if not fichier.peut_etre_modifie_par(request.user) and not request.user.is_admin():
        return JsonResponse({'error': 'Permission refusée'}, status=403)

    # Vérification avec hasattr ✅
    if not hasattr(fichier, 'preview') or not fichier.preview:
        return JsonResponse({'error': 'Aucun aperçu disponible'}, status=404)

    try:
        preview = fichier.preview
        nb_lignes = int(request.GET.get('nb_lignes', 10))

        data = {
            'colonnes': preview.colonnes,
            'donnees': preview.get_sample_data(nb_lignes),
            'nb_total_lignes': preview.nb_total_lignes,
            'status': fichier.status
        }

        return JsonResponse(data)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def mapping_columns(request, pk):
    """Gérer le mapping des colonnes"""
    fichier = get_object_or_404(FichierImporte, pk=pk)

    if not fichier.peut_etre_modifie_par(request.user):
        return JsonResponse({'error': 'Permission refusée'}, status=403)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            mappings_data = data.get('mappings', {})

            # Supprimer les anciens mappings
            fichier.mappings.all().delete()

            # Créer les nouveaux mappings
            for colonne_attendue, colonne_fichier in mappings_data.items():
                if colonne_fichier:  # Ne créer que si une colonne est sélectionnée
                    MappingColonne.objects.create(
                        fichier=fichier,
                        colonne_fichier=colonne_fichier,
                        colonne_attendue=colonne_attendue,
                        est_confirme=True
                    )

            log_user_action(
                user=request.user,
                action="mapping",
                feature="Mapping colonnes",
                target=fichier.type_fichier,
                resource_id=str(fichier.id),
                new_value=f"{len(mappings_data)} mappings créés"
            )

            return JsonResponse({'success': True, 'message': 'Mappings sauvegardés'})

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    else:
        # GET - Récupérer les mappings actuels
        mappings = {}
        for mapping in fichier.mappings.all():
            mappings[mapping.colonne_attendue] = mapping.colonne_fichier

        # Proposer un mapping automatique si aucun mapping n'existe
        if not mappings:
            mappings = FileProcessor.proposer_mapping_colonnes(fichier)

        colonnes_obligatoires = {
            'paie': ['matricule', 'nom', 'prenom', 'salaire_brut'],
            'liste_personnel': ['matricule', 'nom', 'prenom', 'poste'],
            'grille': ['poste', 'niveau', 'salaire_min', 'salaire_max'],
            'convention': ['type_prime', 'montant', 'condition'],
            'procedure': ['regle', 'description']
        }

        return JsonResponse({
            'mappings': mappings,
            'colonnes_fichier': fichier.colonnes_detectees,
            'colonnes_obligatoires': colonnes_obligatoires.get(fichier.type_fichier, [])
        })


# ==================== STATISTIQUES ====================

@login_required
def upload_stats(request):
    """Statistiques des uploads pour les admins"""
    if not request.user.is_admin():
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('uploads:upload_list')

    # Statistiques générales
    stats = {
        'total_fichiers': FichierImporte.objects.count(),
        'fichiers_par_type': {},
        'fichiers_par_status': {},
        'fichiers_par_mission': {},
        'uploads_recents': FichierImporte.objects.order_by('-date_import')[:10]
    }

    # Répartition par type
    for type_code, type_label in FichierImporte.TYPES_FICHIER:
        count = FichierImporte.objects.filter(type_fichier=type_code).count()
        stats['fichiers_par_type'][type_label] = count

    # Répartition par statut
    for status_code, status_label in FichierImporte.STATUS_CHOICES:
        count = FichierImporte.objects.filter(status=status_code).count()
        stats['fichiers_par_status'][status_label] = count

    # Répartition par mission - VERSION SIMPLE ET ROBUSTE
    missions_count = {}
    for fichier in FichierImporte.objects.select_related('mission'):
        mission_name = fichier.get_mission_display()
        missions_count[mission_name] = missions_count.get(mission_name, 0) + 1

    # Trier par count décroissant et prendre les 10 premiers
    sorted_missions = sorted(missions_count.items(), key=lambda x: x[1], reverse=True)[:10]
    stats['fichiers_par_mission'] = dict(sorted_missions)

    return render(request, 'uploads/upload_stats.html', {'stats': stats})


# ==================== VUES ADDITIONNELLES ====================

@login_required
def export_file_data(request, pk):
    """Exporter les données d'un fichier"""
    fichier = get_object_or_404(FichierImporte, pk=pk)

    if not fichier.peut_etre_modifie_par(request.user) and not request.user.is_admin():
        return JsonResponse({'error': 'Permission refusée'}, status=403)

    format_export = request.GET.get('format', 'csv')
    page = int(request.GET.get('page', 0))
    size = int(request.GET.get('size', 100))

    try:
        df = FileProcessor.lire_fichier(fichier)

        # Pagination si demandée
        if size > 0:
            start_idx = page * size
            end_idx = start_idx + size
            df = df.iloc[start_idx:end_idx]

        # Export selon le format
        if format_export == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="{fichier.nom_fichier}_export.csv"'
            df.to_csv(response, index=False)

        elif format_export == 'excel':
            response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = f'attachment; filename="{fichier.nom_fichier}_export.xlsx"'
            df.to_excel(response, index=False)

        else:
            return JsonResponse({'error': 'Format non supporté'}, status=400)

        log_user_action(
            user=request.user,
            action="export",
            feature="Export données",
            target=fichier.type_fichier,
            resource_id=str(fichier.id),
            new_value=format_export
        )

        return response

    except Exception as e:
        logger.error(f"Erreur lors de l'export: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def file_history(request, pk):
    """Historique des actions sur un fichier"""
    fichier = get_object_or_404(FichierImporte, pk=pk)

    if not fichier.peut_etre_modifie_par(request.user) and not request.user.is_admin():
        messages.error(request, "Vous n'avez pas accès à cet historique.")
        return redirect('uploads:file_detail', pk=pk)

    # Récupérer les logs liés à ce fichier
    from accounts.models import UserLog
    logs = UserLog.objects.filter(
        resource_id=str(pk),
        feature__icontains='fichier'
    ).order_by('-timestamp')[:50]

    context = {
        'fichier': fichier,
        'logs': logs,
    }

    return render(request, 'uploads/file_history.html', context)


@login_required
def bulk_approve(request):
    """Approbation en lot des fichiers (admin ou propriétaire des fichiers)"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            file_ids = data.get('file_ids', [])
            action = data.get('action', 'approve')  # approve ou reject

            # Filtrer les fichiers selon les permissions
            if request.user.is_admin():
                fichiers = FichierImporte.objects.filter(id__in=file_ids)
            else:
                # Utilisateur normal ne peut approuver que ses propres fichiers
                fichiers = FichierImporte.objects.filter(id__in=file_ids, utilisateur=request.user)

            updated_count = 0
            for fichier in fichiers:
                if action == 'approve':
                    fichier.est_valide = True
                    fichier.status = 'approved'
                    fichier.approuve_par = request.user
                    fichier.date_approbation = timezone.now()
                else:
                    fichier.est_valide = False
                    fichier.status = 'error'

                fichier.save()
                updated_count += 1

                log_user_action(
                    user=request.user,
                    action=f"bulk_{action}",
                    feature="Validation en lot",
                    target=fichier.type_fichier,
                    resource_id=str(fichier.id)
                )

            return JsonResponse({
                'success': True,
                'message': f'{updated_count} fichiers mis à jour',
                'updated_count': updated_count
            })

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    # GET - Afficher la page de validation en lot
    if request.user.is_admin():
        fichiers_pending = FichierImporte.objects.filter(status='processed')
    else:
        fichiers_pending = FichierImporte.objects.filter(status='processed', utilisateur=request.user)

    context = {
        'fichiers_pending': fichiers_pending,
    }

    return render(request, 'uploads/bulk_approve.html', context)


@login_required
def download_file(request, pk):
    """Téléchargement direct du fichier original"""
    fichier = get_object_or_404(FichierImporte, pk=pk)

    if not fichier.peut_etre_modifie_par(request.user) and not request.user.is_admin():
        messages.error(request, "Vous n'avez pas accès à ce fichier.")
        return redirect('uploads:upload_list')

    try:
        if fichier.fichier and fichier.fichier.storage.exists(fichier.fichier.name):
            response = HttpResponse(
                fichier.fichier.read(),
                content_type='application/octet-stream'
            )
            response['Content-Disposition'] = f'attachment; filename="{fichier.nom_original}"'

            log_user_action(
                user=request.user,
                action="download",
                feature="Téléchargement fichier",
                target=fichier.type_fichier,
                resource_id=str(fichier.id)
            )

            return response
        else:
            messages.error(request, "Fichier non trouvé sur le serveur.")
            return redirect('uploads:file_detail', pk=pk)

    except Exception as e:
        logger.error(f"Erreur lors du téléchargement: {str(e)}")
        messages.error(request, "Erreur lors du téléchargement du fichier.")
        return redirect('uploads:file_detail', pk=pk)


# ==================== VUES D'ADMINISTRATION ====================

@login_required
def cleanup_files(request):
    """Nettoyage des fichiers orphelins (admin seulement)"""
    if not request.user.is_admin():
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('uploads:upload_list')

    if request.method == 'POST':
        try:
            # Supprimer les PreviewData orphelins
            from django.db.models import Q
            orphaned_previews = PreviewData.objects.filter(
                Q(fichier__isnull=True) | Q(fichier__status='error')
            )
            deleted_previews = orphaned_previews.count()
            orphaned_previews.delete()

            # Supprimer les MappingColonne orphelins
            orphaned_mappings = MappingColonne.objects.filter(fichier__isnull=True)
            deleted_mappings = orphaned_mappings.count()
            orphaned_mappings.delete()

            # Supprimer les fichiers sans référence en base
            from django.conf import settings

            media_files = []
            upload_dir = os.path.join(settings.MEDIA_ROOT, 'uploads')
            if os.path.exists(upload_dir):
                for root, dirs, files in os.walk(upload_dir):
                    for file in files:
                        media_files.append(os.path.join(root, file))

            # Fichiers référencés en base
            db_files = set()
            for fichier in FichierImporte.objects.all():
                if fichier.fichier:
                    db_files.add(os.path.join(settings.MEDIA_ROOT, fichier.fichier.name))

            # Fichiers orphelins
            orphaned_files = [f for f in media_files if f not in db_files]
            deleted_files = 0

            for file_path in orphaned_files:
                try:
                    os.remove(file_path)
                    deleted_files += 1
                except OSError:
                    pass

            log_user_action(
                user=request.user,
                action="cleanup",
                feature="Nettoyage système",
                target="fichiers_orphelins",
                new_value=f"Previews: {deleted_previews}, Mappings: {deleted_mappings}, Fichiers: {deleted_files}"
            )

            messages.success(
                request,
                f"Nettoyage terminé: {deleted_previews} aperçus, {deleted_mappings} mappings, {deleted_files} fichiers supprimés"
            )

        except Exception as e:
            logger.error(f"Erreur lors du nettoyage: {str(e)}")
            messages.error(request, f"Erreur lors du nettoyage: {str(e)}")

    # Statistiques de nettoyage
    stats = {
        'orphaned_previews': PreviewData.objects.filter(fichier__isnull=True).count(),
        'orphaned_mappings': MappingColonne.objects.filter(fichier__isnull=True).count(),
        'error_files': FichierImporte.objects.filter(status='error').count(),
    }

    return render(request, 'uploads/cleanup.html', {'stats': stats})


@login_required
def storage_report(request):
    """Rapport d'utilisation de l'espace de stockage (admin seulement)"""
    if not request.user.is_admin():
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('uploads:upload_list')

    # Calcul de l'utilisation de l'espace
    total_size = 0
    file_count = 0
    size_by_type = {}
    size_by_user = {}

    for fichier in FichierImporte.objects.all():
        total_size += fichier.taille_fichier
        file_count += 1

        # Par type
        type_display = fichier.get_type_fichier_display()
        size_by_type[type_display] = size_by_type.get(type_display, 0) + fichier.taille_fichier

        # Par utilisateur
        username = fichier.utilisateur.username
        size_by_user[username] = size_by_user.get(username, 0) + fichier.taille_fichier

    # Conversion en MB
    total_size_mb = round(total_size / (1024 * 1024), 2)
    size_by_type_mb = {k: round(v / (1024 * 1024), 2) for k, v in size_by_type.items()}
    size_by_user_mb = {k: round(v / (1024 * 1024), 2) for k, v in size_by_user.items()}

    # Tri par taille décroissante
    size_by_type_sorted = dict(sorted(size_by_type_mb.items(), key=lambda x: x[1], reverse=True))
    size_by_user_sorted = dict(sorted(size_by_user_mb.items(), key=lambda x: x[1], reverse=True))

    context = {
        'total_size_mb': total_size_mb,
        'file_count': file_count,
        'avg_size_mb': round(total_size_mb / file_count, 2) if file_count > 0 else 0,
        'size_by_type': size_by_type_sorted,
        'size_by_user': size_by_user_sorted,
    }

    return render(request, 'uploads/storage_report.html', context)


@login_required
def migrate_files(request):
    """Migration des fichiers vers une nouvelle structure (admin seulement)"""
    if not request.user.is_admin():
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('uploads:upload_list')

    if request.method == 'POST':
        try:
            migrated_count = 0
            error_count = 0

            for fichier in FichierImporte.objects.all():
                try:
                    # Réorganiser le fichier selon la nouvelle structure
                    if hasattr(fichier, '_reorganize_file'):
                        fichier._reorganize_file()
                        migrated_count += 1
                except Exception as e:
                    logger.error(f"Erreur migration fichier {fichier.id}: {str(e)}")
                    error_count += 1

            log_user_action(
                user=request.user,
                action="migrate",
                feature="Migration fichiers",
                target="structure",
                new_value=f"Réussis: {migrated_count}, Erreurs: {error_count}"
            )

            if error_count == 0:
                messages.success(request, f"Migration terminée: {migrated_count} fichiers migrés")
            else:
                messages.warning(request,
                                 f"Migration terminée avec {error_count} erreurs: {migrated_count} fichiers migrés")

        except Exception as e:
            logger.error(f"Erreur lors de la migration: {str(e)}")
            messages.error(request, f"Erreur lors de la migration: {str(e)}")

    return render(request, 'uploads/migrate.html')


def _valider_fichier_temporaire(fichier_temp):
    """Vérifie que le chemin fourni pointe bien vers un fichier sous media/tmp_uploads/.

    fichier_temp arrive dans un champ de formulaire (POST) donc entièrement
    contrôlable par le client : sans cette vérification, un utilisateur pouvait
    faire lire/copier puis supprimer n'importe quel fichier accessible au
    processus Django (ex: db.sqlite3, settings.py) via replace_file/increment_version.
    """
    from django.conf import settings
    tmp_dir = os.path.realpath(os.path.join(settings.MEDIA_ROOT, 'tmp_uploads'))
    chemin_reel = os.path.realpath(fichier_temp)
    if os.path.commonpath([tmp_dir, chemin_reel]) != tmp_dir or not os.path.isfile(chemin_reel):
        raise ValueError("Chemin de fichier temporaire invalide")
    return chemin_reel


def _valider_acces_mission(request, mission):
    """Vérifie que l'utilisateur a le droit d'agir sur cette mission (admin ou
    membre de la mission) — nécessaire car mission_id vient d'un champ POST."""
    if request.user.is_admin():
        return True
    return request.user.mission_id == mission.id


@login_required
def replace_file(request):
    if request.method == 'POST':
        mission_id = request.POST['mission_id']
        type_fichier = request.POST['type_fichier']
        version = int(request.POST['version'])
        nom_fichier = request.POST.get('nom_fichier', '')

        from accounts.models import Mission
        mission = get_object_or_404(Mission, pk=mission_id)
        if not _valider_acces_mission(request, mission):
            messages.error(request, "Vous n'avez pas accès à cette mission.")
            return redirect('uploads:upload_file')

        try:
            fichier_temp = _valider_fichier_temporaire(request.POST['fichier'])
        except ValueError:
            messages.error(request, "Fichier temporaire invalide ou expiré.")
            return redirect('uploads:upload_file')

        # Supprimer l'ancien fichier
        FichierImporte.objects.filter(mission_id=mission_id, type_fichier=type_fichier, version=version).delete()
        # Créer le nouveau fichier
        with open(fichier_temp, 'rb') as f:
            from django.core.files.base import ContentFile
            file_content = ContentFile(f.read(), name=nom_fichier or fichier_temp.split('/')[-1])
        # Créer l'objet
        fichier = FichierImporte(
            mission=mission,
            type_fichier=type_fichier,
            version=version,
            nom_fichier=nom_fichier or fichier_temp.split('/')[-1],
            utilisateur=request.user
        )
        fichier.fichier.save(nom_fichier or fichier_temp.split('/')[-1], file_content, save=True)
        # Nettoyer le fichier temporaire
        try:
            os.remove(fichier_temp)
        except Exception:
            pass
        # Analyse automatique
        FileProcessor.analyser_fichier(fichier)
        return redirect('uploads:file_detail', pk=fichier.pk)
    return redirect('uploads:upload_file')


@login_required
def increment_version(request):
    if request.method == 'POST':
        mission_id = request.POST['mission_id']
        type_fichier = request.POST['type_fichier']
        nom_fichier = request.POST.get('nom_fichier', '')

        from accounts.models import Mission
        mission = get_object_or_404(Mission, pk=mission_id)
        if not _valider_acces_mission(request, mission):
            messages.error(request, "Vous n'avez pas accès à cette mission.")
            return redirect('uploads:upload_file')

        try:
            fichier_temp = _valider_fichier_temporaire(request.POST['fichier'])
        except ValueError:
            messages.error(request, "Fichier temporaire invalide ou expiré.")
            return redirect('uploads:upload_file')

        # Calculer la version suivante
        max_version = FichierImporte.objects.filter(mission_id=mission_id, type_fichier=type_fichier).order_by('-version').first()
        version_suivante = max_version.version + 1 if max_version else 1
        # Créer le nouveau fichier
        with open(fichier_temp, 'rb') as f:
            from django.core.files.base import ContentFile
            file_content = ContentFile(f.read(), name=nom_fichier or fichier_temp.split('/')[-1])
        fichier = FichierImporte(
            mission=mission,
            type_fichier=type_fichier,
            version=version_suivante,
            nom_fichier=nom_fichier or fichier_temp.split('/')[-1],
            utilisateur=request.user
        )
        fichier.fichier.save(nom_fichier or fichier_temp.split('/')[-1], file_content, save=True)
        # Nettoyer le fichier temporaire
        try:
            os.remove(fichier_temp)
        except Exception:
            pass
        # Analyse automatique
        FileProcessor.analyser_fichier(fichier)
        return redirect('uploads:file_detail', pk=fichier.pk)
    return redirect('uploads:upload_file')