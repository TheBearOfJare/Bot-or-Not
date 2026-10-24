import random
from typing import Any, Dict, List
from game.minigames.base import BaseMinigame

SURVEY_PROMPTS = [
    {
        "question": "Name something people pretend to understand just to look smart.",
        "fallbacks": [
            "Wine tasting",
            "Modern art",
            "Crypto",
            "Quantum physics",
            "Stock market",
            "Philosophy",
            "Classical music",
            "Taxes"
        ]
    },
    {
        "question": "Name a terrible excuse for being an hour late to work.",
        "fallbacks": [
            "Traffic",
            "Overslept",
            "Alarm didn't go off",
            "Flat tire",
            "Forgot my keys",
            "Car wouldn't start",
            "Spilled coffee",
            "Lost track of time"
        ]
    },
    {
        "question": "Name something you should never do in a crowded elevator.",
        "fallbacks": [
            "Fart",
            "Stare into someone's eyes",
            "Eat smelly food",
            "Talk loudly on phone",
            "Press all the buttons",
            "Cough without covering",
            "Stand way too close",
            "Sing loudly"
        ]
    },
    {
        "question": "Name a useless superpower that would actually be very annoying.",
        "fallbacks": [
            "Reading your own mind",
            "Attracting pigeons",
            "Tasting colors",
            "Invisibility only when alone",
            "Sweating juice",
            "Floating one inch",
            "Super smelling",
            "Glowing in broad daylight"
        ]
    }
]

class SurveySaysGame(BaseMinigame):
    def __init__(self, bot_engine, bot_count: int = 1):
        super().__init__(
            game_id="survey",
            title="Survey Says",
            instruction="Family Feud style! Give your top 3 answers to the prompt.",
            bot_engine=bot_engine,
            bot_count=bot_count
        )
        self.chosen_prompt = None

    def _select_prompt(self):
        self.chosen_prompt = random.choice(SURVEY_PROMPTS)
        self.prompt_data = {
            "type": "multi_field",
            "prompt_text": self.chosen_prompt["question"],
            "field_count": 3,
            "placeholders": ["Top Answer #1", "Top Answer #2", "Top Answer #3"]
        }

    def _generate_bots(self):
        for i in range(self.bot_count):
            bot_id = f"bot_{i+1}"
            bot_name = self.bot_engine.get_bot_display_name()
            self.bot_ids.append(bot_id)
            
            answers = self.bot_engine.generate_survey_answers(
                survey_prompt=self.chosen_prompt["question"],
                fallback_answers=self.chosen_prompt["fallbacks"]
            )
            
            sub_id = f"sub_{bot_id}"
            self.submissions[sub_id] = {
                "id": sub_id,
                "author_id": bot_id,
                "author_name": bot_name,
                "is_bot": True,
                "response": answers,  # List of 3 strings
                "is_locked": True,
                "version": 0
            }

    def _get_fallback_response(self) -> list:
        if self.chosen_prompt and self.chosen_prompt.get("fallbacks"):
            fallbacks = self.chosen_prompt["fallbacks"]
            return random.sample(fallbacks, min(3, len(fallbacks)))
        return ["Traffic", "Overslept", "Car trouble"]

    def submit_player_response(self, player_id: str, player_name: str, response_data: Any, is_locked: bool = True, version: int = 0) -> bool:
        with self._lock:
            submission_id = f"sub_{player_id}"
            existing = self.submissions.get(submission_id)
            if existing:
                if existing.get("is_locked", False) and not is_locked:
                    return False
                if version and existing.get("version", 0) > version:
                    return False

            if is_locked:
                # response_data can be a list of 3 strings or a single comma-separated string
                if isinstance(response_data, list):
                    cleaned = [str(x).strip() for x in response_data if str(x).strip()]
                elif isinstance(response_data, str):
                    cleaned = [x.strip() for x in response_data.split("\n") if x.strip()]
                else:
                    cleaned = ["Response 1", "Response 2", "Response 3"]
                
                while len(cleaned) < 3:
                    cleaned.append(f"Answer {len(cleaned)+1}")
                stored_response = cleaned[:3]
            else:
                # Live draft - preserve input state as list of strings
                if isinstance(response_data, list):
                    stored_response = [str(x) for x in response_data]
                elif isinstance(response_data, str):
                    stored_response = [response_data, "", ""]
                else:
                    stored_response = ["", "", ""]

            self.submissions[submission_id] = {
                "id": submission_id,
                "author_id": player_id,
                "author_name": player_name,
                "is_bot": False,
                "response": stored_response,
                "is_locked": is_locked,
                "version": version
            }
            return True

    def finalize_submissions(self, players: Dict[str, Any]):
        """
        Locks any in-progress survey drafts, padding partial answers up to 3,
        or uses fallbacks if player typed nothing.
        """
        with self._lock:
            for pid, p in players.items():
                sub_id = f"sub_{pid}"
                sub = self.submissions.get(sub_id)
                if not sub:
                    fallbacks = self._get_fallback_response()
                    self.submissions[sub_id] = {
                        "id": sub_id,
                        "author_id": pid,
                        "author_name": p["name"],
                        "is_bot": False,
                        "response": fallbacks,
                        "is_locked": True,
                        "version": 0
                    }
                elif not sub.get("is_locked", False):
                    resp = sub.get("response", [])
                    cleaned = [str(x).strip() for x in resp if str(x).strip()] if isinstance(resp, list) else []
                    if cleaned:
                        while len(cleaned) < 3:
                            cleaned.append(f"Answer {len(cleaned)+1}")
                        sub["response"] = cleaned[:3]
                        sub["is_locked"] = True
                    else:
                        sub["response"] = self._get_fallback_response()
                        sub["is_locked"] = True
