import random
from game.minigames.base import BaseMinigame

PUN_PROMPTS = [
    {
        "setup": "Why don't skeletons fight each other? Because...",
        "fallbacks": [
            "they don't have the guts!",
            "their hearts aren't in it.",
            "they have no bone to pick.",
            "calcium deficiency prevents aggression."
        ]
    },
    {
        "setup": "I told my suitcase there will be no vacation this year. Now...",
        "fallbacks": [
            "I'm dealing with emotional baggage.",
            "it is completely unpacked emotionally.",
            "it zipped its mouth and won't talk.",
            "its zipper broke from weeping."
        ]
    },
    {
        "setup": "Parallel lines have so much in common. It's a shame...",
        "fallbacks": [
            "they'll never meet.",
            "their slopes remain eternally alienated.",
            "geometry keeps them emotionally distant.",
            "they can never cross paths."
        ]
    },
    {
        "setup": "What do you call a fake noodle? An...",
        "fallbacks": [
            "Impasta!",
            "Artificial spaghetti construct.",
            "Udon know who I am.",
            "Imitation carb simulator."
        ]
    },
    {
        "setup": "Why did the scarecrow win an award? Because he was...",
        "fallbacks": [
            "outstanding in his field!",
            "the ultimate straw man.",
            "not easily rattled by crows.",
            "optimized for avian deterrence."
        ]
    },
    {
        "setup": "I used to play piano by ear, but now I...",
        "fallbacks": [
            "use my hands like a normal person.",
            "realized my ears lack fingers.",
            "consult sheet music algorithms.",
            "have bruised eardrums."
        ]
    }
]

class CompleteThePunGame(BaseMinigame):
    def __init__(self, bot_engine, bot_count: int = 1):
        super().__init__(
            game_id="pun",
            title="Complete the Pun",
            instruction="Fill in the punchline! Make it sound like a human wrote it so nobody suspects you.",
            bot_engine=bot_engine,
            bot_count=bot_count
        )
        self.chosen_prompt = None

    def _select_prompt(self):
        self.chosen_prompt = random.choice(PUN_PROMPTS)
        self.prompt_data = {
            "type": "text",
            "prompt_text": self.chosen_prompt["setup"],
            "placeholder": "Enter your punchline..."
        }

    def _generate_bots(self):
        for i in range(self.bot_count):
            bot_id = f"bot_{i+1}"
            bot_name = self.bot_engine.get_bot_display_name()
            self.bot_ids.append(bot_id)
            
            punchline = self.bot_engine.generate_pun_punchline(
                pun_setup=self.chosen_prompt["setup"],
                fallback_answers=self.chosen_prompt["fallbacks"]
            )
            
            sub_id = f"sub_{bot_id}"
            self.submissions[sub_id] = {
                "id": sub_id,
                "author_id": bot_id,
                "author_name": bot_name,
                "is_bot": True,
                "response": punchline
            }

    def _get_fallback_response(self) -> str:
        if self.chosen_prompt and self.chosen_prompt.get("fallbacks"):
            return random.choice(self.chosen_prompt["fallbacks"])
        return "Because it computed zero sense!"
