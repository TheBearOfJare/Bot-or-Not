import os
import io
import re
import sys
import torch
import numpy as np
from PIL import Image, ImageEnhance

# Ensure AttnGAN eval module is importable
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ATTNGAN_EVAL_DIR = os.path.join(CURRENT_DIR, "AttnGAN", "eval")
if ATTNGAN_EVAL_DIR not in sys.path:
    sys.path.insert(0, ATTNGAN_EVAL_DIR)

from miscc.config import cfg
from model import RNN_ENCODER, G_NET

_CACHED_MODELS = {}

def upscale_to_captcha(tiny_image_tensor, target_size=(360, 360)):
    """
    Takes a small model output, converts it to PIL, and enforces
    a pixelated, low-fidelity CAPTCHA look.
    """
    # 1. Convert model's raw array/tensor output to standard PIL Image
    if isinstance(tiny_image_tensor, torch.Tensor):
        img_np = tiny_image_tensor.detach().cpu().permute(1, 2, 0).numpy()
        img_np = (np.clip(img_np, 0, 1) * 255).astype(np.uint8)
    else:
        img_np = tiny_image_tensor
        
    img = Image.fromarray(img_np)
    
    # 2. INTENTIONAL DEGRADATION: Save as a compressed JPEG in memory
    # 35 quality creates authentic blocky CAPTCHA compression without wiping out object silhouettes
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=35)
    buf.seek(0)
    fried = Image.open(buf)
    
    # 3. THE PIL TRICK: Upscale using NEAREST NEIGHBOR 
    # This prevents smoothing and locks in raw, crunchy square pixels
    captcha_img = fried.resize(target_size, resample=Image.Resampling.NEAREST)
    
    # 4. CAPTCHA POST-PROCESSING: Mild contrast adjustment to preserve object shadows
    enhancer = ImageEnhance.Contrast(captcha_img)
    captcha_img = enhancer.enhance(1.15)
    
    return captcha_img

def get_attngan_model(dataset="coco"):
    """
    Loads and caches AttnGAN generator, text encoder, and vocabulary.
    Defaults to COCO dataset (with bird dataset available as fallback).
    """
    global _CACHED_MODELS
    if dataset in _CACHED_MODELS:
        return _CACHED_MODELS[dataset]

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    cfg.CUDA = (device.type == "cuda")

    if dataset == "coco":
        cfg.GAN.GF_DIM = 48
        cfg.GAN.DF_DIM = 96
        cfg.GAN.R_NUM = 3
        cfg.TEXT.EMBEDDING_DIM = 256
        pickle_path = os.path.join(CURRENT_DIR, "AttnGAN", "data", "coco", "captions.pickle")
        text_encoder_path = os.path.join(CURRENT_DIR, "AttnGAN", "DAMSMencoders", "coco", "text_encoder100.pth")
        netG_path = os.path.join(CURRENT_DIR, "AttnGAN", "models", "coco_AttnGAN2.pth")
    else:
        cfg.GAN.GF_DIM = 32
        cfg.GAN.DF_DIM = 64
        cfg.GAN.R_NUM = 2
        cfg.TEXT.EMBEDDING_DIM = 256
        pickle_path = os.path.join(CURRENT_DIR, "AttnGAN", "eval", "data", "captions.pickle")
        text_encoder_path = os.path.join(CURRENT_DIR, "AttnGAN", "eval", "data", "text_encoder200.pth")
        netG_path = os.path.join(CURRENT_DIR, "AttnGAN", "eval", "data", "bird_AttnGAN2.pth")

    if not (os.path.exists(pickle_path) and os.path.exists(text_encoder_path) and os.path.exists(netG_path)):
        return None

    import pickle
    with open(pickle_path, "rb") as f:
        pickle_data = pickle.load(f)
    wordtoix = pickle_data[3]

    text_encoder = RNN_ENCODER(len(wordtoix), nhidden=cfg.TEXT.EMBEDDING_DIM).to(device)
    text_encoder.load_state_dict(torch.load(text_encoder_path, map_location=device))
    text_encoder.eval()

    netG = G_NET().to(device)
    netG.load_state_dict(torch.load(netG_path, map_location=device))
    netG.eval()

    bundle = {
        "wordtoix": wordtoix,
        "text_encoder": text_encoder,
        "netG": netG,
        "device": device,
        "dataset": dataset
    }
    _CACHED_MODELS[dataset] = bundle
    return bundle

def generate_attngan_captcha(caption_text: str, output_path: str = None, target_size=(360, 360)) -> Image.Image:
    """
    Generates a full crunchy CAPTCHA using the COCO AttnGAN model.
    """
    models = get_attngan_model(dataset="coco") or get_attngan_model(dataset="birds")
    if not models:
        raise RuntimeError("No AttnGAN weights or vocabulary files found.")

    wordtoix = models["wordtoix"]
    text_encoder = models["text_encoder"]
    netG = models["netG"]
    device = models["device"]

    words = re.findall(r"[a-zA-Z]+", caption_text.lower())
    cap_v = [wordtoix[w] for w in words if w in wordtoix]
    if not cap_v:
        cap_v = [wordtoix.get("car", wordtoix.get("cat", 0))]

    captions = torch.tensor([cap_v], dtype=torch.int64, device=device)
    cap_lens = torch.tensor([len(cap_v)], dtype=torch.int64, device=device)

    with torch.no_grad():
        hidden = text_encoder.init_hidden(1)
        words_embs, sent_emb = text_encoder(captions, cap_lens, hidden)
        mask = (captions == 0)
        noise = torch.randn(1, 100, device=device)
        fake_imgs, _, _, _ = netG(noise, sent_emb, words_embs, mask)

    # Normalize [-1, 1] -> [0, 1] tensor
    normalized_tensor = (fake_imgs[-1][0] + 1.0) / 2.0
    captcha_img = upscale_to_captcha(normalized_tensor, target_size=target_size)

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        captcha_img.save(output_path, "PNG")

    return captcha_img

if __name__ == "__main__":
    prompt = "a cat sitting on the roof of a parked red car"
    print(f"Generating crunchy CAPTCHA image with COCO AttnGAN for prompt: '{prompt}'...")
    final_captcha = generate_attngan_captcha(prompt, output_path="captcha_challenge_1.png", target_size=(360, 360))
    print("Crunchy CAPTCHA image generated and saved to captcha_challenge_1.png successfully!")