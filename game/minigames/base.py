import threading
import uuid
import random
from typing import Dict, Any, List, Union, Optional

class BaseMinigame:
    def __init__(self, game_id: str, title: str, instruction: str, bot_engine, bot_count: int = 1):
        self.game_id = game_id
        self.title = title
        self.instruction = instruction
        self.bot_engine = bot_engine
        self.bot_count = bot_count
        self.max_votes_per_player = 2 if bot_count >= 2 else 1

        self.prompt_data = {}  # Main prompt / image / details
        self.submissions: Dict[str, Dict[str, Any]] = {} # id -> submission dict
        self.votes: Dict[str, List[str]] = {} # voter_id -> list of target submission ids
        self.bot_ids: List[str] = []
        self._lock = threading.Lock()
        self._bot_thread: Optional[threading.Thread] = None

    def start_round(self, players: Dict[str, Any]):
        """
        Called when this minigame starts. Subclasses choose prompts immediately,
        and bot responses are generated in a background thread so the HTTP request
        returns instantly (< 5ms) without hanging the backend.
        """
        with self._lock:
            self.submissions.clear()
            self.votes.clear()
            self.bot_ids.clear()
            self.max_votes_per_player = 2 if self.bot_count >= 2 else 1
            self._select_prompt()

        # Start bot generation in the background during instructions/submission phase
        self._bot_thread = threading.Thread(target=self._safe_generate_bots, daemon=True)
        self._bot_thread.start()

    def _safe_generate_bots(self):
        """Generates bot responses safely in background, with fallback fallback guarantee."""
        try:
            self._generate_bots()
        except Exception as e:
            print(f"[{self.game_id}] Bot generation exception: {e}")
        finally:
            self.ensure_bot_fallbacks()

    def _get_fallback_response(self) -> Any:
        """Override in subclass to return a random fallback answer."""
        return "Ran out of time"

    def ensure_bot_fallbacks(self):
        """Guarantees that all required bot submissions exist before voting starts."""
        with self._lock:
            for i in range(self.bot_count):
                bot_id = f"bot_{i+1}"
                if bot_id not in self.bot_ids:
                    self.bot_ids.append(bot_id)
                sub_id = f"sub_{bot_id}"
                if sub_id not in self.submissions:
                    fallback_val = self._get_fallback_response()
                    if isinstance(fallback_val, str) and fallback_val:
                        fallback_val = fallback_val[0].upper() + fallback_val[1:]
                    elif isinstance(fallback_val, list):
                        fallback_val = [x[0].upper() + x[1:] if isinstance(x, str) and x else x for x in fallback_val]
                    self.submissions[sub_id] = {
                        "id": sub_id,
                        "author_id": bot_id,
                        "author_name": self.bot_engine.get_bot_display_name() if self.bot_engine else "Bot",
                        "is_bot": True,
                        "response": fallback_val,
                        "is_locked": True,
                        "version": 0
                    }

    def ensure_bots_ready(self, timeout: float = 2.0):
        """Wait for background bot generation thread to finish before voting."""
        if self._bot_thread and self._bot_thread.is_alive():
            self._bot_thread.join(timeout=timeout)
        self.ensure_bot_fallbacks()

    def _select_prompt(self):
        """Override in subclass to pick prompt."""
        raise NotImplementedError

    def _generate_bots(self):
        """Override in subclass to generate bot responses."""
        raise NotImplementedError

    def get_prompt_for_player(self, player_id: str) -> Dict[str, Any]:
        """
        Returns prompt payload sent to players (and displayed on host).
        """
        return {
            "game_id": self.game_id,
            "title": self.title,
            "instruction": self.instruction,
            **self.prompt_data
        }

    def submit_player_response(self, player_id: str, player_name: str, response_text: Any, is_locked: bool = True, version: int = 0) -> bool:
        """
        Record a player's submission or live draft.
        """
        with self._lock:
            submission_id = f"sub_{player_id}"
            existing = self.submissions.get(submission_id)
            if existing:
                # If already locked, do not overwrite with an unlocked draft
                if existing.get("is_locked", False) and not is_locked:
                    return False
                # If incoming version timestamp is older than existing version, discard out-of-order packet
                if version and existing.get("version", 0) > version:
                    return False

            self.submissions[submission_id] = {
                "id": submission_id,
                "author_id": player_id,
                "author_name": player_name,
                "is_bot": False,
                "response": response_text,
                "is_locked": is_locked,
                "version": version
            }
            return True

    def are_submissions_complete(self, active_player_ids: List[str]) -> bool:
        """
        Check if all human players have locked in their submissions.
        """
        with self._lock:
            locked_authors = {
                sub["author_id"] for sub in self.submissions.values()
                if not sub["is_bot"] and sub.get("is_locked", False)
            }
            return set(active_player_ids).issubset(locked_authors)

    def finalize_submissions(self, players: Dict[str, Any]):
        """
        Called when submitting phase times out. Locks all pending human drafts,
        or inserts a fallback placeholder if a player wrote nothing.
        """
        with self._lock:
            for pid, p in players.items():
                sub_id = f"sub_{pid}"
                sub = self.submissions.get(sub_id)
                if not sub:
                    self.submissions[sub_id] = {
                        "id": sub_id,
                        "author_id": pid,
                        "author_name": p["name"],
                        "is_bot": False,
                        "response": "[Out of time - Blank submission]",
                        "is_locked": True,
                        "version": 0
                    }
                elif not sub.get("is_locked", False):
                    resp = sub.get("response", "")
                    if isinstance(resp, str) and resp.strip():
                        sub["response"] = resp.strip()
                        sub["is_locked"] = True
                    elif isinstance(resp, list) and any(str(x).strip() for x in resp):
                        sub["is_locked"] = True
                    else:
                        sub["response"] = "[Out of time - Blank submission]"
                        sub["is_locked"] = True

    def get_voting_options(self, voter_id: str = None) -> List[Dict[str, Any]]:
        """
        Returns anonymized list of responses to vote on.
        Hides 'is_bot', 'author_id', and 'author_name'.
        """
        self.ensure_bots_ready(timeout=1.0)
        options = []
        with self._lock:
            for sub_id, sub in self.submissions.items():
                # A player shouldn't vote for their own submission
                if voter_id and sub.get("author_id") == voter_id:
                    continue
                options.append({
                    "id": sub_id,
                    "response": sub["response"],
                })
        random.seed(42)
        random.shuffle(options)
        return options

    def submit_vote(self, voter_id: str, target_option_ids: Union[str, List[str]]) -> bool:
        """
        Record a player's vote(s) on which submission(s) they believe are BOT(s).
        Supports either a single option ID or a list of option IDs.
        """
        if isinstance(target_option_ids, str):
            selected = [target_option_ids]
        elif isinstance(target_option_ids, list):
            selected = [str(x) for x in target_option_ids]
        else:
            return False

        valid_ids = [opt_id for opt_id in selected if opt_id in self.submissions]
        if not valid_ids:
            return False

        # Store up to max_votes_per_player
        self.votes[voter_id] = valid_ids[:self.max_votes_per_player]
        return True

    def are_votes_complete(self, active_player_ids: List[str]) -> bool:
        """
        Check if all human players have submitted their votes.
        """
        return set(active_player_ids).issubset(set(self.votes.keys()))

    def calculate_scores(self, config) -> Dict[str, Any]:
        """
        Calculates score changes for the round:
        - Voter gets POINTS_CORRECT_BOT (+100) per correctly identified bot.
        - Human author LOSES points (POINTS_MISTAKEN_FOR_BOT_PENALTY, -25) per vote cast
          against them by other humans who thought they were a bot!
        """
        score_deltas: Dict[str, int] = {}
        vote_breakdown: Dict[str, List[str]] = {sub_id: [] for sub_id in self.submissions}

        # Track who voted for what
        for voter_id, choice_list in self.votes.items():
            for sub_id in choice_list:
                if sub_id in vote_breakdown:
                    vote_breakdown[sub_id].append(voter_id)

        # 1. Award points to voters who correctly spotted a bot
        for voter_id, choice_list in self.votes.items():
            for sub_id in choice_list:
                target_sub = self.submissions.get(sub_id)
                if target_sub and target_sub["is_bot"]:
                    score_deltas[voter_id] = score_deltas.get(voter_id, 0) + config.POINTS_CORRECT_BOT

        # 2. Penalty for human players whose response was voted as a bot
        for sub_id, sub in self.submissions.items():
            if not sub["is_bot"]:
                human_author = sub["author_id"]
                tricked_count = len(vote_breakdown[sub_id])
                if tricked_count > 0:
                    penalty = tricked_count * config.POINTS_MISTAKEN_FOR_BOT_PENALTY
                    score_deltas[human_author] = score_deltas.get(human_author, 0) + penalty

        return {
            "score_deltas": score_deltas,
            "vote_breakdown": vote_breakdown
        }

    def get_reveal_data(self, player_names_map: Dict[str, str], config) -> Dict[str, Any]:
        """
        Returns data needed for the host reveal screen.
        Shows each submission, who voted for it, and whether it was a BOT or a HUMAN.
        CRITICAL: Never reveals which human player wrote which response!
        """
        scores_result = self.calculate_scores(config)
        vote_breakdown = scores_result["vote_breakdown"]
        score_deltas = scores_result["score_deltas"]

        reveal_cards = []
        for sub_id, sub in self.submissions.items():
            voters = vote_breakdown.get(sub_id, [])
            voter_names = [player_names_map.get(vid, "Unknown") for vid in voters]
            
            reveal_cards.append({
                "submission_id": sub_id,
                "response": sub["response"],
                "is_bot": sub["is_bot"],
                "label": "BOT" if sub["is_bot"] else "HUMAN",
                "bot_name": "BOT" if sub["is_bot"] else None,
                "voter_names": voter_names,
                "vote_count": len(voters)
            })

        return {
            "reveal_cards": reveal_cards,
            "score_deltas": score_deltas
        }
