import random
from typing import Dict, Any, List

class BonusRoundGame:
    """
    Final Bonus Round:
    All previous responses from each human player are shown grouped together as an anonymous 'Dossier'.
    Players try to pin each dossier onto the human who they think wrote them!
    """
    def __init__(self, bot_engine=None, bot_count: int = 0):
        self.game_id = "bonus"
        self.title = "Final Bonus Round: The Human Dossier"
        self.instruction = (
            "Every response from the entire game has been compiled into anonymous dossiers. "
            "Can you match each dossier to the human who wrote them?"
        )
        self.dossiers: Dict[str, Dict[str, Any]] = {} # dossier_id -> { author_id, author_name, items }
        self.player_guesses: Dict[str, Dict[str, str]] = {} # voter_id -> { dossier_id: guessed_player_id }
        self.human_players: List[Dict[str, str]] = [] # [{ "id": ..., "name": ... }]

    def start_round(self, players: Dict[str, Any], player_history: Dict[str, List[Dict[str, Any]]]):
        """
        Builds anonymous dossiers from historical responses of human players.
        """
        self.dossiers.clear()
        self.player_guesses.clear()
        self.human_players = [{"id": pid, "name": p["name"]} for pid, p in players.items()]

        dossier_letters = ["A", "B", "C", "D", "E", "F", "G", "H"]
        letter_idx = 0

        # Create a dossier for each human player who has history
        for player_id, p_info in players.items():
            history = player_history.get(player_id, [])
            if not history:
                continue
            
            letter = dossier_letters[letter_idx % len(dossier_letters)]
            dossier_id = f"dossier_{letter}"
            letter_idx += 1

            self.dossiers[dossier_id] = {
                "dossier_id": dossier_id,
                "label": f"Dossier {letter}",
                "author_id": player_id,
                "author_name": p_info["name"],
                "items": history # list of { round_num, game_title, prompt, response }
            }

    def get_prompt_for_player(self, player_id: str) -> Dict[str, Any]:
        """
        Player receives all dossiers and the candidate player names.
        """
        anonymized_dossiers = []
        for d_id, d in self.dossiers.items():
            # Player shouldn't need to guess their own dossier, or can see it
            is_own = (d["author_id"] == player_id)
            anonymized_dossiers.append({
                "dossier_id": d_id,
                "label": d["label"],
                "items": d["items"],
                "is_own": is_own
            })

        return {
            "game_id": self.game_id,
            "title": self.title,
            "instruction": self.instruction,
            "type": "bonus_matching",
            "dossiers": anonymized_dossiers,
            "candidates": self.human_players
        }

    def submit_guesses(self, player_id: str, guesses: Dict[str, str]) -> bool:
        """
        guesses: { "dossier_A": "player_id_xyz", "dossier_B": ... }
        """
        self.player_guesses[player_id] = guesses
        return True

    def are_votes_complete(self, active_player_ids: List[str]) -> bool:
        return set(active_player_ids).issubset(set(self.player_guesses.keys()))

    def calculate_scores(self, config) -> Dict[str, Any]:
        score_deltas: Dict[str, int] = {}
        correct_guesses: Dict[str, List[str]] = {d_id: [] for d_id in self.dossiers}

        for voter_id, guess_map in self.player_guesses.items():
            for d_id, guessed_target_id in guess_map.items():
                dossier = self.dossiers.get(d_id)
                if dossier and dossier["author_id"] == guessed_target_id:
                    score_deltas[voter_id] = score_deltas.get(voter_id, 0) + config.POINTS_BONUS_MATCH
                    correct_guesses[d_id].append(voter_id)

        return {
            "score_deltas": score_deltas,
            "correct_guesses": correct_guesses
        }

    def get_reveal_data(self, player_names_map: Dict[str, str], config) -> Dict[str, Any]:
        scores_result = self.calculate_scores(config)
        correct_guesses = scores_result["correct_guesses"]
        score_deltas = scores_result["score_deltas"]

        reveal_dossiers = []
        for d_id, d in self.dossiers.items():
            correct_voter_ids = correct_guesses.get(d_id, [])
            correct_voter_names = [player_names_map.get(vid, "Unknown") for vid in correct_voter_ids]
            
            # All guesses for this dossier
            guesses_for_dossier = []
            for voter_id, gmap in self.player_guesses.items():
                guessed_id = gmap.get(d_id)
                guesses_for_dossier.append({
                    "voter_name": player_names_map.get(voter_id, "Unknown"),
                    "guessed_name": player_names_map.get(guessed_id, "Nobody")
                })

            reveal_dossiers.append({
                "dossier_id": d_id,
                "label": d["label"],
                "author_name": d["author_name"],
                "items": d["items"],
                "correct_voter_names": correct_voter_names,
                "guesses": guesses_for_dossier
            })

        return {
            "reveal_dossiers": reveal_dossiers,
            "score_deltas": score_deltas
        }
