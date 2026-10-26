import os
import json
import random
from typing import Dict, Any, List
from game.minigames.base import BaseMinigame

PROMPTS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "prompts", "pun.json"))

# Built-in fallbacks if data/prompts/pun.json is absent
DEFAULT_PUN_PROMPTS: List[str] = [
    "The secret reason Dracula stopped drinking blood is because...",
    "I tried dating a time traveler, but our relationship...",
    "The worst slogan for a cemetery would definitely be: '...'",
    "The real reason the Titanic sank was actually...",
    "A terrible name for a budget airline would be...",
    "I tried to start a hot air balloon business, but it...",
    "My psychic told me my future looks bright, mostly because...",
    "The worst thing you could hear a surgeon say right before anesthesia kicks in is: '...'",
    "I invented a waterproof toaster. The only problem is...",
    "I quit my job at the helium factory because...",
    "A fast food restaurant run entirely by ghosts would be called...",
    "The real reason aliens refuse to visit Earth is...",
    "I asked the librarian for books on paranoia, and they whispered...",
    "My doctor told me I speak only in gardening metaphors. I told him...",
]

def load_pun_prompts() -> List[str]:
    try:
        if os.path.exists(PROMPTS_FILE):
            with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data
    except Exception as e:
        print(f"[CompleteThePunGame] Error loading {PROMPTS_FILE}: {e}")
    return DEFAULT_PUN_PROMPTS

PUN_PROMPTS = load_pun_prompts()

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
        pool = list(load_pun_prompts())
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

