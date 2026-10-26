import random
from typing import Dict, Any, List
from game.minigames.base import BaseMinigame

# Simple product strings for easy expansion
REVIEW_PRODUCTS: List[str] = [
    "A standard yellow No. 2 pencil",
    "A bottle of municipal tap water",
    "A 12-inch clear plastic ruler",
    "A brown cardboard box",
    "A pack of unscented paper napkins",
    "A pair of generic white athletic socks",
    "An ordinary metal paperclip",
    "A standard wooden toothpick",
    "A basic USB wall charger",
    "A roll of aluminum foil",
    "A bag of plain ice cubes",
    "A retractable blue ballpoint pen",
]

# Shared generic emergency 1-star complaints if Ollama is offline or times out
GENERIC_REVIEW_FALLBACKS = [
    "Broke after five minutes of use",
    "Terrible quality, completely useless",
    "Do not recommend, huge waste of money",
    "Arrived damaged and smelled weird",
    "0 stars if I could. Awful",
    "Fell apart immediately",
    "Worst purchase I have ever made"
]

class OneStarReviewGame(BaseMinigame):
    def __init__(self, bot_engine, bot_count: int = 1, questions_count: int = 3):
        super().__init__(
            game_id="review",
            title="1 Star Review",
            instruction="Computers are not good at abstracting the experience from an object. Review-bomb this everyday item.",
            bot_engine=bot_engine,
            bot_count=bot_count,
            questions_count=questions_count
        )

    def _select_prompts(self):
        pool = list(REVIEW_PRODUCTS)
        random.shuffle(pool)
        chosen_list = [pool[i % len(pool)] for i in range(self.questions_count)]

        self.questions = []
        for i, item in enumerate(chosen_list):
            if isinstance(item, str):
                product = item
                fallbacks = None
            else:
                product = item.get("product", "")
                fallbacks = item.get("fallbacks")

            self.questions.append({
                "index": i,
                "prompt_data": {
                    "type": "text",
                    "prompt_text": f"Product: {product}",
                    "item_name": product,
                    "placeholder": "Write your 1-star review here..."
                },
                "meta": {
                    "product": product,
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

                review = self.bot_engine.generate_review(
                    product_name=meta["product"],
                    fallback_answers=meta.get("fallbacks")
                )

                sub_id = f"sub_{bot_id}"
                q["submissions"][sub_id] = {
                    "id": sub_id,
                    "author_id": bot_id,
                    "author_name": bot_name,
                    "is_bot": True,
                    "response": review,
                    "is_locked": True,
                    "version": 0
                }

    def _get_fallback_response_for_question(self, q: Dict[str, Any]) -> str:
        meta = q.get("meta", {})
        fallbacks = meta.get("fallbacks") if isinstance(meta, dict) else None
        if fallbacks:
            chosen = random.choice(fallbacks)
            return chosen[0].upper() + chosen[1:] if chosen else ""
        return random.choice(GENERIC_REVIEW_FALLBACKS)

    def _get_fallback_response(self) -> str:
        return random.choice(GENERIC_REVIEW_FALLBACKS)

