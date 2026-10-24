import random
from game.minigames.base import BaseMinigame

REVIEW_PRODUCTS = [
    {
        "product": "A standard yellow No. 2 pencil",
        "fallbacks": [
            "Lead broke immediately",
            "Eraser just smudged everything into a black smear",
            "Snapped in half on first use",
            "Worst pencil ever, constantly broke"
        ]
    },
    {
        "product": "A lukewarm bottle of municipal tap water",
        "fallbacks": [
            "Tastes like straight rust and old pipes",
            "Was literally warm and gross",
            "Tastes like hose water",
            "Zero stars, just drink from a puddle"
        ]
    },
    {
        "product": "A 12-inch clear plastic ruler",
        "fallbacks": [
            "Snapped in my backpack on day one",
            "So clear I immediately lost it on my desk",
            "Numbers rubbed off after one week",
            "Sharp edges, cheap brittle plastic"
        ]
    },
    {
        "product": "A single brown cardboard box",
        "fallbacks": [
            "Arrived crushed and soaked",
            "Fell apart as soon as I picked it up",
            "Literally just a flimsy piece of cardboard",
            "Bottom ripped open and dropped everything"
        ]
    },
    {
        "product": "A pack of unscented paper napkins",
        "fallbacks": [
            "Ripped immediately when wet",
            "Felt like sandpaper on my face",
            "Absorbed nothing and tore in half",
            "Super thin and completely useless"
        ]
    }
]

class OneStarReviewGame(BaseMinigame):
    def __init__(self, bot_engine, bot_count: int = 1):
        super().__init__(
            game_id="review",
            title="1 Star Review",
            instruction="Review-bomb this mundane everyday item! Give a petty, hilarious 1-star review.",
            bot_engine=bot_engine,
            bot_count=bot_count
        )
        self.chosen_product = None

    def _select_prompt(self):
        self.chosen_product = random.choice(REVIEW_PRODUCTS)
        self.prompt_data = {
            "type": "text",
            "prompt_text": f"Product: {self.chosen_product['product']}",
            "item_name": self.chosen_product['product'],
            "placeholder": "Write your 1-star review here..."
        }

    def _generate_bots(self):
        for i in range(self.bot_count):
            bot_id = f"bot_{i+1}"
            bot_name = self.bot_engine.get_bot_display_name()
            self.bot_ids.append(bot_id)
            
            review = self.bot_engine.generate_review(
                product_name=self.chosen_product["product"],
                fallback_answers=self.chosen_product["fallbacks"]
            )
            
            sub_id = f"sub_{bot_id}"
            self.submissions[sub_id] = {
                "id": sub_id,
                "author_id": bot_id,
                "author_name": bot_name,
                "is_bot": True,
                "response": review,
                "is_locked": True,
                "version": 0
            }

    def _get_fallback_response(self) -> str:
        if self.chosen_product and self.chosen_product.get("fallbacks"):
            chosen = random.choice(self.chosen_product["fallbacks"])
            return chosen[0].upper() + chosen[1:] if chosen else ""
        return "Broke immediately, waste of money"
