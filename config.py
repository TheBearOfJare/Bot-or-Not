import os
import socket

def get_local_ip() -> str:
    """
    Attempts to discover the host's actual LAN IPv4 address (e.g. 192.168.x.x or 10.x.x.x)
    so phones on the same Wi-Fi network can connect.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

class Config:
    HOST = os.getenv("FLASK_HOST", "0.0.0.0")
    PORT = int(os.getenv("FLASK_PORT", 5000))
    DEBUG = os.getenv("FLASK_DEBUG", "True").lower() in ("true", "1")
    SECRET_KEY = os.getenv("SECRET_KEY", "bot-or-not-secret-key-jackbox-party-2026")
    
    # Detected local IP for players joining via QR code
    LOCAL_IP = get_local_ip()

    # Ollama LLM Configuration (llama3.1:8b for text, qwen3.5:4b for vision)
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "qwen3.5:4b")
    OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", 12))   # seconds for LLM inference (room for model weights swap)

    # Timers (in seconds)
    SUBMISSION_TIMEOUT = 30           # Limited time to answer in each minigame (bumped to 30s)
    SUBMISSION_TIMEOUT_SURVEY = 40    # Extended time for Survey Says (3 answers)
    VOTING_TIMEOUT = 25               # Limited time to vote
    INTRO_TIMEOUT = 32                # Game orientation / voicelines briefing display time
    INSTRUCTIONS_TIMEOUT = 8          # Instructions display time
    REVEAL_TIMEOUT = 10               # Reveal phase display time
    SCOREBOARD_TIMEOUT = 8            # Scoreboard intermission time

    # Default minigame order
    DEFAULT_GAME_SEQUENCE = ["pun", "review", "survey", "captcha", "bonus"]

    # Number of questions/prompts per minigame (default 3, configurable in settings)
    QUESTIONS_PER_MINIGAME = int(os.getenv("QUESTIONS_PER_MINIGAME", 3))

    # Game Scoring Rules
    POINTS_CORRECT_BOT = 100                  # Points for correctly identifying a bot
    POINTS_MISTAKEN_FOR_BOT_PENALTY = -25    # Human loses points when other players mistake them for a bot!
    POINTS_BONUS_MATCH = 150                 # Points in bonus round for correctly matching a dossier

    # Dynamic lobby scaling:
    # 1-4 players: 1 bot, 1 vote
    # 5+ players: 2 bots, 2 votes
    LARGE_LOBBY_THRESHOLD = 5
