import json
from contextlib import closing

import modules.scripts
from modules import processing, infotext_utils
from modules.infotext_utils import create_override_settings_dict, parse_generation_parameters
from modules.shared import opts
import modules.shared as shared
from modules.ui import plaintext_to_html
from PIL import Image
import gradio as gr
from modules_forge import main_thread


def txt2img_create_processing(id_task: str, request: gr.Request, prompt: str, negative_prompt: str, prompt_styles, n_iter: int, batch_size: int, cfg_scale: float, distilled_cfg_scale: float, height: int, width: int, enable_hr: bool, denoising_strength: float, hr_scale: float, hr_upscaler: str, hr_second_pass_steps: int, hr_resize_x: int, hr_resize_y: int, hr_checkpoint_name: str, hr_additional_modules: list, hr_sampler_name: str, hr_scheduler: str, hr_prompt: str, hr_negative_prompt, hr_cfg: float, hr_distilled_cfg: float, override_settings_texts, *args, force_enable_hr=False):
    override_settings = create_override_settings_dict(override_settings_texts)

    if force_enable_hr:
        enable_hr = True

    p = processing.StableDiffusionProcessingTxt2Img(
        outpath_samples=opts.outdir_samples or opts.outdir_txt2img_samples,
        outpath_grids=opts.outdir_grids or opts.outdir_txt2img_grids,
        prompt=prompt,
        styles=prompt_styles,
        negative_prompt=negative_prompt,
        batch_size=batch_size,
        n_iter=n_iter,
        cfg_scale=cfg_scale,
        distilled_cfg_scale=distilled_cfg_scale,
        width=width,
        height=height,
        enable_hr=enable_hr,
        denoising_strength=denoising_strength,
        hr_scale=hr_scale,
        hr_upscaler=hr_upscaler,
        hr_second_pass_steps=hr_second_pass_steps,
        hr_resize_x=hr_resize_x,
        hr_resize_y=hr_resize_y,
        hr_checkpoint_name=None if hr_checkpoint_name == 'Use same checkpoint' else hr_checkpoint_name,
        hr_additional_modules=hr_additional_modules,
        hr_sampler_name=None if hr_sampler_name == 'Use same sampler' else hr_sampler_name,
        hr_scheduler=None if hr_scheduler == 'Use same scheduler' else hr_scheduler,
        hr_prompt=hr_prompt,
        hr_negative_prompt=hr_negative_prompt,
        hr_cfg=hr_cfg,
        hr_distilled_cfg=hr_distilled_cfg,
        override_settings=override_settings,
    )

    p.scripts = modules.scripts.scripts_txt2img
    p.script_args = args

    p.user = request.username

    if shared.opts.enable_console_prompts:
        print(f"\ntxt2img: {prompt}", file=shared.progress_print_out)

    return p


def txt2img_upscale_function(id_task: str, request: gr.Request, gallery, gallery_index, generation_info, *args):
    assert len(gallery) > 0, 'No image to upscale'

    if gallery_index < 0 or gallery_index >= len(gallery):
        return gallery, generation_info, f'Bad image index: {gallery_index}', ''

    geninfo = json.loads(generation_info)

    first_image_index = geninfo.get('index_of_first_image', 0)
    count_images = len(geninfo.get('infotexts'))
    if len(gallery) > 1 and (gallery_index < first_image_index or gallery_index >= count_images):
        return gallery, generation_info, 'Unable to upscale grid or control images.', ''

    p = txt2img_create_processing(id_task, request, *args, force_enable_hr=True)
    p.batch_size = 1
    p.n_iter = 1
    p.txt2img_upscale = True

    image_info = gallery[gallery_index]
    p.firstpass_image = infotext_utils.image_from_url_text(image_info)

    parameters = parse_generation_parameters(geninfo.get('infotexts')[gallery_index], [])
    p.seed = parameters.get('Seed', -1)
    p.subseed = parameters.get('Variation seed', -1)

    p.width = gallery[gallery_index][0].size[0]
    p.height = gallery[gallery_index][0].size[1]
    p.extra_generation_params['Original Size'] = f'{args[8]}x{args[7]}'

    p.override_settings['save_images_before_highres_fix'] = False

    processed_obj = None # Define to ensure it's available in finally
    try:
        with closing(p):
            processed = modules.scripts.scripts_txt2img.run(p, *p.script_args)

            if processed is None:
                processed = processing.process_images(p)
        processed_obj = processed
    finally:
        # p is closed by with closing(p)
        shared.total_tqdm.clear()

    insert = getattr(shared.opts, 'hires_button_gallery_insert', False)
    new_gallery = []
    for i, image in enumerate(gallery):
        if insert or i != gallery_index:
            if hasattr(image[0], 'already_saved_as'): # Check if attribute exists
                 image[0].already_saved_as = image[0].filename.rsplit('?', 1)[0]
            new_gallery.append(image)
        if i == gallery_index:
            new_gallery.extend(processed_obj.images)

    new_index = gallery_index
    if insert:
        new_index += 1
        geninfo["infotexts"].insert(new_index, processed_obj.info)
    else:
        geninfo["infotexts"][gallery_index] = processed_obj.info

    # For upscale, p is not typically returned to UI state, but if needed, it would be:
    # return new_gallery, json.dumps(geninfo), plaintext_to_html(processed_obj.info), plaintext_to_html(processed_obj.comments, classname="comments"), p
    return new_gallery, json.dumps(geninfo), plaintext_to_html(processed_obj.info), plaintext_to_html(processed_obj.comments, classname="comments")


def txt2img_function(id_task: str, request: gr.Request, *args):
    p = txt2img_create_processing(id_task, request, *args)
    processed_obj = None # Define to ensure it's available in finally

    try:
        with closing(p):
            processed = modules.scripts.scripts_txt2img.run(p, *p.script_args)

            if processed is None:
                processed = processing.process_images(p)
        processed_obj = processed # Assign here to ensure it's the result from process_images
    finally:
        # p is closed by with closing(p)
        shared.total_tqdm.clear()

    generation_info_js = processed_obj.js()
    if opts.samples_log_stdout:
        print(generation_info_js)

    if opts.do_not_show_images:
        processed_obj.images = []

    # Return processed_obj for standard outputs, and p for state
    return processed_obj.images + processed_obj.extra_images, generation_info_js, plaintext_to_html(processed_obj.info), plaintext_to_html(processed_obj.comments, classname="comments"), p


def txt2img_upscale(id_task: str, request: gr.Request, gallery, gallery_index, generation_info, *args):
    # Note: txt2img_upscale_function currently doesn't return p. If it needs to update last_processed_object_state,
    # its return signature and this call would need modification. For now, assuming only main txt2img/img2img updates the state.
    return main_thread.run_and_wait_result(txt2img_upscale_function, id_task, request, gallery, gallery_index, generation_info, *args)


def txt2img(id_task: str, request: gr.Request, *args):
    # This will now return a tuple: ( (images, generation_info_js, html_info, html_log), p_object )
    # The outer tuple is from run_and_wait_result, the inner is from txt2img_function's new return.
    raw_output = main_thread.run_and_wait_result(txt2img_function, id_task, request, *args)
    # We need to flatten this for Gradio if wrap_gradio_gpu_call expects flat outputs.
    # (images, generation_info_js, html_info, html_log), p_object = raw_output
    # return images, generation_info_js, html_info, html_log, p_object
    return raw_output # Let wrap_gradio_gpu_call handle the Processed object and p.
