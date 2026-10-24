import os
import random
from game.minigames.base import BaseMinigame
from game.minigames.captcha_gen import CAPTCHA_SUBJECTS, create_captcha_asset

class CaptchaCaptionGame(BaseMinigame):
    def __init__(self, bot_engine, bot_count: int = 1):
        super().__init__(
            game_id="captcha",
            title="Captcha Caption",
            instruction="Look at this terrible, glitchy CAPTCHA image. Write a funny, human description of what you see!",
            bot_engine=bot_engine,
            bot_count=bot_count
        )
        self.chosen_subject_key = None
        self.chosen_subject = None
        self.image_url = None
        self.image_filepath = None

    def _select_prompt(self):
        self.chosen_subject_key = random.choice(list(CAPTCHA_SUBJECTS.keys()))
        self.chosen_subject = CAPTCHA_SUBJECTS[self.chosen_subject_key]
        
        img_filename = f"captcha_{self.chosen_subject_key}.png"
        self.image_filepath = os.path.join("static", "images", "captchas", img_filename)

        # Generate crunchy CAPTCHA image with intentional degradation trick
        create_captcha_asset(self.chosen_subject_key, self.image_filepath)

        self.image_url = f"/static/images/captchas/{img_filename}"

        self.prompt_data = {
            "type": "image_caption",
            "prompt_text": "Describe what is happening in this image:",
            "subject_title": "Security Verification",
            "image_url": self.image_url,
            "placeholder": "Describe what is happening in this image..."
        }

    def _generate_bots(self):
        for i in range(self.bot_count):
            bot_id = f"bot_{i+1}"
            bot_name = self.bot_engine.get_bot_display_name()
            self.bot_ids.append(bot_id)

            # Feed the generated image directly to Ollama vision!
            caption = self.bot_engine.generate_captcha_caption(
                image_path=self.image_filepath,
                image_description=self.chosen_subject["description"],
                fallback_answers=self.chosen_subject["fallbacks"]
            )

            sub_id = f"sub_{bot_id}"
            self.submissions[sub_id] = {
                "id": sub_id,
                "author_id": bot_id,
                "author_name": bot_name,
                "is_bot": True,
                "response": caption
            }

    def _get_fallback_response(self) -> str:
        if self.chosen_subject and self.chosen_subject.get("fallbacks"):
            return random.choice(self.chosen_subject["fallbacks"])
        return "A weird, crunchy image of an unusual scene."
