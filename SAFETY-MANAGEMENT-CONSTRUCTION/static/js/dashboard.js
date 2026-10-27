/**
 * Construction Site Safety Monitoring - Live Dashboard Controller
 */

let lastIncidentId = 0;
let isPolling = true;

document.addEventListener('DOMContentLoaded', () => {
    initControls();
    initHardwareSimulation();
    startPolling();
    fetchRecentIncidents();
});

function initControls() {
    const btnStart = document.getElementById('btnStartCamera');
    const btnStop = document.getElementById('btnStopCamera');
    const selCamera = document.getElementById('selCameraSource');
    const btnAudioToggle = document.getElementById('btnAudioToggle');

    if (btnStart) {
        btnStart.addEventListener('click', () => {
            const source = selCamera ? selCamera.value : 0;
            fetch('/api/camera/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source: source })
            })
            .then(res => res.json())
            .then(data => {
                showToast("Camera stream started", "success");
                reloadVideoFeed();
            });
        });
    }

    if (btnStop) {
        btnStop.addEventListener('click', () => {
            fetch('/api/camera/stop', { method: 'POST' })
            .then(res => res.json())
            .then(() => {
                showToast("Camera stopped", "info");
                reloadVideoFeed();
            });
        });
    }

    if (btnAudioToggle) {
        btnAudioToggle.addEventListener('click', () => {
            SafetyAudio.muted = !SafetyAudio.muted;
            btnAudioToggle.innerHTML = SafetyAudio.muted 
                ? '<i class="fa-solid fa-volume-xmark mr-1.5 text-red-400"></i> Sound: OFF'
                : '<i class="fa-solid fa-volume-high mr-1.5 text-emerald-400"></i> Sound: ON';
        });
    }
}

function reloadVideoFeed() {
    const img = document.getElementById('videoStream');
    if (img) {
        img.src = '/video_feed?t=' + new Date().getTime();
    }
}

function initHardwareSimulation() {
    // Buttons for testing Arduino & sensors
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
        });
    }

    if (btnPass) {
        btnPass.addEventListener('click', () => {
            triggerHardwareSim('test_pass');
            SafetyAudio.playPass();
        });
    }

    if (btnReset) {
        btnReset.addEventListener('click', () => {
            triggerHardwareSim('reset');
        });
    }

    if (btnReconnect) {
        btnReconnect.addEventListener('click', () => {
            fetch('/api/hardware/reconnect', { method: 'POST' })
            .then(r => r.json())
            .then(d => {
                showToast(d.is_connected ? "Arduino connected on serial!" : "No Arduino found. Running in simulation mode.", d.is_connected ? "success" : "info");
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
        if (data.telemetry) updateHardwareUI(data.telemetry);
    });
}

function startPolling() {
    setInterval(() => {
        if (!isPolling) return;
        fetch('/api/stats')
            .then(r => r.json())
            .then(stats => {
                updateDashboardStats(stats);
                if (stats.hardware) updateHardwareUI(stats.hardware);
            })
            .catch(() => {});
            
        fetchRecentIncidents();
    }, 850);
}

function updateDashboardStats(stats) {
    // Workers stats
    const elTotal = document.getElementById('statTotalWorkers');
    const elCompliant = document.getElementById('statCompliant');
    const elViolators = document.getElementById('statViolators');
    const elSafetyRate = document.getElementById('statSafetyRate');
    const elRateBar = document.getElementById('safetyRateBar');
    const elFps = document.getElementById('statFps');
    const elCamStatus = document.getElementById('camStatusBadge');

    if (elTotal) elTotal.textContent = stats.total_workers;
    if (elCompliant) elCompliant.textContent = stats.compliant_workers;
    if (elViolators) {
        elViolators.textContent = stats.violators;
        const violCard = document.getElementById('cardViolators');
        if (violCard) {
            if (stats.violators > 0) {
                violCard.classList.add('border-red-500', 'pulse-danger');
            } else {
                violCard.classList.remove('border-red-500', 'pulse-danger');
            }
        }
    }
    if (elSafetyRate) {
        elSafetyRate.textContent = stats.safety_rate + '%';
        if (elRateBar) {
            elRateBar.style.width = stats.safety_rate + '%';
            if (stats.safety_rate >= 80) {
                elRateBar.className = "h-2 rounded-full bg-emerald-500 transition-all duration-300";
                elSafetyRate.className = "text-2xl font-bold text-emerald-400 font-mono";
            } else if (stats.safety_rate >= 50) {
                elRateBar.className = "h-2 rounded-full bg-amber-500 transition-all duration-300";
                elSafetyRate.className = "text-2xl font-bold text-amber-400 font-mono";
            } else {
                elRateBar.className = "h-2 rounded-full bg-red-500 transition-all duration-300";
                elSafetyRate.className = "text-2xl font-bold text-red-400 font-mono";
            }
        }
    }
    if (elFps) elFps.textContent = stats.fps + ' FPS';

    if (elCamStatus) {
        if (stats.is_camera_active) {
            elCamStatus.innerHTML = '<span class="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span> <span class="text-emerald-400 font-semibold">LIVE SURVEILLANCE</span>';
        } else {
            elCamStatus.innerHTML = '<span class="w-2 h-2 rounded-full bg-slate-500"></span> <span class="text-slate-400">STANDBY</span>';
        }
    }
}

function updateHardwareUI(hw) {
    // 1. LCD Screen Lines
    const line1 = document.getElementById('lcdLine1');
    const line2 = document.getElementById('lcdLine2');
    if (line1) line1.textContent = hw.lcd_line1 || "SITE SAFETY GATE";
    if (line2) line2.textContent = hw.lcd_line2 || "SYSTEM READY";

    // 2. IR Sensor Indicator
    const irBadge = document.getElementById('hwIrBadge');
    if (irBadge) {
        if (hw.ir_triggered) {
            irBadge.className = "px-2.5 py-1 rounded-md text-xs font-bold bg-blue-500/20 text-blue-400 border border-blue-500/40 flex items-center gap-1.5 animate-pulse";
            irBadge.innerHTML = '<i class="fa-solid fa-person-walking"></i> WORKER AT GATE';
        } else {
            irBadge.className = "px-2.5 py-1 rounded-md text-xs font-medium bg-slate-800 text-slate-400 border border-slate-700 flex items-center gap-1.5";
            irBadge.innerHTML = '<i class="fa-solid fa-circle text-[8px]"></i> GATE CLEAR';
        }
    }

    // 3. Ultrasonic Distance Gauge
    const distText = document.getElementById('hwDistText');
    const distBar = document.getElementById('hwDistBar');
    const distHazardAlert = document.getElementById('hwHazardAlert');

    if (distText) distText.textContent = Math.round(hw.distance_cm) + ' cm';
    if (distBar) {
        const pct = Math.min(100, Math.max(5, (hw.distance_cm / 200) * 100));
        distBar.style.width = pct + '%';
        if (hw.proximity_alert) {
            distBar.className = "h-2 rounded-full bg-red-500 transition-all duration-200";
            if (distHazardAlert) distHazardAlert.classList.remove('hidden');
        } else {
            distBar.className = "h-2 rounded-full bg-emerald-500 transition-all duration-200";
            if (distHazardAlert) distHazardAlert.classList.add('hidden');
        }
    }

    // 4. Buzzer Badge
    const buzzerBadge = document.getElementById('hwBuzzerBadge');
    if (buzzerBadge) {
        if (hw.buzzer_active) {
            buzzerBadge.className = "px-2.5 py-1 rounded-md text-xs font-bold bg-red-500/20 text-red-400 border border-red-500/40 flex items-center gap-1.5 animate-bounce";
            buzzerBadge.innerHTML = '<i class="fa-solid fa-volume-high"></i> ALARM SOUNDING';
        } else {
            buzzerBadge.className = "px-2.5 py-1 rounded-md text-xs font-medium bg-slate-800 text-slate-400 border border-slate-700 flex items-center gap-1.5";
            buzzerBadge.innerHTML = '<i class="fa-solid fa-volume-xmark"></i> SILENT';
        }
    }

    // 5. Hardware Mode Badge in Top Header and Panel
    const topText = document.getElementById('topHwText');
    const topDot = document.getElementById('topHwDot');
    const panelMode = document.getElementById('hwPanelMode');

    if (topText) topText.textContent = hw.hardware_mode || "SIMULATION";
    if (topDot) {
        topDot.className = hw.is_connected ? "w-2 h-2 rounded-full bg-emerald-400" : "w-2 h-2 rounded-full bg-amber-400";
    }
    if (panelMode) {
        panelMode.textContent = hw.hardware_mode || "SIMULATION";
        panelMode.className = hw.is_connected ? "text-xs font-mono font-bold text-emerald-400" : "text-xs font-mono font-semibold text-amber-400";
    }
}

function fetchRecentIncidents() {
    fetch('/api/incidents/recent')
        .then(r => r.json())
        .then(incidents => {
            const feed = document.getElementById('incidentFeedContainer');
            if (!feed) return;

            if (incidents.length === 0) {
                feed.innerHTML = `
                    <div class="text-center py-10 text-slate-500 text-sm">
                        <i class="fa-solid fa-shield-halved text-3xl mb-2 text-emerald-500/40"></i>
                        <p>No safety violations recorded.</p>
                        <p class="text-xs text-slate-600 mt-1">All personnel compliant.</p>
                    </div>`;
                return;
            }

            // Check if a brand new incident arrived
            const newest = incidents[0];
            if (newest && newest.id > lastIncidentId && lastIncidentId !== 0) {
                SafetyAudio.playAlarm();
                showToast(`⚠️ Violation: ${newest.worker_label} missing ${newest.missing_ppe}`, 'danger');
            }
            if (newest) lastIncidentId = Math.max(lastIncidentId, newest.id);

            let html = '';
            incidents.forEach(inc => {
                const missingBadges = (inc.missing_ppe || 'Gear')
                    .split(',')
                    .map(item => `<span class="px-1.5 py-0.5 rounded bg-red-500/20 text-red-300 font-mono text-[10px] border border-red-500/30">${item.trim()}</span>`)
                    .join(' ');

                const imgHtml = inc.snapshot_path 
                    ? `<img src="/static/${inc.snapshot_path}" alt="violation" class="w-14 h-14 rounded object-cover border border-slate-700 shrink-0">`
                    : `<div class="w-14 h-14 rounded bg-slate-800 border border-slate-700 flex items-center justify-center text-red-400 shrink-0"><i class="fa-solid fa-person-circle-exclamation text-xl"></i></div>`;

                html += `
                    <div class="p-3 bg-slate-800/80 hover:bg-slate-800 rounded-lg border border-slate-700/80 flex items-start gap-3 transition">
                        ${imgHtml}
                        <div class="flex-1 min-w-0">
                            <div class="flex items-center justify-between gap-1">
                                <span class="font-bold text-xs text-slate-200 truncate">${inc.worker_label}</span>
                                <span class="text-[10px] text-slate-400 font-mono">${inc.timestamp.split(' ')[1]}</span>
                            </div>
                            <div class="text-[11px] text-red-400 font-medium mt-1">Missing:</div>
                            <div class="flex flex-wrap gap-1 mt-0.5">${missingBadges}</div>
                        </div>
                    </div>
                `;
            });
            feed.innerHTML = html;
        })
        .catch(() => {});
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    const color = type === 'danger' ? 'bg-red-600 text-white' : (type === 'success' ? 'bg-emerald-600 text-white' : 'bg-slate-800 text-amber-300 border border-slate-700');
    toast.className = `fixed bottom-5 right-5 z-50 px-4 py-2.5 rounded-lg shadow-xl text-xs font-semibold flex items-center gap-2 transition-all transform duration-300 ${color}`;
    toast.innerHTML = `<i class="fa-solid fa-circle-info"></i> <span>${message}</span>`;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}
