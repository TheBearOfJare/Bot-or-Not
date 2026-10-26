import random
from typing import Dict, Any, List
from game.minigames.base import BaseMinigame

# Simple prompt strings for easy expansion
PUN_PROMPTS: List[str] = [
    "Why don't skeletons fight each other? Because...",
    "I told my suitcase there will be no vacation this year. Now...",
    "Parallel lines have so much in common. It's a shame...",
    "What do you call a fake noodle? An...",
    "Why did the scarecrow win an award? Because he was...",
    "I used to play piano by ear, but now I...",
    "Why did the tomato blush? Because...",
    "I'm reading a book on anti-gravity. It's impossible to...",
    "Why can't you trust stairs? Because...",
    "What do you call a sleeping dinosaur? A...",
    "Why did the golfer bring two pairs of pants? In case...",
    "I used to be a personal banker, but then I...",
    "Why did the bicycle fall over? Because...",
    "What do you call cheese that isn't yours? ...",
]

# Shared generic emergency fallbacks if Ollama is offline or times out
GENERIC_PUN_FALLBACKS = [
    "I have no idea honestly",
    "Nobody knows",
    "Too cheesy to say out loud",
    "They just gave up",
    "It seemed like a good idea at the time",
    "Ask again later",
    "It's a mystery to everyone"
]

class CompleteThePunGame(BaseMinigame):
    def __init__(self, bot_engine, bot_count: int = 1, questions_count: int = 3):
        super().__init__(
            game_id="pun",
            title="Complete the Pun",
            instruction="Computers struggle at being funny. Prove that you can do better.",
            bot_engine=bot_engine,
            bot_count=bot_count,
            questions_count=questions_count
        )

    def _select_prompts(self):
        pool = list(PUN_PROMPTS)
        random.shuffle(pool)
        chosen_list = [pool[i % len(pool)] for i in range(self.questions_count)]

        self.questions = []
        for i, item in enumerate(chosen_list):
            if isinstance(item, str):
                setup = item
                fallbacks = None
            else:
                setup = item.get("setup", "")
                fallbacks = item.get("fallbacks")

            self.questions.append({
                "index": i,
                "prompt_data": {
                    "type": "text",
                    "prompt_text": setup,
                    "placeholder": "Enter your punchline..."
                },
                "meta": {
                    "setup": setup,
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

                punchline = self.bot_engine.generate_pun_punchline(
                    pun_setup=meta["setup"],
                    fallback_answers=meta.get("fallbacks")
                )

                sub_id = f"sub_{bot_id}"
                q["submissions"][sub_id] = {
                    "id": sub_id,
                    "author_id": bot_id,
                    "author_name": bot_name,
                    "is_bot": True,
                    "response": punchline,
                    "is_locked": True,
                    "version": 0
                }

    def _get_fallback_response_for_question(self, q: Dict[str, Any]) -> str:
        meta = q.get("meta", {})
        fallbacks = meta.get("fallbacks") if isinstance(meta, dict) else None
        if fallbacks:
            chosen = random.choice(fallbacks)
            return chosen[0].upper() + chosen[1:] if chosen else ""
        return random.choice(GENERIC_PUN_FALLBACKS)

    def _get_fallback_response(self) -> str:
        return random.choice(GENERIC_PUN_FALLBACKS)

