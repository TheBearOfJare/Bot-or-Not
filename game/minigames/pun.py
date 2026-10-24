import random
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
                "response": punchline,
                "is_locked": True,
                "version": 0
            }

    def _get_fallback_response(self) -> str:
        if self.chosen_prompt and self.chosen_prompt.get("fallbacks"):
            chosen = random.choice(self.chosen_prompt["fallbacks"])
            return chosen[0].upper() + chosen[1:] if chosen else ""
        return "They don't have the guts"
