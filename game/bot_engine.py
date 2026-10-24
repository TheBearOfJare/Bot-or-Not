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

    def clean_human_response(self, text: str, max_words: int = 8, strip_final_period: bool = True) -> str:
        """
        Cleans and post-processes LLM output to match real human player behavior:
        - Real humans under a 25s timer type brief, casual phrases (under 8 words).
        - Strips AI prefix chatter ('Punchline:', 'Review:', 'It looks like', etc.).
        - Keeps only the first sentence or clause (no long, theatrical essays).
        - Strips quotes, markdown, and excessive punctuation.
        - Truncates strictly to max_words without trailing punctuation.
        """
        if not text:
            return ""

        raw = text.strip()
        # Remove markdown, quotes, backticks
        raw = raw.replace('"', '').replace('`', '').strip()

        # If multiple lines, only take the first non-empty line
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        if lines:
            raw = lines[0]

        # Strip prefixes iteratively (e.g. "Here is a guess: looks like an orange cat" -> "orange cat")
        prefixes_to_strip = [
            "here is a guess:", "here is my guess:", "here is:", "here's:",
            "1-star review:", "1 star review:", "1-star review", "1 star review",
            "review:", "review -", "review",
            "punchline:", "punchline -", "punchline –",
            "caption:", "caption -", "answer:", "response:",
            "my guess is:", "my guess is", "my guess:", "guess:",
            "it looks like a", "it looks like an", "it looks like",
            "looks like a", "looks like an", "looks like",
            "it seems to be a", "it seems to be",
            "it appears to be a", "it appears to be",
            "i think it's a", "i think it's an", "i think it's", "i think it is", "i think",
            "i see a", "i see an", "i see",
            "because:", "because "
        ]
        prefixes_to_strip.sort(key=len, reverse=True)
        changed = True
        while changed:
            changed = False
            lowered = raw.lower().strip()
            for p in prefixes_to_strip:
                if lowered.startswith(p):
                    raw = raw.strip()[len(p):].strip(" :-\t\n\r\"\'`#")
                    changed = True
                    break

        # Take only the first sentence / clause
        for delimiter in [". ", "! ", "? ", "; "]:
            if delimiter in raw:
                raw = raw.split(delimiter)[0].strip()

        # Enforce max word limit
        words = raw.split()
        if len(words) > max_words:
            raw = " ".join(words[:max_words])

        # Strip final period if desired (phone users rarely type ending periods in rapid games)
        if strip_final_period and raw.endswith("."):
            raw = raw[:-1].strip()

        raw = raw.rstrip(",;:- ")
        cleaned = raw.strip('"`\'*# ')
        # Capitalize first letter to match phone keyboard auto-capitalization
        if cleaned:
            cleaned = cleaned[0].upper() + cleaned[1:]
        return cleaned

    def query_ollama(self, prompt: str, system_prompt: str = "", image_path: str = None, num_predict: int = 25) -> str:
        """
        Attempts to call the local Ollama instance with optional Vision input.
        Uses think=False to disable chain-of-thought overhead for sub-second responses.
        Uses lower temperature (0.7) and tight num_predict to keep responses snappy and human-length.
        """
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "system": system_prompt or "You are a human playing a fast party game on your phone with friends under a 20-second timer. You type quick, short, casual, and believable responses. You never write essays, and you never try too hard to be funny.",
                "stream": False,
                "think": False,
                "options": {
                    "temperature": 0.7,
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
            f"You are playing a fast party game on your phone with friends under a 20-second timer.\n"
            f"Prompt: '{pun_setup}'\n"
            f"Complete this pun in 2 to 6 words max (e.g. 'no guts', 'they don't have the guts', 'it lost its baggage').\n"
            f"Write ONLY the punchline completion. Keep it short, punchy, and casual. No quotes, no explanations."
        )
        sys_prompt = "You type quick 2-6 word casual punchlines for a party game on your phone."
        ans = self.query_ollama(prompt, sys_prompt, num_predict=15)
        if ans:
            cleaned = self.clean_human_response(ans, max_words=7)
            if cleaned:
                return cleaned
        if fallback_answers:
            chosen = random.choice(fallback_answers)
            return chosen[0].upper() + chosen[1:] if chosen else ""
        return "They don't have the guts"

    def generate_review(self, product_name: str, fallback_answers: list = None) -> str:
        prompt = (
            f"You are a human playing a rapid party game on your phone with 20 seconds to answer.\n"
            f"Write a quick, blunt 1-star review for: '{product_name}'.\n"
            f"Write ONE short, casual complaint in 3 to 7 words (e.g. 'Broke immediately', 'Cheap plastic garbage', 'Tasted like dirty tap water').\n"
            f"Do not write paragraphs, do not try hard to be poetic or hilarious. Just sound like an annoyed person typing fast on a phone. No quotes."
        )
        sys_prompt = "You type quick, blunt 3-7 word 1-star complaints on a phone keyboard."
        ans = self.query_ollama(prompt, sys_prompt, num_predict=20)
        if ans:
            cleaned = self.clean_human_response(ans, max_words=8)
            if cleaned:
                return cleaned
        if fallback_answers:
            chosen = random.choice(fallback_answers)
            return chosen[0].upper() + chosen[1:] if chosen else ""
        return "Broke immediately, waste of money"

    def generate_survey_answers(self, survey_prompt: str, fallback_answers: list = None) -> list:
        prompt = (
            f"Family Feud party game. You have 20 seconds on your phone to submit 3 answers.\n"
            f"Prompt: '{survey_prompt}'\n"
            f"Give exactly 3 common answers separated by commas.\n"
            f"Keep each answer very short. (e.g. 'Traffic, Overslept, Flat tire').\n"
            f"Output ONLY the 3 answers separated by commas. No numbering, no extra text."
        )
        sys_prompt = "You are playing family feud. Provide what you think are the top 3 answers to the survey question separated by commas."
        ans = self.query_ollama(prompt, sys_prompt, num_predict=25)
        if ans:
            parts = [self.clean_human_response(p, max_words=3, strip_final_period=True) for p in ans.split(",") if p.strip()]
            parts = [p for p in parts if p]
            if len(parts) >= 3:
                return parts[:3]
        if fallback_answers and len(fallback_answers) >= 3:
            chosen = random.sample(fallback_answers, 3)
            return [x[0].upper() + x[1:] if x else "" for x in chosen]
        return ["Traffic", "Overslept", "Car trouble"]

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
        Uses a quick, casual guessing prompt fitting a human player under a 20-second timer.
        """
        prompt = (
            "Look at the attached image. You are playing a rapid party game on your phone with 20 seconds on the clock.\n"
            "Quickly name what you see in 3 to 7 words (e.g. 'cat on top of a red car' or 'dog next to a fire hydrant').\n"
            "Keep it casual, direct, and simple. Do NOT try to make jokes, do not write a paragraph, do not say it is blurry."
        )
        sys_prompt = "You type quick, direct 3-7 word descriptions of what you see in photos for a party game."
        ans = self.query_ollama(prompt, sys_prompt, image_path=image_path, num_predict=20)
        if ans:
            cleaned = self.clean_human_response(ans, max_words=8)
            if cleaned:
                return cleaned
        if fallback_answers:
            chosen = random.choice(fallback_answers)
            return chosen[0].upper() + chosen[1:] if chosen else ""
        return "Looks like a cat on a car"
