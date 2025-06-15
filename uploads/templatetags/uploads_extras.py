from django import template

register = template.Library()

@register.filter
def dict_get(dictionary, key):
    """Récupère une valeur dans un dictionnaire à partir d'une clé"""
    if isinstance(dictionary, dict):
        return dictionary.get(key, '')
    return ''

@register.filter
def truncate_path(value, length=30):
    """Tronque un chemin de fichier"""
    if len(str(value)) > length:
        return '...' + str(value)[-(length-3):]
    return value

@register.filter
def file_icon(extension):
    """Retourne l'icône Bootstrap appropriée selon l'extension"""
    ext = str(extension).lower()
    if ext in ['.csv']:
        return 'bi-file-earmark-text'
    elif ext in ['.xlsx', '.xls']:
        return 'bi-file-earmark-excel'
    elif ext in ['.pdf']:
        return 'bi-file-earmark-pdf'
    else:
        return 'bi-file-earmark'

@register.filter
def status_color(status):
    """Retourne la couleur Bootstrap selon le statut"""
    colors = {
        'pending': 'warning',
        'processing': 'primary',
        'processed': 'info',
        'approved': 'success',
        'error': 'danger'
    }
    return colors.get(status, 'secondary')
