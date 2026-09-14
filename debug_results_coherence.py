#!/usr/bin/env python
"""
Script de diagnostic pour vérifier la cohérence entre les résultats détectés et affichés
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

def diagnostic_coherence_resultats():
    """Diagnostique la cohérence entre détection et affichage"""
    print("=== DIAGNOSTIC COHÉRENCE RÉSULTATS ===\n")
    
    # Récupérer toutes les sessions complétées
    sessions = SessionAudit.objects.filter(status='completed').order_by('-date_completion')
    
    if not sessions.exists():
        print("Aucune session complétée trouvée")
        return
    
    print(f"Nombre de sessions complétées: {sessions.count()}\n")
    
    for session in sessions[:3]:  # Analyser les 3 dernières sessions
        print(f"--- SESSION: {session.nom_session} (ID: {session.id}) ---")
        print(f"Date: {session.date_completion}")
        print(f"Fichier: {session.fichier_paie}")
        
        # Statistiques de la session
        resultats = session.resultats.all()
        total_resultats = resultats.count()
        anomalies_detectees = resultats.filter(est_anomalie=True).count()
        
        print(f"\nStatistiques stockées en session:")
        print(f"  - Total lignes analysées: {session.nb_lignes_analysees}")
        print(f"  - Anomalies détectées: {session.nb_anomalies_detectees}")
        print(f"  - Salaires anormaux: {session.nb_salaires_anormaux}")
        print(f"  - Employés fantômes: {session.nb_employes_fantomes}")
        print(f"  - Primes anormales: {session.nb_primes_anormales}")
        print(f"  - Heures excessives: {session.nb_heures_excessives}")
        print(f"  - RIB dupliqués: {session.nb_rib_dupliques}")
        print(f"  - Aucune anomalie: {session.nb_aucune_anomalie}")
        
        print(f"\nStatistiques calculées depuis les résultats:")
        print(f"  - Total résultats: {total_resultats}")
        print(f"  - Anomalies détectées: {anomalies_detectees}")
        print(f"  - Salaires anormaux: {resultats.filter(type_anomalie='salaire_anormal').count()}")
        print(f"  - Employés fantômes: {resultats.filter(type_anomalie='ghost_employee').count()}")
        print(f"  - Primes anormales: {resultats.filter(type_anomalie='prime_anormale').count()}")
        print(f"  - Heures excessives: {resultats.filter(type_anomalie='heures_excessives').count()}")
        print(f"  - RIB dupliqués: {resultats.filter(type_anomalie='duplicate_rib').count()}")
        print(f"  - Aucune anomalie: {resultats.filter(type_anomalie='aucune').count()}")
        
        # Vérifier la cohérence
        incoherences = []
        if session.nb_lignes_analysees != total_resultats:
            incoherences.append(f"Lignes analysées: {session.nb_lignes_analysees} vs {total_resultats} résultats")
        if session.nb_anomalies_detectees != anomalies_detectees:
            incoherences.append(f"Anomalies détectées: {session.nb_anomalies_detectees} vs {anomalies_detectees} résultats")
        if session.nb_salaires_anormaux != resultats.filter(type_anomalie='salaire_anormal').count():
            incoherences.append("Salaires anormaux incohérents")
        if session.nb_employes_fantomes != resultats.filter(type_anomalie='ghost_employee').count():
            incoherences.append("Employés fantômes incohérents")
        if session.nb_primes_anormales != resultats.filter(type_anomalie='prime_anormale').count():
            incoherences.append("Primes anormales incohérents")
        if session.nb_heures_excessives != resultats.filter(type_anomalie='heures_excessives').count():
            incoherences.append("Heures excessives incohérentes")
        if session.nb_rib_dupliques != resultats.filter(type_anomalie='duplicate_rib').count():
            incoherences.append("RIB dupliqués incohérents")
        if session.nb_aucune_anomalie != resultats.filter(type_anomalie='aucune').count():
            incoherences.append("Aucune anomalie incohérente")
        
        if incoherences:
            print(f"\n❌ INCOHÉRENCES DÉTECTÉES:")
            for inc in incoherences:
                print(f"  - {inc}")
        else:
            print(f"\n✅ Aucune incohérence détectée")
        
        # Analyser quelques résultats détaillés
        print(f"\nAnalyse détaillée de quelques résultats:")
        anomalies = resultats.filter(est_anomalie=True)[:5]
        for i, resultat in enumerate(anomalies):
            print(f"  {i+1}. {resultat.nom} {resultat.prenom} (Mat: {resultat.matricule})")
            print(f"     - Type: {resultat.get_type_anomalie_display()}")
            print(f"     - Niveau: {resultat.get_niveau_risque_display()}")
            print(f"     - Score IF: {resultat.score_anomalie_if:.3f}")
            print(f"     - Score MLP: {resultat.score_classification_mlp:.3f}")
            print(f"     - Salaire brut: {resultat.salaire_brut}")
            print(f"     - Montant total: {resultat.montant_total}")
        
        print("\n" + "="*60 + "\n")

def corriger_statistiques_session(session_id):
    """Corrige les statistiques d'une session spécifique"""
    try:
        session = SessionAudit.objects.get(id=session_id)
        print(f"Correction des statistiques pour la session {session.nom_session}")
        
        # Recalculer les statistiques
        resultats = session.resultats.all()
        
        session.nb_lignes_analysees = resultats.count()
        session.nb_anomalies_detectees = resultats.filter(est_anomalie=True).count()
        session.nb_salaires_anormaux = resultats.filter(type_anomalie='salaire_anormal').count()
        session.nb_employes_fantomes = resultats.filter(type_anomalie='ghost_employee').count()
        session.nb_primes_anormales = resultats.filter(type_anomalie='prime_anormale').count()
        session.nb_heures_excessives = resultats.filter(type_anomalie='heures_excessives').count()
        session.nb_rib_dupliques = resultats.filter(type_anomalie='duplicate_rib').count()
        session.nb_aucune_anomalie = resultats.filter(type_anomalie='aucune').count()
        
        session.save()
        print("✅ Statistiques corrigées avec succès")
        
    except SessionAudit.DoesNotExist:
        print(f"❌ Session {session_id} non trouvée")

def corriger_toutes_statistiques():
    """Corrige les statistiques de toutes les sessions"""
    print("=== CORRECTION DE TOUTES LES STATISTIQUES ===\n")
    
    sessions = SessionAudit.objects.filter(status='completed')
    corrigees = 0
    
    for session in sessions:
        try:
            resultats = session.resultats.all()
            
            # Vérifier si correction nécessaire
            if (session.nb_lignes_analysees != resultats.count() or
                session.nb_anomalies_detectees != resultats.filter(est_anomalie=True).count()):
                
                print(f"Correction session {session.id}: {session.nom_session}")
                
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
                
        except Exception as e:
            print(f"❌ Erreur lors de la correction de la session {session.id}: {e}")
    
    print(f"\n✅ {corrigees} sessions corrigées sur {sessions.count()}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "corriger":
            if len(sys.argv) > 2:
                corriger_statistiques_session(int(sys.argv[2]))
            else:
                corriger_toutes_statistiques()
        else:
            print("Usage: python debug_results_coherence.py [corriger [session_id]]")
    else:
        diagnostic_coherence_resultats() 