Bot or Not is a jackbox-like party game where players use their deduction skills to determine who is a bot and who is a human.

Premise (may be changed later): Shady organization (maybe vaguely dictatorship government) trying to develop bots to influence the general public. You're test subjects to see how well the bots fit in, doing various tasks that bots are used to influence real life people.

Gameplay:

Players, both human and bots, get put into various simple minigames, answering various kinds of questions as humanly as possible. Everyone else votes on who, if anyone, seems to be a bot.

After everyone has played the minigame (everyone gets voted on once and votes on other players at least once, depending on how many players), it's revealed which responses were from bots and which were from humans. Points are awarded to those who picked out the bots correctly, as well as a small amount for players who managed to convince voters that they were a bot. It is not revealed yet which player actually gave which response.

After a set number of rounds, the players play a final bonus round where all previous responses from a given player are shown grouped together and players pin the set of responses on the human who they think gave them. Once the bonus round is complete, points are tallied up and the player with the most points is declared the winner.

Minigames:

1. Complete the pun: players are given a pun that has had its punchline cut off, they must fill in the punchline.

2. 1 star review: players are given a mundane product to review bomb, and must come up with a reason for why the product is terrible.

3. Survey Says: players are given a family feud style prompt, and must list their top 3 answers. 

4. Captcha caption: players are shown a really bad AI generated image and must give it a description.

Structure:

- Python Flask backend with modular minigames in `game/minigames/`
- Real-time sync for TV host screen (`/`) and mobile player controller (`/player`)
- Automatic LAN IP detection and dynamic QR code generation for quick mobile joining
- Ollama LLM integration (`game/bot_engine.py`) using Qwen (with offline fallback templates)
- Highly flexible playlist sequence: play all 4 minigames + bonus round, or customize in `config.py` or from the host setup lobby
- Bots do their best to pass as humans

### Quickstart

1. Activate virtual environment and run the server:
   ```bash
   .venv/bin/python app.py
   ```
2. Open the **Host Screen** on your computer/TV:
   ```
   http://localhost:5000/
   ```
3. Players join on their phones on the same Wi-Fi by scanning the on-screen QR code or navigating to:
   ```
   http://<YOUR_LOCAL_IP>:5000/player
   ```
4. Click **Start Game** on the host screen to begin! After starting, the game runs on auto-pilot through submissions, voting, reveal, scoreboard, and the final bonus round.