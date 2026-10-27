// SITEGUARD V2 — Dashboard Controller
// Handles live camera polling, hardware telemetry updates,
// incident feed, hardware simulation controls

let lastIncidentId = 0;
let isPolling = true;

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    initCameraControls();
    initHardwareSimulation();
    startPolling();
    fetchRecentIncidents();
});

// ─────────────────────────────────────────────────────────────
// Audio System (Web Audio API — Zero External Dependencies)
// ─────────────────────────────────────────────────────────────
const SafetyAudio = {
    ctx: null,
    muted: false,

    init() {
        if (!this.ctx) {
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            if (AudioCtx) {
                this.ctx = new AudioCtx();
            }
        }
    },

    playBeep(freq = 440, duration = 0.15, type = 'sine') {
        if (this.muted) return;
        try {
            this.init();
            if (!this.ctx) return;
            if (this.ctx.state === 'suspended') {
                this.ctx.resume();
            }
            const osc = this.ctx.createOscillator();
            const gain = this.ctx.createGain();
            osc.type = type;
            osc.frequency.setValueAtTime(freq, this.ctx.currentTime);
            gain.gain.setValueAtTime(0.12, this.ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + duration);
            osc.connect(gain);
            gain.connect(this.ctx.destination);
            osc.start();
            osc.stop(this.ctx.currentTime + duration);
        } catch (e) {
            // Audio context not allowed before gesture
        }
    },

    playAlarm() {
        this.playBeep(880, 0.12, 'sawtooth');
        setTimeout(() => this.playBeep(660, 0.15, 'sawtooth'), 150);
        setTimeout(() => this.playBeep(880, 0.12, 'sawtooth'), 320);
    },

    playPass() {
        this.playBeep(523, 0.12, 'sine');
        setTimeout(() => this.playBeep(659, 0.20, 'sine'), 130);
    }
};

// Enable audio context upon any initial click
document.addEventListener('click', () => SafetyAudio.init(), { once: true });

// ─────────────────────────────────────────────────────────────
// 1. Camera Surveillance Controls
// ─────────────────────────────────────────────────────────────
function initCameraControls() {
    const btnStart = document.getElementById('btnStartCamera');
    const btnStop = document.getElementById('btnStopCamera');
    const selCamera = document.getElementById('selCameraSource');
    const btnAudioToggle = document.getElementById('btnAudioToggle');

    if (btnStart) {
        btnStart.addEventListener('click', () => {
            const source = selCamera ? selCamera.value : 0;
            btnStart.disabled = true;
            btnStart.classList.add('opacity-50');

            fetch('/api/camera/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source: source })
            })
            .then(res => res.json())
            .then(data => {
                showToast("Live camera surveillance started", "success");
                reloadVideoFeed();
            })
            .catch(err => {
                showToast("Failed to initiate camera stream", "danger");
            })
            .finally(() => {
                btnStart.disabled = false;
                btnStart.classList.remove('opacity-50');
            });
        });
    }

    if (btnStop) {
        btnStop.addEventListener('click', () => {
            btnStop.disabled = true;
            fetch('/api/camera/stop', { method: 'POST' })
            .then(res => res.json())
            .then(() => {
                showToast("Camera stream stopped — Standby mode", "info");
                reloadVideoFeed();
            })
            .catch(err => {
                showToast("Failed to stop camera stream", "danger");
            })
            .finally(() => {
                btnStop.disabled = false;
            });
        });
    }

    if (btnAudioToggle) {
        btnAudioToggle.addEventListener('click', () => {
            SafetyAudio.muted = !SafetyAudio.muted;
            btnAudioToggle.innerHTML = SafetyAudio.muted
                ? '<i class="fa-solid fa-volume-xmark mr-1.5 text-danger"></i> Sound: OFF'
                : '<i class="fa-solid fa-volume-high mr-1.5 text-success"></i> Sound: ON';
            showToast(SafetyAudio.muted ? "Sound alerts muted" : "Sound alerts enabled", "info");
        });
    }
}

function reloadVideoFeed() {
    const img = document.getElementById('videoStream');
    if (img) {
        img.src = '/video_feed?t=' + new Date().getTime();
    }
}

// ─────────────────────────────────────────────────────────────
// 2. Hardware Simulation & Gate Controls
// ─────────────────────────────────────────────────────────────
function initHardwareSimulation() {
    const btnIr = document.getElementById('btnSimIr');
    const sliderDist = document.getElementById('sliderSimDist');
    const btnAlarm = document.getElementById('btnSimAlarm');
    const btnPass = document.getElementById('btnSimPass');
    const btnReset = document.getElementById('btnSimReset');
    const btnReconnect = document.getElementById('btnHwReconnect');

    if (btnIr) {
        btnIr.addEventListener('click', () => {
            triggerHardwareSim('ir_toggle');
        });
    }

    if (sliderDist) {
        sliderDist.addEventListener('input', (e) => {
            const val = e.target.value;
            const lbl = document.getElementById('lblDistVal');
            if (lbl) lbl.textContent = val + ' cm';
            triggerHardwareSim('distance', val);
        });
    }

    if (btnAlarm) {
        btnAlarm.addEventListener('click', () => {
            triggerHardwareSim('test_alarm');
            SafetyAudio.playAlarm();
            showToast("Buzzer alarm test triggered", "danger");
        });
    }

    if (btnPass) {
        btnPass.addEventListener('click', () => {
            triggerHardwareSim('test_pass');
            SafetyAudio.playPass();
            showToast("Gate pass clearance test triggered", "success");
        });
    }

    if (btnReset) {
        btnReset.addEventListener('click', () => {
            triggerHardwareSim('reset');
            showToast("Hardware simulation state reset", "info");
        });
    }

    if (btnReconnect) {
        btnReconnect.addEventListener('click', () => {
            fetch('/api/hardware/reconnect', { method: 'POST' })
            .then(r => r.json())
            .then(d => {
                const msg = d.is_connected
                    ? "Arduino Uno connected on serial port"
                    : "No physical Arduino found. Operating in simulation mode.";
                showToast(msg, d.is_connected ? "success" : "info");
            })
            .catch(() => {
                showToast("Hardware connection request failed", "danger");
            });
        });
    }
}

function triggerHardwareSim(eventType, value = null) {
    fetch('/api/hardware/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event: eventType, value: value })
    })
    .then(r => r.json())
    .then(data => {
        if (data.telemetry) {
            updateHardwareUI(data.telemetry);
        }
    })
    .catch(() => {});
}

// ─────────────────────────────────────────────────────────────
// 3. Polling Engine (Every 850ms)
// ─────────────────────────────────────────────────────────────
function startPolling() {
    setInterval(() => {
        if (!isPolling) return;

        fetch('/api/stats')
            .then(r => {
                if (!r.ok) throw new Error('Network response not ok');
                return r.json();
            })
            .then(stats => {
                updateDashboardStats(stats);
                if (stats.hardware) {
                    updateHardwareUI(stats.hardware);
                }
            })
            .catch(() => {});

        fetchRecentIncidents();
    }, 850);
}

// ─────────────────────────────────────────────────────────────
// 4. Update Dashboard Stats DOM Elements
// ─────────────────────────────────────────────────────────────
function updateDashboardStats(stats) {
    const elTotal = document.getElementById('statTotalWorkers');
    const elCompliant = document.getElementById('statCompliant');
    const elViolators = document.getElementById('statViolators');
    const elSafetyRate = document.getElementById('statSafetyRate');
    const elRateBar = document.getElementById('safetyRateBar');
    const elFps = document.getElementById('statFps');
    const elCamStatus = document.getElementById('camStatusBadge');

    if (elTotal && stats.total_workers !== undefined) {
        elTotal.textContent = stats.total_workers;
    }

    if (elCompliant && stats.compliant_workers !== undefined) {
        elCompliant.textContent = stats.compliant_workers;
    }

    if (elViolators && stats.violators !== undefined) {
        elViolators.textContent = stats.violators;
        const violCard = document.getElementById('cardViolators');
        if (violCard) {
            if (stats.violators > 0) {
                violCard.classList.add('border-danger', 'pulse-danger');
            } else {
                violCard.classList.remove('border-danger', 'pulse-danger');
            }
        }
    }

    if (elSafetyRate && stats.safety_rate !== undefined) {
        const rate = Math.round(stats.safety_rate);
        elSafetyRate.textContent = rate + '%';

        if (elRateBar) {
            elRateBar.style.width = rate + '%';
            if (rate >= 80) {
                elRateBar.className = "h-2 rounded-full bg-success transition-all duration-300";
                elSafetyRate.className = "text-2xl font-black text-emerald-400 font-mono";
            } else if (rate >= 50) {
                elRateBar.className = "h-2 rounded-full bg-gold transition-all duration-300";
                elSafetyRate.className = "text-2xl font-black text-gold font-mono";
            } else {
                elRateBar.className = "h-2 rounded-full bg-danger transition-all duration-300";
                elSafetyRate.className = "text-2xl font-black text-red-400 font-mono";
            }
        }
    }

    if (elFps && stats.fps !== undefined) {
        elFps.textContent = stats.fps + ' FPS';
    }

    if (elCamStatus && stats.is_camera_active !== undefined) {
        if (stats.is_camera_active) {
            elCamStatus.innerHTML = '<span class="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span> <span class="text-emerald-400 font-bold font-mono text-xs">LIVE SURVEILLANCE</span>';
        } else {
            elCamStatus.innerHTML = '<span class="w-2 h-2 rounded-full bg-silver-muted"></span> <span class="text-silver-muted font-mono text-xs">STANDBY</span>';
        }
    }
}

// ─────────────────────────────────────────────────────────────
// 5. Update Hardware Telemetry & Gate UI
// ─────────────────────────────────────────────────────────────
function updateHardwareUI(hw) {
    if (!hw) return;

    // 1. LCD Screen Lines
    const line1 = document.getElementById('lcdLine1');
    const line2 = document.getElementById('lcdLine2');
    if (line1) line1.textContent = hw.lcd_line1 || "SITE SAFETY GATE";
    if (line2) line2.textContent = hw.lcd_line2 || "SYSTEM READY";

    // 2. IR Sensor Indicator Badge
    const irBadge = document.getElementById('hwIrBadge');
    if (irBadge) {
        if (hw.ir_triggered) {
            irBadge.className = "px-2.5 py-1 rounded-md text-xs font-bold bg-gold/20 text-gold border border-gold/40 flex items-center gap-1.5 animate-pulse";
            irBadge.innerHTML = '<i class="fa-solid fa-person-walking"></i> WORKER AT GATE';
        } else {
            irBadge.className = "px-2.5 py-1 rounded-md text-xs font-medium bg-charcoal text-silver-muted border border-border flex items-center gap-1.5";
            irBadge.innerHTML = '<i class="fa-solid fa-circle text-[8px] text-silver-muted"></i> GATE CLEAR';
        }
    }

    // 3. Ultrasonic Distance Gauge
    const distText = document.getElementById('hwDistText');
    const distBar = document.getElementById('hwDistBar');
    const distHazardAlert = document.getElementById('hwHazardAlert');

    if (distText && hw.distance_cm !== undefined) {
        distText.textContent = Math.round(hw.distance_cm) + ' cm';
    }

    if (distBar && hw.distance_cm !== undefined) {
        const pct = Math.min(100, Math.max(5, (hw.distance_cm / 200) * 100));
        distBar.style.width = pct + '%';
        if (hw.proximity_alert) {
            distBar.className = "h-2 rounded-full bg-danger transition-all duration-200";
            if (distHazardAlert) distHazardAlert.classList.remove('hidden');
        } else {
            distBar.className = "h-2 rounded-full bg-success transition-all duration-200";
            if (distHazardAlert) distHazardAlert.classList.add('hidden');
        }
    }

    // 4. Buzzer Badge
    const buzzerBadge = document.getElementById('hwBuzzerBadge');
    if (buzzerBadge) {
        if (hw.buzzer_active) {
            buzzerBadge.className = "px-2.5 py-1 rounded-md text-xs font-bold bg-danger/20 text-red-400 border border-danger/40 flex items-center gap-1.5 animate-bounce";
            buzzerBadge.innerHTML = '<i class="fa-solid fa-volume-high"></i> ALARM SOUNDING';
        } else {
            buzzerBadge.className = "px-2.5 py-1 rounded-md text-xs font-medium bg-charcoal text-silver-muted border border-border flex items-center gap-1.5";
            buzzerBadge.innerHTML = '<i class="fa-solid fa-volume-xmark text-silver-muted"></i> SILENT';
        }
    }

    // 5. Hardware Mode Badge in Header & Control Panel
    const topText = document.getElementById('topHwText');
    const topDot = document.getElementById('topHwDot');
    const panelMode = document.getElementById('hwPanelMode');

    if (topText) topText.textContent = hw.hardware_mode || "SIMULATION";
    if (topDot) {
        topDot.className = hw.is_connected ? "w-2 h-2 rounded-full bg-emerald-400" : "w-2 h-2 rounded-full bg-gold";
    }
    if (panelMode) {
        panelMode.textContent = hw.hardware_mode || "SIMULATION";
        panelMode.className = hw.is_connected ? "text-xs font-mono font-bold text-emerald-400" : "text-xs font-mono font-semibold text-gold";
    }
}

// ─────────────────────────────────────────────────────────────
// 6. Recent Incidents Feed (Metallic Chic Cards)
// ─────────────────────────────────────────────────────────────
function fetchRecentIncidents() {
    fetch('/api/incidents/recent')
        .then(r => {
            if (!r.ok) throw new Error('Failed to fetch incidents');
            return r.json();
        })
        .then(incidents => {
            const feed = document.getElementById('incidentFeedContainer');
            if (!feed) return;

            if (!incidents || incidents.length === 0) {
                feed.innerHTML = `
                    <div class="text-center py-10 px-4 text-silver-muted text-xs">
                        <div class="w-12 h-12 mx-auto rounded-xl bg-obsidian border border-border flex items-center justify-center text-gold mb-2 gold-glow-sm">
                            <i class="fa-solid fa-shield-halved text-xl"></i>
                        </div>
                        <p class="font-bold text-ivory">No Safety Violations Logged</p>
                        <p class="text-[11px] text-silver-muted mt-0.5">All monitored personnel are currently PPE compliant.</p>
                    </div>`;
                return;
            }

            // Check if a brand-new violation arrived
            const newest = incidents[0];
            if (newest && newest.id > lastIncidentId && lastIncidentId !== 0) {
                SafetyAudio.playAlarm();
                showToast(`Violation Flagged: ${newest.worker_label || 'Worker'} missing ${newest.missing_ppe}`, 'danger');
            }
            if (newest) {
                lastIncidentId = Math.max(lastIncidentId, newest.id);
            }

            let html = '';
            incidents.forEach(inc => {
                // Missing PPE red badges
                const missingBadges = (inc.missing_ppe || 'Gear')
                    .split(',')
                    .map(item => `<span class="px-1.5 py-0.5 rounded bg-danger/20 text-red-300 font-mono text-[10px] border border-danger/40">${item.trim()}</span>`)
                    .join(' ');

                // Snapshot Thumbnail
                const imgHtml = inc.snapshot_path 
                    ? `<img src="/static/${inc.snapshot_path}" alt="violation" class="w-12 h-12 rounded object-cover border border-border shrink-0">`
                    : `<div class="w-12 h-12 rounded bg-obsidian border border-border flex items-center justify-center text-red-400 shrink-0"><i class="fa-solid fa-person-circle-exclamation text-lg"></i></div>`;

                const timeStr = inc.timestamp ? (inc.timestamp.includes(' ') ? inc.timestamp.split(' ')[1] : inc.timestamp) : '';

                // Status pill
                let statusBadge = '';
                if (inc.status === 'Open') {
                    statusBadge = '<span class="text-[10px] font-mono px-2 py-0.5 rounded bg-danger/15 text-red-300 border border-danger/30">Open</span>';
                } else if (inc.status === 'Reviewed') {
                    statusBadge = '<span class="text-[10px] font-mono px-2 py-0.5 rounded bg-info/15 text-blue-300 border border-info/30">Reviewed</span>';
                } else {
                    statusBadge = '<span class="text-[10px] font-mono px-2 py-0.5 rounded bg-success/15 text-emerald-300 border border-success/30">Resolved</span>';
                }

                html += `
                    <div class="p-3 bg-charcoal hover:bg-charcoal-hover rounded-lg border border-border hover:border-gold/50 transition-all duration-200 flex items-start gap-3 shadow-sm">
                        ${imgHtml}
                        <div class="flex-1 min-w-0">
                            <div class="flex items-center justify-between gap-1">
                                <span class="font-bold text-xs text-ivory truncate font-sans">${inc.worker_label || 'Worker'}</span>
                                <span class="text-[10px] text-silver-muted font-mono">${timeStr}</span>
                            </div>
                            <div class="flex items-center justify-between mt-1">
                                <div class="text-[10px] font-mono text-red-400 uppercase font-semibold">Missing:</div>
                                ${statusBadge}
                            </div>
                            <div class="flex flex-wrap gap-1 mt-1">${missingBadges}</div>
                        </div>
                    </div>
                `;
            });

            feed.innerHTML = html;
        })
        .catch(() => {});
}

// ─────────────────────────────────────────────────────────────
// 7. Floating Toast Notification System
// ─────────────────────────────────────────────────────────────
function showToast(message, type = 'info') {
    let container = document.getElementById('toastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastContainer';
        container.className = 'fixed bottom-5 right-5 z-50 flex flex-col space-y-2 pointer-events-none';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `pointer-events-auto px-4 py-3 rounded-lg shadow-xl text-xs font-medium flex items-center gap-2.5 transition-all duration-300 transform translate-y-2 border max-w-sm`;

    let iconClass = 'fa-solid fa-circle-info text-info';
    let styleClasses = 'bg-charcoal text-ivory border-border';

    if (type === 'danger' || type === 'error') {
        iconClass = 'fa-solid fa-triangle-exclamation text-danger';
        styleClasses = 'bg-charcoal text-ivory border-danger/50 shadow-danger/10';
    } else if (type === 'success') {
        iconClass = 'fa-solid fa-circle-check text-success';
        styleClasses = 'bg-charcoal text-ivory border-success/50 shadow-success/10';
    } else if (type === 'warning') {
        iconClass = 'fa-solid fa-triangle-exclamation text-gold';
        styleClasses = 'bg-charcoal text-ivory border-gold/50 shadow-gold/10';
    } else {
        iconClass = 'fa-solid fa-circle-info text-info';
        styleClasses = 'bg-charcoal text-ivory border-info/50 shadow-info/10';
    }

    toast.className += ` ${styleClasses}`;
    toast.innerHTML = `<i class="${iconClass} text-sm"></i><span class="flex-1 leading-snug">${message}</span>`;

    container.appendChild(toast);

    requestAnimationFrame(() => {
        toast.classList.remove('translate-y-2');
        toast.classList.add('translate-y-0');
    });

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(8px)';
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}
