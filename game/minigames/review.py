import random
from typing import Dict, Any
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
        "product": "A bottle of municipal tap water",
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
        "product": "A brown cardboard box",
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
    },
    {
        "product": "A pair of generic white athletic socks",
        "fallbacks": [
            "Got holes in the toe on the very first step",
            "Slid down into my shoes every three seconds",
            "One sock was mysteriously three inches shorter",
            "Turned into tissue paper after one gentle wash"
        ]
    },
    {
        "product": "An ordinary metal paperclip",
        "fallbacks": [
            "Bent out of shape trying to hold two sheets",
            "Rust immediately appeared in humid air",
            "Tore through my important tax documents",
            "Snapped in half when unbending"
        ]
    },
    {
        "product": "A standard wooden toothpick",
        "fallbacks": [
            "Splintered right between my back molars",
            "Snapped under the slightest pressure",
            "Tasted heavily like tree bark and dirt",
            "Completely blunt, did not pick anything"
        ]
    },
    {
        "product": "A basic USB wall charger",
        "fallbacks": [
            "Took 11 hours to charge my phone 3 percent",
            "Emitted a high-pitched buzzing screech all night",
            "Heated up enough to toast an english muffin",
            "Prongs bent instantly plugging into the wall"
        ]
    },
    {
        "product": "A roll of aluminum foil",
        "fallbacks": [
            "Didn't protect me from aliens",
            "I got one clean sheet and then it never tore straight again",
            "The cookies still got stale",
            "Foiled my plans of world domination"
        ]
    },
    {
        "product": "A bag of plain ice cubes",
        "fallbacks": [
            "Melted completely into water, total ripoff",
            "Way too cold to enjoy comfortably",
            "All stuck together in one giant unyielding brick",
            "Tasted vaguely like the bottom of a freezer"
        ]
    },
    {
        "product": "A retractable blue ballpoint pen",
        "fallbacks": [
            "Exploded blue ink inside my favorite shirt",
            "Clicker got jammed permanently down on day two",
            "Scratched deep grooves into the paper without inking",
            "Skipped every other letter I attempted to write"
        ]
    }
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
        for i, chosen in enumerate(chosen_list):
            self.questions.append({
                "index": i,
                "prompt_data": {
                    "type": "text",
                    "prompt_text": f"Product: {chosen['product']}",
                    "item_name": chosen["product"],
                    "placeholder": "Write your 1-star review here..."
                },
                "meta": chosen,
                "submissions": {},
                "votes": {},
                "bot_ids": []
            })

    def _generate_bots(self):
        for q in self.questions:
            chosen = q["meta"]
            for i in range(self.bot_count):
                bot_id = f"bot_{i+1}"
                bot_name = self.bot_engine.get_bot_display_name()
                if bot_id not in q["bot_ids"]:
                    q["bot_ids"].append(bot_id)

                review = self.bot_engine.generate_review(
                    product_name=chosen["product"],
                    fallback_answers=chosen["fallbacks"]
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
        chosen = q.get("meta")
        if chosen and chosen.get("fallbacks"):
            chosen_ans = random.choice(chosen["fallbacks"])
            return chosen_ans[0].upper() + chosen_ans[1:] if chosen_ans else ""
        return "Broke immediately, waste of money"
