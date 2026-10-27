#!/usr/bin/env python3
"""
Generates a side-by-side comparison spreadsheet (CSV & Markdown) of Ollama responses
for every prompt in Pun, Review, and Survey minigames BEFORE and AFTER changes.
"""

import os
import sys
import json
import csv
import re
import requests
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import Config

OLLAMA_URL = Config.OLLAMA_URL
MODEL = Config.OLLAMA_MODEL

def old_clean(text: str, max_words: int = 12, strip_setup: str = "") -> str:
    """Simulates the previous cleaning function (which did not strip leading ellipses)."""
    if not text:
        return ""
    raw = text.strip()
    raw = re.sub(r"[*_`#~]", "", raw).strip("\"'` ")
    if strip_setup and strip_setup.lower() in raw.lower():
        pattern = re.escape(strip_setup) + r"[\s.?:–-]*"
        raw = re.sub(pattern, "", raw, flags=re.IGNORECASE).strip()
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if lines:
        raw = lines[0].strip("\"'` ")
    # Take first sentence
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", raw)
    if sentences:
        raw = sentences[0].strip()
    raw = raw.rstrip(",;:- ")
    if raw.endswith("."):
        raw = raw[:-1].strip()
    words = raw.split()
    if len(words) > max_words:
        raw = " ".join(words[:max_words]).rstrip(",;:- ")
    raw = raw.strip("\"'*`# ")
    if raw:
        raw = raw[0].upper() + raw[1:]
    return raw

def new_clean(text: str, max_words: int = 12, strip_setup: str = "") -> str:
    """Uses the updated cleaning function that rigorously strips leading ellipses, colons, dashes."""
    if not text:
        return ""
    raw = text.strip()
    raw = re.sub(r"[*_`#~]", "", raw).strip("\"'` ")
    if strip_setup and strip_setup.lower() in raw.lower():
        pattern = re.escape(strip_setup) + r"[\s.?:–-]*"
        raw = re.sub(pattern, "", raw, flags=re.IGNORECASE).strip()
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if lines:
        raw = lines[0].strip("\"'` ")
    # Strip prefixes
    for p in ["punchline:", "review:", "1-star review:", "because:", "because "]:
        if raw.lower().startswith(p):
            raw = raw[len(p):].strip()
    # Strip leading ellipses, periods, colons, hyphens
    raw = re.sub(r"^[\s.:;–—\-…]+", "", raw).strip()
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", raw)
    if sentences:
        raw = sentences[0].strip()
    raw = raw.rstrip(",;:- ")
    if raw.endswith("."):
        raw = raw[:-1].strip()
    words = raw.split()
    if len(words) > max_words:
        raw = " ".join(words[:max_words]).rstrip(",;:- ")
    raw = re.sub(r"^[\s.:;–—\-…]+", "", raw).strip()
    raw = raw.strip("\"'*`# ")
    if raw:
        raw = raw[0].upper() + raw[1:]
    return raw

def call_ollama(prompt: str, sys_prompt: str, temp: float, top_k: int, num_predict: int = 35) -> str:
    try:
        res = requests.post(f"{OLLAMA_URL}/api/generate", json={
            "model": MODEL,
            "prompt": prompt,
            "system": sys_prompt,
            "stream": False,
            "think": False,
            "options": {
                "temperature": temp,
                "top_k": top_k,
                "num_predict": num_predict
            }
        }, timeout=30)
        if res.status_code == 200:
            return res.json().get("response", "").strip()
    except Exception as e:
        print(f"Error querying Ollama: {e}")
    return ""

def main():
    puns_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "prompts", "pun.json"))
    reviews_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "prompts", "review.json"))
    surveys_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "prompts", "survey.json"))

    with open(puns_path, "r", encoding="utf-8") as f:
        puns = json.load(f)
    with open(reviews_path, "r", encoding="utf-8") as f:
        reviews = json.load(f)
    with open(surveys_path, "r", encoding="utf-8") as f:
        surveys = json.load(f)

    print(f"Running benchmarks for:")
    print(f"  - {len(puns)} Pun setups (3 responses each, before & after)")
    print(f"  - {len(reviews)} Review products (3 responses each, before & after)")
    print(f"  - {len(surveys)} Survey questions (1 response each, before & after)")

    results = []

    # 1. PUNS
    print("\n[1/3] Benchmarking Puns...")
    for idx, setup in enumerate(puns, 1):
        print(f"  Puns {idx}/{len(puns)}: {setup[:40]}...")
        # BEFORE
        before_resps = []
        for _ in range(3):
            prompt = (
                f"You are playing a party game where you complete a pun or joke with a funny punchline.\n"
                f"Prompt: {setup}\n\n"
                f"Instructions:\n"
                f"- Write ONLY the punchline / wordplay completion (1 to 7 words).\n"
                f"- Make it a clever pun or joke punchline fitting the prompt.\n"
                f"- Do NOT repeat the setup.\n"
                f"- Output ONLY the punchline text. No quotes, no explanations, no conversational intro, and no meta humor."
            )
            raw = call_ollama(prompt, "You are a witty party game player who writes clever punchlines, puns, and jokes.", 0.7, 40)
            before_resps.append(old_clean(raw, max_words=10, strip_setup=setup))

        # AFTER
        after_resps = []
        for _ in range(3):
            prompt = (
                f"You are playing a party game where you complete a pun or joke with a funny punchline.\n"
                f"Prompt: {setup}\n\n"
                f"Instructions:\n"
                f"- Write ONLY the punchline / wordplay completion (1 to 7 words).\n"
                f"- Make it a clever pun or joke punchline fitting the prompt.\n"
                f"- Do NOT repeat the setup.\n"
                f"- Output ONLY the punchline text. Do NOT start with ellipses or dots (...).\n"
                f"- No quotes, no explanations, no conversational intro, and no meta humor."
            )
            raw = call_ollama(prompt, "You are a witty party game player who writes clever punchlines, puns, and jokes.", 0.75, 50)
            after_resps.append(new_clean(raw, max_words=10, strip_setup=setup))

        results.append({
            "game": "pun",
            "prompt": setup,
            "before_1": before_resps[0],
            "before_2": before_resps[1],
            "before_3": before_resps[2],
            "after_1": after_resps[0],
            "after_2": after_resps[1],
            "after_3": after_resps[2]
        })

    # 2. REVIEWS
    print("\n[2/3] Benchmarking Reviews...")
    for idx, prod in enumerate(reviews, 1):
        print(f"  Reviews {idx}/{len(reviews)}: {prod[:40]}...")
        # BEFORE
        before_resps = []
        for _ in range(3):
            prompt = (
                f"You are a human playing a rapid party game on your phone with 20 seconds to answer.\n"
                f"Write a 1-star review for: '{prod}'.\n"
                f"Write ONE short, casual complaint in 3 to 8 words (e.g. 'Broke immediately', 'Cheap plastic garbage', 'Tasted like dirty tap water').\n"
                f"Do not write paragraphs, just sound like an annoyed person typing fast on a phone. No quotes."
            )
            raw = call_ollama(prompt, "You type quick, blunt 3-8 word 1-star complaints on a phone keyboard.", 0.7, 40)
            before_resps.append(old_clean(raw, max_words=11, strip_setup=prod))

        # AFTER
        after_resps = []
        for _ in range(3):
            prompt = (
                f"You are a human playing a rapid party game on your phone with 20 seconds to answer.\n"
                f"Write a 1-star customer review for: '{prod}'.\n"
                f"Write ONE short, funny complaint (3 to 10 words) about a specific annoying flaw, awkward situation, or ironic downside of this exact product.\n"
                f"Be creative and relatable (do NOT just say 'it broke' or 'cheap plastic'). Sound like an annoyed customer typing fast on a phone. No quotes."
            )
            raw = call_ollama(prompt, "You type quick, witty, and blunt 1-star customer complaints on a phone keyboard.", 0.8, 60)
            after_resps.append(new_clean(raw, max_words=11, strip_setup=prod))

        results.append({
            "game": "review",
            "prompt": prod,
            "before_1": before_resps[0],
            "before_2": before_resps[1],
            "before_3": before_resps[2],
            "after_1": after_resps[0],
            "after_2": after_resps[1],
            "after_3": after_resps[2]
        })

    # 3. SURVEYS
    print("\n[3/3] Benchmarking Surveys...")
    for idx, q in enumerate(surveys, 1):
        print(f"  Surveys {idx}/{len(surveys)}: {q[:40]}...")
        # BEFORE
        prompt = (
            f"Party game like Family Feud. You have 20 seconds on your phone to submit 3 answers.\n"
            f"Question: '{q}'\n\n"
            f"Rules:\n"
            f"- Give exactly 3 answers separated by commas.\n"
            f"- Pay close attention to what the question asks (e.g. if it asks for bad things, useful things, or embarrassing things, your answers must match that!).\n"
            f"- Keep each answer very short (1 to 4 words).\n"
            f"- Output ONLY the 3 answers separated by commas. No numbering, no extra text."
        )
        raw_before = call_ollama(prompt, "You are a party game player answering survey questions with 3 concise answers separated by commas.", 0.7, 40, num_predict=45)
        b_parts = [old_clean(p, max_words=5) for p in raw_before.split(",") if p.strip()]
        before_str = " | ".join(b_parts[:3])

        # AFTER
        raw_after = call_ollama(prompt, "You are a party game player answering survey questions with 3 concise answers separated by commas.", 0.75, 50, num_predict=45)
        a_parts = [new_clean(p, max_words=5) for p in raw_after.split(",") if p.strip()]
        after_str = " | ".join(a_parts[:3])

        results.append({
            "game": "survey",
            "prompt": q,
            "before_1": before_str,
            "before_2": "",
            "before_3": "",
            "after_1": after_str,
            "after_2": "",
            "after_3": ""
        })

    # Export to CSV
    csv_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "benchmark_comparison.csv"))
    os.makedirs(os.path.dirname(csv_file), exist_ok=True)
    fieldnames = ["game", "prompt", "before_1", "before_2", "before_3", "after_1", "after_2", "after_3"]
    with open(csv_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\n[✓] Successfully generated benchmark CSV: {csv_file}")

if __name__ == "__main__":
    main()
