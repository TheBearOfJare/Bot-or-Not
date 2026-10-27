import re
from typing import Any, Union, List

def normalize_response(text: Any, strip_setup: str = "", strip_final_period: bool = True) -> Any:
    """
    Normalizes a player (or bot) answer so that human and bot answers follow identical formatting:
    - Strips outer markdown symbols (*, _, `, #, ~) and quotes ('", "").
    - If prompt setup was repeated in response, strips it.
    - Collapses newlines/extra whitespace into a single clean line.
    - Strips trailing punctuation (,;:-) and trailing period (.).
    - Capitalizes characters following sentence terminators (.!?).
    - Capitalizes the initial character.
    - If passed a list of responses (e.g. Survey minigame), normalizes each element.
    """
    if text is None:
        return ""

    if isinstance(text, list):
        return [normalize_response(item, strip_setup=strip_setup, strip_final_period=strip_final_period) for item in text]

    if not isinstance(text, str):
        text = str(text)

    raw = text.strip()
    if not raw:
        return ""

    # Don't normalize system brackets like [Out of time - Blank submission]
    if raw.startswith("[") and raw.endswith("]"):
        return raw

    # Strip surrounding quotes, backticks, markdown
    raw = re.sub(r"^[\"\'`*#~]+|[\"\'`*#~]+$", "", raw).strip()
    # Strip any residual leading ellipses, bullets, colons, or dashes
    raw = re.sub(r"^[\s.:;–—\-…•]+", "", raw).strip()

    # If setup prompt is repeated in response, strip it
    if strip_setup:
        clean_setup = re.sub(r"[*_`#~]", "", strip_setup).strip(" .?!:–-")
        if clean_setup and clean_setup.lower() in raw.lower():
            pattern = re.escape(clean_setup) + r"[\s.?:–-]*"
            raw = re.sub(pattern, "", raw, flags=re.IGNORECASE).strip()

    # Collapse multiple lines into a single clean line
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        return ""
    raw = " ".join(lines)

    # Clean trailing punctuation (,;:-) and trailing period
    raw = raw.rstrip(",;:- ")
    if strip_final_period and raw.endswith("."):
        raw = raw[:-1].strip()

    raw = raw.strip("\"'*`# ")

    # Capitalize after sentence ends (.!?)
    raw = re.sub(r"([.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), raw)

    # Capitalize first character
    if raw:
        raw = raw[0].upper() + raw[1:]

    return raw
