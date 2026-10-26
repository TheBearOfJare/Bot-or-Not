#!/usr/bin/env python3
"""
CLI script to automatically generate and expand prompt pools for 'Bot or Not' using local Ollama.

Usage:
  python3 scripts/generate_prompts.py --game pun --count 5
  python3 scripts/generate_prompts.py --game review --count 5
  python3 scripts/generate_prompts.py --game survey --count 5
  python3 scripts/generate_prompts.py --all --count 5
  python3 scripts/generate_prompts.py --all --dry-run
"""

import os
import sys
import json
import argparse
import requests

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import Config

PROMPT_PATHS = {
    "pun": os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "prompts", "pun.json")),
    "review": os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "prompts", "review.json")),
    "survey": os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "prompts", "survey.json")),
}

GAME_GUIDELINES = {
    "pun": {
        "title": "Complete the Pun / Joke Setups",
        "system": (
            "You are a witty comedy writer creating open-ended joke and pun setups for an irreverent party game.\n"
            "CRITICAL RULE: DO NOT write established classic jokes or old dad jokes that have known canonical answers "
            "(e.g. NO 'impasta', NO 'anti-gravity book', NO 'scarecrow outstanding in his field', NO 'golfer with two pants').\n"
            "Instead, write original, open-ended premises that force players to invent their own clever punchline.\n"
            "Every setup should end with '...' or 'is...' or 'because...'."
        ),
        "few_shots": [
            "The secret reason Dracula stopped drinking blood is because...",
            "I tried dating a time traveler, but our relationship...",
            "The worst slogan for a cemetery would definitely be: '...'",
            "A fast food restaurant run entirely by ghosts would be called...",
            "I asked the librarian for books on paranoia, and they whispered...",
            "A scented candle made specifically for introverts smells like...",
            "Scientists discovered a planet made entirely of glitter. They named it...",
            "My smart fridge just locked me out until I..."
        ],
        "format_instruction": "Output ONLY the new setups, one per line. No numbering, no quotes, no conversational intro."
    },
    "review": {
        "title": "1-Star Review Products",
        "system": (
            "You brainstorm everyday items, modern gadgets, and mundane objects for a 1-star review party game.\n"
            "CRITICAL RULE: Choose products where the grievance can be personal, ironic, socially awkward, or a specific functional flaw. "
            "DO NOT just pick generic items where the only complaint is 'it broke' or 'poor quality'.\n"
            "Look for items that induce emotional damage, petty frustration, over-engineered annoyance, or backfired expectations."
        ),
        "few_shots": [
            "A high-end bathroom scale with Bluetooth sync to your phone",
            "A mood ring from a museum gift shop",
            "A self-help book titled 'How to Be Decisive'",
            "A 1000-piece jigsaw puzzle of a clear blue sky",
            "A 'smart' electric toothbrush with a mobile tracking app",
            "A GPS navigation app with celebrity voice pack",
            "A 12-inch clear plastic school ruler",
            "A family pack of 8 hot dog buns (when sausages come in packs of 10)"
        ],
        "format_instruction": "Output ONLY the product names/descriptions, one per line. No numbering, no quotes, no reviews."
    },
    "survey": {
        "title": "Survey Says Questions",
        "system": (
            "You create relatable, fun survey questions for a party game like Family Feud.\n"
            "CRITICAL RULE: DO NOT write questions with super obvious, universally agreed-upon top-3 answers (e.g. 'Name 3 fruits').\n"
            "Instead, write questions that require a SECOND LOGICAL STEP (e.g. a superpower that would also be annoying, "
            "something people love as kids but hate as adults, something that feels like a crime but is legal) "
            "OR open-ended questions pulling from broad relatable human experiences (e.g. excuses for work that wouldn't work, "
            "things people do when they think nobody is watching, something you secretly judge others for at the grocery store).\n"
            "Always start questions with 'Name...'."
        ),
        "few_shots": [
            "Name something people pretend to understand just to look smart.",
            "Name an excuse for being an hour late to work that would NOT work.",
            "Name a superpower that would also be very annoying.",
            "Name something that feels like a crime, but is completely legal.",
            "Name something people buy with the full intention of using, but never do.",
            "Name a minor inconvenience that completely ruins your mood for 10 minutes.",
            "Name something people brag about that isn't actually impressive.",
            "Name an excuse people use to leave a party early without hurting feelings."
        ],
        "format_instruction": "Output ONLY the questions, one per line. No numbering, no quotes, no conversational intro."
    }
}

def load_existing(game_key: str) -> list:
    path = PROMPT_PATHS.get(game_key)
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception as e:
            print(f"[!] Error reading {path}: {e}")
    return []

def save_prompts(game_key: str, prompts: list):
    path = PROMPT_PATHS.get(game_key)
    if not path:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(prompts, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"[✓] Saved {len(prompts)} total prompts to {path}")

def generate_for_game(game_key: str, count: int, model: str, ollama_url: str, dry_run: bool = False):
    meta = GAME_GUIDELINES[game_key]
    existing = load_existing(game_key)
    existing_lowered = {p.strip().lower() for p in existing}

    print(f"\n=======================================================")
    print(f" Generating {count} prompts for: {meta['title']} ({game_key})")
    print(f" Existing prompts in database: {len(existing)}")
    print(f" Using model: {model} at {ollama_url}")
    print(f"=======================================================")

    examples_str = "\n".join(f"- {ex}" for ex in meta["few_shots"])
    user_prompt = (
        f"Generate {count + 4} brand new, unique prompts for our party game.\n\n"
        f"Here are reference examples of the exact style and comedic tone required:\n"
        f"{examples_str}\n\n"
        f"Instructions:\n"
        f"- {meta['format_instruction']}\n"
        f"- Do NOT duplicate the examples.\n"
        f"- Do NOT write numbers, bullet points, asterisks, or markdown."
    )

    payload = {
        "model": model,
        "prompt": user_prompt,
        "system": meta["system"],
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0.85,
            "num_predict": 450
        }
    }

    try:
        res = requests.post(f"{ollama_url}/api/generate", json=payload, timeout=60)
        if res.status_code != 200:
            print(f"[!] Ollama returned status {res.status_code}: {res.text}")
            return
        data = res.json()
        raw_text = data.get("response", "").strip()
    except Exception as e:
        print(f"[!] Failed to connect to Ollama at {ollama_url}: {e}")
        return

    # Parse and clean output lines
    new_candidates = []
    for line in raw_text.splitlines():
        cleaned = line.strip().strip('*`"\'# -•0123456789.)')
        if not cleaned:
            continue
        # Strip leading numbers like "1. ", "12) "
        while len(cleaned) > 2 and (cleaned[0].isdigit() or cleaned[0] in ".-) "):
            cleaned = cleaned[1:].strip()
        cleaned = cleaned.strip('*`"\' ')

        # Sanity check length
        if len(cleaned.split()) < 3:
            continue

        if cleaned.lower() not in existing_lowered:
            new_candidates.append(cleaned)
            existing_lowered.add(cleaned.lower())

    selected = new_candidates[:count]
    if not selected:
        print("[!] No new unique candidates generated. Try again or check Ollama response.")
        return

    print(f"\n[+] Generated {len(selected)} new prompts:")
    for i, p in enumerate(selected, 1):
        print(f"  {i}. {p}")

    if dry_run:
        print("\n[Dry Run] Prompts were not saved to disk.")
    else:
        updated_pool = existing + selected
        save_prompts(game_key, updated_pool)

def main():
    parser = argparse.ArgumentParser(description="Generate new prompt pools for Bot or Not games using Ollama.")
    parser.add_argument("--game", choices=["pun", "review", "survey"], help="Specific minigame to generate for.")
    parser.add_argument("--all", action="store_true", help="Generate for all minigames.")
    parser.add_argument("--count", type=int, default=5, help="Number of new prompts to generate per game (default: 5).")
    parser.add_argument("--model", type=str, default=Config.OLLAMA_MODEL, help="Ollama model name (default: from config).")
    parser.add_argument("--url", type=str, default=Config.OLLAMA_URL, help="Ollama API URL (default: from config).")
    parser.add_argument("--dry-run", action="store_true", help="Display generated prompts without saving to disk.")

    args = parser.parse_args()

    if not args.game and not args.all:
        parser.print_help()
        print("\n[!] Please specify --game [pun|review|survey] or --all.")
        sys.exit(1)

    games = ["pun", "review", "survey"] if args.all else [args.game]
    for g in games:
        generate_for_game(g, count=args.count, model=args.model, ollama_url=args.url, dry_run=args.dry_run)

if __name__ == "__main__":
    main()
