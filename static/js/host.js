// host.js - Host screen controller and state rendering

let currentState = null;
let pollTimer = null;
let countdownInterval = null;
let countdownSeconds = 0;
let lastRenderedPhase = null;

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
    pollHostState();
    pollTimer = setInterval(pollHostState, 1000);
});

async function pollHostState() {
    try {
        const res = await fetch("/api/host_state");
        if (res.ok) {
            const data = await res.json();
            currentState = data;
            renderHostView(data);
        }
    } catch (err) {
        console.error("Failed to poll host state:", err);
    }
}

function renderHostView(state) {
    const phases = [
        "lobby", "instructions", "submitting", "voting", 
        "reveal", "scoreboard", "bonus", "bonus-reveal", "game-over"
    ];

    const currentPhaseKey = state.phase.toLowerCase().replace("_", "-");

    // Show only active phase section
    phases.forEach(p => {
        const el = document.getElementById(`phase-${p}`);
        if (el) {
            el.style.display = (p === currentPhaseKey) ? "block" : "none";
        }
    });

    // Detect phase change for timers
    const isNewPhase = (lastRenderedPhase !== state.phase);
    lastRenderedPhase = state.phase;

    switch (state.phase) {
        case "LOBBY":
            renderLobby(state);
            break;
        case "INSTRUCTIONS":
            renderInstructions(state, isNewPhase);
            break;
        case "SUBMITTING":
            renderSubmitting(state, isNewPhase);
            break;
        case "VOTING":
            renderVoting(state, isNewPhase);
            break;
        case "REVEAL":
            renderReveal(state, isNewPhase);
            break;
        case "SCOREBOARD":
            renderScoreboard(state, isNewPhase);
            break;
        case "BONUS":
            renderBonus(state);
            break;
        case "BONUS_REVEAL":
            renderBonusReveal(state, isNewPhase);
            break;
        case "GAME_OVER":
            renderGameOver(state);
            break;
    }
}

let isStartingGame = false;

// --- Phase 1: Lobby ---
function renderLobby(state) {
    clearInterval(countdownInterval);

    // Re-enable start game button if returning to lobby
    isStartingGame = false;
    const startBtn = document.getElementById("btn-start-game");
    if (startBtn) {
        startBtn.disabled = false;
        startBtn.innerHTML = "🚀 START GAME";
        startBtn.style.opacity = "1";
        startBtn.style.cursor = "pointer";
    }

    // Player count and list
    document.getElementById("player-count").innerText = state.player_count;
    const playerContainer = document.getElementById("lobby-players-list");
    
    if (state.players.length === 0) {
        playerContainer.innerHTML = '<p style="color: #9ca3af;" id="no-players-text">Waiting for players to scan QR code and join...</p>';
    } else {
        playerContainer.innerHTML = state.players.map(p => `
            <div class="player-badge ready">
                <span>👤</span>
                <span>${escapeHtml(p.name)}</span>
            </div>
        `).join("");
    }

    // Minigame playlist configuration checkboxes
    const playlistContainer = document.getElementById("playlist-container");
    if (playlistContainer.children.length === 0 && state.available_games) {
        const currentKeys = state.game_sequence.map(g => g.key);
        playlistContainer.innerHTML = state.available_games.map(g => `
            <div class="playlist-item">
                <label style="display: flex; align-items: center; gap: 10px; cursor: pointer; width: 100%;">
                    <input type="checkbox" value="${g.key}" ${currentKeys.includes(g.key) ? "checked" : ""} onchange="updateCustomSequence()" style="width: 20px; height: 20px; accent-color: #3b82f6;">
                    <div>
                        <strong>${escapeHtml(g.name)}</strong>
                        <div style="font-size: 0.85rem; color: #9ca3af;">${escapeHtml(g.description)}</div>
                    </div>
                </label>
            </div>
        `).join("");
    }
}

async function updateCustomSequence() {
    const checked = Array.from(document.querySelectorAll("#playlist-container input[type='checkbox']:checked"))
        .map(cb => cb.value);
    
    if (checked.length === 0) {
        alert("You must select at least one minigame!");
        return;
    }

    await fetch("/api/set_sequence", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sequence: checked })
    });
}

async function startGame() {
    if (isStartingGame) return;

    const btn = document.getElementById("btn-start-game");
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = "⏳ STARTING GAME...";
        btn.style.opacity = "0.7";
        btn.style.cursor = "not-allowed";
    }
    isStartingGame = true;

    try {
        const checked = Array.from(document.querySelectorAll("#playlist-container input[type='checkbox']:checked"))
            .map(cb => cb.value);

        const res = await fetch("/api/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sequence: checked.length > 0 ? checked : null })
        });
        const data = await res.json();
        if (data && data.state) {
            currentState = data.state;
            renderHostView(data.state);
        }
    } catch (err) {
        console.error("Failed to start game:", err);
    } finally {
        isStartingGame = false;
        if (btn && currentState && currentState.phase === "LOBBY") {
            btn.disabled = false;
            btn.innerHTML = "🚀 START GAME";
            btn.style.opacity = "1";
            btn.style.cursor = "pointer";
        }
    }
}

// --- Phase 2: Instructions ---
function renderInstructions(state, isNewPhase) {
    document.getElementById("instructions-round-tag").innerText = `Round ${state.round_number} of ${state.total_rounds}`;
    if (state.game_info) {
        document.getElementById("instructions-game-title").innerText = state.game_info.title;
        document.getElementById("instructions-text").innerText = state.game_info.instruction;
    }

    if (isNewPhase) {
        startCountdown(8, "instructions-timer", advancePhase);
    }
}

// --- Phase 3: Submitting ---
function renderSubmitting(state, isNewPhase) {
    document.getElementById("submitting-round-tag").innerText = `Round ${state.round_number} of ${state.total_rounds}`;
    if (state.game_info) {
        document.getElementById("submitting-game-title").innerText = state.game_info.title;
        const promptData = state.game_info.prompt_data;
        document.getElementById("submitting-prompt-text").innerText = promptData.prompt_text || "";

        // Check if image captcha
        const captchaBox = document.getElementById("submitting-captcha-box");
        const captchaImg = document.getElementById("submitting-captcha-img");
        if (promptData.type === "image_caption" && promptData.image_url) {
            captchaBox.style.display = "block";
            captchaImg.src = promptData.image_url;
        } else {
            captchaBox.style.display = "none";
        }
    }

    if (isNewPhase) {
        startCountdown(state.submission_timeout || 25, "submitting-timer", advancePhase);
    }

    // Submissions progress badges
    const list = document.getElementById("submitting-players-list");
    if (state.submissions_status) {
        list.innerHTML = state.submissions_status.map(p => `
            <div class="player-badge ${p.has_submitted ? 'ready' : 'pending'}">
                <span>${p.has_submitted ? '✅' : '✍️'}</span>
                <span>${escapeHtml(p.name)}</span>
                <span style="font-size: 0.85rem; color: #9ca3af;">${p.has_submitted ? 'Submitted' : 'Typing...'}</span>
            </div>
        `).join("");
    }
}

// --- Phase 4: Voting ---
function renderVoting(state, isNewPhase) {
    if (state.game_info) {
        document.getElementById("voting-game-title").innerText = state.game_info.title;
    }

    const maxVotes = state.max_votes_per_player || 1;
    const headerTitle = document.getElementById("voting-header-title");
    const headerSubtitle = document.getElementById("voting-header-subtitle");
    if (maxVotes >= 2) {
        if (headerTitle) headerTitle.innerText = "Which 2 Responses are BOTs?";
        if (headerSubtitle) headerSubtitle.innerText = "Lobby size 5+: Pick the 2 BOT responses on your phone!";
    } else {
        if (headerTitle) headerTitle.innerText = "Which Response is the BOT?";
        if (headerSubtitle) headerSubtitle.innerText = "Vote on your phone now!";
    }

    if (isNewPhase) {
        startCountdown(state.voting_timeout || 25, "voting-timer", advancePhase);
    }

    // Render anonymized responses grid
    const optionsGrid = document.getElementById("voting-options-grid");
    if (state.voting_options) {
        optionsGrid.innerHTML = state.voting_options.map((opt, i) => {
            const letter = String.fromCharCode(65 + i);
            const content = Array.isArray(opt.response) 
                ? `<ol style="margin-left: 20px;">${opt.response.map(r => `<li>${escapeHtml(r)}</li>`).join("")}</ol>`
                : `"${escapeHtml(opt.response)}"`;

            return `
                <div class="option-card">
                    <div style="font-weight: 800; color: #60a5fa; margin-bottom: 8px;">Response ${letter}</div>
                    <div style="font-size: 1.15rem;">${content}</div>
                </div>
            `;
        }).join("");
    }

    // Render voting status badges
    const statusList = document.getElementById("voting-players-list");
    if (state.voting_status) {
        statusList.innerHTML = state.voting_status.map(p => `
            <div class="player-badge ${p.has_voted ? 'ready' : 'pending'}">
                <span>${p.has_voted ? '🗳️' : '⏳'}</span>
                <span>${escapeHtml(p.name)}</span>
                <span style="font-size: 0.85rem; color: #9ca3af;">${p.has_voted ? 'Voted' : 'Deciding...'}</span>
            </div>
        `).join("");
    }
}

// --- Phase 5: Reveal ---
function renderReveal(state, isNewPhase) {
    const container = document.getElementById("reveal-cards-container");
    if (state.reveal_data && state.reveal_data.reveal_cards) {
        container.innerHTML = state.reveal_data.reveal_cards.map(card => {
            const isBot = card.is_bot;
            const content = Array.isArray(card.response) 
                ? `<ol style="margin-left: 20px;">${card.response.map(r => `<li>${escapeHtml(r)}</li>`).join("")}</ol>`
                : `"${escapeHtml(card.response)}"`;

            const votersText = card.voter_names.length > 0 
                ? `Voted as Bot by: <strong>${card.voter_names.join(", ")}</strong>` 
                : "No votes received.";

            const pointsNotice = isBot 
                ? `<div style="color: #6ee7b7; font-weight: 600; margin-top: 6px;">🎯 Identified as BOT! (+100 pts to voters)</div>`
                : (card.vote_count > 0 
                    ? `<div style="color: #f87171; font-weight: 600; margin-top: 6px;">⚠️ Fooled fellow humans! (-25 pts penalty per vote to author for failing to blend in)</div>` 
                    : `<div style="color: #9ca3af; margin-top: 6px;">Nobody voted for this as a bot. Clean blend-in!</div>`);

            return `
                <div class="reveal-card ${isBot ? 'bot' : 'human'}">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span class="tag ${isBot ? 'tag-bot' : 'tag-human'}">
                            ${isBot ? '🤖 BOT' : '👤 HUMAN PLAYER'}
                        </span>
                        <span style="font-size: 0.95rem; color: #9ca3af;">${card.vote_count} vote(s)</span>
                    </div>
                    <div style="font-size: 1.25rem; margin: 10px 0;">${content}</div>
                    <div style="font-size: 1rem; color: #d1d5db; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 8px; margin-top: 8px;">
                        ${votersText}
                        ${pointsNotice}
                    </div>
                </div>
            `;
        }).join("");
    }

    if (isNewPhase) {
        startCountdown(10, "reveal-timer", advancePhase);
    }
}

// --- Phase 6: Scoreboard (Classified / Redacted) ---
function renderScoreboard(state, isNewPhase) {
    const tbody = document.getElementById("scoreboard-body");
    tbody.innerHTML = state.players.map((p, i) => `
        <tr>
            <td style="font-weight: 700; color: #9ca3af;">🔒 Classified</td>
            <td style="font-weight: 700;">${escapeHtml(p.name)}</td>
            <td><span class="classified-score">${escapeHtml(p.score_display || '█████ [CLASSIFIED]')}</span></td>
        </tr>
    `).join("");

    if (isNewPhase) {
        startCountdown(8, "scoreboard-timer", advancePhase);
    }
}

// --- Phase 7: Bonus Round ---
function renderBonus(state) {
    clearInterval(countdownInterval);

    // Render preview of dossiers
    const previewContainer = document.getElementById("bonus-dossiers-preview");
    if (state.dossiers) {
        previewContainer.innerHTML = state.dossiers.map(d => `
            <div class="dossier-card">
                <div style="font-weight: 800; color: #fbbf24; margin-bottom: 8px;">📁 ${escapeHtml(d.label)}</div>
                ${d.items.map(item => `
                    <div class="dossier-response-item">
                        <div style="font-size: 0.8rem; color: #9ca3af;">${escapeHtml(item.game_title)}:</div>
                        <div style="font-style: italic;">${Array.isArray(item.response) ? item.response.join(", ") : escapeHtml(item.response)}</div>
                    </div>
                `).join("")}
            </div>
        `).join("");
    }

    // Render guessing progress
    const list = document.getElementById("bonus-players-list");
    if (state.bonus_status) {
        list.innerHTML = state.bonus_status.map(p => `
            <div class="player-badge ${p.has_guessed ? 'ready' : 'pending'}">
                <span>${p.has_guessed ? '✅' : '🕵️'}</span>
                <span>${escapeHtml(p.name)}</span>
                <span style="font-size: 0.85rem; color: #9ca3af;">${p.has_guessed ? 'Matches Locked' : 'Matching...'}</span>
            </div>
        `).join("");
    }
}

// --- Phase 8: Bonus Reveal ---
function renderBonusReveal(state, isNewPhase) {
    const container = document.getElementById("bonus-reveal-container");
    if (state.reveal_data && state.reveal_data.reveal_dossiers) {
        container.innerHTML = state.reveal_data.reveal_dossiers.map(d => {
            const correctVoters = d.correct_voter_names.length > 0
                ? `<div style="color: #6ee7b7; margin-top: 6px;">Correctly identified by: <strong>${d.correct_voter_names.join(", ")}</strong> (+150 pts each!)</div>`
                : `<div style="color: #9ca3af; margin-top: 6px;">Nobody guessed this identity correctly!</div>`;

            return `
                <div class="reveal-card human" style="margin-bottom: 20px;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-size: 1.3rem; font-weight: 800; color: #fbbf24;">📁 ${escapeHtml(d.label)}</span>
                        <span class="tag tag-human" style="font-size: 1.1rem;">Written by: ${escapeHtml(d.author_name)}</span>
                    </div>
                    <div style="margin: 12px 0;">
                        ${d.items.map(item => `
                            <div class="dossier-response-item">
                                <span style="color: #93c5fd; font-weight: 600;">${escapeHtml(item.game_title)}:</span>
                                <span>${Array.isArray(item.response) ? item.response.join(", ") : escapeHtml(item.response)}</span>
                            </div>
                        `).join("")}
                    </div>
                    ${correctVoters}
                </div>
            `;
        }).join("");
    }

    if (isNewPhase) {
        startCountdown(10, "bonus-reveal-timer", advancePhase);
    }
}

// --- Phase 9: Game Over ---
function renderGameOver(state) {
    clearInterval(countdownInterval);

    if (state.winner) {
        document.getElementById("winner-name").innerText = `🎉 ${state.winner.name} 🎉`;
        document.getElementById("winner-score").innerText = `Final Score: ${state.winner.score} pts`;
    }

    const tbody = document.getElementById("gameover-scoreboard-body");
    tbody.innerHTML = state.players.map((p, i) => `
        <tr>
            <td class="rank-badge">${i === 0 ? '🥇' : (i === 1 ? '🥈' : (i === 2 ? '🥉' : `#${i + 1}`))}</td>
            <td style="font-weight: 700;">${escapeHtml(p.name)}</td>
            <td style="font-weight: 800; color: #60a5fa;">${p.score} pts</td>
        </tr>
    `).join("");
}

// --- Helpers & Timers ---

function startCountdown(seconds, elementId, callback) {
    clearInterval(countdownInterval);
    countdownSeconds = seconds;
    const el = document.getElementById(elementId);
    if (el) el.innerText = countdownSeconds;

    countdownInterval = setInterval(() => {
        countdownSeconds -= 1;
        if (el) el.innerText = Math.max(0, countdownSeconds);
        if (countdownSeconds <= 0) {
            clearInterval(countdownInterval);
            if (callback) callback();
        }
    }, 1000);
}

async function advancePhase() {
    clearInterval(countdownInterval);
    const phaseAtTrigger = currentState ? currentState.phase : null;
    await fetch("/api/next_phase", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_phase: phaseAtTrigger })
    });
    pollHostState();
}

async function resetToLobby() {
    clearInterval(countdownInterval);
    await fetch("/api/reset", { method: "POST" });
    pollHostState();
}

function escapeHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
