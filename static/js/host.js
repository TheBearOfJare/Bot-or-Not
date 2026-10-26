// host.js - Host screen controller and state rendering

let currentState = null;
let pollTimer = null;
let countdownInterval = null;
let countdownSeconds = 0;
let lastRenderedPhase = null;
let lastPromptIndex = -1;
let lastVoteIndex = -1;
let lastRevealIndex = -1;

// --- Terminal Typewriter Effect ---
function typeTerminalText(element, text, options = {}) {
    if (!element) return;
    const speed = options.speed || 16;
    const showCursor = options.cursor !== false;
    const onComplete = options.onComplete || null;

    if (element._termTimer) {
        clearTimeout(element._termTimer);
        element._termTimer = null;
    }

    if (!text) {
        element.textContent = "";
        if (onComplete) onComplete();
        return;
    }

    element.textContent = "";
    let cursorSpan = null;
    if (showCursor) {
        cursorSpan = document.createElement("span");
        cursorSpan.className = "terminal-cursor";
        cursorSpan.innerHTML = "&nbsp;";
        element.appendChild(cursorSpan);
    }

    let charIndex = 0;
    function nextChar() {
        if (charIndex < text.length) {
            const char = text.charAt(charIndex);
            charIndex++;
            const textNode = document.createTextNode(char);
            if (cursorSpan && cursorSpan.parentNode === element) {
                element.insertBefore(textNode, cursorSpan);
            } else {
                element.appendChild(textNode);
            }
            const jitter = Math.floor(Math.random() * 6) - 3;
            element._termTimer = setTimeout(nextChar, Math.max(6, speed + jitter));
        } else {
            element._termTimer = null;
            if (options.removeCursorAfter) {
                setTimeout(() => {
                    if (cursorSpan && cursorSpan.parentNode === element) {
                        cursorSpan.remove();
                    }
                }, options.removeCursorAfter);
            }
            if (onComplete) onComplete();
        }
    }

    nextChar();
}

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
        "lobby", "intro", "instructions", "submitting", "voting", 
        "reveal", "scoreboard", "bonus", "bonus-reveal", "game-over"
    ];

    // Synchronize host background music with current phase
    if (window.bgmManager && typeof window.bgmManager.onPhaseChange === "function") {
        window.bgmManager.onPhaseChange(state.phase);
    }

    const currentPhaseKey = state.phase.toLowerCase().replace("_", "-");

    // Show only active phase section
    phases.forEach(p => {
        const el = document.getElementById(`phase-${p}`);
        if (el) {
            el.style.display = (p === currentPhaseKey) ? "block" : "none";
        }
    });

    const qInfo = state.question_info || {};
    const currPromptIdx = qInfo.current_prompt_index ?? 0;
    const currVoteIdx = qInfo.current_vote_index ?? 0;
    const currRevIdx = qInfo.current_reveal_index ?? 0;

    // Detect phase and sub-step changes for timer resets
    const isPhaseChanged = (lastRenderedPhase !== state.phase);
    const isNewPrompt = isPhaseChanged || (state.phase === "SUBMITTING" && lastPromptIndex !== currPromptIdx);
    const isNewVote = isPhaseChanged || (state.phase === "VOTING" && lastVoteIndex !== currVoteIdx);
    const isNewReveal = isPhaseChanged || (state.phase === "REVEAL" && lastRevealIndex !== currRevIdx);

    lastRenderedPhase = state.phase;
    lastPromptIndex = currPromptIdx;
    lastVoteIndex = currVoteIdx;
    lastRevealIndex = currRevIdx;

    if (state.phase !== "REVEAL") {
        clearRevealSequence();
        currentRevealingKey = null;
    }

    switch (state.phase) {
        case "LOBBY":
            renderLobby(state);
            break;
        case "INTRO":
            renderIntro(state, isPhaseChanged);
            break;
        case "INSTRUCTIONS":
            renderInstructions(state, isPhaseChanged);
            break;
        case "SUBMITTING":
            renderSubmitting(state, isNewPrompt);
            break;
        case "VOTING":
            renderVoting(state, isNewVote);
            break;
        case "REVEAL":
            renderReveal(state, isNewReveal);
            break;
        case "SCOREBOARD":
            renderScoreboard(state, isPhaseChanged);
            break;
        case "BONUS":
            renderBonus(state);
            break;
        case "BONUS_REVEAL":
            renderBonusReveal(state, isPhaseChanged);
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

    // Update active state of questions per minigame buttons
    const qCount = state.questions_per_minigame || 3;
    document.querySelectorAll(".btn-setting").forEach(btn => {
        btn.classList.toggle("active", btn.id === `btn-q-${qCount}`);
    });

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

async function setQuestionsCount(count) {
    document.querySelectorAll(".btn-setting").forEach(btn => btn.classList.remove("active"));
    const btn = document.getElementById(`btn-q-${count}`);
    if (btn) btn.classList.add("active");

    try {
        await fetch("/api/set_settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ questions_per_minigame: count })
        });
        pollHostState();
    } catch (err) {
        console.error("Failed to update questions count:", err);
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

        const activeBtn = document.querySelector(".btn-setting.active");
        const questionsCount = activeBtn ? parseInt(activeBtn.id.replace("btn-q-", ""), 10) : 3;

        const res = await fetch("/api/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ 
                sequence: checked.length > 0 ? checked : null,
                questions_per_minigame: questionsCount
            })
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

// --- Phase 1.5: Intro (GlorpCorp Orientation Briefing) ---
function renderIntro(state, isNewPhase) {
    const instEl = document.getElementById("intro-text");
    const introText = state.intro_text || "";
    if (instEl && (isNewPhase || instEl.getAttribute("data-typed-text") !== introText)) {
        instEl.setAttribute("data-typed-text", introText);
        // Slower deliberate typewriter pace for orientation briefing
        typeTerminalText(instEl, introText, { speed: 32, cursor: true });
    }

    if (isNewPhase) {
        const timeout = state.intro_timeout || 32;
        startCountdown(timeout, "intro-timer", advancePhase);
    }
}

// --- Phase 2: Instructions ---
function renderInstructions(state, isNewPhase) {
    const qInfo = state.question_info || {};
    const totalQ = qInfo.total_questions || state.questions_per_minigame || 3;

    document.getElementById("instructions-round-tag").innerText = `[ ROUND ${state.round_number} OF ${state.total_rounds} ]`;
    const qTag = document.getElementById("instructions-questions-tag");
    if (qTag) qTag.innerText = `[ ${totalQ} PROMPTS ]`;

    if (state.game_info) {
        document.getElementById("instructions-game-title").innerText = state.game_info.title;
        const instEl = document.getElementById("instructions-text");
        const instText = state.game_info.instruction || "";
        if (instEl && (isNewPhase || instEl.getAttribute("data-typed-text") !== instText)) {
            instEl.setAttribute("data-typed-text", instText);
            typeTerminalText(instEl, instText, { speed: 15, cursor: true });
        }
    }

    if (isNewPhase) {
        startCountdown(8, "instructions-timer", advancePhase);
    }
}

// --- Phase 3: Submitting ---
function renderSubmitting(state, isNewPrompt) {
    const qInfo = state.question_info || {};
    const totalQ = qInfo.total_questions || state.questions_per_minigame || 3;
    const currPromptNum = qInfo.current_prompt_number || 1;

    document.getElementById("submitting-round-tag").innerText = `[ ROUND ${state.round_number} OF ${state.total_rounds} ]`;
    const qTag = document.getElementById("submitting-question-tag");
    if (qTag) qTag.innerText = `[ PROMPT ${currPromptNum} OF ${totalQ} ]`;

    if (state.game_info) {
        document.getElementById("submitting-game-title").innerText = state.game_info.title;
        const promptData = state.game_info.prompt_data || {};
        const pText = promptData.prompt_text || "";

        const promptEl = document.getElementById("submitting-prompt-text");
        if (promptEl && (isNewPrompt || promptEl.getAttribute("data-typed-text") !== pText)) {
            promptEl.setAttribute("data-typed-text", pText);
            typeTerminalText(promptEl, pText, { speed: 18, cursor: true });
        }

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

    if (isNewPrompt) {
        startCountdown(state.submission_timeout || 30, "submitting-timer", advancePhase);
    }

    // Submissions progress badges
    const list = document.getElementById("submitting-players-list");
    if (state.submissions_status) {
        list.innerHTML = state.submissions_status.map(p => `
            <div class="player-badge ${p.has_submitted ? 'ready' : 'pending'}">
                <span>${p.has_submitted ? '✓' : (p.has_draft ? '✍' : '◌')}</span>
                <span>${escapeHtml(p.name)}</span>
                <span style="font-size: 0.82rem; color: var(--text-secondary);">${p.has_submitted ? '[SUBMITTED]' : (p.has_draft ? '[TYPING...]' : '[THINKING...]')}</span>
            </div>
        `).join("");
    }
}

// --- Phase 4: Voting ---
function renderVoting(state, isNewVote) {
    const qInfo = state.question_info || {};
    const totalQ = qInfo.total_questions || state.questions_per_minigame || 3;
    const currVoteNum = qInfo.current_vote_number || 1;

    if (state.game_info) {
        document.getElementById("voting-game-title").innerText = state.game_info.title;
        const promptData = state.game_info.prompt_data || {};
        const reminderEl = document.getElementById("voting-prompt-reminder");
        if (reminderEl) {
            const pText = promptData.prompt_text ? `Prompt: ${promptData.prompt_text}` : "";
            reminderEl.style.display = promptData.prompt_text ? "block" : "none";
            if (pText && (isNewVote || reminderEl.getAttribute("data-typed-text") !== pText)) {
                reminderEl.setAttribute("data-typed-text", pText);
                typeTerminalText(reminderEl, pText, { speed: 14, cursor: true });
            }
        }

        // Check if image captcha
        const captchaBox = document.getElementById("voting-captcha-box");
        const captchaImg = document.getElementById("voting-captcha-img");
        if (captchaBox && captchaImg) {
            const imgUrl = promptData.image_url || state.image_url;
            if ((promptData.type === "image_caption" || state.game_info.id === "captcha") && imgUrl) {
                captchaBox.style.display = "block";
                if (!captchaImg.src.includes(imgUrl)) {
                    captchaImg.src = imgUrl;
                }
            } else {
                captchaBox.style.display = "none";
                captchaImg.src = "";
            }
        }
    }

    const qTag = document.getElementById("voting-question-tag");
    if (qTag) qTag.innerText = `Voting Set ${currVoteNum} of ${totalQ}`;

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

    if (isNewVote) {
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

// --- Phase 5: Reveal (Sequential Talent Show / Stamp Reveal) ---

let revealTimeouts = [];
let currentRevealingKey = null;
let stampAudioCtx = null;

function clearRevealSequence() {
    revealTimeouts.forEach(t => clearTimeout(t));
    revealTimeouts = [];
    const promptReminder = document.getElementById("reveal-prompt-reminder");
    if (promptReminder) {
        if (promptReminder._termTimer) {
            clearTimeout(promptReminder._termTimer);
            promptReminder._termTimer = null;
        }
        promptReminder.removeAttribute("data-typed-text");
    }
}

function playStampSound() {
    try {
        if (!stampAudioCtx) {
            if (window.bgmManager && typeof window.bgmManager.getAudioContext === "function" && window.bgmManager.getAudioContext()) {
                stampAudioCtx = window.bgmManager.getAudioContext();
            } else {
                const AudioCtx = window.AudioContext || window.webkitAudioContext;
                if (AudioCtx) stampAudioCtx = new AudioCtx();
            }
        }
        if (stampAudioCtx && stampAudioCtx.state === "suspended") {
            stampAudioCtx.resume();
        }
        if (!stampAudioCtx) return;

        const now = stampAudioCtx.currentTime;

        // Punchy low stamp thud
        const osc = stampAudioCtx.createOscillator();
        const gain = stampAudioCtx.createGain();
        osc.type = "triangle";
        osc.frequency.setValueAtTime(140, now);
        osc.frequency.exponentialRampToValueAtTime(32, now + 0.18);

        gain.gain.setValueAtTime(0.35, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.2);

        osc.connect(gain);
        gain.connect(stampAudioCtx.destination);
        osc.start(now);
        osc.stop(now + 0.2);

        // Talent show rejection buzzer / impact buzz
        const buzz = stampAudioCtx.createOscillator();
        const buzzGain = stampAudioCtx.createGain();
        buzz.type = "sawtooth";
        buzz.frequency.setValueAtTime(220, now);
        buzz.frequency.linearRampToValueAtTime(95, now + 0.14);

        buzzGain.gain.setValueAtTime(0.18, now);
        buzzGain.gain.exponentialRampToValueAtTime(0.001, now + 0.15);

        buzz.connect(buzzGain);
        buzzGain.connect(stampAudioCtx.destination);
        buzz.start(now);
        buzz.stop(now + 0.15);
    } catch (e) {
        // Fallback gracefully if audio is prevented by browser policy
    }
}

function triggerStampSlam(cardEl, stampEl, cardIndex, stampIndex, totalVotes, isBot) {
    playStampSound();

    // Trigger punchy card shake on impact
    if (cardEl) {
        cardEl.classList.remove("card-shake");
        void cardEl.offsetWidth; // trigger reflow
        cardEl.classList.add("card-shake");
    }

    // Extensible event & callback for user-provided sound assets or animations
    const detail = { cardIndex, stampIndex, totalVotes, isBot };
    window.dispatchEvent(new CustomEvent("bot-vote-stamp", { detail }));
    if (typeof window.onBotVoteStamp === "function") {
        window.onBotVoteStamp(detail);
    }
}

function sortRevealCards(cards) {
    return [...cards].sort((a, b) => {
        const botA = a.is_bot ? 1 : 0;
        const botB = b.is_bot ? 1 : 0;
        if (botA !== botB) {
            return botA - botB; // Humans (0) first, then bots (1)
        }
        return (a.vote_count || 0) - (b.vote_count || 0); // Lowest to highest vote count
    });
}

function renderReveal(state, isNewReveal) {
    const qInfo = state.question_info || {};
    const totalQ = qInfo.total_questions || state.questions_per_minigame || 3;
    const currRevNum = qInfo.current_reveal_number || 1;

    const qTag = document.getElementById("reveal-question-tag");
    if (qTag) qTag.innerText = `Question ${currRevNum} of ${totalQ}`;

    const revealData = state.reveal_data || {};
    const promptReminder = document.getElementById("reveal-prompt-reminder");
    const pText = revealData.active_prompt_data?.prompt_text || "";
    if (promptReminder) {
        promptReminder.style.display = pText ? "block" : "none";
    }

    const captchaBox = document.getElementById("reveal-captcha-box");
    const captchaImg = document.getElementById("reveal-captcha-img");
    if (captchaBox && captchaImg) {
        const imgUrl = revealData.active_prompt_data?.image_url;
        if (revealData.active_prompt_data?.type === "image_caption" && imgUrl) {
            captchaBox.style.display = "block";
            if (!captchaImg.src.includes(imgUrl)) {
                captchaImg.src = imgUrl;
            }
        } else {
            captchaBox.style.display = "none";
            captchaImg.src = "";
        }
    }

    const container = document.getElementById("reveal-cards-container");
    const rawCards = revealData.reveal_cards || [];
    const sortedCards = sortRevealCards(rawCards);

    const revealKey = `${currRevNum}_${pText}`;

    // If new reveal or not currently rendering this question's sequence
    if (isNewReveal || currentRevealingKey !== revealKey) {
        currentRevealingKey = revealKey;
        clearRevealSequence();
        container.innerHTML = "";

        if (sortedCards.length === 0) {
            container.innerHTML = `<div style="text-align:center; color:#9ca3af; padding:30px;">No responses to reveal for this question.</div>`;
            startCountdown(8, "reveal-timer", advancePhase);
            const bottomTimer = document.getElementById("reveal-timer-bottom");
            if (bottomTimer) bottomTimer.innerText = "8";
            return;
        }

        // Calculate card timings with generous, dramatic pacing:
        // For 0-vote cards: 800ms read text -> zero votes badge & details appear -> 2200ms active read -> 500ms transition = 3500ms
        // For cards with votes: 800ms read text -> (votes * 450ms stamps) -> 150ms details fade-in -> 2200ms active read -> 500ms transition = 3650 + (votes * 450) ms
        const cardDurations = sortedCards.map(c => {
            const votes = c.vote_count || 0;
            return votes === 0 ? 3500 : 3650 + (votes * 450);
        });

        const totalAnimMs = cardDurations.reduce((sum, d) => sum + d, 0);

        // Calculate prompt typing and 1-second pause duration
        const fullPrompt = pText ? `>> EVALUATING: ${pText}` : "";
        const promptTypingEstMs = fullPrompt ? (fullPrompt.length * 16) : 0;
        const postPromptWaitMs = fullPrompt ? 1000 : 500;
        const initialDelayMs = promptTypingEstMs + postPromptWaitMs;

        // Leave ~6.5s after all cards are revealed for players to read the complete board
        const totalDurationSec = Math.max(12, Math.ceil((initialDelayMs + totalAnimMs + 6500) / 1000));

        startCountdown(totalDurationSec, "reveal-timer", advancePhase);
        const bottomTimer = document.getElementById("reveal-timer-bottom");
        if (bottomTimer) bottomTimer.innerText = totalDurationSec;

        function startCardSequence() {
            let cumulativeTime = 0;
            sortedCards.forEach((card, cardIndex) => {
                const cardStartTime = cumulativeTime;
                const duration = cardDurations[cardIndex];
                cumulativeTime += duration;

                const t = setTimeout(() => {
                    displayRevealCardStep(container, card, cardIndex);
                }, cardStartTime);
                revealTimeouts.push(t);
            });
        }

        // Write the whole prompt on first, then wait 1 second before answers come in
        if (promptReminder && fullPrompt) {
            promptReminder.setAttribute("data-typed-text", pText);
            typeTerminalText(promptReminder, fullPrompt, {
                speed: 16,
                cursor: true,
                onComplete: () => {
                    const tWait = setTimeout(() => {
                        startCardSequence();
                    }, 1000);
                    revealTimeouts.push(tWait);
                }
            });
        } else {
            const tWait = setTimeout(() => {
                startCardSequence();
            }, 1000);
            revealTimeouts.push(tWait);
        }
    }
}

function displayRevealCardStep(container, card, cardIndex) {
    const isBot = Boolean(card.is_bot);
    const voteCount = card.vote_count || 0;
    const voters = card.voter_names || [];

    const content = Array.isArray(card.response) 
        ? `<ol style="margin-left: 20px;">${card.response.map(r => `<li>${escapeHtml(r)}</li>`).join("")}</ol>`
        : `"${escapeHtml(card.response)}"`;

    const votersText = voters.length > 0 
        ? `Voted as Bot by: <strong>${voters.map(escapeHtml).join(", ")}</strong>` 
        : "No votes received.";

    // Fix bug: If it's a bot with 0 votes, it was NOT identified, so show it went undetected!
    let pointsNotice = "";
    if (isBot) {
        if (voteCount > 0) {
            pointsNotice = `<div style="color: #6ee7b7; font-weight: 600; margin-top: 6px;">🎯 Identified as BOT! (+100 pts to voters)</div>`;
        } else {
            pointsNotice = `<div style="color: #fbbf24; font-weight: 600; margin-top: 6px;">🤖 Undetected BOT passed as human! Fooled all players (0 votes).</div>`;
        }
    } else {
        if (voteCount > 0) {
            pointsNotice = `<div style="color: #f87171; font-weight: 600; margin-top: 6px;">⚠️ Looked like a bot! (${-(25 * voteCount)} pts penalty to author)</div>`;
        } else {
            pointsNotice = `<div style="color: #9ca3af; margin-top: 6px;">Clearly human, no votes.</div>`;
        }
    }

    const cardDiv = document.createElement("div");
    cardDiv.className = `reveal-card ${isBot ? 'bot' : 'human'} revealing-active`;
    cardDiv.id = `reveal-card-${cardIndex}`;

    cardDiv.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
            <span class="tag ${isBot ? 'tag-bot' : 'tag-human'}">
                ${isBot ? '🤖 BOT' : '👤 HUMAN PLAYER'}
            </span>
            <div class="vote-stamps-corner" id="stamps-corner-${cardIndex}"></div>
        </div>
        <div style="font-size: 1.25rem; margin: 10px 0;">${content}</div>
        <div class="reveal-card-details" id="details-card-${cardIndex}" style="font-size: 1rem; color: #d1d5db; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 8px; margin-top: 8px; opacity: 0; transition: opacity 0.35s ease;">
            ${votersText}
            ${pointsNotice}
        </div>
    `;

    container.prepend(cardDiv);
    window.scrollTo({ top: 0, behavior: "smooth" });

    const corner = cardDiv.querySelector(`#stamps-corner-${cardIndex}`);
    const details = cardDiv.querySelector(`#details-card-${cardIndex}`);

    if (voteCount === 0) {
        // Zero votes badge
        const badge = document.createElement("span");
        badge.className = isBot ? "zero-votes-badge bot-undetected-badge" : "zero-votes-badge";
        badge.innerText = isBot ? "0 votes (Undetected!)" : "0 votes";

        // Give players 800ms to read answer text before showing zero-votes badge and details
        const tZero = setTimeout(() => {
            corner.appendChild(badge);
            if (details) details.style.opacity = "1";
        }, 800);
        revealTimeouts.push(tZero);

        // Keep active highlight for players to read the status
        const tActive = setTimeout(() => {
            cardDiv.classList.remove("revealing-active");
        }, 3000);
        revealTimeouts.push(tActive);
    } else {
        // Give players 800ms to read answer text before stamps begin slamming down
        for (let i = 0; i < voteCount; i++) {
            const stampDelay = 800 + (i * 450);
            const tStamp = setTimeout(() => {
                const stamp = document.createElement("div");
                stamp.className = "vote-stamp";
                stamp.setAttribute("data-stamp-index", i);
                stamp.title = "Voted as Bot";
                // Slight random rotation angle for talent show stamp vibe (-10deg to 10deg)
                const rot = (Math.sin((cardIndex + 1) * (i + 1) * 37) * 9).toFixed(1);
                stamp.style.setProperty("--stamp-rot", `${rot}deg`);
                stamp.innerHTML = `<span class="vote-stamp-icon">🤖</span>`;
                corner.appendChild(stamp);

                triggerStampSlam(cardDiv, stamp, cardIndex, i, voteCount, isBot);
            }, stampDelay);
            revealTimeouts.push(tStamp);
        }

        // Once all stamps slammed down: show vote count pill and reveal details
        const finishDelay = 800 + (voteCount * 450) + 150;
        const tFinish = setTimeout(() => {
            const countPill = document.createElement("span");
            countPill.className = "vote-count-pill";
            countPill.innerText = `${voteCount} vote${voteCount > 1 ? 's' : ''}`;
            corner.appendChild(countPill);

            if (details) details.style.opacity = "1";
        }, finishDelay);
        revealTimeouts.push(tFinish);

        // Give players 2.2s of active glow to read who voted and point penalties before removing active glow
        const tActive = setTimeout(() => {
            cardDiv.classList.remove("revealing-active");
        }, finishDelay + 2200);
        revealTimeouts.push(tActive);
    }
}

// --- Phase 6: Scoreboard (Classified Standings & Ranking Changes) ---
function renderScoreboard(state, isNewPhase) {
    const tbody = document.getElementById("scoreboard-body");
    const rankings = state.rankings || [];

    if (rankings.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:#9ca3af;">Computing ranking changes...</td></tr>`;
    } else {
        tbody.innerHTML = rankings.map((r, i) => {
            const rankBadge = i === 0 ? '🥇 1st' : (i === 1 ? '🥈 2nd' : (i === 2 ? '🥉 3rd' : `#${r.rank}`));
            let moveBadge = `<span class="badge-movement badge-movement-none">―</span>`;
            if (r.rank_change > 0) {
                moveBadge = `<span class="badge-movement badge-movement-up">▲ ${r.rank_change}</span>`;
            } else if (r.rank_change < 0) {
                moveBadge = `<span class="badge-movement badge-movement-down">▼ ${Math.abs(r.rank_change)}</span>`;
            }

            return `
                <tr>
                    <td class="rank-badge" style="font-size: 1.25rem;">${rankBadge}</td>
                    <td style="font-weight: 700; font-size: 1.25rem;">${escapeHtml(r.name)}</td>
                    <td>${moveBadge}</td>
                    <td><span class="classified-score">${escapeHtml(r.score_display || '█████ [CLASSIFIED]')}</span></td>
                </tr>
            `;
        }).join("");
    }

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
                        <div style="font-size: 0.8rem; color: #9ca3af;">${escapeHtml(item.game_title)}${item.question_num ? ` (Q${item.question_num})` : ''}:</div>
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
                                <span style="color: #93c5fd; font-weight: 600;">${escapeHtml(item.game_title)}${item.question_num ? ` (Q${item.question_num})` : ''}:</span>
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
        const wName = document.getElementById("winner-name");
        const wScore = document.getElementById("winner-score");
        const winTitle = `[ CHAMPION: ${state.winner.name} ]`;
        const scoreTitle = `Aggregate Evaluation Score: ${state.winner.score} pts`;
        if (wName && wName.getAttribute("data-typed-text") !== winTitle) {
            wName.setAttribute("data-typed-text", winTitle);
            typeTerminalText(wName, winTitle, { speed: 25, cursor: true });
        }
        if (wScore && wScore.getAttribute("data-typed-text") !== scoreTitle) {
            wScore.setAttribute("data-typed-text", scoreTitle);
            typeTerminalText(wScore, scoreTitle, { speed: 20, cursor: true });
        }
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

    const bottomRev = document.getElementById("reveal-timer-bottom");
    if (elementId === "reveal-timer" && bottomRev) bottomRev.innerText = countdownSeconds;

    countdownInterval = setInterval(() => {
        countdownSeconds -= 1;
        const curSec = Math.max(0, countdownSeconds);
        if (el) el.innerText = curSec;
        if (elementId === "reveal-timer" && bottomRev) bottomRev.innerText = curSec;

        if (countdownSeconds <= 0) {
            clearInterval(countdownInterval);
            if (callback) callback();
        }
    }, 1000);
}

async function advancePhase() {
    clearInterval(countdownInterval);
    clearRevealSequence();
    currentRevealingKey = null;
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
    clearRevealSequence();
    currentRevealingKey = null;
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

// --- Title Screen & Audio Controls Bridge ---
let isHostLaunched = false;

function launchHostSystem() {
    if (isHostLaunched) return;
    isHostLaunched = true;

    // Directly initialize AudioContext and trigger BGM from this direct user click
    if (window.bgmManager && typeof window.bgmManager.startFromUserGesture === "function") {
        window.bgmManager.startFromUserGesture();
    }

    const titleScreen = document.getElementById("host-title-screen");
    if (titleScreen) {
        titleScreen.classList.add("fade-out");
        setTimeout(() => {
            titleScreen.style.display = "none";
        }, 400);
    }
}

// Pressing Space or Enter engages the title screen
window.addEventListener("keydown", (e) => {
    if (!isHostLaunched && (e.code === "Space" || e.code === "Enter")) {
        e.preventDefault();
        launchHostSystem();
    }
});

function toggleBgmAudio() {
    if (!isHostLaunched) {
        launchHostSystem();
        return;
    }
    if (window.bgmManager) {
        window.bgmManager.cycleVolume();
    }
}

function unlockAudioPrompt() {
    launchHostSystem();
}
