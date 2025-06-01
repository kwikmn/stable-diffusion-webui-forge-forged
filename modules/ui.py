import datetime
import mimetypes
import os
import sys
from functools import reduce
import warnings
from contextlib import ExitStack
import json # Added for gallery parameter parsing

import gradio as gr
import gradio.utils
from gradio.components.image_editor import Brush
from PIL import Image, PngImagePlugin  # noqa: F401
from modules.call_queue import wrap_gradio_gpu_call, wrap_queued_call, wrap_gradio_call, wrap_gradio_call_no_job # noqa: F401

from modules import gradio_extensions, sd_schedulers  # noqa: F401
from modules import sd_hijack, sd_models, script_callbacks, ui_extensions, deepbooru, extra_networks, ui_common, ui_postprocessing, progress, ui_loadsave, shared_items, ui_settings, timer, sysinfo, ui_checkpoint_merger, scripts, sd_samplers, processing, ui_extra_networks, ui_toprow, launch_utils
from modules.ui_components import FormRow, FormGroup, ToolButton, FormHTML, InputAccordion, ResizeHandleRow
from modules.paths import script_path
from modules.ui_common import create_refresh_button
from modules.ui_gradio_extensions import reload_javascript

from modules.shared import opts, cmd_opts

import modules.infotext_utils as parameters_copypaste
import modules.shared as shared
from modules import prompt_parser
from modules.infotext_utils import image_from_url_text, PasteField
from modules_forge.forge_canvas.canvas import ForgeCanvas, canvas_head
from modules_forge import main_entry, forge_space
import modules.processing_scripts.comments as comments
from modules import gallery_ui # Added for Prompt Gallery tab


create_setting_component = ui_settings.create_setting_component

# Placeholder for the actual StableDiffusionProcessing object from the last run
last_processed_object_state = gr.State(None)


# These lists will be populated dynamically in create_ui after UI components are defined.
all_target_ui_components_txt2img = []
all_target_ui_components_img2img = []
toprow_objects = {}


def get_update_list_for_gallery_parameters(loaded_params_json_str, active_tab_name_dummy_for_js_trigger):
    if not loaded_params_json_str:
        print("[UI] Gallery: No parameters string to apply.")
        return [gr.update() for _ in range(len(all_target_ui_components_txt2img))]
    try:
        if isinstance(loaded_params_json_str, str): loaded_params = json.loads(loaded_params_json_str)
        elif isinstance(loaded_params_json_str, dict): loaded_params = loaded_params_json_str
        else: raise TypeError("loaded_params_json_str is not a dict or string")
    except (json.JSONDecodeError, TypeError) as e:
        print(f"[UI] Gallery: Invalid format for gallery parameters: {e}")
        return [gr.update() for _ in range(len(all_target_ui_components_txt2img))]
    if not loaded_params or not isinstance(loaded_params, dict) or not loaded_params.get("_gallery_params_loaded", False):
        print("[UI] Gallery: Loaded parameters are empty, not a dictionary, or not flagged as loaded from gallery.")
        return [gr.update() for _ in range(len(all_target_ui_components_txt2img))]
    params_for_paste = gallery_ui.get_gallery_parameter_updates(loaded_params)
    if "error" in params_for_paste:
        print(f"[UI] Gallery: Error from get_gallery_parameter_updates: {params_for_paste['error']}")
        return [gr.update() for _ in range(len(all_target_ui_components_txt2img))]
    updates = []
    target_paste_fields = parameters_copypaste.txt2img_paste_fields
    target_ui_components = all_target_ui_components_txt2img
    if not target_paste_fields:
        print("[UI] Gallery: txt2img_paste_fields not populated yet. Cannot apply parameters.")
        return [gr.update() for _ in range(len(target_ui_components))]
    paste_field_map = {pf.component: pf for pf in target_paste_fields}
    for component in target_ui_components:
        paste_field = paste_field_map.get(component)
        if not paste_field:
            updates.append(gr.update())
            continue
        api_key = paste_field.api_key
        value_to_apply = params_for_paste.get(api_key)
        if value_to_apply is not None:
            current_val_update = None
            if api_key == "Styles" or (hasattr(component, 'label') and component.label == "Styles"):
                value_to_apply = [value_to_apply] if isinstance(value_to_apply, str) and value_to_apply else []
                current_val_update = gr.update(value=value_to_apply)
            elif api_key == "enable_hr":
                has_hires_params = params_for_paste.get("Hires upscale") is not None or \
                                   params_for_paste.get("Hires resize-1") is not None or \
                                   params_for_paste.get("Hires upscaler") is not None
                current_val_update = gr.update(value=has_hires_params)
            elif api_key == "Sampler":
                if "Karras" in value_to_apply and shared.opts.sampler_name_karras_suffix_only_for_display:
                     value_to_apply = value_to_apply.replace(" Karras", "")
                elif "Karras" not in value_to_apply and not shared.opts.sampler_name_karras_suffix_only_for_display and sd_samplers.is_sampler_karras(value_to_apply):
                     value_to_apply = value_to_apply + " Karras"
                current_val_update = gr.update(value=value_to_apply)
            else:
                current_val_update = gr.update(value=value_to_apply)
            updates.append(current_val_update)
        else:
            updates.append(gr.update())
    if not updates: return [gr.update() for _ in range(len(target_ui_components))]
    return updates

warnings.filterwarnings("default" if opts.show_warnings else "ignore", category=UserWarning)
warnings.filterwarnings("default" if opts.show_gradio_deprecation_warnings else "ignore", category=gradio_extensions.GradioDeprecationWarning)
mimetypes.init()
mimetypes.add_type('application/javascript', '.js'); mimetypes.add_type('application/javascript', '.mjs')
mimetypes.add_type('image/webp', '.webp'); mimetypes.add_type('image/avif', '.avif')
if not cmd_opts.share and not cmd_opts.listen:
    gradio.utils.version_check = lambda: None
    gradio.utils.get_local_ip_address = lambda: '127.0.0.1'
if cmd_opts.ngrok is not None:
    import modules.ngrok as ngrok
    print('ngrok authtoken detected, trying to connect...'); ngrok.connect(cmd_opts.ngrok, cmd_opts.port if cmd_opts.port is not None else 7860, cmd_opts.ngrok_options)
def gr_show(visible=True): return {"visible": visible, "__type__": "update"}
sample_img2img = "assets/stable-samples/img2img/sketch-mountains-input.jpg"
sample_img2img = sample_img2img if os.path.exists(sample_img2img) else None
random_symbol = '\U0001f3b2\ufe0f'; reuse_symbol = '\u267b\ufe0f'; paste_symbol = '\u2199\ufe0f'; refresh_symbol = '\U0001f504'; save_style_symbol = '\U0001f4be'; apply_style_symbol = '\U0001f4cb'; clear_prompt_symbol = '\U0001f5d1\ufe0f'; extra_networks_symbol = '\U0001F3B4'; switch_values_symbol = '\U000021C5'; restore_progress_symbol = '\U0001F300'; detect_image_size_symbol = '\U0001F4D0'
plaintext_to_html = ui_common.plaintext_to_html
def send_gradio_gallery_to_image(x):
    if len(x) == 0: return None
    return image_from_url_text(x[0])
def calc_resolution_hires(enable, width, height, hr_scale, hr_resize_x, hr_resize_y):
    if not enable: return ""
    p = processing.StableDiffusionProcessingTxt2Img(width=width,height=height,enable_hr=True,hr_scale=hr_scale,hr_resize_x=hr_resize_x,hr_resize_y=hr_resize_y)
    p.calculate_target_resolution(); new_width = p.hr_resize_x or p.hr_upscale_to_x; new_height = p.hr_resize_y or p.hr_upscale_to_y
    new_width -= new_width%8; new_height -= new_height%8
    return f"from <span class='resolution'>{p.width}x{p.height}</span> to <span class='resolution'>{new_width}x{new_height}</span>"
def resize_from_to_html(width,height,scale_by):
    target_width = int(float(width)*scale_by); target_height = int(float(height)*scale_by)
    if not target_width or not target_height: return "no image selected"
    target_width -= target_width%8; target_height -= target_height%8
    return f"resize: from <span class='resolution'>{width}x{height}</span> to <span class='resolution'>{target_width}x{target_height}</span>"
def process_interrogate(interrogation_function,mode,ii_input_dir,ii_output_dir,*ii_singles):
    mode = int(mode)
    if mode in (0,1,3,4): return [interrogation_function(ii_singles[mode]),None]
    elif mode == 2: return [interrogation_function(ii_singles[mode]),None]
    elif mode == 5:
        assert not shared.cmd_opts.hide_ui_dir_config, "Launched with --hide-ui-dir-config, batch img2img disabled"
        images_list = shared.listfiles(ii_input_dir); print(f"Will process {len(images_list)} images.")
        if ii_output_dir!="": os.makedirs(ii_output_dir,exist_ok=True)
        else: ii_output_dir = ii_input_dir
        for image_path in images_list:
            img = Image.open(image_path); filename = os.path.basename(image_path); left,_ = os.path.splitext(filename)
            print(interrogation_function(img),file=open(os.path.join(ii_output_dir,f"{left}.txt"),'a',encoding='utf-8'))
        return [gr.update(),None]
def interrogate(image): prompt = shared.interrogator.interrogate(image.convert("RGB")); return gr.update() if prompt is None else prompt
def interrogate_deepbooru(image): prompt = deepbooru.model.tag(image); return gr.update() if prompt is None else prompt
def connect_clear_prompt(button): button.click(_js="clear_prompt",fn=None,inputs=[],outputs=[])
def update_token_counter(text,steps,styles,*,is_positive=True):
    params = script_callbacks.BeforeTokenCounterParams(text,steps,styles,is_positive=is_positive); script_callbacks.before_token_counter_callback(params)
    text,steps,styles,is_positive = params.prompt,params.steps,params.styles,params.is_positive
    if shared.opts.include_styles_into_token_counters: text = (shared.prompt_styles.apply_styles_to_prompt if is_positive else shared.prompt_styles.apply_negative_styles_to_prompt)(text,styles)
    else: text = comments.strip_comments(text).strip()
    try:
        text,_ = extra_networks.parse_prompt(text)
        if is_positive: _,prompt_flat_list,_ = prompt_parser.get_multicond_prompt_list([text])
        else: prompt_flat_list = [text]
        prompt_schedules = prompt_parser.get_learned_conditioning_prompt_schedules(prompt_flat_list,steps)
    except Exception: prompt_schedules = [[[steps,text]]]
    try: get_prompt_lengths_on_ui = sd_models.model_data.sd_model.get_prompt_lengths_on_ui; assert get_prompt_lengths_on_ui is not None
    except Exception: return f"<span class='gr-box gr-text-input'>?/?</span>"
    flat_prompts = reduce(lambda list1,list2:list1+list2,prompt_schedules); prompts = [prompt_text for _,prompt_text in flat_prompts]
    token_count,max_length = max([get_prompt_lengths_on_ui(prompt) for prompt in prompts],key=lambda args:args[0])
    return f"<span class='gr-box gr-text-input'>{token_count}/{max_length}</span>"
def update_negative_prompt_token_counter(*args): return update_token_counter(*args,is_positive=False)
def setup_progressbar(*args,**kwargs): pass
def apply_setting(key,value):
    if value is None: return gr.update()
    if shared.cmd_opts.freeze_settings: return gr.update()
    if key=="sd_model_checkpoint" and opts.disable_weights_auto_swap: return gr.update()
    if key=="sd_model_checkpoint":
        ckpt_info = sd_models.get_closet_checkpoint_match(value)
        if ckpt_info is not None: value = ckpt_info.title
        else: return gr.update()
    comp_args = opts.data_labels[key].component_args
    if comp_args and isinstance(comp_args,dict) and comp_args.get('visible') is False: return
    valtype = type(opts.data_labels[key].default); oldval = opts.data.get(key,None)
    opts.data[key] = valtype(value) if valtype!=type(None) else value
    if oldval!=value and opts.data_labels[key].onchange is not None: opts.data_labels[key].onchange()
    opts.save(shared.config_filename); return getattr(opts,key)
def save_selected_to_gallery_action(selected_image_index:int,gallery_images:list,p_state_data:object):
    print(f"[PromptGallery] Attempting to save image at index: {selected_image_index}")
    if gallery_images is None or selected_image_index<0 or selected_image_index>=len(gallery_images): print("[PromptGallery] No image selected or gallery is empty/index out of bounds."); return gr.update(value="Error: No image selected or index out of bounds.")
    if p_state_data is None: print("[PromptGallery] Error: Processing data (p_state_data) is not available."); return gr.update(value="Error: Original processing data not found.")
    selected_image_info = gallery_images[selected_image_index]; image_url = selected_image_info.get('name')
    if not image_url: print("[PromptGallery] Error: Could not get image URL/path from gallery selection."); return gr.update(value="Error: Could not retrieve image path.")
    from modules.processing import StableDiffusionProcessing
    p = p_state_data if isinstance(p_state_data,StableDiffusionProcessing) else None
    if not p: print("[PromptGallery] Error: p_state_data is not a valid StableDiffusionProcessing object."); return gr.update(value="Error: Invalid processing data.")
    original_prompt = getattr(p,'original_prompt_for_gallery',p.prompt); original_negative_prompt = getattr(p,'original_negative_prompt_for_gallery',p.negative_prompt)
    print(f"[PromptGallery] Image URL: {image_url}"); print(f"[PromptGallery] Original Prompt: {original_prompt}"); print(f"[PromptGallery] Original Negative Prompt: {original_negative_prompt}"); print(f"[PromptGallery] Steps: {p.steps}, Seed: {p.seed}, CFG: {p.cfg_scale}")
    feedback_message = f"Image '{os.path.basename(image_url) if image_url else 'selected'}' prepared for gallery (details in console)."; shared.state.textinfo = feedback_message; return gr.update(value=feedback_message)
def create_output_panel(tabname,outdir,toprow=None):
    from modules.ui_common import OutputPanel
    with gr.Column(variant='compact',elem_id=f"{tabname}_results_column"):
        with gr.Row(elem_id=f"{tabname}_gallery_container",variant="compact",elem_classes="output-gallery-container"):
            result_gallery = gr.Gallery(label='Output', show_label=False, elem_id=f"{tabname}_gallery", columns=4,height="auto",preview=True,container=False,object_fit='cover',allow_preview=True) # Applied hardcoded values
        with gr.Row(elem_id=f"{tabname}_tools_row",variant="compact",elem_classes="gradio-compact"):
            zip_button = ToolButton(value="Zip",elem_id=f'{tabname}_save_zip'); save_button = ToolButton(value="Save",elem_id=f'{tabname}_save')
            save_gallery_button = ToolButton(value='⭐',elem_id=f'{tabname}_save_gallery',tooltip='Save selected image to gallery (saves original prompt and parameters).',visible=True)
            ui_common.create_output_panel_quick_buttons(tabname,result_gallery)
        generation_info = gr.Textbox(visible=False,elem_id=f'{tabname}_generation_info'); html_log = gr.HTML(elem_id=f'{tabname}_html_log',elem_classes="html-log"); infotext = gr.Textbox(visible=False,elem_id=f'{tabname}_infotext')
        gallery_save_feedback = gr.Textbox(label="Gallery Action Status",visible=True,interactive=False,elem_id=f"{tabname}_gallery_save_feedback",lines=1,max_lines=1)
        save_gallery_button.click(fn=save_selected_to_gallery_action,inputs=[result_gallery.selected_index,result_gallery,last_processed_object_state],outputs=[gallery_save_feedback])
        dummy_component_for_save = gr.Textbox(visible=False,elem_id=f"{tabname}_dummy_component_for_save")
        save_button.click(fn=wrap_gradio_call(ui_common.save_files,extra_outputs=[generation_info,html_log]),_js="gallery_save_files",inputs=[dummy_component_for_save,result_gallery,generation_info,html_log,],outputs=[html_log,],show_progress=False)
        zip_button.click(fn=wrap_gradio_call(ui_common.save_files_zip,extra_outputs=[generation_info,html_log]),_js="gallery_save_files_zip",inputs=[dummy_component_for_save,result_gallery,generation_info,html_log,],outputs=[html_log,],show_progress=False)
        return OutputPanel(gallery=result_gallery,generation_info=generation_info,infotext=infotext,html_log=html_log,save_button=save_button,zip_button=zip_button,button_upscale=ToolButton(value="Upscale",visible=False),button_live_preview=ToolButton(value="Live Preview",visible=False),button_skip=ToolButton(value='Skip',elem_id=f"{tabname}_skip",visible=False),button_interrupt=ToolButton(value='Interrupt',elem_id=f"{tabname}_interrupt",visible=False),button_stop_generating=ToolButton(value='Stop',elem_id=f"{tabname}_stop_generating",visible=False))
def ordered_ui_categories():
    user_order = {x.strip():i*2+1 for i,x in enumerate(shared.opts.ui_reorder_list)}
    for _,category in sorted(enumerate(shared_items.ui_reorder_categories()),key=lambda x:user_order.get(x[1],x[0]*2+0)): yield category
def create_override_settings_dropdown(tabname,row):
    dropdown = gr.Dropdown([],label="Override settings",visible=False,elem_id=f"{tabname}_override_settings",multiselect=True)
    dropdown.change(fn=lambda x:gr.Dropdown.update(visible=bool(x)),inputs=[dropdown],outputs=[dropdown]); return dropdown

# Wrapper functions to ensure 'p' object is passed correctly to UI state
def txt2img_driver(*args, **kwargs):
    processed, p = modules.txt2img.txt2img(*args, **kwargs)
    return processed.images + processed.extra_images, processed.js(), plaintext_to_html(processed.info), plaintext_to_html(processed.comments, classname="comments"), p

def img2img_driver(*args, **kwargs):
    processed, p = modules.img2img.img2img(*args, **kwargs)
    return processed.images + processed.extra_images, processed.js(), plaintext_to_html(processed.info), plaintext_to_html(processed.comments, classname="comments"), p

def txt2img_upscale_driver(*args, **kwargs):
    images, gen_info, html_info, html_log = modules.txt2img.txt2img_upscale(*args, **kwargs)
    return images, gen_info, html_info, html_log, None


def create_ui():
    import modules.img2img
    import modules.txt2img
    global all_target_ui_components_txt2img, all_target_ui_components_img2img, toprow_objects

    reload_javascript(); parameters_copypaste.reset(); settings = ui_settings.UiSettings(); settings.register_settings()
    scripts.scripts_current = scripts.scripts_txt2img; scripts.scripts_txt2img.initialize_scripts(is_img2img=False)

    with gr.Blocks(analytics_enabled=False,head=canvas_head) as txt2img_interface:
        toprow = ui_toprow.Toprow(is_img2img=False,is_compact=shared.opts.compact_prompt_box); toprow_objects["txt2img"] = toprow
        dummy_component = gr.Textbox(visible=False); dummy_component_number = gr.Number(visible=False)
        extra_tabs = gr.Tabs(elem_id="txt2img_extra_tabs",elem_classes=["extra-networks"])
        with extra_tabs:
            with gr.Tab("Generation",id="txt2img_generation") as txt2img_generation_tab, ResizeHandleRow(equal_height=False):
                with ExitStack() as stack:
                    if shared.opts.txt2img_settings_accordion: stack.enter_context(gr.Accordion("Open for Settings",open=False))
                    with stack.enter_context(gr.Column(variant='compact',elem_id="txt2img_settings")):
                        scripts.scripts_txt2img.prepare_ui()
                        for category in ordered_ui_categories():
                            if category=="prompt": toprow.create_inline_toprow_prompts()
                            elif category=="dimensions":
                                with FormRow():
                                    with gr.Column(elem_id="txt2img_column_size",scale=4): width = gr.Slider(minimum=64,maximum=2048,step=8,label="Width",value=512,elem_id="txt2img_width"); height = gr.Slider(minimum=64,maximum=2048,step=8,label="Height",value=512,elem_id="txt2img_height")
                                    with gr.Column(elem_id="txt2img_dimensions_row",scale=1,elem_classes="dimensions-tools"): res_switch_btn = ToolButton(value=switch_values_symbol,elem_id="txt2img_res_switch_btn",tooltip="Switch width/height")
                                    if opts.dimensions_and_batch_together:
                                        with gr.Column(elem_id="txt2img_column_batch"): batch_count = gr.Slider(minimum=1,step=1,label='Batch count',value=1,elem_id="txt2img_batch_count"); batch_size = gr.Slider(minimum=1,maximum=8,step=1,label='Batch size',value=1,elem_id="txt2img_batch_size")
                            elif category=="cfg":
                                with gr.Row(): distilled_cfg_scale = gr.Slider(minimum=0.0,maximum=30.0,step=0.1,label='Distilled CFG Scale',value=3.5,elem_id="txt2img_distilled_cfg_scale"); cfg_scale = gr.Slider(minimum=1.0,maximum=30.0,step=0.1,label='CFG Scale',value=7.0,elem_id="txt2img_cfg_scale")
                            elif category == "accordions":
                                with gr.Row(elem_id="txt2img_accordions", elem_classes="accordions"):
                                    with InputAccordion(False, label="Hires. fix", elem_id="txt2img_hr") as enable_hr:
                                        hr_upscaler = gr.Dropdown(label="Upscaler",elem_id="txt2img_hr_upscaler",choices=[*shared.latent_upscale_modes,*[x.name for x in shared.sd_upscalers]],value=shared.latent_upscale_default_mode); hr_second_pass_steps = gr.Slider(minimum=0,maximum=150,step=1,label='Hires steps',value=0,elem_id="txt2img_hires_steps"); denoising_strength = gr.Slider(minimum=0.0,maximum=1.0,step=0.01,label='Denoising strength',value=0.7,elem_id="txt2img_denoising_strength"); hr_scale = gr.Slider(minimum=1.0,maximum=4.0,step=0.05,label="Upscale by",value=2.0,elem_id="txt2img_hr_scale"); hr_resize_x = gr.Slider(minimum=0,maximum=2048,step=8,label="Resize width to",value=0,elem_id="txt2img_hr_resize_x"); hr_resize_y = gr.Slider(minimum=0,maximum=2048,step=8,label="Resize height to",value=0,elem_id="txt2img_hr_resize_y"); hr_checkpoint_name = gr.Dropdown(label='Hires Checkpoint',elem_id="hr_checkpoint",choices=["Use same checkpoint"]+modules.sd_models.checkpoint_tiles(use_short=True),value="Use same checkpoint"); hr_sampler_name = gr.Dropdown(label='Hires sampling method',elem_id="hr_sampler",choices=["Use same sampler"]+sd_samplers.visible_sampler_names(),value="Use same sampler"); hr_scheduler = gr.Dropdown(label='Hires schedule type',elem_id="hr_scheduler",choices=["Use same scheduler"]+[x.label for x in sd_schedulers.schedulers],value="Use same scheduler"); hr_prompt = gr.Textbox(label="Hires prompt",elem_id="hires_prompt"); hr_negative_prompt = gr.Textbox(label="Hires negative prompt",elem_id="hires_neg_prompt"); hr_cfg = gr.Slider(label="Hires CFG Scale",elem_id="txt2img_hr_cfg"); hr_distilled_cfg = gr.Slider(label="Hires Distilled CFG Scale", elem_id="txt2img_hr_distilled_cfg")
                            elif category=="scripts":
                                with FormGroup(elem_id="txt2img_script_container"): custom_inputs = scripts.scripts_txt2img.setup_ui()
                output_panel_txt2img = create_output_panel("txt2img",opts.outdir_txt2img_samples,toprow)
                all_target_ui_components_txt2img.extend([field.component for field in parameters_copypaste.txt2img_paste_fields if hasattr(field,'component')])
                if 'enable_hr' in locals() and enable_hr not in all_target_ui_components_txt2img: all_target_ui_components_txt2img.append(enable_hr) # Ensure enable_hr is captured
        txt2img_inputs = [dummy_component,toprow.prompt,toprow.negative_prompt,toprow.ui_styles.dropdown,batch_count,batch_size,cfg_scale,distilled_cfg_scale,height,width,enable_hr,denoising_strength,hr_scale,hr_upscaler,hr_second_pass_steps,hr_resize_x,hr_resize_y,hr_checkpoint_name,gr.HTML(),hr_sampler_name,hr_scheduler,hr_prompt,hr_negative_prompt,hr_cfg,hr_distilled_cfg,gr.HTML()]+custom_inputs
        txt2img_outputs_with_state = [output_panel_txt2img.gallery,output_panel_txt2img.generation_info,output_panel_txt2img.infotext,output_panel_txt2img.html_log,last_processed_object_state]
        txt2img_args = dict(fn=wrap_gradio_gpu_call(txt2img_driver),_js="submit",inputs=txt2img_inputs,outputs=txt2img_outputs_with_state,show_progress=False)
        toprow.prompt.submit(**txt2img_args); toprow.submit.click(**txt2img_args)
        txt2img_upscale_outputs_with_state = [output_panel_txt2img.gallery,output_panel_txt2img.generation_info,output_panel_txt2img.infotext,output_panel_txt2img.html_log,last_processed_object_state] # Ensure last_processed_object_state is here too
        output_panel_txt2img.button_upscale.click(fn=wrap_gradio_gpu_call(txt2img_upscale_driver), _js="submit_txt2img_upscale", inputs=([dummy_component, output_panel_txt2img.gallery, dummy_component_number, output_panel_txt2img.generation_info] + txt2img_inputs[1:]), outputs=txt2img_upscale_outputs_with_state, show_progress=False)

    scripts.scripts_current = scripts.scripts_img2img; scripts.scripts_img2img.initialize_scripts(is_img2img=True)
    with gr.Blocks(analytics_enabled=False,head=canvas_head) as img2img_interface:
        toprow_img2img = ui_toprow.Toprow(is_img2img=True,is_compact=shared.opts.compact_prompt_box); toprow_objects["img2img"] = toprow_img2img
        extra_tabs_img2img = gr.Tabs(elem_id="img2img_extra_tabs",elem_classes=["extra-networks"])
        with extra_tabs_img2img:
            with gr.Tab("Generation",id="img2img_generation") as img2img_generation_tab, ResizeHandleRow(equal_height=False):
                img2img_selected_tab = gr.Number(value=0, visible=False); init_img = ForgeCanvas(); sketch = ForgeCanvas(); init_img_with_mask = ForgeCanvas(); inpaint_color_sketch = ForgeCanvas()
                init_img_inpaint = gr.Image(); init_mask_inpaint = gr.Image(); mask_blur = gr.Slider(); mask_alpha = gr.Slider(); inpainting_fill = gr.Radio()
                img2img_denoising_strength = gr.Slider(minimum=0.0,maximum=1.0,step=0.01,label='Denoising strength',value=0.75)
                img2img_width = gr.Slider(label="Width"); img2img_height = gr.Slider(label="Height"); img2img_scale_by = gr.Slider(label="Scale by")
                img2img_resize_mode = gr.Radio(); img2img_inpaint_full_res = gr.Radio(); img2img_inpaint_full_res_padding = gr.Slider(); img2img_inpainting_mask_invert = gr.Radio()
                img2img_batch_input_dir = gr.Textbox(); img2img_batch_output_dir = gr.Textbox(); img2img_batch_inpaint_mask_dir = gr.Textbox()
                img2img_override_settings_texts = gr.HTML()
                img2img_batch_use_png_info = gr.Checkbox(); img2img_batch_png_info_props = gr.CheckboxGroup(); img2img_batch_png_info_dir = gr.Textbox()
                img2img_batch_source_type = gr.Textbox(); img2img_batch_upload = gr.Files()
                batch_count_img2img = gr.Slider(minimum=1, step=1, label='Batch count', value=1); batch_size_img2img = gr.Slider(minimum=1, maximum=8, step=1, label='Batch size', value=1)
                cfg_scale_img2img = gr.Slider(minimum=1.0, maximum=30.0, step=0.1, label='CFG Scale', value=7.0); distilled_cfg_scale_img2img = gr.Slider(minimum=0.0, maximum=30.0, step=0.1, label='Distilled CFG Scale', value=3.5)
                image_cfg_scale_img2img = gr.Slider(minimum=0, maximum=3.0, step=0.05, label='Image CFG Scale', value=1.5)
                img2img_custom_inputs = scripts.scripts_img2img.setup_ui()
                output_panel_img2img = create_output_panel("img2img",opts.outdir_img2img_samples,toprow_img2img)
                all_target_ui_components_img2img.extend([field.component for field in parameters_copypaste.img2img_paste_fields if hasattr(field,'component')])
        img2img_inputs = [dummy_component,img2img_selected_tab,toprow_img2img.prompt,toprow_img2img.negative_prompt,toprow_img2img.ui_styles.dropdown,init_img.background,sketch.background,sketch.foreground,init_img_with_mask.background,init_img_with_mask.foreground,inpaint_color_sketch.background,inpaint_color_sketch.foreground,init_img_inpaint,init_mask_inpaint,mask_blur,mask_alpha,inpainting_fill,batch_count_img2img,batch_size_img2img,cfg_scale_img2img,distilled_cfg_scale_img2img,image_cfg_scale_img2img,img2img_denoising_strength,gr.Number(value=0, visible=False),img2img_height,img2img_width,img2img_scale_by,img2img_resize_mode,img2img_inpaint_full_res,img2img_inpaint_full_res_padding,img2img_inpainting_mask_invert,img2img_batch_input_dir,img2img_batch_output_dir,img2img_batch_inpaint_mask_dir,img2img_override_settings_texts,img2img_batch_use_png_info,img2img_batch_png_info_props,img2img_batch_png_info_dir,img2img_batch_source_type,img2img_batch_upload]+img2img_custom_inputs
        img2img_outputs_with_state = [output_panel_img2img.gallery,output_panel_img2img.generation_info,output_panel_img2img.infotext,output_panel_img2img.html_log,last_processed_object_state]
        img2img_args = dict(fn=wrap_gradio_gpu_call(img2img_driver),_js="submit_img2img",inputs=img2img_inputs,outputs=img2img_outputs_with_state,show_progress=False)
        toprow_img2img.prompt.submit(**img2img_args); toprow_img2img.submit.click(**img2img_args)

    with gr.Blocks(analytics_enabled=False,head=canvas_head) as space_interface: forge_space.main_entry()
    scripts.scripts_current = None
    with gr.Blocks(analytics_enabled=False) as extras_interface: ui_postprocessing.create_ui()
    with gr.Blocks(analytics_enabled=False) as pnginfo_interface: gr.HTML("PNG Info Content Placeholder")
    modelmerger_ui = ui_checkpoint_merger.UiCheckpointMerger(); loadsave = ui_loadsave.UiLoadsave(cmd_opts.ui_config_file); settings.create_ui(loadsave,dummy_component if 'dummy_component' in locals() else gr.Textbox(visible=False))
    interfaces = [(txt2img_interface,"Txt2img","txt2img"),(img2img_interface,"Img2img","img2img"),(space_interface,"Spaces","space"),(extras_interface,"Extras","extras"),(pnginfo_interface,"PNG Info","pnginfo"),(modelmerger_ui.blocks,"Checkpoint Merger","modelmerger")]
    interfaces += script_callbacks.ui_tabs_callback()
    gallery_interface_instance = gallery_ui.create_gallery_ui(); interfaces += [(gallery_interface_instance,"Prompt Gallery","prompt_gallery")]
    interfaces += [(settings.interface,"Settings","settings")]; extensions_interface = ui_extensions.create_ui(); interfaces += [(extensions_interface,"Extensions","extensions")]
    shared.tab_names = [label for _,label,_ in interfaces]
    custom_css = "<link rel=\"stylesheet\" type=\"text/css\" href=\"/file=style_gallery.css\">"; final_head = canvas_head + custom_css if canvas_head else custom_css
    with gr.Blocks(theme=shared.gradio_theme,analytics_enabled=False,title="Stable Diffusion",head=final_head) as demo:
        quicksettings_row = settings.add_quicksettings(); parameters_copypaste.connect_paste_params_buttons()
        with gr.Tabs(elem_id="tabs") as tabs:
            tab_order = {k:i for i,k in enumerate(opts.ui_tab_order)}; sorted_interfaces = sorted(interfaces,key=lambda x:tab_order.get(x[1],9999))
            for interface,label,ifid in sorted_interfaces:
                if label in shared.opts.hidden_tabs: continue
                with gr.TabItem(label,id=ifid,elem_id=f"tab_{ifid}"): interface.render()
                if ifid not in ["extensions","settings"]: loadsave.add_block(interface,ifid)
            loadsave.add_component(f"webui/Tabs@{tabs.elem_id}",tabs); loadsave.setup_ui()
        if gallery_interface_instance and hasattr(gallery_interface_instance,'apply_gallery_params_to_ui_button'):
            dummy_js_trigger_for_gallery_apply = gr.Textbox(visible=False,elem_id="prompt_gallery_js_dummy_trigger")
            gallery_interface_instance.apply_gallery_params_to_ui_button.click(fn=get_update_list_for_gallery_parameters,inputs=[gallery_ui.current_gallery_selected_params,dummy_js_trigger_for_gallery_apply],outputs=all_target_ui_components_txt2img)
        if os.path.exists(os.path.join(script_path,"notification.mp3")) and shared.opts.notification_audio: gr.Audio(interactive=False,value=os.path.join(script_path,"notification.mp3"),elem_id="audio_notification",visible=False)
        footer = shared.html("footer.html"); footer = footer.format(versions=versions_html(),api_docs="/docs" if shared.cmd_opts.api else "https://github.com/AUTOMATIC1111/stable-diffusion-webui/wiki/API"); gr.HTML(footer,elem_id="footer")
        settings.add_functionality(demo)
        modelmerger_ui.setup_ui(dummy_component=dummy_component if 'dummy_component' in locals() else gr.Textbox(visible=False),sd_model_checkpoint_component=main_entry.ui_checkpoint); main_entry.forge_main_entry()
    if 'ui_settings_from_file' in locals() and ui_settings_from_file != loadsave.ui_settings: loadsave.dump_defaults()
    demo.ui_loadsave = loadsave; return demo
def versions_html():
    import torch,launch; python_version = ".".join([str(x) for x in sys.version_info[0:3]]); commit = launch.commit_hash(); tag = launch.git_tag()
    if shared.xformers_available: import xformers; xformers_version = xformers.__version__
    else: xformers_version = "N/A"
    return f"""version: <a href="https://github.com/lllyasviel/stable-diffusion-webui-forge/commit/{commit}">{tag}</a>
&#x2000;•&#x2000; python: <span title="{sys.version}">{python_version}</span>
&#x2000;•&#x2000; torch: {getattr(torch,'__long_version__',torch.__version__)}
&#x2000;•&#x2000; xformers: {xformers_version}
&#x2000;•&#x2000; gradio: {gr.__version__}
&#x2000;•&#x2000; checkpoint: <a id="sd_checkpoint_hash">N/A</a>"""
def setup_ui_api(app):
    from pydantic import BaseModel,Field
    class QuicksettingsHint(BaseModel): name:str=Field(title="Name of the quicksettings field"); label:str=Field(title="Label of the quicksettings field")
    def quicksettings_hint(): return [QuicksettingsHint(name=k,label=v.label) for k,v in opts.data_labels.items()]
    app.add_api_route("/internal/quicksettings-hint",quicksettings_hint,methods=["GET"],response_model=list[QuicksettingsHint])
    app.add_api_route("/internal/ping",lambda:{},methods=["GET"]); app.add_api_route("/internal/profile-startup",lambda:timer.startup_record,methods=["GET"])
    def download_sysinfo(attachment=False):
        from fastapi.responses import PlainTextResponse
        text = sysinfo.get(); filename = f"sysinfo-{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d-%H-%M')}.json"
        return PlainTextResponse(text,headers={'Content-Disposition':f'{"attachment" if attachment else "inline"}; filename="{filename}"'})
    app.add_api_route("/internal/sysinfo",download_sysinfo,methods=["GET"]); app.add_api_route("/internal/sysinfo-download",lambda:download_sysinfo(attachment=True),methods=["GET"])
    import fastapi.staticfiles; app.mount("/webui-assets",fastapi.staticfiles.StaticFiles(directory=launch_utils.repo_dir('stable-diffusion-webui-assets')),name="webui-assets")
