import os
import json
import time
import random
import threading
from typing import Dict, Any, List, Set, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_LOG_FILE = os.path.join(PROJECT_ROOT, "data", "used_prompts.log")

class PromptTracker:
    """
    Temporary session-based prompt tracker.
    
    Keeps track of what prompts have been used since the program launched
    to avoid repeats until all available prompts in a minigame's pool
    have been cycled through.
    
    Maintains both an in-memory chronological history and an on-disk session
    log file (data/used_prompts.log), both initialized fresh on program launch.
    """
    def __init__(self, log_file_path: Optional[str] = DEFAULT_LOG_FILE):
        self._lock = threading.RLock()
        self._log_file_path = log_file_path
        
        # game_id -> set of prompt keys used in the current cycle
        self._used_in_cycle: Dict[str, Set[str]] = {}
        
        # game_id -> current cycle count (starts at 1)
        self._cycles: Dict[str, int] = {}
        
        # Complete chronological list of all prompt usages since launch
        self._history_log: List[Dict[str, Any]] = []
        
        # Initialize the session log file on startup
        self.init_session_log()

    def init_session_log(self):
        """Initializes/resets the temporary prompt log on launch."""
        with self._lock:
            self._used_in_cycle.clear()
            self._cycles.clear()
            self._history_log.clear()
            
            if self._log_file_path:
                try:
                    os.makedirs(os.path.dirname(self._log_file_path), exist_ok=True)
                    start_str = time.strftime("%Y-%m-%d %H:%M:%S")
                    with open(self._log_file_path, "w", encoding="utf-8") as f:
                        f.write("================================================================================\n")
                        f.write("🤖 Bot or Not - Temporary Session Prompt Log\n")
                        f.write(f"Session Started: {start_str}\n")
                        f.write("Tracks all prompts used since program launch to avoid repeats until cycled.\n")
                        f.write("================================================================================\n\n")
                    print(f"[PromptTracker] Session prompt log initialized at {self._log_file_path}")
                except Exception as e:
                    print(f"[PromptTracker] Error initializing log file {self._log_file_path}: {e}")

    @staticmethod
    def get_prompt_key(item: Any) -> str:
        """Extracts a unique, stable string key for any prompt item (string, dict, etc.)."""
        if isinstance(item, str):
            return item.strip()
        if isinstance(item, dict):
            for k in ("setup", "product", "question", "prompt", "seed", "title"):
                val = item.get(k)
                if val and isinstance(val, str):
                    return val.strip()
            try:
                return json.dumps(item, sort_keys=True)
            except Exception:
                return str(item).strip()
        return str(item).strip()

    @staticmethod
    def get_prompt_display(item: Any) -> str:
        """Returns a clean, readable string representation for logging."""
        if isinstance(item, str):
            return item.strip()
        if isinstance(item, dict):
            if "setup" in item:
                return f"Pun Setup: \"{item['setup']}\""
            if "product" in item:
                return f"Product: \"{item['product']}\""
            if "question" in item:
                return f"Survey: \"{item['question']}\""
            if "prompt" in item:
                return f"Prompt: \"{item['prompt']}\""
            if "title" in item:
                return f"Title: \"{item['title']}\""
            return str(item)
        return str(item)

    def _append_to_log_file(self, text: str):
        """Appends formatted text to the session log file."""
        if not self._log_file_path:
            return
        try:
            with open(self._log_file_path, "a", encoding="utf-8") as f:
                f.write(text)
        except Exception as e:
            print(f"[PromptTracker] Log file write error: {e}")

    def _record_entry(self, game_id: str, item: Any, pool_size: int):
        """Records a prompt selection into memory history and log file."""
        now = time.time()
        dt_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))
        k = self.get_prompt_key(item)
        disp = self.get_prompt_display(item)
        cycle = self._cycles.get(game_id, 1)
        used_count = len(self._used_in_cycle.get(game_id, set()))

        entry = {
            "timestamp": now,
            "datetime": dt_str,
            "game_id": game_id,
            "prompt_key": k,
            "prompt_display": disp,
            "cycle": cycle,
            "used_in_cycle": used_count,
            "pool_size": pool_size
        }
        self._history_log.append(entry)

        log_line = f"[{dt_str}] [{game_id}] (Cycle {cycle}, {used_count}/{pool_size}): {disp}"
        print(f"[PromptTracker] {log_line}")
        self._append_to_log_file(log_line + "\n")

    def select_prompts(self, game_id: str, pool: List[Any], count: int) -> List[Any]:
        """
        Selects `count` prompts from `pool` for `game_id` without repeats until
        the entire pool has been cycled through.
        
        Guarantees:
        1. No prompt repeats in a cycle until all available prompts in `pool` have been used.
        2. Across round boundaries, remaining unplayed prompts are played first before cycling.
        3. Within a single round, all returned prompts are distinct (if len(pool) >= count).
        4. Thread-safe and logs every prompt selection to memory and data/used_prompts.log.
        """
        with self._lock:
            if not pool or count <= 0:
                return []

            if game_id not in self._used_in_cycle:
                self._used_in_cycle[game_id] = set()
            if game_id not in self._cycles:
                self._cycles[game_id] = 1

            # Ensure unique items in pool by prompt key
            unique_items = []
            seen_keys = set()
            for item in pool:
                k = self.get_prompt_key(item)
                if k not in seen_keys:
                    seen_keys.add(k)
                    unique_items.append(item)

            pool_size = len(unique_items)
            used_set = self._used_in_cycle[game_id]
            available = [item for item in unique_items if self.get_prompt_key(item) not in used_set]

            selected = []

            # Case 1: We have enough unused prompts in the current cycle
            if len(available) >= count:
                random.shuffle(available)
                chosen = available[:count]
                for item in chosen:
                    k = self.get_prompt_key(item)
                    used_set.add(k)
                    self._record_entry(game_id, item, pool_size)
                selected.extend(chosen)
            else:
                # Case 2: Pool exhausted or about to be exhausted.
                # Use all remaining unused prompts first to complete the current cycle
                if available:
                    random.shuffle(available)
                    for item in available:
                        k = self.get_prompt_key(item)
                        used_set.add(k)
                        self._record_entry(game_id, item, pool_size)
                    selected.extend(available)

                # Announce cycle completion and start new cycle
                old_cycle = self._cycles[game_id]
                self._cycles[game_id] += 1
                used_set.clear()

                cycle_msg = f"*** [{game_id}] Cycled through all {pool_size} available prompts! Starting Cycle {self._cycles[game_id]} ***"
                print(f"[PromptTracker] {cycle_msg}")
                self._append_to_log_file(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {cycle_msg}\n\n")

                # Need remaining items to reach `count`
                needed = count - len(selected)
                if needed > 0:
                    # Exclude items already selected in this round to prevent duplicates within the round
                    selected_keys = {self.get_prompt_key(x) for x in selected}
                    refreshed_pool = [x for x in unique_items if self.get_prompt_key(x) not in selected_keys]
                    
                    if not refreshed_pool:
                        refreshed_pool = list(unique_items)

                    random.shuffle(refreshed_pool)
                    chosen_next = refreshed_pool[:needed]
                    for item in chosen_next:
                        k = self.get_prompt_key(item)
                        used_set.add(k)
                        self._record_entry(game_id, item, pool_size)
                    selected.extend(chosen_next)

            return selected

    def record_prompt_use(self, game_id: str, prompt_text: str, meta: Optional[Dict[str, Any]] = None):
        """Manually records a prompt into the log (e.g. for dynamic CAPTCHA prompts)."""
        with self._lock:
            now = time.time()
            dt_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))
            cycle = self._cycles.get(game_id, 1)
            used_count = len(self._used_in_cycle.get(game_id, set()))
            
            entry = {
                "timestamp": now,
                "datetime": dt_str,
                "game_id": game_id,
                "prompt_key": prompt_text.strip(),
                "prompt_display": prompt_text.strip(),
                "cycle": cycle,
                "used_in_cycle": used_count,
                "pool_size": meta.get("pool_size", 0) if meta else 0,
                "meta": meta or {}
            }
            self._history_log.append(entry)
            log_line = f"[{dt_str}] [{game_id}] (Dynamic/Generated): \"{prompt_text.strip()}\""
            print(f"[PromptTracker] {log_line}")
            self._append_to_log_file(log_line + "\n")

    def get_log(self, game_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns the full chronological list of prompt usages."""
        with self._lock:
            if game_id:
                return [e for e in self._history_log if e["game_id"] == game_id]
            return list(self._history_log)

    def get_stats(self) -> Dict[str, Any]:
        """Returns summary statistics of prompt usage and cycles."""
        with self._lock:
            stats = {}
            all_games = set(list(self._used_in_cycle.keys()) + list(self._cycles.keys()))
            for gid in all_games:
                stats[gid] = {
                    "cycle": self._cycles.get(gid, 1),
                    "used_in_current_cycle": len(self._used_in_cycle.get(gid, set())),
                    "total_used_since_launch": sum(1 for e in self._history_log if e["game_id"] == gid)
                }
            return stats

    def reset(self, game_id: Optional[str] = None):
        """Manually resets tracking if needed."""
        with self._lock:
            if game_id:
                self._used_in_cycle.pop(game_id, None)
                self._cycles[game_id] = 1
                self._history_log = [e for e in self._history_log if e["game_id"] != game_id]
            else:
                self.init_session_log()

# Shared singleton instance
prompt_tracker = PromptTracker()
