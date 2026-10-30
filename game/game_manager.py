import os
import uuid
import time
import threading
from typing import Dict, Any, List, Optional
from config import Config
from game.bot_engine import BotEngine
from game.minigames import MINIGAME_REGISTRY, create_minigame_instance
from game.prompt_tracker import prompt_tracker
from game.minigames.captcha import clear_captcha_images

class GameManager:
    def __init__(self, config=Config):
        self.config = config
        self.bot_engine = BotEngine(config.OLLAMA_URL, config.OLLAMA_MODEL)
        self.prompt_tracker = prompt_tracker
        self.lock = threading.RLock()
        
        # Clear generated CAPTCHA images on startup
        clear_captcha_images()
        
        self.players: Dict[str, Dict[str, Any]] = {}
        # player_id -> list of { "round": int, "game_title": str, "prompt": str, "response": Any }
        self.player_history: Dict[str, List[Dict[str, Any]]] = {}
        
        # Sequence of minigames to play
        self.game_sequence: List[str] = list(self.config.DEFAULT_GAME_SEQUENCE)
        self.current_sequence_index: int = -1
        
        # Configurable questions per minigame (default 3)
        self.questions_per_minigame: int = getattr(self.config, "QUESTIONS_PER_MINIGAME", 3)
        
        # Current phase: LOBBY, INSTRUCTIONS, SUBMITTING, VOTING, REVEAL, SCOREBOARD, BONUS, BONUS_REVEAL, GAME_OVER
        self.phase: str = "LOBBY"
        self.current_game = None
        self.round_number: int = 0
        
        # Phase start timestamp (for timer progress on host/client)
        self.phase_start_time: float = time.time()
        
        # Cached reveal data for the current round
        self.cached_reveal_data: Optional[Dict[str, Any]] = None
        
        # Ranking changes and secret scores
        self.last_round_rankings: List[Dict[str, Any]] = []
        self.player_round_scores: Dict[str, Dict[str, Any]] = {}
        
        # Pause status
        self.is_paused: bool = False
        self.pause_start_time: float = 0.0
        self.paused_total_duration: float = 0.0

    def reset_to_lobby(self, clear_players: bool = False):
        """Reset game state back to lobby."""
        with self.lock:
            self.phase = "LOBBY"
            self.is_paused = False
            self.pause_start_time = 0.0
            self.paused_total_duration = 0.0
            self.current_sequence_index = -1
            self.current_game = None
            self.round_number = 0
            self.cached_reveal_data = None
            self.last_round_rankings.clear()
            self.player_round_scores.clear()
            self.player_history.clear()
            if clear_players:
                self.players.clear()
            else:
                for p in self.players.values():
                    p["score"] = 0
                    self.player_history[p["id"]] = []
    @property
    def current_submission_timeout(self) -> int:
        if self.current_game and getattr(self.current_game, "game_id", None) == "survey":
            return getattr(self.config, "SUBMISSION_TIMEOUT_SURVEY", 45)
        return getattr(self.config, "SUBMISSION_TIMEOUT", 35)

    @property
    def current_voting_timeout(self) -> int:
        is_survey = bool(self.current_game and getattr(self.current_game, "game_id", None) == "survey")
        per_response = getattr(self.config, "VOTING_TIME_PER_RESPONSE_SURVEY", 15) if is_survey else getattr(self.config, "VOTING_TIME_PER_RESPONSE", 10)

        response_count = 0
        if self.current_game and hasattr(self.current_game, "questions"):
            curr_v_idx = getattr(self.current_game, "current_vote_index", 0)
            if 0 <= curr_v_idx < len(self.current_game.questions):
                q = self.current_game.questions[curr_v_idx]
                submissions = q.get("submissions", {})
                if submissions:
                    response_count = len(submissions)

        # Fallback if submissions are not yet populated (e.g. before voting phase starts)
        if response_count == 0:
            human_count = len(self.players)
            large_threshold = getattr(self.config, "LARGE_LOBBY_THRESHOLD", 5)
            bot_count = getattr(self.current_game, "bot_count", None)
            if bot_count is None:
                bot_count = 2 if human_count >= large_threshold else 1
            response_count = human_count + bot_count

        return max(1, response_count) * per_response

    @property
    def current_time_remaining(self) -> int:
        if self.phase in ("LOBBY", "GAME_OVER"):
            return 0
        now = time.time()
        if self.is_paused and self.pause_start_time > 0:
            elapsed = self.pause_start_time - self.phase_start_time - self.paused_total_duration
        else:
            elapsed = now - self.phase_start_time - self.paused_total_duration

        if self.phase == "VOTING":
            timeout = self.current_voting_timeout
        elif self.phase == "SUBMITTING":
            timeout = self.current_submission_timeout
        elif self.phase == "INTRO":
            timeout = getattr(self.config, "INTRO_TIMEOUT", 45)
        elif self.phase == "INSTRUCTIONS":
            timeout = getattr(self.config, "INSTRUCTIONS_TIMEOUT", 8)
        elif self.phase == "SCOREBOARD":
            timeout = getattr(self.config, "SCOREBOARD_TIMEOUT", 8)
        elif self.phase == "BONUS_REVEAL":
            timeout = 10
        else:
            timeout = 30
        return max(0, int(round(timeout - elapsed)))

    def set_game_sequence(self, sequence: List[str]):
        """Allow host to customize which minigames are played and in what order."""
        with self.lock:
            valid_keys = [k for k in sequence if k in MINIGAME_REGISTRY]
            if valid_keys:
                self.game_sequence = valid_keys

    def set_questions_per_minigame(self, count: int):
        """Allow host to configure how many questions/prompts run per minigame."""
        with self.lock:
            self.questions_per_minigame = max(1, min(10, int(count)))
            print(f"[GameManager] Questions per minigame updated to: {self.questions_per_minigame}")

    def register_player(self, name: str) -> Dict[str, Any]:
        """Add a human player to the game."""
        with self.lock:
            cleaned_name = name.strip()[:18] or f"Player-{len(self.players)+1}"
            player_id = f"p_{uuid.uuid4().hex[:6]}"
            
            self.players[player_id] = {
                "id": player_id,
                "name": cleaned_name,
                "score": 0,
                "joined_at": time.time()
            }
            self.player_history[player_id] = []
            return self.players[player_id]

    def remove_player(self, player_id: str) -> bool:
        """Remove a player from the game session (e.g. kicked from lobby by host)."""
        with self.lock:
            if player_id not in self.players:
                return False
            name = self.players[player_id].get("name", player_id)
            del self.players[player_id]
            if player_id in self.player_history:
                del self.player_history[player_id]
            if player_id in self.player_round_scores:
                del self.player_round_scores[player_id]
            self.last_round_rankings = [r for r in self.last_round_rankings if r.get("id") != player_id]
            print(f"[GameManager] Player removed from lobby: {name} ({player_id})")
            return True

    def start_game(self) -> bool:
        """
        Start the match from the lobby.
        Guarded against re-entrant calls so duplicate clicks or requests
        never restart an already running game.
        """
        with self.lock:
            if self.phase != "LOBBY":
                print(f"[GameManager] start_game ignored: phase is already '{self.phase}'")
                return False

            self.current_sequence_index = 0
            self.round_number = 1
            self.is_paused = False
            self.pause_start_time = 0.0
            self.paused_total_duration = 0.0
            self.last_round_rankings.clear()
            self.player_round_scores.clear()
            self._load_current_game()
            self.phase = "INTRO"
            self.phase_start_time = time.time()
            print(f"[GameManager] Match started successfully! Phase: INTRO (GlorpCorp Orientation)")
            return True

    def _load_current_game(self):
        game_key = self.game_sequence[self.current_sequence_index]
        # Dynamic bots: 2 bots if 5+ players, else 1
        bot_count = 2 if len(self.players) >= self.config.LARGE_LOBBY_THRESHOLD else 1
        
        self.current_game = create_minigame_instance(
            game_key=game_key,
            bot_engine=self.bot_engine,
            bot_count=bot_count,
            questions_count=self.questions_per_minigame
        )
        self.cached_reveal_data = None

        if game_key == "bonus":
            self.current_game.start_round(self.players, self.player_history)
        else:
            self.current_game.start_round(self.players)

    def get_intro_text(self) -> str:
        """Reads intro orientation instructions from voicelines.txt."""
        voicelines_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "voicelines.txt")
        if os.path.exists(voicelines_path):
            try:
                with open(voicelines_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        return content
            except Exception as e:
                print(f"[GameManager] Error reading voicelines.txt: {e}")
        return (
            "Welcome, test subjects. The future of propaganda and misinformation is finally here at GlorpCorp.ru. "
            "Our bots are purpose built to help you curb criticism, defame your competitors, or win your next election. "
            "But before they can go influencing public opinion, they need to pass as human first, and there's still a few kinks to work out. "
            "Today's exercises are pretty simple. In each round you'll be given a series of prompts for a simple task. "
            "You have a short amount of time to answer each one, so try to think fast! "
            "Once everyone's finished, you'll get to see everyone's responses, but be careful, because at least one of them was written by our bots. "
            "Your job is to sort out which one's which. Guess which one's the bot, and you'll gain points. "
            "If anyone thinks your response was AI generated, you'll lose points. Got it? Let's begin."
        )

    def toggle_pause(self) -> bool:
        """Toggles the game pause state."""
        with self.lock:
            now = time.time()
            if not self.is_paused:
                self.is_paused = True
                self.pause_start_time = now
            else:
                self.is_paused = False
                if self.pause_start_time > 0:
                    self.paused_total_duration += (now - self.pause_start_time)
                self.pause_start_time = 0.0
            print(f"[GameManager] Pause toggled: is_paused={self.is_paused}")
            return self.is_paused

    def next_phase(self, expected_phase: Optional[str] = None) -> bool:
        """
        Advances game state machine to the next natural phase or sub-step.
        Guarded by lock and expected_phase to prevent race condition skips.
        """
        with self.lock:
            if expected_phase and self.phase != expected_phase:
                print(f"[GameManager] next_phase ignored: expected '{expected_phase}', but current phase is '{self.phase}'")
                return False

            now = time.time()
            self.phase_start_time = now
            self.is_paused = False
            self.pause_start_time = 0.0
            self.paused_total_duration = 0.0

            if self.phase == "LOBBY":
                return self.start_game()

            elif self.phase == "INTRO":
                self.phase = "INSTRUCTIONS"
                self.phase_start_time = now
                print(f"[GameManager] Intro complete. Advancing to Round {self.round_number}: {self.current_game.title if self.current_game else ''}")

            elif self.phase == "INSTRUCTIONS":
                if self.current_game and getattr(self.current_game, "game_id", None) == "bonus":
                    self.phase = "BONUS"
                else:
                    self.phase = "SUBMITTING"
                    if self.current_game:
                        self.current_game._in_voting_phase = False
                        self.current_game.current_prompt_index = 0

            elif self.phase == "SUBMITTING":
                # Finalize submissions for the current prompt
                if self.current_game and hasattr(self.current_game, "finalize_submissions"):
                    curr_p_idx = getattr(self.current_game, "current_prompt_index", 0)
                    self.current_game.finalize_submissions(self.players, question_index=curr_p_idx)

                # Check if there are more prompts to serve one after the other
                total_q = getattr(self.current_game, "questions_count", 1) if self.current_game else 1
                curr_p_idx = getattr(self.current_game, "current_prompt_index", 0) if self.current_game else 0

                if self.current_game and curr_p_idx + 1 < total_q:
                    self.current_game.current_prompt_index += 1
                    self.phase_start_time = now
                    print(f"[GameManager] Advancing to Prompt {self.current_game.current_prompt_index + 1} of {total_q}")
                else:
                    # All prompts served! Move to VOTING!
                    if self.current_game and hasattr(self.current_game, "ensure_bots_ready"):
                        self.current_game.ensure_bots_ready(timeout=2.0)
                    self.phase = "VOTING"
                    if self.current_game:
                        self.current_game._in_voting_phase = True
                        self.current_game.current_vote_index = 0
                    print(f"[GameManager] All {total_q} prompts submitted! Starting Voting Set 1 of {total_q}")

            elif self.phase == "VOTING":
                total_q = getattr(self.current_game, "questions_count", 1) if self.current_game else 1
                curr_v_idx = getattr(self.current_game, "current_vote_index", 0) if self.current_game else 0

                # Finalize votes for current question before advancing so unlocked draft votes are preserved
                if self.current_game and hasattr(self.current_game, "finalize_votes"):
                    self.current_game.finalize_votes(self.players, question_index=curr_v_idx)

                # Check if there are more sets of responses to vote on one after the other
                if self.current_game and curr_v_idx + 1 < total_q:
                    self.current_game.current_vote_index += 1
                    self.phase_start_time = now
                    self.pause_start_time = 0.0
                    self.paused_total_duration = 0.0
                    print(f"[GameManager] Advancing to Voting Set {self.current_game.current_vote_index + 1} of {total_q}")
                else:
                    # All voting sets complete! Calculate scores and start REVEAL!
                    self.phase = "REVEAL"
                    if self.current_game:
                        self.current_game.current_reveal_index = 0
                    self._finalize_round_and_rankings()
                    print(f"[GameManager] All {total_q} voting sets complete! Entering REVEAL phase")

            elif self.phase == "REVEAL":
                total_q = getattr(self.current_game, "questions_count", 1) if self.current_game else 1
                curr_r_idx = getattr(self.current_game, "current_reveal_index", 0) if self.current_game else 0

                # Check if there are more question reveals to step through
                if self.current_game and curr_r_idx + 1 < total_q:
                    self.current_game.current_reveal_index += 1
                    player_names = {pid: p["name"] for pid, p in self.players.items()}
                    self.cached_reveal_data = self.current_game.get_reveal_data(player_names, self.config)
                    self.phase_start_time = now
                    print(f"[GameManager] Showing Reveal for Question {self.current_game.current_reveal_index + 1} of {total_q}")
                else:
                    # All reveals shown! Move to SCOREBOARD to reveal ranking changes!
                    self.phase = "SCOREBOARD"
                    print("[GameManager] All reveals complete. Entering SCOREBOARD phase (Ranking Changes)")

            elif self.phase == "BONUS":
                # Tally bonus round
                player_names = {pid: p["name"] for pid, p in self.players.items()}
                self.cached_reveal_data = self.current_game.get_reveal_data(player_names, self.config)
                self._finalize_bonus_round_and_rankings()
                self.phase = "BONUS_REVEAL"

            elif self.phase == "BONUS_REVEAL":
                self.phase = "GAME_OVER"

            elif self.phase == "SCOREBOARD":
                # Move to next game in sequence
                self.current_sequence_index += 1
                if self.current_sequence_index >= len(self.game_sequence):
                    self.phase = "GAME_OVER"
                else:
                    self.round_number += 1
                    self._load_current_game()
                    self.phase = "INSTRUCTIONS"

            elif self.phase == "GAME_OVER":
                self.reset_to_lobby()

            return True

    def _finalize_round_and_rankings(self):
        """
        Calculates scores across all questions in the round,
        updates player totals, computes rank movements,
        and saves secret score summaries for each player's mobile screen.
        """
        player_names = {pid: p["name"] for pid, p in self.players.items()}
        self.cached_reveal_data = self.current_game.get_reveal_data(player_names, self.config)

        # 1. Capture previous ranks before adding this round's points
        sorted_before = sorted(self.players.values(), key=lambda x: x["score"], reverse=True)
        prev_ranks = {p["id"]: idx + 1 for idx, p in enumerate(sorted_before)}

        # 2. Score changes for this round (summed across all X questions)
        round_deltas = self.cached_reveal_data.get("score_deltas", {})
        for pid, delta in round_deltas.items():
            if pid in self.players:
                self.players[pid]["score"] += delta

        # 3. Compute new ranks and rank changes (movement)
        sorted_after = sorted(self.players.values(), key=lambda x: x["score"], reverse=True)
        new_ranks = {p["id"]: idx + 1 for idx, p in enumerate(sorted_after)}

        self.last_round_rankings = []
        for p in sorted_after:
            pid = p["id"]
            p_rank = new_ranks[pid]
            p_prev = prev_ranks.get(pid, p_rank)
            rank_diff = p_prev - p_rank  # positive = moved UP, negative = moved DOWN

            if rank_diff > 0:
                change_disp = f"▲ {rank_diff}"
            elif rank_diff < 0:
                change_disp = f"▼ {abs(rank_diff)}"
            else:
                change_disp = "―"

            self.last_round_rankings.append({
                "id": pid,
                "name": p["name"],
                "rank": p_rank,
                "prev_rank": p_prev,
                "rank_change": rank_diff,
                "rank_change_display": change_disp,
                # Scores strictly hidden/classified on main host display
                "score_display": "█████ [CLASSIFIED]"
            })

        # 4. Prepare player-specific secret score summaries for mobile screens
        q_results = self.cached_reveal_data.get("questions", [])
        self.player_round_scores = {}
        for pid, p in self.players.items():
            p_round_delta = round_deltas.get(pid, 0)
            breakdown = []
            for q_item in q_results:
                q_num = q_item.get("question_number", 1)
                q_score = q_item.get("score_deltas", {}).get(pid, 0)
                breakdown.append({
                    "question_number": q_num,
                    "points": q_score,
                    "points_display": f"+{q_score} pts" if q_score > 0 else f"{q_score} pts"
                })

            p_rank = new_ranks.get(pid, 1)
            p_prev = prev_ranks.get(pid, p_rank)
            rank_diff = p_prev - p_rank
            if rank_diff > 0:
                change_disp = f"▲ {rank_diff}"
            elif rank_diff < 0:
                change_disp = f"▼ {abs(rank_diff)}"
            else:
                change_disp = "―"

            self.player_round_scores[pid] = {
                "round_score": p_round_delta,
                "round_score_display": f"+{p_round_delta} pts" if p_round_delta > 0 else f"{p_round_delta} pts",
                "total_score": p["score"],
                "total_score_display": f"{p['score']} pts",
                "rank": p_rank,
                "rank_change": rank_diff,
                "rank_change_display": change_disp,
                "breakdown": breakdown
            }

        # 5. Archive human player responses for bonus round from ALL questions
        if hasattr(self.current_game, "questions"):
            for q in self.current_game.questions:
                for sub in q["submissions"].values():
                    if not sub["is_bot"] and sub["author_id"] in self.player_history:
                        self.player_history[sub["author_id"]].append({
                            "round_num": self.round_number,
                            "question_num": q["index"] + 1,
                            "game_title": self.current_game.title,
                            "prompt": q["prompt_data"].get("prompt_text", ""),
                            "response": sub["response"]
                        })

    def _finalize_bonus_round_and_rankings(self):
        """Finalize scores and ranks for the bonus round."""
        sorted_before = sorted(self.players.values(), key=lambda x: x["score"], reverse=True)
        prev_ranks = {p["id"]: idx + 1 for idx, p in enumerate(sorted_before)}

        deltas = self.cached_reveal_data.get("score_deltas", {})
        for pid, delta in deltas.items():
            if pid in self.players:
                self.players[pid]["score"] += delta

        sorted_after = sorted(self.players.values(), key=lambda x: x["score"], reverse=True)
        new_ranks = {p["id"]: idx + 1 for idx, p in enumerate(sorted_after)}

        self.last_round_rankings = []
        for p in sorted_after:
            pid = p["id"]
            p_rank = new_ranks[pid]
            p_prev = prev_ranks.get(pid, p_rank)
            rank_diff = p_prev - p_rank
            change_disp = f"▲ {rank_diff}" if rank_diff > 0 else (f"▼ {abs(rank_diff)}" if rank_diff < 0 else "―")

            self.last_round_rankings.append({
                "id": pid,
                "name": p["name"],
                "rank": p_rank,
                "prev_rank": p_prev,
                "rank_change": rank_diff,
                "rank_change_display": change_disp,
                "score_display": f"{p['score']} pts"
            })

            p_delta = deltas.get(pid, 0)
            self.player_round_scores[pid] = {
                "round_score": p_delta,
                "round_score_display": f"+{p_delta} pts" if p_delta > 0 else f"{p_delta} pts",
                "total_score": p["score"],
                "total_score_display": f"{p['score']} pts",
                "rank": p_rank,
                "rank_change": rank_diff,
                "rank_change_display": change_disp,
                "breakdown": []
            }

    # --- Player Action Handlers ---

    def handle_player_submission(self, player_id: str, response_text: Any, is_locked: bool = True, version: int = 0, question_index: Optional[int] = None) -> bool:
        with self.lock:
            if self.phase != "SUBMITTING" or not self.current_game:
                return False

            curr_idx = getattr(self.current_game, "current_prompt_index", 0)
            if question_index is not None and question_index != curr_idx:
                # Discard packet for an inactive prompt
                return False

            p_name = self.players.get(player_id, {}).get("name", "Unknown")
            ok = self.current_game.submit_player_response(
                player_id, p_name, response_text, is_locked=is_locked, version=version, question_index=curr_idx
            )
            
            # Auto-advance if all human players submitted AND locked in for THIS prompt
            if ok and is_locked and not self.is_paused and self.current_game.are_submissions_complete(list(self.players.keys()), question_index=curr_idx):
                self.next_phase(expected_phase="SUBMITTING")
            return ok

    def handle_player_vote(self, player_id: str, target_option_ids: Any, question_index: Optional[int] = None, is_locked: bool = True) -> bool:
        with self.lock:
            if not self.current_game:
                return False

            now = time.time()
            curr_idx = getattr(self.current_game, "current_vote_index", 0)

            # Normal case: during VOTING phase
            if self.phase == "VOTING":
                target_q_idx = curr_idx if question_index is None else question_index

                if target_q_idx == curr_idx:
                    ok = self.current_game.submit_vote(
                        player_id, target_option_ids, is_locked=is_locked, question_index=curr_idx
                    )
                    # Auto-advance if all human players voted AND locked in for THIS set
                    if ok and is_locked and not self.is_paused and self.current_game.are_votes_complete(list(self.players.keys()), question_index=curr_idx):
                        self.next_phase(expected_phase="VOTING")
                    return ok

                # Grace window: vote for previous question that transitioned within 3 seconds
                elif target_q_idx == curr_idx - 1 and (now - self.phase_start_time) < 3.0:
                    ok = self.current_game.submit_vote(
                        player_id, target_option_ids, is_locked=True, question_index=target_q_idx
                    )
                    return ok

                return False

            # Grace window: if phase just transitioned to REVEAL within 3 seconds, allow late arriving votes for final question
            elif self.phase == "REVEAL" and (now - self.phase_start_time) < 3.0:
                total_q = getattr(self.current_game, "questions_count", 1)
                target_q_idx = (total_q - 1) if question_index is None else question_index
                ok = self.current_game.submit_vote(
                    player_id, target_option_ids, is_locked=True, question_index=target_q_idx
                )
                if ok:
                    # Recalculate scores and reveal data since late vote was received
                    self._finalize_round_and_rankings()
                return ok

            return False

    def handle_bonus_guess(self, player_id: str, guesses: Dict[str, str]) -> bool:
        with self.lock:
            if self.phase != "BONUS" or not self.current_game:
                return False
            ok = self.current_game.submit_guesses(player_id, guesses)
            
            # Auto-advance if all human players guessed
            if ok and not self.is_paused and self.current_game.are_votes_complete(list(self.players.keys())):
                self.next_phase(expected_phase="BONUS")
            return ok

    # --- State Generation for Host and Players ---

    def get_host_state(self) -> Dict[str, Any]:
        """State payload for the main TV / host display."""
        is_game_over = (self.phase == "GAME_OVER")
        
        # In intermediate phases, scores remain classified/hidden from host!
        players_list = []
        if is_game_over:
            sorted_players = sorted(self.players.values(), key=lambda x: x["score"], reverse=True)
            for p in sorted_players:
                players_list.append({
                    "id": p["id"],
                    "name": p["name"],
                    "score": p["score"],
                    "score_display": f"{p['score']} pts"
                })
        else:
            # Preserves suspense - hidden scores
            for p in self.players.values():
                players_list.append({
                    "id": p["id"],
                    "name": p["name"],
                    "score": 0,
                    "score_display": "█████ [CLASSIFIED]"
                })

        max_votes = getattr(self.current_game, "max_votes_per_player", 1) if self.current_game else 1

        curr_prompt_idx = getattr(self.current_game, "current_prompt_index", 0) if self.current_game else 0
        curr_vote_idx = getattr(self.current_game, "current_vote_index", 0) if self.current_game else 0
        curr_rev_idx = getattr(self.current_game, "current_reveal_index", 0) if self.current_game else 0
        total_q = getattr(self.current_game, "questions_count", self.questions_per_minigame) if self.current_game else self.questions_per_minigame

        base_state = {
            "phase": self.phase,
            "is_paused": self.is_paused,
            "round_number": self.round_number,
            "total_rounds": len(self.game_sequence),
            "questions_per_minigame": self.questions_per_minigame,
            "players": players_list,
            "player_count": len(self.players),
            "local_ip": self.config.LOCAL_IP,
            "port": self.config.PORT,
            "join_url": f"http://{self.config.LOCAL_IP}:{self.config.PORT}/player",
            "scores_hidden": not is_game_over,
            "max_votes_per_player": max_votes,
            "time_remaining": self.current_time_remaining,
            "submission_timeout": self.current_submission_timeout,
            "voting_timeout": self.current_voting_timeout,
            "rankings": self.last_round_rankings,
            "question_info": {
                "current_prompt_index": curr_prompt_idx,
                "current_prompt_number": curr_prompt_idx + 1,
                "current_vote_index": curr_vote_idx,
                "current_vote_number": curr_vote_idx + 1,
                "current_reveal_index": curr_rev_idx,
                "current_reveal_number": curr_rev_idx + 1,
                "total_questions": total_q
            },
            "game_sequence": [
                {"key": k, "name": MINIGAME_REGISTRY[k]["name"], "is_bonus": MINIGAME_REGISTRY[k]["is_bonus"]}
                for k in self.game_sequence
            ],
            "available_games": [
                {"key": k, "name": v["name"], "description": v["description"], "is_bonus": v["is_bonus"]}
                for k, v in MINIGAME_REGISTRY.items()
            ]
        }

        if self.current_game:
            # Active prompt data depending on current phase
            active_prompt_data = {}
            if hasattr(self.current_game, "questions") and self.current_game.questions:
                if self.phase == "VOTING" and curr_vote_idx < len(self.current_game.questions):
                    active_prompt_data = self.current_game.questions[curr_vote_idx].get("prompt_data", {})
                elif curr_prompt_idx < len(self.current_game.questions):
                    active_prompt_data = self.current_game.questions[curr_prompt_idx].get("prompt_data", {})
            else:
                active_prompt_data = getattr(self.current_game, "prompt_data", {})

            base_state["game_info"] = {
                "id": self.current_game.game_id,
                "title": self.current_game.title,
                "instruction": self.current_game.instruction,
                "prompt_data": active_prompt_data
            }
            base_state["image_url"] = active_prompt_data.get("image_url", "")

        if self.phase == "INTRO":
            base_state["intro_text"] = self.get_intro_text()
            base_state["intro_timeout"] = getattr(self.config, "INTRO_TIMEOUT", 45)

        # Submissions status
        if self.phase == "SUBMITTING" and self.current_game:
            curr_idx = getattr(self.current_game, "current_prompt_index", 0)
            q = self.current_game.questions[curr_idx] if hasattr(self.current_game, "questions") and curr_idx < len(self.current_game.questions) else {}
            q_subs = q.get("submissions", {})
            locked_ids = {
                sub["author_id"] for sub in q_subs.values()
                if not sub["is_bot"] and sub.get("is_locked", False)
            }
            drafting_ids = {
                sub["author_id"] for sub in q_subs.values()
                if not sub["is_bot"] and not sub.get("is_locked", False)
            }
            base_state["submissions_status"] = [
                {
                    "name": p["name"],
                    "has_submitted": p["id"] in locked_ids,
                    "has_draft": p["id"] in drafting_ids
                }
                for p in self.players.values()
            ]

        # Voting status & anonymized options
        elif self.phase == "VOTING" and self.current_game:
            curr_idx = getattr(self.current_game, "current_vote_index", 0)
            q = self.current_game.questions[curr_idx] if hasattr(self.current_game, "questions") and curr_idx < len(self.current_game.questions) else {}
            voted_ids = set(q.get("votes", {}).keys())
            draft_ids = set(q.get("draft_votes", {}).keys())
            base_state["voting_status"] = [
                {
                    "name": p["name"],
                    "has_voted": p["id"] in voted_ids,
                    "has_draft": p["id"] in draft_ids and p["id"] not in voted_ids
                }
                for p in self.players.values()
            ]
            base_state["voting_options"] = self.current_game.get_voting_options(question_index=curr_idx)

        # Reveal status
        elif self.phase in ("REVEAL", "BONUS_REVEAL"):
            if self.phase == "REVEAL" and self.current_game and hasattr(self.current_game, "get_reveal_data"):
                player_names = {pid: p["name"] for pid, p in self.players.items()}
                self.cached_reveal_data = self.current_game.get_reveal_data(player_names, self.config)
            base_state["reveal_data"] = self.cached_reveal_data

        # Bonus matching status
        elif self.phase == "BONUS" and self.current_game:
            guessed_ids = set(self.current_game.player_guesses.keys())
            base_state["bonus_status"] = [
                {"name": p["name"], "has_guessed": p["id"] in guessed_ids}
                for p in self.players.values()
            ]
            base_state["dossiers"] = [
                {"label": d["label"], "items": d["items"]}
                for d in self.current_game.dossiers.values()
            ]

        # Winner podium on GAME_OVER
        elif self.phase == "GAME_OVER":
            sorted_all = sorted(self.players.values(), key=lambda x: x["score"], reverse=True)
            base_state["winner"] = sorted_all[0] if sorted_all else None

        return base_state

    def get_player_state(self, player_id: str) -> Dict[str, Any]:
        """State payload tailored for a specific player's phone."""
        player = self.players.get(player_id)
        if not player:
            return {"phase": "UNREGISTERED"}

        max_votes = getattr(self.current_game, "max_votes_per_player", 1) if self.current_game else 1

        curr_prompt_idx = getattr(self.current_game, "current_prompt_index", 0) if self.current_game else 0
        curr_vote_idx = getattr(self.current_game, "current_vote_index", 0) if self.current_game else 0
        curr_rev_idx = getattr(self.current_game, "current_reveal_index", 0) if self.current_game else 0
        total_q = getattr(self.current_game, "questions_count", self.questions_per_minigame) if self.current_game else self.questions_per_minigame

        # IMPORTANT: Player ALWAYS sees their own score on mobile screen!
        round_summary = self.player_round_scores.get(player_id)

        state = {
            "phase": self.phase,
            "is_paused": self.is_paused,
            "game_id": self.current_game.game_id if self.current_game else "",
            "player": {
                "id": player["id"],
                "name": player["name"],
                "score": player["score"],
                "score_display": f"{player['score']} pts"
            },
            "round_number": self.round_number,
            "time_remaining": self.current_time_remaining,
            "submission_timeout": self.current_submission_timeout,
            "voting_timeout": self.current_voting_timeout,
            "max_votes_per_player": max_votes,
            "round_summary": round_summary,
            "question_info": {
                "current_prompt_index": curr_prompt_idx,
                "current_prompt_number": curr_prompt_idx + 1,
                "current_vote_index": curr_vote_idx,
                "current_vote_number": curr_vote_idx + 1,
                "current_reveal_index": curr_rev_idx,
                "current_reveal_number": curr_rev_idx + 1,
                "total_questions": total_q
            }
        }

        if self.phase == "LOBBY":
            state["status_message"] = "You're in! Waiting for host to start the game..."

        elif self.phase == "INTRO":
            state["status_message"] = "Orientation briefing in progress on Host screen! Stand by for Round 1..."

        elif self.phase == "INSTRUCTIONS":
            state["title"] = self.current_game.title if self.current_game else ""
            state["instruction"] = self.current_game.instruction if self.current_game else ""
            state["status_message"] = f"Get ready to play! {total_q} prompts coming up!"

        elif self.phase == "SUBMITTING" and self.current_game:
            sub_id = f"sub_{player_id}"
            q = self.current_game.questions[curr_prompt_idx] if hasattr(self.current_game, "questions") and curr_prompt_idx < len(self.current_game.questions) else {}
            sub = q.get("submissions", {}).get(sub_id) if q else self.current_game.submissions.get(sub_id)
            has_submitted = sub.get("is_locked", False) if sub else False

            state["has_submitted"] = has_submitted
            state["question_index"] = curr_prompt_idx
            state["question_number"] = curr_prompt_idx + 1
            state["total_questions"] = total_q
            state["prompt"] = self.current_game.get_prompt_for_player(player_id, question_index=curr_prompt_idx)

            if sub and not has_submitted:
                state["draft"] = sub.get("response")
            if has_submitted:
                if curr_prompt_idx + 1 < total_q:
                    state["status_message"] = f"Prompt {curr_prompt_idx + 1} locked in! Waiting for next prompt..."
                else:
                    state["status_message"] = "Final response locked in! Get ready to vote..."

        elif self.phase == "VOTING" and self.current_game:
            q = self.current_game.questions[curr_vote_idx] if hasattr(self.current_game, "questions") and curr_vote_idx < len(self.current_game.questions) else {}
            has_voted = player_id in q.get("votes", {}) if q else player_id in self.current_game.votes

            prompt_data = q.get("prompt_data", {}) if q else getattr(self.current_game, "prompt_data", {})

            state["has_voted"] = has_voted
            state["question_index"] = curr_vote_idx
            state["question_number"] = curr_vote_idx + 1
            state["total_questions"] = total_q
            state["options"] = self.current_game.get_voting_options(voter_id=player_id, question_index=curr_vote_idx)
            state["prompt_text"] = prompt_data.get("prompt_text", "")
            state["prompt_data"] = prompt_data
            state["image_url"] = prompt_data.get("image_url", "")

            if has_voted:
                if curr_vote_idx + 1 < total_q:
                    state["status_message"] = f"Vote for Set {curr_vote_idx + 1} locked in! Next set coming up..."
                else:
                    state["status_message"] = "Final vote locked in! Watch the TV screen for the reveal!"
            else:
                draft_votes = q.get("draft_votes", {}).get(player_id, [])
                state["draft_vote_ids"] = draft_votes

        elif self.phase in ("REVEAL", "BONUS_REVEAL"):
            state["status_message"] = "Check your secret score below and look at the TV for the reveal!"

        elif self.phase == "SCOREBOARD":
            state["status_message"] = "Check your secret score below! Standings are on the TV."

        elif self.phase == "BONUS" and self.current_game:
            has_guessed = player_id in self.current_game.player_guesses
            state["has_guessed"] = has_guessed
            state["bonus_data"] = self.current_game.get_prompt_for_player(player_id)
            if has_guessed:
                state["status_message"] = "Dossier matches submitted! Look at the main screen..."

        elif self.phase == "GAME_OVER":
            state["status_message"] = "Game over! Check the main screen for the winner!"

        return state
