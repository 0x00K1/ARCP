/**
 * Security Manager for ARCP Dashboard
 */

class SecurityManager {
    constructor() {
        this._attemptsStore = {
            login_attempts: { count: 0, lastAttempt: 0, lockoutUntil: 0 },
            pin_attempts: { count: 0, lastAttempt: 0, lockoutUntil: 0 }
        };
        this.loginAttempts = this.loadAttemptData('login_attempts') || this._attemptsStore.login_attempts;
        this.pinAttempts = this.loadAttemptData('pin_attempts') || this._attemptsStore.pin_attempts;
        
        // Configuration
        this.config = {
            login: {
                maxAttempts: 5,
                lockoutDuration: 300000, // 5 minutes in ms
                progressiveDelayBase: 2000, // 2 seconds base delay
                maxDelay: 60000 // 1 minute max delay
            },
            pin: {
                maxAttempts: 3,
                lockoutDuration: 180000, // 3 minutes in ms
                progressiveDelayBase: 1000, // 1 second base delay
                maxDelay: 30000 // 30 seconds max delay
            }
        };
        
        // Clean up old data on initialization
        this.cleanupOldData();
    }
    
    /**
     * Load attempt data from in-memory store with error handling
     */
    loadAttemptData(key) {
        try {
            const data = this._attemptsStore ? this._attemptsStore[key] : null;
            return data ? { ...data } : null;
        } catch (e) {
            this.logToSystem('WARN', `Failed to load security data for ${key}: ${e.message}`);
            return null;
        }
    }
    
    /**
     * Save attempt data to in-memory store
     */
    saveAttemptData(key, data) {
        try {
            if (!this._attemptsStore) this._attemptsStore = {};
            if (this._attemptsStore[key]) {
                Object.assign(this._attemptsStore[key], data);
            } else {
                this._attemptsStore[key] = { ...data };
            }
        } catch (e) {
            this.logToSystem('WARN', `Failed to save security data for ${key}: ${e.message}`);
        }
    }
    
    /**
     * Clean up old attempt data (older than 24 hours)
     */
    cleanupOldData() {
        const now = Date.now();
        const maxAge = 24 * 60 * 60 * 1000; // 24 hours
        
        // Clean login attempts
        if (this.loginAttempts.lastAttempt && (now - this.loginAttempts.lastAttempt) > maxAge) {
            this.loginAttempts = { count: 0, lastAttempt: 0, lockoutUntil: 0 };
            this.saveAttemptData('login_attempts', this.loginAttempts);
        }
        
        // Clean PIN attempts
        if (this.pinAttempts.lastAttempt && (now - this.pinAttempts.lastAttempt) > maxAge) {
            this.pinAttempts = { count: 0, lastAttempt: 0, lockoutUntil: 0 };
            this.saveAttemptData('pin_attempts', this.pinAttempts);
        }
    }
    
    /**
     * Calculate progressive delay based on attempt count
     */
    calculateDelay(attemptCount, config) {
        if (attemptCount <= 1) return 0;
        
        // Exponential backoff: base * 2^(attempts-2)
        const delay = config.progressiveDelayBase * Math.pow(2, attemptCount - 2);
        return Math.min(delay, config.maxDelay);
    }
    
    /**
     * Check if login attempts are currently rate limited
     */
    checkLoginRateLimit() {
        return this.checkRateLimit('login', this.loginAttempts);
    }
    
    /**
     * Check if PIN attempts are currently rate limited
     */
    checkPinRateLimit() {
        return this.checkRateLimit('pin', this.pinAttempts);
    }
    
    /**
     * Generic rate limit checker
     */
    checkRateLimit(type, attempts) {
        const now = Date.now();
        const config = this.config[type];
        
        // Check if currently locked out
        if (attempts.lockoutUntil && now < attempts.lockoutUntil) {
            const remainingTime = Math.ceil((attempts.lockoutUntil - now) / 1000);
            return {
                allowed: false,
                reason: `Too many ${type} attempts. Locked out for ${remainingTime} more seconds.`,
                delay: remainingTime * 1000,
                isLockout: true
            };
        }
        
        // Clear lockout if expired
        if (attempts.lockoutUntil && now >= attempts.lockoutUntil) {
            attempts.lockoutUntil = 0;
            attempts.count = 0; // Reset count after lockout expires
            this.saveAttemptData(`${type}_attempts`, attempts);
        }
        
        // Check progressive delay
        if (attempts.count > 1 && attempts.lastAttempt) {
            const requiredDelay = this.calculateDelay(attempts.count, config);
            const timeSinceLastAttempt = now - attempts.lastAttempt;
            
            if (timeSinceLastAttempt < requiredDelay) {
                const remainingDelay = Math.ceil((requiredDelay - timeSinceLastAttempt) / 1000);
                return {
                    allowed: false,
                    reason: `Wait ${remainingDelay} seconds before trying again.`,
                    delay: requiredDelay - timeSinceLastAttempt,
                    isDelay: true
                };
            }
        }
        
        return { allowed: true };
    }
    
    /**
     * Record a login attempt
     */
    recordLoginAttempt(success) {
        return this.recordAttempt('login', this.loginAttempts, success);
    }
    
    /**
     * Record a PIN attempt
     */
    recordPinAttempt(success) {
        return this.recordAttempt('pin', this.pinAttempts, success);
    }
    
    /**
     * Generic attempt recorder
     */
    recordAttempt(type, attempts, success) {
        const now = Date.now();
        const config = this.config[type];
        
        if (success) {
            // Reset on success
            attempts.count = 0;
            attempts.lastAttempt = now;
            attempts.lockoutUntil = 0;
            this.saveAttemptData(`${type}_attempts`, attempts);
            
            // console.log(`Successful ${type} attempt - counters reset`);
            return { success: true };
        }
        
        // Record failed attempt
        attempts.count += 1;
        attempts.lastAttempt = now;
        
        // this.logToSystem('WARN', `Failed ${type} attempt ${attempts.count}/${config.maxAttempts}`);
        
        // Check if lockout threshold reached
        if (attempts.count >= config.maxAttempts) {
            attempts.lockoutUntil = now + config.lockoutDuration;
            attempts.count = 0; // Reset count for next cycle
            
            const lockoutMinutes = Math.ceil(config.lockoutDuration / 60000);
            this.logToSystem('ERR', `${type} lockout activated for ${lockoutMinutes} minutes`);
            
            this.saveAttemptData(`${type}_attempts`, attempts);
            
            return {
                success: false,
                locked: true,
                lockoutDuration: config.lockoutDuration,
                message: `Too many failed ${type} attempts. Locked out for ${lockoutMinutes} minutes.`
            };
        }
        
        this.saveAttemptData(`${type}_attempts`, attempts);
        
        const nextDelay = this.calculateDelay(attempts.count + 1, config);
        return {
            success: false,
            nextDelay: nextDelay,
            attemptsRemaining: config.maxAttempts - attempts.count
        };
    }
    
    /**
     * Clear all security data (for testing or reset)
     */
    clearAllData() {
        this._attemptsStore.login_attempts = { count: 0, lastAttempt: 0, lockoutUntil: 0 };
        this._attemptsStore.pin_attempts = { count: 0, lastAttempt: 0, lockoutUntil: 0 };
        this.loginAttempts = this._attemptsStore.login_attempts;
        this.pinAttempts = this._attemptsStore.pin_attempts;
        // console.log('Security data cleared');
    }
    
    /**
     * Get current security status
     */
    getSecurityStatus() {
        const now = Date.now();
        
        return {
            login: {
                attempts: this.loginAttempts.count,
                lastAttempt: this.loginAttempts.lastAttempt,
                isLockedOut: this.loginAttempts.lockoutUntil > now,
                lockoutRemaining: Math.max(0, this.loginAttempts.lockoutUntil - now)
            },
            pin: {
                attempts: this.pinAttempts.count,
                lastAttempt: this.pinAttempts.lastAttempt,
                isLockedOut: this.pinAttempts.lockoutUntil > now,
                lockoutRemaining: Math.max(0, this.pinAttempts.lockoutUntil - now)
            }
        };
    }
    
    /**
     * Create a secure delay promise
     */
    createSecureDelay(milliseconds) {
        return new Promise(resolve => {
            const startTime = Date.now();
            const minDelay = Math.max(500, milliseconds); // Minimum 500ms delay
            
            setTimeout(() => {
                const elapsed = Date.now() - startTime;
                if (elapsed < minDelay) {
                    // Ensure minimum delay is enforced
                    setTimeout(resolve, minDelay - elapsed);
                } else {
                    resolve();
                }
            }, milliseconds);
        });
    }
    
    /**
     * Validate user input for security
     */
    validateInput(input, type) {
        if (!input || typeof input !== 'string') {
            return { valid: false, reason: 'Invalid input' };
        }
        
        const trimmed = input.trim();
        
        if (type === 'username') {
            if (trimmed.length < 3) {
                return { valid: false, reason: 'Username too short' };
            }
            if (trimmed.length > 50) {
                return { valid: false, reason: 'Username too long' };
            }
            if (!/^[a-zA-Z0-9_.-]+$/.test(trimmed)) {
                return { valid: false, reason: 'Username contains invalid characters' };
            }
        }
        
        if (type === 'password') {
            if (trimmed.length < 1) {
                return { valid: false, reason: 'Password cannot be empty' };
            }
            if (trimmed.length > 200) {
                return { valid: false, reason: 'Password too long' };
            }
        }
        
        if (type === 'pin') {
            if (trimmed.length < 4) {
                return { valid: false, reason: 'PIN must be at least 4 characters' };
            }
            if (trimmed.length > 32) {
                return { valid: false, reason: 'PIN must be no more than 32 characters' };
            }
        }
        
        return { valid: true, value: trimmed };
    }
    
    /**
     * Log security events to console with timestamp
     */
    logSecurityEvent(type, message, data = {}) {
        const timestamp = new Date().toISOString();
        const logData = {
            timestamp,
            type,
            message,
            ...data
        };
        
        // Determine appropriate log level based on event type
        let logLevel = 'INFO'; // default
        if (type.includes('failed') || type.includes('error') || type.includes('lockout')) {
            logLevel = 'ERR';
        } else if (type.includes('rate_limited') || type.includes('warning')) {
            logLevel = 'WARN';
        } else if (type.includes('success')) {
            logLevel = 'SUCS';
        }
        
        // Log to dashboard if available (using standardized levels)
        if (typeof window !== 'undefined' && window.dashboard && typeof window.dashboard.addLog === 'function') {
            window.dashboard.addLog(logLevel, `Security: ${message}`);
        }
        
        // Store in session storage for dashboard debugging (limited storage)
        try {
            const securityLogs = JSON.parse(sessionStorage.getItem('arcp_security_logs') || '[]');
            securityLogs.push(logData);
            
            // Keep only last 50 entries
            if (securityLogs.length > 50) {
                securityLogs.splice(0, securityLogs.length - 50);
            }
            
            sessionStorage.setItem('arcp_security_logs', JSON.stringify(securityLogs));
        } catch (e) {
            this.logToSystem('WARN', `Failed to store security log: ${e.message}`);
        }
    }
    
    /**
     * Helper method to log directly to dashboard
     */
    logToSystem(level, message) {
        // Try to access the global dashboard instance and call its addLog method directly
        if (typeof window !== 'undefined' && window.dashboard && typeof window.dashboard.addLog === 'function') {
            window.dashboard.addLog(level, `[SecurityManager] ${message}`);
        }
        // If dashboard not available, fail silently to avoid console interception
        // Console fallback removed to prevent log level conflicts
    }
}
