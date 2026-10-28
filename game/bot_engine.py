import os
import io
import re
import base64
import random
import requests
from typing import Optional, List
from PIL import Image
from config import Config

CAPTCHA_OBJECTS = [
    "fire hydrant", "school bus", "red car", "bicycle", "motorcycle",
    "traffic light", "stop sign", "cat", "dog", "cow", "bear",
    "slice of pizza", "boat", "train", "bench", "crosswalk", "umbrella"
]

class BotEngine:
    def __init__(self, ollama_url: str = None, model: str = None, vision_model: str = None):
        self.ollama_url = ollama_url or Config.OLLAMA_URL
        self.model = model or Config.OLLAMA_MODEL
        self.vision_model = vision_model or getattr(Config, "OLLAMA_VISION_MODEL", self.model)
        self.timeout = Config.OLLAMA_TIMEOUT

    def get_bot_display_name(self) -> str:
        """Bots are simply labeled as a Bot, no individual fake names."""
        return "Bot"

    def prewarm(self):
        """Pre-warm primary Ollama model in background so first game request doesn't suffer cold-start."""
        try:
            payload = {
                "model": self.model,
                "prompt": "hi",
                "stream": False,
                "think": False,
                "options": {"num_predict": 1}
            }
            requests.post(f"{self.ollama_url}/api/generate", json=payload, timeout=self.timeout)
            print(f"[BotEngine] Ollama model '{self.model}' pre-warmed and ready.")
        except Exception as e:
            print(f"[BotEngine] Ollama pre-warm note ({self.model}): {e}")

    def clean_human_response(self, text: str, max_words: int = 12, strip_setup: str = "", strip_final_period: bool = True) -> str:
        """
        Cleans and post-processes LLM output to match real human player behavior:
        - Real humans under a 35s timer type brief, casual phrases (under 12 words).
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
            # Also strip sub-clauses from setup (e.g. after colon or quotes)
            subparts = [p.strip() for p in re.split(r"[:\"'\n]", clean_setup) if len(p.strip().split()) >= 2]
            for sp in subparts:
                if raw.lower().startswith(sp.lower()):
                    raw = raw[len(sp):].strip(" :–-.,")

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

        # Strip leading ellipses, periods, colons, dashes, and whitespace
        raw = re.sub(r"^[\s.:;–—\-…]+", "", raw).strip()

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

        # Final strip of quotes, markdown, and any residual leading ellipses/punctuation
        raw = re.sub(r"^[\s.:;–—\-…]+", "", raw).strip()
        raw = raw.strip("\"'*`# ")
        # Capitalize first letter to match phone keyboard auto-capitalization
        if raw:
            raw = raw[0].upper() + raw[1:]
        return raw

    def query_ollama(self, prompt: str, system_prompt: str = "", image_path: str = None, num_predict: int = 35, temperature: float = 0.7, top_k: int = 40, model_override: str = None) -> str:
        """
        Calls local Ollama with think=False for ultra-fast, sub-second responses.
        Uses moderate temperature and sufficient token headroom (num_predict) to prevent premature cutoffs.
        Automatically routes image inputs to vision_model.
        """
        try:
            target_model = model_override or (self.vision_model if image_path else self.model)
            payload = {
                "model": target_model,
                "prompt": prompt,
                "system": system_prompt or "You are a human playing a fast party game on your phone with friends under a 35-second timer. You type quick, short, casual, and possibly humorous responses.",
                "stream": False,
                "think": False,
                "options": {
                    "temperature": temperature,
                    "top_k": top_k,
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

    def select_best_candidate(self, prompt_context: str, candidates: list, game_type: str = "joke") -> str:
        """
        Runs a rapid single-token judge call to pick the funniest, cleverest candidate out of N options.
        Falls back to the first candidate if selection fails.
        """
        if not candidates:
            return ""
        if len(candidates) == 1:
            return candidates[0]

        options_text = "\n".join(f"{i+1}. {c}" for i, c in enumerate(candidates))
        if game_type == "pun":
            criteria = "Which punchline is the funniest, most clever, and best fitting for a party game?"
        elif game_type == "review":
            criteria = "Which 1-star review is the funniest, most relatable, and most creative complaint?"
        else:
            criteria = "Which response is the funniest and cleverest?"

        judge_prompt = (
            f"Party game prompt: '{prompt_context}'\n\n"
            f"Candidate answers:\n"
            f"{options_text}\n\n"
            f"{criteria}\n"
            f"Output ONLY the single digit of the winner (e.g. 1, 2, or 3). Do not write any other text."
        )
        sys_prompt = "You are an expert comedy judge picking the funniest and cleverest party game response. Prioritize creative use of content and conciseness."

        judge_res = self.query_ollama(
            judge_prompt,
            system_prompt=sys_prompt,
            num_predict=5,
            temperature=0.1,
            top_k=10
        )
        if judge_res:
            digits = re.findall(r"\b([1-9])\b", judge_res)
            if digits:
                chosen_idx = int(digits[0]) - 1
                if 0 <= chosen_idx < len(candidates):
                    return candidates[chosen_idx]

        return candidates[0]

    def build_pun_prompt(self, pun_setup: str, extra_instruction: str = "") -> tuple[str, str]:
        prompt = (
            f"You are a witty human player in a party comedy game (like Quiplash or Cards Against Humanity) typing a quick, funny answer on your phone.\n"
            f"Write a hilarious punchline (1 to 6 words) to complete or answer this prompt:\n"
            f"Prompt: {pun_setup}\n\n"
            f"How to make it funny (pick the angle that fits best):\n"
            f"- Clever double meaning or wordplay that fits naturally (e.g. a timetravel relationship that 'had no future', a balloon business that 'never took off')\n"
            f"- Relatable truth or sarcastic twist (e.g. introverts' candle smelling like 'cancelled plans', coffee called 'liquid sleep substitute')\n"
            f"- An absurd, deadpan, or unexpected punchline\n\n"
            f"CRITICAL RULES:\n"
            f"- Must make grammatical sense in natural English. Do NOT invent gibberish or broken words just to force a pun.\n"
            f"- If the prompt ends with '...', your punchline must complete the sentence seamlessly. Do not repeat the last word of the prompt.\n"
            f"- 1 to 6 words only.\n"
            f"- Output ONLY the punchline. No quotes, no explanations, no conversational intro."
        )
        if extra_instruction:
            prompt += f"\n- {extra_instruction}"
        sys_prompt = "You are a witty comedian playing a fast party game on your phone, writing punchy, natural, and hilarious punchlines."
        return prompt, sys_prompt

    def generate_pun_punchline(self, pun_setup: str, fallback_answers: list = None, num_candidates: int = 6) -> str:
        prompt, sys_prompt = self.build_pun_prompt(pun_setup)
        
        candidates = []
        for _ in range(num_candidates):
            ans = self.query_ollama(prompt, sys_prompt, num_predict=35, temperature=0.75, top_k=60)
            if ans:
                cleaned = self.clean_human_response(ans, max_words=10, strip_setup=pun_setup)
                if cleaned and cleaned not in candidates:
                    candidates.append(cleaned)

        if candidates:
            if len(candidates) > 1:
                return self.select_best_candidate(pun_setup, candidates, game_type="pun")
            return candidates[0]

        if fallback_answers:
            chosen = random.choice(fallback_answers)
            return chosen[0].upper() + chosen[1:] if chosen else ""
        return random.choice([
            "I have no idea honestly",
            "Nobody knows",
            "Too cheesy to say out loud",
            "They just gave up",
            "It seemed like a good idea at the time",
            "Ask again later"
        ])

    def build_review_prompt(self, product_name: str, extra_instruction: str = "") -> tuple[str, str]:
        prompt = (
            f"You are a human playing a rapid party game on your phone with 20 seconds to answer.\n"
            f"Write a 1-star customer review for: '{product_name}'.\n"
            f"Write ONE short, possibly funny complaint (3 to 10 words) about a specific annoying flaw, awkward situation, or ironic downside of this exact product.\n"
            f"Be creative and relatable (do NOT just say 'it broke' or 'cheap plastic'). Sound like an annoyed customer typing fast on a phone. No quotes."
        )
        if extra_instruction:
            prompt += f"\n- {extra_instruction}"
        sys_prompt = "You type brief, specific, and clear 1-star customer complaints on a phone keyboard."
        return prompt, sys_prompt

    def generate_review(self, product_name: str, fallback_answers: list = None, num_candidates: int = 3) -> str:
        prompt, sys_prompt = self.build_review_prompt(product_name)

        candidates = []
        for _ in range(num_candidates):
            ans = self.query_ollama(prompt, sys_prompt, num_predict=35, temperature=0.85, top_k=60)
            if ans:
                cleaned = self.clean_human_response(ans, max_words=11, strip_setup=product_name)
                if cleaned and cleaned not in candidates:
                    candidates.append(cleaned)

        if candidates:
            if len(candidates) > 1:
                return self.select_best_candidate(product_name, candidates, game_type="review")
            return candidates[0]

        if fallback_answers:
            chosen = random.choice(fallback_answers)
            return chosen[0].upper() + chosen[1:] if chosen else ""
        return random.choice([
            "Broke after five minutes of use",
            "Terrible quality, completely useless",
            "Do not recommend, huge waste of money",
            "Arrived damaged and smelled weird",
            "0 stars if I could. Awful",
            "Worst purchase I have ever made"
        ])

    def build_survey_prompt(self, survey_prompt: str, extra_instruction: str = "") -> tuple[str, str]:
        prompt = (
            f"Party game like Family Feud. You have 20 seconds on your phone to submit 3 answers.\n"
            f"Question: '{survey_prompt}'\n\n"
            f"Rules:\n"
            f"- Give exactly 3 answers separated by commas.\n"
            f"- Pay close attention to what the question asks (e.g. if it asks for bad things, useful things, or embarrassing things, your answers must match that!).\n"
            f"- Keep each answer very short (1 to 4 words).\n"
            f"- Output ONLY the 3 answers separated by commas. No numbering, no extra text."
        )
        if extra_instruction:
            prompt += f"\n- {extra_instruction}"
        sys_prompt = "You are a party game player answering survey questions with 3 concise answers separated by commas."
        return prompt, sys_prompt

    def generate_survey_answers(self, survey_prompt: str, fallback_answers: list = None) -> list:
        prompt, sys_prompt = self.build_survey_prompt(survey_prompt)
        ans = self.query_ollama(prompt, sys_prompt, num_predict=45, temperature=0.75, top_k=60)
        if ans:
            parts = [self.clean_human_response(p, max_words=5, strip_final_period=True) for p in ans.split(",") if p.strip()]
            parts = [p for p in parts if p]
            if len(parts) >= 3:
                return parts[:3]
        if fallback_answers and len(fallback_answers) >= 3:
            chosen = random.sample(fallback_answers, 3)
            return [x[0].upper() + x[1:] if x else "" for x in chosen]
        return list(random.choice([
            ["Traffic", "Overslept", "Car trouble"],
            ["My phone", "Procrastination", "Snacks"],
            ["Awkward silence", "Forgetting names", "Spilling coffee"],
            ["House keys", "Wallet", "Phone charger"],
            ["Slow Wi-Fi", "Loud chewing", "Long lines"]
        ]))

    def generate_dynamic_captcha_prompt(self, seed_subject: Optional[str] = None) -> dict:
        """
        Dynamically generates a fresh CAPTCHA prompt on the fly using Ollama,
        intermixing common CAPTCHA subjects with descriptive COCO terms (colors, objects, actions, locations).
        Falls back to a procedural COCO mix if Ollama is offline or times out.
        """
        COCO_COLORS = ["red", "yellow", "blue", "green", "orange", "black", "white", "brown"]
        COCO_ACTIONS = [
            "parked next to", "stopped near", "sitting beside", "standing in front of",
            "crossing near", "waiting beside", "resting under"
        ]
        COCO_LOCATIONS = [
            "a sidewalk in the city", "a street corner", "a crosswalk on the road",
            "a tree in the park", "a sunny street", "a road near a building"
        ]

        if not seed_subject:
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
            "Quickly name what you see in 3 to 8 words (e.g. 'cat riding on top of a red car', 'cyberpunk landscape at night', or 'man holding a giant pizza').\n"
            "Keep it casual, direct, and simple. If you're unsure, give it an artistic name eg. 'parking lot sunset' or something sarcastic eg. 'the mitochondria is the powerhouse of the cell'. Do not write a paragraph, do not say it is blurry."
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
        return random.choice([
            "Looks like a street scene",
            "Car parked near a building",
            "A blurry outdoor photo",
            "Someone standing on a sidewalk",
            "Looks like a cat on a car"
        ])

