import os
import io
import base64
import random
import requests
from PIL import Image
from config import Config

class BotEngine:
    def __init__(self, ollama_url: str = None, model: str = None):
        self.ollama_url = ollama_url or Config.OLLAMA_URL
        self.model = model or Config.OLLAMA_MODEL
        self.timeout = Config.OLLAMA_TIMEOUT

    def get_bot_display_name(self) -> str:
        """Bots are simply labeled as a Bot, no individual fake names."""
        return "Bot"

    def prewarm(self):
        """Pre-warm Ollama model in background so first game request doesn't suffer cold-start."""
        try:
            payload = {
                "model": self.model,
                "prompt": "hi",
                "stream": False,
                "think": False,
                "options": {"num_predict": 1}
            }
            requests.post(f"{self.ollama_url}/api/generate", json=payload, timeout=5)
            print(f"[BotEngine] Ollama model '{self.model}' pre-warmed and ready.")
        except Exception as e:
            print(f"[BotEngine] Ollama pre-warm note: {e} (will use fallbacks if Ollama is offline)")

    def query_ollama(self, prompt: str, system_prompt: str = "", image_path: str = None, num_predict: int = 60) -> str:
        """
        Attempts to call the local Ollama instance with optional Vision input.
        Uses think=False to disable chain-of-thought overhead for sub-second responses.
        """
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "system": system_prompt or "You are playing a party game where you try to write short, casual, human-like responses.",
                "stream": False,
                "think": False,
                "options": {
                    "temperature": 0.85,
                    "num_predict": num_predict
                }
            }

            # If an image is provided, feed it to Ollama vision
            if image_path and os.path.exists(image_path):
                try:
                    img = Image.open(image_path).convert("RGB").resize((360, 360))
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=85)
                    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                    payload["images"] = [b64]
                except Exception as img_err:
                    print(f"[BotEngine] Error encoding image for Ollama vision: {img_err}")

            res = requests.post(f"{self.ollama_url}/api/generate", json=payload, timeout=self.timeout)
            if res.status_code == 200:
                data = res.json()
                raw_text = data.get("response", "").strip()

                # If response was empty (due to thinking model token boundary), try parsing thinking
                if not raw_text and data.get("thinking"):
                    thinking = data.get("thinking", "")
                    lines = [ln.strip() for ln in thinking.split("\n") if ln.strip()]
                    if lines:
                        raw_text = lines[-1].strip('*`"\' ')

                clean = raw_text.strip('"\'*` \n')
                if clean:
                    return clean
        except Exception as e:
            print(f"[BotEngine] Ollama query failed ({e}), using fallback generation.")
            return None
        return None

    def generate_pun_punchline(self, pun_setup: str, fallback_answers: list = None) -> str:
        prompt = (
            f"You are a player in a game, trying to complete puns. "
            f"The prompt is: '{pun_setup}'. "
            f"Provide ONLY the punchline/completion for this pun in 1-8 words. "
            f"Do not include explanations, thinking, or extra text."
        )
        sys_prompt = "You write humorous, witty, or ironic punchlines to puns."
        ans = self.query_ollama(prompt, sys_prompt, num_predict=35)
        if ans:
            return ans
        if fallback_answers:
            return random.choice(fallback_answers)
        return "Because it computed zero sense!"

    def generate_review(self, product_name: str, fallback_answers: list = None) -> str:
        prompt = (
            f"You are writing a 1-star product review for '{product_name}'. "
            f"Write 1-2 sentence fragments explaining why it is utterly terrible. "
            f"Do not include quotes or review headers."
        )
        sys_prompt = "You are an angry, petty online reviewer leaving a 1-star complaint."
        ans = self.query_ollama(prompt, sys_prompt, num_predict=65)
        if ans:
            return ans
        if fallback_answers:
            return random.choice(fallback_answers)
        return f"Absolute waste of money. {product_name} failed all baseline expectations."

    def generate_survey_answers(self, survey_prompt: str, fallback_answers: list = None) -> list:
        prompt = (
            f"Family Feud style game. Prompt: '{survey_prompt}'. "
            f"List exactly 3 distinct answers separated by commas. "
            f"Example: Answer 1, Answer 2, Answer 3. Nothing else."
        )
        sys_prompt = "Provide 3 concise answers separated by commas."
        ans = self.query_ollama(prompt, sys_prompt, num_predict=45)
        if ans:
            parts = [p.strip().strip('"\'') for p in ans.split(",") if p.strip()]
            if len(parts) >= 3:
                return parts[:3]
        if fallback_answers and len(fallback_answers) >= 3:
            return random.sample(fallback_answers, 3)
        return ["My algorithm", "Syntax errors", "Rebooting the server"]

    def generate_dynamic_captcha_prompt(self) -> dict:
        """
        Dynamically generates a fresh CAPTCHA prompt on the fly using Ollama,
        intermixing common CAPTCHA subjects with descriptive COCO terms (colors, objects, actions, locations).
        Falls back to a procedural COCO mix if Ollama is offline or times out.
        """
        CAPTCHA_OBJECTS = [
            "fire hydrant", "school bus", "red car", "bicycle", "motorcycle",
            "traffic light", "stop sign", "cat", "dog", "cow", "bear",
            "slice of pizza", "boat", "train", "bench", "crosswalk", "umbrella"
        ]
        COCO_COLORS = ["red", "yellow", "blue", "green", "orange", "black", "white", "brown"]
        COCO_ACTIONS = [
            "parked next to", "stopped near", "sitting beside", "standing in front of",
            "crossing near", "waiting beside", "resting under"
        ]
        COCO_LOCATIONS = [
            "a sidewalk in the city", "a street corner", "a crosswalk on the road",
            "a tree in the park", "a sunny street", "a road near a building"
        ]

        seed_subject = random.choice(CAPTCHA_OBJECTS)
        prompt_builder = (
            f"You are designing a prompt for an image generator in a party game. "
            f"Write a simple, concrete 1-sentence scene description (8 to 14 words) featuring a {seed_subject}. "
            f"Combine it with everyday objects (like cars, bikes, hydrants, signs, streets, or animals). "
            f"Use clear visual words: colors, actions, and locations. "
            f"Example: 'A large brown dog sitting next to a red fire hydrant on the sidewalk.' "
            f"Output ONLY the single sentence. No quotes, no explanations."
        )
        sys_prompt = "You are a concise visual prompt designer creating simple concrete scenes."

        generated_text = self.query_ollama(prompt_builder, sys_prompt, num_predict=35)
        if generated_text:
            cleaned = generated_text.strip().strip('"\'*`\n').split('\n')[0].strip()
            if len(cleaned.split()) >= 4:
                return {
                    "prompt": cleaned,
                    "seed": seed_subject,
                    "title": f"Verification: {seed_subject.title()}"
                }

        # Robust procedural fallback if Ollama times out or fails
        color1 = random.choice(COCO_COLORS)
        obj2 = random.choice([o for o in CAPTCHA_OBJECTS if o != seed_subject])
        color2 = random.choice(COCO_COLORS)
        action = random.choice(COCO_ACTIONS)
        loc = random.choice(COCO_LOCATIONS)
        fallback_prompt = f"A {color1} {seed_subject} {action} a {color2} {obj2} on {loc}."
        return {
            "prompt": fallback_prompt,
            "seed": seed_subject,
            "title": f"Verification: {seed_subject.title()}"
        }

    def generate_captcha_caption(self, image_path: str, fallback_answers: list = None) -> str:
        """
        Feeds ONLY the raw image to Ollama Vision with NO text spoilers or hints.
        The bot is strictly forced to interpret what it sees directly from the image.
        Uses a confident, casual guessing prompt to maximize descriptive guesses without refusals.
        """
        prompt = (
            "Look at the attached image. You are playing a fun picture-guessing party game with friends.\n"
            "Describe what this weird, glitchy picture looks like to you (objects, vehicles, animals, shapes, colors, or scene).\n"
            "Give a confident, casual 1-sentence guess of what you see. 1 sentence max, minimal punctuation.\n"
            "Do not apologize, do not say it is blurry or distorted, and never say you don't know—just give your best confident guess!"
        )
        sys_prompt = "You are a casual player in an image-guessing party game. You always confidently name whatever objects, creatures, vehicles, or scene you see in the picture."
        ans = self.query_ollama(prompt, sys_prompt, image_path=image_path, num_predict=45)
        if ans:
            cleaned = ans.strip().strip('"\'*`\n').replace('"', '')
            if cleaned:
                return cleaned
        if fallback_answers:
            return random.choice(fallback_answers)
        return "A weird colorful contraption on the street."
