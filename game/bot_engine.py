import os
import io
import re
import difflib
import base64
import random
import requests
from typing import Optional, List, Any, Dict, Tuple
from PIL import Image
from config import Config

CAPTCHA_OBJECTS = [
    "fire hydrant", "school bus", "red car", "bicycle", "motorcycle",
    "traffic light", "stop sign", "cat", "dog", "cow", "bear",
    "slice of pizza", "boat", "train", "bench", "crosswalk", "umbrella"
]

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for", "with",
    "by", "of", "from", "it", "its", "it's", "is", "was", "are", "were", "be",
    "been", "being", "he", "she", "they", "i", "we", "you", "my", "your", "his",
    "her", "their", "because", "so", "that", "this", "just", "very", "really",
    "too", "like", "as", "than", "there", "here", "all", "any", "some", "up", "out"
}

GENERIC_PUN_FALLBACKS = [
    "I have no idea honestly",
    "Nobody knows",
    "Too cheesy to say out loud",
    "They just gave up",
    "It seemed like a good idea at the time",
    "Ask again later",
    "It's a mystery to everyone"
]

GENERIC_REVIEW_FALLBACKS = [
    "Broke after five minutes of use",
    "Terrible quality, completely useless",
    "Do not recommend, huge waste of money",
    "Arrived damaged and smelled weird",
    "0 stars if I could. Awful",
    "Fell apart immediately",
    "Worst purchase I have ever made"
]

GENERIC_SURVEY_FALLBACKS = [
    ["Traffic", "Overslept", "Car trouble"],
    ["My phone", "Procrastination", "Snacks"],
    ["Awkward silence", "Forgetting names", "Spilling coffee"],
    ["House keys", "Wallet", "Phone charger"],
    ["Slow Wi-Fi", "Loud chewing", "Long lines"],
    ["Cold weather", "Alarm clock", "Monday mornings"]
]

GENERIC_CAPTCHA_FALLBACKS = [
    "Looks like a street scene",
    "Car parked near a building",
    "A blurry outdoor photo",
    "Someone standing on a sidewalk",
    "Looks like an animal in a park",
    "A strange abstract object",
    "City street at sunset"
]

def clean_tokens(text: str) -> List[str]:
    """Extract lowercase alphanumeric tokens."""
    return re.findall(r"\b[a-z0-9]+\b", str(text).lower())

def get_content_tokens(text: str, prompt_context: str = "") -> set:
    """Extract content words excluding common stopwords and prompt setup words."""
    toks = clean_tokens(text)
    prompt_words = set(clean_tokens(prompt_context)) if prompt_context else set()
    return {t for t in toks if t not in STOPWORDS and t not in prompt_words}

def are_texts_similar(text1: str, text2: str, prompt_context: str = "", threshold: float = 0.5) -> bool:
    """
    Checks if two texts are semantically or lexically 'more or less the same answer':
    1. Case-insensitive exact match
    2. Normalized match (stripped punctuation, extra spaces)
    3. Token-level Jaccard overlap (>= threshold)
    4. Content-word Jaccard overlap (>= threshold) or content-word subset containment
    5. Substring containment of normalized text
    6. High character-sequence similarity (SequenceMatcher ratio >= 0.68)
    """
    if not text1 or not text2:
        return False

    t1 = str(text1).strip().lower()
    t2 = str(text2).strip().lower()
    if t1 == t2:
        return True

    norm1 = re.sub(r"[^\w\s]", "", t1).strip()
    norm2 = re.sub(r"[^\w\s]", "", t2).strip()
    if norm1 == norm2:
        return True

    # Substring containment on normalized text
    if len(norm1) >= 4 and len(norm2) >= 4:
        if norm1 in norm2 or norm2 in norm1:
            return True

    toks1 = clean_tokens(t1)
    toks2 = clean_tokens(t2)
    if not toks1 or not toks2:
        return False

    set1 = set(toks1)
    set2 = set(toks2)

    # Token-level Jaccard similarity
    union = set1 | set2
    inter = set1 & set2
    if union and (len(inter) / len(union)) >= threshold:
        return True

    # Content-words overlap (filtering stopwords and prompt words)
    c1 = get_content_tokens(t1, prompt_context)
    c2 = get_content_tokens(t2, prompt_context)
    if c1 and c2:
        c_union = c1 | c2
        c_inter = c1 & c2
        if c_union and (len(c_inter) / len(c_union)) >= threshold:
            return True
        # Subset check: if one's content words are completely inside the other
        if len(c1) >= 1 and len(c2) >= 1:
            min_c = min(len(c1), len(c2))
            max_c = max(len(c1), len(c2))
            if (c1.issubset(c2) or c2.issubset(c1)) and (min_c >= 2 or max_c <= 2):
                return True

    # Sequence similarity ratio
    ratio = difflib.SequenceMatcher(None, norm1, norm2).ratio()
    if ratio >= 0.68:
        return True

    return False

def are_survey_responses_similar(list1: List[str], list2: List[str], prompt_context: str = "") -> bool:
    """Returns True if any item in list1 is similar to any item in list2."""
    if not list1 or not list2:
        return False
    return any(are_texts_similar(i1, i2, prompt_context=prompt_context) for i1 in list1 for i2 in list2 if i1 and i2)

def is_response_similar_to_any(response: Any, existing_responses: List[Any], prompt_context: str = "") -> bool:
    """
    Checks if 'response' (either string or survey list) is similar to ANY existing response in existing_responses.
    """
    if not existing_responses:
        return False

    for existing in existing_responses:
        if existing is None:
            continue
        if isinstance(response, list) and isinstance(existing, list):
            if are_survey_responses_similar(response, existing, prompt_context=prompt_context):
                return True
        elif isinstance(response, str) and isinstance(existing, str):
            if are_texts_similar(response, existing, prompt_context=prompt_context):
                return True
        elif isinstance(response, str) and isinstance(existing, list):
            for item in existing:
                if are_texts_similar(response, item, prompt_context=prompt_context):
                    return True
        elif isinstance(response, list) and isinstance(existing, str):
            for item in response:
                if are_texts_similar(item, existing, prompt_context=prompt_context):
                    return True
    return False

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

    def _pick_distinct_fallback(self, fallbacks: list = None, generic_fallbacks: list = None, avoid: list = None, prompt_context: str = "") -> Any:
        """
        Picks a fallback response that is guaranteed not similar to any response in 'avoid'.
        Tries question-specific fallbacks first, then generic fallbacks.
        """
        pool = list(fallbacks or [])
        random.shuffle(pool)
        for fb in pool:
            if not is_response_similar_to_any(fb, avoid or [], prompt_context=prompt_context):
                return fb[0].upper() + fb[1:] if isinstance(fb, str) and fb else fb

        generic_pool = list(generic_fallbacks or [])
        random.shuffle(generic_pool)
        for fb in generic_pool:
            if not is_response_similar_to_any(fb, avoid or [], prompt_context=prompt_context):
                return fb[0].upper() + fb[1:] if isinstance(fb, str) and fb else fb

        if generic_pool:
            return generic_pool[0]
        return "Nobody knows"

    def _pick_distinct_survey_items(self, count: int, fallbacks: list = None, avoid: list = None, prompt_context: str = "") -> List[str]:
        """
        Selects 'count' distinct survey items that do not overlap with each other or any item in 'avoid'.
        """
        items: List[str] = []
        avoid_list = list(avoid or [])

        # 1. Question-specific fallbacks
        pool = list(fallbacks or [])
        random.shuffle(pool)
        for fb in pool:
            if isinstance(fb, str) and fb.strip():
                clean_fb = fb.strip()
                if not is_response_similar_to_any(clean_fb, avoid_list + items, prompt_context=prompt_context):
                    items.append(clean_fb[0].upper() + clean_fb[1:])
                    if len(items) >= count:
                        return items

        # 2. Generic survey fallbacks
        generic_items = [it for set_ in GENERIC_SURVEY_FALLBACKS for it in set_]
        random.shuffle(generic_items)
        for it in generic_items:
            clean_it = it.strip()
            if not is_response_similar_to_any(clean_it, avoid_list + items, prompt_context=prompt_context):
                items.append(clean_it[0].upper() + clean_it[1:])
                if len(items) >= count:
                    return items

        # Emergency filler pool if completely exhausted
        fillers = ["Forgot keys", "Spilled drink", "Lost wallet", "Overslept", "Slow internet", "Long line", "Cold coffee"]
        for it in fillers:
            if not is_response_similar_to_any(it, avoid_list + items, prompt_context=prompt_context):
                items.append(it)
                if len(items) >= count:
                    return items

        while len(items) < count:
            items.append(f"Option {len(items) + 1}")
        return items

    def select_best_candidate(self, prompt_context: str, candidates: list, game_type: str = "joke", avoid_responses: list = None) -> str:
        """
        Runs a rapid single-token judge call to pick the funniest, cleverest candidate out of N options.
        Filters out any candidates that are similar to avoid_responses.
        Falls back to the first valid candidate if selection fails.
        """
        if not candidates:
            return ""

        # Filter out any candidate that is similar to avoid_responses
        valid_candidates = [
            c for c in candidates
            if c and not is_response_similar_to_any(c, avoid_responses or [], prompt_context=prompt_context)
        ]
        if not valid_candidates:
            valid_candidates = [c for c in candidates if c]
            if not valid_candidates:
                return ""

        if len(valid_candidates) == 1:
            return valid_candidates[0]

        options_text = "\n".join(f"{i+1}. {c}" for i, c in enumerate(valid_candidates))
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
                if 0 <= chosen_idx < len(valid_candidates):
                    return valid_candidates[chosen_idx]

        return valid_candidates[0]

    def build_pun_prompt(self, pun_setup: str, extra_instruction: str = "", bot_index: int = 0, avoid_responses: list = None) -> tuple[str, str]:
        if bot_index == 0:
            angle_desc = (
                "- Clever double meaning, literal wordplay, or a natural witty completion (e.g. a time travel relationship that 'had no future', a balloon business that 'never took off')\n"
                "- Relatable truth or witty observation"
            )
            persona = "You are a witty comedian playing a fast party game on your phone, writing punchy, natural, and clever punchlines."
        else:
            angle_desc = (
                "- An absurd, deadpan, or unexpected comic twist (anti-humor, bizarre misdirection, or exaggerated reality)\n"
                "- Sarcastic truth or cynical reaction (e.g. introverts' candle smelling like 'cancelled plans')"
            )
            persona = "You are an offbeat comedian playing a fast party game on your phone, writing unexpected comic twists, deadpan anti-humor, or absurd misdirections."

        prompt = (
            f"You are a witty human player in a party comedy game (like Quiplash or Cards Against Humanity) typing a quick, funny answer on your phone.\n"
            f"Write a hilarious punchline (1 to 6 words) to complete or answer this prompt:\n"
            f"Prompt: {pun_setup}\n\n"
            f"Comedic angle to take:\n"
            f"{angle_desc}\n\n"
            f"CRITICAL RULES:\n"
            f"- Must make grammatical sense in natural English. Do NOT invent gibberish or broken words.\n"
            f"- If the prompt ends with '...', your punchline must complete the sentence seamlessly. Do not repeat the last word of the prompt.\n"
            f"- 1 to 6 words only.\n"
            f"- Output ONLY the punchline. No quotes, no explanations, no conversational intro."
        )

        if avoid_responses:
            clean_avoids = [f"'{r}'" for r in avoid_responses if r]
            if clean_avoids:
                avoid_str = ", ".join(clean_avoids)
                prompt += (
                    f"\n\nSTRICT REQUIREMENT: Another player already answered: {avoid_str}.\n"
                    f"You MUST NOT use these words, synonyms, or the same punchline concept. Give a COMPLETELY DIFFERENT punchline!"
                )

        if extra_instruction:
            prompt += f"\n- {extra_instruction}"
        return prompt, persona

    def generate_pun_punchline(self, pun_setup: str, fallback_answers: list = None, num_candidates: int = 6, avoid_responses: list = None, bot_index: int = 0) -> str:
        prompt, sys_prompt = self.build_pun_prompt(pun_setup, bot_index=bot_index, avoid_responses=avoid_responses)
        
        candidates = []
        for _ in range(num_candidates):
            ans = self.query_ollama(prompt, sys_prompt, num_predict=35, temperature=0.75 + (0.1 if bot_index > 0 else 0.0), top_k=60)
            if ans:
                cleaned = self.clean_human_response(ans, max_words=10, strip_setup=pun_setup)
                if cleaned and cleaned not in candidates and not is_response_similar_to_any(cleaned, avoid_responses or [], prompt_context=pun_setup):
                    candidates.append(cleaned)

        if candidates:
            if len(candidates) > 1:
                return self.select_best_candidate(pun_setup, candidates, game_type="pun", avoid_responses=avoid_responses)
            return candidates[0]

        return self._pick_distinct_fallback(fallback_answers, GENERIC_PUN_FALLBACKS, avoid=avoid_responses, prompt_context=pun_setup)

    def generate_coordinated_pun_punchlines(self, pun_setup: str, bot_count: int = 1, fallback_answers: list = None) -> List[str]:
        """
        Coordinates multiple bots answering the same pun prompt.
        Ensures each bot gets a high-quality answer that is not identical or similar to any other bot.
        """
        if bot_count <= 1:
            return [self.generate_pun_punchline(pun_setup, fallback_answers=fallback_answers, bot_index=0)]

        results: List[str] = []
        candidate_pool: List[str] = []

        # 1. Generate candidates for Bot 1 (Angle 0: clever wordplay / punchy)
        prompt1, sys_prompt1 = self.build_pun_prompt(pun_setup, bot_index=0)
        for _ in range(4):
            ans = self.query_ollama(prompt1, sys_prompt1, num_predict=35, temperature=0.75, top_k=60)
            if ans:
                cleaned = self.clean_human_response(ans, max_words=10, strip_setup=pun_setup)
                if cleaned and cleaned not in candidate_pool:
                    candidate_pool.append(cleaned)

        if candidate_pool:
            b1 = self.select_best_candidate(pun_setup, candidate_pool, game_type="pun") if len(candidate_pool) > 1 else candidate_pool[0]
        else:
            b1 = self._pick_distinct_fallback(fallback_answers, GENERIC_PUN_FALLBACKS, avoid=[], prompt_context=pun_setup)
        results.append(b1)

        # 2. For subsequent bots (Bot 2, etc.):
        for b_idx in range(1, bot_count):
            distinct_candidates = [
                c for c in candidate_pool
                if not is_response_similar_to_any(c, results, prompt_context=pun_setup)
            ]

            b_resp = None
            new_candidates: List[str] = []
            # If candidate pool doesn't have at least 2 distinct options, query Ollama for Bot 2 with explicit avoidance & alternate angle
            if len(distinct_candidates) < 2:
                prompt_b, sys_prompt_b = self.build_pun_prompt(pun_setup, bot_index=b_idx, avoid_responses=results)
                for _ in range(3):
                    ans = self.query_ollama(prompt_b, sys_prompt_b, num_predict=35, temperature=0.85, top_k=60)
                    if ans:
                        cleaned = self.clean_human_response(ans, max_words=10, strip_setup=pun_setup)
                        if cleaned and not is_response_similar_to_any(cleaned, results, prompt_context=pun_setup) and cleaned not in new_candidates:
                            new_candidates.append(cleaned)

            combined_distinct = distinct_candidates + new_candidates
            if combined_distinct:
                if len(combined_distinct) > 1:
                    b_resp = self.select_best_candidate(pun_setup, combined_distinct, game_type="pun", avoid_responses=results)
                else:
                    b_resp = combined_distinct[0]

            if not b_resp or is_response_similar_to_any(b_resp, results, prompt_context=pun_setup):
                b_resp = self._pick_distinct_fallback(fallback_answers, GENERIC_PUN_FALLBACKS, avoid=results, prompt_context=pun_setup)

            results.append(b_resp)

        return results

    def build_review_prompt(self, product_name: str, extra_instruction: str = "", bot_index: int = 0, avoid_responses: list = None) -> tuple[str, str]:
        if bot_index == 0:
            angle_desc = "Focus on a specific ironic design flaw, subtle defect, or awkward personal embarrassment with this product."
            persona = "You type brief, specific, and clear 1-star customer complaints on a phone keyboard."
        else:
            angle_desc = "Focus on an exaggerated dramatic consequence, weird unwanted side effect, or absurdly catastrophic failure."
            persona = "You type dramatic, funny, and chaotic 1-star customer complaints on a phone keyboard."

        prompt = (
            f"You are a human playing a rapid party game on your phone with 20 seconds to answer.\n"
            f"Write a 1-star customer review for: '{product_name}'.\n"
            f"Write ONE short, possibly funny complaint (3 to 10 words).\n"
            f"{angle_desc}\n"
            f"Be creative and relatable (do NOT just say 'it broke' or 'cheap plastic'). Sound like an annoyed customer typing fast on a phone. No quotes. Be funny."
        )

        if avoid_responses:
            clean_avoids = [f"'{r}'" for r in avoid_responses if r]
            if clean_avoids:
                avoid_str = ", ".join(clean_avoids)
                prompt += (
                    f"\n\nSTRICT REQUIREMENT: Another customer already complained: {avoid_str}.\n"
                    f"You MUST complain about a completely DIFFERENT flaw or scenario. Do not repeat their complaint or words."
                )

        if extra_instruction:
            prompt += f"\n- {extra_instruction}"
        return prompt, persona

    def generate_review(self, product_name: str, fallback_answers: list = None, num_candidates: int = 3, avoid_responses: list = None, bot_index: int = 0) -> str:
        prompt, sys_prompt = self.build_review_prompt(product_name, bot_index=bot_index, avoid_responses=avoid_responses)

        candidates = []
        for _ in range(num_candidates):
            ans = self.query_ollama(prompt, sys_prompt, num_predict=35, temperature=0.85 + (0.05 if bot_index > 0 else 0.0), top_k=60)
            if ans:
                cleaned = self.clean_human_response(ans, max_words=11, strip_setup=product_name)
                if cleaned and cleaned not in candidates and not is_response_similar_to_any(cleaned, avoid_responses or [], prompt_context=product_name):
                    candidates.append(cleaned)

        if candidates:
            if len(candidates) > 1:
                return self.select_best_candidate(product_name, candidates, game_type="review", avoid_responses=avoid_responses)
            return candidates[0]

        return self._pick_distinct_fallback(fallback_answers, GENERIC_REVIEW_FALLBACKS, avoid=avoid_responses, prompt_context=product_name)

    def generate_coordinated_reviews(self, product_name: str, bot_count: int = 1, fallback_answers: list = None) -> List[str]:
        """
        Coordinates multiple bots answering the same 1-star review prompt.
        Ensures each bot gets a distinct, funny complaint from different angles.
        """
        if bot_count <= 1:
            return [self.generate_review(product_name, fallback_answers=fallback_answers, bot_index=0)]

        results: List[str] = []
        candidate_pool: List[str] = []

        # 1. Generate for Bot 1 (Angle 0: specific ironic defect)
        prompt1, sys_prompt1 = self.build_review_prompt(product_name, bot_index=0)
        for _ in range(3):
            ans = self.query_ollama(prompt1, sys_prompt1, num_predict=35, temperature=0.85, top_k=60)
            if ans:
                cleaned = self.clean_human_response(ans, max_words=11, strip_setup=product_name)
                if cleaned and cleaned not in candidate_pool:
                    candidate_pool.append(cleaned)

        if candidate_pool:
            b1 = self.select_best_candidate(product_name, candidate_pool, game_type="review") if len(candidate_pool) > 1 else candidate_pool[0]
        else:
            b1 = self._pick_distinct_fallback(fallback_answers, GENERIC_REVIEW_FALLBACKS, avoid=[], prompt_context=product_name)
        results.append(b1)

        # 2. Generate for subsequent bots:
        for b_idx in range(1, bot_count):
            distinct_candidates = [
                c for c in candidate_pool
                if not is_response_similar_to_any(c, results, prompt_context=product_name)
            ]

            b_resp = None
            new_candidates: List[str] = []
            if len(distinct_candidates) < 2:
                prompt_b, sys_prompt_b = self.build_review_prompt(product_name, bot_index=b_idx, avoid_responses=results)
                for _ in range(3):
                    ans = self.query_ollama(prompt_b, sys_prompt_b, num_predict=35, temperature=0.9, top_k=60)
                    if ans:
                        cleaned = self.clean_human_response(ans, max_words=11, strip_setup=product_name)
                        if cleaned and not is_response_similar_to_any(cleaned, results, prompt_context=product_name) and cleaned not in new_candidates:
                            new_candidates.append(cleaned)

            combined_distinct = distinct_candidates + new_candidates
            if combined_distinct:
                if len(combined_distinct) > 1:
                    b_resp = self.select_best_candidate(product_name, combined_distinct, game_type="review", avoid_responses=results)
                else:
                    b_resp = combined_distinct[0]

            if not b_resp or is_response_similar_to_any(b_resp, results, prompt_context=product_name):
                b_resp = self._pick_distinct_fallback(fallback_answers, GENERIC_REVIEW_FALLBACKS, avoid=results, prompt_context=product_name)

            results.append(b_resp)

        return results

    def build_survey_prompt(self, survey_prompt: str, extra_instruction: str = "", bot_index: int = 0, avoid_responses: list = None) -> tuple[str, str]:
        if bot_index == 0:
            angle_desc = "Give 3 common, popular, top-of-mind answers that most people would think of."
        else:
            angle_desc = "Give 3 quirky, funny, or slightly embarrassing alternative answers."

        prompt = (
            f"Party game like Family Feud. You have 20 seconds on your phone to submit 3 answers.\n"
            f"Question: '{survey_prompt}'\n\n"
            f"Rules:\n"
            f"- {angle_desc}\n"
            f"- Give exactly 3 answers separated by commas.\n"
            f"- Pay close attention to what the question asks (e.g. if it asks for bad things, useful things, or embarrassing things, your answers must match that!).\n"
            f"- Keep each answer very short (1 to 4 words).\n"
            f"- Output ONLY the 3 answers separated by commas. No numbering, no extra text. Be funny if the funny answer is true."
        )

        if avoid_responses:
            flat_items = []
            for r in avoid_responses:
                if isinstance(r, list):
                    flat_items.extend(r)
                elif isinstance(r, str) and r:
                    flat_items.append(r)
            if flat_items:
                avoid_str = ", ".join(f"'{it}'" for it in flat_items if it)
                prompt += (
                    f"\n\nSTRICT REQUIREMENT: Another player already submitted: {avoid_str}.\n"
                    f"Do NOT repeat ANY of these answers or synonyms. All 3 of your answers must be completely distinct."
                )

        if extra_instruction:
            prompt += f"\n- {extra_instruction}"
        sys_prompt = "You are a party game player answering survey questions with 3 concise answers separated by commas."
        return prompt, sys_prompt

    def generate_survey_answers(self, survey_prompt: str, fallback_answers: list = None, avoid_responses: list = None, bot_index: int = 0) -> list:
        prompt, sys_prompt = self.build_survey_prompt(survey_prompt, bot_index=bot_index, avoid_responses=avoid_responses)
        ans = self.query_ollama(prompt, sys_prompt, num_predict=45, temperature=0.75 + (0.1 if bot_index > 0 else 0.0), top_k=60)
        parts = []
        if ans:
            parts = [self.clean_human_response(p, max_words=5, strip_final_period=True) for p in ans.split(",") if p.strip()]
            parts = [p for p in parts if p]

        flat_avoid = []
        if avoid_responses:
            for r in avoid_responses:
                if isinstance(r, list):
                    flat_avoid.extend(r)
                elif isinstance(r, str) and r:
                    flat_avoid.append(r)

        valid_items = []
        for p in parts:
            if not is_response_similar_to_any(p, flat_avoid, prompt_context=survey_prompt) and not is_response_similar_to_any(p, valid_items, prompt_context=survey_prompt):
                valid_items.append(p)
            if len(valid_items) == 3:
                break

        if len(valid_items) < 3:
            needed = 3 - len(valid_items)
            fillers = self._pick_distinct_survey_items(needed, fallbacks=fallback_answers, avoid=flat_avoid + valid_items, prompt_context=survey_prompt)
            valid_items.extend(fillers)

        return valid_items[:3]

    def generate_coordinated_survey_answers(self, survey_prompt: str, bot_count: int = 1, fallback_answers: list = None) -> List[List[str]]:
        """
        Coordinates multiple bots answering the same survey question.
        Ensures each bot submits 3 answers and that NO item overlaps across bots.
        """
        if bot_count <= 1:
            return [self.generate_survey_answers(survey_prompt, fallback_answers=fallback_answers, bot_index=0)]

        results: List[List[str]] = []
        all_chosen_items: List[str] = []

        # Bot 1:
        b1_items = self.generate_survey_answers(survey_prompt, fallback_answers=fallback_answers, bot_index=0)
        results.append(b1_items)
        all_chosen_items.extend(b1_items)

        # Subsequent bots:
        for b_idx in range(1, bot_count):
            prompt_b, sys_prompt_b = self.build_survey_prompt(survey_prompt, bot_index=b_idx, avoid_responses=results)
            ans = self.query_ollama(prompt_b, sys_prompt_b, num_predict=45, temperature=0.85, top_k=60)
            candidate_items = []
            if ans:
                parts = [self.clean_human_response(p, max_words=5, strip_final_period=True) for p in ans.split(",") if p.strip()]
                candidate_items = [p for p in parts if p]

            valid_items = []
            for item in candidate_items:
                if not is_response_similar_to_any(item, all_chosen_items, prompt_context=survey_prompt) and not is_response_similar_to_any(item, valid_items, prompt_context=survey_prompt):
                    valid_items.append(item)
                if len(valid_items) == 3:
                    break

            if len(valid_items) < 3:
                needed = 3 - len(valid_items)
                fillers = self._pick_distinct_survey_items(
                    count=needed,
                    fallbacks=fallback_answers,
                    avoid=all_chosen_items + valid_items,
                    prompt_context=survey_prompt
                )
                valid_items.extend(fillers)

            chosen_set = valid_items[:3]
            results.append(chosen_set)
            all_chosen_items.extend(chosen_set)

        return results

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
            f"Describe it like you might title a work of art or caption a meme. Be creative and funny."
            f"Example: 'A supersonic snail crossing the road' or 'Bakery in the woods on fire' "
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

    def build_captcha_prompt(self, bot_index: int = 0, avoid_responses: list = None) -> tuple[str, str]:
        if bot_index == 0:
            prompt = (
                "Look at the attached image. You are playing a rapid party game on your phone with 20 seconds on the clock.\n"
                "Quickly name what you see in 3 to 8 words (e.g. 'cat riding on top of a red car', 'cyberpunk landscape at night', or 'man holding a giant pizza').\n"
                "Keep it casual, direct, and simple. Do not write a paragraph, do not say it is blurry."
            )
            sys_prompt = "You type quick, direct 3-8 word descriptions of what you see in photos for a party game."
        else:
            prompt = (
                "Look at the attached image. You are playing a rapid party game on your phone with 20 seconds on the clock.\n"
                "Give this scene a humorous, witty, or sarcastic caption or artistic title in 3 to 8 words (e.g. 'Neighborhood watch on duty', 'Feline Uber driver', 'Parking lot sunset masterpiece').\n"
                "Sound like a witty human typing a meme caption on a phone. Casual, direct, and funny."
            )
            sys_prompt = "You type witty, sarcastic meme captions or funny titles for photos in a party game."

        if avoid_responses:
            clean_avoids = [f"'{r}'" for r in avoid_responses if r]
            if clean_avoids:
                avoid_str = ", ".join(clean_avoids)
                prompt += (
                    f"\n\nSTRICT REQUIREMENT: Another player already guessed: {avoid_str}.\n"
                    f"Do NOT repeat this description or words. Give a different creative interpretation or humorous title."
                )
        return prompt, sys_prompt

    def generate_captcha_caption(self, image_path: str, fallback_answers: list = None, avoid_responses: list = None, bot_index: int = 0) -> str:
        """
        Feeds ONLY the raw image to Ollama Vision with NO text spoilers or hints.
        """
        prompt, sys_prompt = self.build_captcha_prompt(bot_index=bot_index, avoid_responses=avoid_responses)
        ans = self.query_ollama(prompt, sys_prompt, image_path=image_path, num_predict=35, temperature=0.7 if bot_index == 0 else 0.85)
        if ans:
            cleaned = self.clean_human_response(ans, max_words=10)
            if cleaned and not is_response_similar_to_any(cleaned, avoid_responses or []):
                return cleaned

        return self._pick_distinct_fallback(fallback_answers, GENERIC_CAPTCHA_FALLBACKS, avoid=avoid_responses)

    def generate_coordinated_captcha_captions(self, image_path: str, bot_count: int = 1, fallback_answers: list = None) -> List[str]:
        """
        Coordinates multiple bots captioning the same CAPTCHA image.
        Ensures Bot 1 gives a direct description and Bot 2 gives a humorous/creative caption,
        with zero repetition or near-duplicate phrasing.
        """
        if bot_count <= 1:
            return [self.generate_captcha_caption(image_path, fallback_answers=fallback_answers, bot_index=0)]

        results: List[str] = []

        # Bot 1: Direct description
        prompt1, sys_prompt1 = self.build_captcha_prompt(bot_index=0)
        ans1 = self.query_ollama(prompt1, sys_prompt1, image_path=image_path, num_predict=35)
        b1 = None
        if ans1:
            cleaned1 = self.clean_human_response(ans1, max_words=10)
            if cleaned1:
                b1 = cleaned1

        if not b1:
            b1 = self._pick_distinct_fallback(fallback_answers, GENERIC_CAPTCHA_FALLBACKS, avoid=[])
        results.append(b1)

        # Subsequent bots: Creative / meme caption with explicit avoidance
        for b_idx in range(1, bot_count):
            prompt_b, sys_prompt_b = self.build_captcha_prompt(bot_index=b_idx, avoid_responses=results)
            ans_b = self.query_ollama(prompt_b, sys_prompt_b, image_path=image_path, num_predict=35, temperature=0.85)
            b_resp = None
            if ans_b:
                cleaned_b = self.clean_human_response(ans_b, max_words=10)
                if cleaned_b and not is_response_similar_to_any(cleaned_b, results):
                    b_resp = cleaned_b

            if not b_resp or is_response_similar_to_any(b_resp, results):
                b_resp = self._pick_distinct_fallback(fallback_answers, GENERIC_CAPTCHA_FALLBACKS, avoid=results)

            results.append(b_resp)

        return results

