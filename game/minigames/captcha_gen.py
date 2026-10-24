import os
import io
import random
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance

try:
    from captchaCaptionImageGen import generate_attngan_captcha, get_attngan_model
except ImportError:
    generate_attngan_captcha = None
    get_attngan_model = None

CAPTCHA_SUBJECTS = {
    "cat_on_car": {
        "title": "A Cat on a Car",
        "description": "an orange cat sitting on the roof of a parked red car under a streetlamp at night",
        "attngan_prompt": "a cat sitting on the roof of a parked red car on the street",
        "fallbacks": [
            "An orange cat perched on top of a red car acting like it owns the vehicle.",
            "Feline overlord refusing to pay parking fees while loafing on an automobile roof.",
            "Someone parked their red sedan directly underneath a very judgmental cat.",
            "A cat guarding a red car in the middle of the night under a street light."
        ]
    },
    "ufo_abducting_cow": {
        "title": "A UFO Abducting a Cow",
        "description": "a flying saucer hovering in the sky using a glowing tractor beam to abduct a spotted cow from a field",
        "attngan_prompt": "a flying aircraft in the night sky over a cow standing in a grassy field",
        "fallbacks": [
            "A UFO tractor-beaming a cow into outer space at midnight.",
            "Extraterrestrials performing their routine dairy acquisition mission.",
            "A flying saucer picking up a bovine hitchhiker with a neon beam.",
            "Alien spaceship lifting a confused cow off the pasture."
        ]
    },
    "dino_chasing_bus": {
        "title": "A Dinosaur Chasing a School Bus",
        "description": "a green dinosaur chasing a yellow school bus down a street past a stop sign",
        "attngan_prompt": "a large green animal chasing a yellow school bus down a street next to a stop sign",
        "fallbacks": [
            "A T-Rex trying to catch the morning school bus because it missed its alarm.",
            "Godzilla casually tailgating a yellow school bus in morning traffic.",
            "Jurassic field trip gone horribly wrong on a suburban avenue.",
            "A green dinosaur running after a yellow bus near a stop sign."
        ]
    },
    "bear_on_bike": {
        "title": "A Bear on a Tiny Bicycle",
        "description": "a large brown bear riding a comically small bicycle across a pedestrian crosswalk",
        "attngan_prompt": "a large brown bear riding a small bicycle across a pedestrian crosswalk",
        "fallbacks": [
            "A massive bear testing the weight limit of a miniature bicycle in the crosswalk.",
            "Circus bear commuting to work on two tiny wheels.",
            "A bear observing pedestrian crossing laws while balanced on a child's bike.",
            "A big grizzly struggling to pedal a tiny two-wheeler."
        ]
    },
    "hydrant_geyser_cat": {
        "title": "A Fire Hydrant Geyser and Panicking Cat",
        "description": "a broken fire hydrant shooting a giant geyser of water into the air next to a wet cat running away on a sidewalk",
        "attngan_prompt": "a red fire hydrant spraying water into the air next to a wet cat running on a sidewalk",
        "fallbacks": [
            "A municipal fire hydrant erupting like Old Faithful while a soaking wet cat flees the splash zone.",
            "Total water pipe catastrophe turning the sidewalk into an unplanned waterpark.",
            "A fire hydrant shooting a geyser of water high into the air while a cat panics.",
            "Sidewalk fountain explosion soaking everything within a 20-foot radius."
        ]
    },
    "raccoon_trash_heist": {
        "title": "A Raccoon Raiding a Trash Can",
        "description": "a raccoon rummaging through a knocked-over trash can with garbage spilling onto the sidewalk under a street sign at night",
        "attngan_prompt": "a raccoon rummaging through a metal trash can on the sidewalk under a street sign at night",
        "fallbacks": [
            "A trash panda conducting an aggressive midnight audit of someone's garbage can.",
            "A raccoon caught red-handed tipping over a trash can by a stop sign.",
            "Midnight dumpster diving operation in progress under the moon.",
            "A bandit raccoon spilling trash bags all over the pavement."
        ]
    },
    "robot_walking_dog": {
        "title": "A Robot Walking a Cyber Dog",
        "description": "a humanoid robot walking a mechanical dog on a leash past a traffic light in a futuristic city",
        "attngan_prompt": "a metallic robot walking a dog on a leash past a traffic light on a city street",
        "fallbacks": [
            "A robot taking its dog for a walk while waiting for the traffic light to turn green.",
            "Future municipal compliance: cyborg walking a mechanical canine down the sidewalk.",
            "A tin can robot being dragged along by a dog under a street signal.",
            "An android walking a pet in a pixelated cyberpunk downtown."
        ]
    },
    "ufo_at_red_light": {
        "title": "A UFO Stopped at a Red Light",
        "description": "a tiny alien spaceship stopped patiently at a red traffic light above a pedestrian crosswalk",
        "attngan_prompt": "a small vehicle stopped at a red traffic light above a pedestrian crosswalk",
        "fallbacks": [
            "An extraterrestrial spaceship actually obeying municipal traffic signals.",
            "Alien in a flying saucer stuck at a red light in rush hour traffic.",
            "Even intergalactic travelers have to wait for the light to turn green.",
            "A mini UFO hovering quietly above a pedestrian crosswalk."
        ]
    },
    "cat_blocking_traffic": {
        "title": "A Giant Cat Blocking Traffic",
        "description": "a giant lazy cat sprawled across the road blocking a yellow school bus and traffic",
        "attngan_prompt": "a giant orange cat lying across the street blocking a yellow bus and cars",
        "fallbacks": [
            "Major traffic standstill caused by a gigantic cat taking an afternoon nap across both lanes.",
            "School bus halted by a furry feline roadblock refusing to budge.",
            "The most effective speed bump ever: an enormous sleeping cat on the asphalt.",
            "A massive cat taking a nap across the entire street while cars wait."
        ]
    },
    "snowman_campfire": {
        "title": "A Snowman by a Campfire",
        "description": "a snowman standing next to a crackling campfire in the snow, beginning to melt under the night sky",
        "attngan_prompt": "a white snowman standing next to a burning campfire in the snow at night",
        "fallbacks": [
            "A snowman making the questionable life choice of warming up next to a blazing campfire.",
            "Frosty discovering the tragic laws of thermodynamics by a campfire.",
            "A snowman enjoying a cozy fire until realizing it is melting into a puddle.",
            "Melting snowman chilling by a campsite fire in the woods."
        ]
    },
    "shark_in_flood": {
        "title": "A Shark in a Flooded Street",
        "description": "a flooded street with a shark fin swimming around a submerged stop sign during a rainstorm",
        "attngan_prompt": "a flooded city street with deep water and a stop sign during a rainstorm",
        "fallbacks": [
            "Flash flood warning upgraded to shark warning near the flooded stop sign.",
            "A shark swimming down main street during a torrential downpour.",
            "Street flooding so bad that aquatic apex predators have moved into the bike lane.",
            "A shark fin cruising past a stop sign in ankle-deep flood water."
        ]
    },
    "wizard_summoning_pizza": {
        "title": "A Wizard Summoning Giant Pizza",
        "description": "a wizard with a pointy hat and staff casting a spell to summon a giant slice of pizza from a thundercloud",
        "attngan_prompt": "a person wearing a pointy hat with a giant slice of pizza in the sky",
        "fallbacks": [
            "A wizard using forbidden arcane magic to conjure midnight pepperoni pizza.",
            "Sorcerer striking lightning from the sky to manifest a giant pizza slice.",
            "Ancient spellcasting solely dedicated to avoiding delivery fees.",
            "A wizard on a rooftop summoning celestial junk food during a storm."
        ]
    }
}

def draw_subject_base(subject_key: str, size=(160, 160)) -> Image.Image:
    """
    Procedurally draws rich, humorous, multi-element scenes combining classic CAPTCHA subjects
    (traffic lights, crosswalks, cars, stop signs, cats, animals, buses) into narrative situations.
    """
    w, h = size
    img = Image.new("RGB", size, (35, 40, 55))
    draw = ImageDraw.Draw(img)

    if subject_key in ("cat_on_car", "cat"):
        # Sky: dark night
        draw.rectangle([0, 0, w, int(h * 0.58)], fill=(25, 28, 48))
        # Ground/Road
        draw.rectangle([0, int(h * 0.58), w, h], fill=(45, 48, 55))
        # Sidewalk curb
        draw.rectangle([0, int(h * 0.55), w, int(h * 0.58)], fill=(90, 95, 100))
        # Crescent moon & stars
        draw.ellipse([w - 35, 12, w - 15, 32], fill=(245, 245, 215))
        draw.ellipse([w - 30, 10, w - 10, 30], fill=(25, 28, 48))
        for sx, sy in [(20, 25), (60, 15), (95, 35), (130, 20)]:
            draw.point((sx, sy), fill=(255, 255, 230))
            draw.point((sx + 1, sy), fill=(255, 255, 230))

        # Streetlamp on right
        lx = w - 35
        draw.line([(lx, int(h * 0.2)), (lx, int(h * 0.56))], fill=(60, 65, 70), width=4)
        draw.line([(lx, int(h * 0.2)), (lx - 16, int(h * 0.2))], fill=(60, 65, 70), width=3)
        draw.polygon([(lx - 22, int(h * 0.2)), (lx - 10, int(h * 0.2)), (lx - 16, int(h * 0.25))], fill=(255, 240, 120))
        # Lamp glow cone
        cone = [(lx - 16, int(h * 0.25)), (lx - 85, int(h * 0.7)), (lx + 20, int(h * 0.7))]
        draw.polygon(cone, fill=(50, 52, 58))

        # Red car on left/center
        cx, cy = int(w * 0.38), int(h * 0.65)
        # Wheels
        draw.ellipse([cx - 36, cy + 14, cx - 18, cy + 32], fill=(20, 20, 20))
        draw.ellipse([cx + 18, cy + 14, cx + 36, cy + 32], fill=(20, 20, 20))
        draw.ellipse([cx - 30, cy + 20, cx - 24, cy + 26], fill=(160, 160, 160))
        draw.ellipse([cx + 24, cy + 20, cx + 30, cy + 26], fill=(160, 160, 160))
        # Car Lower Body
        draw.rectangle([cx - 44, cy, cx + 44, cy + 20], fill=(215, 35, 35))
        # Car Cabin / Roof
        draw.polygon([(cx - 30, cy), (cx - 18, cy - 16), (cx + 22, cy - 16), (cx + 34, cy)], fill=(200, 30, 30))
        # Windows
        draw.polygon([(cx - 24, cy - 2), (cx - 15, cy - 14), (cx - 2, cy - 14), (cx - 2, cy - 2)], fill=(160, 210, 240))
        draw.polygon([(cx + 2, cy - 2), (cx + 2, cy - 14), (cx + 18, cy - 14), (cx + 28, cy - 2)], fill=(160, 210, 240))
        # Headlight
        draw.rectangle([cx + 40, cy + 4, cx + 44, cy + 12], fill=(255, 245, 140))

        # Vibrant Orange Ginger Cat perched on car roof
        cat_x, cat_y = cx + 2, cy - 25
        cat_color = (245, 135, 30)
        draw.ellipse([cat_x - 14, cat_y - 8, cat_x + 14, cat_y + 8], fill=cat_color)
        draw.ellipse([cat_x + 8, cat_y - 18, cat_x + 22, cat_y - 4], fill=cat_color)
        # Pointy ears
        draw.polygon([(cat_x + 9, cat_y - 16), (cat_x + 13, cat_y - 25), (cat_x + 16, cat_y - 16)], fill=cat_color)
        draw.polygon([(cat_x + 16, cat_y - 16), (cat_x + 20, cat_y - 25), (cat_x + 23, cat_y - 16)], fill=cat_color)
        # Glowing eyes
        draw.point((cat_x + 15, cat_y - 11), fill=(255, 255, 70))
        draw.point((cat_x + 19, cat_y - 11), fill=(255, 255, 70))
        # Tail
        draw.line([(cat_x - 12, cat_y - 2), (cat_x - 22, cat_y - 14), (cat_x - 18, cat_y - 22)], fill=cat_color, width=4)

    elif subject_key == "ufo_abducting_cow":
        # Deep space / sky
        draw.rectangle([0, 0, w, int(h * 0.65)], fill=(15, 20, 40))
        for sx, sy in [(15, 15), (45, 30), (120, 18), (145, 45), (30, 70), (135, 80)]:
            draw.point((sx, sy), fill=(255, 255, 220))
            draw.point((sx + 1, sy), fill=(255, 255, 220))
        # Green rolling hills
        draw.ellipse([-30, int(h * 0.6), int(w * 0.8), int(h * 1.2)], fill=(35, 100, 45))
        draw.ellipse([int(w * 0.4), int(h * 0.62), int(w * 1.3), int(h * 1.2)], fill=(28, 85, 38))
        # Wooden fence posts
        for fx in [15, 45, 75]:
            draw.line([(fx, int(h * 0.72)), (fx, int(h * 0.86))], fill=(110, 80, 50), width=3)
        draw.line([(10, int(h * 0.76)), (80, int(h * 0.76))], fill=(110, 80, 50), width=2)
        draw.line([(10, int(h * 0.82)), (80, int(h * 0.82))], fill=(110, 80, 50), width=2)

        # Glowing green/yellow tractor beam
        ufo_x, ufo_y = int(w * 0.62), int(h * 0.22)
        beam_poly = [(ufo_x - 10, ufo_y + 10), (ufo_x + 10, ufo_y + 10), (ufo_x + 36, int(h * 0.9)), (ufo_x - 36, int(h * 0.9))]
        draw.polygon(beam_poly, fill=(50, 110, 85))
        draw.polygon([(ufo_x - 5, ufo_y + 10), (ufo_x + 5, ufo_y + 10), (ufo_x + 20, int(h * 0.9)), (ufo_x - 20, int(h * 0.9))], fill=(70, 160, 110))

        # Floating Cow in the beam
        cow_x, cow_y = ufo_x + 2, int(h * 0.52)
        draw.ellipse([cow_x - 16, cow_y - 9, cow_x + 16, cow_y + 9], fill=(245, 245, 245))
        draw.ellipse([cow_x - 8, cow_y - 7, cow_x - 1, cow_y], fill=(30, 30, 30))
        draw.ellipse([cow_x + 5, cow_y - 3, cow_x + 12, cow_y + 6], fill=(30, 30, 30))
        draw.ellipse([cow_x - 22, cow_y - 12, cow_x - 12, cow_y - 2], fill=(245, 245, 245))
        draw.ellipse([cow_x - 24, cow_y - 8, cow_x - 18, cow_y - 2], fill=(240, 160, 170))
        draw.line([(cow_x - 10, cow_y + 8), (cow_x - 13, cow_y + 18)], fill=(30, 30, 30), width=3)
        draw.line([(cow_x - 4, cow_y + 8), (cow_x - 6, cow_y + 17)], fill=(30, 30, 30), width=3)
        draw.line([(cow_x + 6, cow_y + 8), (cow_x + 8, cow_y + 18)], fill=(30, 30, 30), width=3)
        draw.line([(cow_x + 12, cow_y + 8), (cow_x + 15, cow_y + 17)], fill=(30, 30, 30), width=3)

        # Flying Saucer / UFO
        draw.ellipse([ufo_x - 14, ufo_y - 14, ufo_x + 14, ufo_y + 4], fill=(130, 230, 240), outline=(200, 255, 255))
        draw.ellipse([ufo_x - 34, ufo_y - 4, ufo_x + 34, ufo_y + 12], fill=(160, 170, 185), outline=(100, 110, 125), width=2)
        for lx in [ufo_x - 24, ufo_x - 12, ufo_x, ufo_x + 12, ufo_x + 24]:
            draw.ellipse([lx - 2, ufo_y + 2, lx + 2, ufo_y + 6], fill=(255, 220, 40))

    elif subject_key in ("dino_chasing_bus", "school_bus"):
        draw.rectangle([0, 0, w, int(h * 0.55)], fill=(135, 195, 235))
        draw.rectangle([10, int(h * 0.25), 40, int(h * 0.55)], fill=(170, 180, 190))
        draw.rectangle([45, int(h * 0.32), 70, int(h * 0.55)], fill=(190, 175, 170))
        draw.rectangle([75, int(h * 0.2), 105, int(h * 0.55)], fill=(160, 175, 195))
        draw.rectangle([0, int(h * 0.55), w, h], fill=(60, 62, 68))
        draw.rectangle([0, int(h * 0.52), w, int(h * 0.55)], fill=(120, 125, 130))
        for rx in range(0, w, 24):
            draw.line([(rx, int(h * 0.78)), (rx + 12, int(h * 0.78))], fill=(240, 210, 40), width=2)

        sx = w - 18
        draw.line([(sx, int(h * 0.35)), (sx, int(h * 0.65))], fill=(80, 85, 90), width=3)
        draw.ellipse([sx - 11, int(h * 0.26), sx + 11, int(h * 0.44)], fill=(220, 30, 30))
        draw.text((sx - 7, int(h * 0.31)), "STOP", fill=(255, 255, 255))

        bx, by = int(w * 0.56), int(h * 0.6)
        draw.rectangle([bx - 32, by - 16, bx + 28, by + 12], fill=(250, 195, 25), outline=(30, 30, 30), width=2)
        draw.rectangle([bx + 28, by - 4, bx + 38, by + 12], fill=(250, 195, 25), outline=(30, 30, 30), width=2)
        for wx in [-24, -10, 4, 18]:
            draw.rectangle([bx + wx, by - 12, bx + wx + 9, by - 3], fill=(160, 215, 245))
        draw.line([(bx - 32, by + 6), (bx + 38, by + 6)], fill=(30, 30, 30), width=3)
        draw.ellipse([bx - 22, by + 6, bx - 8, by + 20], fill=(25, 25, 25))
        draw.ellipse([bx + 16, by + 6, bx + 30, by + 20], fill=(25, 25, 25))

        dx, dy = int(w * 0.2), int(h * 0.56)
        draw.polygon([(dx - 22, dy + 2), (dx - 6, dy - 6), (dx - 4, dy + 6)], fill=(45, 140, 55))
        draw.ellipse([dx - 12, dy - 14, dx + 14, dy + 12], fill=(45, 140, 55))
        draw.polygon([(dx + 6, dy - 8), (dx + 16, dy - 26), (dx + 26, dy - 20), (dx + 14, dy - 4)], fill=(45, 140, 55))
        draw.rectangle([dx + 14, dy - 26, dx + 28, dy - 14], fill=(45, 140, 55))
        draw.polygon([(dx + 20, dy - 18), (dx + 28, dy - 18), (dx + 26, dy - 14)], fill=(210, 40, 40))
        draw.line([(dx + 22, dy - 18), (dx + 28, dy - 18)], fill=(255, 255, 255), width=2)
        draw.ellipse([dx + 16, dy - 23, dx + 19, dy - 20], fill=(255, 240, 40))
        draw.line([(dx - 6, dy + 8), (dx - 10, dy + 22)], fill=(35, 120, 45), width=4)
        draw.line([(dx + 4, dy + 8), (dx + 10, dy + 20)], fill=(35, 120, 45), width=4)
        draw.line([(dx + 12, dy - 2), (dx + 18, dy - 2)], fill=(35, 120, 45), width=3)

    elif subject_key in ("bear_on_bike", "bicycle", "crosswalk"):
        draw.rectangle([0, 0, w, int(h * 0.45)], fill=(140, 200, 240))
        draw.polygon([(0, int(h * 0.45)), (40, int(h * 0.2)), (90, int(h * 0.45))], fill=(90, 130, 160))
        draw.polygon([(60, int(h * 0.45)), (115, int(h * 0.15)), (160, int(h * 0.45))], fill=(80, 115, 145))
        for tx in [12, 140]:
            draw.polygon([(tx, int(h * 0.45)), (tx + 12, int(h * 0.32)), (tx + 24, int(h * 0.45))], fill=(35, 85, 45))
        draw.rectangle([0, int(h * 0.45), w, h], fill=(55, 58, 62))
        for zx in range(15, w - 15, 26):
            draw.polygon([(zx, int(h * 0.48)), (zx + 14, int(h * 0.48)), (zx + 20, int(h * 0.95)), (zx + 6, int(h * 0.95))], fill=(245, 245, 250))

        bx, by = w // 2, int(h * 0.62)
        draw.ellipse([bx - 26, by + 12, bx - 10, by + 28], outline=(30, 30, 30), width=3)
        draw.ellipse([bx + 10, by + 12, bx + 26, by + 28], outline=(30, 30, 30), width=3)
        draw.line([(bx - 18, by + 20), (bx, by + 20)], fill=(30, 110, 220), width=3)
        draw.line([(bx - 18, by + 20), (bx - 5, by + 6)], fill=(30, 110, 220), width=3)
        draw.line([(bx, by + 20), (bx - 5, by + 6)], fill=(30, 110, 220), width=3)
        draw.line([(bx, by + 20), (bx + 14, by + 4)], fill=(30, 110, 220), width=3)
        draw.line([(bx + 18, by + 20), (bx + 14, by + 4)], fill=(30, 110, 220), width=3)
        draw.line([(bx + 10, by), (bx + 18, by)], fill=(30, 30, 30), width=3)

        bear_color = (115, 68, 32)
        draw.ellipse([bx - 22, by - 24, bx + 16, by + 10], fill=bear_color)
        draw.ellipse([bx + 4, by - 36, bx + 24, by - 16], fill=bear_color)
        draw.ellipse([bx + 6, by - 39, bx + 12, by - 33], fill=bear_color)
        draw.ellipse([bx + 18, by - 39, bx + 24, by - 33], fill=bear_color)
        draw.ellipse([bx + 16, by - 26, bx + 27, by - 18], fill=(165, 110, 65))
        draw.point((bx + 25, by - 23), fill=(20, 20, 20))
        draw.point((bx + 15, by - 28), fill=(20, 20, 20))
        draw.line([(bx + 2, by - 12), (bx + 14, by)], fill=bear_color, width=5)
        draw.line([(bx - 10, by), (bx - 2, by + 18)], fill=bear_color, width=5)

    elif subject_key in ("hydrant_geyser_cat", "fire_hydrant"):
        draw.rectangle([0, 0, w, int(h * 0.45)], fill=(180, 205, 225))
        draw.rectangle([0, int(h * 0.45), w, int(h * 0.65)], fill=(160, 165, 170))
        draw.rectangle([0, int(h * 0.65), w, h], fill=(60, 62, 66))
        draw.line([(0, int(h * 0.65)), (w, int(h * 0.65))], fill=(110, 115, 120), width=3)

        hx = int(w * 0.32)
        hy = int(h * 0.6)
        draw.polygon([(hx - 6, hy - 10), (hx - 22, 10), (hx + 22, 10), (hx + 6, hy - 10)], fill=(70, 160, 245))
        draw.polygon([(hx - 3, hy - 10), (hx - 12, 12), (hx + 12, 12), (hx + 3, hy - 10)], fill=(180, 230, 255))
        for sp_x, sp_y in [(hx - 26, 18), (hx + 24, 16), (hx - 34, 30), (hx + 32, 28), (hx - 8, 8), (hx + 12, 6)]:
            draw.ellipse([sp_x - 5, sp_y - 5, sp_x + 5, sp_y + 5], fill=(190, 235, 255))

        draw.rectangle([hx - 12, hy - 16, hx + 12, hy + 10], fill=(220, 30, 30))
        draw.rectangle([hx - 18, hy - 4, hx - 12, hy + 4], fill=(210, 190, 30))
        draw.rectangle([hx + 12, hy - 4, hx + 18, hy + 4], fill=(210, 190, 30))

        cx = int(w * 0.72)
        cy = int(h * 0.62)
        for dx, dy in [(cx - 8, cy - 8), (cx + 4, cy - 14), (cx - 16, cy + 2)]:
            draw.point((dx, dy), fill=(100, 190, 250))
        draw.ellipse([cx - 18, cy - 6, cx + 14, cy + 6], fill=(30, 30, 35))
        draw.ellipse([cx + 10, cy - 12, cx + 22, cy], fill=(30, 30, 35))
        draw.polygon([(cx + 12, cy - 10), (cx + 8, cy - 16), (cx + 16, cy - 11)], fill=(30, 30, 35))
        draw.polygon([(cx + 17, cy - 10), (cx + 15, cy - 17), (cx + 21, cy - 10)], fill=(30, 30, 35))
        draw.ellipse([cx + 16, cy - 8, cx + 19, cy - 5], fill=(255, 240, 50))
        draw.line([(cx - 12, cy + 4), (cx - 24, cy + 12)], fill=(30, 30, 35), width=3)
        draw.line([(cx + 8, cy + 4), (cx + 20, cy + 12)], fill=(30, 30, 35), width=3)
        draw.line([(cx - 16, cy - 2), (cx - 28, cy - 16)], fill=(30, 30, 35), width=3)

    elif subject_key in ("raccoon_trash_heist", "stop_sign"):
        draw.rectangle([0, 0, w, int(h * 0.58)], fill=(45, 32, 40))
        for by in range(12, int(h * 0.56), 14):
            draw.line([(0, by), (w, by)], fill=(55, 42, 50), width=1)
        draw.rectangle([0, int(h * 0.58), w, h], fill=(68, 72, 78))
        draw.ellipse([w - 36, 12, w - 16, 32], fill=(250, 250, 220))
        draw.ellipse([w - 30, 10, w - 10, 30], fill=(45, 32, 40))

        # Stop sign on sidewalk
        sx = 28
        draw.line([(sx, int(h * 0.18)), (sx, int(h * 0.72))], fill=(80, 85, 90), width=4)
        draw.ellipse([sx - 14, int(h * 0.16), sx + 14, int(h * 0.34)], fill=(215, 30, 30))
        draw.text((sx - 10, int(h * 0.22)), "STOP", fill=(255, 255, 255))

        # Tipped over metal trash can
        tx, ty = int(w * 0.48), int(h * 0.7)
        draw.polygon([(tx - 18, ty - 16), (tx + 16, ty - 12), (tx + 16, ty + 14), (tx - 18, ty + 14)], fill=(160, 165, 170), outline=(90, 95, 100), width=2)
        draw.ellipse([tx + 22, ty - 12, tx + 34, ty + 14], fill=(145, 150, 155), outline=(80, 85, 90), width=2)
        draw.polygon([(tx + 18, ty + 6), (tx + 28, ty + 4), (tx + 24, ty + 10)], fill=(250, 230, 40))
        draw.ellipse([tx + 28, ty + 6, tx + 36, ty + 14], fill=(220, 50, 40))
        draw.ellipse([tx + 10, ty + 8, tx + 20, ty + 16], fill=(30, 30, 35))

        # Masked Raccoon
        rx, ry = int(w * 0.68), int(h * 0.68)
        draw.ellipse([rx - 8, ry - 12, rx + 18, ry + 8], fill=(120, 125, 130))
        draw.ellipse([rx - 16, ry - 8, rx - 4, ry + 4], fill=(120, 125, 130))
        draw.rectangle([rx - 14, ry - 5, rx - 6, ry], fill=(20, 20, 20))
        draw.point((rx - 10, ry - 3), fill=(255, 255, 255))
        draw.polygon([(rx - 12, ry - 8), (rx - 10, ry - 16), (rx - 7, ry - 8)], fill=(60, 60, 65))
        draw.line([(rx + 14, ry), (rx + 32, ry - 8)], fill=(120, 125, 130), width=6)
        draw.line([(rx + 18, ry - 2), (rx + 22, ry - 4)], fill=(25, 25, 25), width=6)
        draw.line([(rx + 26, ry - 6), (rx + 30, ry - 8)], fill=(25, 25, 25), width=6)

    elif subject_key in ("robot_walking_dog", "traffic_light"):
        draw.rectangle([0, 0, w, int(h * 0.55)], fill=(30, 25, 50))
        draw.rectangle([15, int(h * 0.15), 45, int(h * 0.55)], fill=(20, 18, 35))
        draw.rectangle([50, int(h * 0.22), 85, int(h * 0.55)], fill=(25, 22, 42))
        draw.rectangle([90, int(h * 0.12), 125, int(h * 0.55)], fill=(18, 16, 32))
        for wy in range(int(h * 0.2), int(h * 0.5), 12):
            draw.point((25, wy), fill=(250, 210, 60))
            draw.point((35, wy), fill=(70, 220, 240))
            draw.point((65, wy), fill=(255, 80, 160))
            draw.point((105, wy), fill=(250, 210, 60))
        draw.rectangle([0, int(h * 0.55), w, int(h * 0.7)], fill=(65, 70, 80))
        draw.rectangle([0, int(h * 0.7), w, h], fill=(35, 38, 45))
        draw.line([(0, int(h * 0.7)), (w, int(h * 0.7))], fill=(0, 220, 200), width=2)

        tx = 22
        draw.line([(tx, int(h * 0.25)), (tx, int(h * 0.7))], fill=(50, 55, 60), width=3)
        draw.rectangle([tx - 6, int(h * 0.22), tx + 6, int(h * 0.44)], fill=(20, 22, 25))
        draw.ellipse([tx - 3, int(h * 0.24), tx + 3, int(h * 0.29)], fill=(240, 30, 30))
        draw.ellipse([tx - 3, int(h * 0.31), tx + 3, int(h * 0.36)], fill=(240, 200, 30))
        draw.ellipse([tx - 3, int(h * 0.38), tx + 3, int(h * 0.43)], fill=(30, 230, 60))

        rx, ry = int(w * 0.48), int(h * 0.55)
        draw.line([(rx, ry - 32), (rx, ry - 38)], fill=(180, 185, 195), width=2)
        draw.ellipse([rx - 2, ry - 41, rx + 2, ry - 37], fill=(255, 50, 50))
        draw.rectangle([rx - 8, ry - 32, rx + 8, ry - 20], fill=(175, 180, 190), outline=(60, 65, 75))
        draw.rectangle([rx - 5, ry - 28, rx + 5, ry - 24], fill=(0, 240, 255))
        draw.rectangle([rx - 9, ry - 18, rx + 9, ry], fill=(160, 165, 175), outline=(60, 65, 75))
        draw.line([(rx - 5, ry), (rx - 6, ry + 16)], fill=(130, 135, 145), width=4)
        draw.line([(rx + 5, ry), (rx + 6, ry + 16)], fill=(130, 135, 145), width=4)
        draw.line([(rx + 8, ry - 14), (rx + 18, ry - 6)], fill=(130, 135, 145), width=3)

        dog_x, dog_y = int(w * 0.78), int(h * 0.65)
        draw.line([(rx + 18, ry - 6), (dog_x - 6, dog_y - 6)], fill=(255, 60, 60), width=2)
        draw.rectangle([dog_x - 12, dog_y - 8, dog_x + 8, dog_y + 4], fill=(210, 215, 225))
        draw.rectangle([dog_x + 6, dog_y - 14, dog_x + 16, dog_y - 6], fill=(210, 215, 225))
        draw.point((dog_x + 13, dog_y - 11), fill=(0, 255, 200))
        draw.line([(dog_x + 8, dog_y - 14), (dog_x + 6, dog_y - 19)], fill=(120, 125, 135), width=2)
        draw.line([(dog_x - 9, dog_y + 4), (dog_x - 11, dog_y + 12)], fill=(120, 125, 135), width=2)
        draw.line([(dog_x - 3, dog_y + 4), (dog_x - 5, dog_y + 12)], fill=(120, 125, 135), width=2)
        draw.line([(dog_x + 2, dog_y + 4), (dog_x + 4, dog_y + 12)], fill=(120, 125, 135), width=2)
        draw.line([(dog_x + 6, dog_y + 4), (dog_x + 8, dog_y + 12)], fill=(120, 125, 135), width=2)
        draw.line([(dog_x - 12, dog_y - 4), (dog_x - 18, dog_y - 12)], fill=(120, 125, 135), width=2)

    elif subject_key == "ufo_at_red_light":
        draw.rectangle([0, 0, w, int(h * 0.55)], fill=(120, 70, 110))
        draw.rectangle([10, int(h * 0.35), 45, int(h * 0.55)], fill=(65, 40, 75))
        draw.rectangle([115, int(h * 0.3), 150, int(h * 0.55)], fill=(65, 40, 75))
        draw.rectangle([0, int(h * 0.55), w, h], fill=(50, 52, 58))
        for zx in range(20, w - 20, 28):
            draw.polygon([(zx, int(h * 0.62)), (zx + 14, int(h * 0.62)), (zx + 18, int(h * 0.95)), (zx + 4, int(h * 0.95))], fill=(240, 240, 245))

        tx = int(w * 0.3)
        draw.line([(tx, int(h * 0.15)), (tx, int(h * 0.65))], fill=(40, 42, 45), width=4)
        draw.rectangle([tx - 8, int(h * 0.12), tx + 8, int(h * 0.42)], fill=(20, 22, 25), outline=(70, 75, 80))
        draw.ellipse([tx - 10, int(h * 0.14) - 4, tx + 10, int(h * 0.22) + 4], fill=(120, 30, 30))
        draw.ellipse([tx - 5, int(h * 0.14), tx + 5, int(h * 0.22)], fill=(255, 30, 30))
        draw.ellipse([tx - 4, int(h * 0.24), tx + 4, int(h * 0.30)], fill=(70, 60, 20))
        draw.ellipse([tx - 4, int(h * 0.32), tx + 4, int(h * 0.38)], fill=(20, 60, 30))

        ux, uy = int(w * 0.68), int(h * 0.48)
        draw.ellipse([ux - 12, uy - 14, ux + 12, uy + 2], fill=(120, 220, 240))
        draw.ellipse([ux - 6, uy - 10, ux + 6, uy], fill=(60, 210, 80))
        draw.point((ux - 2, uy - 6), fill=(10, 10, 10))
        draw.point((ux + 2, uy - 6), fill=(10, 10, 10))
        draw.ellipse([ux - 28, uy - 4, ux + 28, uy + 10], fill=(170, 180, 195), outline=(90, 95, 105), width=2)
        for lx in [-18, -9, 0, 9, 18]:
            draw.point((ux + lx, uy + 3), fill=(255, 230, 50))

    elif subject_key == "cat_blocking_traffic":
        draw.rectangle([0, 0, w, int(h * 0.4)], fill=(140, 200, 240))
        draw.rectangle([0, int(h * 0.4), w, int(h * 0.52)], fill=(60, 140, 65))
        draw.rectangle([0, int(h * 0.52), w, h], fill=(55, 58, 62))
        sx = w - 16
        draw.line([(sx, int(h * 0.3)), (sx, int(h * 0.56))], fill=(70, 75, 80), width=3)
        draw.ellipse([sx - 10, int(h * 0.22), sx + 10, int(h * 0.38)], fill=(220, 30, 30))
        draw.text((sx - 7, int(h * 0.26)), "STOP", fill=(255, 255, 255))

        bx, by = int(w * 0.22), int(h * 0.6)
        draw.rectangle([bx - 26, by - 14, bx + 20, by + 8], fill=(250, 195, 25), outline=(30, 30, 30), width=2)
        for wx in [-18, -6, 6]:
            draw.rectangle([bx + wx, by - 10, bx + wx + 8, by - 2], fill=(160, 215, 245))
        draw.ellipse([bx - 16, by + 4, bx - 6, by + 16], fill=(30, 30, 30))
        draw.ellipse([bx + 6, by + 4, bx + 16, by + 16], fill=(30, 30, 30))

        cx, cy = int(w * 0.64), int(h * 0.72)
        cat_color = (235, 130, 45)
        draw.ellipse([cx - 32, cy - 14, cx + 28, cy + 14], fill=cat_color)
        for st_x in range(cx - 20, cx + 18, 10):
            draw.line([(st_x, cy - 12), (st_x - 3, cy + 8)], fill=(185, 90, 25), width=3)
        draw.ellipse([cx + 20, cy - 12, cx + 38, cy + 8], fill=cat_color)
        draw.polygon([(cx + 28, cy - 11), (cx + 34, cy - 20), (cx + 38, cy - 10)], fill=cat_color)
        draw.arc([cx + 26, cy - 6, cx + 32, cy - 1], 0, 180, fill=(30, 30, 30), width=2)
        draw.arc([cx + 32, cy - 6, cx + 38, cy - 1], 0, 180, fill=(30, 30, 30), width=2)
        draw.ellipse([cx - 2, cy + 8, cx + 10, cy + 18], fill=cat_color)
        draw.ellipse([cx - 16, cy + 8, cx - 4, cy + 18], fill=cat_color)
        draw.arc([cx - 44, cy - 10, cx - 22, cy + 14], 90, 270, fill=cat_color, width=5)

    elif subject_key == "snowman_campfire":
        draw.rectangle([0, 0, w, int(h * 0.65)], fill=(18, 24, 45))
        for sx, sy in [(20, 15), (55, 25), (105, 12), (140, 35)]:
            draw.point((sx, sy), fill=(255, 255, 220))
        draw.rectangle([0, int(h * 0.65), w, h], fill=(230, 235, 245))
        for tx in [15, w - 28]:
            draw.polygon([(tx, int(h * 0.66)), (tx + 10, int(h * 0.38)), (tx + 20, int(h * 0.66))], fill=(25, 65, 40))

        fx, fy = int(w * 0.68), int(h * 0.76)
        draw.line([(fx - 14, fy + 8), (fx + 14, fy + 4)], fill=(90, 55, 30), width=4)
        draw.line([(fx - 12, fy + 4), (fx + 12, fy + 8)], fill=(80, 50, 25), width=4)
        draw.polygon([(fx - 10, fy + 6), (fx, fy - 18), (fx + 10, fy + 6)], fill=(245, 90, 20))
        draw.polygon([(fx - 6, fy + 6), (fx - 1, fy - 14), (fx + 6, fy + 6)], fill=(255, 210, 40))
        for ex, ey in [(fx - 4, fy - 22), (fx + 5, fy - 26), (fx + 1, fy - 30)]:
            draw.point((ex, ey), fill=(255, 220, 50))

        sm_x, sm_y = int(w * 0.36), int(h * 0.72)
        draw.ellipse([sm_x - 22, sm_y + 4, sm_x + 22, sm_y + 18], fill=(245, 248, 255))
        draw.ellipse([sm_x - 18, sm_y - 10, sm_x + 16, sm_y + 12], fill=(245, 248, 255))
        draw.ellipse([sm_x - 13, sm_y - 24, sm_x + 13, sm_y - 6], fill=(245, 248, 255))
        draw.ellipse([sm_x - 9, sm_y - 36, sm_x + 11, sm_y - 20], fill=(245, 248, 255))
        draw.rectangle([sm_x - 12, sm_y - 38, sm_x + 14, sm_y - 35], fill=(30, 30, 35))
        draw.rectangle([sm_x - 6, sm_y - 48, sm_x + 8, sm_y - 38], fill=(30, 30, 35))
        draw.polygon([(sm_x + 6, sm_y - 28), (sm_x + 16, sm_y - 27), (sm_x + 6, sm_y - 25)], fill=(245, 120, 20))
        draw.point((sm_x + 2, sm_y - 30), fill=(20, 20, 20))
        draw.point((sm_x + 7, sm_y - 30), fill=(20, 20, 20))
        draw.line([(sm_x - 12, sm_y - 16), (sm_x - 24, sm_y - 24)], fill=(100, 65, 35), width=2)
        draw.line([(sm_x + 12, sm_y - 16), (sm_x + 22, sm_y - 12)], fill=(100, 65, 35), width=2)

    elif subject_key == "shark_in_flood":
        draw.rectangle([0, 0, w, int(h * 0.38)], fill=(70, 78, 92))
        draw.ellipse([10, -10, 90, 40], fill=(48, 55, 68))
        draw.ellipse([70, -12, 160, 42], fill=(42, 48, 60))
        for rx, ry in [(25, 25), (70, 20), (115, 30), (145, 18), (40, 50), (95, 45)]:
            draw.line([(rx, ry), (rx - 4, ry + 14)], fill=(185, 210, 235), width=2)

        # Deep flooded water
        draw.rectangle([0, int(h * 0.38), w, h], fill=(30, 75, 120))

        # Flooded Stop Sign on left
        sx = 34
        draw.line([(sx, int(h * 0.2)), (sx, int(h * 0.62))], fill=(80, 85, 90), width=4)
        draw.ellipse([sx - 14, int(h * 0.14), sx + 14, int(h * 0.36)], fill=(225, 25, 25))
        draw.text((sx - 10, int(h * 0.22)), "STOP", fill=(255, 255, 255))

        # Submerged Bicycle wheels in water
        draw.arc([sx + 16, int(h * 0.44), sx + 36, int(h * 0.62)], 180, 360, fill=(40, 120, 225), width=3)
        draw.line([(sx + 26, int(h * 0.44)), (sx + 32, int(h * 0.38))], fill=(30, 30, 30), width=3)

        # Prominent Shark dorsal fin swimming right-to-left
        fx, fy = int(w * 0.68), int(h * 0.58)
        draw.polygon([(fx - 24, fy + 14), (fx + 4, fy - 24), (fx + 16, fy + 14)], fill=(95, 105, 120), outline=(45, 55, 68), width=2)
        # Foam ripples
        draw.line([(fx - 32, fy + 14), (fx + 24, fy + 14)], fill=(200, 230, 255), width=2)
        draw.arc([fx - 18, fy + 10, fx + 8, fy + 18], 0, 180, fill=(210, 235, 255), width=2)

    elif subject_key == "wizard_summoning_pizza":
        draw.rectangle([0, 0, w, int(h * 0.6)], fill=(20, 15, 38))
        draw.ellipse([10, -10, 90, 40], fill=(45, 35, 65))
        draw.ellipse([70, -15, 155, 45], fill=(35, 25, 55))
        draw.line([(40, 30), (55, 55)], fill=(255, 255, 120), width=2)
        draw.line([(55, 55), (50, 65)], fill=(255, 255, 120), width=2)
        draw.line([(50, 65), (65, 88)], fill=(255, 255, 120), width=2)
        draw.rectangle([0, int(h * 0.6), w, h], fill=(85, 45, 40))
        draw.rectangle([0, int(h * 0.58), w, int(h * 0.61)], fill=(120, 70, 60))

        wx, wy = int(w * 0.28), int(h * 0.58)
        draw.polygon([(wx - 12, wy + 24), (wx + 10, wy + 24), (wx - 1, wy)], fill=(95, 35, 140))
        draw.ellipse([wx - 6, wy - 8, wx + 6, wy + 4], fill=(245, 205, 185))
        draw.polygon([(wx - 5, wy), (wx + 5, wy), (wx, wy + 10)], fill=(240, 240, 245))
        draw.polygon([(wx - 12, wy - 7), (wx + 12, wy - 7), (wx, wy - 26)], fill=(75, 25, 115))
        draw.ellipse([wx - 14, wy - 8, wx + 14, wy - 5], fill=(75, 25, 115))
        draw.line([(wx + 8, wy + 22), (wx + 18, wy - 18)], fill=(120, 75, 40), width=3)
        draw.ellipse([wx + 15, wy - 24, wx + 23, wy - 16], fill=(100, 240, 255))

        pz_x, pz_y = int(w * 0.68), int(h * 0.42)
        draw.polygon([(pz_x - 22, pz_y - 16), (pz_x + 22, pz_y - 16), (pz_x, pz_y + 22)], fill=(245, 195, 45))
        draw.ellipse([pz_x - 24, pz_y - 22, pz_x + 24, pz_y - 12], fill=(195, 130, 65))
        for px, py in [(pz_x - 8, pz_y - 8), (pz_x + 8, pz_y - 6), (pz_x, pz_y + 6)]:
            draw.ellipse([px - 4, py - 4, px + 4, py + 4], fill=(190, 35, 30))
        draw.line([(pz_x, pz_y + 20), (pz_x, pz_y + 28)], fill=(245, 215, 60), width=2)
        for sx, sy in [(pz_x - 24, pz_y), (pz_x + 26, pz_y + 4), (pz_x - 12, pz_y + 18)]:
            draw.point((sx, sy), fill=(255, 240, 100))

    else:
        # Fallback multi-element scene
        draw.rectangle([0, 0, w, int(h * 0.6)], fill=(70, 120, 180))
        draw.rectangle([0, int(h * 0.6), w, h], fill=(60, 60, 65))
        draw.ellipse([w // 2 - 20, int(h * 0.5), w // 2 + 20, int(h * 0.7)], fill=(220, 40, 40))

    return img

def is_attngan_active() -> bool:
    """Returns True if AttnGAN model is loaded and ready for generations."""
    if get_attngan_model is None:
        return False
    try:
        return get_attngan_model(dataset="coco") is not None
    except Exception:
        return False

def create_captcha_asset(prompt_or_key: str, output_path: str, target_size=(360, 360)) -> str:
    """
    Generates a crunchy CAPTCHA image using the AttnGAN text-to-image neural network.
    Accepts either a dynamic prompt string or a subject key.
    Falls back gracefully to procedural generation if AttnGAN is unavailable.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    if prompt_or_key in CAPTCHA_SUBJECTS:
        subject_info = CAPTCHA_SUBJECTS[prompt_or_key]
        prompt = subject_info.get("attngan_prompt") or subject_info.get("description") or prompt_or_key.replace("_", " ")
        fallback_key = prompt_or_key
    else:
        prompt = prompt_or_key
        fallback_key = random.choice(list(CAPTCHA_SUBJECTS.keys()))

    if generate_attngan_captcha is not None:
        try:
            generate_attngan_captcha(prompt, output_path=output_path, target_size=target_size)
            return output_path
        except Exception as e:
            print(f"[AttnGAN] Generation failed for '{prompt[:30]}...' ({e}); using procedural fallback.")

    # Procedural Fallback if AttnGAN model failed or was not loaded
    base_img = draw_subject_base(fallback_key, size=(160, 160))
    noise = np.random.randint(-12, 12, (160, 160, 3), dtype=np.int16)
    arr = np.clip(np.array(base_img, dtype=np.int16) + noise, 0, 255).astype(np.uint8)
    noisy_img = Image.fromarray(arr)

    buf = io.BytesIO()
    noisy_img.save(buf, "JPEG", quality=35)
    buf.seek(0)
    fried = Image.open(buf)

    captcha_img = fried.resize(target_size, resample=Image.Resampling.NEAREST)
    enhancer = ImageEnhance.Contrast(captcha_img)
    captcha_img = enhancer.enhance(1.15)
    captcha_img.save(output_path, "PNG")

    return output_path
