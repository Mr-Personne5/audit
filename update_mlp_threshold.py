#!/usr/bin/env python
"""
Script pour mettre à jour le seuil MLP des configurations existantes
"""

import os
import sys
import django

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'audit_ia.settings')
django.setup()

from auditengine.models import ParametrageIA

def update_mlp_threshold():
    """Met à jour le seuil MLP des configurations existantes"""
    print("=== MISE À JOUR DU SEUIL MLP ===\n")
    
    # Récupérer toutes les configurations
    configs = ParametrageIA.objects.all()
    
    if not configs.exists():
        print("Aucune configuration trouvée")
        return
    
    print(f"Nombre de configurations: {configs.count()}")
    
    updated = 0
    for config in configs:
        print(f"\nConfiguration {config.id}:")
        print(f"  - Ancien seuil MLP: {config.score_minimum_classification}")
        
        # Mettre à jour si le seuil est trop élevé (> 0.7)
        if config.score_minimum_classification > 0.7:
            config.score_minimum_classification = 0.6
            config.save()
            print(f"  - Nouveau seuil MLP: {config.score_minimum_classification}")
            updated += 1
        else:
            print(f"  - Seuil déjà acceptable: {config.score_minimum_classification}")
    
    print(f"\n✅ {updated} configurations mises à jour sur {configs.count()}")

if __name__ == "__main__":
    update_mlp_threshold() 