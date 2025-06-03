import os
import json
import datetime
import hashlib
from PIL import Image
from modules import shared, images
# StableDiffusionProcessing is imported conditionally for type hinting to avoid circular imports at load time
if hasattr(shared, 'StableDiffusionProcessing'):
    StableDiffusionProcessing = shared.StableDiffusionProcessing
else:
    class StableDiffusionProcessing:
        pass # Dummy class for type hinting if not available

GALLERY_DIR = "gallery"
os.makedirs(GALLERY_DIR, exist_ok=True)

def get_unique_filename(prompt_text: str):
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")
    prompt_hash = hashlib.md5((prompt_text or "").encode('utf-8')).hexdigest()[:8]
    return f"{timestamp}_{prompt_hash}"

def save_to_gallery(image: Image.Image, p: StableDiffusionProcessing, original_prompt: str, original_negative_prompt: str):
    if not image:
        print("Error: Image is missing for gallery save.")
        return None, None
    if not p:
        print("Error: Processing data (p) is missing for gallery save.")
        return None, None

    unique_base = get_unique_filename(original_prompt or "gallery_image")

    image_filename = f"{unique_base}.png"
    json_filename = f"{unique_base}.json"

    image_path = os.path.join(GALLERY_DIR, image_filename)
    json_path = os.path.join(GALLERY_DIR, json_filename)

    try:
        # Construct a basic infotext string for embedding, primarily for quick reference
        # The JSON file is the canonical source of all parameters.
        info_to_embed = f"{original_prompt}\nNegative prompt: {original_negative_prompt}\nSteps: {p.steps}, Seed: {p.seed}, CFG scale: {p.cfg_scale}, Size: {p.width}x{p.height}, Model hash: {getattr(p, 'sd_model_hash', 'N/A')}, Sampler: {p.sampler_name}"

        # Use existing save_image_with_geninfo if available and opts.enable_pnginfo is True
        if hasattr(images, 'save_image_with_geninfo') and shared.opts.enable_pnginfo:
            images.save_image_with_geninfo(image, info_to_embed, image_path, pnginfo_section_name="parameters")
        else:
            image.save(image_path)

    except Exception as e:
        print(f"Error saving image to gallery {image_path}: {e}")
        return None, None

    params_to_save = {
        "original_prompt": original_prompt,
        "original_negative_prompt": original_negative_prompt,
        "steps": getattr(p, 'steps', None),
        "sampler_name": getattr(p, 'sampler_name', None),
        "scheduler": getattr(p, 'scheduler', None),
        "cfg_scale": getattr(p, 'cfg_scale', None),
        "seed": getattr(p, 'seed', None),
        "width": getattr(p, 'width', None),
        "height": getattr(p, 'height', None),
        "model_hash": getattr(p, 'sd_model_hash', None),
        "model_name": getattr(p, 'sd_model_name', None),
        "sd_vae_name": getattr(p, 'sd_vae_name', None),
        "sd_vae_hash": getattr(p, 'sd_vae_hash', None),
        "denoising_strength": getattr(p, 'denoising_strength', None),
        "subseed": getattr(p, 'subseed', None) if hasattr(p, 'subseed_strength') and getattr(p, 'subseed_strength', 0) > 0 else None,
        "subseed_strength": getattr(p, 'subseed_strength', 0) if hasattr(p, 'subseed_strength') and getattr(p, 'subseed_strength', 0) > 0 else None,
        "seed_resize_from_w": getattr(p, 'seed_resize_from_w', 0) if hasattr(p, 'seed_resize_from_w') and getattr(p, 'seed_resize_from_w', 0) > 0 else None,
        "seed_resize_from_h": getattr(p, 'seed_resize_from_h', 0) if hasattr(p, 'seed_resize_from_h') and getattr(p, 'seed_resize_from_h', 0) > 0 else None,
        "clip_skip": int(shared.opts.CLIP_stop_at_last_layers) if hasattr(shared, 'opts') else None,
        "extra_generation_params": {},
        "face_restoration": getattr(p, 'restore_faces', None),
        "tiling": getattr(p, 'tiling', None),
        "image_cfg_scale": getattr(p, 'image_cfg_scale', None), # For img2img
        "mask_blur": getattr(p, 'mask_blur', None), # For img2img inpaint
        "inpainting_fill": getattr(p, 'inpainting_fill', None), # For img2img inpaint
        "inpaint_full_res": getattr(p, 'inpaint_full_res', None), # For img2img inpaint
        "inpaint_full_res_padding": getattr(p, 'inpaint_full_res_padding', None), # For img2img inpaint
        "inpainting_mask_invert": getattr(p, 'inpainting_mask_invert', None), # For img2img inpaint
    }

    if hasattr(p, 'extra_generation_params') and p.extra_generation_params:
        for k, v in p.extra_generation_params.items():
            try:
                # Ensure the value is JSON serializable
                json.dumps({k: v})
                params_to_save["extra_generation_params"][k] = v
            except TypeError:
                print(f"Warning: Parameter '{k}' with value '{v}' in extra_generation_params is not JSON serializable and will be skipped for gallery.")

    # Handling Hires. fix parameters
    if hasattr(p, 'enable_hr') and p.enable_hr:
        params_to_save["enable_hr"] = True
        params_to_save["hr_scale"] = getattr(p, 'hr_scale', 0)
        params_to_save["hr_upscaler"] = getattr(p, 'hr_upscaler', None)
        params_to_save["hr_second_pass_steps"] = getattr(p, 'hr_second_pass_steps', 0)
        params_to_save["hr_resize_x"] = getattr(p, 'hr_resize_x', 0)
        params_to_save["hr_resize_y"] = getattr(p, 'hr_resize_y', 0)
        # Handle potential differences in how hr_prompt and hr_negative_prompt are stored or derived
        hr_prompt_val = getattr(p, 'hr_prompt', '')
        if getattr(p, 'user_left_hr_prompt_empty', False) and not hr_prompt_val: # If user left it empty and it's still empty
             params_to_save["hr_prompt"] = original_prompt
        else:
             params_to_save["hr_prompt"] = hr_prompt_val

        hr_neg_prompt_val = getattr(p, 'hr_negative_prompt', '')
        if getattr(p, 'user_left_hr_negative_prompt_empty', False) and not hr_neg_prompt_val:
             params_to_save["hr_negative_prompt"] = original_negative_prompt
        else:
             params_to_save["hr_negative_prompt"] = hr_neg_prompt_val

        params_to_save["hr_checkpoint_name"] = getattr(p, 'hr_checkpoint_name', None)
        params_to_save["hr_sampler_name"] = getattr(p, 'hr_sampler_name', None)
        params_to_save["hr_scheduler"] = getattr(p, 'hr_scheduler', None)
        params_to_save["hr_cfg"] = getattr(p, 'hr_cfg', None)
        params_to_save["hr_distilled_cfg"] = getattr(p, 'hr_distilled_cfg', None)

    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(params_to_save, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving JSON metadata to gallery {json_path}: {e}")
        if os.path.exists(image_path):
            try:
                os.remove(image_path)
                print(f"Cleaned up image file: {image_path}")
            except Exception as e_rem:
                print(f"Error cleaning up image file {image_path} after JSON save failure: {e_rem}")
        return None, None

    print(f"Saved to gallery: image at {image_path}, metadata at {json_path}")
    return image_path, json_path

def get_gallery_items():
    items = []
    if not os.path.exists(GALLERY_DIR):
        return items

    try:
        # Sort by filename, which should roughly correspond to creation time due to timestamp in filename
        file_list = sorted(os.listdir(GALLERY_DIR), reverse=True)
    except Exception as e:
        print(f"Error listing gallery directory {GALLERY_DIR}: {e}")
        return items

    for f_name in file_list:
        if f_name.lower().endswith(".png"):
            base_name, _ = os.path.splitext(f_name)
            json_filename = f"{base_name}.json"
            json_path = os.path.join(GALLERY_DIR, json_filename)
            image_path = os.path.join(GALLERY_DIR, f_name)

            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as f_json:
                        data = json.load(f_json)
                    # Ensure paths are OS-agnostic for web display if needed, but keep original for file access
                    web_image_path = image_path.replace('\\', '/')
                    prompt_preview = data.get("original_prompt", "")[:100] # Get first 100 chars for preview
                    items.append({
                        "name": base_name,
                        "image_path": image_path, # For local file access
                        "preview_image_path": f"/file={web_image_path}", # For Gradio/web UI
                        "json_path": json_path,
                        "prompt_preview": prompt_preview + "..." if len(data.get("original_prompt", "")) > 100 else prompt_preview,
                        "metadata": data
                    })
                except Exception as e:
                    print(f"Error reading or parsing JSON {json_path}: {e}")
            # Do not log warning for missing JSON if image itself is likely a temp file or non-gallery image
            # else:
            # print(f"Warning: Image {image_path} found without corresponding JSON metadata.")
    return items

def load_gallery_item_data(json_path: str):
    if not json_path or not os.path.exists(json_path):
        print(f"Error: JSON path is invalid or does not exist: {json_path}")
        return None
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"Error loading or parsing gallery item JSON {json_path}: {e}")
        return None

GITIGNORE_FILE = ".gitignore"
# Ensure the entry uses forward slashes and ends with a slash for directories
GALLERY_GITIGNORE_ENTRY = GALLERY_DIR.replace('\\', '/') + '/'

def add_to_gitignore(entry):
    # Normalize the entry to ensure it ends with a slash and uses forward slashes
    normalized_entry = entry.strip().replace('\\', '/')
    if not normalized_entry.endswith('/'):
        normalized_entry += '/'

    if not os.path.exists(GITIGNORE_FILE):
        try:
            with open(GITIGNORE_FILE, 'w', encoding='utf-8') as f:
                f.write(normalized_entry + "\n")
            print(f"Created {GITIGNORE_FILE} and added {normalized_entry}")
        except Exception as e:
            print(f"Error creating .gitignore: {e}")
        return

    try:
        with open(GITIGNORE_FILE, 'r+', encoding='utf-8') as f:
            content = f.read()
            # Normalize existing lines for comparison
            lines = [line.strip().replace('\\', '/') for line in content.splitlines()]

            found = False
            for line in lines:
                # Ensure existing lines are also treated as directories if they don't have an extension
                # and end with a slash for comparison
                current_line_normalized = line
                if not current_line_normalized.endswith('/') and '.' not in current_line_normalized.split('/')[-1]:
                    current_line_normalized += '/'

                if current_line_normalized == normalized_entry:
                    found = True
                    break

            if not found:
                # Ensure there's a newline before adding the new entry if the file is not empty
                if content and not content.endswith('\n') and not content.endswith('\r\n'):
                    f.write("\n")
                f.write(normalized_entry + "\n")
                print(f"Added {normalized_entry} to {GITIGNORE_FILE}")
            else:
                print(f"{normalized_entry} already in {GITIGNORE_FILE}")
    except Exception as e:
        print(f"Error updating .gitignore: {e}")

# Automatically try to add the gallery directory to .gitignore when this module is loaded
add_to_gitignore(GALLERY_GITIGNORE_ENTRY)
