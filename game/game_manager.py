import uuid
import time
import threading
from typing import Dict, Any, List, Optional
from config import Config
from game.bot_engine import BotEngine
from game.minigames import MINIGAME_REGISTRY, create_minigame_instance

class GameManager:
    def __init__(self, config=Config):
        self.config = config
        self.bot_engine = BotEngine(config.OLLAMA_URL, config.OLLAMA_MODEL)
        self.lock = threading.RLock()
        
        self.players: Dict[str, Dict[str, Any]] = {}
        # player_id -> list of { "round": int, "game_title": str, "prompt": str, "response": Any }
        self.player_history: Dict[str, List[Dict[str, Any]]] = {}
        
        # Sequence of minigames to play
        self.game_sequence: List[str] = list(self.config.DEFAULT_GAME_SEQUENCE)
        self.current_sequence_index: int = -1
        
        # Current phase: LOBBY, INSTRUCTIONS, SUBMITTING, VOTING, REVEAL, SCOREBOARD, BONUS, BONUS_REVEAL, GAME_OVER
        self.phase: str = "LOBBY"
        self.current_game = None
        self.round_number: int = 0
        
        # Phase start timestamp (for timer progress on host/client)
        self.phase_start_time: float = time.time()
        
        # Cached reveal data for the current round
        self.cached_reveal_data: Optional[Dict[str, Any]] = None

    def reset_to_lobby(self, clear_players: bool = False):
        """Reset game state back to lobby."""
        with self.lock:
            self.phase = "LOBBY"
            self.current_sequence_index = -1
            self.current_game = None
            self.round_number = 0
            self.cached_reveal_data = None
            self.player_history.clear()
            if clear_players:
                self.players.clear()
            else:
                for p in self.players.values():
                    p["score"] = 0
                    self.player_history[p["id"]] = []

    def set_game_sequence(self, sequence: List[str]):
        """Allow host to customize which minigames are played and in what order."""
        with self.lock:
            valid_keys = [k for k in sequence if k in MINIGAME_REGISTRY]
            if valid_keys:
                self.game_sequence = valid_keys

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

    def remove_player(self, player_id: str):
        with self.lock:
            if player_id in self.players:
                del self.players[player_id]
            if player_id in self.player_history:
                del self.player_history[player_id]

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
            self._load_current_game()
            self.phase = "INSTRUCTIONS"
            self.phase_start_time = time.time()
            print(f"[GameManager] Match started successfully! Round {self.round_number}: {self.current_game.title}")
            return True

    def _load_current_game(self):
        game_key = self.game_sequence[self.current_sequence_index]
        # Dynamic bots: 2 bots if 5+ players, else 1
        bot_count = 2 if len(self.players) >= self.config.LARGE_LOBBY_THRESHOLD else 1
        
        self.current_game = create_minigame_instance(
            game_key=game_key,
            bot_engine=self.bot_engine,
            bot_count=bot_count
        )
        self.cached_reveal_data = None

        if game_key == "bonus":
            self.current_game.start_round(self.players, self.player_history)
        else:
            self.current_game.start_round(self.players)

    def next_phase(self, expected_phase: Optional[str] = None) -> bool:
        """
        Advances game state machine to the next natural phase.
        Guarded by lock and expected_phase to prevent race condition skips.
        """
        with self.lock:
            if expected_phase and self.phase != expected_phase:
                print(f"[GameManager] next_phase ignored: expected '{expected_phase}', but current phase is '{self.phase}'")
                return False

            now = time.time()
            self.phase_start_time = now

            if self.phase == "LOBBY":
                return self.start_game()

            elif self.phase == "INSTRUCTIONS":
                if self.current_game and getattr(self.current_game, "game_id", None) == "bonus":
                    self.phase = "BONUS"
                else:
                    self.phase = "SUBMITTING"

            elif self.phase == "SUBMITTING":
                # Finalize any pending drafts or timeout placeholders
                if self.current_game and hasattr(self.current_game, "submissions"):
                    if hasattr(self.current_game, "finalize_submissions"):
                        self.current_game.finalize_submissions(self.players)
                    else:
                        for pid, p in self.players.items():
                            sub_id = f"sub_{pid}"
                            if sub_id not in self.current_game.submissions:
                                self.current_game.submit_player_response(
                                    pid, p["name"], "[Out of time - Blank submission]", is_locked=True
                                )
                # Ensure bots are ready before entering VOTING!
                if self.current_game and hasattr(self.current_game, "ensure_bots_ready"):
                    self.current_game.ensure_bots_ready(timeout=2.0)
                self.phase = "VOTING"

            elif self.phase == "VOTING":
                # Calculate scores and cache reveal data
                player_names = {pid: p["name"] for pid, p in self.players.items()}
                self.cached_reveal_data = self.current_game.get_reveal_data(player_names, self.config)
                
                # Apply score changes behind the scenes (scores remain classified/hidden from players)
                deltas = self.cached_reveal_data.get("score_deltas", {})
                for pid, delta in deltas.items():
                    if pid in self.players:
                        self.players[pid]["score"] += delta

                # Archive player responses for the bonus round
                for sub in self.current_game.submissions.values():
                    if not sub["is_bot"] and sub["author_id"] in self.player_history:
                        self.player_history[sub["author_id"]].append({
                            "round_num": self.round_number,
                            "game_title": self.current_game.title,
                            "prompt": self.current_game.prompt_data.get("prompt_text", ""),
                            "response": sub["response"]
                        })

                self.phase = "REVEAL"

            elif self.phase == "REVEAL":
                self.phase = "SCOREBOARD"

            elif self.phase == "BONUS":
                # Tally bonus round
                player_names = {pid: p["name"] for pid, p in self.players.items()}
                self.cached_reveal_data = self.current_game.get_reveal_data(player_names, self.config)
                deltas = self.cached_reveal_data.get("score_deltas", {})
                for pid, delta in deltas.items():
                    if pid in self.players:
                        self.players[pid]["score"] += delta
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

    # --- Player Action Handlers ---

    def handle_player_submission(self, player_id: str, response_text: Any, is_locked: bool = True, version: int = 0) -> bool:
        with self.lock:
            if self.phase != "SUBMITTING" or not self.current_game:
                return False
            p_name = self.players.get(player_id, {}).get("name", "Unknown")
            ok = self.current_game.submit_player_response(
                player_id, p_name, response_text, is_locked=is_locked, version=version
            )
            
            # Auto-advance if all human players submitted AND locked in
            if ok and is_locked and self.current_game.are_submissions_complete(list(self.players.keys())):
                self.next_phase(expected_phase="SUBMITTING")
            return ok

    def handle_player_vote(self, player_id: str, target_option_ids: Any) -> bool:
        with self.lock:
            if self.phase != "VOTING" or not self.current_game:
                return False
            ok = self.current_game.submit_vote(player_id, target_option_ids)
            
            # Auto-advance if all human players voted
            if ok and self.current_game.are_votes_complete(list(self.players.keys())):
                self.next_phase(expected_phase="VOTING")
            return ok

    def handle_bonus_guess(self, player_id: str, guesses: Dict[str, str]) -> bool:
        with self.lock:
            if self.phase != "BONUS" or not self.current_game:
                return False
            ok = self.current_game.submit_guesses(player_id, guesses)
            
            # Auto-advance if all human players guessed
            if ok and self.current_game.are_votes_complete(list(self.players.keys())):
                self.next_phase(expected_phase="BONUS")
            return ok

    # --- State Generation for Host and Players ---

    def get_host_state(self) -> Dict[str, Any]:
        """State payload for the main TV / host display."""
        is_game_over = (self.phase == "GAME_OVER")
        
        # In intermediate phases, scores and ranks are classified!
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

        base_state = {
            "phase": self.phase,
            "round_number": self.round_number,
            "total_rounds": len(self.game_sequence),
            "players": players_list,
            "player_count": len(self.players),
            "local_ip": self.config.LOCAL_IP,
            "port": self.config.PORT,
            "join_url": f"http://{self.config.LOCAL_IP}:{self.config.PORT}/player",
            "scores_hidden": not is_game_over,
            "max_votes_per_player": max_votes,
            "submission_timeout": self.config.SUBMISSION_TIMEOUT,
            "voting_timeout": self.config.VOTING_TIMEOUT,
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
            base_state["game_info"] = {
                "id": self.current_game.game_id,
                "title": self.current_game.title,
                "instruction": self.current_game.instruction,
                "prompt_data": getattr(self.current_game, "prompt_data", {})
            }

        # Submissions status
        if self.phase == "SUBMITTING" and self.current_game:
            locked_ids = {
                sub["author_id"] for sub in self.current_game.submissions.values()
                if not sub["is_bot"] and sub.get("is_locked", False)
            }
            drafting_ids = {
                sub["author_id"] for sub in self.current_game.submissions.values()
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
            voted_ids = set(self.current_game.votes.keys())
            base_state["voting_status"] = [
                {"name": p["name"], "has_voted": p["id"] in voted_ids}
                for p in self.players.values()
            ]
            base_state["voting_options"] = self.current_game.get_voting_options()

        # Reveal status
        elif self.phase in ("REVEAL", "BONUS_REVEAL"):
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

        is_game_over = (self.phase == "GAME_OVER")
        max_votes = getattr(self.current_game, "max_votes_per_player", 1) if self.current_game else 1

        state = {
            "phase": self.phase,
            "player": {
                "id": player["id"],
                "name": player["name"],
                "score": player["score"] if is_game_over else None,
                "score_display": f"{player['score']} pts" if is_game_over else "Encrypted 🔒"
            },
            "round_number": self.round_number,
            "submission_timeout": self.config.SUBMISSION_TIMEOUT,
            "voting_timeout": self.config.VOTING_TIMEOUT,
            "max_votes_per_player": max_votes
        }

        if self.phase == "LOBBY":
            state["status_message"] = "You're in! Waiting for host to start the game..."

        elif self.phase == "INSTRUCTIONS":
            state["title"] = self.current_game.title if self.current_game else ""
            state["instruction"] = self.current_game.instruction if self.current_game else ""
            state["status_message"] = "Get ready to play!"

        elif self.phase == "SUBMITTING" and self.current_game:
            sub_id = f"sub_{player_id}"
            sub = self.current_game.submissions.get(sub_id)
            has_submitted = sub.get("is_locked", False) if sub else False
            state["has_submitted"] = has_submitted
            state["prompt"] = self.current_game.get_prompt_for_player(player_id)
            if sub and not has_submitted:
                state["draft"] = sub.get("response")
            if has_submitted:
                state["status_message"] = "Response submitted! Waiting for timer / others..."

        elif self.phase == "VOTING" and self.current_game:
            has_voted = player_id in self.current_game.votes
            state["has_voted"] = has_voted
            state["options"] = self.current_game.get_voting_options(voter_id=player_id)
            state["prompt_text"] = self.current_game.prompt_data.get("prompt_text", "")
            if has_voted:
                state["status_message"] = "Vote locked in! Look at the main TV screen..."

        elif self.phase in ("REVEAL", "BONUS_REVEAL"):
            state["status_message"] = "Check the TV screen for the reveal!"

        elif self.phase == "SCOREBOARD":
            state["status_message"] = "Scores are classified! Next round coming up..."

        elif self.phase == "BONUS" and self.current_game:
            has_guessed = player_id in self.current_game.player_guesses
            state["has_guessed"] = has_guessed
            state["bonus_data"] = self.current_game.get_prompt_for_player(player_id)
            if has_guessed:
                state["status_message"] = "Dossier matches submitted! Look at the main screen..."

        elif self.phase == "GAME_OVER":
            state["status_message"] = "Game over! Check the main screen for the winner!"

        return state
