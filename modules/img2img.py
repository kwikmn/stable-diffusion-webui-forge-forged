import os
from contextlib import closing
from pathlib import Path

from PIL import Image, ImageOps, ImageFilter, ImageEnhance, UnidentifiedImageError
import gradio as gr

from modules import images
from modules.infotext_utils import create_override_settings_dict, parse_generation_parameters
from modules.processing import Processed, StableDiffusionProcessingImg2Img, process_images
from modules.shared import opts, state
from modules.sd_models import get_closet_checkpoint_match
import modules.shared as shared
import modules.processing as processing
from modules.ui import plaintext_to_html
import modules.scripts
from modules_forge import main_thread


def process_batch(p, input, output_dir, inpaint_mask_dir, args, to_scale=False, scale_by=1.0, use_png_info=False, png_info_props=None, png_info_dir=None):
    output_dir = output_dir.strip()
    processing.fix_seed(p)

    if isinstance(input, str):
        batch_images = list(shared.walk_files(input, allowed_extensions=(".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".avif")))
    else:
        batch_images = [os.path.abspath(x.name) for x in input]

    is_inpaint_batch = False
    if inpaint_mask_dir:
        inpaint_masks = shared.listfiles(inpaint_mask_dir)
        is_inpaint_batch = bool(inpaint_masks)

        if is_inpaint_batch:
            print(f"\nInpaint batch is enabled. {len(inpaint_masks)} masks found.")

    print(f"Will process {len(batch_images)} images, creating {p.n_iter * p.batch_size} new images for each.")

    state.job_count = len(batch_images) * p.n_iter

    # extract "default" params to use in case getting png info fails
    prompt = p.prompt
    negative_prompt = p.negative_prompt
    seed = p.seed
    cfg_scale = p.cfg_scale
    sampler_name = p.sampler_name
    steps = p.steps
    override_settings = p.override_settings
    sd_model_checkpoint_override = get_closet_checkpoint_match(override_settings.get("sd_model_checkpoint", None))
    batch_results = None
    discard_further_results = False
    for i, image_path_str in enumerate(batch_images): # Renamed variable
        state.job = f"{i+1} out of {len(batch_images)}"
        if state.skipped:
            state.skipped = False

        if state.interrupted or state.stopping_generation:
            break

        try:
            img = images.read(image_path_str)
        except UnidentifiedImageError as e:
            print(e)
            continue
        # Use the EXIF orientation of photos taken by smartphones.
        img = ImageOps.exif_transpose(img)

        if to_scale:
            p.width = int(img.width * scale_by)
            p.height = int(img.height * scale_by)

        p.init_images = [img] * p.batch_size

        image_path = Path(image_path_str) # Use the renamed variable
        if is_inpaint_batch:
            if len(inpaint_masks) == 1:
                mask_image_path = inpaint_masks[0]
            else:
                mask_image_dir = Path(inpaint_mask_dir)
                masks_found = list(mask_image_dir.glob(f"{image_path.stem}.*"))
                if len(masks_found) == 0:
                    print(f"Warning: mask is not found for {image_path} in {mask_image_dir}. Skipping it.")
                    continue
                mask_image_path = masks_found[0]
            mask_image = images.read(mask_image_path)
            p.image_mask = mask_image

        if use_png_info:
            try:
                info_img = img
                if png_info_dir:
                    info_img_path = os.path.join(png_info_dir, os.path.basename(image_path_str))
                    info_img = images.read(info_img_path)
                geninfo, _ = images.read_info_from_image(info_img)
                parsed_parameters = parse_generation_parameters(geninfo)
                parsed_parameters = {k: v for k, v in parsed_parameters.items() if k in (png_info_props or {})}
            except Exception:
                parsed_parameters = {}
            p.prompt = prompt + (" " + parsed_parameters["Prompt"] if "Prompt" in parsed_parameters else "")
            p.negative_prompt = negative_prompt + (" " + parsed_parameters["Negative prompt"] if "Negative prompt" in parsed_parameters else "")
            p.seed = int(parsed_parameters.get("Seed", seed))
            p.cfg_scale = float(parsed_parameters.get("CFG scale", cfg_scale))
            p.sampler_name = parsed_parameters.get("Sampler", sampler_name)
            p.steps = int(parsed_parameters.get("Steps", steps))
            model_info = get_closet_checkpoint_match(parsed_parameters.get("Model hash", None))
            if model_info is not None: p.override_settings['sd_model_checkpoint'] = model_info.name
            elif sd_model_checkpoint_override: p.override_settings['sd_model_checkpoint'] = sd_model_checkpoint_override
            else: p.override_settings.pop("sd_model_checkpoint", None)

        if output_dir:
            p.outpath_samples = output_dir
            p.override_settings['save_to_dirs'] = False
        if opts.img2img_batch_use_original_name:
            filename_pattern = f'{image_path.stem}-[generation_number]' if p.n_iter > 1 or p.batch_size > 1 else f'{image_path.stem}'
            p.override_settings['samples_filename_pattern'] = filename_pattern

        current_processed_obj = None
        try:
            with closing(p): # p will be closed automatically
                proc = modules.scripts.scripts_img2img.run(p, *args)
                if proc is None:
                    proc = process_images(p)
            current_processed_obj = proc
        finally:
            pass # p is already handled by closing()

        if not discard_further_results and current_processed_obj:
            if batch_results:
                batch_results.images.extend(current_processed_obj.images)
                batch_results.infotexts.extend(current_processed_obj.infotexts)
            else:
                batch_results = current_processed_obj
            if 0 <= shared.opts.img2img_batch_show_results_limit < len(batch_results.images):
                discard_further_results = True
                batch_results.images = batch_results.images[:int(shared.opts.img2img_batch_show_results_limit)]
                batch_results.infotexts = batch_results.infotexts[:int(shared.opts.img2img_batch_show_results_limit)]
    return batch_results


def img2img_function(id_task: str, request: gr.Request, mode: int, prompt: str, negative_prompt: str, prompt_styles, init_img, sketch, sketch_fg, init_img_with_mask, init_img_with_mask_fg, inpaint_color_sketch, inpaint_color_sketch_fg, init_img_inpaint, init_mask_inpaint, mask_blur: int, mask_alpha: float, inpainting_fill: int, n_iter: int, batch_size: int, cfg_scale: float, distilled_cfg_scale: float, image_cfg_scale: float, denoising_strength: float, selected_scale_tab: int, height: int, width: int, scale_by: float, resize_mode: int, inpaint_full_res: bool, inpaint_full_res_padding: int, inpainting_mask_invert: int, img2img_batch_input_dir: str, img2img_batch_output_dir: str, img2img_batch_inpaint_mask_dir: str, override_settings_texts, img2img_batch_use_png_info: bool, img2img_batch_png_info_props: list, img2img_batch_png_info_dir: str, img2img_batch_source_type: str, img2img_batch_upload: list, *args):
    override_settings = create_override_settings_dict(override_settings_texts)
    is_batch = mode == 5
    height, width = int(height), int(width)
    image = None
    mask = None

    if mode == 0: image = init_img
    elif mode == 1: image = Image.alpha_composite(sketch, sketch_fg)
    elif mode == 2:
        image = init_img_with_mask
        mask = init_img_with_mask_fg.getchannel('A').convert('L')
        mask = Image.merge('RGBA', (mask, mask, mask, Image.new('L', mask.size, 255)))
    elif mode == 3:
        image = Image.alpha_composite(inpaint_color_sketch, inpaint_color_sketch_fg)
        mask = inpaint_color_sketch_fg.getchannel('A').convert('L')
        short_side = min(mask.size)
        dilation_size = int(0.015 * short_side) * 2 + 1
        mask = mask.filter(ImageFilter.MaxFilter(dilation_size))
        mask = Image.merge('RGBA', (mask, mask, mask, Image.new('L', mask.size, 255)))
    elif mode == 4:
        image = init_img_inpaint
        mask = init_mask_inpaint

    if mask and isinstance(mask, Image.Image):
        mask = mask.point(lambda v: 255 if v > 128 else 0)

    image = images.fix_image(image)
    mask = images.fix_image(mask)

    if selected_scale_tab == 1 and not is_batch:
        assert image, "Can't scale by because no image is selected"
        width = int(image.width * scale_by) - (int(image.width * scale_by) % 8)
        height = int(image.height * scale_by) - (int(image.height * scale_by) % 8)

    assert 0. <= denoising_strength <= 1., 'can only work with strength in [0.0, 1.0]'

    p = StableDiffusionProcessingImg2Img(
        outpath_samples=opts.outdir_samples or opts.outdir_img2img_samples,
        outpath_grids=opts.outdir_grids or opts.outdir_img2img_grids,
        prompt=prompt, negative_prompt=negative_prompt, styles=prompt_styles,
        batch_size=batch_size, n_iter=n_iter, cfg_scale=cfg_scale, width=width, height=height,
        init_images=[image], mask=mask, mask_blur=mask_blur, inpainting_fill=inpainting_fill,
        resize_mode=resize_mode, denoising_strength=denoising_strength, image_cfg_scale=image_cfg_scale,
        inpaint_full_res=inpaint_full_res, inpaint_full_res_padding=inpaint_full_res_padding,
        inpainting_mask_invert=inpainting_mask_invert, override_settings=override_settings,
        distilled_cfg_scale=distilled_cfg_scale
    )
    p.scripts = modules.scripts.scripts_img2img
    p.script_args = args
    p.user = request.username

    if shared.opts.enable_console_prompts: print(f"\nimg2img: {prompt}", file=shared.progress_print_out)

    processed_obj = None # Ensure it's defined for finally block
    try:
        with closing(p): # p will be closed automatically
            if is_batch:
                # ... (batch processing logic remains the same) ...
                if img2img_batch_source_type == "upload":
                    assert isinstance(img2img_batch_upload, list) and img2img_batch_upload
                    processed = process_batch(p, img2img_batch_upload, "", "", args, to_scale=selected_scale_tab == 1, scale_by=scale_by, use_png_info=img2img_batch_use_png_info, png_info_props=img2img_batch_png_info_props, png_info_dir=(img2img_batch_png_info_dir if not shared.cmd_opts.hide_ui_dir_config else ""))
                else: # "from dir"
                    assert not shared.cmd_opts.hide_ui_dir_config, "Launched with --hide-ui-dir-config, batch img2img disabled"
                    processed = process_batch(p, img2img_batch_input_dir, img2img_batch_output_dir, img2img_batch_inpaint_mask_dir, args, to_scale=selected_scale_tab == 1, scale_by=scale_by, use_png_info=img2img_batch_use_png_info, png_info_props=img2img_batch_png_info_props, png_info_dir=img2img_batch_png_info_dir)
                if processed is None: processed = Processed(p, [], p.seed, "")
            else:
                processed = modules.scripts.scripts_img2img.run(p, *args)
                if processed is None:
                    processed = process_images(p)
        processed_obj = processed
    finally:
        shared.total_tqdm.clear()

    generation_info_js = processed_obj.js()
    if opts.samples_log_stdout: print(generation_info_js)
    if opts.do_not_show_images: processed_obj.images = []

    return processed_obj.images + processed_obj.extra_images, generation_info_js, plaintext_to_html(processed_obj.info), plaintext_to_html(processed_obj.comments, classname="comments"), p


def img2img(id_task: str, request: gr.Request, mode: int, prompt: str, negative_prompt: str, prompt_styles, init_img, sketch, sketch_fg, init_img_with_mask, init_img_with_mask_fg, inpaint_color_sketch, inpaint_color_sketch_fg, init_img_inpaint, init_mask_inpaint, mask_blur: int, mask_alpha: float, inpainting_fill: int, n_iter: int, batch_size: int, cfg_scale: float, distilled_cfg_scale: float, image_cfg_scale: float, denoising_strength: float, selected_scale_tab: int, height: int, width: int, scale_by: float, resize_mode: int, inpaint_full_res: bool, inpaint_full_res_padding: int, inpainting_mask_invert: int, img2img_batch_input_dir: str, img2img_batch_output_dir: str, img2img_batch_inpaint_mask_dir: str, override_settings_texts, img2img_batch_use_png_info: bool, img2img_batch_png_info_props: list, img2img_batch_png_info_dir: str, img2img_batch_source_type: str, img2img_batch_upload: list, *args):
    # This will now return a tuple from main_thread.run_and_wait_result,
    # where the actual result from img2img_function is ( (images, generation_info_js, html_info, html_log), p_object )
    return main_thread.run_and_wait_result(img2img_function, id_task, request, mode, prompt, negative_prompt, prompt_styles, init_img, sketch, sketch_fg, init_img_with_mask, init_img_with_mask_fg, inpaint_color_sketch, inpaint_color_sketch_fg, init_img_inpaint, init_mask_inpaint, mask_blur, mask_alpha, inpainting_fill, n_iter, batch_size, cfg_scale, distilled_cfg_scale, image_cfg_scale, denoising_strength, selected_scale_tab, height, width, scale_by, resize_mode, inpaint_full_res, inpaint_full_res_padding, inpainting_mask_invert, img2img_batch_input_dir, img2img_batch_output_dir, img2img_batch_inpaint_mask_dir, override_settings_texts, img2img_batch_use_png_info, img2img_batch_png_info_props, img2img_batch_png_info_dir, img2img_batch_source_type, img2img_batch_upload, *args)
