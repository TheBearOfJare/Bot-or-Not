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

@app.route("/")
def host_screen():
    """Main TV / Host display."""
    return render_template("host.html", local_ip=Config.LOCAL_IP, port=Config.PORT)

@app.route("/player")
def player_screen():
    """Mobile controller display for players."""
    return render_template("player.html")

@app.route("/qr")
def qr_code():
    """
    Dynamically generates a QR code pointing directly to the mobile player join URL.
    """
    target_url = f"http://{Config.LOCAL_IP}:{Config.PORT}/player"
    
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
    return jsonify(game_manager.get_player_state(player_id))

@app.route("/api/join", methods=["POST"])
def api_join():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"success": False, "error": "Name cannot be empty"}), 400
    
    player = game_manager.register_player(name)
    session["player_id"] = player["id"]
    return jsonify({"success": True, "player": player})

@app.route("/api/start", methods=["POST"])
def api_start():
    data = request.get_json(silent=True) or {}
    custom_sequence = data.get("sequence")
    if custom_sequence and isinstance(custom_sequence, list):
        game_manager.set_game_sequence(custom_sequence)
        
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

@app.route("/api/submit", methods=["POST"])
def api_submit():
    data = request.get_json(silent=True) or {}
    player_id = data.get("player_id") or session.get("player_id")
    response_val = data.get("response")
    is_locked = bool(data.get("locked", True))
    version = data.get("version", 0)
    
    if not player_id or response_val is None:
        return jsonify({"success": False, "error": "Missing player_id or response"}), 400
        
    ok = game_manager.handle_player_submission(
        player_id, response_val, is_locked=is_locked, version=version
    )
    return jsonify({"success": ok})

@app.route("/api/vote", methods=["POST"])
def api_vote():
    data = request.get_json(silent=True) or {}
    player_id = data.get("player_id") or session.get("player_id")
    target_option_ids = data.get("target_option_ids") or data.get("target_option_id")
    
    if not player_id or not target_option_ids:
        return jsonify({"success": False, "error": "Missing player_id or target_option_ids"}), 400
        
    ok = game_manager.handle_player_vote(player_id, target_option_ids)
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

if __name__ == "__main__":
    import threading
    threading.Thread(target=game_manager.bot_engine.prewarm, daemon=True).start()

    print(f"\n=======================================================")
    print(f"🤖 Bot or Not Game Server Starting!")
    print(f"📺 Host Screen:   http://localhost:{Config.PORT}/")
    print(f"📱 Player Mobile: http://{Config.LOCAL_IP}:{Config.PORT}/player")
    print(f"🌐 Local LAN IP:  {Config.LOCAL_IP}")
    print(f"=======================================================\n")
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
