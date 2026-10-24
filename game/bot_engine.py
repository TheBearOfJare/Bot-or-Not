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
                "system": system_prompt or "You are playing a party game where you try to write funny, casual human-like responses.",
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
                    img = Image.open(image_path).convert("RGB").resize((180, 180))
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=80)
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
            f"You are a player in the game 'Bot or Not'. The prompt is: '{pun_setup}'. "
            f"Provide ONLY the punchline/completion for this pun in 1-8 words. "
            f"Do not include explanations, thinking, or extra text."
        )
        sys_prompt = "You write punchy, cheesy, or slightly robotic punchlines to puns."
        ans = self.query_ollama(prompt, sys_prompt, num_predict=35)
        if ans:
            return ans
        if fallback_answers:
            return random.choice(fallback_answers)
        return "Because it computed zero sense!"

    def generate_review(self, product_name: str, fallback_answers: list = None) -> str:
        prompt = (
            f"You are writing a hilarious, absurd 1-star product review for '{product_name}'. "
            f"Write 1 or 2 sentences max explaining why it is utterly terrible. "
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

    def generate_captcha_caption(self, image_path: str, image_description: str, fallback_answers: list = None) -> str:
        """
        Feeds the actual generated scene image to Ollama Vision!
        """
        prompt = (
            f"You are a human player playing a funny party game looking at this weird scene: {image_description}. "
            f"Write a short, casual, funny 1-sentence caption describing what is happening in the scene. "
            f"Sound like a casual party game player. Do not mention the words CAPTCHA, robot, AI, or clicking."
        )
        sys_prompt = "You are a casual player in a party game writing a funny one-sentence description of the humorous scene."
        ans = self.query_ollama(prompt, sys_prompt, image_path=image_path, num_predict=65)
        if ans:
            return ans
        if fallback_answers:
            return random.choice(fallback_answers)
        return f"A weird scene where {image_description}."
