from typing import Dict, Type
from game.minigames.pun import CompleteThePunGame
from game.minigames.review import OneStarReviewGame
from game.minigames.survey import SurveySaysGame
from game.minigames.captcha import CaptchaCaptionGame
from game.minigames.bonus import BonusRoundGame

# Registry of all available minigames
MINIGAME_REGISTRY: Dict[str, Dict[str, any]] = {
    "pun": {
        "name": "Complete the Pun",
        "description": "Fill in the missing punchline.",
        "class": CompleteThePunGame,
        "is_bonus": False
    },
    "review": {
        "name": "1 Star Review",
        "description": "Review-bomb a product.",
        "class": OneStarReviewGame,
        "is_bonus": False
    },
    "survey": {
        "name": "Survey Says",
        "description": "Family Feud style: Name your top 3 answers.",
        "class": SurveySaysGame,
        "is_bonus": False
    },
    "captcha": {
        "name": "Captcha Caption",
        "description": "Describe the contents of the CAPTCHA image.",
        "class": CaptchaCaptionGame,
        "is_bonus": False
    },
    "bonus": {
        "name": "Final Bonus Round",
        "description": "Match grouped player response dossiers to the humans who wrote them.",
        "class": BonusRoundGame,
        "is_bonus": True
    }
}

def create_minigame_instance(game_key: str, bot_engine, bot_count: int = 1, questions_count: int = 3):
    """
    Factory function to instantiate a minigame by key.
    """
    if game_key not in MINIGAME_REGISTRY:
        raise ValueError(f"Unknown minigame key: '{game_key}'. Available: {list(MINIGAME_REGISTRY.keys())}")
    
    game_meta = MINIGAME_REGISTRY[game_key]
    game_cls = game_meta["class"]
    if game_meta.get("is_bonus", False):
        return game_cls(bot_engine=bot_engine, bot_count=bot_count)
    return game_cls(bot_engine=bot_engine, bot_count=bot_count, questions_count=questions_count)
