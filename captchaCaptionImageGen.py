import torch
import numpy as np
from PIL import Image, ImageEnhance, ImageOps

def upscale_to_captcha(tiny_image_tensor, target_size=(300, 300)):
    """
    Takes a small model output, converts it to PIL, and enforces
    a pixelated, low-fidelity CAPTCHA look.
    """
    # 1. Convert your model's raw array/tensor output to a standard PIL Image
    # (Assuming tensor is shape (C, H, W) normalized between 0-1)
    if isinstance(tiny_image_tensor, torch.Tensor):
        img_np = tiny_image_tensor.detach().cpu().permute(1, 2, 0).numpy()
        img_np = (np.clip(img_np, 0, 1) * 255).astype(np.uint8)
    else:
        img_np = tiny_image_tensor # Raw numpy alternative
        
    img = Image.fromarray(img_np)
    
    # 2. INTENTIONAL DEGRADATION: Save as an aggressively compressed JPEG
    # This adds realistic compression artifacts around the edges
    temp_path = "temp_compressed.jpg"
    img.save(temp_path, "JPEG", quality=10) # 10% quality is delightfully fried
    img = Image.open(temp_path)
    
    # 3. THE PIL TRICK: Upscale using NEAREST NEIGHBOR 
    # This prevents smoothing and locks in raw, crunchy square pixels
    captcha_img = img.resize(target_size, resample=Image.Resampling.NEAREST)
    
    # 4. CAPTCHA POST-PROCESSING: Add a bit of contrast/noise overlay if desired
    # Making it slightly harder to read boosts the captcha vibe
    enhancer = ImageEnhance.Contrast(captcha_img)
    captcha_img = enhancer.enhance(1.4) # Crush the shadows slightly
    
    return captcha_img

# --- SIMULATION FOR YOUR GAME ENGINE ---
if __name__ == "__main__":
    # Simulate a fake 128x128 noise image output from AttnGAN
    fake_model_output = torch.rand(3, 128, 128) 
    
    # Process it
    final_captcha = upscale_to_captcha(fake_model_output, target_size=(400, 400))
    
    # Save the asset for your mini-game UI
    final_captcha.save("captcha_challenge_1.png")
    print("Crunchy CAPTCHA image generated and saved successfully!")
