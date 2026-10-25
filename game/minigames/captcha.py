import os
import time
import random
from typing import Dict, Any
from game.minigames.base import BaseMinigame
from game.minigames.captcha_gen import CAPTCHA_SUBJECTS, create_captcha_asset

class CaptchaCaptionGame(BaseMinigame):
    def __init__(self, bot_engine, bot_count: int = 1, questions_count: int = 3):
        super().__init__(
            game_id="captcha",
            title="Captcha Caption",
            instruction="Decipher and describe the contents of the CAPTCHA shown to you.",
            bot_engine=bot_engine,
            bot_count=bot_count,
            questions_count=questions_count
        )

    def _select_prompts(self):
        self.questions = []
        ts = int(time.time())

        for i in range(self.questions_count):
            prompt_info = self.bot_engine.generate_dynamic_captcha_prompt()
            chosen_prompt = prompt_info["prompt"]
            subject_key = prompt_info.get("seed", f"captcha_{i}")
            subject = CAPTCHA_SUBJECTS.get(subject_key, {
                "title": prompt_info.get("title", "Security Verification"),
                "description": chosen_prompt,
                "fallbacks": [
                    "Looks like a street scene",
                    "Car parked on the road",
                    "Blurry scene with an animal"
                ]
            })

            img_filename = f"captcha_{subject_key}_{ts}_{i}.png"
            image_filepath = os.path.join("static", "images", "captchas", img_filename)
            create_captcha_asset(chosen_prompt, image_filepath)
            image_url = f"/static/images/captchas/{img_filename}?v={ts}_{i}"

            self.questions.append({
                "index": i,
                "prompt_data": {
                    "type": "image_caption",
                    "prompt_text": "Describe what is happening in this image:",
                    "subject_title": "Security Verification",
                    "image_url": image_url,
                    "placeholder": "Describe what is happening in this image..."
                },
                "meta": {
                    "chosen_prompt": chosen_prompt,
                    "subject": subject,
                    "image_filepath": image_filepath,
                    "image_url": image_url
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

                fallbacks = meta["subject"].get("fallbacks") if meta.get("subject") else None
                caption = self.bot_engine.generate_captcha_caption(
                    image_path=meta["image_filepath"],
                    fallback_answers=fallbacks
                )

                sub_id = f"sub_{bot_id}"
                q["submissions"][sub_id] = {
                    "id": sub_id,
                    "author_id": bot_id,
                    "author_name": bot_name,
                    "is_bot": True,
                    "response": caption,
                    "is_locked": True,
                    "version": 0
                }

    def _get_fallback_response_for_question(self, q: Dict[str, Any]) -> str:
        meta = q.get("meta", {})
        subject = meta.get("subject")
        if subject and subject.get("fallbacks"):
            chosen = random.choice(subject["fallbacks"])
            return chosen[0].upper() + chosen[1:] if chosen else ""
        return "Looks like a cat on a car"

    def _get_fallback_response(self) -> str:
        return "Looks like a cat on a car"
