// ARCP Dashboard JavaScript

// Status mapping for consistent health badge colors
const STATUS_MAP = {
    green: ['healthy', true, 'connected', 'available', 'online'],
    orange: ['degraded', 'warning', 'fallback'],
    red: ['error', 'critical', false, 'disconnected', 'unavailable', 'offline'],
    gray: ['unknown', 'unclear', '???']
};

class ARCPDashboard {
    constructor() {
        this.apiBase = window.location.origin;
        this.websocket = null;
        this.charts = {};
        this.autoRefresh = true; // Enable auto-refresh by default [Non-editable] logic change by 'enableAutoRefresh'
        this.refreshInterval = null;
        this.pingInterval = null; // Add ping interval tracking
        this.autoRefreshActive = false; // Track if auto-refresh is currently scheduled
        // WebSocket ping/pong health tracking
        this.wsMissedPongs = 0; // consecutive missed pong responses
        this.wsWarnThreshold = window.ARCP_WS_PING_WARN_MISSES || 3; // warn after N misses
        this.wsDisconnectThreshold = window.ARCP_WS_PING_DISCONNECT_MISSES || 7; // hard fail after N misses
        this.wsPingTimeoutMs = window.ARCP_WS_PING_TIMEOUT_MS || 10000; // timeout waiting for a pong
        this.lastPingSentAt = 0; // timestamp of last ping
        this.lastPongAt = 0; // timestamp of last pong seen
        this.hasForcedReloadForWs = false; // avoid reload loop
        this.settings = this.loadSettings();
        this.currentTimeRange = this.settings.metricsTimeRange || '15m'; // Default to 15 minutes
        this.agents = [];
        this.agentStats = { total: 0, active: 0, types: {}, status: {} }; // Initialize agent statistics
        this.sessionValidationInFlight = null; // De-duplicate concurrent session checks
        this.lastSessionStatusCheckAt = 0; // Timestamp for throttling session_status calls
        this.cachedSessionStatus = null; // Cache last session_status result
        this.sessionStatusCacheMs = 5000; // Throttle window for session status checks (5 seconds)
        this.logs = [];
        this.authToken = localStorage.getItem('arcp-admin-token');
        this.currentUser = localStorage.getItem('arcp-admin-user');
        this.currentPin = null; // Track current PIN for authentication
        this.clientFingerprint = this.generateClientFingerprint(); // Generate client fingerprint
        
        // PIN status caching to prevent duplicate API calls
        this.pinStatusCache = null;
        this.pinStatusCacheTime = 0;
        this.pinStatusCacheMs = 10000; // Cache PIN status for 10 seconds
        
        // Pagination properties for agents
        this.agentPagination = {
            currentPage: 1,
            itemsPerPage: 30,
            totalPages: 1,
            filteredAgents: []
        };
        this.serverTimezone = 'UTC'; // Default timezone, will be fetched from server
        this.monitoringData = {
            performanceData: [],
            networkData: [],
            errorData: [],
            alertQueue: [],
            systemHealth: {
                arcp: false,
                redis: false,
                ai: false,
                websocket: false
            },
            // Store latest metrics from WebSocket monitoring frame
            latestMetrics: {
                avg_response_time: 0,
                total_requests: 0,
                error_rate: 0,
                agent_count: 0,
                // Calculated from agent_metrics array
                response_time_distribution: { fast: 0, medium: 0, slow: 0, very_slow: 0 },
                load_balancing: {}, // agent_id -> load_percentage
                resource_utilization: { cpu: 0, memory: 0, network: 0, storage: 0 }
            }
        };
        this.alertSearchText = '';
        this.alertTypeFilter = '';
        this.logSearchText = '';
        this.lastSessionCheck = 0; // Timestamp to prevent multiple parallel session checks
        this.websocketBackoff = 5000; // WebSocket reconnection backoff
        this.websocketRetryTimer = null; // Track pending retry timer
        this.alertAudioCtx = null; // Reusable AudioContext for alert sounds
        this.lastToastTime = {}; // Track last toast time for rate limiting
        this.alertSuppressionMap = {}; // Track suppressed alerts to prevent loops
        this.isPaused = false; // Initialize monitoring as active
        
        // Initialize SecurityManager (it will access dashboard globally)
        this.securityManager = new SecurityManager();
        
        // Make dashboard globally accessible for SecurityManager
        window.dashboard = this;
        
        // Apply UI settings before auth flow for consistent theme
        this.applySettings();
        
        this.init();
        // Global loading state
        this.loadingCount = 0;
        this.progressInterval = null;
        this.progressElement = null;
        this.progressValue = 0;
        this.overlayDelayTimer = null;
        this.progressDelayTimer = null;
        this.progressStarted = false;
        this.progressDelayMs = 300; // show bar only if request lasts > 300ms
        this.overlayDelayMs = 1000; // overlay shown after 1s
        this.ensureLoadingUI();
        if (this.authToken) {
            this.showLoading(true);
        } else {
            this.showLoading(false);
        }
    }

    generateClientFingerprint() {
        // Generate a client fingerprint based on browser and system characteristics
        const components = [
            navigator.userAgent,
            navigator.language,
            navigator.platform,
            screen.width + 'x' + screen.height,
            screen.colorDepth,
            new Date().getTimezoneOffset(),
            window.location.hostname,
            navigator.hardwareConcurrency || 'unknown',
            navigator.deviceMemory || 'unknown'
        ];
        
        // Create a simple hash of the components
        const fingerprint = components.join('|');
        let hash = 0;
        for (let i = 0; i < fingerprint.length; i++) {
            const char = fingerprint.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash; // Convert to 32-bit integer
        }
        
        return Math.abs(hash).toString(16);
    }

    /**
     * Format timestamp consistently across the dashboard using server timezone
     * @param {string|Date} timestamp - ISO timestamp string or Date object
     * @param {boolean} includeDate - Whether to include date in output
     * @param {boolean} includeSeconds - Whether to include seconds in time
     * @returns {string} Formatted timestamp
     */
    formatTimestamp(timestamp, includeDate = false, includeSeconds = true) {
        try {
            const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
            
            // Check if date is valid
            if (isNaN(date.getTime())) {
                return 'Invalid Date';
            }
            
            const options = {
                timeZone: this.serverTimezone,
                hour12: true,
                hour: '2-digit',
                minute: '2-digit'
            };
            
            if (includeSeconds) {
                options.second = '2-digit';
            }
            
            if (includeDate) {
                options.year = 'numeric';
                options.month = 'short';
                options.day = '2-digit';
            }
            
            return date.toLocaleString('en-US', options);
        } catch (error) {
            console.warn('Error formatting timestamp:', error);
            // Fallback to simple local time
            const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
            return includeDate ? date.toLocaleString() : date.toLocaleTimeString();
        }
    }

    getDataPointLimit(timeRange = null) {
        // Calculate appropriate data point limit based on time range
        const range = timeRange || this.currentTimeRange || '15m';
        
        // Assuming data points come in every ~15 seconds for real-time monitoring
        // 5m = 20 points, 15m = 60 points, 1h = 240 points, 4h = 960 points
        switch (range) {
            case '5m': return 20;
            case '15m': return 60;
            case '1h': return 240;
            case '4h': return 960;
            default: return 60;
        }
    }

    /*
     * We get server timezone configuration
     * [ TL?...
     *   Fetches the server's IANA time zone and caches it in this.serverTimezone.
     *   The client may run in a different time zone than the server; we use the server's
     *   zone for consistent display of server-originated timestamps. Falls back to 'UTC'.
     * ] 
     */
    async fetchConfig() {
        try {
            const response = await this.apiCall(`${this.apiBase}/dashboard/config`, {
                method: 'GET',
                headers: this.getAuthHeaders()
            });
            const data = await response.json();
            if (data.timezone) {
                this.serverTimezone = data.timezone;
                // console.log(`Server timezone configured: ${this.serverTimezone}`);
            } else {
                console.warn('Server timezone not configured, using default UTC');
                this.serverTimezone = 'UTC';
            }
            if (typeof data.log_buffer_maxlen === 'number') {
                this.serverLogBufferMax = data.log_buffer_maxlen;
                // console.log('serverLogBufferMax', this.serverLogBufferMax);
            }
            if (typeof data.log_message_maxlen === 'number') {
                this.serverLogMessageMax = data.log_message_maxlen;
                // console.log('serverLogMessageMax', this.serverLogMessageMax);
            }
            // Merge server-stored UI settings (optional)
            if (data.ui && typeof data.ui === 'object') {
                const ui = data.ui;
                const merged = { ...this.settings };
                if (typeof ui.enableAutoRefresh === 'boolean') merged.enableAutoRefresh = ui.enableAutoRefresh;
                if (typeof ui.refreshInterval === 'number') merged.refreshInterval = ui.refreshInterval;
                if (typeof ui.maxLogEntries === 'number') merged.maxLogEntries = Math.min(ui.maxLogEntries, this.serverLogBufferMax || ui.maxLogEntries);
                this.settings = merged;
                // Do not persist to localStorage until authenticated; apply to UI instead
                this.applySettings();
            }
        } catch (error) {
            console.warn('Could not fetch server timezone, using UTC:', error);
            this.serverTimezone = 'UTC';
        }
    }

    generateAlertTitle(alert) {
        // Generate a meaningful title for alerts based on type and message
        if (alert.title) return alert.title;
        
        const type = alert.type || 'general';
        const message = alert.message || '';
        
        // Generate smart titles based on alert type and content
        switch (type.toLowerCase()) {
            case 'system_health':
                if (message.toLowerCase().includes('unhealthy')) {
                    return 'System Health Critical';
                } else if (message.toLowerCase().includes('degraded')) {
                    return 'System Health Warning';
                }
                return 'System Health';
                
            case 'storage':
                if (message.toLowerCase().includes('redis')) {
                    return 'Redis Storage Issue';
                } else if (message.toLowerCase().includes('database')) {
                    return 'Database Connection Issue';
                }
                return 'Storage';
                
            case 'agent':
                return 'Agent Status';
                
            case 'network':
                return 'Network Connectivity';
                
            case 'performance':
                return 'Performance';
                
            default:
                // Capitalize the type name
                return type.charAt(0).toUpperCase() + type.slice(1);
        }
    }

    getAuthHeaders(includePIN = false) {
        // Get standard authentication headers with client fingerprint
        const headers = {
            'Content-Type': 'application/json'
        };
        
        if (this.authToken) {
            headers['Authorization'] = `Bearer ${this.authToken}`;
        }
        
        // Only include PIN when explicitly requested for PIN-protected operations
        if (includePIN && this.currentPin) {
            headers['X-Session-Pin'] = this.currentPin;
        }
        
        // Add client fingerprint for security
        headers['X-Client-Fingerprint'] = this.clientFingerprint;
        
        return headers;
    }

    // ========== Global Loading UI ==========
    ensureLoadingUI() {
        // Inject CSS once for high z-index overlay and top progress bar
        if (!document.getElementById('arcp-loading-styles')) {
            const style = document.createElement('style');
            style.id = 'arcp-loading-styles';
            style.textContent = `
                #loadingOverlay { z-index: 2147483647 !important; position: fixed; }
                .arcp-progress-bar { position: fixed; top: 0; left: 0; height: 3px; width: 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); z-index: 2147483647; transition: width 150ms ease; box-shadow: 0 0 6px rgba(13,110,253,0.6); }
                .arcp-progress-shadow { position: fixed; top: 3px; left: 0; height: 2px; width: 0; background: rgba(13,110,253,0.25); z-index: 2147483646; transition: width 200ms ease; }
            `;
            document.head.appendChild(style);
        }
        // Create progress elements if missing
        if (!document.getElementById('arcpProgressBar')) {
            const bar = document.createElement('div');
            bar.id = 'arcpProgressBar';
            bar.className = 'arcp-progress-bar';
            document.body.appendChild(bar);
            const shadow = document.createElement('div');
            shadow.id = 'arcpProgressShadow';
            shadow.className = 'arcp-progress-shadow';
            document.body.appendChild(shadow);
            this.progressElement = bar;
            this.progressShadow = shadow;
        } else {
            this.progressElement = document.getElementById('arcpProgressBar');
            this.progressShadow = document.getElementById('arcpProgressShadow');
        }
    }

    beginLoading() {
        this.ensureLoadingUI();
        if (this.loadingCount === 0) {
            // Record start time
            this.loadingStartTime = (typeof performance !== 'undefined' ? performance.now() : Date.now());
            // Overlay delayed to avoid flicker on fast requests
            if (this.overlayDelayTimer) clearTimeout(this.overlayDelayTimer);
            this.overlayDelayTimer = setTimeout(() => this.showLoading(true), this.overlayDelayMs || 1000);
            // Progress bar delayed to avoid flashing for very fast requests
            this.progressValue = 0;
            this.setProgressWidth(0);
            this.progressStarted = false;
            if (this.progressDelayTimer) clearTimeout(this.progressDelayTimer);
            this.progressDelayTimer = setTimeout(() => {
                this.progressStarted = true;
                this.startProgressAnimation();
            }, this.progressDelayMs || 300);
        }
        this.loadingCount++;
    }

    endLoading() {
        this.loadingCount = Math.max(0, this.loadingCount - 1);
        if (this.loadingCount === 0) {
            if (this.overlayDelayTimer) {
                clearTimeout(this.overlayDelayTimer);
                this.overlayDelayTimer = null;
            }
            // Cancel delayed start if pending
            if (this.progressDelayTimer) {
                clearTimeout(this.progressDelayTimer);
                this.progressDelayTimer = null;
            }
            // Only complete the bar if it actually started
            if (this.progressStarted) {
                this.stopProgressAnimation(true);
            } else {
                this.setProgressWidth(0);
                if (this.progressElement) this.progressElement.style.width = '0%';
                if (this.progressShadow) this.progressShadow.style.width = '0%';
            }
            // Hide overlay slightly after completing progress for smoothness
            setTimeout(() => this.showLoading(false), 200);
        }
    }

    setProgressWidth(percent) {
        if (this.progressElement) {
            this.progressElement.style.width = `${percent}%`;
        }
        if (this.progressShadow) {
            const shadowWidth = Math.min(100, percent + 10);
            this.progressShadow.style.width = `${shadowWidth}%`;
        }
    }

    startProgressAnimation() {
        if (this.progressInterval) clearInterval(this.progressInterval);
        if (this.progressElement) this.progressElement.style.display = 'block';
        if (this.progressShadow) this.progressShadow.style.display = 'block';
        // Ease towards 90% while loading; final completion happens in stopProgressAnimation
        this.progressInterval = setInterval(() => {
            const target = 90;
            const delta = Math.max(0.5, (target - this.progressValue) * 0.08);
            this.progressValue = Math.min(target, this.progressValue + delta);
            this.setProgressWidth(this.progressValue);
        }, 120);
    }

    stopProgressAnimation(complete = false) {
        if (this.progressInterval) {
            clearInterval(this.progressInterval);
            this.progressInterval = null;
        }
        if (complete) {
            this.progressValue = 100;
            this.setProgressWidth(100);
            // Reset bar after a short delay
            setTimeout(() => {
                this.setProgressWidth(0);
                if (this.progressElement) this.progressElement.style.display = 'none';
                if (this.progressShadow) this.progressShadow.style.display = 'none';
            }, 300);
        } else {
            this.setProgressWidth(0);
            if (this.progressElement) this.progressElement.style.display = 'none';
            if (this.progressShadow) this.progressShadow.style.display = 'none';
        }
    }

    async handleApiResponse(response, skipSessionCheck = false) {
        // Check if response indicates token expiration or authorization issues
        if (response.status === 401) {
            // Treat 401 as invalid session and centralize handling
            await this.checkSessionStatus(true);
            throw new Error('Token expired');
        }
        
        // Handle 403 Forbidden - check session status (but avoid recursive calls)
        if (response.status === 403 && !skipSessionCheck) {
            // Prevent multiple parallel session checks within 2 seconds
            const now = Date.now();
            if (now - this.lastSessionCheck < 2000) {
                // console.log('Skipping session check - too recent');
                const errorText = await response.text();
                throw new Error('Access denied: ' + errorText);
            }
            this.lastSessionCheck = now;
            
            // console.log('403 Forbidden detected, checking session status...');
            try {
                const status = await this.checkSessionStatus();
                if (!status.valid) {
                    throw new Error('Session invalid');
                }
                // Session valid but forbidden → permission issue
                const errorText = await response.text();
                console.warn('403 error but session is valid:', errorText);
                throw new Error('Access denied: ' + errorText);
            } catch (sessionError) {
                throw sessionError;
            }
        }
        
        return response;
    }

    // Centralized session status check with deduplication and unified logout handling
    async checkSessionStatus(forceTreat401AsExpired = false) {
        if (!this.authToken) {
            return { valid: false };
        }

        // De-duplicate in-flight checks
        if (this.sessionValidationInFlight) {
            try {
                return await this.sessionValidationInFlight;
            } catch (e) {
                // If in-flight failed, propagate as invalid
                return { valid: false };
            }
        }

        // Throttle network calls using short-lived cache
        const now = Date.now();
        if (this.cachedSessionStatus && (now - this.lastSessionStatusCheckAt) < this.sessionStatusCacheMs) {
            return this.cachedSessionStatus;
        }

        this.sessionValidationInFlight = (async () => {
            try {
                const response = await fetch(`${this.apiBase}/auth/session_status`, {
                    method: 'GET',
                    headers: this.getAuthHeaders()
                });

                if (response.ok) {
                    const data = await response.json();
                    const result = { valid: !!data.valid };
                    this.cachedSessionStatus = result;
                    this.lastSessionStatusCheckAt = Date.now();
                    return result;
                }

                if (response.status === 401 || forceTreat401AsExpired) {
                    this.showToast('Session expired. Log in again.', 'warning');
                    await this.logout(true);
                    this.cachedSessionStatus = { valid: false };
                    this.lastSessionStatusCheckAt = Date.now();
                    return { valid: false };
                }

                // Other non-OK statuses → treat as invalid
                this.showToast('Session verification failed. Try logging in again.', 'warning');
                await this.logout(true);
                this.cachedSessionStatus = { valid: false };
                this.lastSessionStatusCheckAt = Date.now();
                return { valid: false };
            } catch (error) {
                console.error('Session status check error:', error);
                // Network or unexpected error: conservative logout
                this.showToast('Unable to verify session. Log in again.', 'warning');
                await this.logout(true);
                this.cachedSessionStatus = { valid: false };
                this.lastSessionStatusCheckAt = Date.now();
                return { valid: false };
            } finally {
                this.sessionValidationInFlight = null;
            }
        })();

        return await this.sessionValidationInFlight;
    }

    async apiCall(url, options = {}) {
        // Wrapper for API calls with automatic token expiration handling and global loading indicator
        try {
            this.beginLoading();

            const response = await fetch(url, options);
            this.endLoading();
            // Pass skipSessionCheck flag for session status endpoint to prevent recursion
            const skip = url.includes('/auth/session_status');
            await this.handleApiResponse(response, skip);
            return response;
        } catch (error) {
            this.endLoading();
            if (error.message === 'Token expired') {
                throw error; // Re-throw token expiration errors
            }
            console.error('API call error:', error);
            throw error;
        }
    }

    async init() {
        // Check authentication first - if not authenticated, show login and stop initialization
        if (!this.authToken) {
            // Ensure background activities are not running when unauthenticated
            this.disconnectWebSocket();
            this.isPaused = true;
            this.autoRefresh = false;
            // Ensure loading overlay is hidden when prompting for login
            this.showLoading(false);
            this.showAdminLoginModal((success) => {
                // Only continue initialization if login was successful
                if (success) {
                    this.continueInit();
                }
                // If login failed, stay on login screen
            });
            return;
        }

        // Validate token before continuing initialization
        if (this.authToken && (await this.checkSessionStatus()).valid) {
            this.continueInit();
        } else {
            this.authToken = null;
            localStorage.removeItem('arcp-admin-token');
            this.showAdminLoginModal((success) => {
                if (success) {
                    this.continueInit();
                }
            });
        }
    }

    async continueInit() {
        // Hide dashboard until PIN is confirmed set
        document.getElementById('dashboardContainer').style.display = 'none';
        this.showLoading(true);
        
        // Check if PIN is set BEFORE setting up WebSocket
        try {
            const data = await this.checkPinStatus();
            if (!data.pin_set) {
                const pinSet = await this.showPinModal({
                    mode: 'set',
                    onSuccess: () => {
                        // Clear PIN status cache since PIN was just set
                        this.pinStatusCache = null;
                        this.pinStatusCacheTime = 0;
                        this.showSuccess('Session PIN set successfully. PIN will be cleared when you logout.');
                    }
                });
                if (!pinSet) {
                    alert('You must set a session PIN to access the dashboard.');
                    this.logout();
                    return;
                }
            } else {
                // PIN is already set, verify it
                const pinVerified = await this.showPinModal({
                    mode: 'verify',
                    onSuccess: () => {
                        // PIN verified - WebSocket will be set up after this
                        // Clear PIN status cache to ensure fresh state
                        this.pinStatusCache = null;
                        this.pinStatusCacheTime = 0;
                    }
                });
                if (!pinVerified) {
                    alert('PIN verification failed. You must verify your PIN to access the dashboard.');
                    this.logout();
                    return;
                }
            }
        } catch (e) {
            alert('Error checking PIN status.');
            this.logout();
            return;
        }
        
        // Setup WebSocket AFTER PIN is confirmed
        this.setupWebSocket();
        
        // Fetch server timezone configuration
        await this.fetchConfig();
        
        // Show the dashboard
        document.getElementById('dashboardContainer').style.display = 'block';
        this.setupEventListeners();
        this.applySettings();
        this.updateAuthStatus();
        
        // Load persisted alerts before loading other data
        this.loadAlertsFromStorage();
        
        await this.loadInitialData();
        this.initializeCharts();
        
        // Initialize monitoring without WebSocket first
        await this.initializeMonitoring(); // Initialize real-time monitoring
        
        // Auto-refresh follows saved settings; do not forcibly change the flag here
        this.setupAutoRefresh();
        this.setupTokenValidation(); // Setup periodic token validation

        // Initialize recent activity display
        this.updateRecentActivity();

        // Alerts tab controls
        const alertSearch = document.getElementById('alertSearch');
        if (alertSearch) {
            alertSearch.addEventListener('input', (e) => {
                this.alertSearchText = e.target.value.toLowerCase();
                this.renderAlerts();
            });
        }
        const alertTypeFilter = document.getElementById('alertTypeFilter');
        if (alertTypeFilter) {
            alertTypeFilter.addEventListener('change', (e) => {
                this.alertTypeFilter = e.target.value;
                this.renderAlerts();
            });
        }
        const clearAlertsBtn = document.getElementById('clearAlertsBtn');
        if (clearAlertsBtn) {
            clearAlertsBtn.addEventListener('click', async () => {
                dashboard.addLog('INFO', 'Attempt to clear alerts');
                // Require PIN before clearing alerts
                await this.requirePin(async () => {
                this.clearAlerts();
                });
            });
        }

        // Logs tab search
        const logSearch = document.getElementById('logSearch');
        if (logSearch) {
            logSearch.addEventListener('input', (e) => {
                this.logSearchText = e.target.value.toLowerCase();
                this.renderLogs();
            });
        }

        // Logs level filter
        const logLevelSelect = document.getElementById('logLevel');
        if (logLevelSelect) {
            logLevelSelect.addEventListener('change', () => {
                this.renderLogs();
            });
        }
    }

    setupEventListeners() {
        // Tab navigation
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', async (e) => {
                const tabName = e.currentTarget.dataset.tab;
                await this.switchTab(tabName);
            });
        });

        // Search and filters
        const agentSearch = document.getElementById('agentSearch');
        if (agentSearch) {
            agentSearch.addEventListener('input', (e) => {
                this.filterAgents();
            });
        }

        const agentTypeFilter = document.getElementById('agentTypeFilter');
        if (agentTypeFilter) {
            agentTypeFilter.addEventListener('change', () => {
                this.filterAgents();
            });
        }

        const agentStatusFilter = document.getElementById('agentStatusFilter');
        if (agentStatusFilter) {
            agentStatusFilter.addEventListener('change', () => {
                this.filterAgents();
            });
        }

        // Log level filter
        const logLevel = document.getElementById('logLevel');
        if (logLevel) {
            logLevel.addEventListener('change', () => {
                this.filterLogs();
            });
        }

        // Settings
        const enableAutoRefresh = document.getElementById('enableAutoRefresh');
        if (enableAutoRefresh) {
            enableAutoRefresh.addEventListener('change', (e) => {
                const refreshIntervalInput = document.getElementById('refreshInterval');
                if (refreshIntervalInput) {
                    refreshIntervalInput.disabled = !e.target.checked;
                }
                // Update settings object but don't save until user clicks Save button
                this.settings.enableAutoRefresh = e.target.checked;
            });
        }

        const refreshInterval = document.getElementById('refreshInterval');
        if (refreshInterval) {
            refreshInterval.addEventListener('change', (e) => {
                // Just update the settings object, don't save automatically
                this.settings.refreshInterval = parseInt(e.target.value);
            });
        }
    }

    setupWebSocket() {
        this.setupMonitoringWebSocket();
    }

    disconnectWebSocket() {
        if (this.websocket) {
            this.addLog('INFO', 'Disconnecting WebSocket...');
            
            // Clear any reconnection timers
            if (this.websocketRetryTimer) {
                clearTimeout(this.websocketRetryTimer);
                this.websocketRetryTimer = null;
            }
            
            // Close WebSocket connection
            this.websocket.close();
            this.websocket = null;
            this.connectingWebSocket = false;
            
            // Reset backoff to initial value for next connection attempt
            this.websocketBackoff = 5000;
            
            // Update connection status
            this.updateConnectionStatus(false);
            this.addLog('INFO', 'WebSocket disconnected');
        }
    }

    setupMonitoringWebSocket() {
        // Check authentication first - don't attempt connection without proper auth
        if (!this.authToken) {
            // console.log('No authentication token available, skipping WebSocket connection');
            return;
        }
        
        // Prevent multiple WebSocket connections
        if (this.websocket && this.websocket.readyState === WebSocket.CONNECTING) {
            // console.log('WebSocket already connecting, skipping...');
            return;
        }
        
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            // console.log('WebSocket already connected, skipping...');
            return;
        }
        
        // Add connection attempt guard
        if (this.connectingWebSocket) {
            // console.log('WebSocket connection attempt already in progress, skipping...');
            return;
        }
        
        // Prevent connection attempt while retry timer is pending
        if (this.websocketRetryTimer) {
            // console.log('WebSocket retry timer is pending, skipping...');
            return;
        }
        
        this.connectingWebSocket = true;
        
        // Close existing connection if any
        if (this.websocket) {
            this.websocket.close();
            this.websocket = null;
        }
        
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        let wsUrl = `${protocol}//${window.location.host}/dashboard/ws?token=${encodeURIComponent(this.authToken)}`;
        
        try {
            // Create WebSocket connection
            this.websocket = new WebSocket(wsUrl);
            
            // Define retry function first
            function retry() {
                // Only retry if we still have proper authentication
                if (!this.authToken) {
                    // console.log('Not retrying WebSocket - missing authentication token');
                    return;
                }
                
                // Clear any existing retry timer
                if (this.websocketRetryTimer) {
                    clearTimeout(this.websocketRetryTimer);
                }
                
                // Clear any ping interval to prevent racing timers
                if (this.pingInterval) {
                    clearInterval(this.pingInterval);
                    this.pingInterval = null;
                }
                
                console.warn('WebSocket closed; retrying in', this.websocketBackoff / 1000, 'seconds...');
                this.websocketRetryTimer = setTimeout(() => {
                    this.websocketRetryTimer = null; // Clear the timer reference
                    this.setupMonitoringWebSocket();
                }, this.websocketBackoff);
                this.websocketBackoff = Math.min(this.websocketBackoff * 2, 300000); // 5s → 10s → 30s → 5min
            }
            
            // Store retry function for access in closures
            this.retry = retry.bind(this);
            
            this.websocket.onopen = () => {
                // console.log('Dashboard WebSocket connected');
                this.connectingWebSocket = false; // Clear connection guard
                this.websocketBackoff = 5000; // Reset backoff on successful connection
                this.updateConnectionStatus(true);
                this.stopPolling(); // Stop any legacy polling
                this.monitoringData.systemHealth.websocket = true;
                this.updateSystemHealthIndicators();
                // Reset ping/pong health state
                this.wsMissedPongs = 0;
                this.lastPingSentAt = 0;
                this.lastPongAt = Date.now();
                this.hasForcedReloadForWs = false;
                
                // Show success alert for reconnection (if this was a reconnect)
                if (this.wasDisconnected) {
                    this.addAlert({
                        type: 'info',
                        severity: 'info',
                        title: 'Dashboard Connection Restored',
                        message: 'Real-time updates are now available - WebSocket reconnected successfully',
                        timestamp: new Date().toISOString()
                    });
                    this.wasDisconnected = false;
                }
                
                // Send authentication frame immediately on connection
                // PIN validation is handled at session level, not WebSocket level
                this.websocket.send(JSON.stringify({
                    type: 'auth',
                    token: this.authToken,
                    fingerprint: this.clientFingerprint
                }));
                
                // Setup ping timer when connection is established
                if (!this.pingInterval) {
                    const pingMs = (window.ARCP_WS_PING_INTERVAL_MS || 30000);
                    this.pingInterval = setInterval(() => {
                        // Before sending a new ping, evaluate the last one
                        const now = Date.now();
                        if (
                            this.lastPingSentAt &&
                            (now - this.lastPingSentAt) > this.wsPingTimeoutMs &&
                            this.lastPongAt < this.lastPingSentAt
                        ) {
                            // We did not get a pong in time for the previous ping
                            this.wsMissedPongs++;
                            this.handleWsMissedPongs();
                        }

                        if (this.websocket?.readyState === WebSocket.OPEN) {
                            this.websocket.send('ping');
                            this.lastPingSentAt = now;
                        }
                    }, pingMs); // Ping interval configurable via global
                }
            };
            
            this.websocket.onmessage = (event) => {
                try {
                    // Handle ping/pong messages even when paused
                    if (event.data === 'ping') {
                        this.websocket.send('pong');
                        return;
                    }
                    
                    if (event.data === 'pong') {
                        // Backend is responsive again
                        this.lastPongAt = Date.now();
                        if (this.wsMissedPongs > 0) {
                            this.wsMissedPongs = 0;
                            this.showToastWithRateLimit('Real-time connection responsive again', 'success', 4000);
                            this.addAlert({
                                type: 'info',
                                severity: 'info',
                                title: 'Dashboard Connection Stable',
                                message: 'PONG received from backend — connectivity restored',
                                timestamp: new Date().toISOString()
                            });
                        }
                        return;
                    }

                    const frame = JSON.parse(event.data);

                    // Always allow acknowledgment messages and critical system messages
                    const alwaysAllowedTypes = ['pause_ack', 'resume_ack', 'refresh_ack', 'clear_logs_ack', 'agents_ack', 'logs', 'agents', 'alert'];
                    
                    // Skip data processing if monitoring is paused, except for critical types
                    if (this.isPaused === true && !alwaysAllowedTypes.includes(frame.type)) {
                        // console.log(`Monitoring paused - skipping ${frame.type} frame`);
                        return;
                    }

                    this.routeFrame(frame);
                } catch (error) {
                    console.warn('Failed to parse WebSocket message:', event.data, error);
                }
            };
            
            this.websocket.onclose = (event) => {
                console.warn('Dashboard WebSocket closed:', event.code, event.reason);
                this.connectingWebSocket = false; // Clear connection guard
                this.wasDisconnected = true; // Mark as disconnected for reconnection alert
                this.updateConnectionStatus(false);
                this.monitoringData.systemHealth.websocket = false;
                
                // Set all agent statuses to unknown when WebSocket disconnects
                this.setAgentsStatusUnknown();
                
                // Reset all charts to zero when WebSocket disconnects
                this.resetAllChartsToZero();
                
                this.updateSystemHealthIndicators();
                
                // If user is logged out, skip connection lost alert/toast
                if (this.authToken) {
                    this.addAlert({
                        type: 'critical',
                        severity: 'critical',
                        title: 'Dashboard Connection Lost',
                        message: `Real-time updates are not available (WebSocket closed: ${event.code}) - attempting to reconnect`,
                        timestamp: new Date().toISOString()
                    });
                }
                
                // Clear ping interval when connection closes
                if (this.pingInterval) {
                    clearInterval(this.pingInterval);
                    this.pingInterval = null;
                }
                // Reset ping health state
                this.wsMissedPongs = 0;
                this.lastPingSentAt = 0;
                this.lastPongAt = 0;
                
                // Only retry if we still have proper authentication
                if (this.authToken) {
                    this.retry();
                } else {
                    // console.log('Not retrying WebSocket - missing authentication token');
                }
            };
            
            this.websocket.onerror = (error) => {
                console.error('Dashboard WebSocket error:', error);
                this.connectingWebSocket = false; // Clear connection guard
                
                // Show warning alert for connection errors only when authenticated
                if (this.authToken) {
                    this.addAlert({
                        type: 'warning',
                        severity: 'warning',
                        title: 'Dashboard Connection Error',
                        message: 'WebSocket connection encountered an error - will attempt to reconnect',
                        timestamp: new Date().toISOString()
                    });
                }
                
                this.websocket.close();
            };
            
        } catch (error) {
            console.error('Dashboard WebSocket connection failed:', error);
            this.connectingWebSocket = false; // Clear connection guard
            this.updateConnectionStatus(false);
        }
    }

    routeFrame(frame) {
        // Always store data but respect pause state for UI updates
        switch (frame.type) {
            case 'monitoring':
                // Always store monitoring data, but only update charts if not paused
                this.updateCharts(frame.data);
                break;
            case 'health':
                // Always process health data (critical for system status)
                this.updateSystemHealth(frame.data);
                break;
            case 'alert':
                // Handle both server-hydrated array `{alerts: [...]}` and single alert object
                if (frame && frame.data) {
                    this.addAlert(frame.data);
                } else if (frame && frame.alerts) {
                    this.addAlert({ alerts: frame.alerts });
                }
                break;
            case 'agents':
                // Always process agent updates (important for status)
                this.updateAgents(frame.data);
                // Update recent activity when agents change
                this.updateRecentActivity();
                break;
            case 'logs':
                // Always process logs
                this.updateLogs(frame.data);
                break;
            case 'pause_ack':
                // Handle pause acknowledgment from backend
                // console.log('Monitoring paused on backend');
                this.showToastWithRateLimit('Monitoring paused - EX Agent and Logs', 'warning', 3000);
                break;
            case 'resume_ack':
                // Handle resume acknowledgment from backend
                // console.log('Monitoring resumed on backend');
                this.showToastWithRateLimit('Monitoring resumed', 'success', 3000);
                break;
            case 'refresh_ack':
                // Handle refresh acknowledgment from backend
                // console.log('Manual refresh completed by backend');
                this.showToastWithRateLimit('Dashboard data refreshed successfully', 'success', 2000);
                break;
            case 'clear_logs_ack':
                // Handle clear logs acknowledgment from backend
                if (frame.data.status === 'completed') {
                    this.showToastWithRateLimit('Logs cleared successfully', 'success', 2000);
                } else if (frame.data.status === 'error') {
                    this.showToastWithRateLimit(`Failed to clear logs: ${frame.data.message}`, 'error', 3000);
                    this.addLog('ERR', `Clear failed: ${frame.data.message}`);
                }
                break;
            case 'clear_alerts_ack':
                // Handle clear alerts acknowledgment from backend
                if (frame.data.status === 'completed') {
                    this.showToastWithRateLimit('Alerts cleared successfully', 'success', 2000);
                } else if (frame.data.status === 'error') {
                    this.showToastWithRateLimit(`Failed to clear alerts: ${frame.data.message}`, 'error', 3000);
                    this.addLog('ERR', `Clear alerts failed: ${frame.data.message}`);
                }
                break;
            case 'agents_ack':
                // Handle agents data acknowledgment from backend
                if (frame.data.status === 'completed') {
                    // console.log('Agents data loaded successfully');
                } else if (frame.data.status === 'error') {
                    console.error('Error loading agents data:', frame.data.message);
                    this.showToastWithRateLimit(`Error loading agents: ${frame.data.message}`, 'error', 3000);
                }
                break;
            default:
                // console.log('Unknown frame type:', frame.type, frame);
        }
    }

    handleWsMissedPongs() {
        // Warning path
        if (this.wsMissedPongs === this.wsWarnThreshold) {
            // One-time warning toast and alert when threshold hit
            this.showToastWithRateLimit('Experiencing connectivity issues (missing pong responses)', 'warning', 10000);
            this.addAlert({
                type: 'warning',
                severity: 'warning',
                title: 'WebSocket Connectivity Warning',
                message: `No PONG from backend for ${this.wsMissedPongs} consecutive pings`,
                timestamp: new Date().toISOString()
            });
        }

        // Escalate to critical and treat as disconnected beyond threshold
        if (this.wsMissedPongs >= this.wsDisconnectThreshold) {
            // Prevent repeated actions
            if (!this.hasForcedReloadForWs) {
                // Reset all charts to zero when connection is unresponsive
                this.resetAllChartsToZero();
                
                this.addAlert({
                    type: 'critical',
                    severity: 'critical',
                    title: 'WebSocket Unresponsive',
                    message: `No PONG for ${this.wsMissedPongs} consecutive pings - forcing reconnection`,
                    timestamp: new Date().toISOString()
                });
                this.showToastWithRateLimit('Real-time connection unresponsive - reloading...', 'critical', 15000);

                // Attempt graceful reconnect first
                try {
                    if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
                        this.websocket.close();
                    }
                } catch (_) { /* ignore */ }

                // As a last resort, force a hard refresh to recover UI state
                this.hasForcedReloadForWs = true;
                setTimeout(() => {
                    try {
                        window.location.reload();
                    } catch (_) { /* ignore */ }
                }, 750);
            }
        }
    }

    updateCharts(monitoringData) {
        // Always store the latest data, even if paused (for resuming later)
        this.monitoringData.latestMetrics = {
            avg_response_time: monitoringData.avg_response_time || 0,
            total_requests: monitoringData.total_requests || 0,
            error_rate: monitoringData.error_rate || 0,
            agent_count: monitoringData.agent_count || 0,
            // Include agent_metrics for detailed analysis
            agent_metrics: monitoringData.agent_metrics || [],
            // For advanced charts, we'll calculate from agent_metrics or use defaults
            response_time_distribution: this.calculateResponseTimeDistribution(monitoringData.agent_metrics || []),
            load_balancing: this.calculateLoadBalancing(monitoringData.agent_metrics || []),
            // Use real resource utilization data from WebSocket
            resource_utilization: monitoringData.resource_utilization || { cpu: 0, memory: 0, network: 0, storage: 0 }
        };
        
        // Record last update time
        this.monitoringData.lastUpdate = Date.now();
        
        // Skip chart updates if monitoring is paused
        if (this.isPaused) {
            // console.log('Monitoring paused - data stored but charts not updated');
            return;
        }
        
        const currentTime = this.formatTimestamp(new Date(), false, false);
        
        // Store historical data points for trend analysis
        const dataPoint = {
            timestamp: new Date().toISOString(),
            response_time: monitoringData.avg_response_time || 0,
            requests: monitoringData.total_requests || 0,
            error_rate: monitoringData.error_rate || 0
        };
        
        // Add to historical arrays and keep data points based on current time range
        this.monitoringData.performanceData.push(dataPoint);
        this.monitoringData.networkData.push(dataPoint);
        this.monitoringData.errorData.push(dataPoint);
        
        // Keep data points based on current time range setting (with some buffer)
        const maxDataPoints = Math.max(this.getDataPointLimit() * 2, 100); // At least 100, or 2x current range
        if (this.monitoringData.performanceData.length > maxDataPoints) {
            this.monitoringData.performanceData = this.monitoringData.performanceData.slice(-maxDataPoints);
            this.monitoringData.networkData = this.monitoringData.networkData.slice(-maxDataPoints);
            this.monitoringData.errorData = this.monitoringData.errorData.slice(-maxDataPoints);
        }
        
        // Only update agent-dependent charts if we have registered agents
        if (this.hasRegisteredAgents()) {
            // Update real-time performance chart with calculated values
            const calculatedResponseTime = this.calculateAverageResponseTime();
            this.updateChart(this.charts.realtimePerformance, currentTime, calculatedResponseTime);
            
            // Update network activity chart with calculated requests per minute
            const calculatedNetworkActivity = this.calculateNetworkActivity();
            this.updateChart(this.charts.networkActivity, currentTime, calculatedNetworkActivity);
            
            // Update error rate chart
            const errorRate = (monitoringData.error_rate || 0) * 100;
            this.updateChart(this.charts.errorRate, currentTime, errorRate);
            
            // Update metric summaries with calculated values
            this.updateMetricSummaries(
                calculatedResponseTime,
                calculatedNetworkActivity,
                monitoringData.error_rate || 0
            );
        } else {
            // No registered agents - show zero values
            this.updateChart(this.charts.realtimePerformance, currentTime, 0);
            this.updateChart(this.charts.networkActivity, currentTime, 0);
            this.updateChart(this.charts.errorRate, currentTime, 0);
            
            // Update metric summaries with zero values
            this.updateMetricSummaries(0, 0, 0);
        }
        
        // Debug logging for troubleshooting
        // if (calculatedResponseTime > 0 || calculatedNetworkActivity > 0 || (monitoringData.resource_utilization && Object.values(monitoringData.resource_utilization).some(v => v > 0))) {
        //     console.log('Chart Updates:', {
        //         responseTime: calculatedResponseTime,
        //         networkActivity: calculatedNetworkActivity,
        //         errorRate: monitoringData.error_rate,
        //         resourceUtil: monitoringData.resource_utilization,
        //         agentMetrics: monitoringData.agent_metrics?.length || 0
        //     });
        // }
        
        // Update agent count
        if (monitoringData.agent_count !== undefined) {
            const agentCountElement = document.getElementById('agentCount');
            if (agentCountElement) {
                agentCountElement.textContent = monitoringData.agent_count;
            }
        }
        
        // Update advanced charts with data
        this.updateAdvancedCharts();
        
        // Check for alerts based on real data
        this.checkForAlerts(monitoringData.avg_response_time || 0, monitoringData.error_rate || 0);
    }

    resetAllChartsToZero() {
        // Reset all monitoring charts to zero when WebSocket disconnects
        try {
            const currentTime = this.formatTimestamp(new Date(), false, false);
            
            // Reset real-time monitoring charts
            if (this.charts.realtimePerformance) {
                this.updateChart(this.charts.realtimePerformance, currentTime, 0);
            }
            if (this.charts.networkActivity) {
                this.updateChart(this.charts.networkActivity, currentTime, 0);
            }
            if (this.charts.errorRate) {
                this.updateChart(this.charts.errorRate, currentTime, 0);
            }
            if (this.charts.successRate) {
                this.updateChart(this.charts.successRate, currentTime, 0);
            }
            
            // Reset advanced charts
            if (this.charts.responseTimeDist) {
                this.charts.responseTimeDist.data.datasets[0].data = [0, 0, 0, 0];
                this.charts.responseTimeDist.update();
            }
            if (this.charts.loadBalancing) {
                this.charts.loadBalancing.data.labels = [];
                this.charts.loadBalancing.data.datasets[0].data = [];
                this.charts.loadBalancing.update();
            }
            if (this.charts.resourceUtil) {
                this.charts.resourceUtil.data.datasets[0].data = [0, 0, 0, 0];
                this.charts.resourceUtil.update();
            }
            
            // Reset monitoring metrics to zero
            this.monitoringData.latestMetrics = {
                avg_response_time: 0,
                total_requests: 0,
                error_rate: 0,
                agent_count: 0,
                response_time_distribution: { fast: 0, medium: 0, slow: 0, very_slow: 0 },
                load_balancing: {},
                resource_utilization: { cpu: 0, memory: 0, network: 0, storage: 0 }
            };
            
            // Update metric summaries to show zero values
            this.updateMetricSummaries(0, 0, 0);
            
            // console.log('All charts reset to zero due to WebSocket disconnection');
        } catch (error) {
            console.error('Error resetting charts to zero:', error);
        }
    }

    calculateResponseTimeDistribution(agentMetrics) {
        // Calculate response time distribution from agent metrics
        if (!agentMetrics || agentMetrics.length === 0) {
            return { fast: 0, medium: 0, slow: 0, very_slow: 0 };
        }
        
        let fast = 0, medium = 0, slow = 0, verySlow = 0;
        
        agentMetrics.forEach(metrics => {
            const responseTime = metrics.avg_response_time || metrics.average_response_time || 0;
            if (responseTime < 100) fast++;
            else if (responseTime < 500) medium++;
            else if (responseTime < 1000) slow++;
            else verySlow++;
        });
        
        const total = agentMetrics.length;
        return {
            fast: total > 0 ? (fast / total) * 100 : 0,
            medium: total > 0 ? (medium / total) * 100 : 0,
            slow: total > 0 ? (slow / total) * 100 : 0,
            very_slow: total > 0 ? (verySlow / total) * 100 : 0
        };
    }

    calculateLoadBalancing(agentMetrics) {
        // Calculate load balancing data from agent metrics
        if (!agentMetrics || agentMetrics.length === 0) {
            return {};
        }
        
        const loadByAgent = {};
        agentMetrics.forEach(metrics => {
            const agentId = metrics.agent_id;
            const requests = metrics.total_requests || metrics.requests_processed || 0;
            const responseTime = metrics.avg_response_time || metrics.average_response_time || 0;
            
            // Calculate load score based on requests and response time
            // Higher requests = higher load, higher response time = higher load
            const loadScore = requests + (responseTime / 100); // Normalize response time
            loadByAgent[agentId] = Math.min(100, loadScore); // Cap at 100%
        });
        
        return loadByAgent;
    }

    updateSystemHealth(healthData) {
        // Always store the latest health data, even if paused
        this.monitoringData.systemHealth = {
            arcp: healthData.status === 'healthy',
            redis: healthData.components?.storage?.redis === 'connected',
            ai: healthData.components?.ai_services?.status === 'healthy',
            websocket: this.websocket?.readyState === WebSocket.OPEN
        };
        
        // Only update UI if monitoring is not paused
        if (!this.isPaused) {
            this.updateSystemHealthIndicators();
        } else {
            // console.log('Monitoring paused - health data stored but UI not updated');
        }
    }

    addAlert(alertData) {
        // Handle both WebSocket format {alerts: [...]} and single alert objects
        let alertsToAdd = [];
        
        if (alertData.alerts && Array.isArray(alertData.alerts)) {
            // WebSocket format: {alerts: [alert1, alert2, ...]}
            alertsToAdd = alertData.alerts;
        } else if (alertData.title || alertData.message) {
            // Single alert object
            alertsToAdd = [alertData];
        }
        
        // Defensive: ensure monitoringData and alertQueue are always defined
        if (!this.monitoringData) {
            this.monitoringData = { alertQueue: [] };
        }
        if (!this.monitoringData.alertQueue) {
            this.monitoringData.alertQueue = [];
        }
        
        for (const alert of alertsToAdd) {
            // Normalize severity/type
            const rawSeverity = (alert.severity || alert.type || 'warning').toString().toLowerCase();
            let normalizedSeverity = rawSeverity;
            if (normalizedSeverity === 'error' || normalizedSeverity === 'danger') normalizedSeverity = 'critical';
            if (!['critical', 'warning', 'info'].includes(normalizedSeverity)) normalizedSeverity = 'info';
            const normalizedType = (alert.type || 'general').toString().toLowerCase();
            
            // Validate and normalize alert data
            const normalizedAlert = {
                id: alert.id || (Date.now() + Math.random()),
                title: alert.title || this.generateAlertTitle(alert),
                message: alert.message || 'No message provided',
                severity: normalizedSeverity,
                type: normalizedType,
                timestamp: alert.timestamp || new Date().toISOString()
            };
            
            // Create a unique key for alert suppression
            const suppressionKey = `${normalizedAlert.type}:${normalizedAlert.message}`;
            
            // For WebSocket connection alerts, use a more specific key
            let finalSuppressionKey = suppressionKey;
            if (normalizedAlert.title?.toLowerCase().includes('dashboard connection') ||
                normalizedAlert.message.toLowerCase().includes('websocket') ||
                normalizedAlert.message.toLowerCase().includes('real-time updates')) {
                finalSuppressionKey = 'websocket_connection_lost'; // Use a unified key for all WebSocket connection issues
            }
            
            const now = Date.now();
            
            // Determine suppression time based on alert type and severity
            let suppressionTime = 10000; // Default 10 seconds
            
            // Special handling for different alert types
            if (normalizedAlert.type === 'system_health' || 
                normalizedAlert.message.toLowerCase().includes('system health') ||
                normalizedAlert.message.toLowerCase().includes('unhealthy') ||
                normalizedAlert.message.toLowerCase().includes('degraded')) {
                suppressionTime = 300000; // 5 minutes for system health
            } else if (normalizedAlert.type === 'storage' ||
                      normalizedAlert.message.toLowerCase().includes('redis') ||
                      normalizedAlert.message.toLowerCase().includes('database') ||
                      normalizedAlert.message.toLowerCase().includes('connection failed')) {
                suppressionTime = 180000; // 3 minutes for storage issues
            } else if (normalizedAlert.type === 'agent_connectivity' &&
                      normalizedAlert.message.toLowerCase().includes('no agents registered')) {
                suppressionTime = 900000; // 15 minutes for "no agents" - it's expected during startup
            } else if (normalizedAlert.type === 'agent_connectivity') {
                suppressionTime = 120000; // 2 minutes for other agent connectivity issues
            } else if (normalizedAlert.title?.toLowerCase().includes('dashboard connection') ||
                      normalizedAlert.message.toLowerCase().includes('websocket') ||
                      normalizedAlert.message.toLowerCase().includes('real-time updates')) {
                suppressionTime = 300000; // 5 minutes for WebSocket connection issues - avoid spam during disconnections
            } else if (normalizedAlert.severity === 'critical') {
                suppressionTime = 60000; // 1 minute for critical alerts
            } else if (normalizedAlert.severity === 'warning') {
                suppressionTime = 180000; // 3 minutes for warning alerts
            } else if (normalizedAlert.severity === 'info') {
                suppressionTime = 300000; // 5 minutes for info alerts
            }
            
            // Check suppression map
            if (this.alertSuppressionMap[finalSuppressionKey] && 
                (now - this.alertSuppressionMap[finalSuppressionKey]) < suppressionTime) {
                // console.log(`Alert suppressed: ${finalSuppressionKey} (${suppressionTime/1000}s remaining)`);
                continue; // Skip this alert - it's suppressed
            }
            
            // Also check existing alerts for duplicates (backup check)
            const isDuplicate = this.monitoringData.alertQueue.some(existingAlert => {
                // For WebSocket alerts, check if any WebSocket connection alert exists in recent timeframe
                if (finalSuppressionKey === 'websocket_connection_lost') {
                    return (existingAlert.title?.toLowerCase().includes('dashboard connection') ||
                           existingAlert.message.toLowerCase().includes('websocket') ||
                           existingAlert.message.toLowerCase().includes('real-time updates')) &&
                           (new Date() - new Date(existingAlert.timestamp)) < suppressionTime;
                }
                // For other alerts, use exact matching
                return existingAlert.message === normalizedAlert.message && 
                       existingAlert.type === normalizedAlert.type &&
                       (new Date() - new Date(existingAlert.timestamp)) < suppressionTime;
            });
            if (isDuplicate) {
                // console.log(`Duplicate alert found: ${finalSuppressionKey}`);
                continue;
            }
            
            // Update suppression map
            this.alertSuppressionMap[finalSuppressionKey] = now;
            
            // Clean up old suppression entries (older than 10 minutes)
            Object.keys(this.alertSuppressionMap).forEach(key => {
                if (now - this.alertSuppressionMap[key] > 600000) {
                    delete this.alertSuppressionMap[key];
                }
            });
            
            // Add to alerts queue for display in alerts tab
            this.monitoringData.alertQueue.unshift(normalizedAlert);
            
            // Show toast notification for immediate feedback (but limit frequency)
            this.showToastWithRateLimit(normalizedAlert.message, normalizedAlert.severity === 'critical' ? 'danger' : 'warning');
            
            // Send client-generated alert to backend for persistence
            try {
                if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
                    this.websocket.send(JSON.stringify({
                        type: 'dashboard_alert',
                        timestamp: new Date().toISOString(),
                        data: normalizedAlert
                    }));
                }
            } catch (_) { /* ignore */ }

            // console.log(`Alert added: ${normalizedAlert.title} - ${normalizedAlert.message}`);
        }
        
        // Sort newest first by timestamp
        try {
            this.monitoringData.alertQueue.sort((a, b) => {
                const ta = new Date(a.timestamp).getTime() || 0;
                const tb = new Date(b.timestamp).getTime() || 0;
                return tb - ta;
            });
        } catch (_) { /* ignore */ }
        
        // Keep only last 50 alerts
        if (this.monitoringData.alertQueue.length > 50) {
            this.monitoringData.alertQueue = this.monitoringData.alertQueue.slice(0, 50);
        }
        
        // Persist alerts to localStorage
        this.saveAlertsToStorage();
        
        // Update alerts display if on alerts tab
        if (document.querySelector('.nav-item.active')?.dataset.tab === 'alerts') {
            this.renderAlerts();
        } else {
            this.renderAlerts(); // Always render for real-time updates
        }
        
        // Play sound if enabled in localStorage settings
        const settings = JSON.parse(localStorage.getItem('arcp-dashboard-settings') || '{}');
        if (settings.soundAlerts && alertsToAdd.some(alert => 
            (alert.severity && alert.severity.toLowerCase() === 'critical') ||
            (alert.type && alert.type.toLowerCase() === 'critical') ||
            (alert.severity && alert.severity.toLowerCase() === 'warning') ||
            (alert.type && alert.type.toLowerCase() === 'warning')
        )) {
            this.playAlertSound();
        }
    }

    /**
     * Save alerts to localStorage for persistence
     */
    saveAlertsToStorage() {
        try {
            const alertsData = {
                alerts: this.monitoringData.alertQueue || [],
                timestamp: Date.now()
            };
            localStorage.setItem('arcp-dashboard-alerts', JSON.stringify(alertsData));
        } catch (error) {
            console.warn('Failed to save alerts to localStorage:', error);
        }
    }

    /**
     * Load alerts from localStorage on page load
     */
    loadAlertsFromStorage() {
        try {
            const stored = localStorage.getItem('arcp-dashboard-alerts');
            if (!stored) return;
            
            const alertsData = JSON.parse(stored);
            if (!alertsData.alerts || !Array.isArray(alertsData.alerts)) return;
            
            // Ensure monitoringData exists
            if (!this.monitoringData) {
                this.monitoringData = { alertQueue: [] };
            }
            if (!this.monitoringData.alertQueue) {
                this.monitoringData.alertQueue = [];
            }
            
            // Add all loaded alerts to the queue
            this.monitoringData.alertQueue = alertsData.alerts;
            // Sort newest first
            try {
                this.monitoringData.alertQueue.sort((a, b) => {
                    const ta = new Date(a.timestamp).getTime() || 0;
                    const tb = new Date(b.timestamp).getTime() || 0;
                    return tb - ta;
                });
            } catch (_) { /* ignore */ }
            
            // Update the display if we're on the alerts tab
            this.renderAlerts();
        } catch (error) {
            console.warn('Failed to load alerts from localStorage:', error);
            // Remove corrupted data
            localStorage.removeItem('arcp-dashboard-alerts');
        }
    }

    /**
     * Clear all alerts and remove from localStorage
     */
    clearAllAlerts() {
        // Clear in-memory alerts
        if (this.monitoringData && this.monitoringData.alertQueue) {
            this.monitoringData.alertQueue = [];
        }
        
        // Clear persisted alerts
        localStorage.removeItem('arcp-dashboard-alerts');
        
        // Update display
        this.renderAlerts();
        
        // console.log('All alerts cleared');
    }

    updateLogs(logData) {
        if (logData.logs && Array.isArray(logData.logs)) {
            // Normalize log levels before assigning to ensure consistent styling
            this.logs = logData.logs.map(log => ({
                ...log,
                level: this.normalizeLogLevel(log.level)
            }));
            this.renderLogs();
            // Persist to localStorage for reload resilience
            try {
                if (this.authToken) {
                    localStorage.setItem('arcp-dashboard-logs', JSON.stringify({ logs: this.logs, ts: Date.now() }));
                }
            } catch (_) { /* ignore quota errors */ }
        }
    }

    normalizeLogLevel(level) {
        // Centralized log level normalization logic
        if (level === 'WARNING') {
            return 'WARN';
        } else if (level === 'ERROR') {
            return 'ERR';
        } else if (level === 'SUCCESS') {
            return 'SUCS';
        } else if (level === 'CRITICAL') {
            return 'CRIT';
        } else if (level === 'INFORMATION') {
            return 'INFO';
        }
        // Keep other levels as-is (INFO, WARN, ERR, SUCS, CRIT)
        return level;
    }

    // Map UI dropdown values to a set of acceptable normalized levels
    mapUILogLevelToAccepted(value) {
        const u = (value || '').toString().trim().toUpperCase();
        if (u === 'INFO' || u === 'INFORMATION') return ['INFO'];
        if (u === 'SUCCESS' || u === 'SUCS') return ['SUCS'];
        if (u === 'WARNING' || u === 'WARN') return ['WARN'];
        if (u === 'CRITICAL' || u === 'CRIT') return ['CRIT'];
        if (u === 'ERROR' || u === 'ERR') return ['ERR'];
        return [];
    }

    updateAgents(agentsData) {
        // Update the agents data from WebSocket
        if (agentsData && agentsData.agents && Array.isArray(agentsData.agents)) {
            this.agents = agentsData.agents;
            
            // Update agent statistics with fallback calculations
            if (agentsData.total_count !== undefined) {
                // Calculate actual alive/dead counts from the agents array as fallback
                let aliveCount = 0;
                let deadCount = 0;
                let agentTypesCounts = {};
                
                this.agents.forEach(agent => {
                    // Count status based on actual agent data
                    if (agent.status === 'alive') {
                        aliveCount++;
                    } else {
                        deadCount++;
                    }
                    
                    // Count types
                    const type = agent.agent_type || 'unknown';
                    agentTypesCounts[type] = (agentTypesCounts[type] || 0) + 1;
                });
                
                this.agentStats = {
                    total: agentsData.total_count,
                    // Use backend data if available, otherwise use our calculated values
                    active: agentsData.active_count || aliveCount,
                    types: agentsData.agent_types || agentTypesCounts,
                    status: agentsData.status_summary || { alive: aliveCount, dead: deadCount }
                };
                
                // Update DOM elements for statistics display
                this.updateAgentStatisticsDOM();
            }
            
            // Add agent status logs when agents are updated
            this.updateAgentLogs();
            
            // Always update agent type filter when agents change (regardless of active tab)
            this.updateAgentTypeFilter();
            
            // Always update recent activity when agents change
            this.updateRecentActivity();
            
            // Re-render agents if we're on the agents tab
            const activeTab = document.querySelector('.nav-item.active')?.dataset.tab;
            if (activeTab === 'agents') {
                this.filterAgents();
            }
            
            // :)
            if (this.isPaused === true) {
                return;
            }

            // Update agent status grid if we're on monitoring tab
            if (activeTab === 'monitoring') {
                this.updateAgentStatusGrid();
            }
            
            // Update charts with agent data
            this.updateChartsFromAgentData();
            
            // Update performance metrics display
            this.updatePerformanceMetrics();
        }
    }

    updateAgentLogs() {
        // Add logs for agent status (but only add new ones, avoid duplicates)
        const currentTime = new Date().toISOString();
        
        // Clear existing agent status logs to avoid duplicates
        this.logs = this.logs.filter(log => log.source !== 'agent_status');
        
        // Add current agent status logs
        this.agents.forEach(agent => {
            if (agent.status === 'alive') {
                this.logs.push({
                    timestamp: agent.last_seen || currentTime,
                    level: 'INFO',
                    message: `Agent ${agent.agent_id} (${agent.agent_type}) is alive`,
                    source: 'agent_status'
                });
            } else {
                this.logs.push({
                    timestamp: agent.last_seen || currentTime,
                    level: 'WARN',
                    message: `Agent ${agent.agent_id} (${agent.agent_type}) is dead`,
                    source: 'agent_status'
                });
            }
        });
        
        // Sort logs by timestamp (newest first) and limit to reasonable number
        this.logs.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
        if (this.logs.length > 100) {
            this.logs = this.logs.slice(0, 100);
        }
        
        // Re-render logs if we're on the logs tab
        const activeTab = document.querySelector('.nav-item.active')?.dataset.tab;
        if (activeTab === 'logs') {
            this.renderLogs();
        }
    }

    setAgentsStatusUnknown() {
        // When WebSocket disconnects, we don't know the real status of agents
        this.agents.forEach(agent => {
            agent.status = 'unknown';
            agent.last_seen = 'Connection Lost';
        });
        
        // Update agent statistics to reflect unknown status
        this.agentStats = {
            total: this.agents.length,
            active: 0,
            types: {},
            status: { unknown: this.agents.length }
        };
        
        // Re-render agents with unknown status
        this.renderAgents();
        this.updateAgentStatusGrid();
        this.updateAgentStatisticsDOM();
    }

    updateAgentStatisticsDOM() {
        // Update the statistics display using agent data from WebSocket
        if (!this.agentStats) return;
        
        // Update main statistics
        const totalElement = document.getElementById('totalAgents');
        if (totalElement) totalElement.textContent = this.agentStats.total || 0;
        
        const aliveElement = document.getElementById('aliveAgents');
        if (aliveElement) aliveElement.textContent = this.agentStats.active || 0;
        
        const deadElement = document.getElementById('deadAgents');
        if (deadElement) {
            // Calculate dead agents: total - active OR use status.dead
            let deadCount = this.agentStats.status?.dead || 0;
            // Fallback calculation if status_summary is wrong
            if (deadCount === 0 && this.agentStats.total > this.agentStats.active) {
                deadCount = this.agentStats.total - this.agentStats.active;
            }
            deadElement.textContent = deadCount;
        }
        
        const typesElement = document.getElementById('agentTypes');
        if (typesElement) {
            const typesCount = Object.keys(this.agentStats.types || {}).length;
            typesElement.textContent = typesCount;
        }
        
        // Debug log to help troubleshoot
        // console.log('Agent stats updated:', {
        //     total: this.agentStats.total,
        //     active: this.agentStats.active,
        //     status_summary: this.agentStats.status,
        //     types: this.agentStats.types
        // });
    }

    updateChartsFromAgentData() {
        // Update status chart using WebSocket agent data
        if (this.charts.status && this.agentStats) {
            const aliveCount = this.agentStats.active || 0;
            const deadCount = this.agentStats.status?.dead || 0;
            
            this.charts.status.data.datasets[0].data = [aliveCount, deadCount];
            this.charts.status.update();
        }

        // Update types chart using WebSocket agent data
        if (this.charts.types && this.agentStats?.types) {
            const agentTypes = this.agentStats.types;
            
            this.charts.types.data.labels = Object.keys(agentTypes);
            this.charts.types.data.datasets[0].data = Object.values(agentTypes);
            this.charts.types.update();
        }
        
        // Update performance metrics when agent data changes
        this.updatePerformanceMetrics();
    }

    stopPolling() {
        // Clear WebSocket retry timer to prevent unwanted reconnections
        if (this.websocketRetryTimer) {
            clearTimeout(this.websocketRetryTimer);
            this.websocketRetryTimer = null;
        }
        // Stop ping interval for WebSocket
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
            this.pingInterval = null;
        }
        // Stop connection health monitor
        if (this.connectionHealthInterval) {
            clearInterval(this.connectionHealthInterval);
            this.connectionHealthInterval = null;
        }
        
        // console.log('All monitoring intervals stopped');
    }

    async startMonitoring() {
        // Clear any existing intervals
        this.stopPolling();
        
        // Only start WebSocket monitoring if we have proper authentication
        if (this.authToken) {
            // Start WebSocket monitoring instead of polling (only if not already connected)
            if (!this.websocket || this.websocket.readyState !== WebSocket.OPEN) {
                this.setupMonitoringWebSocket();
            }
        } else {
            // console.log('Skipping WebSocket setup - authentication token not available');
        }
    }

    handleAgentListUpdate(agentList) {
        // Update local agent list with real-time data
        this.agents = agentList;
        this.filterAgents();
        this.updateAgentTypeFilter();
        this.updateRecentActivity();
        
        // Update stats if we're on the overview tab
        if (document.querySelector('.nav-item.active')?.dataset.tab === 'overview') {
            this.loadStats();
        }
    }

    updateConnectionStatus(connected) {
        const statusElement = document.getElementById('connectionStatus');
        if (statusElement) {
            const icon = statusElement.querySelector('i');
            const text = statusElement.querySelector('span');
            
            if (connected) {
                statusElement.classList.remove('disconnected');
                icon.className = 'fas fa-circle';
                text.textContent = 'Connected';
            } else {
                statusElement.classList.add('disconnected');
                icon.className = 'fas fa-exclamation-circle';
                text.textContent = 'Disconnected';
            }
        }
    }

    async loadInitialData() {
        this.showLoading(true);
        
        try {
            await Promise.all([
                this.loadStats(),
                this.loadLogs()
            ]);
        } catch (error) {
            console.error('Error loading initial data:', error);
            this.showError('Failed to load dashboard data');
        } finally {
            this.showLoading(false);
        }
    }

    async loadStats() {
        // Stats are provided via WebSocket monitoring frames
        // Initialize with default values, will be updated by WebSocket
        this.updateStats({
            total_requests: 0,
            avg_response_time: 0,
            error_rate: 0,
            active_agents: 0 // Will be updated by WebSocket agent data
        });
    }

    async loadLogs() {
        // Try to hydrate from localStorage only if admin is logged in
        try {
            if (this.authToken) {
                const cached = localStorage.getItem('arcp-dashboard-logs');
                if (cached) {
                    const parsed = JSON.parse(cached);
                    if (parsed && Array.isArray(parsed.logs)) {
                        this.logs = parsed.logs.map(log => ({
                            ...log,
                            level: this.normalizeLogLevel(log.level)
                        }));
                    }
                }
            }
        } catch (_) { /* ignore */ }

        // If still empty, seed with a basic entry
        if (!this.logs || this.logs.length === 0) {
            this.logs = [
                { timestamp: new Date().toISOString(), level: 'INFO', message: 'ARCP Dashboard initialized', source: 'system' },
            ];
        }

        // Sort logs by timestamp (newest first)
        this.logs.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
        this.renderLogs();
    }

    updateStats(statsResponse) {
        // Extract the registry_statistics from the API response
        const stats = statsResponse.registry_statistics || statsResponse;
        
        document.getElementById('totalAgents').textContent = stats.total_agents || 0;
        document.getElementById('aliveAgents').textContent = stats.alive_agents || 0;
        document.getElementById('deadAgents').textContent = stats.dead_agents || 0;
        
        // agent_types is an object, so count the keys
        const agentTypesCount = stats.agent_types ? Object.keys(stats.agent_types).length : 0;
        document.getElementById('agentTypes').textContent = agentTypesCount;

        this.updateChartsFromStats(statsResponse);
        this.updateRecentActivity();
    }

    renderAgents() {
        const agentsGrid = document.getElementById('agentsGrid');
        if (!agentsGrid) return;

        agentsGrid.innerHTML = '';

        // Get filter criteria
        const search = document.getElementById('agentSearch')?.value.toLowerCase() || '';
        const typeFilter = document.getElementById('agentTypeFilter')?.value || '';
        const statusFilter = document.getElementById('agentStatusFilter')?.value || '';

        // Filter agents first
        this.agentPagination.filteredAgents = this.agents.filter(agent => {
            const matchesSearch = !search ||
                (agent.name && agent.name.toLowerCase().includes(search)) ||
                (agent.agent_id && agent.agent_id.toLowerCase().includes(search)) ||
                (agent.endpoint && agent.endpoint.toLowerCase().includes(search));
            const matchesType = !typeFilter || agent.agent_type === typeFilter;
            const matchesStatus = !statusFilter || (agent.status || '').toLowerCase() === statusFilter.toLowerCase();
            return matchesSearch && matchesType && matchesStatus;
        });

        // Calculate pagination
        const totalAgents = this.agentPagination.filteredAgents.length;
        this.agentPagination.totalPages = Math.ceil(totalAgents / this.agentPagination.itemsPerPage);
        
        // Ensure current page is valid
        if (this.agentPagination.currentPage > this.agentPagination.totalPages) {
            this.agentPagination.currentPage = Math.max(1, this.agentPagination.totalPages);
        }

        // Calculate start and end indices for current page
        const startIndex = (this.agentPagination.currentPage - 1) * this.agentPagination.itemsPerPage;
        const endIndex = Math.min(startIndex + this.agentPagination.itemsPerPage, totalAgents);

        // Get agents for current page
        const currentPageAgents = this.agentPagination.filteredAgents.slice(startIndex, endIndex);

        // Render agent cards for current page
        currentPageAgents.forEach(agent => {
            const agentCard = this.createAgentCard(agent);
            agentsGrid.appendChild(agentCard);
        });

        // Update pagination controls
        this.updatePaginationControls();
    }

    createAgentCard(agent) {
        const card = document.createElement('div');
        card.className = `agent-card ${agent.status || 'dead'}`;
        card.dataset.agentId = agent.agent_id;
        card.dataset.agentType = agent.agent_type;
        card.dataset.status = agent.status || 'dead';
        
        // Handle unknown status and special display for disconnected state
        let lastSeenDisplay;
        let statusDisplay;
        
        if (agent.status === 'unknown') {
            lastSeenDisplay = agent.last_seen === 'Connection Lost' ? 'Connection Lost' : '???';
            statusDisplay = '???';
        } else {
            lastSeenDisplay = agent.last_seen ? this.formatTimestamp(agent.last_seen, true, true) : 'Never';
            statusDisplay = (agent.status || 'dead').toUpperCase();
        }

        card.innerHTML = `
            <div class="agent-header">
                <div class="agent-info">
                    <h4>${agent.name || agent.agent_id}</h4>
                    <p>${agent.agent_type}</p>
                </div>
                <span class="agent-status ${agent.status || 'dead'}">
                    ${statusDisplay}
                </span>
            </div>
            <div class="agent-details">
                <div class="agent-detail-item">
                    <strong>Endpoint:</strong>
                    <span>${agent.endpoint || 'N/A'}</span>
                </div>
                <div class="agent-detail-item">
                    <strong>Last Seen:</strong>
                    <span>${lastSeenDisplay}</span>
                </div>
                <div class="agent-detail-item">
                    <strong>Version:</strong>
                    <span>${agent.version || 'Unknown'}</span>
                </div>
            </div>
            <div class="agent-actions">
                <button class="btn btn-secondary btn-small" onclick="dashboard.viewAgentDetails('${agent.agent_id}')">
                    <i class="fas fa-eye"></i> Details
                </button>
                <button class="btn btn-secondary btn-small" onclick="dashboard.pingAgent('${agent.agent_id}')">
                    <i class="fas fa-satellite-dish"></i> Ping
                </button>
                <button class="btn btn-danger btn-small" onclick="dashboard.unregisterAgent('${agent.agent_id}')" title="Unregister Agent">
                    <i class="fas fa-trash"></i> Unregister
                </button>
            </div>
        `;

        return card;
    }

    updateAgentTypeFilter() {
        const filter = document.getElementById('agentTypeFilter');
        if (!filter) return;

        const selectedBefore = filter.value; // preserve user selection

        const setOptions = (types) => {
            const key = Array.isArray(types) ? types.join('|') : '';
            if (this.lastTypeOptionsKey === key) {
                // No change in available types; keep current selection
                return;
            }
            // Clear existing options except "All Types"
            while (filter.children.length > 1) {
                filter.removeChild(filter.lastChild);
            }
            (types || []).forEach(type => {
                const option = document.createElement('option');
                option.value = type;
                option.textContent = type;
                filter.appendChild(option);
            });
            // Restore prior selection if it's still available
            if (selectedBefore && types && types.includes(selectedBefore)) {
                filter.value = selectedBefore;
            }
            this.lastTypeOptionsKey = key;
        };

        // If cached, use it immediately without altering selection
        if (Array.isArray(this.allowedTypesCache) && this.allowedTypesCache.length) {
            setOptions(this.allowedTypesCache);
            return;
        }
        // Prevent duplicate concurrent fetches
        if (this.allowedTypesFetchPromise) {
            this.allowedTypesFetchPromise.then((types) => {
                if (Array.isArray(types) && types.length) {
                    setOptions(types);
                }
            }).catch(() => {
                const discovered = [...new Set(this.agents.map(agent => agent.agent_type).filter(Boolean))];
                setOptions(discovered);
            });
            return;
        }
        // Throttle requests if function is called frequently
        const now = Date.now();
        if (this.allowedTypesFetchedAt && (now - this.allowedTypesFetchedAt) < 30000) { // 30s throttle
            const discovered = [...new Set(this.agents.map(agent => agent.agent_type).filter(Boolean))];
            setOptions(discovered);
            return;
        }
        this.allowedTypesFetchPromise = fetch(`${this.apiBase}/public/agent_types`)
            .then(resp => resp.ok ? resp.json() : null)
            .then(data => {
                const types = data && Array.isArray(data.allowed_agent_types) ? data.allowed_agent_types : null;
                if (types && types.length) {
                    this.allowedTypesCache = types;
                    this.allowedTypesFetchedAt = Date.now();
                    setOptions(types);
                    return types;
                } else {
                    const discovered = [...new Set(this.agents.map(agent => agent.agent_type).filter(Boolean))];
                    setOptions(discovered);
                    return discovered;
                }
            })
            .catch(() => {
                const discovered = [...new Set(this.agents.map(agent => agent.agent_type).filter(Boolean))];
                setOptions(discovered);
                return discovered;
            })
            .finally(() => {
                this.allowedTypesFetchPromise = null;
            });
    }

    filterAgents() {
        // Reset to first page when filtering
        this.agentPagination.currentPage = 1;
        this.renderAgents();
    }

    updatePaginationControls() {
        const paginationControls = document.getElementById('agentPaginationControls');
        const paginationInfo = document.getElementById('paginationInfo');
        const currentPageNumber = document.getElementById('currentPageNumber');
        const totalPagesNumber = document.getElementById('totalPagesNumber');
        const prevBtn = document.getElementById('prevPageBtn');
        const nextBtn = document.getElementById('nextPageBtn');

        if (!paginationControls) return;

        const totalAgents = this.agentPagination.filteredAgents.length;
        
        // Show/hide pagination controls based on whether pagination is needed
        if (totalAgents <= this.agentPagination.itemsPerPage) {
            paginationControls.style.display = 'none';
            return;
        } else {
            paginationControls.style.display = 'flex';
        }

        // Update pagination info
        const startIndex = (this.agentPagination.currentPage - 1) * this.agentPagination.itemsPerPage;
        const endIndex = Math.min(startIndex + this.agentPagination.itemsPerPage, totalAgents);
        
        if (paginationInfo) {
            paginationInfo.textContent = `Showing ${startIndex + 1}-${endIndex} of ${totalAgents} agents`;
        }

        if (currentPageNumber) {
            currentPageNumber.textContent = this.agentPagination.currentPage;
        }

        if (totalPagesNumber) {
            totalPagesNumber.textContent = this.agentPagination.totalPages;
        }

        // Update button states
        if (prevBtn) {
            prevBtn.disabled = this.agentPagination.currentPage <= 1;
        }

        if (nextBtn) {
            nextBtn.disabled = this.agentPagination.currentPage >= this.agentPagination.totalPages;
        }
    }

    goToPreviousPage() {
        if (this.agentPagination.currentPage > 1) {
            this.agentPagination.currentPage--;
            this.renderAgents();
        }
    }

    goToNextPage() {
        if (this.agentPagination.currentPage < this.agentPagination.totalPages) {
            this.agentPagination.currentPage++;
            this.renderAgents();
        }
    }

    goToPage(pageNumber) {
        if (pageNumber >= 1 && pageNumber <= this.agentPagination.totalPages) {
            this.agentPagination.currentPage = pageNumber;
            this.renderAgents();
        }
    }

    initializeCharts() {
        // Destroy existing charts to prevent infinite increase
        if (this.charts.status) {
            this.charts.status.destroy();
            this.charts.status = null;
        }
        if (this.charts.types) {
            this.charts.types.destroy();
            this.charts.types = null;
        }
        if (this.charts.performance) {
            this.charts.performance.destroy();
            this.charts.performance = null;
        }

        this.createStatusChart();
        this.createTypesChart();
        this.createPerformanceChart();
    }

    createStatusChart() {
        const ctx = document.getElementById('statusChart');
        if (!ctx) return;

        this.charts.status = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['alive', 'dead'],
                datasets: [{
                    data: [0, 0],
                    backgroundColor: ['#4caf50', '#f44336'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });
    }

    createTypesChart() {
        const ctx = document.getElementById('typesChart');
        if (!ctx) return;

        this.charts.types = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [{
                    label: 'Agents by Type',
                    data: [],
                    backgroundColor: '#667eea',
                    borderColor: '#764ba2',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1
                        }
                    }
                }
            }
        });
    }

    createPerformanceChart() {
        const ctx = document.getElementById('performanceChart');
        if (!ctx) return;

        this.charts.performance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Response Time (ms)',
                    data: [],
                    borderColor: '#667eea',
                    backgroundColor: 'rgba(102, 126, 234, 0.1)',
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        });
    }

    updateChartsFromStats(statsResponse) {
        // Extract the registry_statistics from the API response
        const stats = statsResponse.registry_statistics || statsResponse;
        
        // Update status chart
        if (this.charts.status) {
            this.charts.status.data.datasets[0].data = [
                stats.alive_agents || 0,
                stats.dead_agents || 0
            ];
            this.charts.status.update();
        }

        // Update types chart
        if (this.charts.types && stats.agent_types) {
            // Use the agent_types from the API response
            const agentTypes = stats.agent_types || {};
            
            this.charts.types.data.labels = Object.keys(agentTypes);
            this.charts.types.data.datasets[0].data = Object.values(agentTypes);
            this.charts.types.update();
        }
    }

    // ===== REAL-TIME MONITORING FUNCTIONALITY =====

    async initializeMonitoring() {
        this.soundAlertsEnabled = this.settings.soundAlerts;
        // Setup sound alerts toggle checkbox listener
        const soundAlertsCheckbox = document.getElementById('soundAlerts');
        if (soundAlertsCheckbox) {
            soundAlertsCheckbox.checked = this.soundAlertsEnabled;
            soundAlertsCheckbox.addEventListener('change', (e) => {
                this.soundAlertsEnabled = e.target.checked;
                this.settings.soundAlerts = this.soundAlertsEnabled;
                // Do NOT call this.saveSettingsToStorage() here!
            });
        }
        
        // Initialize monitoring state
        this.isPaused = false;
        
        // Initialize charts and event listeners
        this.initializeMonitoringCharts();
        this.setupMonitoringEventListeners();
        
        // Start connection health monitor
        this.startConnectionHealthMonitor();
        
        // Initialize performance metrics display
        this.updatePerformanceMetrics();
        
        // Initialize monitoring status
        this.updateMonitoringStatus();
        
        this.addLog('INFO', 'Monitoring initialized');
        
        // WebSocket monitoring is already started in continueInit(), no need to call startMonitoring() again
    }

    setupMonitoringEventListeners() {
        // Pause/Resume monitoring button with PIN protection
        const pauseBtn = document.getElementById('pauseMonitoring');
        if (pauseBtn) {
            // Remove any existing onclick handlers to prevent double-execution
            pauseBtn.removeAttribute('onclick');
            
            pauseBtn.addEventListener('click', async (e) => {
                e.preventDefault();
                e.stopPropagation();
                // PIN protection for pause/resume monitoring
                await this.requirePin(async () => {
                    this.toggleMonitoring();
                });
            });
        }

        // Status filter buttons
        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                this.filterAgentStatus(e.target.dataset.filter);
            });
        });

        // Time range selector
        const timeRangeSelect = document.getElementById('metricsTimeRange');
        if (timeRangeSelect) {
            timeRangeSelect.addEventListener('change', (e) => {
                this.updateTimeRange(e.target.value);
            });
        }
    }

    initializeMonitoringCharts() {
        // Clean up existing monitoring charts to prevent memory leaks
        const monitoringChartNames = [
            'realtimePerformance', 'networkActivity', 'errorRate',
            'responseTimeDist', 'loadBalancing', 'successRate', 'resourceUtil'
        ];
        monitoringChartNames.forEach(chartName => {
            if (this.charts[chartName]) {
                this.charts[chartName].destroy();
                delete this.charts[chartName];
            }
        });
        
        // Real-time Performance Chart
        this.createRealtimePerformanceChart();
        
        // Network Activity Chart
        this.createNetworkActivityChart();
        
        // Error Rate Chart
        this.createErrorRateChart();
        
        // Advanced Charts
        this.createResponseTimeDistChart();
        this.createLoadBalancingChart();
        this.createSuccessRateChart();
        this.createResourceUtilChart();
    }

    createRealtimePerformanceChart() {
        const ctx = document.getElementById('realtimePerformanceChart');
        if (!ctx) return;

        this.charts.realtimePerformance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Response Time (ms)',
                    data: [],
                    borderColor: '#667eea',
                    backgroundColor: 'rgba(102, 126, 234, 0.1)',
                    tension: 0.4,
                    fill: true
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        display: false
                    },
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Response Time (ms)'
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    }
                },
                animation: {
                    duration: 0
                }
            }
        });
    }

    createNetworkActivityChart() {
        const ctx = document.getElementById('networkActivityChart');
        if (!ctx) return;

        this.charts.networkActivity = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [{
                    label: 'Requests/min',
                    data: [],
                    backgroundColor: 'rgba(76, 175, 80, 0.8)',
                    borderColor: '#4caf50',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        display: false
                    },
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Requests/min'
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    }
                },
                animation: {
                    duration: 300
                }
            }
        });
    }

    createErrorRateChart() {
        const ctx = document.getElementById('errorRateChart');
        if (!ctx) return;

        this.charts.errorRate = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Error Rate (%)',
                    data: [],
                    borderColor: '#f44336',
                    backgroundColor: 'rgba(244, 67, 54, 0.1)',
                    tension: 0.4,
                    fill: true
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        display: false
                    },
                    y: {
                        beginAtZero: true,
                        max: 100,
                        title: {
                            display: true,
                            text: 'Error Rate (%)'
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    }
                },
                animation: {
                    duration: 0
                }
            }
        });
    }

    createResponseTimeDistChart() {
        const ctx = document.getElementById('responseTimeDistChart');
        if (!ctx) return;

        this.charts.responseTimeDist = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['< 100ms', '100-500ms', '500ms-1s', '> 1s'],
                datasets: [{
                    data: [0, 0, 0, 0],
                    backgroundColor: [
                        '#4caf50',
                        '#ff9800',
                        '#f44336',
                        '#9c27b0'
                    ]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });
    }

    createLoadBalancingChart() {
        const ctx = document.getElementById('loadBalancingChart');
        if (!ctx) return;

        this.charts.loadBalancing = new Chart(ctx, {
            type: 'bar', // radar ??
            data: {
                labels: [],
                datasets: [{
                    label: 'Load Distribution',
                    data: [],
                    backgroundColor: 'rgba(102, 126, 234, 0.8)',
                    borderColor: '#667eea',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        title: {
                            display: true,
                            text: 'Agents'
                        }
                    },
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Load Score'
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });
    }

    createSuccessRateChart() {
        const ctx = document.getElementById('successRateChart');
        if (!ctx) return;

        this.charts.successRate = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Success Rate (%)',
                    data: [],
                    borderColor: '#4caf50',
                    backgroundColor: 'rgba(76, 175, 80, 0.1)',
                    tension: 0.4,
                    fill: true
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100
                    }
                },
                animation: {
                    duration: 300
                }
            }
        });
    }

    createResourceUtilChart() {
        const ctx = document.getElementById('resourceUtilChart');
        if (!ctx) return;

        this.charts.resourceUtil = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: ['CPU', 'Memory', 'Network', 'Storage'],
                datasets: [{
                    label: 'Utilization (%)',
                    data: [0, 0, 0, 0],
                    backgroundColor: [
                        'rgba(102, 126, 234, 0.8)',
                        'rgba(255, 152, 0, 0.8)',
                        'rgba(76, 175, 80, 0.8)',
                        'rgba(244, 67, 54, 0.8)'
                    ]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100
                    }
                }
            }
        });
    }

    toggleMonitoring() {
        const pauseBtn = document.getElementById('pauseMonitoring');
        const icon = pauseBtn?.querySelector('i');
        const text = pauseBtn?.querySelector('span') || pauseBtn;
        
        // Toggle the state
        this.isPaused = !this.isPaused;
        
        // Add to global window for debugging
        window.monitoringPaused = this.isPaused;
                
        if (this.isPaused) {
            // PAUSE MONITORING
            this.pauseMonitoring();
            
            // Update button UI
            if (icon) icon.className = 'fas fa-play';
            if (text) text.textContent = ' Resume';
            if (pauseBtn) {
                pauseBtn.classList.remove('btn-secondary');
                pauseBtn.classList.add('btn-success');
                pauseBtn.title = 'Resume real-time monitoring';
            }
        } else {
            // RESUME MONITORING
            this.resumeMonitoring();
            
            // Update button UI
            if (icon) icon.className = 'fas fa-pause';
            if (text) text.textContent = ' Pause';
            if (pauseBtn) {
                pauseBtn.classList.remove('btn-success');
                pauseBtn.classList.add('btn-secondary');
                pauseBtn.title = 'Pause real-time monitoring';
            }
        }
        
        // Update all monitoring status indicators
        this.updateMonitoringStatus();
    }

    pauseMonitoring() {
        // console.log('Pausing monitoring...');
        
        // Add body class for visual enhancements
        document.body.classList.add('monitoring-paused');
        
        // Clear connection health monitor
        if (this.connectionHealthInterval) {
            clearInterval(this.connectionHealthInterval);
            this.connectionHealthInterval = null;
        }
        
        // Send pause request to backend via WebSocket
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            // console.log('Sending pause request to dashboard backend');
            this.websocket.send(JSON.stringify({
                type: 'pause_monitoring',
                timestamp: new Date().toISOString(),
                data: { paused: true }
            }));
        }
        
        // Clear chart animations and updates
        this.pauseChartUpdates();
        
        // Update system health indicators to show paused state
        this.updateSystemHealthIndicators();
    }

    resumeMonitoring() {
        // console.log('Resuming monitoring...');
        
        // Remove body class for visual enhancements
        document.body.classList.remove('monitoring-paused');
        
        // Send resume request to backend via WebSocket
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            // console.log('Sending resume request to dashboard backend');
            this.websocket.send(JSON.stringify({
                type: 'resume_monitoring',
                timestamp: new Date().toISOString(),
                data: { paused: false }
            }));
        }
        
        // Restart connection health monitor
        this.startConnectionHealthMonitor();
        
        // Resume chart updates
        this.resumeChartUpdates();
        
        // Update system health indicators
        this.updateSystemHealthIndicators();
        
        // Trigger immediate data refresh
        this.refreshChartsWithLastData();
    }

    pauseChartUpdates() {
        // Add visual indicators to charts that they are paused
        Object.values(this.charts).forEach(chart => {
            if (chart && chart.canvas) {
                chart.canvas.style.opacity = '0.5';
                chart.canvas.style.filter = 'grayscale(50%)';
            }
        });
        
        // Add CSS for monitoring paused state if not already added
        this.addMonitoringPausedCSS();
        
        // Add overlay to monitoring content sections but NOT the header
        const monitoringTab = document.querySelector('#monitoring');
        if (monitoringTab) {
            // Apply overlay to specific content sections, excluding the header
            const sectionsToOverlay = [
                '.header-left',
                '.live-metrics-grid',
                '.agent-status-section',
                '.advanced-metrics-section'
            ];
            
            sectionsToOverlay.forEach(selectorText => {
                const section = monitoringTab.querySelector(selectorText);
                if (section && !section.querySelector('.monitoring-paused-overlay')) {
                    const overlay = document.createElement('div');
                    overlay.className = 'monitoring-paused-overlay';
                    overlay.innerHTML = `
                        <div class="pause-indicator">
                            <i class="fas fa-pause-circle"></i>
                            <span>Monitoring Paused</span>
                            <small>Charts and updates are suspended</small>
                            <small style="margin-top: 8px; font-weight: bold;">Use controls to resume</small>
                        </div>
                    `;
                    section.style.position = 'relative';
                    section.appendChild(overlay);
                }
            });
            
            // Ensure header controls remain accessible
            const monitoringHeader = monitoringTab.querySelector('.monitoring-header');
            if (monitoringHeader) {
                // Specifically ensure pause and export buttons are accessible
                const pauseBtn = document.getElementById('pauseMonitoring');
                const exportBtn = document.getElementById('exportMonitoringData');
                
                if (pauseBtn) {
                    pauseBtn.style.position = 'relative';
                    pauseBtn.style.zIndex = '10000'; // Highest priority
                    pauseBtn.style.pointerEvents = 'auto';
                }
                
                if (exportBtn) {
                    exportBtn.style.position = 'relative';
                    exportBtn.style.zIndex = '10000'; // Highest priority
                    exportBtn.style.pointerEvents = 'auto';
                }
            }
        }
    }

    addMonitoringPausedCSS() {
        // Check if styles already exist
        if (document.getElementById('monitoring-paused-styles')) return;
        
        const styles = document.createElement('style');
        styles.id = 'monitoring-paused-styles';
        styles.textContent = `
            .monitoring-paused-overlay {
                position: absolute !important;
                top: 0 !important;
                left: 0 !important;
                right: 0 !important;
                bottom: 0 !important;
                background: rgba(0, 0, 0, 0.3) !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                z-index: 1000 !important;
                pointer-events: all !important;
                backdrop-filter: blur(2px) !important;
                cursor: not-allowed !important;
            }
            
            /* Disable all interactions in paused sections */
            body.monitoring-paused .live-metrics-grid,
            body.monitoring-paused .agent-status-section,
            body.monitoring-paused .advanced-metrics-section,
            body.monitoring-paused .header-left {
                pointer-events: none !important;
                user-select: none !important;
            }
            
            /* Disable hover effects on all interactive elements when paused */
            body.monitoring-paused .live-metrics-grid *:hover,
            body.monitoring-paused .agent-status-section *:hover,
            body.monitoring-paused .advanced-metrics-section *:hover,
            body.monitoring-paused .header-left *:hover {
                background-color: inherit !important;
                color: inherit !important;
                transform: none !important;
                box-shadow: inherit !important;
                border-color: inherit !important;
                opacity: inherit !important;
            }
            
            /* Disable button hover states when paused */
            body.monitoring-paused .live-metrics-grid button:hover,
            body.monitoring-paused .agent-status-section button:hover,
            body.monitoring-paused .advanced-metrics-section button:hover,
            body.monitoring-paused .header-left button:hover {
                background: inherit !important;
                color: inherit !important;
                box-shadow: none !important;
                transform: none !important;
                cursor: not-allowed !important;
            }
            
            /* Disable card hover effects when paused */
            body.monitoring-paused .metric-card:hover,
            body.monitoring-paused .chart-card:hover,
            body.monitoring-paused .agent-status-card:hover {
                transform: none !important;
                box-shadow: inherit !important;
                background: inherit !important;
            }
            
            /* Ensure main dashboard header stays on top */
            .dashboard-header {
                position: relative !important;
                z-index: 10001 !important;
            }
            
            /* Ensure dashboard navigation stays accessible */
            .dashboard-nav {
                position: relative !important;
                z-index: 10001 !important;
            }
            
            .pause-indicator {
                background: rgba(255, 193, 7, 0.95) !important;
                color: #000 !important;
                padding: 20px 30px !important;
                border-radius: 10px !important;
                text-align: center !important;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3) !important;
                border: 2px solid #ffc107 !important;
            }
            
            .pause-indicator i {
                font-size: 2rem !important;
                display: block !important;
                margin-bottom: 10px !important;
            }
            
            .pause-indicator span {
                font-size: 1.2rem !important;
                font-weight: bold !important;
                display: block !important;
                margin-bottom: 5px !important;
            }
            
            .pause-indicator small {
                font-size: 0.9rem !important;
                opacity: 0.8 !important;
                display: block !important;
            }
            
            /* Ensure monitoring header and buttons remain accessible */
            .monitoring-header {
                position: relative !important;
                z-index: 9999 !important;
                pointer-events: auto !important;
            }
            
            #pauseMonitoring, 
            #exportMonitoringData {
                position: relative !important;
                z-index: 10000 !important;
                pointer-events: auto !important;
                opacity: 1 !important;
                filter: none !important;
            }
            
            .monitoring-controls {
                position: relative !important;
                z-index: 10000 !important;
                pointer-events: auto !important;
            }
            
            body.monitoring-paused .live-metrics-grid *,
            body.monitoring-paused .agent-status-section *,
            body.monitoring-paused .advanced-metrics-section *,
            body.monitoring-paused .header-left * {
                pointer-events: none !important;
                user-select: none !important;
                cursor: default !important;
            }
            
            /* Override any existing hover/focus/active states */
            body.monitoring-paused .live-metrics-grid *:hover,
            body.monitoring-paused .live-metrics-grid *:focus,
            body.monitoring-paused .live-metrics-grid *:active,
            body.monitoring-paused .agent-status-section *:hover,
            body.monitoring-paused .agent-status-section *:focus,
            body.monitoring-paused .agent-status-section *:active,
            body.monitoring-paused .advanced-metrics-section *:hover,
            body.monitoring-paused .advanced-metrics-section *:focus,
            body.monitoring-paused .advanced-metrics-section *:active,
            body.monitoring-paused .header-left *:hover,
            body.monitoring-paused .header-left *:focus,
            body.monitoring-paused .header-left *:active {
                background-color: inherit !important;
                color: inherit !important;
                transform: none !important;
                box-shadow: inherit !important;
                border-color: inherit !important;
                opacity: inherit !important;
                text-decoration: none !important;
                outline: none !important;
                cursor: default !important;
            }
            
            body.monitoring-paused .live-metrics-grid *,
            body.monitoring-paused .agent-status-section *,
            body.monitoring-paused .advanced-metrics-section *,
            body.monitoring-paused .header-left * {
                transition: none !important;
                animation: none !important;
            }
            
            /* Add visual emphasis to the pause button when monitoring is paused */
            body.monitoring-paused #pauseMonitoring {
                box-shadow: 0 0 10px rgba(255, 193, 7, 0.5) !important;
                border: 2px solid #ffc107 !important;
                pointer-events: auto !important;
                cursor: pointer !important;
            }
            
            /* Ensure export button remains clearly accessible when paused */
            body.monitoring-paused #exportMonitoringData {
                box-shadow: 0 0 5px rgba(0, 123, 255, 0.3) !important;
                pointer-events: auto !important;
                cursor: pointer !important;
            }
            
            .monitoring-status-badge.paused {
                background-color: #ffc107 !important;
                color: #000 !important;
                animation: pulse-warning 2s infinite !important;
            }
            
            @keyframes pulse-warning {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.7; }
            }
        `;
        document.head.appendChild(styles);
    }

    resumeChartUpdates() {
        // Remove visual indicators from charts
        Object.values(this.charts).forEach(chart => {
            if (chart && chart.canvas) {
                chart.canvas.style.opacity = '1';
                chart.canvas.style.filter = 'none';
            }
        });
        
        // Remove all overlays from monitoring sections
        const overlays = document.querySelectorAll('.monitoring-paused-overlay');
        overlays.forEach(overlay => {
            overlay.remove();
        });
        
        // Reset header and button styles
        const monitoringTab = document.querySelector('#monitoring');
        if (monitoringTab) {
            const monitoringHeader = monitoringTab.querySelector('.monitoring-header');
            if (monitoringHeader) {
                monitoringHeader.style.position = '';
                monitoringHeader.style.zIndex = '';
                monitoringHeader.style.pointerEvents = '';
            }
            
            // Reset button styles
            const pauseBtn = document.getElementById('pauseMonitoring');
            const exportBtn = document.getElementById('exportMonitoringData');
            
            if (pauseBtn) {
                pauseBtn.style.position = '';
                pauseBtn.style.zIndex = '';
                pauseBtn.style.pointerEvents = '';
            }
            
            if (exportBtn) {
                exportBtn.style.position = '';
                exportBtn.style.zIndex = '';
                exportBtn.style.pointerEvents = '';
            }
        }
        
        // Remove CSS when no longer needed
        this.removeMonitoringPausedCSS();
    }

    removeMonitoringPausedCSS() {
        const styles = document.getElementById('monitoring-paused-styles');
        if (styles) {
            styles.remove();
        }
    }

    updateMonitoringStatus() {
        // Update system health update indicator
        const systemHealthUpdate = document.getElementById('systemHealthUpdate');
        if (systemHealthUpdate) {
            if (this.isPaused) {
                systemHealthUpdate.textContent = 'Paused';
                systemHealthUpdate.style.color = '#ffc107';
                systemHealthUpdate.style.fontWeight = 'bold';
            } else {
                systemHealthUpdate.textContent = 'Live';
                systemHealthUpdate.style.color = '#28a745';
                systemHealthUpdate.style.fontWeight = 'normal';
            }
        }
        
        // Update connection status if paused
        const connectionStatus = document.getElementById('connectionStatus');
        if (connectionStatus && this.isPaused) {
            // connectionStatus.classList.add('paused');
            // // Update the text to show paused state
            // const text = connectionStatus.querySelector('span');
            // const icon = connectionStatus.querySelector('i');
            // if (text) text.textContent = 'Paused';
            // if (icon) icon.className = 'fas fa-pause-circle';
        } else if (connectionStatus) {
            // connectionStatus.classList.remove('paused');
            const text = connectionStatus.querySelector('span');
            const icon = connectionStatus.querySelector('i');
            if (this.websocket?.readyState === WebSocket.OPEN) {
                if (text) text.textContent = 'Connected';
                if (icon) icon.className = 'fas fa-circle';
            } else {
                if (text) text.textContent = 'Disconnected';
                if (icon) icon.className = 'fas fa-exclamation-circle';
            }
        }
        
        // Update any monitoring badges
        const monitoringBadges = document.querySelectorAll('.monitoring-status-badge');
        monitoringBadges.forEach(badge => {
            if (this.isPaused) {
                badge.classList.add('paused');
                badge.textContent = 'Paused';
            } else {
                badge.classList.remove('paused');
                badge.textContent = 'Live';
            }
        });
    }

    refreshChartsWithLastData() {
        // Use the last known data to refresh charts
        if (this.monitoringData.latestMetrics && !this.isPaused) {
            const currentTime = new Date().toLocaleTimeString();
            
            // Update charts with last known values
            const avgResponseTime = this.calculateAverageResponseTime();
            const networkActivity = this.calculateNetworkActivity();
            const errorRate = this.monitoringData.latestMetrics.error_rate || 0;
            
            // Only update if we have valid data and registered agents
            if (this.hasRegisteredAgents() && (avgResponseTime > 0 || networkActivity > 0 || errorRate > 0)) {
                this.updateChart(this.charts.realtimePerformance, currentTime, avgResponseTime);
                this.updateChart(this.charts.networkActivity, currentTime, networkActivity);
                this.updateChart(this.charts.errorRate, currentTime, errorRate * 100);
                
                // Update advanced charts
                this.updateAdvancedCharts();
                
                // Update metric summaries
                this.updateMetricSummaries(avgResponseTime, networkActivity, errorRate);
            } else if (!this.hasRegisteredAgents()) {
                // Clear charts when no agents are registered
                this.updateChart(this.charts.realtimePerformance, currentTime, 0);
                this.updateChart(this.charts.networkActivity, currentTime, 0);
                this.updateChart(this.charts.errorRate, currentTime, 0);
                this.updateMetricSummaries(0, 0, 0);
            }
        }
    }

    updateChart(chart, label, value) {
        if (!chart || !chart.data) {
            console.warn('Chart or chart data is not available');
            return;
        }
        
        // Validate the value
        const numericValue = Number(value);
        if (isNaN(numericValue)) {
            console.warn('Invalid chart value:', value);
            return;
        }
        
        chart.data.labels.push(label);
        chart.data.datasets[0].data.push(numericValue);
        
        // Use dynamic data point limit based on current time range
        const maxDataPoints = this.getDataPointLimit();
        if (chart.data.labels.length > maxDataPoints) {
            chart.data.labels.shift();
            chart.data.datasets[0].data.shift();
        }
        
        try {
            chart.update('none');
        } catch (error) {
            console.error('Error updating chart:', error);
        }
    }

    updateMetricSummaries(avgResponseTime, networkActivity, errorRate) {
        // Update performance summary
        const perfSummary = document.getElementById('perfSummary');
        if (perfSummary) {
            perfSummary.textContent = `Avg: ${avgResponseTime.toFixed(1)}ms`;
        }
        
        // Update network summary
        const networkSummary = document.getElementById('networkSummary');
        if (networkSummary) {
            networkSummary.textContent = `${networkActivity.toFixed(0)} req/min`;
        }
        
        // Update error summary
        const errorSummary = document.getElementById('errorSummary');
        if (errorSummary) {
            errorSummary.textContent = `${errorRate.toFixed(1)}%`;
        }
    }

    updateSystemHealthIndicators() {
        // Use health data from WebSocket frames instead of REST API
        const healthData = this.monitoringData?.systemHealth || {
            arcp: false,
            redis: false,
            ai: false,
            websocket: this.websocket?.readyState === WebSocket.OPEN
        };
        
        // If WebSocket is disconnected, show unknown status for all services
        if (!healthData.websocket) {
            this.updateHealthIndicator('arcpHealth', 'unknown', '???');
            this.updateHealthIndicator('redisHealth', 'unknown', '???');
            this.updateHealthIndicator('aiHealth', 'unknown', '???');
            this.updateHealthIndicator('websocketHealth', false, 'Disconnected');
            
            // Update header status badges
            this.updateStatusBadge('systemStatus', 'unknown', 'System Status Unknown');
            this.updateStatusBadge('dbStatus', 'unknown', 'Storage Status Unknown');
            this.updateStatusBadge('wsStatus', false, 'WebSocket Inactive');
        } else {
            // WebSocket is connected, show actual status
            this.updateHealthIndicator('arcpHealth', healthData.arcp, 
                healthData.arcp ? 'Online' : 'Degraded');
            
            this.updateHealthIndicator('redisHealth', healthData.redis, 
                healthData.redis ? 'Connected' : 'Disconnected');
            
            this.updateHealthIndicator('aiHealth', healthData.ai, 
                healthData.ai ? 'Available' : 'Unavailable');
            
            this.updateHealthIndicator('websocketHealth', healthData.websocket, 
                healthData.websocket ? 'Connected' : 'Disconnected');
            
            // Update header status badges
            this.updateStatusBadge('systemStatus', healthData.arcp, 
                healthData.arcp ? 'System Healthy' : 'System Degraded');
            this.updateStatusBadge('dbStatus', healthData.redis, 
                healthData.redis ? 'Storage Connected' : 'Storage Disconnected');
            this.updateStatusBadge('wsStatus', healthData.websocket, 
                healthData.websocket ? 'WebSocket Active' : 'WebSocket Inactive');
        }
        
        // Update the last update timestamp
        const updateElement = document.getElementById('systemHealthUpdate');
        if (updateElement) {
            updateElement.textContent = 'Up: ' + this.formatTimestamp(new Date(), false, false);
        }
    }

    getStatusClass(status) {
        // Normalize status for comparison - more robust handling
        const normalizedStatus = typeof status === "string" ? status.toLowerCase() : status;
        
        // Check each status category
        for (const [colorClass, statusValues] of Object.entries(STATUS_MAP)) {
            if (statusValues.includes(normalizedStatus)) {
                return `status-${colorClass}`;
            }
        }
        
        // Default to red for unknown status
        return 'status-red';
    }

    updateHealthIndicator(elementId, status, text) {
        const element = document.getElementById(elementId);
        if (!element) return;
        
        const statusClass = this.getStatusClass(status);
        element.innerHTML = `<i class="fas fa-circle ${statusClass}"></i> ${text}`;
    }

    updateStatusBadge(elementId, status, text) {
        const element = document.getElementById(elementId);
        if (!element) return;
        
        const statusClass = this.getStatusClass(status);
        element.innerHTML = `<i class="fas fa-circle ${statusClass}"></i> ${text}`;
    }

    // Helper methods for agent validation
    hasRegisteredAgents() {
        return this.agentStats && this.agentStats.total > 0;
    }

    hasOnlineAgents() {
        return this.agentStats && this.agentStats.active > 0;
    }

    calculateAverageResponseTime() {
        // Return 0 if no agents are registered or online
        if (!this.hasRegisteredAgents() || !this.hasOnlineAgents()) {
            return 0;
        }

        // Use real data from WebSocket monitoring
        const avgFromBackend = this.monitoringData.latestMetrics.avg_response_time || 0;
        
        // console.log('Response time calculation - backend average:', avgFromBackend);
        
        // If backend provides average, use it
        if (avgFromBackend > 0) {
            return avgFromBackend;
        }
        
        // Otherwise, calculate from individual agent metrics for more granular data
        const agentMetrics = this.monitoringData.latestMetrics.agent_metrics || [];
        
        // console.log('Response time calculation - agent metrics:', agentMetrics);
        
        if (agentMetrics.length === 0) {
            return 0;
        }
        
        // Calculate weighted average based on agents with actual data
        let totalWeightedTime = 0;
        let totalWeight = 0;
        
        agentMetrics.forEach(agent => {
            const responseTime = agent.avg_response_time || agent.average_response_time || 0;
            const requests = agent.total_requests || agent.requests_processed || 0;
            
            if (responseTime > 0 && requests > 0) {
                totalWeightedTime += responseTime * requests;
                totalWeight += requests;
            }
        });
        
        const calculatedAverage = totalWeight > 0 ? totalWeightedTime / totalWeight : 0;
        
        // For demonstration in development: if no real response times, show agent readiness
        if (calculatedAverage === 0 && agentMetrics.length > 0) {
            // Show a small baseline response time to indicate agents are ready
            const readyAgents = agentMetrics.filter(agent => agent.status === 'alive').length;
            const baselineResponseTime = readyAgents > 0 ? 50 + (readyAgents * 10) : 0; // Base 50ms + 10ms per agent
            // console.log('Baseline response time (agents ready):', baselineResponseTime);
            return baselineResponseTime;
        }
        
        // console.log('Calculated average response time:', calculatedAverage);
        return calculatedAverage;
    }

    calculateNetworkActivity() {
        // Return 0 if no agents are registered or online
        if (!this.hasRegisteredAgents() || !this.hasOnlineAgents()) {
            return 0;
        }

        // Calculate real network activity (requests per minute) from agent metrics
        const agentMetrics = this.monitoringData.latestMetrics.agent_metrics || [];
        
        // console.log('Network activity calculation - agent metrics:', agentMetrics);
        
        if (agentMetrics.length === 0) {
            return 0;
        }
        
        // Get total requests across all agents
        const totalRequests = agentMetrics.reduce((sum, agent) => {
            const requests = agent.total_requests || agent.requests_processed || 0;
            return sum + requests;
        }, 0);
        
        // console.log('Total requests from agents:', totalRequests);
        
        // For production: calculate rate from historical data
        if (this.monitoringData.networkData.length >= 2) {
            const currentTime = Date.now();
            const previousData = this.monitoringData.networkData[this.monitoringData.networkData.length - 2];
            const timeDiffMinutes = (currentTime - new Date(previousData.timestamp).getTime()) / (1000 * 60);
            
            if (timeDiffMinutes > 0) {
                const requestDiff = totalRequests - (previousData.requests || 0);
                const requestsPerMin = Math.max(0, requestDiff / timeDiffMinutes);
                // console.log('Calculated requests per minute:', requestsPerMin);
                return requestsPerMin;
            }
        }
        
        // For demonstration purposes in a development/testing environment:
        // Show some baseline activity based on agent status
        const activeAgents = agentMetrics.filter(agent => 
            agent.status === 'alive' || 
            new Date() - new Date(agent.last_active || 0) < 300000 // 5 minutes
        ).length;
        
        if (activeAgents > 0) {
            // Generate a small baseline value to show chart is working
            // This represents potential request capacity rather than actual requests
            const baselineActivity = activeAgents * 5; // 5 potential requests per minute per agent
            // console.log('Baseline network activity (no actual requests):', baselineActivity);
            return baselineActivity;
        }
        
        // Fallback: if no historical data, show current request count as baseline
        // In production, this will show activity once requests start flowing
        return totalRequests > 0 ? totalRequests : 0;
    }

    calculateErrorRate() {
        // Return 0 if no agents are registered
        if (!this.hasRegisteredAgents()) {
            return 0;
        }
        // Use real data from WebSocket monitoring
        return (this.monitoringData.latestMetrics.error_rate || 0) * 100;
    }

    updateAgentStatusGrid() {
        const grid = document.getElementById('agentStatusGrid');
        if (!grid) return;
        
        grid.innerHTML = '';
        
        this.agents.forEach(agent => {
            const card = this.createAgentStatusCard(agent);
            grid.appendChild(card);
        });
    }

    createAgentStatusCard(agent) {
        const div = document.createElement('div');
        
        // Handle unknown status properly
        let statusClass, lastSeenDisplay, uptimeDisplay;
        
        if (agent.status === 'unknown') {
            statusClass = 'unknown';
            lastSeenDisplay = agent.last_seen === 'Connection Lost' ? 'Connection Lost' : '???';
            uptimeDisplay = '???';
        } else {
            statusClass = agent.status === 'alive' ? 'alive' : 'dead';
            lastSeenDisplay = agent.last_seen ? this.formatTimestamp(agent.last_seen, false, true) : 'Never';
            uptimeDisplay = this.calculateUptime(agent);
        }
        
        div.className = `agent-status-card ${statusClass}`;
        div.innerHTML = `
            <div class="agent-status-header">
                <span class="agent-name">${agent.name || agent.agent_id}</span>
                <span class="agent-type-badge">${agent.agent_type || 'Unknown'}</span>
            </div>
            <div class="agent-metrics">
                <span>Last Seen: ${lastSeenDisplay}</span>
                <span>Uptime: ${uptimeDisplay}</span>
            </div>
        `;
        
        return div;
    }

    calculateUptime(agent) {
        if (!agent.registered_at) return 'Unknown';
        
        const registered = new Date(agent.registered_at);
        const now = new Date();
        const uptimeMs = now - registered;
        
        const hours = Math.floor(uptimeMs / (1000 * 60 * 60));
        const minutes = Math.floor((uptimeMs % (1000 * 60 * 60)) / (1000 * 60));
        
        if (hours > 0) {
            return `${hours}h ${minutes}m`;
        } else {
            return `${minutes}m`;
        }
    }

    filterAgentStatus(filter) {
        const cards = document.querySelectorAll('.agent-status-card');
        
        cards.forEach(card => {
            const isVisible = filter === 'all' || 
                            (filter === 'alive' && card.classList.contains('alive')) ||
                            (filter === 'dead' && card.classList.contains('dead')) ||
                            (filter === 'warning' && card.classList.contains('warning'));
            
            card.style.display = isVisible ? 'block' : 'none';
        });
    }

    updateAdvancedCharts() {
        try {
            // Always update resource utilization regardless of agent status
            this.updateResourceUtilization();
            
            // Only update agent-dependent charts if we have registered agents
            if (this.hasRegisteredAgents()) {
                // Update response time distribution (requires online agents)
                this.updateResponseTimeDistribution();
                
                // Update load balancing (requires online agents)
                this.updateLoadBalancing();
                
                // Update success rate trends
                this.updateSuccessRateTrends();
            }
        } catch (error) {
            console.error('Error updating advanced charts:', error);
        }
    }

    updateResponseTimeDistribution() {
        if (!this.charts.responseTimeDist) return;
        
        try {
            // Only update if we have online agents
            if (!this.hasOnlineAgents()) {
                // Set all values to 0 when no online agents
                this.charts.responseTimeDist.data.datasets[0].data = [0, 0, 0, 0];
                this.charts.responseTimeDist.update();
                return;
            }

            // Use response time distribution data from WebSocket
            const distribution = this.monitoringData.latestMetrics.response_time_distribution || {
                fast: 0, medium: 0, slow: 0, very_slow: 0
            };
            
            if (distribution && typeof distribution === 'object') {
                const fast = Number(distribution.fast) || 0;
                const medium = Number(distribution.medium) || 0;
                const slow = Number(distribution.slow) || 0;
                const verySlow = Number(distribution.very_slow) || 0;
                
                this.charts.responseTimeDist.data.datasets[0].data = [fast, medium, slow, verySlow];
            } else {
                // Fallback: calculate distribution from historical data if available
                const recentData = this.monitoringData.performanceData.slice(-20); // Last 20 data points
                if (recentData.length > 0) {
                    let fast = 0, medium = 0, slow = 0, verySlow = 0;
                    
                    recentData.forEach(point => {
                        const responseTime = Number(point.response_time) || 0;
                        if (responseTime < 100) fast++;
                        else if (responseTime < 500) medium++;
                        else if (responseTime < 1000) slow++;
                        else verySlow++;
                    });
                    
                    const total = recentData.length;
                    this.charts.responseTimeDist.data.datasets[0].data = [
                        (fast / total) * 100,
                        (medium / total) * 100,
                        (slow / total) * 100,
                        (verySlow / total) * 100
                    ];
                } else {
                    // No data available - show zeros
                    this.charts.responseTimeDist.data.datasets[0].data = [0, 0, 0, 0];
                }
            }
            
            this.charts.responseTimeDist.update();
        } catch (error) {
            console.error('Error updating response time distribution chart:', error);
        }
    }

    updateLoadBalancing() {
        if (!this.charts.loadBalancing) return;
        
        try {
            // Only update if we have online agents
            if (!this.hasOnlineAgents()) {
                // Clear chart data when no online agents
                this.charts.loadBalancing.data.labels = [];
                this.charts.loadBalancing.data.datasets[0].data = [];
                this.charts.loadBalancing.update();
                return;
            }

            // Use real load balancing data from WebSocket
            const loadBalancing = this.monitoringData.latestMetrics.load_balancing || {};
            
            if (loadBalancing && typeof loadBalancing === 'object') {
                const agentTypes = Object.keys(loadBalancing);
                const loadData = Object.values(loadBalancing).map(val => Number(val) || 0);
                
                this.charts.loadBalancing.data.labels = agentTypes;
                this.charts.loadBalancing.data.datasets[0].data = loadData;
            } else {
                // Fallback: use actual agent data if load balancing metrics not provided
                const agentTypes = [...new Set(this.agents.map(a => a.agent_type || 'Unknown'))];
                const loadData = agentTypes.map(type => {
                    const agentsOfType = this.agents.filter(a => a.agent_type === type);
                    const aliveCount = agentsOfType.filter(a => a.status === 'alive').length;
                    const totalCount = agentsOfType.length || 1;
                    return (aliveCount / totalCount) * 100; // Load percentage based on alive agents
                });
                
                this.charts.loadBalancing.data.labels = agentTypes;
                this.charts.loadBalancing.data.datasets[0].data = loadData;
            }
            
            this.charts.loadBalancing.update();
        } catch (error) {
            console.error('Error updating load balancing chart:', error);
        }
    }

    updateSuccessRateTrends() {
        if (!this.charts.successRate) return;
        
        try {
            const currentTime = this.formatTimestamp(new Date(), false, false);
            
            // Only update if we have registered agents AND they are online/alive
            if (!this.hasRegisteredAgents() || !this.hasOnlineAgents()) {
                this.updateChart(this.charts.successRate, currentTime, 0);
                return;
            }
            
            // Use real error rate to calculate success rate
            const errorRate = Number(this.monitoringData.latestMetrics.error_rate) || 0;
            const successRate = Math.max(0, (1 - errorRate) * 100);
            
            this.updateChart(this.charts.successRate, currentTime, successRate);
        } catch (error) {
            console.error('Error updating success rate trends chart:', error);
        }
    }

    updateResourceUtilization() {
        if (!this.charts.resourceUtil) {
            console.warn('Resource utilization chart not available');
            return;
        }
        
        try {
            // Use real resource utilization data from WebSocket
            const resources = this.monitoringData.latestMetrics.resource_utilization || {
                cpu: 0, memory: 0, network: 0, storage: 0
            };
            
            // console.log('Resource utilization data:', resources);
            
            if (resources && typeof resources === 'object') {
                const cpu = Number(resources.cpu) || 0;
                const memory = Number(resources.memory) || 0;
                const network = Number(resources.network) || 0;
                const storage = Number(resources.storage) || 0;
                
                // console.log('Parsed resource values:', { cpu, memory, network, storage });
                
                this.charts.resourceUtil.data.datasets[0].data = [cpu, memory, network, storage];
            } else {
                console.warn('No valid resource data available');
                // No resource data available - show zeros or basic fallback
                this.charts.resourceUtil.data.datasets[0].data = [0, 0, 0, 0];
            }
            
            this.charts.resourceUtil.update();
            // console.log('Resource utilization chart updated successfully');
        } catch (error) {
            console.error('Error updating resource utilization chart:', error);
        }
    }

    // For now already handled by server-side alerting
    checkForAlerts(avgResponseTime, errorRate) {
        const alerts = [];
        
        // Reduced client-side alerting since server now handles most alerts
        // WebSocket connection alerts are handled by onclose event and connection health monitor
                
        // Add new alerts to the queue
        alerts.forEach(alert => {
            this.addAlert(alert);
        });
    }

    startConnectionHealthMonitor() {
        // Periodically check connection health and generate alerts if needed
        if (this.connectionHealthInterval) {
            clearInterval(this.connectionHealthInterval);
        }
        
        this.connectionHealthInterval = setInterval(() => {
            this.checkConnectionHealth();
        }, 10000); // Check every 10 seconds
    }
    
    checkConnectionHealth() {
        // Skip if monitoring is paused
        if (this.isPaused) return;
        
        // Check WebSocket connection status
        const isConnected = this.websocket?.readyState === WebSocket.OPEN;
        
        if (!isConnected) {
            // WebSocket is disconnected - check if we should send an alert
            // Use the same suppression key as the other WebSocket alerts
            const suppressionKey = 'websocket_connection_lost';
            const now = Date.now();
            const suppressionTime = 300000; // 5 minutes
            
            // Only add alert if not suppressed
            if (!this.alertSuppressionMap[suppressionKey] || 
                (now - this.alertSuppressionMap[suppressionKey]) >= suppressionTime) {
                
                this.addAlert({
                    type: 'critical',
                    severity: 'critical',
                    title: 'Dashboard Connection Lost',
                    message: 'Real-time updates are not available - WebSocket connection is down',
                    timestamp: new Date().toISOString()
                });
            }
        }
    }

    renderAlerts() {
        const container = document.getElementById('realtimeAlerts');
        if (!container) return;
        container.innerHTML = '';
        // Filter alerts by search and type
        let alerts = this.monitoringData.alertQueue || [];
        if (this.alertSearchText) {
            alerts = alerts.filter(alert =>
                (alert.title && alert.title.toLowerCase().includes(this.alertSearchText)) ||
                (alert.message && alert.message.toLowerCase().includes(this.alertSearchText))
            );
        }
        if (this.alertTypeFilter) {
            const f = this.alertTypeFilter.toLowerCase();
            alerts = alerts.filter(alert => (alert.severity && alert.severity.toLowerCase() === f) || (alert.type && alert.type.toLowerCase() === f));
        }
        if (alerts.length === 0) {
            container.innerHTML = '<div style="text-align: center; color: #666; padding: 2rem;">No alerts</div>';
            return;
        }
        alerts.forEach(alert => {
            const alertElement = this.createAlertElement(alert);
            container.appendChild(alertElement);
        });
    }

    createAlertElement(alert) {
        const div = document.createElement('div');
        
        // Use severity for CSS styling (critical, warning, info)
        const severityClass = alert.severity || 'info'; // Default to 'info' if no severity
        div.className = `alert-item ${severityClass}`;
        
        // Choose icon based on severity
        const iconClass = alert.severity === 'critical' ? 'fas fa-exclamation-triangle' :
                         alert.severity === 'warning' ? 'fas fa-exclamation-circle' :
                         alert.severity === 'error' ? 'fas fa-times-circle' :
                         'fas fa-info-circle';
        
        // Use severity for icon styling to match CSS
        const iconCssClass = severityClass;
        
        // Format timestamp to readable time
        const alertTime = alert.timestamp ? this.formatTimestamp(alert.timestamp, true, true) : 'Unknown';
        
        div.innerHTML = `
            <div class="alert-icon ${iconCssClass}">
                <i class="${iconClass}"></i>
            </div>
            <div class="alert-content">
                <div class="alert-title">${alert.title}</div>
                <div class="alert-message">${alert.message}</div>
            </div>
            <div class="alert-time">${alertTime}</div>
        `;
        
        return div;
    }

    clearAlerts() {
        // Clear both memory and localStorage
        this.clearAllAlerts();
        
        // Reset alert suppression map to allow alerts to reappear
        this.alertSuppressionMap = {};
        
        // dashboard.addLog('INFO', 'Alerts cleared');

        // Ask backend to clear persisted alerts as well
        try {
            if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
                this.websocket.send(JSON.stringify({
                    type: 'clear_alerts',
                    timestamp: new Date().toISOString(),
                    data: { source: 'dashboard_admin' }
                }));
            }
        } catch (err) {
            console.warn('Failed to send clear alerts request to backend:', err);
        }
    }

    toggleSoundAlerts() {
        this.soundAlertsEnabled = !this.soundAlertsEnabled;
        this.settings.soundAlerts = this.soundAlertsEnabled;
        // Do NOT call this.saveSettingsToStorage() here!
        const toggle = document.getElementById('soundToggle');
        const icon = toggle.querySelector('i');
        if (this.soundAlertsEnabled) {
            icon.className = 'fas fa-volume-up';
            toggle.innerHTML = '<i class="fas fa-volume-up"></i> Sound On';
        } else {
            icon.className = 'fas fa-volume-mute';
            toggle.innerHTML = '<i class="fas fa-volume-mute"></i> Sound Off';
        }
    }

    playAlertSound() {
        // A beep :) sound using a reusable AudioContext
        try {
            // Do not play sounds when logged out or when sound alerts are disabled
            if (!this.authToken) return;
            if (this.settings && this.settings.soundAlerts === false) return;
            
            if (!this.alertAudioCtx) {
                this.alertAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
            }
            
            const oscillator = this.alertAudioCtx.createOscillator();
            const gainNode = this.alertAudioCtx.createGain();
            
            oscillator.connect(gainNode);
            gainNode.connect(this.alertAudioCtx.destination);
            
            oscillator.frequency.value = 800;
            oscillator.type = 'sine';
            
            gainNode.gain.setValueAtTime(0.3, this.alertAudioCtx.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, this.alertAudioCtx.currentTime + 0.5);
            
            oscillator.start(this.alertAudioCtx.currentTime);
            oscillator.stop(this.alertAudioCtx.currentTime + 0.5);
        } catch (error) {
            console.warn('Failed to play alert sound:', error);
        }
    }

    updateTimeRange(range) {
        // Update current time range and save to settings
        this.currentTimeRange = range;
        this.settings.metricsTimeRange = range;
        this.saveSettingsToStorage();
        
        // Get the appropriate data point limit for this range
        const maxDataPoints = this.getDataPointLimit(range);
        
        // Update all charts to respect the new time range
        Object.values(this.charts).forEach(chart => {
            if (chart && chart.data && chart.data.labels) {
                // Trim to the new limit
                while (chart.data.labels.length > maxDataPoints) {
                    chart.data.labels.shift();
                    chart.data.datasets.forEach(dataset => {
                        if (dataset.data) dataset.data.shift();
                    });
                }
                chart.update('none'); // Update without animation for better performance
            }
        });
        
        // Also trim the monitoring data arrays to match the new range
        const maxStoragePoints = Math.max(maxDataPoints * 2, 100);
        if (this.monitoringData.performanceData.length > maxStoragePoints) {
            this.monitoringData.performanceData = this.monitoringData.performanceData.slice(-maxStoragePoints);
            this.monitoringData.networkData = this.monitoringData.networkData.slice(-maxStoragePoints);
            this.monitoringData.errorData = this.monitoringData.errorData.slice(-maxStoragePoints);
        }
        
        // console.log(`Time range updated to ${range}, max chart points: ${maxDataPoints}, max storage points: ${maxStoragePoints}`);
    }

    exportMonitoringData() {
        const data = {
            timestamp: new Date().toISOString(),
            agents: this.agents,
            performanceData: this.monitoringData.performanceData,
            networkData: this.monitoringData.networkData,
            errorData: this.monitoringData.errorData,
            alerts: this.monitoringData.alertQueue,
            systemHealth: this.monitoringData.systemHealth
        };
        
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        
        const a = document.createElement('a');
        a.href = url;
        a.download = `arcp-monitoring-${new Date().toISOString().split('T')[0]}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        
        URL.revokeObjectURL(url);
        
        this.showSuccess('Monitoring data exported successfully');
    }

    updateRecentActivity() {
        const activityList = document.getElementById('recentActivity');
        if (!activityList) {
            console.warn('Recent activity element not found');
            return;
        }

        // Debug logging
        // console.log('Updating recent activity - agents available:', this.agents.length);
        
        // Check if we have any agents
        if (!this.agents || this.agents.length === 0) {
            // console.log('No agents available for recent activity');
            activityList.innerHTML = `
                <div class="activity-item">
                    <div class="activity-icon info">
                        <i class="fas fa-info-circle"></i>
                    </div>
                    <div class="activity-content">
                        <p>No agent activity yet</p>
                        <small>Waiting for agents to register...</small>
                    </div>
                </div>`;
            return;
        }

        // Get real recent activity from agents
        const recentActivities = [];
        
        // Sort agents by last_seen to get recent activity - handle invalid dates
        const sortedAgents = [...this.agents].sort((a, b) => {
            // Handle invalid or missing last_seen values
            const aTime = new Date(a.last_seen && a.last_seen !== 'Connection Lost' ? a.last_seen : 0);
            const bTime = new Date(b.last_seen && b.last_seen !== 'Connection Lost' ? b.last_seen : 0);
            
            // If both dates are invalid, sort by agent_id for consistency
            if (isNaN(aTime.getTime()) && isNaN(bTime.getTime())) {
                return (a.agent_id || '').localeCompare(b.agent_id || '');
            }
            
            // If one date is invalid, put the valid one first
            if (isNaN(aTime.getTime())) return 1;
            if (isNaN(bTime.getTime())) return -1;
            
            return bTime - aTime;
        });

        // console.log('Sorted agents for recent activity:', sortedAgents.slice(0, 5).map(a => ({
        //     id: a.agent_id,
        //     status: a.status,
        //     last_seen: a.last_seen
        // })));

        // Generate activities from real agent data
        sortedAgents.slice(0, 5).forEach(agent => {
            let timeAgo;
            
            // Handle different last_seen scenarios
            if (!agent.last_seen || agent.last_seen === 'Connection Lost') {
                timeAgo = agent.status === 'unknown' ? 'Connection lost' : 'Never';
            } else {
                const lastSeen = new Date(agent.last_seen);
                if (isNaN(lastSeen.getTime())) {
                    timeAgo = 'Invalid date';
                } else {
                    timeAgo = this.getTimeAgo(lastSeen);
                }
            }
            
            // Generate activity based on agent status
            if (agent.status === 'alive') {
                recentActivities.push({
                    type: 'heartbeat',
                    message: `Agent ${agent.agent_id || 'Unknown'} is alive`,
                    time: timeAgo,
                    agent_id: agent.agent_id
                });
            } else if (agent.status === 'dead') {
                recentActivities.push({
                    type: 'disconnect',
                    message: `Agent ${agent.agent_id || 'Unknown'} went dead`,
                    time: timeAgo,
                    agent_id: agent.agent_id
                });
            } else {
                // Handle unknown status
                recentActivities.push({
                    type: 'unknown',
                    message: `Agent ${agent.agent_id || 'Unknown'} status unknown`,
                    time: timeAgo,
                    agent_id: agent.agent_id
                });
            }
        });

        // console.log('Generated recent activities:', recentActivities);

        // If no activities were generated, show a message
        if (recentActivities.length === 0) {
            activityList.innerHTML = `
                <div class="activity-item">
                    <div class="activity-icon warning">
                        <i class="fas fa-exclamation-triangle"></i>
                    </div>
                    <div class="activity-content">
                        <p>No recent activity</p>
                        <small>All agents are inactive</small>
                    </div>
                </div>`;
            return;
        }

        activityList.innerHTML = recentActivities.map(activity => `
            <div class="activity-item">
                <div class="activity-icon ${activity.type}">
                    <i class="fas fa-${activity.type === 'register' ? 'plus' : activity.type === 'heartbeat' ? 'heartbeat' : activity.type === 'unknown' ? 'question' : 'times'}"></i>
                </div>
                <div class="activity-content">
                    <p>${activity.message}</p>
                    <small>${activity.time}</small>
                </div>
            </div>
        `).join('');
        
        // console.log('Recent activity HTML updated');
    }

    getTimeAgo(date) {
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);

        if (diffMins < 1) return 'Just now';
        if (diffMins < 60) return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`;
        if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
        return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
    }

    renderLogs() {
        const logsContainer = document.getElementById('logsContainer');
        if (!logsContainer) return;

        // Filter logs by search and level
        let logs = this.logs || [];
        const rawLevelFilter = document.getElementById('logLevel')?.value || '';
        const acceptedLevels = this.mapUILogLevelToAccepted(rawLevelFilter);
        if (this.logSearchText) {
            logs = logs.filter(log =>
                (log.message && log.message.toLowerCase().includes(this.logSearchText)) ||
                (log.level && log.level.toLowerCase().includes(this.logSearchText))
            );
        }
        if (acceptedLevels.length) {
            logs = logs.filter(log => acceptedLevels.includes(this.normalizeLogLevel(log.level)));
        }

        // Apply maxLogEntries limit to rendered logs
        const hardMaxLogs = this.serverLogBufferMax || 10000;
        const maxLogEntries = Math.min(this.settings.maxLogEntries || hardMaxLogs, hardMaxLogs);
        if (logs.length > maxLogEntries) {
            logs = logs.slice(0, maxLogEntries);
        }

        logsContainer.innerHTML = logs.map(log => `
            <div class="log-entry">
                <span class="log-timestamp">${this.formatTimestamp(log.timestamp, true, true)}</span>
                <span class="log-level ${log.level}">${log.level}</span>
                <span class="log-message">${log.message}</span>
            </div>
        `).join('');
        
        // Only auto-scroll if already near bottom to avoid interrupting manual scroll
        const threshold = 20; // pixels from bottom
        const distanceFromBottom = logsContainer.scrollHeight - logsContainer.scrollTop - logsContainer.clientHeight;
        if (distanceFromBottom < threshold) {
            logsContainer.scrollTop = logsContainer.scrollHeight;
        }
    }

    filterLogs() {
        const levelFilterRaw = document.getElementById('logLevel')?.value || '';
        const acceptedLevels = this.mapUILogLevelToAccepted(levelFilterRaw);
        const logEntries = document.querySelectorAll('.log-entry');

        logEntries.forEach(entry => {
            const levelText = entry.querySelector('.log-level').textContent.trim().toUpperCase();
            entry.style.display = !acceptedLevels.length || acceptedLevels.includes(levelText) ? 'flex' : 'none';
        });
    }

    addLog(level, message) {
        // Normalize log levels to ensure consistent styling
        const normalizedLevel = this.normalizeLogLevel(level);

        const log = {
            timestamp: new Date().toISOString(),
            level: normalizedLevel,
            message: message
        };

        this.logs.unshift(log);

        // Keep only the last N logs
        const hardMaxLogs2 = this.serverLogBufferMax || 10000;
        const maxLogs = Math.min(this.settings.maxLogEntries || hardMaxLogs2, hardMaxLogs2);
        if (this.logs.length > maxLogs) {
            this.logs = this.logs.slice(0, maxLogs);
        }

        // Send dashboard logs to backend for persistence
        // console.log('Sending log to backend:', log);
        this.sendLogToBackend(log);

        this.renderLogs();
        // Persist to localStorage for reload resilience
        try {
            if (this.authToken) {
                localStorage.setItem('arcp-dashboard-logs', JSON.stringify({ logs: this.logs, ts: Date.now() }));
            }
        } catch (_) { /* ignore quota errors */ }
    }

    sendLogToBackend(log) {
        // Send dashboard logs to backend via WebSocket if available
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            try {
                this.websocket.send(JSON.stringify({
                    type: 'dashboard_log',
                    timestamp: new Date().toISOString(),
                    data: {
                        level: log.level,
                        message: log.message,
                        timestamp: log.timestamp
                    }
                }));
            } catch (error) {
                console.warn('Failed to send log to backend:', error);
            }
        }
    }

    async switchTab(tabName) {
        // Update navigation
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.remove('active');
        });
        document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');

        // Update content
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.remove('active');
        });
        document.getElementById(tabName).classList.add('active');

        // Load tab-specific data
        if (tabName === 'agents') {
            // Request immediate agents data when switching to agents tab
            if (this.websocket?.readyState === WebSocket.OPEN) {
                // console.log('Requesting immediate agents data...');
                this.websocket.send(JSON.stringify({
                    type: 'agents_request',
                    timestamp: new Date().toISOString()
                }));
            } else {
                // console.log('WebSocket not available, agents data will load when connection is established');
            }
        } else if (tabName === 'monitoring') {
            // Initialize monitoring if not already done
            if (!this.monitoringData) {
                await this.initializeMonitoring();
            }
            
            // Update monitoring status when switching to monitoring tab
            this.updateMonitoringStatus();
            
            // Apply pause state if monitoring is paused
            if (this.isPaused) {
                this.pauseChartUpdates();
            }
            
            // Update performance metrics immediately when switching to monitoring tab
            this.updatePerformanceMetrics();
            // Update all monitoring data immediately via WebSocket
            if (this.websocket?.readyState === WebSocket.OPEN) {
                // WebSocket is active, data will come automatically
                // console.log('Monitoring tab activated, WebSocket already connected');
            } else if (!this.connectingWebSocket) {
                // WebSocket not available and not connecting, attempt to reconnect
                // console.log('WebSocket not connected, attempting to reconnect...');
                this.setupMonitoringWebSocket();
            } else {
                // console.log('WebSocket connection already in progress for monitoring tab');
            }
        }
    }

    updatePerformanceMetrics() {
        const metricsElement = document.getElementById('responseTimesMetrics');
        if (!metricsElement) {
            console.warn('responseTimesMetrics element not found');
            return;
        }

        // Calculate real metrics from agent data
        const aliveAgents = this.agents.filter(agent => agent.status === 'alive');
        const totalAgents = this.agents.length;
        const alivePercentage = totalAgents > 0 ? ((aliveAgents.length / totalAgents) * 100).toFixed(1) : 0;

        // Calculate average uptime based on registered_at (total runtime)
        let avgUptimeHours = 0;
        if (aliveAgents.length > 0) {
            const now = new Date();
            const uptimes = aliveAgents.map(agent => {
                const registered = new Date(agent.registered_at);
                return Math.max(0, (now - registered) / (1000 * 60 * 60)); // hours
            });
            avgUptimeHours = (uptimes.reduce((a, b) => a + b, 0) / uptimes.length).toFixed(1);
        }

        // Get unique agent types
        const uniqueTypes = new Set(this.agents.map(a => a.agent_type));

        metricsElement.innerHTML = `
            <div class="metric-item">
                <h5>Agents alive</h5>
                <p>${aliveAgents.length}/${totalAgents} (${alivePercentage}%)</p>
            </div>
            <div class="metric-item">
                <h5>Average Uptime</h5>
                <p>${avgUptimeHours} hours</p>
            </div>
            <div class="metric-item">
                <h5>Agent Types</h5>
                <p>${uniqueTypes.size} types</p>
            </div>
        `;
    }

    setupAutoRefresh() {
        // Clear any existing interval
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }

        // Check if auto-refresh is enabled in settings
        const shouldEnable = this.settings.enableAutoRefresh && this.autoRefresh;
        if (shouldEnable) {
            const interval = (this.settings.refreshInterval || 5) * 1000;
            // console.log(`Setting up auto-refresh with interval: ${interval}ms`);
            const tick = () => {
                // console.log('Auto-refresh triggered');
                this.refreshData();
            };
            // Only run immediate tick and log when transitioning from disabled -> enabled
            if (!this.autoRefreshActive) {
                try { tick(); } catch (_) {}
                this.addLog('INFO', `Auto-refresh enabled (${interval/1000}s interval)`);
            }
            this.refreshInterval = setInterval(tick, interval);
            this.autoRefreshActive = true;
        } else {
            this.autoRefreshActive = false;
        }
    }

    refreshData() {
        // console.log('Refreshing dashboard data via WebSocket...');
        
        if (this.websocket?.readyState === WebSocket.OPEN) {
            // Send refresh request to backend for immediate fresh data
            // console.log('Sending refresh request to backend');
            if (this.authToken) this.websocket.send(JSON.stringify({
                type: 'refresh_request',
                timestamp: new Date().toISOString(),
                data: { 
                    forced: true,
                    request_all: true  // Request all data types
                }
            }));
            
            // Update health indicators locally
            this.updateSystemHealthIndicators();
            this.showToastWithRateLimit('Refreshing dashboard data...', 'info', 2000);
            // console.log('Dashboard refresh request sent to backend');
        } else if (!this.connectingWebSocket) {
            // Only attempt reconnection if not already connecting
            // console.log('WebSocket not connected, attempting to reconnect...');
            this.setupMonitoringWebSocket();
            this.addLog('WARN', 'WebSocket reconnection attempted');
            this.showToastWithRateLimit('Reconnecting to server...', 'warning', 2000);
        } else {
            // console.log('WebSocket connection already in progress, skipping reconnection attempt');
            this.showToastWithRateLimit('Connection already in progress...', 'info', 2000);
        }
    }

    showLoading(show) {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            overlay.classList.toggle('show', show);
        }
    }

    showError(message) {
        this.addLog('ERR', message);
        this.showToast(message, 'error');
        // Security context for error notifications
        if (message.includes('rate limit') || message.includes('locked') || message.includes('attempts')) {
            this.securityManager.logSecurityEvent('security_error_shown', message);
        }
    }
    showCritical(message) {
        this.addLog('CRIT', message);
        this.showToast(message, 'critical');
        // Security context for critical notifications
        this.securityManager?.logSecurityEvent?.('security_critical_shown', message);
    }
    showSuccess(message) {
        this.addLog('SUCS', message);
        this.showToast(message, 'success');
    }

    showToast(message, type = 'info') {
        // Remove any existing toast
        const oldToast = document.getElementById('arcp-toast');
        if (oldToast) oldToast.remove();

        // Create new toast
        const toast = document.createElement('div');
        toast.id = 'arcp-toast';
        // Determine background color by type
        const bgColor = type.toLowerCase() === 'error' || type.toLowerCase() === 'critical' || type.toLowerCase() === 'danger'
            ? 'rgba(231,76,60,0.9)'
            : type.toLowerCase() === 'success'
            ? 'rgba(46,204,113,0.9)'
            : type.toLowerCase() === 'info'
            ? 'rgba(52,152,219,0.9)'
            : type.toLowerCase() === 'warning'
                ? 'rgba(255,193,7,0.95)'    
                : 'rgba(0,0,0,0.8)';
        // Style toast for bottom-right
        toast.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            z-index: 10000;
            background: ${bgColor};
            color: white;
            padding: 12px 16px;
            border-radius: 6px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            max-width: 400px;
            font-weight: 500;
            opacity: 0;
            transition: opacity 0.3s ease;
        `;
        toast.textContent = message;
        document.body.appendChild(toast);
        // Fade in
        setTimeout(() => { toast.style.opacity = '1'; }, 10);
        // Fade out and remove
        setTimeout(() => { toast.style.opacity = '0'; }, 3000);
        setTimeout(() => { toast.remove(); }, 3300);
    }

    showToastWithRateLimit(message, type = 'info', rateLimit = 5000) {
        // Create a key for rate limiting based on message and type
        const key = `${type}:${message}`;
        const now = Date.now();
        
        // Check if we should rate limit this toast
        if (this.lastToastTime[key] && (now - this.lastToastTime[key]) < rateLimit) {
            return; // Skip this toast to prevent spam
        }
        
        // Update last toast time
        this.lastToastTime[key] = now;
        
        // Clean up old entries (older than 1 minute)
        Object.keys(this.lastToastTime).forEach(oldKey => {
            if (now - this.lastToastTime[oldKey] > 60000) {
                delete this.lastToastTime[oldKey];
            }
        });
        
        // Show the toast
        this.showToast(message, type);
    }

    loadSettings() {
        const saved = localStorage.getItem('arcp-dashboard-settings');
        
        if (saved) {
            // Return existing settings
            return JSON.parse(saved);
        } else {
            // First time user - create and save default settings
            const defaultSettings = {
                enableAutoRefresh: false,
                refreshInterval: 60,
                maxLogEntries: 1000,
                soundAlerts: true,  // Enable sound alerts by default
                metricsTimeRange: '15m'  // Default time range
            };
            
            // Do NOT persist defaults until admin has logged in
            try {
                if (this && this.authToken) {
                    localStorage.setItem('arcp-dashboard-settings', JSON.stringify(defaultSettings));
                }
            } catch (_) { /* ignore */ }
            // console.log('First time user: Default settings saved to localStorage');
            
            return defaultSettings;
        }
    }

    async saveSettings() {
        // Always require PIN for saving settings
        await this.requirePin(() => {
            this.#saveSettingsCore();
        });
    }

    #saveSettingsCore() {
        // Validate input values
        const enableAutoRefreshInput = document.getElementById('enableAutoRefresh');
        const refreshIntervalInput = document.getElementById('refreshInterval');
        const maxLogEntriesInput = document.getElementById('maxLogEntries');
        const soundAlertsInput = document.getElementById('soundAlerts');
        let valid = true;
        let messages = [];
        
        const enableAutoRefresh = enableAutoRefreshInput.checked;
        let refreshInterval = parseInt(refreshIntervalInput.value);
        let maxLogEntries = parseInt(maxLogEntriesInput.value);
        
        // Only validate refresh interval if auto-refresh is enabled
        if (enableAutoRefresh && (isNaN(refreshInterval) || refreshInterval < 30 || refreshInterval > 3600)) {
            valid = false;
            messages.push('Refresh interval must be a number between 30 and 3600 seconds.');
            refreshIntervalInput.classList.add('input-error');
        } else {
            refreshIntervalInput.classList.remove('input-error');
        }
        
        const hardMax = this.serverLogBufferMax || 10000;
        if (isNaN(maxLogEntries) || maxLogEntries < 10 || maxLogEntries > hardMax) {
            valid = false;
            messages.push(`Max log entries must be a number between 10 and ${hardMax}.`);
            maxLogEntriesInput.classList.add('input-error');
        } else {
            maxLogEntriesInput.classList.remove('input-error');
        }
        
        if (!valid) {
            this.showError(messages.join(' '));
            this.addLog('ERR', 'Failed to save settings: ' + messages.join(' '));
            return;
        }
        
        this.settings.enableAutoRefresh = enableAutoRefresh;
        this.settings.refreshInterval = refreshInterval;
        this.settings.maxLogEntries = maxLogEntries;
        this.settings.soundAlerts = soundAlertsInput.checked;
        
        // Get current time range from dropdown
        const metricsTimeRange = document.getElementById('metricsTimeRange');
        if (metricsTimeRange) {
            this.settings.metricsTimeRange = metricsTimeRange.value;
            this.currentTimeRange = metricsTimeRange.value;
        }
        
        this.saveSettingsToStorage();
        // Persist settings to backend for durability across browsers/sessions
        if (this.authToken) {
            this.apiCall(`${this.apiBase}/dashboard/config`, {
                method: 'POST',
                headers: this.getAuthHeaders(true),
                body: JSON.stringify({ ui: {
                    enableAutoRefresh: this.settings.enableAutoRefresh,
                    refreshInterval: this.settings.refreshInterval,
                    maxLogEntries: this.settings.maxLogEntries,
                    soundAlerts: this.settings.soundAlerts,
                    metricsTimeRange: this.settings.metricsTimeRange
                }})
            }).catch(() => {/* ignore */});
        }
        
        // Apply the new settings immediately
        this.applySettings(); // Re-apply to update UI state
        
        this.showSuccess('Settings saved successfully');
    }

    saveSettingsToStorage() {
        // Actually persist settings to localStorage or backend if needed
        try {
            if (!this.authToken) return; // Do not store settings until admin login
            localStorage.setItem('arcp-dashboard-settings', JSON.stringify(this.settings));
        } catch (_) { /* ignore */ }
    }

    applySettings() {
        const enableAutoRefresh = document.getElementById('enableAutoRefresh');
        if (enableAutoRefresh) {
            enableAutoRefresh.checked = this.settings.enableAutoRefresh;
        }

        const refreshInterval = document.getElementById('refreshInterval');
        if (refreshInterval) {
            refreshInterval.value = this.settings.refreshInterval;
            refreshInterval.disabled = !this.settings.enableAutoRefresh;
        }

        const maxLogEntries = document.getElementById('maxLogEntries');
        if (maxLogEntries) {
            maxLogEntries.value = this.settings.maxLogEntries;
            const hardMax = this.serverLogBufferMax || 10000;
            maxLogEntries.placeholder = `(Min:10 Max:${hardMax})`;
            if (this.settings.maxLogEntries > hardMax) {
                this.settings.maxLogEntries = hardMax;
                maxLogEntries.value = hardMax;
                this.saveSettingsToStorage();
            }
        }

        const soundAlerts = document.getElementById('soundAlerts');
        if (soundAlerts) {
            soundAlerts.checked = this.settings.soundAlerts;
        }

        // Apply time range setting
        const metricsTimeRange = document.getElementById('metricsTimeRange');
        if (metricsTimeRange) {
            metricsTimeRange.value = this.settings.metricsTimeRange || '15m';
            this.currentTimeRange = this.settings.metricsTimeRange || '15m';
        }

        // Ensure runtime flag matches persisted setting after reload and schedule interval
        this.autoRefresh = !!this.settings.enableAutoRefresh;
        this.setupAutoRefresh();

        // Apply dark mode setting from localStorage (with default)
        let darkMode = localStorage.getItem('arcp-dashboard-darkmode');
        if (darkMode === null) {
            // First time user - set default dark mode to false (light mode)
            darkMode = false;
            localStorage.setItem('arcp-dashboard-darkmode', 'false');
            // console.log('First time user: Default dark mode setting (light mode) saved to localStorage');
        } else {
            darkMode = darkMode === 'true';
        }
        
        document.body.classList.toggle('dark-mode', darkMode);
        this.updateDarkModeIcon();
    }

    toggleDarkMode() {
        // Toggle and persist dark mode in its own key
        const current = localStorage.getItem('arcp-dashboard-darkmode') === 'true';
        const newValue = !current;
        localStorage.setItem('arcp-dashboard-darkmode', newValue);
        document.body.classList.toggle('dark-mode', newValue);
        this.updateDarkModeIcon();
    }

    updateDarkModeIcon() {
        const darkModeToggle = document.getElementById('darkModeToggle');
        if (darkModeToggle) {
            const icon = darkModeToggle.querySelector('i');
            const darkMode = localStorage.getItem('arcp-dashboard-darkmode') === 'true';
            if (darkMode) {
                icon.className = 'fas fa-moon';
                darkModeToggle.title = 'Switch to Light Mode';
            } else {
                icon.className = 'fas fa-sun';
                darkModeToggle.title = 'Switch to Dark Mode';
            }
        }
    }

    // Agent action methods
    async viewAgentDetails(agentId) {
        try {
            const response = await this.apiCall(`${this.apiBase}/agents/${agentId}?include_metrics=true`, {
                headers: this.getAuthHeaders()
            });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            const agent = await response.json();
            
            this.showAgentDetailsModal(agent);
            this.addLog('INFO', `Viewed details for agent ${agentId}`);
        } catch (error) {
            console.error('Error fetching agent details:', error);
            this.showError(`Failed to fetch agent details for agent ${agentId}: ${error.message}`);
        }
    }

    async pingAgent(agentId) {
        // Direct client-to-agent ping using the agent's own endpoint
        const getAgentInfo = async () => {
            let agent = (this.agents || []).find(a => a.agent_id === agentId);
            if (!agent) {
                try {
                    const resp = await this.apiCall(`${this.apiBase}/agents/${agentId}` , { headers: this.getAuthHeaders() });
                    if (resp.ok) {
                        agent = await resp.json();
                    }
                } catch (_) { /* ignore */ }
            }
            return agent;
        };

        const tryPing = async (endpoint) => {
            if (!endpoint) throw new Error('Agent endpoint not available');
            const clean = (s) => (s || '').replace(/\/$/, '');
            const base = clean(endpoint);
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), 5000);
            const headers = { 'Accept': 'application/json' };
            try {
                try {
                    const res = await fetch(`${base}/ping`, { method: 'GET', mode: 'cors', signal: controller.signal, headers });
                    if (res.ok) {
                        clearTimeout(timer);
                        return '/ping';
                    }
                } catch (_) {
                    // ignore
                }
                clearTimeout(timer);
                throw new Error('No response from the agent');
            } finally {
                clearTimeout(timer);
            }
        };

        try {
            const agent = await getAgentInfo();
            const usedPath = await tryPing(agent?.endpoint);
            // console.log(`Agent ${agentId} responded to ${usedPath}`);
            this.showSuccess(`Agent ${agentId} responded to ping`);

            // Refresh agents list after successful ping
            if (this.websocket?.readyState === WebSocket.OPEN) {
                this.websocket.send(JSON.stringify({
                    type: 'agents_request',
                    timestamp: new Date().toISOString()
                }));
            }
        } catch (error) {
            this.showError(`Agent ping (${agentId}) failed: ${error.message}`);
        }
    }

    async unregisterAgent(agentId) {
        if (!this.authToken) {
            this.showAdminLoginModal((success) => {
                if (success) {
                    this.unregisterAgent(agentId);
                }
            });
            return;
        }
        // Confirm destructive action
        if (!confirm(`⚠️ DANGER: Unregister Agent "${agentId}"?\n\nThis will permanently:\n• Remove agent from registry\n• Delete all agent data\n• Clear vector embeddings\n• Remove performance metrics\n\nThis action CANNOT be undone!`)) {
            return;
        }
        // Require PIN before proceeding
        await this.requirePin(async () => {
            try {
                const response = await this.apiCall(`${this.apiBase}/agents/${agentId}`, {
                    method: 'DELETE',
                    headers: this.getAuthHeaders(true) // Include PIN for destructive operation
                });
                if (response.status === 401 || response.status === 403) {
                    alert(
                        `Authentication failed for unregister.\n\n` +
                        `Re-authenticate to proceed.`
                    );
                    // If unauthorized, ask the admin to re-authenticate and retry
                    this.logout();
                    this.showAdminLoginModal((success) => {
                        if (success) {
                            this.unregisterAgent(agentId);
                        }
                    });
                    return;
                }
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                const result = await response.json();
                await this.loadStats();
                
                // Request fresh agent data via WebSocket to reflect the unregistration
                if (this.websocket?.readyState === WebSocket.OPEN) {
                    this.websocket.send(JSON.stringify({
                        type: 'agents_request',
                        timestamp: new Date().toISOString()
                    }));
                }
                
                this.showSuccess(`Agent ${agentId} has been unregistered successfully!`);
            } catch (error) {
                console.error('Error unregistering agent:', error);
                this.addLog('ERR', `Failed to unregister agent ${agentId}: ${error.message}`);
                this.showError(`Failed to unregister agent ${agentId}: ${error.message}`);
            }
        });
    }



    async adminLogin(username, password) {
        // Validate inputs
        const usernameValidation = this.securityManager.validateInput(username, 'username');
        if (!usernameValidation.valid) {
            const errorMsg = usernameValidation.reason;
            return { success: false, error: errorMsg };
        }
        
        const passwordValidation = this.securityManager.validateInput(password, 'password');
        if (!passwordValidation.valid) {
            const errorMsg = passwordValidation.reason;
            return { success: false, error: errorMsg };
        }
        
        // Check rate limiting before attempting login
        const rateLimitCheck = this.securityManager.checkLoginRateLimit();
        if (!rateLimitCheck.allowed) {
            this.securityManager.logSecurityEvent('login_rate_limited', rateLimitCheck.reason);
            
            if (rateLimitCheck.isLockout) {
                // Show countdown for lockout
                this.showLockoutCountdown(rateLimitCheck.delay, 'login');
            }
            return { success: false, error: rateLimitCheck.reason };
        }
        
        try {
            const response = await fetch(`${this.apiBase}/auth/login`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Client-Fingerprint': this.clientFingerprint
                },
                body: JSON.stringify({ 
                    username: usernameValidation.value, 
                    password: passwordValidation.value 
                })
            });

            if (response.ok) {
                const data = await response.json();
                this.authToken = data.access_token;
                this.currentUser = usernameValidation.value;
                localStorage.setItem('arcp-admin-token', this.authToken);
                localStorage.setItem('arcp-admin-user', this.currentUser);
                
                // Record successful login
                const result = this.securityManager.recordLoginAttempt(true);
                this.securityManager.logSecurityEvent('login_success', 'Admin login successful', {
                    username: this.currentUser,
                    timestamp: new Date().toISOString()
                });
                
                this.showSuccess('Login successful! Welcome to ARCP.');
                await this.continueInit();
                return { success: true };
            } else {
                // Parse error response
                let errorData;
                try {
                    errorData = await response.json();
                } catch (e) {
                    errorData = { message: 'Unknown error occurred' };
                }
                
                // Record failed login
                const result = this.securityManager.recordLoginAttempt(false);
                this.securityManager.logSecurityEvent('login_failed', 'Admin login failed', {
                    username: usernameValidation.value,
                    status: response.status,
                    error: errorData.message || errorData.detail,
                    timestamp: new Date().toISOString()
                });
                
                let errorMessage;
                
                // Handle different error types based on status code and response
                if (response.status === 429) {
                    // Rate limit exceeded
                    const detail = errorData.detail || '';
                    let retryAfter = null;
                    
                    // Try to extract retry_after from detail string
                    if (typeof detail === 'string' && detail.includes('retry_after')) {
                        const match = detail.match(/'retry_after':\s*'(\d+)'/);
                        if (match) {
                            retryAfter = parseInt(match[1]);
                        }
                    }
                    
                    errorMessage = retryAfter 
                        ? `Too many login attempts. Wait ${retryAfter} seconds before trying again.`
                        : 'Too many login attempts. Wait before trying again.';
                    
                    if (retryAfter) {
                        this.showLockoutCountdown(retryAfter * 1000, 'login'); // Convert to milliseconds
                    }
                } else if (response.status === 401) {
                    // Invalid credentials
                    errorMessage = errorData.detail || errorData.message || 'Invalid admin credentials';
                } else {
                    // Handle local rate limiting from security manager
                    if (result.locked) {
                        errorMessage = result.message;
                        this.showLockoutCountdown(result.lockoutDuration, 'login');
                    } else if (result.nextDelay) {
                        const nextDelaySeconds = Math.ceil(result.nextDelay / 1000);
                        errorMessage = `${errorData.message || 'Login failed'}. ${result.attemptsRemaining} attempts remaining. Next attempt allowed in ${nextDelaySeconds} seconds.`;
                    } else {
                        errorMessage = errorData.message || errorData.detail || 'Login failed. Try again.';
                    }
                }
                
                return { success: false, error: errorMessage };
            }
        } catch (error) {
            console.error('Login error:', error);
            
            // Record failed attempt due to network error
            this.securityManager.recordLoginAttempt(false);
            this.securityManager.logSecurityEvent('login_error', 'Login network error', {
                error: error.message,
                timestamp: new Date().toISOString()
            });
            
            let errorMessage;
            // Handle different types of errors
            if (error.name === 'TypeError' && error.message.includes('fetch')) {
                errorMessage = 'Network connection error. Check your connection and try again.';
            } else if (error.message && error.message.includes('Rate limit')) {
                errorMessage = 'Too many login attempts. Wait before trying again.';
            } else if (error.message && error.message.includes('timeout')) {
                errorMessage = 'Request timeout. Wait before trying again.';
            } else {
                errorMessage = 'An unexpected error occurred. Wait before trying again.';
            }
            
            return { success: false, error: errorMessage };
        }
    }

    async logout(tokenExpired = false) {
        // Call backend logout endpoint to clear session PIN (only if token is still valid)
        if (this.authToken && !tokenExpired) {
            try {
                await this.apiCall(`${this.apiBase}/auth/logout`, {
                    method: 'POST',
                    headers: this.getAuthHeaders() // Include fingerprint for admin session validation
                });
            } catch (error) {
                console.error('Logout error:', error);
                // Even if logout API fails, continue with local cleanup
            }
        }
        
        // Tear down background activity
        this.disconnectWebSocket();
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
            this.pingInterval = null;
        }
        if (this.connectionHealthInterval) {
            clearInterval(this.connectionHealthInterval);
            this.connectionHealthInterval = null;
        }
        if (this.tokenValidationInterval) {
            clearInterval(this.tokenValidationInterval);
            this.tokenValidationInterval = null;
        }
        if (this.websocketRetryTimer) {
            clearTimeout(this.websocketRetryTimer);
            this.websocketRetryTimer = null;
        }
        
        // Stop sounds and prevent further playback
        try {
            if (this.alertAudioCtx) {
                this.alertAudioCtx.close();
            }
        } catch (_) {}
        this.alertAudioCtx = null;
        
        // Clear in-memory data that could trigger UI updates/alerts
        this.monitoringData.alertQueue = [];
        this.alertSuppressionMap = {};
        this.monitoringData.systemHealth = { arcp: false, redis: false, ai: false, websocket: false };
        this.renderAlerts?.();
        
        // Reset flags to prevent auto actions while logged out
        this.isPaused = true;
        this.autoRefresh = false;
        
        this.authToken = null;
        this.currentUser = null;
        this.currentPin = null; // Clear the current PIN
        
        // Clear session status cache on logout
        this.cachedSessionStatus = null;
        this.lastSessionStatusCheckAt = 0;
        
        // Clear PIN status cache on logout
        this.pinStatusCache = null;
        this.pinStatusCacheTime = 0;
        
        localStorage.removeItem('arcp-admin-token');
        localStorage.removeItem('arcp-admin-user');
        // Remove persisted dashboard data on logout
        try {
            localStorage.removeItem('arcp-dashboard-settings');
            localStorage.removeItem('arcp-dashboard-logs');
            localStorage.removeItem('arcp-dashboard-alerts');
        } catch (_) { /* ignore storage errors */ }
        // Clear client-side logs from memory and UI
        this.logs = [];
        this.renderLogs?.();
        this.updateAuthStatus();
        this.addLog('INFO', tokenExpired ? 'Session expired - logged out' : 'Admin logged out');
        
        // Hide dashboard and show login modal
        const container = document.getElementById('dashboardContainer');
        if (container) container.style.display = 'none';
        this.showAdminLoginModal((success) => {
            // Only show dashboard if login was successful
            if (success) {
                this.continueInit();
            }
        });
    }

    async checkTokenValidity() {
        const status = await this.checkSessionStatus();
        return !!status.valid;
    }

    setupTokenValidation() {
        // Clear existing interval to avoid duplicates
        if (this.tokenValidationInterval) {
            clearInterval(this.tokenValidationInterval);
            this.tokenValidationInterval = null;
        }
        
        // Check token validity every 5 minutes
        if (this.authToken) {
            this.tokenValidationInterval = setInterval(async () => {
                await this.checkSessionStatus();
            }, 5 * 60 * 1000); // 5 minutes
        }
    }

    updateAuthStatus() {
        const statusElement = document.getElementById('adminAuthStatus');
        if (statusElement) {
            if (this.currentUser) {
                statusElement.innerHTML = `
                    <span style="color: #28a745; font-weight: 500;">
                        <i class="fas fa-user-shield"></i> Admin: ${this.currentUser}
                    </span>
                    <button onclick="dashboard.logout()" style="
                        margin-left: 8px; background: #dc3545; color: white; border: none;
                        padding: 2px 8px; border-radius: 4px; font-size: 12px; cursor: pointer;
                    ">Logout</button>
                `;
            } else {
                statusElement.innerHTML = `
                    <span style="color: #6c757d;">
                        <i class="fas fa-user-slash"></i> Not authenticated
                    </span>
                    <button onclick="dashboard.showAdminLoginModal()" style="
                        margin-left: 8px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none;
                        padding: 2px 8px; border-radius: 4px; font-size: 12px; cursor: pointer;
                    ">admin Login</button>
                `;
            }
        }
    }

    showAdminLoginModal(callback) {
        // Hide any loading overlay when showing login
        try { this.showLoading(false); } catch (_) {}
        // Ensure we don't create duplicate login modals
        const existing = document.getElementById('arcp-admin-login-modal');
        if (existing) {
            try { existing.remove(); } catch (_) {}
        }
        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.id = 'arcp-admin-login-modal';

        // Check for dark mode
        const isDarkMode = document.body.classList.contains('dark-mode');

        modal.style.cssText = `
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center;
            z-index: 1000;
        `;
        const colors = {
            background: isDarkMode ? '#34495e' : 'white',
            textPrimary: isDarkMode ? '#ecf0f1' : '#333',
            textSecondary: isDarkMode ? '#bdc3c7' : '#666',
            headerColor: isDarkMode ? '#3498db' : '#667eea',
            inputBg: isDarkMode ? '#2c3e50' : '#f8f9fa',
            inputBorder: isDarkMode ? '#374151' : '#ddd',
            inputColor: isDarkMode ? '#e5e7eb' : '#333',
            labelColor: isDarkMode ? '#e5e7eb' : '#333',
            primaryGradient: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
        };

        modal.innerHTML = `
            <div class="modal-content" style="
                z-index: 99999;;
                background: ${colors.background}; border-radius: 12px; padding: 24px; max-width: 400px; width: 90%;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3); color: ${colors.textPrimary};
            ">
                <div class="modal-header" style="margin-bottom: 20px; text-align: center;">
                    <h3 style="margin: 0; color: ${colors.textPrimary};">
                        <i class="fas fa-shield-alt" style="background: ${colors.primaryGradient}; -webkit-background-clip: text; background-clip: text; color: transparent; margin-right: 8px;"></i>
                        Admin Authentication
                        <i class="fas fa-shield-alt" style="background: ${colors.primaryGradient}; -webkit-background-clip: text; background-clip: text; color: transparent; margin-left: 8px;"></i>
                    </h3>
                </div>
                <div class="modal-body">
                    <form id="adminLoginForm" style="display: flex; flex-direction: column; gap: 16px;">
                        <div>
                            <label style="display: block; margin-bottom: 4px; font-weight: 500; color: ${colors.labelColor};">Username:</label>
                            <input type="text" id="adminUsername" placeholder="Enter username" style="
                                width: 100%; padding: 8px 12px; border: 1px solid ${colors.inputBorder}; border-radius: 6px;
                                font-size: 14px; background: ${colors.inputBg}; color: ${colors.inputColor};
                            " />
                        </div>
                        <div>
                            <label style="display: block; margin-bottom: 4px; font-weight: 500; color: ${colors.labelColor};">Password:</label>
                            <input type="password" id="adminPassword" placeholder="Enter password" style="
                                width: 100%; padding: 8px 12px; border: 1px solid ${colors.inputBorder}; border-radius: 6px;
                                font-size: 14px; background: ${colors.inputBg}; color: ${colors.inputColor};
                            " />
                        </div>
                        <div style="margin-top: 20px; display: flex; gap: 12px; justify-content: flex-end;">
                            <button type="submit" style="
                                background: ${colors.primaryGradient}; color: white; border: none; padding: 8px 16px;
                                border-radius: 6px; cursor: pointer; font-weight: 600; letter-spacing: 0.2px;
                                display: block; margin: 0 auto;
                            ">Login</button>
                        </div>
                        <div id="loginError" class="validation-message"></div>
                    </form>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
        const loginError = document.getElementById('loginError');
        loginError.textContent = '';

        // Handle form submission
        const form = modal.querySelector('#adminLoginForm');
        form.onsubmit = async (e) => {
            e.preventDefault();
            const username = modal.querySelector('#adminUsername').value;
            const password = modal.querySelector('#adminPassword').value;

            if (!username || !password) {
                loginError.textContent = 'Enter both username and password.';
                loginError.classList.add('show');
                return;
            }

            const button = form.querySelector('button[type="submit"]');
            button.textContent = 'Logging in...';
            button.disabled = true;

            const result = await this.adminLogin(username, password);
            
            if (result.success) {
                modal.remove();
                if (callback) callback(true);
            } else {
                button.textContent = 'Login';
                button.disabled = false;
                
                // Show error message in modal
                if (result.error) {
                    loginError.textContent = result.error;
                    loginError.classList.add('show');
                }
                
                // Clear the form fields and re-focus
                modal.querySelector('#adminUsername').value = '';
                modal.querySelector('#adminPassword').value = '';
                // (auto-focus removed by request)
                
                if (callback) callback(false);
            }
        };

        // Track programmatic focus so we don't clear error instantly
    let suppressNextFocusClear = false; // auto-focus removed

        const clearErrorOnFocus = (e) => {
            if (suppressNextFocusClear) {
                // This was a programmatic focus; don't clear yet
                suppressNextFocusClear = false;
                return;
            }
            if (loginError.textContent) {
                loginError.textContent = '';
                loginError.classList.remove('show');
            }
        };
        modal.querySelector('#adminUsername').addEventListener('focus', clearErrorOnFocus);
        modal.querySelector('#adminPassword').addEventListener('focus', clearErrorOnFocus);

        // Do not close login modal on outside click (prevent accidental dismiss)
        modal.onclick = (e) => { /* no-op */ };
    }

    showAgentDetailsModal(agent) {
        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        
        // Check for dark mode
        const isDarkMode = document.body.classList.contains('dark-mode');
        
        modal.style.cssText = `
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center;
            z-index: 1000;
        `;
        
        // Define colors based on theme
        const colors = {
            background: isDarkMode ? '#34495e' : 'white',
            textPrimary: isDarkMode ? '#ecf0f1' : '#333',
            textSecondary: isDarkMode ? '#bdc3c7' : '#666',
            headerColor: isDarkMode ? '#3498db' : '#667eea',
            codeBackground: isDarkMode ? '#2c3e50' : '#f1f3f4',
            codeColor: isDarkMode ? '#ecf0f1' : '#333',
            descriptionBg: isDarkMode ? '#2c3e50' : '#f8f9fa',
            descriptionColor: isDarkMode ? '#bdc3c7' : '#333',
            capabilityBg: isDarkMode ? 'rgba(52, 152, 219, 0.2)' : '#e3f2fd',
            capabilityColor: isDarkMode ? '#3498db' : '#1565c0',
            tagBg: isDarkMode ? 'rgba(102, 204, 153, 0.15)' : '#e9f7ef',
            tagColor: isDarkMode ? '#66cc99' : '#1e7e34',
            statusAliveBg: isDarkMode ? 'rgba(46, 204, 113, 0.2)' : '#d4edda',
            statusAliveColor: isDarkMode ? '#2ecc71' : '#155724',
            statusDeadBg: isDarkMode ? 'rgba(231, 76, 60, 0.2)' : '#f8d7da',
            statusDeadColor: isDarkMode ? '#e74c3c' : '#721c24',
            closeButtonColor: isDarkMode ? '#95a5a6' : '#666',
            closeButtonBg: isDarkMode ? '#2c3e50' : 'transparent'
        };

        const maskKey = (key) => {
            if (!key || typeof key !== 'string') return 'N/A';
            if (key.length <= 10) return key;
            return key.slice(0, 8) + '...' + key.slice(-6);
        };

        const featuresList = Array.isArray(agent.features) ? agent.features : [];
        const languageList = Array.isArray(agent.language_support) ? agent.language_support : [];
        const policyTags = Array.isArray(agent.policy_tags) ? agent.policy_tags : [];
        const metadataEntries = agent.metadata && typeof agent.metadata === 'object' ? Object.entries(agent.metadata) : [];

        const metrics = agent.metrics || {};
        const metricsHtml = `
            <div class="detail-group">
                <h4 style="color: ${colors.headerColor}; margin-bottom: 10px;">Metrics</h4>
                <div style="display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 8px;">
                    <p style="margin:0;color:${colors.textPrimary};"><strong>Total Requests:</strong> ${metrics.total_requests ?? 0}</p>
                    <p style="margin:0;color:${colors.textPrimary};"><strong>Requests Processed:</strong> ${metrics.requests_processed ?? 0}</p>
                    <p style="margin:0;color:${colors.textPrimary};"><strong>Success Rate:</strong> ${typeof metrics.success_rate === 'number' ? (metrics.success_rate*100).toFixed(1)+'%' : 'N/A'}</p>
                    <p style="margin:0;color:${colors.textPrimary};"><strong>Error Rate:</strong> ${typeof metrics.error_rate === 'number' ? (metrics.error_rate*100).toFixed(1)+'%' : 'N/A'}</p>
                    <p style="margin:0;color:${colors.textPrimary};"><strong>Avg Response Time:</strong> ${typeof metrics.avg_response_time === 'number' ? metrics.avg_response_time.toFixed(2) + 's' : (typeof metrics.average_response_time === 'number' ? metrics.average_response_time.toFixed(2) + 's' : 'N/A')}</p>
                    <p style="margin:0;color:${colors.textPrimary};"><strong>Reputation:</strong> ${typeof metrics.reputation_score === 'number' ? metrics.reputation_score.toFixed(2) : 'N/A'}</p>
                    <p style="margin:0;color:${colors.textPrimary};"><strong>Last Active:</strong> ${metrics.last_active ? this.formatTimestamp(metrics.last_active, true, true) : 'N/A'}</p>
                </div>
            </div>`;

        const requirements = agent.requirements || {};
        const reqRequired = Array.isArray(requirements.required_fields) ? requirements.required_fields.length : 0;
        const reqOptional = Array.isArray(requirements.optional_fields) ? requirements.optional_fields.length : 0;

        modal.innerHTML = `
            <div class="modal-content" style="
                background: ${colors.background}; border-radius: 12px; padding: 24px; max-width: 800px; width: 95%;
                max-height: 85%; overflow-y: auto; box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                color: ${colors.textPrimary};
            ">
                <div class="modal-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                    <h3 style="margin: 0; color: ${colors.textPrimary};">Agent Details: ${agent.name || agent.agent_id}</h3>
                    <button class="modal-close" style="
                        background: ${colors.closeButtonBg}; border: none; font-size: 24px; cursor: pointer;
                        color: ${colors.closeButtonColor}; padding: 4px 8px; border-radius: 4px;
                    ">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="agent-detail-grid" style="display: grid; gap: 20px; grid-template-columns: 1fr;">
                        <div class="detail-group">
                            <h4 style="color: ${colors.headerColor}; margin-bottom: 10px;">Basic Information</h4>
                            <p style="color: ${colors.textPrimary};"><strong>Agent ID:</strong> ${agent.agent_id}</p>
                            <p style="color: ${colors.textPrimary};"><strong>Name:</strong> ${agent.name || 'N/A'}</p>
                            <p style="color: ${colors.textPrimary};"><strong>Type:</strong> ${agent.agent_type}</p>
                            <p style="color: ${colors.textPrimary};"><strong>Communication:</strong> ${agent.communication_mode || 'N/A'}</p>
                            <p style="color: ${colors.textPrimary};"><strong>Version:</strong> ${agent.version || 'Unknown'}</p>
                            <p style="color: ${colors.textPrimary};"><strong>Owner:</strong> ${agent.owner || 'Unknown'}</p>
                            ${typeof agent.similarity === 'number' ? `<p style="color:${colors.textPrimary};"><strong>Similarity:</strong> ${(agent.similarity*100).toFixed(1)}%</p>` : ''}
                            <p style="color: ${colors.textPrimary};"><strong>Status:</strong> <span style="
                                padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: bold;
                                ${agent.status === 'alive' ? 
                                    `background: ${colors.statusAliveBg}; color: ${colors.statusAliveColor};` : 
                                    `background: ${colors.statusDeadBg}; color: ${colors.statusDeadColor};`}
                            ">${agent.status?.toUpperCase() || 'UNKNOWN'}</span></p>
                        </div>
                        <div class="detail-group">
                            <h4 style="color: ${colors.headerColor}; margin-bottom: 10px;">Network</h4>
                            <p style="color: ${colors.textPrimary};"><strong>Endpoint:</strong> <code style="background: ${colors.codeBackground}; color: ${colors.codeColor}; padding: 2px 4px; border-radius: 3px;">${agent.endpoint || 'N/A'}</code></p>
                            <p style="color: ${colors.textPrimary};"><strong>Last Seen:</strong> ${agent.last_seen ? this.formatTimestamp(agent.last_seen, true, true) : 'Never'}</p>
                            <p style="color: ${colors.textPrimary};"><strong>Registered:</strong> ${agent.registered_at ? this.formatTimestamp(agent.registered_at, true, true) : 'Unknown'}</p>
                        </div>
                        <div class="detail-group">
                            <h4 style="color: ${colors.headerColor}; margin-bottom: 10px;">Capabilities (${(agent.capabilities || []).length})</h4>
                            <div class="capabilities-list" style="display: flex; flex-wrap: wrap; gap: 6px;">
                                ${(agent.capabilities || []).map(cap => `
                                    <span style="
                                        background: ${colors.capabilityBg}; color: ${colors.capabilityColor}; padding: 4px 8px;
                                        border-radius: 12px; font-size: 12px; font-weight: 500;
                                    ">${cap}</span>
                                `).join('')}
                            </div>
                        </div>
                        ${agent.context_brief ? `
                        <div class="detail-group">
                            <h4 style="color: ${colors.headerColor}; margin-bottom: 10px;">Description</h4>
                            <p style="background: ${colors.descriptionBg}; color: ${colors.descriptionColor}; padding: 12px; border-radius: 6px; margin: 0;">${agent.context_brief}</p>
                        </div>
                        ` : ''}
                        ${(featuresList && featuresList.length) ? `
                        <div class="detail-group">
                            <h4 style="color: ${colors.headerColor}; margin-bottom: 10px;">Features (${featuresList.length})</h4>
                            <div class="features-list" style="display:flex; flex-wrap: wrap; gap:6px;">
                                ${featuresList.map(f => `<span style="background:${colors.tagBg}; color:${colors.tagColor}; padding:4px 8px; border-radius: 12px; font-size:12px;">${f}</span>`).join('')}
                            </div>
                        </div>
                        ` : ''}
                        ${(policyTags && policyTags.length) ? `
                        <div class="detail-group">
                            <h4 style="color: ${colors.headerColor}; margin-bottom: 10px;">Policy Tags (${policyTags.length})</h4>
                            <div class="policy-tags" style="display:flex; flex-wrap: wrap; gap:6px;">
                                ${policyTags.map(t => `<span style="background:${colors.tagBg}; color:${colors.tagColor}; padding:4px 8px; border-radius: 12px; font-size:12px;">${t}</span>`).join('')}
                            </div>
                        </div>
                        ` : ''}
                        ${(languageList && languageList.length) ? `
                        <div class="detail-group">
                            <h4 style="color: ${colors.headerColor}; margin-bottom: 10px;">Languages (${languageList.length})</h4>
                            <div class="languages-list" style="display:flex; flex-wrap: wrap; gap:6px;">
                                ${languageList.map(l => `<span style="background:${colors.capabilityBg}; color:${colors.capabilityColor}; padding:4px 8px; border-radius: 12px; font-size:12px;">${l}</span>`).join('')}
                            </div>
                        </div>
                        ` : ''}
                        ${(agent.max_tokens || agent.rate_limit) ? `
                        <div class="detail-group">
                            <h4 style="color: ${colors.headerColor}; margin-bottom: 10px;">Limits</h4>
                            <p style="color:${colors.textPrimary};"><strong>Max Tokens:</strong> ${agent.max_tokens ?? 'N/A'}</p>
                            <p style="color:${colors.textPrimary};"><strong>Rate Limit:</strong> ${agent.rate_limit ?? 'N/A'}</p>
                        </div>
                        ` : ''}
                        ${agent.public_key ? `
                        <div class="detail-group">
                            <h4 style="color: ${colors.headerColor}; margin-bottom: 10px;">Public Key</h4>
                            <p style="color:${colors.textPrimary};"><code style="background:${colors.codeBackground}; color:${colors.codeColor}; padding:2px 4px; border-radius:3px;">${maskKey(agent.public_key)}</code></p>
                        </div>
                        ` : ''}
                        ${(metadataEntries && metadataEntries.length) ? `
                        <div class="detail-group">
                            <h4 style="color: ${colors.headerColor}; margin-bottom: 10px;">Metadata (${metadataEntries.length})</h4>
                            <div style="background:${colors.descriptionBg}; padding:12px; border-radius:6px;">
                                ${metadataEntries.map(([k,v]) => `<p style="margin:4px 0; color:${colors.textPrimary};"><strong>${k}:</strong> ${typeof v === 'object' ? JSON.stringify(v) : String(v)}</p>`).join('')}
                            </div>
                        </div>
                        ` : ''}
                        ${(requirements && (reqRequired || reqOptional)) ? `
                        <div class="detail-group">
                            <h4 style="color: ${colors.headerColor}; margin-bottom: 10px;">Requirements</h4>
                            <p style="color:${colors.textPrimary};"><strong>Required Fields:</strong> ${reqRequired}</p>
                            <p style="color:${colors.textPrimary};"><strong>Optional Fields:</strong> ${reqOptional}</p>
                        </div>
                        ` : ''}
                        ${metricsHtml}
                    </div>
                </div>
                <div class="modal-footer" style="margin-top: 24px; display: flex; gap: 12px; justify-content: flex-end;">
                    <button onclick="this.closest('.modal-overlay').remove()" style="
                        background: #6c757d; color: white; border: none; padding: 8px 16px;
                        border-radius: 6px; cursor: pointer; font-weight: 500;
                    ">Close</button>
                    <button onclick="dashboard.pingAgent('${agent.agent_id}'); this.closest('.modal-overlay').remove()" style="
                        background: #28a745; color: white; border: none; padding: 8px 16px;
                        border-radius: 6px; cursor: pointer; font-weight: 500;
                    ">Ping Agent</button>
                    <button onclick="dashboard.unregisterAgent('${agent.agent_id}'); this.closest('.modal-overlay').remove()" style="
                        background: #dc3545; color: white; border: none; padding: 8px 16px;
                        border-radius: 6px; cursor: pointer; font-weight: 500;
                    ">Unregister Agent</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        // Close modal handlers
        modal.querySelector('.modal-close').onclick = () => modal.remove();
        modal.onclick = (e) => {
            if (e.target === modal) modal.remove();
        };
    }

    // Handle WebSocket events
    handleAgentRegistered(agent) {
        this.addLog('SUCCESS', `New agent registered: ${agent.agent_id} (${agent.agent_type})`);
        
        // Add to local agent list if not already present
        const existingIndex = this.agents.findIndex(a => a.agent_id === agent.agent_id);
        if (existingIndex === -1) {
            this.agents.push(agent);
            this.renderAgents();
            this.updateAgentTypeFilter();
        }
        
        // Refresh stats to reflect new agent
        this.loadStats();
        this.updateRecentActivity();
    }

    handleAgentHeartbeat(agentId) {
        this.addLog('INFO', `Heartbeat received from ${agentId}`);
        
        // Update agent status in local list
        const agent = this.agents.find(a => a.agent_id === agentId);
        if (agent) {
            agent.status = 'alive';
            agent.last_seen = new Date().toISOString();
        }
        
        // Update UI immediately
        const agentCard = document.querySelector(`[data-agent-id="${agentId}"]`);
        if (agentCard) {
            agentCard.classList.remove('dead');
            agentCard.classList.add('alive');
            agentCard.dataset.status = 'alive';
            
            // Update the status badge
            const statusBadge = agentCard.querySelector('.agent-status');
            if (statusBadge) {
                statusBadge.textContent = agent.status.toUpperCase();
                statusBadge.className = 'agent-status alive';
            }
        }
        
        this.updateRecentActivity();
    }

    handleAgentDisconnected(agentId) {
        this.addLog('WARN', `Agent ${agentId} went dead`);
        
        // Update agent status in local list
        const agent = this.agents.find(a => a.agent_id === agentId);
        if (agent) {
            agent.status = 'dead';
            agent.last_seen = new Date().toISOString();
        }
        
        // Update UI immediately
        const agentCard = document.querySelector(`[data-agent-id="${agentId}"]`);
        if (agentCard) {
            agentCard.classList.remove('alive');
            agentCard.classList.add('dead');
            agentCard.dataset.status = 'dead';
            
            // Update the status badge
            const statusBadge = agentCard.querySelector('.agent-status');
            if (statusBadge) {
                statusBadge.textContent = agent.status.toUpperCase();
                statusBadge.className = 'agent-status dead';
            }
        }
        
        this.updateRecentActivity();
        this.loadStats(); // Update stats to reflect dead agent
    }

    async checkPinStatus() {
        // Check if we have a valid cached result
        const now = Date.now();
        if (this.pinStatusCache && (now - this.pinStatusCacheTime) < this.pinStatusCacheMs) {
            // console.log('PIN status: using cached result (age:', Math.round((now - this.pinStatusCacheTime) / 1000), 's)');
            return this.pinStatusCache;
        }
        
        // console.log('PIN status: making API call to /auth/pin_status');
        try {
            const resp = await this.apiCall(`${this.apiBase}/auth/pin_status`, {
                headers: {
                    'Authorization': `Bearer ${this.authToken}`,
                    'X-Client-Fingerprint': this.clientFingerprint
                }
            });
            const data = await resp.json();
            
            // Cache the result
            this.pinStatusCache = data;
            this.pinStatusCacheTime = now;
            
            // console.log('PIN status: API call successful, cached result');
            return data;
        } catch (e) {
            console.warn('Error checking PIN status:', e);
            // Return cached result if available, otherwise return default
            return this.pinStatusCache || { pin_set: false };
        }
    }

    clearPinStatusCache() {
        this.pinStatusCache = null;
        this.pinStatusCacheTime = 0;
        // console.log('PIN status cache cleared');
    }

    getPinStatusCacheInfo() {
        const now = Date.now();
        const age = this.pinStatusCacheTime ? Math.round((now - this.pinStatusCacheTime) / 1000) : 'N/A';
        const valid = this.pinStatusCache && (now - this.pinStatusCacheTime) < this.pinStatusCacheMs;
        return {
            hasCache: !!this.pinStatusCache,
            ageSeconds: age,
            isValid: valid,
            cacheMs: this.pinStatusCacheMs
        };
    }

    async refreshPinStatus() {
        // console.log('PIN status: manually refreshing cache');
        this.clearPinStatusCache();
        return await this.checkPinStatus();
    }

    setPinStatusCacheTimeout(ms) {
        this.pinStatusCacheMs = ms;
        // console.log('PIN status cache timeout set to', ms, 'ms');
    }

    async getPinStatusUncached() {
        // console.log('PIN status: making uncached API call to /auth/pin_status');
        try {
            const resp = await this.apiCall(`${this.apiBase}/auth/pin_status`, {
                headers: {
                    'Authorization': `Bearer ${this.authToken}`,
                    'X-Client-Fingerprint': this.clientFingerprint
                }
            });
            const data = await resp.json();
            // console.log('PIN status: uncached API call successful');
            return data;
        } catch (e) {
            console.warn('Error checking PIN status (uncached):', e);
            throw e;
        }
    }

    async checkAndPromptPin() {
        // Only for admin
        try {
            const data = await this.checkPinStatus();
            if (!data.pin_set) {
                await this.showPinModal({
                    mode: 'set',
                    onSuccess: () => {
                        // Clear PIN status cache since PIN was just set
                        this.pinStatusCache = null;
                        this.pinStatusCacheTime = 0;
                        this.showSuccess('PIN set for this session.');
                    }
                });
            }
        } catch (e) {
            // Ignore if not admin
        }
    }

    async showPinModal({ mode = 'verify', onSuccess = null } = {}) {
        // mode: 'set', 'verify'
        const dashboard = this; // capture dashboard instance
        return new Promise((resolve) => {
            // Indicate modal-related operation is loading
            dashboard.showLoading(true);
            const modal = document.getElementById('pinModal');
            const title = document.getElementById('pinModalTitle');
            const pinInput = document.getElementById('pinInput');
            const pinForm = document.getElementById('pinForm');
            const pinError = document.getElementById('pinError');
            const closeBtn = document.getElementById('closePinModal');
            pinInput.value = '';
            pinError.textContent = '';
            modal.style.display = 'flex';
            modal.style.zIndex = '99999';
            pinInput.type = 'password';
            // auto-focus removed
            
            // Clear error when user focuses on PIN input
            pinInput.onfocus = () => {
                pinError.textContent = '';
                pinError.classList.remove('show');
            };
            
            if (mode === 'set') {
                title.innerHTML = 'Set Session PIN<br><small style="font-size: 0.8em; color: #666;">(Required for this session)</small>';
            } else {
                title.innerHTML = 'Enter Session PIN';
            }
            const closeModal = () => {
                // In "set" mode, don't allow closing to prevent security issue
                if (mode === 'set') {
                    return; // Force user to set PIN or they'll be logged out
                }
                modal.style.display = 'none';
                pinForm.onsubmit = null;
                closeBtn.onclick = null;
                resolve(false);
            };
            
            // Only allow close button/outside click in verify mode, not set mode
            if (mode !== 'set') {
                closeBtn.onclick = closeModal;
                modal.onclick = (e) => { if (e.target === modal) closeModal(); };
            } else {
                // In set mode, disable close button and outside click
                closeBtn.style.display = 'none';
                modal.onclick = null;
            }
            pinForm.onsubmit = async (e) => {
                e.preventDefault();
                pinError.textContent = '';
                const pin = pinInput.value;
                                    
                const pinValidation = dashboard.securityManager.validateInput(pin, 'pin');

                // Validate PIN input only when setting PIN, not when verifying
                if (mode === 'set') {
                    if (!pinValidation.valid) {
                        pinError.textContent = pinValidation.reason;
                        pinError.classList.add('show');
                        
                        // Clear PIN field on validation error
                        pinInput.value = '';
                        // auto-focus removed
                        
                        return;
                    }
                }
                
                // Check rate limiting for PIN attempts (except for initial set mode)
                if (mode !== 'set') {
                    const rateLimitCheck = dashboard.securityManager.checkPinRateLimit();
                    if (!rateLimitCheck.allowed) {
                        dashboard.securityManager.logSecurityEvent('pin_rate_limited', rateLimitCheck.reason);
                        pinError.textContent = rateLimitCheck.reason;
                        pinError.classList.add('show');
                        
                        // Clear PIN field on rate limit error
                        pinInput.value = '';
                        
                        if (rateLimitCheck.isLockout) {
                            // Close modal and show lockout countdown
                            modal.style.display = 'none';
                            dashboard.showLockoutCountdown(rateLimitCheck.delay, 'pin');
                            pinForm.onsubmit = null;
                            closeBtn.onclick = null;
                            resolve(false);
                        } else {
                            // auto-focus removed
                        }
                        return;
                    }
                }
                
                try {
                    dashboard.showLoading(true);
                    if (mode === 'set') {
                        // Set PIN (only allowed if not already set)
                        const resp = await fetch(`${dashboard.apiBase}/auth/set_pin`, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'Authorization': `Bearer ${dashboard.authToken}`,
                                'X-Client-Fingerprint': dashboard.clientFingerprint
                            },
                            body: JSON.stringify({ pin: pinValidation.value })
                        });
                        
                        // console.log(resp.status);
                        if (resp.status === 400) {
                            // PIN already set for this session → switch to verify flow
                            modal.style.display = 'none';
                            closeBtn.style.display = '';
                            const verified = await dashboard.showPinModal({ mode: 'verify' });
                            resolve(!!verified);
                            return
                        } else if (resp.status === 401) {
                            dashboard.logout(true); // Token expired
                            pinError.textContent = 'Session expired. Login again.';
                            pinError.classList.add('show');
                            return;
                        } else if (resp.status === 403) {
                            pinError.textContent = 'Admin only';
                            pinError.classList.add('show');
                            pinInput.value = '';
                            // auto-focus removed
                            return;
                        } else if (resp.status === 422) {
                            // Parse error details from server response
                            let errorMsg = 'PIN validation failed';
                            try {
                                const errorData = await resp.json();
                                if (errorData.detail) {
                                    // Handle HTML-encoded detail strings like:
                                    // "['{&#x27;type&#x27;: &#x27;value_error&#x27;, &#x27;loc&#x27;: (&#x27;body&#x27;, &#x27;pin&#x27;), &#x27;msg&#x27;: &#x27;Value error, PIN is too weak&#x27;, ..."
                                    let detail = errorData.detail;
                                    
                                    // Decode HTML entities
                                    detail = detail.replace(/&#x27;/g, "'").replace(/&quot;/g, '"').replace(/&amp;/g, '&');
                                    
                                    // Try to extract the msg field from the detail
                                    const msgMatch = detail.match(/'msg':\s*'([^']+)'/);
                                    if (msgMatch && msgMatch[1]) {
                                        // Extract just the main error message part
                                        let msg = msgMatch[1];
                                        if (msg.startsWith('Value error, ')) {
                                            msg = msg.substring('Value error, '.length);
                                        }
                                        errorMsg = msg;
                                    } else if (detail.includes('PIN is too weak')) {
                                        errorMsg = 'PIN is too weak';
                                    } else if (detail.includes('too short')) {
                                        errorMsg = 'PIN is too short';
                                    } else if (detail.includes('too common')) {
                                        errorMsg = 'PIN is too common';
                                    } else {
                                        // Fallback to showing the cleaned detail
                                        errorMsg = detail;
                                    }
                                } else if (errorData.message) {
                                    errorMsg = errorData.message;
                                }
                            } catch (e) {
                                // Fallback to default message if JSON parsing fails
                                errorMsg = 'PIN validation failed';
                            }
                            
                            pinError.textContent = errorMsg;
                            pinError.classList.add('show');
                            pinInput.value = '';
                            // auto-focus removed
                            return;
                        } else if (resp.status === 429) {
                            // Rate limited - extract remaining time from server if available
                            let retryMsg = 'Rate limited. Try again later.';
                            try {
                                const h = resp.headers?.get?.('Retry-After');
                                let remaining = h ? parseInt(h, 10) : NaN;
                                let data;
                                try { data = await resp.clone().json(); } catch (_) { data = null; }
                                let details = data?.details || data?.detail || null;
                                if (typeof details === 'string') {
                                    // Attempt to parse stringified dict
                                    const m = details.match(/retry_after[^\d]*(\d+)/i);
                                    if (m && m[1]) remaining = parseInt(m[1], 10);
                                } else if (details && typeof details === 'object' && 'retry_after' in details) {
                                    remaining = parseInt(details.retry_after, 10);
                                }
                                if (!Number.isNaN(remaining) && remaining > 0) {
                                    const mins = Math.floor(remaining / 60);
                                    const secs = remaining % 60;
                                    const human = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
                                    retryMsg = `Rate limited. Try again in ${human}.`;
                                }
                            } catch (_) { /* ignore parse errors */ }
                            pinError.textContent = retryMsg;
                            pinError.classList.add('show');
                            pinInput.value = '';
                            // auto-focus removed
                            dashboard.securityManager.logSecurityEvent('pin_set_rate_limited', 'PIN set rate limited');
                            return;
                        } else if (!resp.ok) {
                            // const data = await resp.json();
                            pinError.textContent = 'Failed to set PIN.';
                            pinError.classList.add('show');
                            pinInput.value = '';
                            pinInput.focus();
                            return;
                        }
                        
                        // Store the PIN for later use
                        dashboard.currentPin = pinValidation.value;
                        
                        // Clear PIN status cache since PIN was just set
                        dashboard.pinStatusCache = null;
                        dashboard.pinStatusCacheTime = 0;
                        
                        modal.style.display = 'none';
                        // Restore close button for future modal use
                        closeBtn.style.display = '';
                        
                        // Log successful PIN set
                        dashboard.securityManager.logSecurityEvent('pin_set_success', 'Session PIN set successfully');
                        
                        if (onSuccess) onSuccess();
                        resolve(true);
                        return;
                    }
                    
                    // Verify PIN
                    const resp = await fetch(`${dashboard.apiBase}/auth/verify_pin`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${dashboard.authToken}`,
                            'X-Client-Fingerprint': dashboard.clientFingerprint
                        },
                        body: JSON.stringify({ pin: pin })
                    });
                    
                    if (!resp.ok) {
                        // Attempt to read server error detail
                        let data = null;
                        let serverMessage = 'An error occurred';
                        
                        try {
                            data = await resp.json();
                            serverMessage = data.detail || data.message || data.error || 'An error occurred';
                        } catch (e) {
                            console.error('Failed to parse error response:', e);
                            serverMessage = `Server error (${resp.status})`;
                        }
                        
                        // Record failed PIN attempt
                        const result = dashboard.securityManager.recordPinAttempt(false);
                        
                        if (resp.status === 401) {
                            dashboard.securityManager.logSecurityEvent('pin_verify_failed', serverMessage);
                            if (result.locked) {
                                pinError.textContent = result.message;
                                pinError.classList.add('show');
                                pinError.classList.remove('success');
                                modal.style.display = 'none';
                                dashboard.showLockoutCountdown(result.lockoutDuration, 'pin');
                                pinForm.onsubmit = null;
                                closeBtn.onclick = null;
                                resolve(false);
                                return;
                            } else if (result.nextDelay) {
                                const nextDelaySeconds = Math.ceil(result.nextDelay / 1000);
                                pinError.textContent = `${serverMessage}. ${result.attemptsRemaining} attempts remaining. Next attempt in ${nextDelaySeconds} seconds.`;
                                pinError.classList.add('show');
                                pinError.classList.remove('success');
                                pinInput.value = '';
                                // auto-focus removed
                            } else {
                                pinError.textContent = serverMessage;
                                pinError.classList.add('show');
                                pinError.classList.remove('success');
                                pinInput.value = '';
                                // auto-focus removed
                            }
                            if (dashboard && dashboard.addLog) dashboard.addLog('WARN', serverMessage);
                        } else if (resp.status === 429) {
                            // Rate limited by backend - include remaining time if provided
                            let retryMsg = 'Rate limited. Try again later.';
                            try {
                                const h = resp.headers?.get?.('Retry-After');
                                let remaining = h ? parseInt(h, 10) : NaN;
                                let details = (data && (data.details || data.detail)) || null;
                                if (typeof details === 'string') {
                                    const m = details.match(/retry_after[^\d]*(\d+)/i);
                                    if (m && m[1]) remaining = parseInt(m[1], 10);
                                } else if (details && typeof details === 'object' && 'retry_after' in details) {
                                    remaining = parseInt(details.retry_after, 10);
                                }
                                if (!Number.isNaN(remaining) && remaining > 0) {
                                    const mins = Math.floor(remaining / 60);
                                    const secs = remaining % 60;
                                    const human = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
                                    retryMsg = `Rate limited. Try again in ${human}.`;
                                }
                            } catch (_) { /* ignore parse errors */ }
                            pinError.textContent = retryMsg;
                            pinError.classList.add('show');
                            pinError.classList.remove('success');
                            pinInput.value = '';
                            // auto-focus removed
                            dashboard.securityManager.logSecurityEvent('pin_verify_rate_limited', 'PIN verification rate limited');
                        } else {
                            const data = await resp.json();
                            pinError.textContent = data.detail || 'Incorrect PIN.';
                            pinError.classList.add('show');
                            pinError.classList.remove('success');
                            pinInput.value = '';
                            // auto-focus removed
                        }
                        // Cancel action and keep modal open for retry or close
                        return;
                    }
                    
                    // Record successful PIN attempt
                    dashboard.securityManager.recordPinAttempt(true);
                    dashboard.securityManager.logSecurityEvent('pin_verify_success', 'PIN verification successful');
                    
                    // Store the PIN for later use
                    dashboard.currentPin = pin;
                    
                    // Clear PIN status cache since PIN was just verified
                    dashboard.pinStatusCache = null;
                    dashboard.pinStatusCacheTime = 0;
                    
                    modal.style.display = 'none';
                    // Restore close button for future modal use
                    closeBtn.style.display = '';
                    if (onSuccess) onSuccess();
                    resolve(true);
                    return;
                } catch (err) {
                    dashboard.securityManager.logSecurityEvent('pin_error', 'PIN operation network error', {
                        error: err.message
                    });
                    pinError.textContent = 'Network error. Try again.';
                    pinError.classList.add('show');
                    pinError.classList.remove('success');
                    
                    // Clear PIN field on network error
                    pinInput.value = '';
                    // auto-focus removed
                }
                finally {
                    dashboard.showLoading(false);
                }
            };
            // Loading done for modal setup
            dashboard.showLoading(false);
        });
    }

    /**
     * Show lockout countdown for rate limited attempts
     */
    showLockoutCountdown(duration, type) {
        const seconds = Math.ceil(duration / 1000);
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = seconds % 60;
        
        let message;
        if (minutes > 0) {
            message = `🔒 ${type.toUpperCase()} LOCKED: ${minutes}m ${remainingSeconds}s remaining`;
        } else {
            message = `🔒 ${type.toUpperCase()} LOCKED: ${remainingSeconds}s remaining`;
        }
        
        // Show persistent error message
        this.showCritical(message);
        
        // Update countdown every second
        let remaining = seconds;
        const countdownInterval = setInterval(() => {
            remaining--;
            
            if (remaining <= 0) {
                clearInterval(countdownInterval);
                this.showSuccess(`${type.charAt(0).toUpperCase() + type.slice(1)} attempts are now allowed again.`);
                return;
            }
            
            const mins = Math.floor(remaining / 60);
            const secs = remaining % 60;
            
            if (mins > 0) {
                message = `🔒 ${type.toUpperCase()} LOCKED: ${mins}m ${secs}s remaining`;
            } else {
                message = `🔒 ${type.toUpperCase()} LOCKED: ${secs}s remaining`;
            }
            
            // Update any visible error messages
            const errorElements = document.querySelectorAll('.notification.error');
            errorElements.forEach(element => {
                if (element.textContent.includes('LOCKED')) {
                    element.textContent = message;
                }
            });
        }, 1000);
    }

    async requirePin(actionFn) {
        // Always check if PIN is set, and prompt to set if not
        try {
            const data = await this.checkPinStatus();
            if (!data.pin_set) {
                // PIN not set, prompt to set it
                const setSuccess = await this.showPinModal({ 
                    mode: 'set', 
                    onSuccess: () => {
                        // Clear PIN status cache since PIN was just set
                        this.pinStatusCache = null;
                        this.pinStatusCacheTime = 0;
                        this.showSuccess('Session PIN set successfully. PIN will be cleared when you logout.');
                    }
                });
                if (!setSuccess) {
                    return; // User cancelled PIN setup
                }
                // If user just set PIN, run action directly without prompting again
                // Clear PIN status cache since PIN was just set
                this.pinStatusCache = null;
                this.pinStatusCacheTime = 0;
                await actionFn();
                return;
            }
            // PIN is set, continue to verification
        } catch (error) {
            console.error('Error checking PIN status:', error);
            // If we can't check status, assume PIN is set and continue to verification
        }
        
        // Always verify PIN before action
        const verified = await this.showPinModal({ mode: 'verify' });
        if (verified) {
            // Clear PIN status cache after successful verification
            this.pinStatusCache = null;
            this.pinStatusCacheTime = 0;
            await actionFn();
        }
    }

    async requirePinOrPasswordToReset() {
        // Show reset PIN modal (asks for password)
        await this.showPinModal({ mode: 'reset', onSuccess: () => {
            // Clear PIN status cache since PIN was reset
            this.pinStatusCache = null;
            this.pinStatusCacheTime = 0;
            this.showSuccess('Session PIN reset successfully. PIN will be cleared when you logout.');
        }});
    }

    async clearLogs() {
        if (this && this.addLog) this.addLog('INFO', 'Attempt to clear logs');
        await this.requirePin(async () => {
            // Clear frontend logs
            this.logs = [];
            this.renderLogs();
            
            // Clear backend logs
            if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
                try {
                    this.websocket.send(JSON.stringify({
                        type: 'clear_logs',
                        timestamp: new Date().toISOString(),
                        data: { source: 'dashboard_admin' }
                    }));
                } catch (error) {
                    console.warn('Failed to send clear logs request to backend:', error);
                    this.addLog('WARN', 'Failed to clear backend logs - WebSocket error');
                }
            } else {
                this.addLog('WARN', 'Backend logs not cleared - WebSocket not connected');
            }
        });
    }
}

// Global functions
function refreshData() {
    dashboard.refreshData();
}

function toggleAutoRefresh() {
    dashboard.autoRefresh = !dashboard.autoRefresh;
    dashboard.settings.enableAutoRefresh = dashboard.autoRefresh;
    dashboard.saveSettingsToStorage();
    // console.log('Auto-refresh toggled to:', dashboard.autoRefresh);
    dashboard.setupAutoRefresh();
}

// Global function for pause monitoring (can be called from HTML)
function toggleMonitoring() {
    if (dashboard) {
        // Direct call - PIN protection handled by event listener
        dashboard.toggleMonitoring();
    }
}

// Initialize dashboard when DOM is loaded
let dashboard;
document.addEventListener('DOMContentLoaded', () => {
    const numericOnly = id => {
        const el = document.getElementById(id);
        if (!el) return; // Skip if element not found
        
        // Block any non-digit keys
        el.addEventListener('keydown', e => {
            const ctrl = e.ctrlKey || e.metaKey;
            const allowed =
                e.key.length === 1 ? /[0-9]/.test(e.key) :
                ['Backspace','Delete','ArrowLeft','ArrowRight',
                 'Tab','Home','End','Enter'].includes(e.key) ||
                (ctrl && ['a','c','v','x'].includes(e.key.toLowerCase()));
            if (!allowed) e.preventDefault();
        });

        // Strip non-digits on paste
        el.addEventListener('paste', e => {
            e.preventDefault();
            const digits = (e.clipboardData || window.clipboardData)
                             .getData('text').replace(/\D+/g,'');
            const start = el.selectionStart;
            const end = el.selectionEnd;
            el.setRangeText(digits, start, end, 'end');
        });
    };

    numericOnly('refreshInterval');
    numericOnly('maxLogEntries');
    
    // Initialize dashboard
    dashboard = new ARCPDashboard();
});

// Export for external use
window.ARCPDashboard = ARCPDashboard;