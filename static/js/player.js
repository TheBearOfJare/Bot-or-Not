// player.js - Mobile controller logic for players

let playerId = localStorage.getItem("bot_or_not_player_id");
let playerName = localStorage.getItem("bot_or_not_player_name");
let playerPollTimer = null;
let currentPromptType = "text";
let lastSubmissionRound = -1;
let lastVotingRound = -1;

// Timers and multi-select state
let playerCountdown = null;
let playerCountdownSeconds = 25;
let currentPhaseCached = null;
let currentRoundCached = null;
let selectedVoteIds = [];
let maxVotesRequired = 1;
let bonusGuesses = {};

document.addEventListener("DOMContentLoaded", () => {
    if (playerId) {
        startPolling();
    } else {
        showScreen("screen-join");
    }
});

function showScreen(screenId) {
    const screens = [
        "screen-join", "screen-lobby", "screen-instructions", 
        "screen-submitting", "screen-voting", "screen-watch-tv", "screen-bonus"
    ];
    screens.forEach(s => {
        const el = document.getElementById(s);
        if (el) el.style.display = (s === screenId) ? "block" : "none";
    });
}

async function handleJoin(e) {
    e.preventDefault();
    const nameInput = document.getElementById("player-name-input");
    const name = nameInput.value.trim();
    if (!name) return;

    try {
        const res = await fetch("/api/join", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: name })
        });
        const data = await res.json();
        if (data.success) {
            playerId = data.player.id;
            playerName = data.player.name;
            localStorage.setItem("bot_or_not_player_id", playerId);
            localStorage.setItem("bot_or_not_player_name", playerName);
            currentPhaseCached = null;
            currentRoundCached = null;
            bonusGuesses = {};
            selectedVoteIds = [];
            startPolling();
        } else {
            alert(data.error || "Failed to join");
        }
    } catch (err) {
        console.error("Join error:", err);
        alert("Error connecting to game server.");
    }
}

function leaveGame(e) {
    if (e) e.preventDefault();
    clearInterval(playerPollTimer);
    localStorage.removeItem("bot_or_not_player_id");
    localStorage.removeItem("bot_or_not_player_name");
    playerId = null;
    playerName = null;
    bonusGuesses = {};
    selectedVoteIds = [];
    currentPhaseCached = null;
    currentRoundCached = null;
    document.getElementById("player-name-input").value = "";
    document.getElementById("player-status-bar").style.display = "none";
    showScreen("screen-join");
}

function startPolling() {
    pollPlayerState();
    if (playerPollTimer) clearInterval(playerPollTimer);
    playerPollTimer = setInterval(pollPlayerState, 1000);
}

async function pollPlayerState() {
    if (!playerId) return;
    try {
        const res = await fetch(`/api/player_state?player_id=${encodeURIComponent(playerId)}`);
        if (res.ok) {
            const state = await res.json();
            if (state.phase === "UNREGISTERED") {
                localStorage.removeItem("bot_or_not_player_id");
                playerId = null;
                showScreen("screen-join");
                return;
            }
            renderPlayerView(state);
        }
    } catch (err) {
        console.error("Player poll error:", err);
    }
}

function renderPlayerView(state) {
    // Update player header badge - scores remain classified during intermediate rounds
    if (state.player) {
        document.getElementById("player-status-bar").style.display = "block";
        document.getElementById("player-display-name").innerText = state.player.name;
        document.getElementById("player-display-score").innerText = state.player.score_display || "Encrypted 🔒";
    }

    const isPhaseOrRoundChanged = (currentPhaseCached !== state.phase || currentRoundCached !== state.round_number);
    currentPhaseCached = state.phase;
    currentRoundCached = state.round_number;

    switch (state.phase) {
        case "LOBBY":
            clearInterval(playerCountdown);
            showScreen("screen-lobby");
            break;

        case "INSTRUCTIONS":
            clearInterval(playerCountdown);
            showScreen("screen-instructions");
            document.getElementById("player-inst-title").innerText = state.title || "Next Minigame";
            document.getElementById("player-inst-text").innerText = state.instruction || "";
            break;

        case "SUBMITTING":
            renderSubmittingScreen(state, isPhaseOrRoundChanged);
            break;

        case "VOTING":
            renderVotingScreen(state, isPhaseOrRoundChanged);
            break;

        case "REVEAL":
        case "BONUS_REVEAL":
            clearInterval(playerCountdown);
            showScreen("screen-watch-tv");
            document.getElementById("watch-tv-title").innerText = "The Reveal!";
            document.getElementById("watch-tv-desc").innerText = "Watch the TV screen to see who was a bot!";
            document.getElementById("player-round-score-notice").innerText = "";
            break;

        case "SCOREBOARD":
            clearInterval(playerCountdown);
            showScreen("screen-watch-tv");
            document.getElementById("watch-tv-title").innerText = "Scores are Classified!";
            document.getElementById("watch-tv-desc").innerText = "Results are hidden until the final evaluation!";
            document.getElementById("player-round-score-notice").innerText = "";
            break;

        case "BONUS":
            clearInterval(playerCountdown);
            renderBonusScreen(state, isPhaseOrRoundChanged);
            break;

        case "GAME_OVER":
            clearInterval(playerCountdown);
            showScreen("screen-watch-tv");
            document.getElementById("watch-tv-title").innerText = "Game Over!";
            document.getElementById("watch-tv-desc").innerText = "Look at the main screen for the grand winner!";
            document.getElementById("player-round-score-notice").innerText = "";
            break;
    }
}

// --- Submitting Phase ---
function renderSubmittingScreen(state, isPhaseChanged) {
    showScreen("screen-submitting");
    const formBox = document.getElementById("submitting-form-container");
    const doneBox = document.getElementById("submitting-done-container");

    if (state.has_submitted) {
        clearInterval(playerCountdown);
        formBox.style.display = "none";
        doneBox.style.display = "block";
        return;
    }

    formBox.style.display = "block";
    doneBox.style.display = "none";

    const promptData = state.prompt || {};
    currentPromptType = promptData.type || "text";

    document.getElementById("prompt-heading").innerText = promptData.prompt_text || "Enter your response:";

    // Reset inputs if new round
    if (lastSubmissionRound !== state.round_number) {
        lastSubmissionRound = state.round_number;
        document.getElementById("single-response-input").value = "";
        document.getElementById("survey-input-1").value = "";
        document.getElementById("survey-input-2").value = "";
        document.getElementById("survey-input-3").value = "";
    }

    // Start 25s submit timer
    if (isPhaseChanged) {
        startMobileTimer(state.submission_timeout || 25, "player-submit-seconds", () => {
            // Auto submit whatever is typed
            submitAnswer(true);
        });
    }

    const singleBox = document.getElementById("input-single-container");
    const multiBox = document.getElementById("input-multi-container");
    const captchaBox = document.getElementById("player-captcha-preview");

    if (currentPromptType === "multi_field") {
        singleBox.style.display = "none";
        multiBox.style.display = "block";
        captchaBox.style.display = "none";
    } else if (currentPromptType === "image_caption") {
        singleBox.style.display = "block";
        multiBox.style.display = "none";
        captchaBox.style.display = "block";
        if (promptData.image_url) {
            document.getElementById("player-captcha-img").src = promptData.image_url;
        }
        document.getElementById("single-response-input").placeholder = promptData.placeholder || "Describe what is happening in this image...";
    } else {
        singleBox.style.display = "block";
        multiBox.style.display = "none";
        captchaBox.style.display = "none";
        document.getElementById("single-response-input").placeholder = promptData.placeholder || "Type here...";
    }
}

async function submitAnswer(isAutoTimeout = false) {
    let payload = null;
    if (currentPromptType === "multi_field") {
        const a1 = document.getElementById("survey-input-1").value.trim();
        const a2 = document.getElementById("survey-input-2").value.trim();
        const a3 = document.getElementById("survey-input-3").value.trim();
        if (!a1 && !a2 && !a3 && !isAutoTimeout) {
            alert("Please enter at least one answer!");
            return;
        }
        payload = [a1 || "Answer 1", a2 || "Answer 2", a3 || "Answer 3"];
    } else {
        const val = document.getElementById("single-response-input").value.trim();
        if (!val && !isAutoTimeout) {
            alert("Please write a response!");
            return;
        }
        payload = val || "[No response submitted]";
    }

    clearInterval(playerCountdown);

    try {
        const res = await fetch("/api/submit", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ player_id: playerId, response: payload })
        });
        const data = await res.json();
        if (data.success) {
            pollPlayerState();
        }
    } catch (err) {
        console.error("Submit error:", err);
    }
}

// --- Voting Phase ---
function renderVotingScreen(state, isPhaseChanged) {
    showScreen("screen-voting");
    const choicesBox = document.getElementById("voting-choices-container");
    const doneBox = document.getElementById("voting-done-container");

    if (state.has_voted) {
        clearInterval(playerCountdown);
        choicesBox.style.display = "none";
        doneBox.style.display = "block";
        return;
    }

    choicesBox.style.display = "block";
    doneBox.style.display = "none";

    maxVotesRequired = state.max_votes_per_player || 1;
    const titleEl = document.getElementById("player-voting-title");
    const subEl = document.getElementById("player-voting-subtitle");
    const lockBtn = document.getElementById("btn-lock-multi-votes");

    if (maxVotesRequired >= 2) {
        if (titleEl) titleEl.innerText = "Select 2 BOT Responses";
        if (subEl) subEl.innerText = "Lobby size 5+: Tap 2 responses you think are bots, then lock in:";
        if (lockBtn) lockBtn.style.display = "block";
    } else {
        if (titleEl) titleEl.innerText = "Which one is the BOT?";
        if (subEl) subEl.innerText = "Tap the response you think was generated by an AI:";
        if (lockBtn) lockBtn.style.display = "none";
    }

    if (isPhaseChanged) {
        selectedVoteIds = [];
        updateMultiVoteButton();
        startMobileTimer(state.voting_timeout || 25, "player-vote-seconds", null);
    }

    const optionsContainer = document.getElementById("player-voting-options");
    const options = state.options || [];

    if (options.length === 0) {
        optionsContainer.innerHTML = '<p style="text-align:center; color:#9ca3af;">No other responses to vote on.</p>';
        return;
    }

    // Guard: Prevent re-rendering option cards every second while voting
    const existingOptionCards = optionsContainer.querySelectorAll(".option-card");
    if (existingOptionCards.length > 0 && !isPhaseChanged) {
        return;
    }

    optionsContainer.innerHTML = options.map((opt, i) => {
        const isSelected = selectedVoteIds.includes(opt.id);
        const content = Array.isArray(opt.response)
            ? `<ol style="margin-left: 20px;">${opt.response.map(r => `<li>${escapeHtml(r)}</li>`).join("")}</ol>`
            : `"${escapeHtml(opt.response)}"`;

        return `
            <div class="option-card ${isSelected ? 'multi-selected' : ''}" 
                 onclick="handleOptionClick('${opt.id}')" 
                 id="opt-card-${opt.id}"
                 style="margin-bottom: 12px;">
                <div style="font-size: 1.1rem; margin-bottom: 8px;">${content}</div>
                <button class="btn ${isSelected ? 'btn-success' : 'btn-primary'} btn-sm" style="width: 100%;">
                    ${isSelected ? '✅ SELECTED AS BOT' : '🚨 VOTE AS BOT'}
                </button>
            </div>
        `;
    }).join("");
}

function handleOptionClick(optionId) {
    if (maxVotesRequired === 1) {
        // Single vote immediate submit
        submitVotes([optionId]);
    } else {
        // Toggle selection for 2 votes
        if (selectedVoteIds.includes(optionId)) {
            selectedVoteIds = selectedVoteIds.filter(id => id !== optionId);
        } else {
            if (selectedVoteIds.length < maxVotesRequired) {
                selectedVoteIds.push(optionId);
            } else {
                // Replace oldest selection
                selectedVoteIds.shift();
                selectedVoteIds.push(optionId);
            }
        }
        updateMultiVoteUI();
    }
}

function updateMultiVoteUI() {
    document.querySelectorAll("#player-voting-options .option-card").forEach(card => {
        const id = card.id.replace("opt-card-", "");
        const btn = card.querySelector("button");
        if (selectedVoteIds.includes(id)) {
            card.classList.add("multi-selected");
            if (btn) {
                btn.className = "btn btn-success btn-sm";
                btn.innerText = "✅ SELECTED AS BOT";
            }
        } else {
            card.classList.remove("multi-selected");
            if (btn) {
                btn.className = "btn btn-primary btn-sm";
                btn.innerText = "🚨 VOTE AS BOT";
            }
        }
    });
    updateMultiVoteButton();
}

function updateMultiVoteButton() {
    const lockBtn = document.getElementById("btn-lock-multi-votes");
    if (!lockBtn) return;
    const count = selectedVoteIds.length;
    lockBtn.innerText = `Lock In Votes (${count}/${maxVotesRequired})`;
    if (count === maxVotesRequired) {
        lockBtn.className = "btn btn-success";
        lockBtn.disabled = false;
    } else {
        lockBtn.className = "btn btn-primary";
        lockBtn.disabled = true;
    }
}

async function submitMultiVotes() {
    if (selectedVoteIds.length < maxVotesRequired) {
        alert(`Please select ${maxVotesRequired} bot responses!`);
        return;
    }
    submitVotes(selectedVoteIds);
}

async function submitVotes(optionIds) {
    clearInterval(playerCountdown);
    try {
        const res = await fetch("/api/vote", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ player_id: playerId, target_option_ids: optionIds })
        });
        const data = await res.json();
        if (data.success) {
            pollPlayerState();
        }
    } catch (err) {
        console.error("Vote error:", err);
    }
}

// --- Bonus Round Matching ---
function renderBonusScreen(state, isPhaseOrRoundChanged) {
    showScreen("screen-bonus");
    const formBox = document.getElementById("bonus-form-container");
    const doneBox = document.getElementById("bonus-done-container");

    if (state.has_guessed) {
        formBox.style.display = "none";
        doneBox.style.display = "block";
        return;
    }

    formBox.style.display = "block";
    doneBox.style.display = "none";

    const list = document.getElementById("bonus-dossiers-list");

    if (isPhaseOrRoundChanged) {
        bonusGuesses = {};
    }

    // Guard: Prevent wiping out select dropdowns every 1-second poll
    const existingCards = list.querySelectorAll(".dossier-card");
    if (existingCards.length > 0 && !isPhaseOrRoundChanged) {
        return;
    }

    const bonusData = state.bonus_data || {};
    const dossiers = bonusData.dossiers || [];
    const candidates = bonusData.candidates || [];

    if (dossiers.length === 0) {
        list.innerHTML = '<p style="text-align:center; color:#9ca3af;">Preparing dossiers...</p>';
        return;
    }

    list.innerHTML = dossiers.map(d => {
        const selectedVal = bonusGuesses[d.dossier_id] || "";
        const optionsHtml = candidates.map(c => `
            <option value="${c.id}" ${c.id === selectedVal ? 'selected' : ''}>${escapeHtml(c.name)}</option>
        `).join("");

        return `
            <div class="dossier-card" data-dossier-id="${d.dossier_id}">
                <div style="font-weight: 800; color: #fbbf24; margin-bottom: 6px;">
                    📁 ${escapeHtml(d.label)} ${d.is_own ? '<span style="color:#6ee7b7; font-size:0.8rem;">(This might be yours!)</span>' : ''}
                </div>
                ${d.items.map(it => `
                    <div class="dossier-response-item">
                        <div style="font-size: 0.75rem; color: #9ca3af;">${escapeHtml(it.game_title)}:</div>
                        <div style="font-style: italic;">${Array.isArray(it.response) ? it.response.join(", ") : escapeHtml(it.response)}</div>
                    </div>
                `).join("")}
                <div style="margin-top: 10px;">
                    <label style="font-size: 0.85rem; color: #d1d5db;">Who wrote this?</label>
                    <select class="dossier-guess-select" style="margin-top: 4px;" onchange="handleBonusSelectChange('${d.dossier_id}', this.value)">
                        <option value="">-- Select Player --</option>
                        ${optionsHtml}
                    </select>
                </div>
            </div>
        `;
    }).join("");
}

function handleBonusSelectChange(dossierId, selectedPlayerId) {
    if (selectedPlayerId) {
        bonusGuesses[dossierId] = selectedPlayerId;
    } else {
        delete bonusGuesses[dossierId];
    }
}

async function submitBonusMatches() {
    // Read from both the DOM selects and bonusGuesses
    const cards = document.querySelectorAll("#bonus-dossiers-list .dossier-card");
    cards.forEach(card => {
        const dossierId = card.getAttribute("data-dossier-id");
        const select = card.querySelector(".dossier-guess-select");
        if (dossierId && select && select.value) {
            bonusGuesses[dossierId] = select.value;
        }
    });

    if (Object.keys(bonusGuesses).length === 0) {
        alert("Please match at least one dossier to a player!");
        return;
    }

    try {
        const res = await fetch("/api/bonus_guess", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ player_id: playerId, guesses: bonusGuesses })
        });
        const data = await res.json();
        if (data.success) {
            pollPlayerState();
        } else {
            alert(data.error || "Failed to submit guesses.");
        }
    } catch (err) {
        console.error("Bonus guess error:", err);
    }
}

function startMobileTimer(seconds, elementId, timeoutCallback) {
    clearInterval(playerCountdown);
    playerCountdownSeconds = seconds;
    const el = document.getElementById(elementId);
    if (el) el.innerText = playerCountdownSeconds;

    playerCountdown = setInterval(() => {
        playerCountdownSeconds -= 1;
        if (el) el.innerText = Math.max(0, playerCountdownSeconds);
        if (playerCountdownSeconds <= 0) {
            clearInterval(playerCountdown);
            if (timeoutCallback) timeoutCallback();
        }
    }, 1000);
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
