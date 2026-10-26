// player.js - Mobile controller logic for players

let playerId = localStorage.getItem("bot_or_not_player_id");
let playerName = localStorage.getItem("bot_or_not_player_name");
let playerPollTimer = null;
let currentPromptType = "text";
let lastSubmissionRound = -1;
let lastSubmissionQuestionIdx = -1;
let lastVotingRound = -1;
let lastVotingQuestionIdx = -1;
let lastStateCached = null;

// Timers and multi-select state
let playerCountdown = null;
let playerCountdownSeconds = 25;
let currentPhaseCached = null;
let currentRoundCached = null;
let selectedVoteIds = [];
let maxVotesRequired = 1;
let bonusGuesses = {};

// Draft auto-sync state
let draftSyncTimer = null;
let lastSentDraftJson = null;
let lastDraftSentTime = 0;

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

document.addEventListener("DOMContentLoaded", () => {
    initInputListeners();
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
            lastSubmissionRound = -1;
            lastSubmissionQuestionIdx = -1;
            lastVotingRound = -1;
            lastVotingQuestionIdx = -1;
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
    lastSubmissionRound = -1;
    lastSubmissionQuestionIdx = -1;
    lastVotingRound = -1;
    lastVotingQuestionIdx = -1;
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
            lastStateCached = state;
            renderPlayerView(state);
        }
    } catch (err) {
        console.error("Player poll error:", err);
    }
}

function renderPlayerView(state) {
    // Update player header badge with secret score visible to player
    if (state.player) {
        document.getElementById("player-status-bar").style.display = "block";
        document.getElementById("player-display-name").innerText = state.player.name;
        document.getElementById("player-display-score").innerText = state.player.score_display || `${state.player.score || 0} pts`;
    }

    const qInfo = state.question_info || {};
    const currPromptIdx = qInfo.current_prompt_index ?? (state.question_index ?? 0);
    const currVoteIdx = qInfo.current_vote_index ?? (state.question_index ?? 0);

    const isPhaseOrRoundChanged = (currentPhaseCached !== state.phase || currentRoundCached !== state.round_number);
    const isPromptChanged = isPhaseOrRoundChanged || (state.phase === "SUBMITTING" && lastSubmissionQuestionIdx !== currPromptIdx);
    const isVoteChanged = isPhaseOrRoundChanged || (state.phase === "VOTING" && lastVotingQuestionIdx !== currVoteIdx);

    currentPhaseCached = state.phase;
    currentRoundCached = state.round_number;

    switch (state.phase) {
        case "LOBBY":
            clearInterval(playerCountdown);
            showScreen("screen-lobby");
            break;

        case "INTRO":
            clearInterval(playerCountdown);
            showScreen("screen-instructions");
            const introTitle = document.getElementById("player-inst-title");
            if (introTitle) introTitle.innerText = "GLORPCORP ORIENTATION";
            const introInstEl = document.getElementById("player-inst-text");
            const introMsg = "Mandatory Turing Protocol briefing in progress on Host display. Direct attention to the main screen before Round 1 begins...";
            if (introInstEl && (isPhaseOrRoundChanged || introInstEl.getAttribute("data-typed-text") !== introMsg)) {
                introInstEl.setAttribute("data-typed-text", introMsg);
                typeTerminalText(introInstEl, introMsg, { speed: 15, cursor: true });
            }
            break;

        case "INSTRUCTIONS":
            clearInterval(playerCountdown);
            showScreen("screen-instructions");
            const pTitle = document.getElementById("player-inst-title");
            if (pTitle) pTitle.innerText = state.title || "Next Minigame";
            const instEl = document.getElementById("player-inst-text");
            const instText = state.instruction || "";
            if (instEl && (isPhaseOrRoundChanged || instEl.getAttribute("data-typed-text") !== instText)) {
                instEl.setAttribute("data-typed-text", instText);
                typeTerminalText(instEl, instText, { speed: 15, cursor: true });
            }
            break;

        case "SUBMITTING":
            renderSubmittingScreen(state, isPromptChanged);
            break;

        case "VOTING":
            renderVotingScreen(state, isVoteChanged);
            break;

        case "REVEAL":
        case "SCOREBOARD":
        case "BONUS_REVEAL":
            renderWatchTvScreen(state);
            break;

        case "BONUS":
            clearInterval(playerCountdown);
            renderBonusScreen(state, isPhaseOrRoundChanged);
            break;

        case "GAME_OVER":
            clearInterval(playerCountdown);
            showScreen("screen-watch-tv");
            document.getElementById("watch-tv-title").innerText = "Game Over!";
            document.getElementById("watch-tv-desc").innerText = "Look at the main screen for the grand champion!";
            const rpt = document.getElementById("player-score-report");
            if (rpt) rpt.style.display = "none";
            break;
    }
}

// --- Watch TV Screen (Reveals & Confidential Scorecard) ---
function renderWatchTvScreen(state) {
    clearInterval(playerCountdown);
    showScreen("screen-watch-tv");

    const titleEl = document.getElementById("watch-tv-title");
    const descEl = document.getElementById("watch-tv-desc");
    const scoreReport = document.getElementById("player-score-report");

    if (state.phase === "SCOREBOARD") {
        titleEl.innerText = "Standings on the TV!";
        descEl.innerText = "Check the TV for ranking movements, and keep your secret score safe below.";
    } else if (state.phase === "REVEAL") {
        titleEl.innerText = "The Reveal on the TV!";
        descEl.innerText = "Watch the main screen to see which answers were bots!";
    } else if (state.phase === "BONUS_REVEAL") {
        titleEl.innerText = "Dossier Reveal!";
        descEl.innerText = "Watch the main screen to see who wrote which dossier!";
    }

    const summary = state.round_summary;
    if (summary && scoreReport) {
        scoreReport.style.display = "block";

        const roundVal = document.getElementById("player-round-score-val");
        if (roundVal) {
            roundVal.innerText = summary.round_score_display || "+0 pts";
            if (summary.round_score > 0) {
                roundVal.style.color = "#34d399";
            } else if (summary.round_score < 0) {
                roundVal.style.color = "#f87171";
            } else {
                roundVal.style.color = "#9ca3af";
            }
        }

        const totalVal = document.getElementById("player-total-score-val");
        if (totalVal) {
            totalVal.innerText = summary.total_score_display || `${state.player?.score || 0} pts`;
        }

        const rankVal = document.getElementById("player-rank-movement-val");
        if (rankVal) {
            rankVal.innerText = `#${summary.rank || 1} (${summary.rank_change_display || '―'})`;
        }

        const breakdownList = document.getElementById("player-breakdown-list");
        if (breakdownList) {
            const items = summary.breakdown || [];
            if (items.length > 0) {
                breakdownList.innerHTML = items.map(b => `
                    <div style="display: flex; justify-content: space-between; margin-bottom: 4px; font-size: 0.9rem;">
                        <span style="color: #d1d5db;">Prompt ${b.question_number}:</span>
                        <span style="font-weight: 700; color: ${b.points > 0 ? '#34d399' : (b.points < 0 ? '#f87171' : '#9ca3af')};">
                            ${escapeHtml(b.points_display)}
                        </span>
                    </div>
                `).join("");
            } else {
                breakdownList.innerHTML = `<span style="color: #9ca3af; font-size: 0.85rem;">Points recorded for this round.</span>`;
            }
        }
    } else if (scoreReport) {
        scoreReport.style.display = "none";
    }
}

// --- Real-time Draft Auto-Sync ---

function getCurrentInputPayload() {
    if (currentPromptType === "multi_field") {
        const a1 = (document.getElementById("survey-input-1")?.value || "");
        const a2 = (document.getElementById("survey-input-2")?.value || "");
        const a3 = (document.getElementById("survey-input-3")?.value || "");
        return [a1, a2, a3];
    } else {
        return (document.getElementById("single-response-input")?.value || "");
    }
}

function onTextInputUpdate() {
    if (currentPhaseCached !== "SUBMITTING" || !playerId) return;

    const payload = getCurrentInputPayload();
    const jsonStr = JSON.stringify(payload);
    if (jsonStr === lastSentDraftJson) return;

    const now = Date.now();
    const timeSinceLast = now - lastDraftSentTime;
    const THROTTLE_MS = 250;

    clearTimeout(draftSyncTimer);

    if (timeSinceLast >= THROTTLE_MS) {
        sendDraftUpdate(payload);
    } else {
        draftSyncTimer = setTimeout(() => {
            sendDraftUpdate(getCurrentInputPayload());
        }, THROTTLE_MS - timeSinceLast);
    }
}

async function sendDraftUpdate(payload) {
    if (currentPhaseCached !== "SUBMITTING" || !playerId) return;
    const jsonStr = JSON.stringify(payload);
    lastSentDraftJson = jsonStr;
    lastDraftSentTime = Date.now();

    const currQIdx = lastStateCached?.question_info?.current_prompt_index ?? (lastStateCached?.question_index ?? 0);

    try {
        await fetch("/api/submit", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                player_id: playerId,
                response: payload,
                locked: false,
                version: lastDraftSentTime,
                question_index: currQIdx
            })
        });
    } catch (err) {
        console.warn("Draft auto-sync warning:", err);
    }
}

function flushDraftNow() {
    if (currentPhaseCached === "SUBMITTING" && playerId) {
        clearTimeout(draftSyncTimer);
        const payload = getCurrentInputPayload();
        sendDraftUpdate(payload);
    }
}

function initInputListeners() {
    const singleInput = document.getElementById("single-response-input");
    if (singleInput) {
        singleInput.addEventListener("input", onTextInputUpdate);
        singleInput.addEventListener("change", onTextInputUpdate);
        singleInput.addEventListener("blur", flushDraftNow);
    }

    ["survey-input-1", "survey-input-2", "survey-input-3"].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener("input", onTextInputUpdate);
            el.addEventListener("change", onTextInputUpdate);
            el.addEventListener("blur", flushDraftNow);
        }
    });

    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "hidden") {
            flushDraftNow();
        }
    });

    window.addEventListener("pagehide", flushDraftNow);
}

// --- Submitting Phase ---
function renderSubmittingScreen(state, isPromptChanged) {
    showScreen("screen-submitting");
    const formBox = document.getElementById("submitting-form-container");
    const doneBox = document.getElementById("submitting-done-container");

    const qInfo = state.question_info || {};
    const currPromptNum = qInfo.current_prompt_number || (state.question_number || 1);
    const totalQ = qInfo.total_questions || (state.total_questions || 3);
    const currPromptIdx = qInfo.current_prompt_index ?? (state.question_index ?? 0);

    const stepTag = document.getElementById("player-prompt-step-tag");
    if (stepTag) stepTag.innerText = `Prompt ${currPromptNum} of ${totalQ}`;

    if (state.has_submitted) {
        clearInterval(playerCountdown);
        clearTimeout(draftSyncTimer);
        formBox.style.display = "none";
        doneBox.style.display = "block";

        const doneDesc = document.getElementById("submitting-done-desc");
        if (doneDesc) {
            if (currPromptNum < totalQ) {
                doneDesc.innerText = `Prompt ${currPromptNum} of ${totalQ} locked in! Waiting for next prompt...`;
            } else {
                doneDesc.innerText = "All prompts submitted! Waiting for voting phase...";
            }
        }
        return;
    }

    formBox.style.display = "block";
    doneBox.style.display = "none";

    const promptData = state.prompt || {};
    currentPromptType = promptData.type || "text";

    const promptHeading = document.getElementById("prompt-heading");
    const pHeadText = promptData.prompt_text || "Enter your response:";
    if (promptHeading && (isPromptChanged || promptHeading.getAttribute("data-typed-text") !== pHeadText)) {
        promptHeading.setAttribute("data-typed-text", pHeadText);
        typeTerminalText(promptHeading, pHeadText, { speed: 18, cursor: true });
    }

    // Reset inputs when prompt changes
    if (isPromptChanged) {
        lastSubmissionRound = state.round_number;
        lastSubmissionQuestionIdx = currPromptIdx;
        document.getElementById("single-response-input").value = "";
        document.getElementById("survey-input-1").value = "";
        document.getElementById("survey-input-2").value = "";
        document.getElementById("survey-input-3").value = "";
        lastSentDraftJson = null;
        lastDraftSentTime = 0;
        clearTimeout(draftSyncTimer);

        // Start countdown timer for this prompt
        startMobileTimer(state.submission_timeout || 30, "player-submit-seconds", () => {
            submitAnswer(true);
        });
    } else if (state.draft && !state.has_submitted) {
        // Restore draft from server if input is currently empty
        const singleInput = document.getElementById("single-response-input");
        const s1 = document.getElementById("survey-input-1");
        const s2 = document.getElementById("survey-input-2");
        const s3 = document.getElementById("survey-input-3");
        if (currentPromptType === "multi_field" && Array.isArray(state.draft)) {
            if (!s1.value && !s2.value && !s3.value) {
                s1.value = state.draft[0] || "";
                s2.value = state.draft[1] || "";
                s3.value = state.draft[2] || "";
            }
        } else if (typeof state.draft === "string" && !singleInput.value) {
            singleInput.value = state.draft;
        }
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
        document.getElementById("single-response-input").placeholder = promptData.placeholder || "Describe what is depicted in this image...";
    } else {
        singleBox.style.display = "block";
        multiBox.style.display = "none";
        captchaBox.style.display = "none";
        document.getElementById("single-response-input").placeholder = promptData.placeholder || "Type here...";
    }
}

async function submitAnswer(isAutoTimeout = false) {
    clearTimeout(draftSyncTimer);

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

    const formBox = document.getElementById("submitting-form-container");
    const doneBox = document.getElementById("submitting-done-container");
    if (formBox && doneBox) {
        formBox.style.display = "none";
        doneBox.style.display = "block";
    }

    const currQIdx = lastStateCached?.question_info?.current_prompt_index ?? (lastStateCached?.question_index ?? 0);

    try {
        const res = await fetch("/api/submit", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                player_id: playerId,
                response: payload,
                locked: true,
                version: Date.now(),
                question_index: currQIdx
            })
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
function renderVotingScreen(state, isVoteChanged) {
    showScreen("screen-voting");
    const choicesBox = document.getElementById("voting-choices-container");
    const doneBox = document.getElementById("voting-done-container");

    const qInfo = state.question_info || {};
    const currVoteNum = qInfo.current_vote_number || (state.question_number || 1);
    const totalQ = qInfo.total_questions || (state.total_questions || 3);
    const currVoteIdx = qInfo.current_vote_index ?? (state.question_index ?? 0);

    const stepTag = document.getElementById("player-voting-step-tag");
    if (stepTag) stepTag.innerText = `Voting Set ${currVoteNum} of ${totalQ}`;

    const reminderEl = document.getElementById("player-voting-prompt-reminder");
    if (reminderEl) {
        const pText = state.prompt_text ? `Prompt: ${state.prompt_text}` : "";
        reminderEl.style.display = state.prompt_text ? "block" : "none";
        if (pText && (isVoteChanged || reminderEl.getAttribute("data-typed-text") !== pText)) {
            reminderEl.setAttribute("data-typed-text", pText);
            typeTerminalText(reminderEl, `>> PROMPT: ${pText}`, { speed: 14, cursor: true });
        }
    }

    // Check if CAPTCHA challenge image is present for voting
    const captchaBox = document.getElementById("player-voting-captcha-preview");
    const captchaImg = document.getElementById("player-voting-captcha-img");
    const imageUrl = state.image_url || (state.prompt_data && state.prompt_data.image_url);
    if (captchaBox && captchaImg) {
        if (imageUrl) {
            captchaBox.style.display = "block";
            if (!captchaImg.src.includes(imageUrl)) {
                captchaImg.src = imageUrl;
            }
        } else {
            captchaBox.style.display = "none";
            captchaImg.src = "";
        }
    }

    if (state.has_voted) {
        clearInterval(playerCountdown);
        choicesBox.style.display = "none";
        doneBox.style.display = "block";

        const doneDesc = document.getElementById("voting-done-desc");
        if (doneDesc) {
            if (currVoteNum < totalQ) {
                doneDesc.innerText = `Vote for Set ${currVoteNum} of ${totalQ} locked in! Next voting set coming up...`;
            } else {
                doneDesc.innerText = "All votes locked in! Watch the TV screen for the reveal!";
            }
        }

        const doneCaptchaBox = document.getElementById("player-voting-done-captcha");
        const doneCaptchaImg = document.getElementById("player-voting-done-captcha-img");
        if (doneCaptchaBox && doneCaptchaImg) {
            if (imageUrl) {
                doneCaptchaBox.style.display = "block";
                if (!doneCaptchaImg.src.includes(imageUrl)) {
                    doneCaptchaImg.src = imageUrl;
                }
            } else {
                doneCaptchaBox.style.display = "none";
                doneCaptchaImg.src = "";
            }
        }
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

    if (isVoteChanged) {
        lastVotingRound = state.round_number;
        lastVotingQuestionIdx = currVoteIdx;
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

    // Guard: Prevent re-rendering option cards every second while voting unless question changed
    const existingOptionCards = optionsContainer.querySelectorAll(".option-card");
    if (existingOptionCards.length > 0 && !isVoteChanged) {
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
    const currQIdx = lastStateCached?.question_info?.current_vote_index ?? (lastStateCached?.question_index ?? 0);

    try {
        const res = await fetch("/api/vote", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                player_id: playerId,
                target_option_ids: optionIds,
                question_index: currQIdx
            })
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
                        <div style="font-size: 0.75rem; color: #9ca3af;">${escapeHtml(it.game_title)}${it.question_num ? ` (Q${it.question_num})` : ''}:</div>
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
