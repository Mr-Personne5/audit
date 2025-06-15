from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta, datetime
from typing import Dict, Any

from .models import CustomUser, Mission, UserLog
from .forms import CustomUserCreationForm, CustomUserChangeForm, MissionForm
from .utils import log_user_action, log_authentication


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


# === DASHBOARD VIEWS ===
@login_required
def dashboard(request):
    user = request.user
    user.update_last_activity()

    context = {
        'user': user,
        'current_mission': user.mission
    }

    template = 'accounts/dashboard_admin.html' if user.is_admin() else 'accounts/dashboard_user.html'

    log_user_action(user, "consultation", "Dashboard", request=request)
    return render(request, template, context)


# === USER MANAGEMENT VIEWS ===
@login_required
@user_passes_test(is_admin)
def user_list(request):
    users = CustomUser.objects.select_related('mission').all()
    search = request.GET.get('search', '')
    role_filter = request.GET.get('role', '')

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
        'role_filter': role_filter
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
    return render(request, 'accounts/mission_list.html', {
        'missions': missions,
        'today': timezone.now().date()
    })


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