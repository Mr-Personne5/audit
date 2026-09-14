# accounts/templatetags/custom_filters.py - VERSION CORRIGÉE
from django import template
from django.utils.http import urlencode

from django.core.exceptions import ValidationError
import json

register = template.Library()

@register.filter
def count_assigned_users(missions):
    """Compter le nombre total d'utilisateurs assignés aux missions"""
    try:
        total = 0
        for mission in missions:
            total += mission.customuser_set.count()
        return total
    except (AttributeError, TypeError):  # ✅ Exceptions spécifiques au lieu de except:
        return 0

@register.filter
def build_query_string(get_params):
    """Construire une query string pour la pagination avec les filtres"""
    try:
        params = get_params.copy()
        if 'page' in params:
            del params['page']
        if params:
            return '&' + urlencode(params)
        return ''
    except (AttributeError, TypeError):  # ✅ Exceptions spécifiques
        return ''

@register.simple_tag
def get_user_initials(user):
    """Récupérer les initiales d'un utilisateur"""
    try:
        first = user.first_name[:1] if user.first_name else 'U'
        last = user.last_name[:1] if user.last_name else 'U'
        return f"{first}{last}".upper()
    except AttributeError:  # ✅ Exception spécifique
        return "UU"

@register.filter
def pprint(value):
    """Pretty print pour JSON dans les templates"""
    try:
        if isinstance(value, str):
            parsed = json.loads(value)
        else:
            parsed = value
        return json.dumps(parsed, indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):  # ✅ Exceptions spécifiques
        return str(value)

@register.filter
def mul(value, arg):
    """Multiplie la valeur par l'argument (usage : {{ value|mul:100 }})"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return ''
