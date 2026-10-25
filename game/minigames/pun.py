import random
from typing import Dict, Any
from game.minigames.base import BaseMinigame

PUN_PROMPTS = [
    {
        "setup": "Why don't skeletons fight each other? Because...",
        "fallbacks": [
            "They don't have the guts",
            "Their hearts aren't in it",
            "They got no backbone",
            "They have no stomach for it"
        ]
    },
    {
        "setup": "I told my suitcase there will be no vacation this year. Now...",
        "fallbacks": [
            "I'm dealing with emotional baggage",
            "It won't talk to me",
            "It's completely packed with rage",
            "It won't open up to me"
        ]
    },
    {
        "setup": "Parallel lines have so much in common. It's a shame...",
        "fallbacks": [
            "They'll never meet",
            "They never cross paths",
            "They never get together",
            "They're always apart"
        ]
    },
    {
        "setup": "What do you call a fake noodle? An...",
        "fallbacks": [
            "Impasta",
            "Impasta obviously",
            "Im-pasta",
            "Impostor pasta"
        ]
    },
    {
        "setup": "Why did the scarecrow win an award? Because he was...",
        "fallbacks": [
            "Outstanding in his field",
            "Out standing in his field",
            "Just standing there",
            "The only one who showed up"
        ]
    },
    {
        "setup": "I used to play piano by ear, but now I...",
        "fallbacks": [
            "Use my hands",
            "Use my fingers like a normal person",
            "Just listen to Spotify",
            "Gave up completely"
        ]
    },
    {
        "setup": "Why did the tomato blush? Because...",
        "fallbacks": [
            "It saw the salad dressing",
            "Someone caught it undressed",
            "It was ripe with embarrassment",
            "It dropped its peel"
        ]
    },
    {
        "setup": "I'm reading a book on anti-gravity. It's impossible to...",
        "fallbacks": [
            "Put down",
            "Keep my feet on the ground",
            "Drop it",
            "Stay grounded"
        ]
    },
    {
        "setup": "Why can't you trust stairs? Because...",
        "fallbacks": [
            "They're always up to something",
            "They always let you down",
            "They take steps behind your back",
            "They're full of shady steps"
        ]
    },
    {
        "setup": "What do you call a sleeping dinosaur? A...",
        "fallbacks": [
            "Dino-snore",
            "T-Wrecks",
            "Jurassic snorer",
            "Fossilized sleeper"
        ]
    },
    {
        "setup": "Why did the golfer bring two pairs of pants? In case...",
        "fallbacks": [
            "He got a hole in one",
            "He shanked into the pond",
            "The first pair got stained",
            "He ripped them driving"
        ]
    },
    {
        "setup": "I used to be a personal banker, but then I...",
        "fallbacks": [
            "Lost interest",
            "Ran out of balance",
            "Withdrew from society",
            "Defaulted on my enthusiasm"
        ]
    },
    {
        "setup": "Why did the bicycle fall over? Because...",
        "fallbacks": [
            "It was two-tired",
            "It couldn't stand on its own",
            "Its kickstand quit",
            "It lost momentum"
        ]
    },
    {
        "setup": "What do you call cheese that isn't yours? ...",
        "fallbacks": [
            "Nacho cheese",
            "Stolen cheddar",
            "Not-yo cheese",
            "Somebody else's snack"
        ]
    }
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
        for i, chosen in enumerate(chosen_list):
            self.questions.append({
                "index": i,
                "prompt_data": {
                    "type": "text",
                    "prompt_text": chosen["setup"],
                    "placeholder": "Enter your punchline..."
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

                punchline = self.bot_engine.generate_pun_punchline(
                    pun_setup=chosen["setup"],
                    fallback_answers=chosen["fallbacks"]
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
        chosen = q.get("meta")
        if chosen and chosen.get("fallbacks"):
            chosen_ans = random.choice(chosen["fallbacks"])
            return chosen_ans[0].upper() + chosen_ans[1:] if chosen_ans else ""
        return "They don't have the guts"
