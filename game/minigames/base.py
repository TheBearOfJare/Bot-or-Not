import threading
import uuid
import random
from typing import Dict, Any, List, Union, Optional
from game.normalization import normalize_response

class BaseMinigame:
    def __init__(self, game_id: str, title: str, instruction: str, bot_engine, bot_count: int = 1, questions_count: int = 3):
        self.game_id = game_id
        self.title = title
        self.instruction = instruction
        self.bot_engine = bot_engine
        self.bot_count = bot_count
        self.questions_count = max(1, questions_count)
        self.max_votes_per_player = 2 if bot_count >= 2 else 1

        self.current_prompt_index: int = 0
        self.current_vote_index: int = 0
        self.current_reveal_index: int = 0
        self._in_voting_phase: bool = False

        # List of question objects:
        # [{ "index": 0, "prompt_data": {...}, "submissions": {...}, "votes": {...}, "bot_ids": [...], "meta": {...} }]
        self.questions: List[Dict[str, Any]] = []

        self._lock = threading.RLock()
        self._bot_thread: Optional[threading.Thread] = None

    @property
    def prompt_data(self) -> Dict[str, Any]:
        """Backwards compatibility: returns current question's prompt_data."""
        with self._lock:
            idx = self.current_vote_index if self._in_voting_phase else self.current_prompt_index
            if 0 <= idx < len(self.questions):
                return self.questions[idx].get("prompt_data", {})
            return {}

    @property
    def submissions(self) -> Dict[str, Dict[str, Any]]:
        """Backwards compatibility: returns current question's submissions."""
        with self._lock:
            idx = self.current_vote_index if self._in_voting_phase else self.current_prompt_index
            if 0 <= idx < len(self.questions):
                return self.questions[idx].get("submissions", {})
            return {}

    @property
    def votes(self) -> Dict[str, List[str]]:
        """Backwards compatibility: returns current voting question's votes."""
        with self._lock:
            if 0 <= self.current_vote_index < len(self.questions):
                return self.questions[self.current_vote_index].get("votes", {})
            return {}

    @property
    def bot_ids(self) -> List[str]:
        with self._lock:
            if 0 <= self.current_prompt_index < len(self.questions):
                return self.questions[self.current_prompt_index].get("bot_ids", [])
            return []

    def start_round(self, players: Dict[str, Any]):
        """
        Called when this minigame starts. Subclasses choose prompts immediately,
        and bot responses are generated in a background thread so the HTTP request
        returns instantly (< 5ms) without hanging the backend.
        """
        with self._lock:
            self.current_prompt_index = 0
            self.current_vote_index = 0
            self.current_reveal_index = 0
            self._in_voting_phase = False
            self.max_votes_per_player = 2 if self.bot_count >= 2 else 1
            self.questions = []
            self._select_prompts()

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

    def _get_fallback_response_for_question(self, q: Dict[str, Any]) -> Any:
        """Override in subclass to return a random fallback answer for a specific question."""
        return self._get_fallback_response()

    def ensure_bot_fallbacks(self):
        """Guarantees that all required bot submissions exist before voting starts."""
        with self._lock:
            for q in self.questions:
                q_submissions = q["submissions"]
                q_bot_ids = q["bot_ids"]
                for i in range(self.bot_count):
                    bot_id = f"bot_{i+1}"
                    if bot_id not in q_bot_ids:
                        q_bot_ids.append(bot_id)
                    sub_id = f"sub_{bot_id}"
                    if sub_id not in q_submissions:
                        fallback_val = self._get_fallback_response_for_question(q)
                        if isinstance(fallback_val, str) and fallback_val:
                            fallback_val = fallback_val[0].upper() + fallback_val[1:]
                        elif isinstance(fallback_val, list):
                            fallback_val = [x[0].upper() + x[1:] if isinstance(x, str) and x else x for x in fallback_val]
                        q_submissions[sub_id] = {
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

    def _select_prompts(self):
        """Override in subclass to pick X prompts. Default calls _select_prompt once."""
        if hasattr(self, "_select_prompt"):
            self._select_prompt()

    def _generate_bots(self):
        """Override in subclass to generate bot responses for all questions."""
        raise NotImplementedError

    def get_prompt_for_player(self, player_id: str, question_index: Optional[int] = None) -> Dict[str, Any]:
        """
        Returns prompt payload sent to players (and displayed on host).
        """
        with self._lock:
            idx = self.current_prompt_index if question_index is None else question_index
            if 0 <= idx < len(self.questions):
                q = self.questions[idx]
                return {
                    "game_id": self.game_id,
                    "title": self.title,
                    "instruction": self.instruction,
                    "question_index": idx,
                    "question_number": idx + 1,
                    "total_questions": len(self.questions),
                    **q["prompt_data"]
                }
            return {
                "game_id": self.game_id,
                "title": self.title,
                "instruction": self.instruction,
                "question_index": 0,
                "question_number": 1,
                "total_questions": max(1, len(self.questions))
            }

    def submit_player_response(self, player_id: str, player_name: str, response_text: Any, is_locked: bool = True, version: int = 0, question_index: Optional[int] = None) -> bool:
        """
        Record a player's submission or live draft for a specific question.
        """
        with self._lock:
            idx = self.current_prompt_index if question_index is None else question_index
            if not (0 <= idx < len(self.questions)):
                return False
            q = self.questions[idx]
            submission_id = f"sub_{player_id}"
            existing = q["submissions"].get(submission_id)
            if existing:
                # If already locked, do not overwrite with an unlocked draft
                if existing.get("is_locked", False) and not is_locked:
                    return False
                # If incoming version timestamp is older than existing version, discard out-of-order packet
                if version and existing.get("version", 0) > version:
                    return False

            final_response = response_text
            if is_locked:
                setup = q.get("meta", {}).get("setup", "") or q.get("meta", {}).get("product", "") or ""
                final_response = normalize_response(response_text, strip_setup=setup)

            q["submissions"][submission_id] = {
                "id": submission_id,
                "author_id": player_id,
                "author_name": player_name,
                "is_bot": False,
                "response": final_response,
                "is_locked": is_locked,
                "version": version
            }
            return True

    def are_submissions_complete(self, active_player_ids: List[str], question_index: Optional[int] = None) -> bool:
        """
        Check if all human players have locked in their submissions for a question.
        """
        with self._lock:
            idx = self.current_prompt_index if question_index is None else question_index
            if not (0 <= idx < len(self.questions)):
                return False
            q = self.questions[idx]
            locked_authors = {
                sub["author_id"] for sub in q["submissions"].values()
                if not sub["is_bot"] and sub.get("is_locked", False)
            }
            return set(active_player_ids).issubset(locked_authors)

    def finalize_submissions(self, players: Dict[str, Any], question_index: Optional[int] = None):
        """
        Called when submitting phase times out. Locks all pending human drafts,
        or inserts a fallback placeholder if a player wrote nothing.
        """
        with self._lock:
            idx = self.current_prompt_index if question_index is None else question_index
            if not (0 <= idx < len(self.questions)):
                return
            q = self.questions[idx]
            setup = q.get("meta", {}).get("setup", "") or q.get("meta", {}).get("product", "") or ""
            for pid, p in players.items():
                sub_id = f"sub_{pid}"
                sub = q["submissions"].get(sub_id)
                if not sub:
                    q["submissions"][sub_id] = {
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
                        sub["response"] = normalize_response(resp.strip(), strip_setup=setup)
                        sub["is_locked"] = True
                    elif isinstance(resp, list) and any(str(x).strip() for x in resp):
                        sub["response"] = normalize_response(resp, strip_setup=setup)
                        sub["is_locked"] = True
                    else:
                        sub["response"] = "[Out of time - Blank submission]"
                        sub["is_locked"] = True

    def get_voting_options(self, voter_id: str = None, question_index: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Returns anonymized list of responses to vote on for a specific question.
        Hides 'is_bot', 'author_id', and 'author_name'.
        """
        self.ensure_bots_ready(timeout=1.0)
        options = []
        with self._lock:
            idx = self.current_vote_index if question_index is None else question_index
            if not (0 <= idx < len(self.questions)):
                return []
            q = self.questions[idx]
            for sub_id, sub in q["submissions"].items():
                # A player shouldn't vote for their own submission
                if voter_id and sub.get("author_id") == voter_id:
                    continue
                options.append({
                    "id": sub_id,
                    "response": sub["response"],
                })
        rnd = random.Random(42 + idx)
        rnd.shuffle(options)
        return options

    def submit_vote(self, voter_id: str, target_option_ids: Union[str, List[str]], is_locked: bool = True, question_index: Optional[int] = None) -> bool:
        """
        Record a player's vote(s) on which submission(s) they believe are BOT(s) for a question.
        Supports both locked votes (final) and draft votes (in-progress selections).
        """
        with self._lock:
            idx = self.current_vote_index if question_index is None else question_index
            if not (0 <= idx < len(self.questions)):
                return False
            q = self.questions[idx]
            q.setdefault("votes", {})
            drafts = q.setdefault("draft_votes", {})

            if isinstance(target_option_ids, str):
                selected = [target_option_ids]
            elif isinstance(target_option_ids, list):
                selected = [str(x) for x in target_option_ids]
            else:
                selected = []

            valid_ids = [
                opt_id for opt_id in selected 
                if opt_id in q["submissions"] and q["submissions"][opt_id].get("author_id") != voter_id
            ]

            if is_locked:
                if not valid_ids:
                    return False
                # Store up to max_votes_per_player
                q["votes"][voter_id] = valid_ids[:self.max_votes_per_player]
                drafts.pop(voter_id, None)
                return True
            else:
                # In draft mode, do not downgrade if already locked in
                if voter_id in q["votes"]:
                    return True
                drafts[voter_id] = valid_ids[:self.max_votes_per_player]
                return True

    def finalize_votes(self, players: Dict[str, Any], question_index: Optional[int] = None):
        """
        Called when voting phase times out or phase advances.
        Locks all pending human draft votes into actual votes so unlocked selections are not lost.
        """
        with self._lock:
            idx = self.current_vote_index if question_index is None else question_index
            if not (0 <= idx < len(self.questions)):
                return
            q = self.questions[idx]
            q.setdefault("votes", {})
            drafts = q.setdefault("draft_votes", {})

            for pid in players:
                # If player already locked in, leave it
                if pid in q["votes"]:
                    continue

                player_drafts = drafts.get(pid, [])
                valid = [
                    oid for oid in player_drafts 
                    if oid in q["submissions"] and q["submissions"][oid].get("author_id") != pid
                ]
                if valid:
                    q["votes"][pid] = valid[:self.max_votes_per_player]

    def are_votes_complete(self, active_player_ids: List[str], question_index: Optional[int] = None) -> bool:
        """
        Check if all human players have submitted their votes for a question.
        """
        with self._lock:
            idx = self.current_vote_index if question_index is None else question_index
            if not (0 <= idx < len(self.questions)):
                return False
            q = self.questions[idx]
            return set(active_player_ids).issubset(set(q.get("votes", {}).keys()))

    def calculate_scores(self, config) -> Dict[str, Any]:
        """
        Calculates score changes across ALL questions for this minigame:
        - Voter gets POINTS_CORRECT_BOT (+100) per correctly identified bot.
        - Human author LOSES points (POINTS_MISTAKEN_FOR_BOT_PENALTY, -25) per vote cast
          against them by other humans who thought they were a bot!
        """
        with self._lock:
            total_score_deltas: Dict[str, int] = {}
            per_question_results = []

            for idx, q in enumerate(self.questions):
                q_score_deltas: Dict[str, int] = {}
                q_vote_breakdown: Dict[str, List[str]] = {sub_id: [] for sub_id in q["submissions"]}

                # Track who voted for what
                for voter_id, choice_list in q["votes"].items():
                    for sub_id in choice_list:
                        if sub_id in q_vote_breakdown:
                            q_vote_breakdown[sub_id].append(voter_id)

                # 1. Award points to voters who correctly spotted a bot
                for voter_id, choice_list in q["votes"].items():
                    for sub_id in choice_list:
                        target_sub = q["submissions"].get(sub_id)
                        if target_sub and target_sub["is_bot"]:
                            q_score_deltas[voter_id] = q_score_deltas.get(voter_id, 0) + config.POINTS_CORRECT_BOT

                # 2. Penalty for human players whose response was voted as a bot
                for sub_id, sub in q["submissions"].items():
                    if not sub["is_bot"]:
                        human_author = sub["author_id"]
                        tricked_count = len(q_vote_breakdown[sub_id])
                        if tricked_count > 0:
                            penalty = tricked_count * config.POINTS_MISTAKEN_FOR_BOT_PENALTY
                            q_score_deltas[human_author] = q_score_deltas.get(human_author, 0) + penalty

                # Accumulate into total score deltas
                for pid, delta in q_score_deltas.items():
                    total_score_deltas[pid] = total_score_deltas.get(pid, 0) + delta

                per_question_results.append({
                    "question_index": idx,
                    "prompt_data": q["prompt_data"],
                    "score_deltas": q_score_deltas,
                    "vote_breakdown": q_vote_breakdown
                })

            return {
                "score_deltas": total_score_deltas,
                "per_question_results": per_question_results
            }

    def get_reveal_data(self, player_names_map: Dict[str, str], config) -> Dict[str, Any]:
        """
        Returns data needed for the host reveal screen.
        Provides reveal cards per question and total score deltas.
        """
        with self._lock:
            scores_result = self.calculate_scores(config)
            total_deltas = scores_result["score_deltas"]
            per_q = scores_result["per_question_results"]

            questions_reveal = []
            for item in per_q:
                q_idx = item["question_index"]
                q = self.questions[q_idx]
                vote_breakdown = item["vote_breakdown"]
                q_deltas = item["score_deltas"]

                reveal_cards = []
                for sub_id, sub in q["submissions"].items():
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

                # Sort: Humans first (0), then Bots (1); internally lowest to highest votes
                reveal_cards.sort(key=lambda c: (1 if c["is_bot"] else 0, c["vote_count"]))

                questions_reveal.append({
                    "question_index": q_idx,
                    "question_number": q_idx + 1,
                    "total_questions": len(self.questions),
                    "prompt_data": q["prompt_data"],
                    "reveal_cards": reveal_cards,
                    "score_deltas": q_deltas
                })

            rev_idx = min(self.current_reveal_index, len(questions_reveal) - 1) if questions_reveal else 0
            active_cards = questions_reveal[rev_idx]["reveal_cards"] if questions_reveal else []

            return {
                "score_deltas": total_deltas,
                "questions": questions_reveal,
                "current_question_index": rev_idx,
                "current_question_number": rev_idx + 1,
                "total_questions": len(questions_reveal),
                "reveal_cards": active_cards,
                "active_prompt_data": questions_reveal[rev_idx]["prompt_data"] if questions_reveal else {}
            }
