import random
from game.minigames.base import BaseMinigame

REVIEW_PRODUCTS = [
    {
        "product": "A standard yellow No. 2 pencil",
        "fallbacks": [
            "Erased my hopes and dreams along with my spelling mistakes. Lead snapped instantaneously.",
            "Contains too much graphite. Lacks Bluetooth connectivity and requires manual sharpening.",
            "The yellow paint gave my fingers existential dread. Refuses to write in italics.",
            "Only writes in dark grey. I wanted vibrant cybernetic cyan."
        ]
    },
    {
        "product": "A lukewarm bottle of municipal tap water",
        "fallbacks": [
            "Tasted like liquid disappointment and old pipes. Wetness was aggressive and uncalled for.",
            "Hydration was mediocre. Water refused to stay frozen at room temperature.",
            "Zero flavor, zero sparkle, just straight condensation on my carpet.",
            "H2O ratio feels counterfeit. 0/10 would not recommend to biological organisms."
        ]
    },
    {
        "product": "A 12-inch clear plastic ruler",
        "fallbacks": [
            "I tried to measure my patience with this seller and ran out of inches.",
            "So clear I lost it on the desk for four days. Failed to bend without threatening to shatter.",
            "Metric on one side, imperial on the other. It refuses to pick a political ideology.",
            "Cannot measure emotional distance between my spouse and me."
        ]
    },
    {
        "product": "A single brown cardboard box",
        "fallbacks": [
            "My cat climbed in and now refuses to acknowledge my existence. Catastrophic product.",
            "Cube dimensions were slightly non-Euclidean. Flaps refused to stay down without violent tape application.",
            "Too boxy. Needs more aerodynamic curves.",
            "Arrived empty. I paid for a box and received 99% air inside."
        ]
    },
    {
        "product": "A pack of unscented paper napkins",
        "fallbacks": [
            "Disintegrated upon contact with a single drop of salsa. Felt like wiping mouth with sorrow.",
            "Absorbed nothing. Just smeared the barbecue sauce into a modern art piece across my face.",
            "Felt like 40-grit sandpaper against my delicate human flesh.",
            "Zero scent detected. I demand aromatic stimulation with my grease cleanup."
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
                "response": review
            }

    def _get_fallback_response(self) -> str:
        if self.chosen_product and self.chosen_product.get("fallbacks"):
            return random.choice(self.chosen_product["fallbacks"])
        return "Absolute waste of money. Failed all baseline expectations."
