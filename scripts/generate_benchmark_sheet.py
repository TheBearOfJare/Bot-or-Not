#!/usr/bin/env python3
"""
Benchmark Runner & Comparison Sheet Generator for 'Bot or Not'.

Generates side-by-side comparison spreadsheets (CSV & Markdown) of Ollama responses
for Pun, Review, and Survey prompts BEFORE and AFTER changes.

Supports rapid testing via command-line arguments:
  # Rapidly test changes to the pun prompt on just the first 3 setups:
  python3 scripts/generate_benchmark_sheet.py pun -n 3

  # Test a brand-new pun prompt setup directly from the command line:
  python3 scripts/generate_benchmark_sheet.py pun -p "The secret reason Dracula stopped drinking blood is because..."

  # Test with an extra on-the-fly prompt instruction:
  python3 scripts/generate_benchmark_sheet.py pun -n 3 -i "Try using portmanteau or witty food puns"

  # Run only reviews and surveys:
  python3 scripts/generate_benchmark_sheet.py review survey -n 5

  # Run in live mode (only current BotEngine, no baseline calls, 2x faster):
  python3 scripts/generate_benchmark_sheet.py pun -n 3 --mode live

  # Run all datasets with full baseline comparison:
  python3 scripts/generate_benchmark_sheet.py --all
"""

import os
import sys
import json
import csv
import re
import time
import random
import argparse
import requests

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import Config
from game.bot_engine import BotEngine

# Default prompt paths
PROMPT_PATHS = {
    "pun": os.path.join(PROJECT_ROOT, "data", "prompts", "pun.json"),
    "review": os.path.join(PROJECT_ROOT, "data", "prompts", "review.json"),
    "survey": os.path.join(PROJECT_ROOT, "data", "prompts", "survey.json"),
}

# ==============================================================================
# Historical Baseline Cleaners & Prompts (BEFORE)
# ==============================================================================

def old_clean(text: str, max_words: int = 12, strip_setup: str = "") -> str:
    """Historical baseline cleaner (did not strip leading ellipses or modern prefixes)."""
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

def get_baseline_prompt(game: str, prompt_text: str) -> tuple[str, str, float, int]:
    """Returns (user_prompt, system_prompt, temperature, top_k) for the historical baseline."""
    if game == "pun":
        prompt = (
            f"You are playing a party game where you complete a pun or joke with a funny punchline.\n"
            f"Prompt: {prompt_text}\n\n"
            f"Instructions:\n"
            f"- Write ONLY the punchline / wordplay completion (1 to 7 words).\n"
            f"- Make it a clever pun or joke punchline fitting the prompt.\n"
            f"- Do NOT repeat the setup.\n"
            f"- Output ONLY the punchline text. No quotes, no explanations, no conversational intro, and no meta humor."
        )
        sys_prompt = "You are a witty party game player who writes clever punchlines, puns, and jokes."
        return prompt, sys_prompt, 0.7, 40
    elif game == "review":
        prompt = (
            f"You are a human playing a rapid party game on your phone with 20 seconds to answer.\n"
            f"Write a 1-star review for: '{prompt_text}'.\n"
            f"Write ONE short, casual complaint in 3 to 8 words (e.g. 'Broke immediately', 'Cheap plastic garbage', 'Tasted like dirty tap water').\n"
            f"Do not write paragraphs, just sound like an annoyed person typing fast on a phone. No quotes."
        )
        sys_prompt = "You type quick, blunt 3-8 word 1-star complaints on a phone keyboard."
        return prompt, sys_prompt, 0.7, 40
    elif game == "survey":
        prompt = (
            f"Party game like Family Feud. You have 20 seconds on your phone to submit 3 answers.\n"
            f"Question: '{prompt_text}'\n\n"
            f"Rules:\n"
            f"- Give exactly 3 answers separated by commas.\n"
            f"- Pay close attention to what the question asks (e.g. if it asks for bad things, useful things, or embarrassing things, your answers must match that!).\n"
            f"- Keep each answer very short (1 to 4 words).\n"
            f"- Output ONLY the 3 answers separated by commas. No numbering, no extra text."
        )
        sys_prompt = "You are a party game player answering survey questions with 3 concise answers separated by commas."
        return prompt, sys_prompt, 0.7, 40
    return prompt_text, "", 0.7, 40

# ==============================================================================
# Low-level Ollama Caller (with fallback)
# ==============================================================================

def call_ollama(
    prompt: str,
    sys_prompt: str,
    temp: float,
    top_k: int,
    num_predict: int = 35,
    model: str = None,
    url: str = None
) -> str:
    url = url or Config.OLLAMA_URL
    model = model or Config.OLLAMA_MODEL
    try:
        res = requests.post(
            f"{url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "system": sys_prompt,
                "stream": False,
                "think": False,
                "options": {
                    "temperature": temp,
                    "top_k": top_k,
                    "num_predict": num_predict,
                },
            },
            timeout=Config.OLLAMA_TIMEOUT or 30,
        )
        if res.status_code == 200:
            return res.json().get("response", "").strip()
        else:
            print(f"[!] Ollama returned status {res.status_code}: {res.text}")
    except Exception as e:
        print(f"[!] Error querying Ollama at {url}: {e}")
    return ""

# ==============================================================================
# Prompt Loading & Normalization
# ==============================================================================

def normalize_game_name(name: str) -> str:
    name = name.strip().lower()
    mapping = {
        "pun": "pun", "puns": "pun",
        "review": "review", "reviews": "review",
        "survey": "survey", "surveys": "survey", "survey_says": "survey"
    }
    return mapping.get(name, name)

def load_prompts(game: str, custom_file: str = None, direct_prompts: list = None) -> list:
    """Loads prompt strings from CLI arguments, custom file, or standard JSON files."""
    if direct_prompts:
        return direct_prompts

    file_path = custom_file or PROMPT_PATHS.get(game)
    if not file_path or not os.path.exists(file_path):
        print(f"[!] Prompt file not found: {file_path}")
        return []

    try:
        if file_path.endswith(".json"):
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return [str(p).strip() for p in data if str(p).strip()]
        else:
            with open(file_path, "r", encoding="utf-8") as f:
                return [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"[!] Failed to read {file_path}: {e}")
    return []

# ==============================================================================
# Benchmarking Engine
# ==============================================================================

def run_benchmark(args):
    bot = BotEngine(ollama_url=args.url, model=args.model)

    # Determine games to run
    selected_games = []
    if args.all:
        selected_games = ["pun", "review", "survey"]
    elif args.datasets:
        for d in args.datasets:
            norm = normalize_game_name(d)
            if norm == "all":
                selected_games = ["pun", "review", "survey"]
                break
            if norm in PROMPT_PATHS and norm not in selected_games:
                selected_games.append(norm)
    elif args.games:
        for g in args.games:
            norm = normalize_game_name(g)
            if norm in PROMPT_PATHS and norm not in selected_games:
                selected_games.append(norm)
    elif args.prompt:
        # Default to 'pun' if custom prompt provided without explicit game
        selected_games = ["pun"]
    else:
        # Default to all if nothing specified
        selected_games = ["pun", "review", "survey"]

    if not selected_games:
        print("[!] No valid games or datasets specified. Choose from: pun, review, survey (or 'all').")
        sys.exit(1)

    # Verify Ollama connection
    try:
        check = requests.get(f"{args.url}/api/tags", timeout=5)
        if check.status_code != 200:
            print(f"[!] Warning: Ollama returned status {check.status_code} at {args.url}")
    except Exception as e:
        print(f"\n[!] ERROR: Could not connect to Ollama at {args.url}: {e}")
        print("    Make sure Ollama is running (`ollama serve`).\n")
        if not args.dry_run:
            sys.exit(1)

    repeats = max(1, args.repeats)
    mode = args.mode.lower()
    is_compare = (mode == "compare")

    print("\n" + "=" * 76)
    print(f" Bot or Not // Benchmark Runner")
    print(f" Model:     {args.model} ({args.url})")
    print(f" Mode:      {mode.upper()} {'(BEFORE baseline vs AFTER active engine)' if is_compare else '(ACTIVE ENGINE ONLY)'}")
    print(f" Datasets:  {', '.join(selected_games)}")
    print(f" Repeats:   {repeats} per prompt")
    if args.limit:
        print(f" Limit:     {args.limit} prompts per dataset")
    if args.sample:
        print(f" Sample:    Randomly picking {args.sample} prompts per dataset")
    if args.instruction:
        print(f" Extra:     \"{args.instruction}\"")
    print(f" Output:    {args.output}")
    print("=" * 76 + "\n")

    all_results = []
    total_start_time = time.time()

    for game_idx, game in enumerate(selected_games, 1):
        # Load dataset
        prompts = load_prompts(
            game=game,
            custom_file=args.file if len(selected_games) == 1 else None,
            direct_prompts=args.prompt if len(selected_games) == 1 else None
        )

        if not prompts:
            print(f"[-] No prompts found for game '{game}'. Skipping.")
            continue

        # Handle sampling, offset, and limit
        if args.sample and args.sample < len(prompts):
            prompts = random.sample(prompts, args.sample)
        else:
            if args.offset:
                prompts = prompts[args.offset:]
            if args.limit:
                prompts = prompts[:args.limit]

        print(f"[{game_idx}/{len(selected_games)}] Benchmarking '{game}' ({len(prompts)} prompts)...")

        for p_idx, prompt_text in enumerate(prompts, 1):
            p_start = time.time()
            if not args.quiet:
                short_text = (prompt_text[:68] + "...") if len(prompt_text) > 70 else prompt_text
                print(f"\n  [{p_idx}/{len(prompts)}] {short_text}")

            before_resps = []
            after_resps = []
            judge_winner = ""

            # ------------------------------------------------------------------
            # 1. BASELINE (BEFORE) - only if compare mode
            # ------------------------------------------------------------------
            if is_compare and not args.dry_run:
                base_prompt, base_sys, base_temp, base_top_k = get_baseline_prompt(game, prompt_text)
                for _ in range(repeats):
                    if game == "survey":
                        raw = call_ollama(base_prompt, base_sys, base_temp, base_top_k, num_predict=45, model=args.model, url=args.url)
                        parts = [old_clean(p, max_words=5) for p in raw.split(",") if p.strip()]
                        before_resps.append(" | ".join(parts[:3]))
                    else:
                        max_w = 10 if game == "pun" else 11
                        raw = call_ollama(base_prompt, base_sys, base_temp, base_top_k, num_predict=35, model=args.model, url=args.url)
                        cleaned = old_clean(raw, max_words=max_w, strip_setup=prompt_text)
                        before_resps.append(cleaned)

            # ------------------------------------------------------------------
            # 2. ACTIVE / EXPERIMENTAL (AFTER)
            # ------------------------------------------------------------------
            if not args.dry_run:
                # Build active prompt using BotEngine helper methods
                if game == "pun":
                    active_prompt, active_sys = bot.build_pun_prompt(prompt_text, extra_instruction=args.instruction or "")
                    temp = args.temperature if args.temperature is not None else 0.85
                    top_k = args.top_k if args.top_k is not None else 50
                    max_w = 10
                elif game == "review":
                    active_prompt, active_sys = bot.build_review_prompt(prompt_text, extra_instruction=args.instruction or "")
                    temp = args.temperature if args.temperature is not None else 0.85
                    top_k = args.top_k if args.top_k is not None else 60
                    max_w = 11
                elif game == "survey":
                    active_prompt, active_sys = bot.build_survey_prompt(prompt_text, extra_instruction=args.instruction or "")
                    temp = args.temperature if args.temperature is not None else 0.75
                    top_k = args.top_k if args.top_k is not None else 60
                    max_w = 5
                else:
                    active_prompt = prompt_text
                    active_sys = ""
                    temp = 0.75
                    top_k = 50
                    max_w = 12

                # Allow full prompt template override if passed
                if args.custom_prompt:
                    active_prompt = args.custom_prompt.replace("{prompt}", prompt_text).replace("{setup}", prompt_text)
                if args.system_prompt:
                    active_sys = args.system_prompt

                # Generate candidates
                for _ in range(repeats):
                    if game == "survey":
                        raw = bot.query_ollama(active_prompt, active_sys, num_predict=45, temperature=temp, top_k=top_k)
                        if raw:
                            parts = [bot.clean_human_response(p, max_words=5, strip_final_period=True) for p in raw.split(",") if p.strip()]
                            parts = [p for p in parts if p]
                            after_resps.append(" | ".join(parts[:3]))
                        else:
                            after_resps.append("")
                    else:
                        raw = bot.query_ollama(active_prompt, active_sys, num_predict=35, temperature=temp, top_k=top_k)
                        cleaned = bot.clean_human_response(raw, max_words=max_w, strip_setup=prompt_text)
                        after_resps.append(cleaned)

                # Comedy Judge selection across generated candidates
                valid_candidates = [c for c in after_resps if c.strip()]
                if args.judge and len(valid_candidates) > 1 and game in ("pun", "review"):
                    judge_winner = bot.select_best_candidate(prompt_text, valid_candidates, game_type=game)
                elif valid_candidates:
                    judge_winner = valid_candidates[0]

            elapsed = time.time() - p_start

            # Live terminal output
            if not args.quiet:
                if is_compare:
                    print("     BEFORE [baseline]:")
                    for idx, b in enumerate(before_resps, 1):
                        print(f"       {idx}. {b}")
                    print("     AFTER [active engine]:")
                    for idx, a in enumerate(after_resps, 1):
                        is_win = " (★)" if a == judge_winner and judge_winner else ""
                        print(f"       {idx}. {a}{is_win}")
                else:
                    print("     RESPONSES:")
                    for idx, a in enumerate(after_resps, 1):
                        is_win = " (★)" if a == judge_winner and judge_winner else ""
                        print(f"       {idx}. {a}{is_win}")

                if judge_winner and len(after_resps) > 1 and game in ("pun", "review"):
                    print(f"     🏆 Judge Winner: \"{judge_winner}\"")
                print(f"     ⏱  Done in {elapsed:.1f}s")

            # Format record for CSV/Markdown
            record = {
                "game": game,
                "prompt": prompt_text,
            }

            if is_compare:
                for i in range(repeats):
                    record[f"before_{i+1}"] = before_resps[i] if i < len(before_resps) else ""
                for i in range(repeats):
                    record[f"after_{i+1}"] = after_resps[i] if i < len(after_resps) else ""
            else:
                for i in range(repeats):
                    record[f"response_{i+1}"] = after_resps[i] if i < len(after_resps) else ""

            if args.judge and game in ("pun", "review"):
                record["judge_winner"] = judge_winner

            all_results.append(record)

    # --------------------------------------------------------------------------
    # Export Results
    # --------------------------------------------------------------------------
    if args.dry_run:
        print("\n[Dry Run] Completed without querying Ollama.")
        return

    csv_path = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    if all_results:
        fieldnames = list(all_results[0].keys())
        try:
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_results)
            print(f"\n[✓] Successfully saved benchmark CSV: {csv_path}")
        except PermissionError:
            fallback = csv_path.replace(".csv", f"_{int(time.time())}.csv")
            with open(fallback, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_results)
            print(f"\n[!] Primary file locked. Saved to fallback: {fallback}")

    # Optional Markdown export
    if args.markdown:
        md_path = os.path.splitext(csv_path)[0] + ".md"
        try:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(f"# Bot or Not // Benchmark Results\n\n")
                f.write(f"- **Model**: `{args.model}`\n")
                f.write(f"- **Mode**: `{mode}`\n")
                f.write(f"- **Prompts Evaluated**: {len(all_results)}\n\n")

                if all_results:
                    headers = list(all_results[0].keys())
                    f.write("| " + " | ".join(headers) + " |\n")
                    f.write("| " + " | ".join(["---"] * len(headers)) + " |\n")
                    for row in all_results:
                        f.write("| " + " | ".join(str(row.get(h, "")).replace("|", "\\|") for h in headers) + " |\n")
            print(f"[✓] Saved Markdown summary: {md_path}")
        except Exception as e:
            print(f"[!] Could not write Markdown file: {e}")

    total_elapsed = time.time() - total_start_time
    print(f"[✓] Benchmarking finished in {total_elapsed:.1f}s ({len(all_results)} total prompts tested).\n")

# ==============================================================================
# CLI Entrypoint
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Run benchmarks for Bot or Not prompt datasets (pun, review, survey) with side-by-side comparisons.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Rapidly test changes to the pun prompt on just 3 setups:
  python3 scripts/generate_benchmark_sheet.py pun -n 3

  # Test a brand new pun setup right from the command line:
  python3 scripts/generate_benchmark_sheet.py pun -p "The worst slogan for a cemetery would definitely be: '...'"

  # Test on-the-fly extra instruction:
  python3 scripts/generate_benchmark_sheet.py pun -n 3 -i "Use clever rhymes or portmanteau words"

  # Run only reviews and surveys:
  python3 scripts/generate_benchmark_sheet.py review survey -n 5

  # Run in live mode (only tests active BotEngine, no baseline calls, 2x faster):
  python3 scripts/generate_benchmark_sheet.py pun -n 3 --mode live

  # Run all datasets with full baseline comparison:
  python3 scripts/generate_benchmark_sheet.py --all
        """
    )

    # Positional argument for datasets
    parser.add_argument(
        "datasets",
        nargs="*",
        help="One or more datasets to run: pun, review, survey (or 'all')."
    )

    # Flags for dataset filtering
    parser.add_argument("-g", "--games", "--datasets", dest="games", nargs="+", help="Specific dataset(s) to benchmark (e.g. -g pun review).")
    parser.add_argument("--all", action="store_true", help="Benchmark all prompt datasets (pun, review, survey).")

    # Prompt overrides / rapid testing
    parser.add_argument("-p", "--prompt", action="append", help="Direct prompt setup(s) to test from the command line.")
    parser.add_argument("-f", "--file", type=str, help="Path to a custom JSON or text file containing test prompts.")
    parser.add_argument("-n", "--limit", "--count", type=int, help="Maximum number of prompts to evaluate per dataset.")
    parser.add_argument("-s", "--sample", type=int, help="Randomly sample N prompts instead of evaluating in order.")
    parser.add_argument("--offset", type=int, default=0, help="Start at index offset in prompt list.")
    parser.add_argument("-r", "--repeats", type=int, default=3, help="Number of responses to generate per prompt (default: 3).")

    # Prompt tweaks & engine overrides
    parser.add_argument("-i", "--instruction", type=str, help="Extra instruction to append to the prompt instructions.")
    parser.add_argument("--custom-prompt", type=str, help="Full user prompt override (use {prompt} for the setup/product/question placeholder).")
    parser.add_argument("--system-prompt", type=str, help="System prompt override.")
    parser.add_argument("-m", "--model", type=str, default=Config.OLLAMA_MODEL, help=f"Ollama model name (default: {Config.OLLAMA_MODEL}).")
    parser.add_argument("-t", "--temperature", type=float, help="Temperature override for generation.")
    parser.add_argument("--top-k", type=int, help="top_k override for generation.")
    parser.add_argument("--url", type=str, default=Config.OLLAMA_URL, help=f"Ollama API URL (default: {Config.OLLAMA_URL}).")
    parser.add_argument("--no-judge", dest="judge", action="store_false", default=True, help="Disable comedy judge candidate selection.")

    # Execution & output modes
    parser.add_argument("--mode", choices=["compare", "live"], default="compare", help="Mode: 'compare' (BEFORE vs AFTER) or 'live' (AFTER only). Default: compare.")
    parser.add_argument("-o", "--output", type=str, default=os.path.join(PROJECT_ROOT, "data", "benchmark_comparison.csv"), help="Output CSV file path.")
    parser.add_argument("--md", "--markdown", dest="markdown", action="store_true", default=True, help="Also export Markdown table summary (default: True).")
    parser.add_argument("--no-md", dest="markdown", action="store_false", help="Disable Markdown summary export.")
    parser.add_argument("-q", "--quiet", action="store_true", help="Quiet mode (suppress live console printing).")
    parser.add_argument("--dry-run", action="store_true", help="Display matched prompts without querying Ollama.")

    args = parser.parse_args()
    run_benchmark(args)

if __name__ == "__main__":
    main()
