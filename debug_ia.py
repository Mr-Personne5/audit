#!/usr/bin/env python
"""
Script de diagnostic pour l'IA
"""

import os
import sys
import django

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'audit_ia.settings')
django.setup()

from auditengine.models import SessionAudit
from uploads.models import FichierImporte
from auditengine.engine import AuditEngine

def diagnostic_ia():
    """Diagnostic complet du système IA"""
    
    print("=== DIAGNOSTIC IA ===\n")
    
    # 1. Vérifier les sessions IA existantes
    print("1. SESSIONS IA:")
    sessions = SessionAudit.objects.all()
    if not sessions.exists():
        print("   Aucune session IA trouvée")
        return
    
    for session in sessions:
        print(f"   Session {session.id}: {session.nom_session}")
        print(f"     Status: {session.status}")
        print(f"     Mission: {session.mission}")
        print(f"     Fichier: {session.fichier_paie.nom_fichier}")
        print(f"     Date création: {session.date_creation}")
        if session.date_traitement:
            print(f"     Date traitement: {session.date_traitement}")
        if session.date_completion:
            print(f"     Date completion: {session.date_completion}")
        if session.erreurs:
            print(f"     Erreurs: {session.erreurs}")
        print()
    
    # 2. Vérifier les fichiers disponibles
    print("2. FICHIERS DISPONIBLES:")
    fichiers_paie = FichierImporte.objects.filter(type_fichier='paie', status='approved')
    
    print(f"   Fichiers Paie approuvés: {fichiers_paie.count()}")
    for f in fichiers_paie:
        print(f"     - {f.nom_fichier} (ID: {f.id})")
    print()
    
    # 3. Tester le moteur IA
    print("3. TEST DU MOTEUR IA:")
    session_pending = sessions.filter(status='pending').first()
    if session_pending:
        print(f"   Test avec la session {session_pending.id}...")
        try:
            engine = AuditEngine(session_pending)
            
            # Test étape par étape
            print("   Étape 1: Chargement des données...")
            engine._charger_donnees()
            print(f"     Données chargées: {len(engine.df_data)} lignes")
            print(f"     Colonnes: {list(engine.df_data.columns)}")
            
            print("   Étape 2: Chargement des modèles...")
            engine._charger_modeles()
            print("     Modèles chargés avec succès")
            
            print("   Étape 3: Préparation des features...")
            engine._preparer_features()
            print(f"     Features IF: {engine.features_if.shape}")
            print(f"     Features MLP: {engine.features_mlp.shape}")
            
            if engine.features_if.empty:
                print("     ERREUR: Features IF vides!")
                print(f"     Colonnes disponibles: {list(engine.df_data.columns)}")
                print(f"     Colonnes attendues par IF: {list(engine.model_if.feature_names_in_) if hasattr(engine.model_if, 'feature_names_in_') else 'Non disponible'}")
            else:
                print("     Features préparées avec succès")
                
        except Exception as e:
            print(f"   Exception lors du test: {str(e)}")
    else:
        print("   Aucune session en attente pour le test")
    print()

if __name__ == "__main__":
    diagnostic_ia() 