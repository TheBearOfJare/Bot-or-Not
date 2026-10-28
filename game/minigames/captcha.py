import os
import time
import random
from typing import Dict, Any, Optional
from game.minigames.base import BaseMinigame
from game.minigames.captcha_gen import CAPTCHA_SUBJECTS, create_captcha_asset, is_attngan_active
from game.bot_engine import CAPTCHA_OBJECTS
from game.prompt_tracker import prompt_tracker

def clear_captcha_images(captchas_dir: Optional[str] = None) -> int:
    """
    Cleans up all generated CAPTCHA images on program launch.
    Leaves .gitignore intact. Returns the number of files deleted.
    """
    if captchas_dir is None:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        captchas_dir = os.path.join(base_dir, "static", "images", "captchas")
    
    os.makedirs(captchas_dir, exist_ok=True)
    deleted_count = 0
    try:
        for fname in os.listdir(captchas_dir):
            if fname.startswith("."):
                continue  # Keep .gitignore or other hidden files
            fpath = os.path.join(captchas_dir, fname)
            if os.path.isfile(fpath):
                try:
                    os.remove(fpath)
                    deleted_count += 1
                except Exception as e:
                    print(f"[Captcha] Error removing file {fpath}: {e}")
        if deleted_count > 0:
            print(f"[Captcha] Cleared {deleted_count} stale CAPTCHA image(s) on launch from {captchas_dir}")
        else:
            print(f"[Captcha] Stale CAPTCHA images directory is already clean.")
    except Exception as e:
        print(f"[Captcha] Error clearing captchas directory {captchas_dir}: {e}")
    return deleted_count

class CaptchaCaptionGame(BaseMinigame):
    def __init__(self, bot_engine, bot_count: int = 1, questions_count: int = 3):
        super().__init__(
            game_id="captcha",
            title="Captcha Caption",
            instruction="Humans are good at interperating abstract representations of real-world concepts. Computers are... not. Decipher and describe the contents of the CAPTCHA shown to you.",
            bot_engine=bot_engine,
            bot_count=bot_count,
            questions_count=questions_count
        )

    def _select_prompts(self):
        self.questions = []
        ts = int(time.time())
        attngan_ready = is_attngan_active()

        if attngan_ready:
            chosen_seeds = prompt_tracker.select_prompts("captcha", CAPTCHA_OBJECTS, self.questions_count)
        else:
            available_keys = list(CAPTCHA_SUBJECTS.keys())
            chosen_seeds = prompt_tracker.select_prompts("captcha", available_keys, self.questions_count)

        for i in range(self.questions_count):
            if attngan_ready:
                seed = chosen_seeds[i]
                prompt_info = self.bot_engine.generate_dynamic_captcha_prompt(seed_subject=seed)
                chosen_prompt = prompt_info["prompt"]
                subject_key = prompt_info.get("seed", seed)
                subject = CAPTCHA_SUBJECTS.get(subject_key, {
                    "title": prompt_info.get("title", f"Verification: {seed.title()}"),
                    "description": chosen_prompt,
                    "fallbacks": [
                        "Looks like a street scene",
                        "Car parked on the road",
                        "Blurry scene with an animal"
                    ]
                })
            else:
                subject_key = chosen_seeds[i]
                subject = CAPTCHA_SUBJECTS[subject_key]
                chosen_prompt = subject_key

            img_filename = f"captcha_{subject_key}_{ts}_{i}.png"
            image_filepath = os.path.join("static", "images", "captchas", img_filename)
            os.makedirs(os.path.dirname(image_filepath), exist_ok=True)
            create_captcha_asset(chosen_prompt, image_filepath)
            image_url = f"/static/images/captchas/{img_filename}?v={ts}_{i}"

            self.questions.append({
                "index": i,
                "prompt_data": {
                    "type": "image_caption",
                    "prompt_text": "Describe what is depicted in this CAPTCHA:",
                    "subject_title": "Security Verification",
                    "image_url": image_url,
                    "placeholder": "Describe what is depicted in this CAPTCHA..."
                },
                "meta": {
                    "chosen_prompt": chosen_prompt,
                    "subject": subject,
                    "image_filepath": image_filepath,
                    "image_url": image_url
                },
                "submissions": {},
                "votes": {},
                "draft_votes": {},
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
