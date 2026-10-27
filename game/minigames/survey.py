import os
import json
import random
from typing import Any, Dict, List, Optional
from game.minigames.base import BaseMinigame
from game.normalization import normalize_response

PROMPTS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "prompts", "survey.json"))

# Built-in fallbacks if data/prompts/survey.json is absent
DEFAULT_SURVEY_PROMPTS: List[str] = [
    "Name something people pretend to understand just to look smart.",
    "Name an excuse for being an hour late to work that would NOT work.",
    "Name something you should never do in a crowded elevator.",
    "Name a superpower that would also be very annoying.",
    "Name something you find at the bottom of a backpack or purse.",
    "Name something people always forget when going on vacation.",
    "Name something people do when they think no one is watching.",
    "Name a food that is great hot but completely disgusting cold.",
    "Name something you should never admit on a first date.",
    "Name a terrible gift to receive from your boss.",
    "Name something that feels like a crime, but is completely legal.",
    "Name a sound you never want to hear coming from your car while driving.",
]

def load_survey_prompts() -> List[str]:
    try:
        if os.path.exists(PROMPTS_FILE):
            with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data
    except Exception as e:
        print(f"[SurveySaysGame] Error loading {PROMPTS_FILE}: {e}")
    return DEFAULT_SURVEY_PROMPTS

SURVEY_PROMPTS = load_survey_prompts()

# Shared generic emergency 3-answer sets if Ollama is offline or times out
GENERIC_SURVEY_FALLBACKS = [
    ["Traffic", "Overslept", "Car trouble"],
    ["My phone", "Procrastination", "Snacks"],
    ["Awkward silence", "Forgetting names", "Spilling coffee"],
    ["House keys", "Wallet", "Phone charger"],
    ["Slow Wi-Fi", "Loud chewing", "Long lines"],
    ["Cold weather", "Alarm clock", "Monday mornings"]
]

class SurveySaysGame(BaseMinigame):
    def __init__(self, bot_engine, bot_count: int = 1, questions_count: int = 3):
        super().__init__(
            game_id="survey",
            title="Survey Says",
            instruction="Computers reason differently than humans because they don't have a human experience. Demonstrate your relatability as a human and answer these survey questions.",
            bot_engine=bot_engine,
            bot_count=bot_count,
            questions_count=questions_count
        )

    def _select_prompts(self):
        pool = list(load_survey_prompts())
        random.shuffle(pool)
        chosen_list = [pool[i % len(pool)] for i in range(self.questions_count)]

        self.questions = []
        for i, item in enumerate(chosen_list):
            if isinstance(item, str):
                question = item
                fallbacks = None
            else:
                question = item.get("question", "")
                fallbacks = item.get("fallbacks")

            self.questions.append({
                "index": i,
                "prompt_data": {
                    "type": "multi_field",
                    "prompt_text": question,
                    "field_count": 3,
                    "placeholders": ["Top Answer #1", "Top Answer #2", "Top Answer #3"]
                },
                "meta": {
                    "question": question,
                    "fallbacks": fallbacks
                },
                "submissions": {},
                "votes": {},
                "bot_ids": []
            })

    def _generate_bots(self):
        for q in self.questions:
            meta = q["meta"]
            for i in range(self.bot_count):
                bot_id = f"bot_{i+1}"
                bot_name = self.bot_engine.get_bot_display_name()
                if bot_id not in q["bot_ids"]:
                    q["bot_ids"].append(bot_id)

                answers = self.bot_engine.generate_survey_answers(
                    survey_prompt=meta["question"],
                    fallback_answers=meta.get("fallbacks")
                )

                sub_id = f"sub_{bot_id}"
                q["submissions"][sub_id] = {
                    "id": sub_id,
                    "author_id": bot_id,
                    "author_name": bot_name,
                    "is_bot": True,
                    "response": answers,  # List of 3 strings
                    "is_locked": True,
                    "version": 0
                }

    def _get_fallback_response_for_question(self, q: Dict[str, Any]) -> list:
        meta = q.get("meta", {})
        fallbacks = meta.get("fallbacks") if isinstance(meta, dict) else None
        if fallbacks and len(fallbacks) >= 3:
            return random.sample(fallbacks, 3)
        return list(random.choice(GENERIC_SURVEY_FALLBACKS))

    def _get_fallback_response(self) -> list:
        return list(random.choice(GENERIC_SURVEY_FALLBACKS))


    def submit_player_response(self, player_id: str, player_name: str, response_data: Any, is_locked: bool = True, version: int = 0, question_index: Optional[int] = None) -> bool:
        with self._lock:
            idx = self.current_prompt_index if question_index is None else question_index
            if not (0 <= idx < len(self.questions)):
                return False
            q = self.questions[idx]

            submission_id = f"sub_{player_id}"
            existing = q["submissions"].get(submission_id)
            if existing:
                if existing.get("is_locked", False) and not is_locked:
                    return False
                if version and existing.get("version", 0) > version:
                    return False

            if is_locked:
                if isinstance(response_data, str) and response_data.startswith("[") and response_data.endswith("]"):
                    stored_response = response_data
                elif isinstance(response_data, list):
                    cleaned = [normalize_response(str(x)) for x in response_data if str(x).strip()]
                    if cleaned:
                        while len(cleaned) < 3:
                            cleaned.append(f"Answer {len(cleaned)+1}")
                        stored_response = cleaned[:3]
                    else:
                        stored_response = "[Out of time - Blank submission]"
                elif isinstance(response_data, str):
                    cleaned = [normalize_response(x) for x in response_data.split("\n") if x.strip()]
                    if cleaned:
                        while len(cleaned) < 3:
                            cleaned.append(f"Answer {len(cleaned)+1}")
                        stored_response = cleaned[:3]
                    else:
                        stored_response = "[Out of time - Blank submission]"
                else:
                    stored_response = "[Out of time - Blank submission]"
            else:
                if isinstance(response_data, list):
                    stored_response = [str(x) for x in response_data]
                elif isinstance(response_data, str):
                    stored_response = [response_data, "", ""]
                else:
                    stored_response = ["", "", ""]

            q["submissions"][submission_id] = {
                "id": submission_id,
                "author_id": player_id,
                "author_name": player_name,
                "is_bot": False,
                "response": stored_response,
                "is_locked": is_locked,
                "version": version
            }
            return True

    def finalize_submissions(self, players: Dict[str, Any], question_index: Optional[int] = None):
        """
        Locks any in-progress survey drafts, padding partial answers up to 3,
        or uses blank submission placeholder if player typed nothing.
        """
        with self._lock:
            idx = self.current_prompt_index if question_index is None else question_index
            if not (0 <= idx < len(self.questions)):
                return
            q = self.questions[idx]

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
                    resp = sub.get("response", [])
                    cleaned = [normalize_response(str(x)) for x in resp if str(x).strip()] if isinstance(resp, list) else []
                    if cleaned:
                        while len(cleaned) < 3:
                            cleaned.append(f"Answer {len(cleaned)+1}")
                        sub["response"] = cleaned[:3]
                        sub["is_locked"] = True
                    else:
                        sub["response"] = "[Out of time - Blank submission]"
                        sub["is_locked"] = True
