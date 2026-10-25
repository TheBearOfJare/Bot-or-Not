import os
import io
import re
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

    def clean_human_response(self, text: str, max_words: int = 12, strip_setup: str = "", strip_final_period: bool = True) -> str:
        """
        Cleans and post-processes LLM output to match real human player behavior:
        - Real humans under a 30s timer type brief, casual phrases (under 12 words).
        - Strips AI prefix chatter ('Punchline:', 'Review:', 'It looks like', etc.).
        - Keeps the first complete sentence/clause without chopping words mid-sentence.
        - Strips setup repetitions, markdown, and excessive punctuation.
        - Never slices mid-clause or produces dangling prepositions ('on the', 'by a').
        """
        if not text:
            return ""

        raw = text.strip()
        # Remove markdown, quotes, backticks
        raw = re.sub(r"[*_`#~]", "", raw).strip("\"'` ")

        # If setup prompt is repeated in response, strip it
        if strip_setup:
            clean_setup = re.sub(r"[*_`#~]", "", strip_setup).strip(" .?!:–-")
            if clean_setup and clean_setup.lower() in raw.lower():
                pattern = re.escape(clean_setup) + r"[\s.?:–-]*"
                raw = re.sub(pattern, "", raw, flags=re.IGNORECASE).strip()

        # If multiple lines, locate first content line (skip header/preamble lines)
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        if not lines:
            return ""

        header_patterns = [
            r"^(here is|here's|punchline|review|caption|answer|response|my guess|guess|solution|joke)[\s:–-]*$",
            r"^(here is|here's|sure|okay|ok|well)[\s,]+(a|the|my)?[\s]*(punchline|review|caption|answer|response|guess|joke)?[\s:–-]*$",
            r"^(wait|sorry|actually|let me try|oops)[\s,].*$"
        ]

        content_line = ""
        for ln in lines:
            is_header = any(re.match(hp, ln.strip(), re.IGNORECASE) for hp in header_patterns)
            if not is_header:
                content_line = ln
                break

        if not content_line:
            content_line = lines[-1]

        raw = content_line.strip("\"'` ")

        # Strip prefixes iteratively
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
                    raw = raw.strip()[len(p):].strip(" :-\t\n\r\"'`#")
                    changed = True
                    break

        # If the response contains a question mark followed by an answer (e.g. 'A dinosaur? Dino-snore!'), take the part after '?'
        if "?" in raw and not raw.endswith("?"):
            parts = raw.split("?", 1)
            after_q = parts[1].strip()
            if len(after_q.split()) >= 1:
                raw = after_q

        # Take first sentence if multiple sentences exist (avoid splitting on abbreviations like No. 2, Dr., etc.)
        sentences = re.split(r"(?<!\bNo)(?<!\bMr)(?<!\bDr)(?<!\bvs)(?<!\be\.g)(?<=[.!?])\s+(?=[A-Z])", raw)
        if sentences:
            raw = sentences[0].strip()

        # Clean trailing punctuation
        raw = raw.rstrip(",;:- ")
        if strip_final_period and raw.endswith("."):
            raw = raw[:-1].strip()

        # Enforce max word limit without cutting off mid-clause on dangling words
        words = raw.split()
        if len(words) > max_words:
            dangling = {"the", "a", "an", "and", "or", "but", "by", "of", "in", "on", "at", "to", "for", "with", "from"}
            trimmed = words[:max_words]
            while len(trimmed) > 1 and trimmed[-1].lower() in dangling:
                trimmed.pop()
            raw = " ".join(trimmed).rstrip(",;:- ")

        raw = raw.strip("\"'*`# ")
        # Capitalize first letter to match phone keyboard auto-capitalization
        if raw:
            raw = raw[0].upper() + raw[1:]
        return raw

    def query_ollama(self, prompt: str, system_prompt: str = "", image_path: str = None, num_predict: int = 35) -> str:
        """
        Calls local Ollama with think=False for ultra-fast, sub-second responses.
        Uses moderate temperature and sufficient token headroom (num_predict) to prevent premature cutoffs.
        """
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "system": system_prompt or "You are a human playing a fast party game on your phone with friends under a 30-second timer. You type quick, short, casual, and believable responses.",
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
            f"You are playing a party game where you complete a pun or joke with a funny punchline.\n"
            f"Prompt: {pun_setup}\n\n"
            f"Instructions:\n"
            f"- Write ONLY the punchline / wordplay completion (1 to 7 words).\n"
            f"- Make it a clever pun or joke punchline fitting the prompt.\n"
            f"- Do NOT repeat the setup.\n"
            f"- Output ONLY the punchline text. No quotes, no explanations, no conversational intro."
        )
        sys_prompt = "You are a witty party game player who writes clever punchlines, puns, and jokes."
        ans = self.query_ollama(prompt, sys_prompt, num_predict=35)
        if ans:
            cleaned = self.clean_human_response(ans, max_words=10, strip_setup=pun_setup)
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
            f"Write ONE short, casual complaint in 3 to 8 words (e.g. 'Broke immediately', 'Cheap plastic garbage', 'Tasted like dirty tap water').\n"
            f"Do not write paragraphs, just sound like an annoyed person typing fast on a phone. No quotes."
        )
        sys_prompt = "You type quick, blunt 3-8 word 1-star complaints on a phone keyboard."
        ans = self.query_ollama(prompt, sys_prompt, num_predict=35)
        if ans:
            cleaned = self.clean_human_response(ans, max_words=11, strip_setup=product_name)
            if cleaned:
                return cleaned
        if fallback_answers:
            chosen = random.choice(fallback_answers)
            return chosen[0].upper() + chosen[1:] if chosen else ""
        return "Broke immediately, waste of money"

    def generate_survey_answers(self, survey_prompt: str, fallback_answers: list = None) -> list:
        prompt = (
            f"Party game like Family Feud. You have 20 seconds on your phone to submit 3 answers.\n"
            f"Question: '{survey_prompt}'\n\n"
            f"Rules:\n"
            f"- Give exactly 3 answers separated by commas.\n"
            f"- Pay close attention to what the question asks (e.g. if it asks for bad things, useless things, or embarrassing things, your answers must match that!).\n"
            f"- Keep each answer very short (1 to 4 words).\n"
            f"- Output ONLY the 3 answers separated by commas. No numbering, no extra text."
        )
        sys_prompt = "You are a party game player answering survey questions with 3 concise answers separated by commas."
        ans = self.query_ollama(prompt, sys_prompt, num_predict=45)
        if ans:
            parts = [self.clean_human_response(p, max_words=5, strip_final_period=True) for p in ans.split(",") if p.strip()]
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
            "Quickly name what you see in 3 to 8 words (e.g. 'cat on top of a red car' or 'dog next to a fire hydrant').\n"
            "Keep it casual, direct, and simple. Do NOT try to make jokes, do not write a paragraph, do not say it is blurry."
        )
        sys_prompt = "You type quick, direct 3-8 word descriptions of what you see in photos for a party game."
        ans = self.query_ollama(prompt, sys_prompt, image_path=image_path, num_predict=35)
        if ans:
            cleaned = self.clean_human_response(ans, max_words=10)
            if cleaned:
                return cleaned
        if fallback_answers:
            chosen = random.choice(fallback_answers)
            return chosen[0].upper() + chosen[1:] if chosen else ""
        return "Looks like a cat on a car"
