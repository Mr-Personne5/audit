#!/usr/bin/env python
"""
Script de test pour vérifier les corrections de la logique de détection d'anomalies
"""

import os
import sys
import django
from decimal import Decimal

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'audit_ia.settings')
django.setup()

from auditengine.models import SessionAudit, ResultatAudit
from auditengine.engine import AuditEngine

def test_corrections_ia():
    """Teste les corrections apportées à la logique IA"""
    print("=== TEST DES CORRECTIONS IA ===\n")
    
    # Récupérer une session récente pour tester
    sessions = SessionAudit.objects.filter(status='completed').order_by('-date_completion')
    
    if not sessions.exists():
        print("Aucune session complétée trouvée pour le test")
        return
    
    session = sessions.first()
    print(f"Session de test: {session.nom_session} (ID: {session.id})")
    print(f"Fichier: {session.fichier_paie}")
    print(f"Date: {session.date_completion}")
    
    # Supprimer les anciens résultats pour retester
    print(f"\nSuppression des anciens résultats...")
    ResultatAudit.objects.filter(session=session).delete()
    
    # Réinitialiser les statistiques
    session.nb_lignes_analysees = 0
    session.nb_anomalies_detectees = 0
    session.nb_salaires_anormaux = 0
    session.nb_employes_fantomes = 0
    session.nb_primes_anormales = 0
    session.nb_heures_excessives = 0
    session.nb_rib_dupliques = 0
    session.nb_aucune_anomalie = 0
    session.status = 'pending'
    session.save()
    
    print("Relancement de l'audit IA...")
    
    try:
        # Relancer l'audit
        engine = AuditEngine(session)
        success = engine.executer_audit()
        
        if success:
            print("✅ Audit IA terminé avec succès")
            
            # Analyser les résultats
            resultats = session.resultats.all()
            total_resultats = resultats.count()
            anomalies_detectees = resultats.filter(est_anomalie=True).count()
            
            print(f"\nRésultats après correction:")
            print(f"  - Total résultats: {total_resultats}")
            print(f"  - Anomalies détectées: {anomalies_detectees}")
            print(f"  - Taux d'anomalies: {(anomalies_detectees/total_resultats*100):.2f}%")
            
            # Analyse par type
            types_detectes = {}
            for resultat in resultats:
                type_anom = resultat.type_anomalie
                types_detectes[type_anom] = types_detectes.get(type_anom, 0) + 1
            
            print(f"\nRépartition par type:")
            for type_anom, count in types_detectes.items():
                print(f"  - {type_anom}: {count} ({count/total_resultats*100:.1f}%)")
            
            # Vérifier la cohérence
            print(f"\nVérification de la cohérence:")
            print(f"  - est_anomalie=True avec type='aucune': {resultats.filter(est_anomalie=True, type_anomalie='aucune').count()}")
            print(f"  - est_anomalie=False avec type!='aucune': {resultats.filter(est_anomalie=False).exclude(type_anomalie='aucune').count()}")
            
            # Afficher quelques exemples d'anomalies
            anomalies = resultats.filter(est_anomalie=True)[:5]
            if anomalies.exists():
                print(f"\nExemples d'anomalies détectées:")
                for i, resultat in enumerate(anomalies):
                    print(f"  {i+1}. {resultat.nom} {resultat.prenom} (Mat: {resultat.matricule})")
                    print(f"     - Type: {resultat.get_type_anomalie_display()}")
                    print(f"     - Niveau: {resultat.get_niveau_risque_display()}")
                    print(f"     - Score IF: {resultat.score_anomalie_if:.3f}")
                    print(f"     - Score MLP: {resultat.score_classification_mlp:.3f}")
                    print(f"     - Recommandation: {resultat.recommandation_auto[:50]}...")
            
            # Statistiques de la session
            print(f"\nStatistiques de la session:")
            print(f"  - Lignes analysées: {session.nb_lignes_analysees}")
            print(f"  - Anomalies détectées: {session.nb_anomalies_detectees}")
            print(f"  - Salaires anormaux: {session.nb_salaires_anormaux}")
            print(f"  - Employés fantômes: {session.nb_employes_fantomes}")
            print(f"  - Primes anormales: {session.nb_primes_anormales}")
            print(f"  - Heures excessives: {session.nb_heures_excessives}")
            print(f"  - RIB dupliqués: {session.nb_rib_dupliques}")
            print(f"  - Aucune anomalie: {session.nb_aucune_anomalie}")
            
        else:
            print("❌ Échec de l'audit IA")
            
    except Exception as e:
        print(f"❌ Erreur lors de l'audit: {e}")
        import traceback
        traceback.print_exc()

def corriger_sessions_existantes():
    """Corrige les sessions existantes avec la nouvelle logique"""
    print("\n=== CORRECTION DES SESSIONS EXISTANTES ===\n")
    
    sessions = SessionAudit.objects.filter(status='completed')
    corrigees = 0
    
    for session in sessions:
        try:
            resultats = session.resultats.all()
            
            # Appliquer la nouvelle logique
            for resultat in resultats:
                # Une anomalie est détectée si Isolation Forest détecte ET le type n'est pas 'aucune'
                nouvelle_est_anomalie = (resultat.score_anomalie_if and 
                                       resultat.score_anomalie_if > 0 and
                                       resultat.type_anomalie != 'aucune')
                
                if resultat.est_anomalie != nouvelle_est_anomalie:
                    resultat.est_anomalie = nouvelle_est_anomalie
                    resultat.save()
            
            # Recalculer les statistiques
            session.nb_lignes_analysees = resultats.count()
            session.nb_anomalies_detectees = resultats.filter(est_anomalie=True).count()
            session.nb_salaires_anormaux = resultats.filter(type_anomalie='salaire_anormal').count()
            session.nb_employes_fantomes = resultats.filter(type_anomalie='ghost_employee').count()
            session.nb_primes_anormales = resultats.filter(type_anomalie='prime_anormale').count()
            session.nb_heures_excessives = resultats.filter(type_anomalie='heures_excessives').count()
            session.nb_rib_dupliques = resultats.filter(type_anomalie='duplicate_rib').count()
            session.nb_aucune_anomalie = resultats.filter(type_anomalie='aucune').count()
            
            session.save()
            corrigees += 1
            print(f"✅ Session {session.id} corrigée")
            
        except Exception as e:
            print(f"❌ Erreur lors de la correction de la session {session.id}: {e}")
    
    print(f"\n✅ {corrigees} sessions corrigées sur {sessions.count()}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "corriger":
        corriger_sessions_existantes()
    else:
        test_corrections_ia() 