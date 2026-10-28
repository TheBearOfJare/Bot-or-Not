#!/usr/bin/env python3
"""
Launcher script that automatically:
1. Spawns a free Cloudflare Quick Tunnel (trycloudflare.com).
2. Extracts the public HTTPS URL.
3. Passes it to Bot or Not (app.py) for the QR code and host screen.
4. Cleanly terminates the tunnel on exit (Ctrl+C).
"""

import os
import re
import sys
import time
import shutil
import signal
import subprocess
from config import Config

def main():
    cloudflared_bin = shutil.which("cloudflared")
    if not cloudflared_bin:
        print("\n❌ Error: 'cloudflared' is not installed or not in your PATH.")
        print("On Arch/CachyOS, install it via: sudo pacman -S cloudflared\n")
        sys.exit(1)

    print("\n=======================================================")
    print("🚀 Initializing Bot or Not with Cloudflare Quick Tunnel")
    print("=======================================================")
    print("⏳ Spawning Cloudflare Quick Tunnel...")

    tunnel_proc = subprocess.Popen(
        [cloudflared_bin, "tunnel", "--url", f"http://127.0.0.1:{Config.PORT}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    tunnel_url = None
    start_time = time.time()
    url_regex = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")

    # Read output until tunnel URL is found or timeout (up to 30s)
    try:
        while time.time() - start_time < 30:
            line = tunnel_proc.stdout.readline()
            if not line:
                if tunnel_proc.poll() is not None:
                    break
                time.sleep(0.05)
                continue

            match = url_regex.search(line)
            if match:
                tunnel_url = match.group(0)
                break

            if tunnel_proc.poll() is not None:
                break
    except KeyboardInterrupt:
        tunnel_proc.terminate()
        sys.exit(0)

    if not tunnel_url:
        print("\n❌ Failed to obtain Cloudflare Quick Tunnel URL.")
        print("Ensure you have an active internet connection.")
        try:
            tunnel_proc.terminate()
        except Exception:
            pass
        sys.exit(1)

    print(f"✅ Tunnel Connected: {tunnel_url}")
    print(f"📱 Mobile Controller Link: {tunnel_url}/player")
    print("=======================================================\n")

    env_file = os.path.join(os.path.dirname(__file__), ".env")
    try:
        with open(env_file, "w", encoding="utf-8") as f:
            f.write(f"PUBLIC_URL={tunnel_url}\n")
    except Exception:
        pass

    flask_env = os.environ.copy()
    flask_env["PUBLIC_URL"] = tunnel_url

    flask_cmd = [sys.executable, "app.py", f"--public-url={tunnel_url}"] + sys.argv[1:]
    flask_proc = subprocess.Popen(flask_cmd, env=flask_env)

    def cleanup(signum=None, frame=None):
        print("\n🛑 Shutting down Bot or Not and Cloudflare Tunnel...")
        try:
            flask_proc.terminate()
            flask_proc.wait(timeout=3)
        except Exception:
            try:
                flask_proc.kill()
            except Exception:
                pass
        try:
            tunnel_proc.terminate()
            tunnel_proc.wait(timeout=3)
        except Exception:
            try:
                tunnel_proc.kill()
            except Exception:
                pass
        try:
            with open(env_file, "w", encoding="utf-8") as f:
                f.write("PUBLIC_URL=\n")
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    try:
        ret = flask_proc.wait()
        cleanup()
        sys.exit(ret)
    except KeyboardInterrupt:
        cleanup()

if __name__ == "__main__":
    main()

