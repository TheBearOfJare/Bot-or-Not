import os
import json
import random
from typing import Dict, Any, List, Optional
from game.minigames.base import BaseMinigame
from game.prompt_tracker import prompt_tracker
from game.bot_engine import is_response_similar_to_any, GENERIC_REVIEW_FALLBACKS

PROMPTS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "prompts", "review.json"))

# Built-in fallbacks if data/prompts/review.json is absent
DEFAULT_REVIEW_PRODUCTS: List[str] = [
    "A high-end bathroom scale with Bluetooth sync to your phone",
    "A scented candle labeled 'Ocean Breeze'",
    "A mood ring from a museum gift shop",
    "A self-help book titled 'How to Be Decisive'",
    "A 1000-piece jigsaw puzzle of a clear blue sky",
    "A high-magnification illuminated makeup mirror",
    "An ultra-precision digital alarm clock with sunrise simulator",
    "A pair of noise-canceling headphones",
    "A 'smart' electric toothbrush with a mobile tracking app",
    "A memory foam ergonomic contour pillow",
    "A motion-sensor automatic kitchen trash can",
    "A robotic vacuum cleaner with pet detection",
    "A 12-inch clear plastic school ruler",
]

def load_review_products() -> List[str]:
    try:
        if os.path.exists(PROMPTS_FILE):
            with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data
    except Exception as e:
        print(f"[OneStarReviewGame] Error loading {PROMPTS_FILE}: {e}")
    return DEFAULT_REVIEW_PRODUCTS

REVIEW_PRODUCTS = load_review_products()

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
        pool = list(load_review_products())
        chosen_list = prompt_tracker.select_prompts("review", pool, self.questions_count)

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
                "draft_votes": {},
                "bot_ids": []
            })

    def _generate_bots(self):
        for q in self.questions:
            meta = q["meta"]
            fallbacks = meta.get("fallbacks") if isinstance(meta, dict) else None
            product = meta.get("product", "") if isinstance(meta, dict) else ""

            if self.bot_engine:
                reviews = self.bot_engine.generate_coordinated_reviews(
                    product_name=product,
                    bot_count=self.bot_count,
                    fallback_answers=fallbacks
                )
            else:
                reviews = [self._get_fallback_response_for_question(q) for _ in range(self.bot_count)]

            for i in range(self.bot_count):
                bot_id = f"bot_{i+1}"
                bot_name = self.bot_engine.get_bot_display_name() if self.bot_engine else "Bot"
                if bot_id not in q["bot_ids"]:
                    q["bot_ids"].append(bot_id)

                resp = reviews[i] if i < len(reviews) else self._get_fallback_response_for_question(q)
                sub_id = f"sub_{bot_id}"
                q["submissions"][sub_id] = {
                    "id": sub_id,
                    "author_id": bot_id,
                    "author_name": bot_name,
                    "is_bot": True,
                    "response": resp,
                    "is_locked": True,
                    "version": 0
                }

    def _get_fallback_response_for_question(self, q: Dict[str, Any], avoid_responses: List[Any] = None) -> str:
        meta = q.get("meta", {})
        fallbacks = meta.get("fallbacks") if isinstance(meta, dict) else None
        product = meta.get("product", "") if isinstance(meta, dict) else ""
        if self.bot_engine:
            return self.bot_engine._pick_distinct_fallback(fallbacks, GENERIC_REVIEW_FALLBACKS, avoid=avoid_responses, prompt_context=product)

        pool = [f for f in (fallbacks or GENERIC_REVIEW_FALLBACKS) if not is_response_similar_to_any(f, avoid_responses or [], prompt_context=product)]
        chosen = random.choice(pool) if pool else random.choice(GENERIC_REVIEW_FALLBACKS)
        return chosen[0].upper() + chosen[1:] if chosen else ""

    def _get_fallback_response(self) -> str:
        return random.choice(GENERIC_REVIEW_FALLBACKS)

