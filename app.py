import io
import qrcode
# pyrefly: ignore[missing-import]
from flask import Flask, render_template, request, jsonify, send_file, session
from config import Config
from game.game_manager import GameManager

import time

app = Flask(__name__)
app.config.from_object(Config)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

@app.context_processor
def inject_cache_bust():
    return {"v": int(time.time())}

# Singleton game manager
game_manager = GameManager(Config)

@app.after_request
def add_cors_and_pna_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    if request.headers.get("Access-Control-Request-Private-Network") == "true":
        response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response

@app.route("/api/<path:path>", methods=["OPTIONS"])
def api_options_handler(path):
    response = jsonify({"status": "ok"})
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response, 204

@app.route("/")
def host_screen():
    """Main TV / Host display."""
    return render_template(
        "host.html",
        local_ip=Config.LOCAL_IP,
        port=Config.PORT,
        join_url=Config.get_join_url(),
        base_url=Config.get_base_url(),
        public_url=Config.PUBLIC_URL
    )

@app.route("/player")
def player_screen():
    """Mobile controller display for players."""
    return render_template("player.html")

@app.route("/qr")
def qr_code():
    """
    Dynamically generates a QR code pointing directly to the mobile player join URL.
    """
    target_url = Config.get_join_url()
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=3,
    )
    qr.add_data(target_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="#111827", back_color="#ffffff")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")

# --- API Endpoints ---

@app.route("/api/host_state", methods=["GET"])
def api_host_state():
    return jsonify(game_manager.get_host_state())

@app.route("/api/player_state", methods=["GET"])
def api_player_state():
    player_id = request.args.get("player_id") or session.get("player_id")
    if not player_id:
        return jsonify({"phase": "UNREGISTERED"})
    st = game_manager.get_player_state(player_id)
    if st.get("phase") == "UNREGISTERED" and "player_id" in session:
        session.pop("player_id", None)
    return jsonify(st)

@app.route("/api/join", methods=["POST"])
def api_join():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"success": False, "error": "Name cannot be empty"}), 400
    
    player = game_manager.register_player(name)
    session["player_id"] = player["id"]
    return jsonify({"success": True, "player": player})

@app.route("/api/remove_player", methods=["POST"])
@app.route("/api/kick_player", methods=["POST"])
def api_remove_player():
    data = request.get_json(silent=True) or {}
    player_id = data.get("player_id") or request.args.get("player_id")
    if not player_id:
        target_name = (data.get("name") or request.args.get("name") or "").strip()
        if target_name:
            for pid, p in game_manager.players.items():
                if p.get("name") == target_name:
                    player_id = pid
                    break

    if not player_id:
        return jsonify({"success": False, "error": "Missing player_id"}), 400

    if game_manager.phase != "LOBBY":
        return jsonify({"success": False, "error": "Players can only be removed while in the lobby"}), 400

    removed = game_manager.remove_player(player_id)
    if session.get("player_id") == player_id:
        session.pop("player_id", None)
    return jsonify({
        "success": removed,
        "player_id": player_id,
        "state": game_manager.get_host_state()
    })

@app.route("/api/start", methods=["POST"])
def api_start():
    data = request.get_json(silent=True) or {}
    custom_sequence = data.get("sequence")
    if custom_sequence and isinstance(custom_sequence, list):
        game_manager.set_game_sequence(custom_sequence)
        
    custom_questions = data.get("questions_per_minigame")
    if custom_questions is not None:
        try:
            game_manager.set_questions_per_minigame(int(custom_questions))
        except (ValueError, TypeError):
            pass

    started = game_manager.start_game()
    return jsonify({"success": started, "phase": game_manager.phase, "state": game_manager.get_host_state()})

@app.route("/api/set_sequence", methods=["POST"])
def api_set_sequence():
    data = request.get_json(silent=True) or {}
    seq = data.get("sequence")
    if seq and isinstance(seq, list):
        game_manager.set_game_sequence(seq)
        return jsonify({"success": True, "sequence": game_manager.game_sequence})
    return jsonify({"success": False, "error": "Invalid sequence format"}), 400

@app.route("/api/set_settings", methods=["POST"])
def api_set_settings():
    data = request.get_json(silent=True) or {}
    q_count = data.get("questions_per_minigame")
    if q_count is not None:
        try:
            game_manager.set_questions_per_minigame(int(q_count))
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "Invalid questions count"}), 400
    return jsonify({
        "success": True,
        "questions_per_minigame": game_manager.questions_per_minigame
    })

@app.route("/api/submit", methods=["POST"])
def api_submit():
    data = request.get_json(silent=True) or {}
    player_id = data.get("player_id") or session.get("player_id")
    response_val = data.get("response")
    is_locked = bool(data.get("locked", True))
    version = data.get("version", 0)
    question_index = data.get("question_index")
    
    if not player_id or response_val is None:
        return jsonify({"success": False, "error": "Missing player_id or response"}), 400
        
    ok = game_manager.handle_player_submission(
        player_id, response_val, is_locked=is_locked, version=version, question_index=question_index
    )
    return jsonify({"success": ok})

@app.route("/api/vote", methods=["POST"])
def api_vote():
    data = request.get_json(silent=True) or {}
    player_id = data.get("player_id") or session.get("player_id")
    target_option_ids = data.get("target_option_ids") or data.get("target_option_id")
    question_index = data.get("question_index")
    is_locked = bool(data.get("is_locked", True)) if "is_locked" in data else bool(data.get("locked", True))
    
    if not player_id:
        return jsonify({"success": False, "error": "Missing player_id"}), 400
    if is_locked and not target_option_ids:
        return jsonify({"success": False, "error": "Missing target_option_ids"}), 400
        
    ok = game_manager.handle_player_vote(
        player_id, target_option_ids or [], question_index=question_index, is_locked=is_locked
    )
    return jsonify({"success": ok})

@app.route("/api/bonus_guess", methods=["POST"])
def api_bonus_guess():
    data = request.get_json(silent=True) or {}
    player_id = data.get("player_id") or session.get("player_id")
    guesses = data.get("guesses") # { dossier_id: target_player_id }
    
    if not player_id or not guesses:
        return jsonify({"success": False, "error": "Missing player_id or guesses"}), 400
        
    ok = game_manager.handle_bonus_guess(player_id, guesses)
    return jsonify({"success": ok})

@app.route("/api/next_phase", methods=["POST"])
def api_next_phase():
    """Manual or timer advance button for host."""
    data = request.get_json(silent=True) or {}
    expected_phase = data.get("current_phase")
    ok = game_manager.next_phase(expected_phase=expected_phase)
    return jsonify({"success": ok, "state": game_manager.get_host_state()})

@app.route("/api/reset", methods=["POST"])
def api_reset():
    data = request.get_json(silent=True) or {}
    clear_players = data.get("clear_players", False)
    game_manager.reset_to_lobby(clear_players=clear_players)
    return jsonify({"success": True, "state": game_manager.get_host_state()})

@app.route("/api/toggle_pause", methods=["POST"])
def api_toggle_pause():
    is_paused = game_manager.toggle_pause()
    return jsonify({"success": True, "is_paused": is_paused, "state": game_manager.get_host_state()})

@app.route("/api/prompt_log", methods=["GET"])
def api_prompt_log():
    game_id = request.args.get("game_id")
    return jsonify({
        "success": True,
        "stats": game_manager.prompt_tracker.get_stats(),
        "log": game_manager.prompt_tracker.get_log(game_id=game_id)
    })

if __name__ == "__main__":
    import sys
    import threading
    from game.minigames.captcha import clear_captcha_images
    clear_captcha_images()

    for i, arg in enumerate(sys.argv):
        if arg in ("--public-url", "--tunnel") and i + 1 < len(sys.argv):
            Config.PUBLIC_URL = sys.argv[i + 1].strip().rstrip("/")
        elif arg.startswith("--public-url="):
            Config.PUBLIC_URL = arg.split("=", 1)[1].strip().rstrip("/")
        elif arg.startswith("--tunnel="):
            Config.PUBLIC_URL = arg.split("=", 1)[1].strip().rstrip("/")

    threading.Thread(target=game_manager.bot_engine.prewarm, daemon=True).start()

    print(f"\n=======================================================")
    print(f"🤖 Bot or Not Game Server Starting!")
    print(f"📺 Host Screen:   http://localhost:{Config.PORT}/")
    print(f"📱 Player Mobile: {Config.get_join_url()}")
    if Config.PUBLIC_URL:
        print(f"☁️  Public Tunnel: {Config.get_base_url()}")
    print(f"🌐 Local LAN IP:  {Config.LOCAL_IP}")
    print(f"=======================================================\n")
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
