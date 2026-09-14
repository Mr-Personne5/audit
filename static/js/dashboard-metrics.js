// Dashboard Metrics - Métriques dynamiques pour le tableau de bord
class DashboardMetrics {
    constructor() {
        this.metrics = {};
        this.updateInterval = 30000; // 30 secondes
        this.charts = {};
        this.init();
    }

    init() {
        this.loadInitialMetrics();
        this.setupAutoRefresh();
        this.setupEventListeners();
    }

    // Chargement initial des métriques
    async loadInitialMetrics() {
        try {
            const response = await fetch('/accounts/api/dashboard_advanced_metrics/');
            const data = await response.json();
            this.updateMetricsDisplay(data);
            this.animateCounters();
        } catch (error) {
            console.error('Erreur lors du chargement des métriques:', error);
        }
    }

    // Mise à jour automatique des métriques
    setupAutoRefresh() {
        setInterval(() => {
            this.refreshMetrics();
        }, this.updateInterval);
    }

    // Rafraîchissement des métriques
    async refreshMetrics() {
        try {
            const response = await fetch('/accounts/api/dashboard_advanced_metrics/');
            const data = await response.json();
            this.updateMetricsDisplay(data);
        } catch (error) {
            console.error('Erreur lors du rafraîchissement:', error);
        }
    }

    // Mise à jour de l'affichage des métriques
    updateMetricsDisplay(data) {
        // Métriques principales
        this.updateMetric('total-anomalies', data.total_anomalies);
        this.updateMetric('detection-rate', data.detection_rate);
        this.updateMetric('accuracy-rate', data.accuracy_rate);
        this.updateMetric('active-missions', data.active_missions);
        this.updateMetric('pending-approvals', data.pending_approvals);
        this.updateMetric('today-actions', data.today_actions);

        // Tendances
        this.updateTrend('anomalies-trend', data.anomalies_trend);
        this.updateTrend('detection-trend', data.detection_trend);

        // Alertes
        this.updateAlerts(data.alerts);

        // Statuts des missions
        this.updateMissionStatus(data.mission_status);
    }

    // Mise à jour d'une métrique spécifique
    updateMetric(elementId, value) {
        const element = document.getElementById(elementId);
        if (element) {
            const currentValue = parseInt(element.textContent) || 0;
            this.animateValue(element, currentValue, value);
        }
    }

    // Animation des compteurs
    animateValue(element, start, end) {
        const duration = 1000;
        const startTime = performance.now();
        
        const animate = (currentTime) => {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            
            const current = Math.floor(start + (end - start) * this.easeOutQuart(progress));
            element.textContent = current.toLocaleString();
            
            if (progress < 1) {
                requestAnimationFrame(animate);
            }
        };
        
        requestAnimationFrame(animate);
    }

    // Fonction d'easing pour animation fluide
    easeOutQuart(t) {
        return 1 - Math.pow(1 - t, 4);
    }

    // Animation des compteurs au chargement
    animateCounters() {
        const counters = document.querySelectorAll('.metric-counter');
        counters.forEach(counter => {
            const target = parseInt(counter.getAttribute('data-target')) || 0;
            this.animateValue(counter, 0, target);
        });
    }

    // Mise à jour des tendances
    updateTrend(elementId, trend) {
        const element = document.getElementById(elementId);
        if (element) {
            const trendClass = trend > 0 ? 'trend-up' : trend < 0 ? 'trend-down' : 'trend-stable';
            const trendIcon = trend > 0 ? '↗' : trend < 0 ? '↘' : '→';
            const trendColor = trend > 0 ? 'text-success' : trend < 0 ? 'text-danger' : 'text-muted';
            
            element.innerHTML = `
                <span class="${trendColor}">
                    <i class="bi bi-arrow-${trend > 0 ? 'up' : trend < 0 ? 'down' : 'right'}"></i>
                    ${Math.abs(trend)}%
                </span>
            `;
        }
    }

    // Mise à jour des alertes
    updateAlerts(alerts) {
        const alertsContainer = document.getElementById('alerts-container');
        if (alertsContainer) {
            alertsContainer.innerHTML = '';
            
            alerts.forEach(alert => {
                const alertElement = this.createAlertElement(alert);
                alertsContainer.appendChild(alertElement);
            });
        }
    }

    // Création d'un élément d'alerte
    createAlertElement(alert) {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${alert.level} alert-dismissible fade show mb-2`;
        alertDiv.innerHTML = `
            <div class="d-flex align-items-center">
                <i class="bi bi-${this.getAlertIcon(alert.level)} me-2"></i>
                <div class="flex-grow-1">
                    <strong>${alert.title}</strong>
                    <br><small>${alert.message}</small>
                </div>
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        return alertDiv;
    }

    // Icône selon le niveau d'alerte
    getAlertIcon(level) {
        const icons = {
            'danger': 'exclamation-triangle-fill',
            'warning': 'exclamation-circle',
            'info': 'info-circle',
            'success': 'check-circle'
        };
        return icons[level] || 'info-circle';
    }

    // Mise à jour du statut des missions
    updateMissionStatus(missionStatus) {
        const statusContainer = document.getElementById('mission-status-container');
        if (statusContainer) {
            statusContainer.innerHTML = '';
            
            missionStatus.forEach(mission => {
                const missionElement = this.createMissionStatusElement(mission);
                statusContainer.appendChild(missionElement);
            });
        }
    }

    // Création d'un élément de statut de mission
    createMissionStatusElement(mission) {
        const missionDiv = document.createElement('div');
        missionDiv.className = 'mission-status-item p-3 border rounded mb-2';
        missionDiv.innerHTML = `
            <div class="d-flex justify-content-between align-items-center">
                <div>
                    <h6 class="mb-1">${mission.name}</h6>
                    <small class="text-muted">${mission.client || 'Client non spécifié'}</small>
                </div>
                <div class="text-end">
                    <span class="badge bg-${this.getStatusColor(mission.status)}">${mission.status}</span>
                    <br><small class="text-muted">${mission.progress}%</small>
                </div>
            </div>
            <div class="progress mt-2" style="height: 4px;">
                <div class="progress-bar bg-${this.getStatusColor(mission.status)}" 
                     style="width: ${mission.progress}%"></div>
            </div>
        `;
        return missionDiv;
    }

    // Couleur selon le statut
    getStatusColor(status) {
        const colors = {
            'active': 'success',
            'pending': 'warning',
            'completed': 'info',
            'overdue': 'danger'
        };
        return colors[status] || 'secondary';
    }

    // Configuration des écouteurs d'événements
    setupEventListeners() {
        // Bouton de rafraîchissement manuel
        const refreshBtn = document.getElementById('refresh-metrics-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                this.refreshMetrics();
                this.showRefreshFeedback();
            });
        }

        // Filtres temporels
        const timeFilters = document.querySelectorAll('.time-filter');
        timeFilters.forEach(filter => {
            filter.addEventListener('change', (e) => {
                this.updateTimeFilter(e.target.value);
            });
        });
    }

    // Feedback de rafraîchissement
    showRefreshFeedback() {
        const refreshBtn = document.getElementById('refresh-metrics-btn');
        if (refreshBtn) {
            const originalText = refreshBtn.innerHTML;
            refreshBtn.innerHTML = '<i class="bi bi-check-circle me-2"></i>Actualisé';
            refreshBtn.classList.add('btn-success');
            
            setTimeout(() => {
                refreshBtn.innerHTML = originalText;
                refreshBtn.classList.remove('btn-success');
            }, 2000);
        }
    }

    // Mise à jour du filtre temporel
    async updateTimeFilter(timeRange) {
        try {
            const response = await fetch(`/accounts/api/dashboard_advanced_metrics/?time_range=${timeRange}`);
            const data = await response.json();
            this.updateMetricsDisplay(data);
        } catch (error) {
            console.error('Erreur lors du changement de filtre:', error);
        }
    }
}

// Initialisation au chargement de la page
document.addEventListener('DOMContentLoaded', function() {
    if (document.querySelector('.dashboard-advanced')) {
        window.dashboardMetrics = new DashboardMetrics();
    }
}); 