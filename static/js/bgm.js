// bgm.js - Host-Only Background Music Controller for "Bot or Not"
//
// Features:
// 1. Zero audio on boot until Title Screen interaction (Firefox & Chrome compliant).
// 2. Sample-accurate MP3 silence trimming: removes encoder delay (1000-1280 frames) and
//    trailing padding to eliminate the repeat delay/stutter on looping.
// 3. Dynamic Stem Crossfading:
//    - INSTRUCTIONS & SUBMITTING (Answering): Chill stem (50% lower volume)
//    - VOTING: Escalating stem (25% lower volume, synchronized on exact loop beat)
//    - REVEAL: Energy stem (synchronized on exact loop beat)
//    - SCOREBOARD: Empty / silence (reserved for future custom rankings audio)
// 4. Dramatic silence beat: Waits after fading out Main theme before fading in Chill BGM.
// 5. Host device ONLY (no audio on player controllers).
// 6. Balanced mix multipliers: Chill is 50% lower (0.50x) and Escalation is 25% lower (0.75x)
//    regardless of the user's master volume setting.

class BGMManager {
    constructor() {
        this.ctx = null;
        this.masterGain = null;
        this.bgmGain = null;
        this.isStarted = false;

        this.urls = {
            intro: "/static/Intro.mp3",
            loop: "/static/Loop.mp3",
            chill: "/static/Bot%20or%20not%20BGM%20Chill.mp3",
            escalation: "/static/Bot%20or%20not%20BGM%20Escalation.mp3",
            energy: "/static/Bot%20or%20not%20BGM%20Energy.mp3"
        };

        this.rawArrayBuffers = {
            intro: null,
            loop: null,
            chill: null,
            escalation: null,
            energy: null
        };

        this.buffers = {
            intro: null,
            loop: null,
            chill: null,
            escalation: null,
            energy: null
        };

        this.loopDuration = 14.7692; // 8 bars @ 130 BPM 4/4 (240/130 * 8 = 14.769231s)
        this.loopStartTime = 0;

        this.activeTrack = "none";    // "main", "chill", "escalation", "energy", "silent"
        this.targetTrack = "main";
        this.activeNodes = [];        // active { source, gain, track }
        this.activeFadeTimeout = null;
        this.chillDelayTimeout = null;

        // Relative mix adjustments:
        // Chill is 50% lower (-50% -> 0.50x), Escalation is 25% lower (-25% -> 0.75x)
        this.trackMultipliers = {
            main: 1.0,
            energy: 0.5,
            chill: 0.5,
            escalation: 0.5
        };

        const savedVol = localStorage.getItem("bot_bgm_volume");
        this.volume = savedVol !== null ? Math.max(0.05, Math.min(1.0, parseFloat(savedVol))) : 0.7;
        this.isMuted = localStorage.getItem("bot_bgm_muted") === "true";

        this.currentPhase = "LOBBY";

        // 130 BPM Beat Tracking & Host Screen Border Pulse Sync
        this.bpm = 130;
        this.beatDuration = 60 / 130; // 0.46153846s @ 130 BPM
        this.beatZeroTime = 0;
        this.isBeatActive = false;

        if (typeof document !== "undefined") {
            document.documentElement.style.setProperty("--host-beat-duration", `${(60 / 130).toFixed(6)}s`);
            document.documentElement.style.setProperty("--host-beat-duration-double", `${(120 / 130).toFixed(6)}s`);
        }

        // Pre-fetch raw array buffers via standard HTTP (network only, 0 audio API calls)
        this.prefetchAudioData();
    }

    async prefetchAudioData() {
        const fetchBuffer = async (url) => {
            try {
                const res = await fetch(url);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return await res.arrayBuffer();
            } catch (err) {
                console.warn(`[BGMManager] Failed to fetch ${url}:`, err);
                return null;
            }
        };

        const entries = Object.entries(this.urls);
        await Promise.all(entries.map(async ([key, url]) => {
            this.rawArrayBuffers[key] = await fetchBuffer(url);
        }));

        if (this.isStarted && this.ctx) {
            await this.decodeAllBuffers();
            this.triggerTargetTrack();
        }
    }

    startFromUserGesture() {
        if (this.isStarted && this.ctx && this.ctx.state !== "suspended") {
            return;
        }

        try {
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            if (!this.ctx && AudioCtx) {
                this.ctx = new AudioCtx();
                this.masterGain = this.ctx.createGain();
                this.bgmGain = this.ctx.createGain();

                this.bgmGain.connect(this.masterGain);
                this.masterGain.connect(this.ctx.destination);
                this.applyGainVolume(0.001);
            }

            if (this.ctx && this.ctx.state === "suspended") {
                this.ctx.resume();
            }

            this.isStarted = true;
            this.updateUi();

            // Decode all buffers and trigger active phase
            this.decodeAllBuffers().then(() => {
                this.triggerTargetTrack();
            });
        } catch (e) {
            console.warn("[BGMManager] Failed to start audio from user gesture:", e);
        }
    }

    triggerTargetTrack() {
        if (!this.isStarted || !this.ctx) return;
        if (this.targetTrack === "main") {
            this.playMain();
        } else if (["chill", "escalation", "energy"].includes(this.targetTrack)) {
            this.playStem(this.targetTrack);
        } else if (this.targetTrack === "silent") {
            this.stopBGM(0.3);
        } else {
            this.onPhaseChange(this.currentPhase || "LOBBY");
        }
    }

    /**
     * Exact 130 BPM (4/4 time) Sample-Accurate Buffer Slicing & Boundary Alignment
     *
     * Musical timing:
     * - Tempo: 130 BPM
     * - 1 Beat = 60 / 130 = 0.461538... sec
     * - 1 Bar  = 240 / 130 = 1.846154... sec
     *
     * Track specifications:
     * - Intro: 10 bars = 40 beats = 18.461538s (814,154 samples @ 44.1kHz, 886,154 @ 48kHz)
     * - Loop:  40 bars = 160 beats = 73.846154s (3,256,615 samples @ 44.1kHz, 3,544,615 @ 48kHz)
     * - Stems (Chill, Escalation, Energy):
     *          8 bars = 32 beats = 14.769231s (651,323 samples @ 44.1kHz, 708,923 @ 48kHz)
     *
     * Detects the first downbeat transient (stripping the ~29ms MP3 encoder priming delay),
     * slices exactly to the musical bar boundary, and applies a smooth Hann boundary taper
     * to the tail of looping tracks matching dst[0] to eliminate loop wraparound clicks
     * without dampening the downbeat attack transient.
     */
    processTrackBuffer(key, buffer) {
        if (!this.ctx || !buffer) return buffer;

        const specs = {
            intro:      { bars: 10, isLoop: false },
            loop:       { bars: 40, isLoop: true  },
            chill:      { bars: 8,  isLoop: true  },
            escalation: { bars: 8,  isLoop: true  },
            energy:     { bars: 8,  isLoop: true  }
        };

        const spec = specs[key];
        if (!spec) return buffer;

        const sr = buffer.sampleRate;
        const bpm = 130;
        const samplesPerBar = sr * (240 / bpm);
        const targetLen = Math.round(spec.bars * samplesPerBar);
        const numChannels = buffer.numberOfChannels;
        const rawLen = buffer.length;

        // Detect first downbeat transient after MP3 encoder delay (~26-30ms)
        let start = 0;
        const searchLimit = Math.min(4000, rawLen);
        for (let i = 0; i < searchLimit; i++) {
            let hasSignal = false;
            for (let ch = 0; ch < numChannels; ch++) {
                if (Math.abs(buffer.getChannelData(ch)[i]) > 0.012) {
                    hasSignal = true;
                    break;
                }
            }
            if (hasSignal) {
                start = i;
                break;
            }
        }

        // Secondary fallback if attack is softer
        if (start === 0) {
            for (let i = 0; i < searchLimit; i++) {
                let hasSignal = false;
                for (let ch = 0; ch < numChannels; ch++) {
                    if (Math.abs(buffer.getChannelData(ch)[i]) > 0.003) {
                        hasSignal = true;
                        break;
                    }
                }
                if (hasSignal) {
                    start = i;
                    break;
                }
            }
        }

        if (start + targetLen > rawLen) {
            start = Math.max(0, rawLen - targetLen);
        }

        const clean = this.ctx.createBuffer(numChannels, targetLen, sr);
        for (let ch = 0; ch < numChannels; ch++) {
            const src = buffer.getChannelData(ch);
            const dst = clean.getChannelData(ch);
            dst.set(src.subarray(start, start + targetLen));

            // If track loops, smoothly blend the last 128 samples (~2.9ms) to connect seamlessly to dst[0]
            // This eliminates loop turnaround clicks without altering the attack transient of dst[0].
            if (spec.isLoop && targetLen > 256) {
                const K = 128;
                const delta = dst[0] - dst[targetLen - 1];
                for (let i = 0; i < K; i++) {
                    const factor = 0.5 * (1 - Math.cos(Math.PI * (i + 1) / K));
                    dst[targetLen - K + i] += delta * factor;
                }
            }
        }

        return clean;
    }

    equalizeStemBuffers() {
        if (!this.buffers.chill || !this.buffers.escalation || !this.buffers.energy) return;

        // Equalize all 3 stems to the minimum sample count so they are 100% sample-identical in duration
        const targetLen = Math.min(
            this.buffers.chill.length,
            this.buffers.escalation.length,
            this.buffers.energy.length
        );
        this.loopDuration = targetLen / this.ctx.sampleRate;

        const trimToLength = (buf) => {
            if (buf.length === targetLen) return buf;
            const res = this.ctx.createBuffer(buf.numberOfChannels, targetLen, buf.sampleRate);
            for (let ch = 0; ch < buf.numberOfChannels; ch++) {
                res.getChannelData(ch).set(buf.getChannelData(ch).subarray(0, targetLen));
            }
            return res;
        };

        this.buffers.chill = trimToLength(this.buffers.chill);
        this.buffers.escalation = trimToLength(this.buffers.escalation);
        this.buffers.energy = trimToLength(this.buffers.energy);
    }

    async decodeAllBuffers() {
        if (!this.ctx) return;

        const decode = async (key) => {
            if (this.buffers[key]) return this.buffers[key];
            const raw = this.rawArrayBuffers[key];
            let rawBuf = null;

            if (!raw) {
                try {
                    const res = await fetch(this.urls[key]);
                    const ab = await res.arrayBuffer();
                    rawBuf = await this.ctx.decodeAudioData(ab);
                } catch (err) {
                    console.warn(`[BGMManager] Error fetching/decoding ${key}:`, err);
                    return null;
                }
            } else {
                try {
                    const slice = raw.slice(0);
                    rawBuf = await this.ctx.decodeAudioData(slice);
                } catch (err) {
                    console.warn(`[BGMManager] Error decoding buffer for ${key}:`, err);
                    return null;
                }
            }

            if (rawBuf) {
                // Musical 130 BPM grid alignment and seamless boundary preparation
                this.buffers[key] = this.processTrackBuffer(key, rawBuf);
            }
            return this.buffers[key];
        };

        await Promise.all(Object.keys(this.urls).map(decode));
        this.equalizeStemBuffers();
    }

    getTrackMultiplier(trackName) {
        if (!trackName) return 1.0;
        const key = String(trackName).toLowerCase();
        if (Object.prototype.hasOwnProperty.call(this.trackMultipliers, key)) {
            return this.trackMultipliers[key];
        }
        return 1.0;
    }

    applyGainVolume(rampTime = 0.2) {
        const effVol = this.isMuted ? 0 : this.volume;
        if (this.ctx && this.masterGain) {
            const now = this.ctx.currentTime;
            this.masterGain.gain.cancelScheduledValues(now);
            this.masterGain.gain.setValueAtTime(this.masterGain.gain.value, now);
            this.masterGain.gain.linearRampToValueAtTime(effVol, now + rampTime);
        }
        this.updateBeatPulseState();
    }

    stopActiveNodes(fadeDuration = 0.35) {
        if (this.activeFadeTimeout) {
            clearTimeout(this.activeFadeTimeout);
            this.activeFadeTimeout = null;
        }

        if (this.activeNodes.length === 0) {
            this.updateBeatPulseState();
            return;
        }

        const nodesToStop = [...this.activeNodes];
        this.activeNodes = [];

        if (this.ctx) {
            const now = this.ctx.currentTime;
            nodesToStop.forEach(({ gain }) => {
                if (gain) {
                    try {
                        gain.gain.cancelScheduledValues(now);
                        gain.gain.setValueAtTime(gain.gain.value, now);
                        gain.gain.linearRampToValueAtTime(0.0001, now + fadeDuration);
                    } catch (e) {}
                }
            });
        }

        this.updateBeatPulseState();

        this.activeFadeTimeout = setTimeout(() => {
            nodesToStop.forEach(({ source, gain }) => {
                try {
                    if (source) {
                        source.stop();
                        source.disconnect();
                    }
                    if (gain) gain.disconnect();
                } catch (e) {}
            });
            this.updateBeatPulseState();
        }, Math.max(50, (fadeDuration * 1000) + 40));
    }

    playMain() {
        this.targetTrack = "main";
        if (!this.isStarted || !this.ctx) return;

        // Cancel any pending chill delay
        if (this.chillDelayTimeout) {
            clearTimeout(this.chillDelayTimeout);
            this.chillDelayTimeout = null;
        }

        if (this.activeTrack === "main") {
            return;
        }

        this.stopActiveNodes(0.35);
        this.activeTrack = "main";

        if (this.ctx.state === "suspended") {
            this.ctx.resume();
        }

        if (this.buffers.intro && this.buffers.loop) {
            try {
                const now = this.ctx.currentTime + 0.05;
                this.beatZeroTime = now;

                const introNode = this.ctx.createBufferSource();
                introNode.buffer = this.buffers.intro;

                const loopNode = this.ctx.createBufferSource();
                loopNode.buffer = this.buffers.loop;
                loopNode.loop = true;

                const targetGain = this.getTrackMultiplier("main");
                const trackGain = this.ctx.createGain();
                trackGain.gain.setValueAtTime(0.001, now);
                trackGain.gain.linearRampToValueAtTime(targetGain, now + 0.4);

                introNode.connect(trackGain);
                loopNode.connect(trackGain);
                trackGain.connect(this.bgmGain);

                introNode.start(now);
                // Sample-accurate scheduled transition from 10-bar Intro to 40-bar Loop
                loopNode.start(now + this.buffers.intro.duration);

                introNode.onended = () => {
                    try { introNode.disconnect(); } catch (e) {}
                };

                this.activeNodes.push({ source: introNode, gain: trackGain, track: "main" }, { source: loopNode, gain: trackGain, track: "main" });
                this.updateBeatPulseState();
            } catch (err) {
                console.warn("[BGMManager] Error playing main track:", err);
            }
        } else if (this.buffers.loop) {
            try {
                const now = this.ctx.currentTime + 0.05;
                this.beatZeroTime = now;

                const loopNode = this.ctx.createBufferSource();
                loopNode.buffer = this.buffers.loop;
                loopNode.loop = true;

                const targetGain = this.getTrackMultiplier("main");
                const trackGain = this.ctx.createGain();
                trackGain.gain.setValueAtTime(0.001, now);
                trackGain.gain.linearRampToValueAtTime(targetGain, now + 0.4);

                loopNode.connect(trackGain);
                trackGain.connect(this.bgmGain);

                loopNode.start(now);
                this.activeNodes.push({ source: loopNode, gain: trackGain, track: "main" });
                this.updateBeatPulseState();
            } catch (err) {
                console.warn("[BGMManager] Error playing loop-only main track:", err);
            }
        }
    }

    playStem(stemName) {
        this.targetTrack = stemName;
        if (!this.isStarted || !this.ctx) return;

        // Cancel any pending chill delay
        if (this.chillDelayTimeout) {
            clearTimeout(this.chillDelayTimeout);
            this.chillDelayTimeout = null;
        }

        if (this.activeTrack === stemName) {
            return;
        }

        if (this.ctx.state === "suspended") {
            this.ctx.resume();
        }

        const buffer = this.buffers[stemName];
        if (!buffer) return;

        const isTransitionBetweenStems = ["chill", "escalation", "energy"].includes(this.activeTrack);

        let offset = 0;
        const now = this.ctx.currentTime + 0.04;

        if (isTransitionBetweenStems && this.loopStartTime > 0) {
            const elapsed = now - this.loopStartTime;
            offset = ((elapsed % this.loopDuration) + this.loopDuration) % this.loopDuration;
            offset = Math.max(0, Math.min(buffer.duration - 0.02, offset));
            this.beatZeroTime = now - offset;
        } else {
            this.loopStartTime = now;
            offset = 0;
            this.beatZeroTime = now;
        }

        this.stopActiveNodes(0.35);
        this.activeTrack = stemName;

        try {
            const stemNode = this.ctx.createBufferSource();
            stemNode.buffer = buffer;
            stemNode.loop = true;

            const targetGain = this.getTrackMultiplier(stemName);
            const stemGain = this.ctx.createGain();
            stemGain.gain.setValueAtTime(0.001, now);
            stemGain.gain.linearRampToValueAtTime(targetGain, now + 0.35);

            stemNode.connect(stemGain);
            stemGain.connect(this.bgmGain);

            stemNode.start(now, offset);
            this.activeNodes.push({ source: stemNode, gain: stemGain, track: stemName });
            this.updateBeatPulseState();
        } catch (err) {
            console.warn(`[BGMManager] Error playing stem ${stemName}:`, err);
        }
    }

    stopBGM(fadeDuration = 0.4) {
        this.targetTrack = "silent";
        if (this.chillDelayTimeout) {
            clearTimeout(this.chillDelayTimeout);
            this.chillDelayTimeout = null;
        }

        if (this.activeTrack === "silent" && this.activeNodes.length === 0) {
            this.updateBeatPulseState();
            return;
        }
        this.activeTrack = "silent";
        this.stopActiveNodes(fadeDuration);
        this.updateBeatPulseState();
    }

    /**
     * Dynamic Phase Transitions:
     * - LOBBY, INTRO: Main Theme (Intro -> Loop)
     * - INSTRUCTIONS: Fades out Main theme, WAITS ~1.3s for breathing room, then fades in Chill BGM
     * - SUBMITTING (Answering section): Keep Chill playing and looping
     * - VOTING: Escalating stem (synchronized on exact loop beat)
     * - REVEAL: Energy stem (synchronized on exact loop beat)
     * - SCOREBOARD: Empty / silence (reserved for future custom rankings audio)
     */
    onPhaseChange(phase) {
        if (!phase) return;
        this.currentPhase = phase;
        if (!this.isStarted) return; // Wait until host clicks start on Title Screen

        const normalized = phase.toUpperCase();

        switch (normalized) {
            case "LOBBY":
            case "INTRO":
                if (this.chillDelayTimeout) {
                    clearTimeout(this.chillDelayTimeout);
                    this.chillDelayTimeout = null;
                }
                this.playMain();
                break;

            case "INSTRUCTIONS":
                // If coming from Main theme (Intro briefing or lobby), fade out Main,
                // WAIT a moment (1.3s), then fade in Chill BGM
                if (this.activeTrack === "main") {
                    this.stopBGM(0.45);
                    this.targetTrack = "chill";
                    if (this.chillDelayTimeout) clearTimeout(this.chillDelayTimeout);
                    this.chillDelayTimeout = setTimeout(() => {
                        this.chillDelayTimeout = null;
                        if (["INSTRUCTIONS", "SUBMITTING"].includes(this.currentPhase)) {
                            this.playStem("chill");
                        }
                    }, 2000); // 450ms fade + 1550ms silence pause
                } else if (this.activeTrack === "silent") {
                    // Coming from scoreboard: brief breathing beat then chill
                    this.targetTrack = "chill";
                    if (this.chillDelayTimeout) clearTimeout(this.chillDelayTimeout);
                    this.chillDelayTimeout = setTimeout(() => {
                        this.chillDelayTimeout = null;
                        if (["INSTRUCTIONS", "SUBMITTING"].includes(this.currentPhase)) {
                            this.playStem("chill");
                        }
                    }, 800);
                } else {
                    this.playStem("chill");
                }
                break;

            case "SUBMITTING":
                // Keep the Chill track for the answering section
                if (this.chillDelayTimeout) {
                    // If instruction delay was still ticking, start chill now
                    clearTimeout(this.chillDelayTimeout);
                    this.chillDelayTimeout = null;
                }
                this.playStem("chill");
                break;

            case "VOTING":
                // Use Escalating for voting (synchronized transition)
                if (this.chillDelayTimeout) {
                    clearTimeout(this.chillDelayTimeout);
                    this.chillDelayTimeout = null;
                }
                this.playStem("escalation");
                break;

            case "REVEAL":
                // Use Energy for the reveal (synchronized transition)
                if (this.chillDelayTimeout) {
                    clearTimeout(this.chillDelayTimeout);
                    this.chillDelayTimeout = null;
                }
                this.playStem("energy");
                break;

            case "BONUS":
                // Final bonus dossier answering section: keep chill
                this.playStem("chill");
                break;

            case "SCOREBOARD":
            case "BONUS_REVEAL":
            case "GAME_OVER":
            default:
                // Keep empty / silent for rankings screen (custom audio coming later)
                this.stopBGM(0.4);
                break;
        }
    }

    cycleVolume() {
        if (!this.isStarted) {
            this.startFromUserGesture();
            return;
        }

        if (this.isMuted) {
            this.isMuted = false;
            this.volume = 0.7;
        } else if (this.volume >= 0.9) {
            this.volume = 0.4;
        } else if (this.volume >= 0.4) {
            this.volume = 0.15;
        } else if (this.volume > 0.05) {
            this.isMuted = true;
        } else {
            this.isMuted = false;
            this.volume = 0.7;
        }

        localStorage.setItem("bot_bgm_volume", this.volume.toFixed(2));
        localStorage.setItem("bot_bgm_muted", this.isMuted ? "true" : "false");

        this.applyGainVolume(0.15);
        this.updateUi();
        this.updateBeatPulseState();
    }

    setVolume(vol) {
        if (!this.isStarted) {
            this.startFromUserGesture();
        }
        const val = parseFloat(vol);
        if (isNaN(val) || val <= 0.001) {
            this.isMuted = true;
        } else {
            this.isMuted = false;
            this.volume = Math.max(0.05, Math.min(1.0, val));
        }
        localStorage.setItem("bot_bgm_volume", this.volume.toFixed(2));
        localStorage.setItem("bot_bgm_muted", this.isMuted ? "true" : "false");

        this.applyGainVolume(0.15);
        this.updateUi();
        this.updateBeatPulseState();
    }

    updateUi() {
        const iconEl = document.getElementById("bgm-icon");
        const labelEl = document.getElementById("bgm-label");
        const btn = document.getElementById("btn-audio-toggle");

        const pct = Math.round(this.volume * 100);

        if (!this.isStarted) {
            if (iconEl) iconEl.innerHTML = window.Icons ? window.Icons.volumeMute : "";
            if (labelEl) labelEl.innerText = "AUDIO STANDBY";
            if (btn) btn.classList.add("btn-muted");
            return;
        }

        if (this.isMuted || pct === 0) {
            if (iconEl) iconEl.innerHTML = window.Icons ? window.Icons.volumeMute : "";
            if (labelEl) labelEl.innerText = "BGM: MUTED";
            if (btn) btn.classList.add("btn-muted");
        } else {
            let iconSvg = "";
            if (window.Icons) {
                iconSvg = pct > 60 ? window.Icons.volumeHigh : (pct > 25 ? window.Icons.volumeMedium : window.Icons.volumeLow);
            }
            if (iconEl) iconEl.innerHTML = iconSvg;
            if (labelEl) labelEl.innerText = `BGM: ${pct}%`;
            if (btn) btn.classList.remove("btn-muted");
        }
    }

    /**
     * Beat Synchronization & Pulse Phase Alignment (Host Screen Only)
     * Calculates the sample-accurate position within the 130 BPM quarter-note beat grid
     * and sets --host-beat-delay on the document root so CSS border pulse animations
     * are synchronized on the downbeat of the audio.
     */
    syncBeatPhase() {
        if (!this.ctx || !this.beatZeroTime) return;

        const now = this.ctx.currentTime;
        const elapsed = now - this.beatZeroTime;
        if (elapsed < 0) {
            // Audio starts scheduled slightly in the future (e.g. +0.04s)
            const ms = Math.max(10, Math.round(-elapsed * 1000));
            setTimeout(() => {
                if (this.isBeatActive) this.syncBeatPhase();
            }, ms);
            return;
        }

        const beatLen = 60 / this.bpm; // 0.46153846s @ 130 BPM
        const offset = ((elapsed % beatLen) + beatLen) % beatLen;
        const targetDelay = -offset;

        document.documentElement.style.setProperty("--host-beat-delay", `${targetDelay.toFixed(4)}s`);
    }

    /**
     * Toggles the subtle rhythmic border pulse on host screen according to whether
     * tracks are actively playing and audible.
     */
    updateBeatPulseState() {
        if (typeof document === "undefined") return;

        // Ensure this effect is strictly host-screen only
        const isHost = document.body && (
            document.body.classList.contains("host-screen") ||
            document.querySelector(".host-container") ||
            document.getElementById("host-title-screen")
        );
        if (!isHost) return;

        // Guarantee host-screen class is present on host body
        if (document.body && !document.body.classList.contains("host-screen")) {
            document.body.classList.add("host-screen");
        }

        const isPlaying = this.isStarted &&
                          this.ctx &&
                          this.ctx.state === "running" &&
                          !this.isMuted &&
                          this.volume > 0.01 &&
                          ["main", "chill", "escalation", "energy"].includes(this.activeTrack) &&
                          this.activeNodes.length > 0;

        if (isPlaying) {
            if (!this.isBeatActive) {
                this.isBeatActive = true;
                this.syncBeatPhase();
                document.body.classList.add("host-beat-active");
            } else {
                // If already active and transitioning tracks, update delay once
                this.syncBeatPhase();
            }
        } else {
            if (this.isBeatActive) {
                this.isBeatActive = false;
                document.body.classList.remove("host-beat-active");
            }
        }
    }

    getAudioContext() {
        return this.ctx;
    }
}

// Global instance for host screen
window.bgmManager = new BGMManager();
