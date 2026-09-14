// Mission Supervision Dashboard - JavaScript pour l'interface de supervision
class MissionSupervision {
    constructor() {
        this.currentMissionId = null;
        this.currentCategory = 'files';
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.loadInitialData();
        this.setupFilters();
    }

    // Configuration des écouteurs d'événements
    setupEventListeners() {
        // Onglets des catégories
        document.querySelectorAll('.category-tab').forEach(tab => {
            tab.addEventListener('click', (e) => {
                this.switchCategory(e.target.dataset.category);
            });
        });

        // Recherche en temps réel
        const searchInput = document.getElementById('search-input');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.filterItems(e.target.value);
            });
        }

        // Filtres
        document.getElementById('mission-filter')?.addEventListener('change', (e) => {
            this.filterByMission(e.target.value);
        });

        document.getElementById('status-filter')?.addEventListener('change', (e) => {
            this.filterByStatus(e.target.value);
        });

        document.getElementById('period-filter')?.addEventListener('change', (e) => {
            this.filterByPeriod(e.target.value);
        });
    }

    // Chargement initial des données
    async loadInitialData() {
        try {
            console.log('Chargement des données de supervision...');
            const response = await fetch('/accounts/api/mission_supervision_data/');
            const data = await response.json();
            console.log('Données reçues:', data);
            this.updateMissionStats(data.missions);
            this.updateProgressRings(data.missions);
            this.updateGlobalStats(data.global_stats);
            this.updateFilteredCount(); // Initialiser le compteur
        } catch (error) {
            console.error('Erreur lors du chargement des données:', error);
        }
    }

    // Mise à jour des statistiques des missions
    updateMissionStats(missions) {
        missions.forEach(mission => {
            // Fichiers
            const filesElement = document.getElementById(`files-${mission.id}`);
            const filesDetailElement = document.getElementById(`files-detail-${mission.id}`);
            if (filesElement) {
                filesElement.textContent = mission.files_count || 0;
            }
            if (filesDetailElement && mission.files_stats) {
                const processed = mission.files_stats.processed || 0;
                const total = mission.files_stats.total || 0;
                filesDetailElement.textContent = `${processed}/${total} traités`;
                
                // Couleur selon le taux de succès
                if (total > 0) {
                    const successRate = (processed / total) * 100;
                    if (successRate >= 80) {
                        filesDetailElement.className = 'stat-detail text-success';
                    } else if (successRate >= 50) {
                        filesDetailElement.className = 'stat-detail text-warning';
                    } else {
                        filesDetailElement.className = 'stat-detail text-danger';
                    }
                }
            }

            // Analyses
            const analysesElement = document.getElementById(`analyses-${mission.id}`);
            const analysesDetailElement = document.getElementById(`analyses-detail-${mission.id}`);
            if (analysesElement) {
                analysesElement.textContent = mission.analyses_count || 0;
            }
            if (analysesDetailElement && mission.analyses_stats) {
                const completed = mission.analyses_stats.completed || 0;
                const total = mission.analyses_stats.total || 0;
                analysesDetailElement.textContent = `${completed}/${total} terminées`;
                
                // Couleur selon le taux de succès
                if (total > 0) {
                    const successRate = (completed / total) * 100;
                    if (successRate >= 80) {
                        analysesDetailElement.className = 'stat-detail text-success';
                    } else if (successRate >= 50) {
                        analysesDetailElement.className = 'stat-detail text-warning';
                    } else {
                        analysesDetailElement.className = 'stat-detail text-danger';
                    }
                }
            }

            // Rapprochements
            const reconciliationsElement = document.getElementById(`reconciliations-${mission.id}`);
            const reconciliationsDetailElement = document.getElementById(`reconciliations-detail-${mission.id}`);
            if (reconciliationsElement) {
                reconciliationsElement.textContent = mission.reconciliations_count || 0;
            }
            if (reconciliationsDetailElement && mission.reconciliations_stats) {
                const completed = mission.reconciliations_stats.completed || 0;
                const total = mission.reconciliations_stats.total || 0;
                reconciliationsDetailElement.textContent = `${completed}/${total} terminés`;
                
                // Couleur selon le taux de succès
                if (total > 0) {
                    const successRate = (completed / total) * 100;
                    if (successRate >= 80) {
                        reconciliationsDetailElement.className = 'stat-detail text-success';
                    } else if (successRate >= 50) {
                        reconciliationsDetailElement.className = 'stat-detail text-warning';
                    } else {
                        reconciliationsDetailElement.className = 'stat-detail text-danger';
                    }
                }
            }

            // Anomalies
            const anomaliesElement = document.getElementById(`anomalies-${mission.id}`);
            const anomaliesDetailElement = document.getElementById(`anomalies-detail-${mission.id}`);
            if (anomaliesElement) {
                anomaliesElement.textContent = mission.anomalies_count || 0;
            }
            if (anomaliesDetailElement) {
                anomaliesDetailElement.textContent = 'détectées';
                if (mission.anomalies_count > 0) {
                    anomaliesDetailElement.className = 'stat-detail text-warning';
                } else {
                    anomaliesDetailElement.className = 'stat-detail text-success';
                }
            }
        });
    }

    // Mise à jour des anneaux de progression
    updateProgressRings(missions) {
        missions.forEach(mission => {
            const progressElement = document.getElementById(`progress-${mission.id}`);
            if (progressElement) {
                const progress = mission.progress || 0;
                const circumference = 2 * Math.PI * 26;
                const offset = circumference - (progress / 100) * circumference;
                progressElement.style.strokeDasharray = `${circumference} ${circumference}`;
                progressElement.style.strokeDashoffset = offset;
                
                // Couleur selon la progression
                if (progress >= 80) {
                    progressElement.style.stroke = '#198754'; // Vert
                } else if (progress >= 50) {
                    progressElement.style.stroke = '#ffc107'; // Jaune
                } else {
                    progressElement.style.stroke = '#dc3545'; // Rouge
                }
            }
        });
    }

    // Mise à jour des statistiques globales
    updateGlobalStats(globalStats) {
        if (!globalStats) return;
        
        const elements = {
            'total-missions': globalStats.total_missions,
            'total-files': globalStats.total_files,
            'total-analyses': globalStats.total_analyses,
            'total-reconciliations': globalStats.total_reconciliations,
            'total-anomalies': globalStats.total_anomalies,
            'average-progress': `${globalStats.average_progress}%`
        };
        
        Object.entries(elements).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = value;
            }
        });
    }

    // Affichage des détails d'une mission
    async viewMissionDetails(missionId) {
        this.currentMissionId = missionId;
        
        try {
            const response = await fetch(`/accounts/api/mission_details/${missionId}/`);
            const data = await response.json();
            
            // Mise à jour du header
            document.getElementById('selected-mission-name').textContent = data.mission.name;
            document.getElementById('selected-mission-client').textContent = data.mission.client || 'Client non spécifié';
            
            // Affichage de la section détails
            document.getElementById('mission-details').style.display = 'block';
            
            // Chargement du contenu de la catégorie active
            this.loadCategoryContent(this.currentCategory);
            
            // Scroll vers les détails
            document.getElementById('mission-details').scrollIntoView({ behavior: 'smooth' });
            
        } catch (error) {
            console.error('Erreur lors du chargement des détails:', error);
        }
    }

    // Changement de catégorie
    switchCategory(category) {
        this.currentCategory = category;
        
        // Mise à jour des onglets
        document.querySelectorAll('.category-tab').forEach(tab => {
            tab.classList.remove('active');
        });
        document.querySelector(`[data-category="${category}"]`).classList.add('active');
        
        // Chargement du contenu
        this.loadCategoryContent(category);
    }

    // Chargement du contenu d'une catégorie
    async loadCategoryContent(category) {
        if (!this.currentMissionId) return;
        
        const contentContainer = document.getElementById('category-content');
        contentContainer.innerHTML = '<div class="text-center"><i class="bi bi-hourglass-split fs-2 text-muted"></i><p class="mt-2">Chargement...</p></div>';
        
        try {
            const response = await fetch(`/accounts/api/mission_category_data/${this.currentMissionId}/${category}/`);
            const data = await response.json();
            
            contentContainer.innerHTML = this.renderCategoryContent(category, data);
            
        } catch (error) {
            console.error('Erreur lors du chargement du contenu:', error);
            contentContainer.innerHTML = '<div class="alert alert-danger">Erreur lors du chargement des données</div>';
        }
    }

    // Rendu du contenu d'une catégorie
    renderCategoryContent(category, data) {
        switch (category) {
            case 'files':
                return this.renderFilesContent(data.files);
            case 'analyses':
                return this.renderAnalysesContent(data.analyses);
            case 'reconciliations':
                return this.renderReconciliationsContent(data.reconciliations);
            case 'recommendations':
                return this.renderRecommendationsContent(data.recommendations);
            case 'logs':
                return this.renderLogsContent(data.logs);
            default:
                return '<div class="alert alert-warning">Catégorie non reconnue</div>';
        }
    }

    // Rendu des fichiers
    renderFilesContent(files) {
        if (!files || files.length === 0) {
            return '<div class="text-center text-muted"><i class="bi bi-file-earmark-text fs-1"></i><p class="mt-2">Aucun fichier importé</p></div>';
        }

        return `
            <div class="items-grid">
                ${files.map(file => `
                    <div class="item-card">
                        <div class="d-flex justify-content-between align-items-start mb-2">
                            <h6 class="mb-1">${file.nom_fichier}</h6>
                            <span class="status-badge status-${file.status}">${this.getStatusLabel(file.status)}</span>
                        </div>
                        <p class="text-muted small mb-2">${file.description || 'Aucune description'}</p>
                        <div class="d-flex justify-content-between align-items-center">
                            <small class="text-muted">
                                <i class="bi bi-person me-1"></i>${file.utilisateur.get_full_name}
                            </small>
                            <small class="text-muted">
                                <i class="bi bi-calendar me-1"></i>${new Date(file.date_import).toLocaleDateString()}
                            </small>
                        </div>
                        <div class="mt-2">
                            <button class="btn btn-sm btn-outline-primary" onclick="downloadFile(${file.id})">
                                <i class="bi bi-download me-1"></i>Télécharger
                            </button>
                            <button class="btn btn-sm btn-outline-info" onclick="viewFileDetails(${file.id})">
                                <i class="bi bi-eye me-1"></i>Détails
                            </button>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    }

    // Rendu des analyses
    renderAnalysesContent(analyses) {
        if (!analyses || analyses.length === 0) {
            return '<div class="text-center text-muted"><i class="bi bi-cpu fs-1"></i><p class="mt-2">Aucune analyse effectuée</p></div>';
        }

        return `
            <div class="items-grid">
                ${analyses.map(analysis => `
                    <div class="item-card">
                        <div class="d-flex justify-content-between align-items-start mb-2">
                            <h6 class="mb-1">Session ${analysis.id}</h6>
                            <span class="status-badge status-${analysis.status}">${this.getStatusLabel(analysis.status)}</span>
                        </div>
                        <p class="text-muted small mb-2">${analysis.description || 'Analyse IA'}</p>
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <small class="text-muted">
                                <i class="bi bi-person me-1"></i>${analysis.utilisateur.get_full_name}
                            </small>
                            <small class="text-muted">
                                <i class="bi bi-calendar me-1"></i>${new Date(analysis.date_creation).toLocaleDateString()}
                            </small>
                        </div>
                        <div class="d-flex justify-content-between align-items-center">
                            <div>
                                <small class="text-success">
                                    <i class="bi bi-check-circle me-1"></i>${analysis.anomalies_detectees} anomalies
                                </small>
                            </div>
                            <div>
                                <button class="btn btn-sm btn-outline-primary" onclick="viewAnalysisResults(${analysis.id})">
                                    <i class="bi bi-eye me-1"></i>Résultats
                                </button>
                            </div>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    }

    // Rendu des rapprochements
    renderReconciliationsContent(reconciliations) {
        if (!reconciliations || reconciliations.length === 0) {
            return '<div class="text-center text-muted"><i class="bi bi-arrow-left-right fs-1"></i><p class="mt-2">Aucun rapprochement effectué</p></div>';
        }

        return `
            <div class="items-grid">
                ${reconciliations.map(reconciliation => `
                    <div class="item-card">
                        <div class="d-flex justify-content-between align-items-start mb-2">
                            <h6 class="mb-1">Rapprochement ${reconciliation.id}</h6>
                            <span class="status-badge status-${reconciliation.status}">${this.getStatusLabel(reconciliation.status)}</span>
                        </div>
                        <p class="text-muted small mb-2">${reconciliation.description || 'Rapprochement de données'}</p>
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <small class="text-muted">
                                <i class="bi bi-person me-1"></i>${reconciliation.utilisateur.get_full_name}
                            </small>
                            <small class="text-muted">
                                <i class="bi bi-calendar me-1"></i>${new Date(reconciliation.date_creation).toLocaleDateString()}
                            </small>
                        </div>
                        <div class="d-flex justify-content-between align-items-center">
                            <div>
                                <small class="text-info">
                                    <i class="bi bi-percent me-1"></i>${reconciliation.taux_correspondance}% correspondance
                                </small>
                            </div>
                            <div>
                                <button class="btn btn-sm btn-outline-primary" onclick="viewReconciliationDetails(${reconciliation.id})">
                                    <i class="bi bi-eye me-1"></i>Détails
                                </button>
                            </div>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    }

    // Rendu des recommandations
    renderRecommendationsContent(recommendations) {
        if (!recommendations || recommendations.length === 0) {
            return '<div class="text-center text-muted"><i class="bi bi-lightbulb fs-1"></i><p class="mt-2">Aucune recommandation générée</p></div>';
        }

        return `
            <div class="items-grid">
                ${recommendations.map(recommendation => `
                    <div class="item-card">
                        <div class="d-flex justify-content-between align-items-start mb-2">
                            <h6 class="mb-1">Recommandation ${recommendation.id}</h6>
                            <span class="badge bg-${this.getPriorityColor(recommendation.priorite)}">${recommendation.priorite}</span>
                        </div>
                        <p class="text-muted small mb-2">${recommendation.description}</p>
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <small class="text-muted">
                                <i class="bi bi-person me-1"></i>${recommendation.utilisateur.get_full_name}
                            </small>
                            <small class="text-muted">
                                <i class="bi bi-calendar me-1"></i>${new Date(recommendation.date_creation).toLocaleDateString()}
                            </small>
                        </div>
                        <div class="d-flex justify-content-between align-items-center">
                            <div>
                                <small class="text-warning">
                                    <i class="bi bi-exclamation-triangle me-1"></i>${recommendation.impact} impact
                                </small>
                            </div>
                            <div>
                                <button class="btn btn-sm btn-outline-primary" onclick="viewRecommendationDetails(${recommendation.id})">
                                    <i class="bi bi-eye me-1"></i>Détails
                                </button>
                            </div>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    }

    // Rendu des logs
    renderLogsContent(logs) {
        if (!logs || logs.length === 0) {
            return '<div class="text-center text-muted"><i class="bi bi-journal-text fs-1"></i><p class="mt-2">Aucun log d\'activité</p></div>';
        }

        return `
            <div class="table-responsive">
                <table class="table table-hover">
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Utilisateur</th>
                            <th>Action</th>
                            <th>Détails</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${logs.map(log => `
                            <tr>
                                <td><small>${new Date(log.timestamp).toLocaleString()}</small></td>
                                <td>${log.user.get_full_name}</td>
                                <td><span class="badge bg-secondary">${log.action}</span></td>
                                <td>${log.description}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
    }

    // Utilitaires
    getStatusLabel(status) {
        const labels = {
            'pending': 'En attente',
            'processing': 'En cours',
            'completed': 'Terminé',
            'error': 'Erreur'
        };
        return labels[status] || status;
    }

    getPriorityColor(priority) {
        const colors = {
            'high': 'danger',
            'medium': 'warning',
            'low': 'info'
        };
        return colors[priority] || 'secondary';
    }

    // Filtres
    setupFilters() {
        // Les filtres sont déjà configurés dans setupEventListeners()
        console.log('Filtres configurés');
    }

    filterItems(searchTerm) {
        const missionCards = document.querySelectorAll('.mission-card');
        
        missionCards.forEach(card => {
            const missionName = card.querySelector('h5').textContent.toLowerCase();
            const missionClient = card.querySelector('.opacity-75').textContent.toLowerCase();
            
            if (searchTerm === '' || 
                missionName.includes(searchTerm.toLowerCase()) || 
                missionClient.includes(searchTerm.toLowerCase())) {
                card.style.display = 'block';
            } else {
                card.style.display = 'none';
            }
        });
        
        this.updateFilteredCount();
    }

    filterByMission(missionId) {
        if (!missionId) {
            // Afficher toutes les missions
            document.querySelectorAll('.mission-card').forEach(card => {
                card.style.display = 'block';
            });
        } else {
            document.querySelectorAll('.mission-card').forEach(card => {
                const cardMissionId = card.dataset.missionId;
                if (cardMissionId === missionId) {
                    card.style.display = 'block';
                } else {
                    card.style.display = 'none';
                }
            });
        }
        
        this.updateFilteredCount();
    }

    filterByStatus(status) {
        if (!status) {
            // Afficher toutes les missions
            document.querySelectorAll('.mission-card').forEach(card => {
                card.style.display = 'block';
            });
        } else {
            document.querySelectorAll('.mission-card').forEach(card => {
                const badge = card.querySelector('.badge');
                const cardStatus = badge.textContent.toLowerCase();
                
                if (status === 'active' && cardStatus === 'active') {
                    card.style.display = 'block';
                } else if (status === 'completed' && cardStatus === 'inactive') {
                    card.style.display = 'block';
                } else if (status === 'pending') {
                    // Pour les missions en attente, on peut filtrer par progression
                    const progressElement = card.querySelector('.progress-ring circle.progress');
                    if (progressElement) {
                        const progress = this.getProgressFromElement(progressElement);
                        if (progress < 50) {
                            card.style.display = 'block';
                        } else {
                            card.style.display = 'none';
                        }
                    }
                } else {
                    card.style.display = 'none';
                }
            });
        }
        
        this.updateFilteredCount();
    }

    filterByPeriod(period) {
        if (!period || period === 'all') {
            // Afficher toutes les missions
            document.querySelectorAll('.mission-card').forEach(card => {
                card.style.display = 'block';
            });
        } else {
            const today = new Date();
            let startDate;

            switch (period) {
                case 'today':
                    startDate = new Date(today.getFullYear(), today.getMonth(), today.getDate());
                    break;
                case 'week':
                    startDate = new Date(today.getTime() - (7 * 24 * 60 * 60 * 1000));
                    break;
                case 'month':
                    startDate = new Date(today.getFullYear(), today.getMonth() - 1, today.getDate());
                    break;
                default:
                    startDate = new Date(0); // Toutes les dates
            }

            document.querySelectorAll('.mission-card').forEach(card => {
                const dateText = card.querySelector('small.text-muted').textContent;
                const missionDate = this.parseDateFromText(dateText);
                
                if (missionDate >= startDate) {
                    card.style.display = 'block';
                } else {
                    card.style.display = 'none';
                }
            });
        }
        
        this.updateFilteredCount();
    }

    // Utilitaires pour les filtres
    getProgressFromElement(progressElement) {
        const circumference = 2 * Math.PI * 26;
        const strokeDasharray = progressElement.style.strokeDasharray;
        if (strokeDasharray) {
            const values = strokeDasharray.split(' ');
            const progress = parseFloat(values[0]);
            return (progress / circumference) * 100;
        }
        return 0;
    }

    parseDateFromText(dateText) {
        // Extraire la date du texte "À partir du DD/MM/YYYY"
        const dateMatch = dateText.match(/(\d{2})\/(\d{2})\/(\d{4})/);
        if (dateMatch) {
            const [, day, month, year] = dateMatch;
            return new Date(year, month - 1, day);
        }
        return new Date(0);
    }

    // Mise à jour du compteur de missions filtrées
    updateFilteredCount() {
        const visibleCards = document.querySelectorAll('.mission-card[style*="display: block"], .mission-card:not([style*="display: none"])');
        const countElement = document.getElementById('filtered-count');
        if (countElement) {
            countElement.textContent = visibleCards.length;
        }
    }

    // Actions
    closeMissionDetails() {
        document.getElementById('mission-details').style.display = 'none';
        this.currentMissionId = null;
    }

    async exportData() {
        // Export des données
        console.log('Export des données...');
    }

    async exportMissionData(missionId) {
        // Export des données d'une mission spécifique
        console.log(`Export des données de la mission ${missionId}...`);
    }

    createNewMission() {
        window.location.href = '/accounts/missions/create/';
    }
}

// Fonctions globales pour les boutons
function viewMissionDetails(missionId) {
    window.missionSupervision.viewMissionDetails(missionId);
}

function closeMissionDetails() {
    window.missionSupervision.closeMissionDetails();
}

function refreshAllData() {
    window.missionSupervision.loadInitialData();
}

function exportData() {
    window.missionSupervision.exportData();
}

function exportMissionData(missionId) {
    window.missionSupervision.exportMissionData(missionId);
}

function createNewMission() {
    window.missionSupervision.createNewMission();
}

// Initialisation
document.addEventListener('DOMContentLoaded', function() {
    window.missionSupervision = new MissionSupervision();
}); 