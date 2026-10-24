import random
from typing import Any
from game.minigames.base import BaseMinigame

SURVEY_PROMPTS = [
    {
        "question": "Name something people pretend to understand just to look smart.",
        "fallbacks": [
            "Wine notes / tannins",
            "Modern abstract art",
            "Cryptocurrency and blockchain",
            "Quantum physics",
            "The plot of Inception",
            "Stock market options"
        ]
    },
    {
        "question": "Name a terrible excuse for being an hour late to work.",
        "fallbacks": [
            "My cat looked too comfortable sleeping on my legs",
            "I forgot which day of the week it was",
            "A flock of aggressive geese blocked my driveway",
            "Alien abduction took longer than expected",
            "I fell into a TikTok rabbit hole about competitive cheese rolling",
            "My GPS had an emotional breakdown"
        ]
    },
    {
        "question": "Name something you should never do in a crowded elevator.",
        "fallbacks": [
            "Eat a pungent egg salad sandwich with onions",
            "Face backwards and stare deeply into strangers' eyes",
            "Start vigorously stretching or doing jumping jacks",
            "Announce 'I bet you're wondering why I gathered you here'",
            "Press every single floor button while giggling",
            "Take off your shoes and socks"
        ]
    },
    {
        "question": "Name a useless superpower that would actually be very annoying.",
        "fallbacks": [
            "Hearing everyone's Wi-Fi passwords in your head",
            "Sweating warm apple juice",
            "Invisibility, but only when nobody is looking at you",
            "Attracting stray pigeons wherever you walk",
            "Speaking in reverse whenever you're nervous",
            "Instant telekinesis, but it only moves paperclips 1 inch"
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
                "response": answers  # List of 3 strings
            }

    def _get_fallback_response(self) -> list:
        if self.chosen_prompt and self.chosen_prompt.get("fallbacks"):
            fallbacks = self.chosen_prompt["fallbacks"]
            return random.sample(fallbacks, min(3, len(fallbacks)))
        return ["My algorithm", "Syntax errors", "Rebooting the server"]

    def submit_player_response(self, player_id: str, player_name: str, response_data: Any) -> bool:
        # response_data can be a list of 3 strings or a single comma-separated string
        if isinstance(response_data, list):
            cleaned = [str(x).strip() for x in response_data if str(x).strip()]
        elif isinstance(response_data, str):
            cleaned = [x.strip() for x in response_data.split("\n") if x.strip()]
        else:
            cleaned = ["Response 1", "Response 2", "Response 3"]
        
        while len(cleaned) < 3:
            cleaned.append(f"Answer {len(cleaned)+1}")

        with self._lock:
            submission_id = f"sub_{player_id}"
            self.submissions[submission_id] = {
                "id": submission_id,
                "author_id": player_id,
                "author_name": player_name,
                "is_bot": False,
                "response": cleaned[:3]
            }
            return True
