# modules/gallery_ui.py
import gradio as gr
from modules import gallery_saver, ui_common, shared, ui # Import ui for parameters_copypaste later if needed
import os

# Store the last loaded parameters from gallery to repopulate UI
# This might be better placed in a shared context or ui.py if accessed by many places
current_gallery_selected_params = gr.State(None)

def create_gallery_ui():
    with gr.Blocks() as gallery_interface:
        gr.HTML("<p style='text-align:center;'>Browse saved prompts and their generated images. Click an image to load its parameters.</p>")

        with gr.Row():
            refresh_button = gr.Button("Refresh Gallery", variant="primary")
            # Hidden textbox to store the JSON path of the item to load (used by JS)
            item_to_load_json_path = gr.Textbox(label="JSON path to load", visible=False, elem_id="prompt_gallery_item_to_load_json_path")
            # Hidden button to trigger parameter loading from Python (used by JS)
            load_params_button = gr.Button("Load Params Internal", visible=False, elem_id="prompt_gallery_load_params_button")
            # Hidden button to trigger applying loaded parameters to the main UI (txt2img/img2img)
            apply_gallery_params_to_ui_button = gr.Button("Apply Params to UI Internal", visible=False, elem_id="prompt_gallery_apply_params_to_ui_button")

        gallery_items_area = gr.Blocks(elem_id="prompt_gallery_items_area") # Using gr.Blocks as a container

        def get_gallery_html():
            items = gallery_saver.get_gallery_items()
            if not items:
                return "<p style='text-align:center;'>Gallery is empty.</p>"

            html_content = "<div class='gallery-grid'>"
            for item in items:
                # Ensure paths are correctly formatted for web display if they contain backslashes
                web_preview_path = item.get('preview_image_path', '').replace('\\', '/')

                # Use item['name'] (unique filename without extension) as a key for card click
                # Ensure json_path is properly escaped for JavaScript string literal
                escaped_json_path = item.get('json_path', '').replace('\\', '\\\\').replace("'", "\\'")
                card_onclick_js = f"selectGalleryItem('{escaped_json_path}')"

                # Simplified card HTML, can be enhanced later with extra-networks-card.html structure
                html_content += f"""
                <div class='gallery-card' onclick="{card_onclick_js}">
                    <img src='{web_preview_path}' alt='{item.get('prompt_preview', 'Gallery image')}' loading='lazy'/>
                    <div class='gallery-caption'>{item.get('prompt_preview', '')}</div>
                </div>
                """
            html_content += "</div>"
            return html_content

        with gallery_items_area:
            gallery_display = gr.HTML(value=get_gallery_html())

        refresh_button.click(
            fn=get_gallery_html,
            inputs=[],
            outputs=[gallery_display]
        )

        # Define the Python callback for loading parameters
        # This function will be triggered by the hidden load_params_button
        def load_parameters_from_gallery(json_path_str):
            if not json_path_str:
                print("[GalleryUI] JSON path is empty.")
                # Return a dictionary that JS can check for an error
                return {"error": "JSON path is empty.", "_gallery_params_loaded": False}

            print(f"[GalleryUI] Loading parameters from: {json_path_str}")
            params = gallery_saver.load_gallery_item_data(json_path_str)
            if not params:
                print(f"[GalleryUI] Failed to load parameters from {json_path_str}")
                return {"error": f"Failed to load parameters from {json_path_str}", "_gallery_params_loaded": False}

            # Store for other potential uses, or directly prepare updates
            # current_gallery_selected_params.value = params # This does not work directly for gr.State from a callback like this.
                                                            # The value needs to be returned to a gr.State output.

            print(f"[GalleryUI] Parameters loaded: {params}")
            params["_gallery_params_loaded"] = True # Add a flag for JS to check
            return params # This will be sent back to the JS that called this gr.Button.click via current_gallery_selected_params

        # This is the Python function that JS will call to get all the gr.Update objects
        # This function is NOT directly called by a Gradio component event in this file.
        # It's intended to be called by an API endpoint or a JS-triggered Python call.
        # For now, it's defined here but will be wired up in ui.py or via an API.
        def get_gallery_parameter_updates(loaded_params_dict):
            if not loaded_params_dict or not loaded_params_dict.get("_gallery_params_loaded"):
                return { "error": "No parameters loaded or invalid data" }

            infotext_like_params = {}
            infotext_like_params["Prompt"] = loaded_params_dict.get('original_prompt')
            infotext_like_params["Negative prompt"] = loaded_params_dict.get('original_negative_prompt')
            infotext_like_params["Steps"] = loaded_params_dict.get('steps')
            infotext_like_params["Sampler"] = loaded_params_dict.get('sampler_name')
            infotext_like_params["Schedule type"] = loaded_params_dict.get('scheduler')
            infotext_like_params["CFG scale"] = loaded_params_dict.get('cfg_scale')
            infotext_like_params["Seed"] = loaded_params_dict.get('seed')
            infotext_like_params["Size-1"] = loaded_params_dict.get('width')
            infotext_like_params["Size-2"] = loaded_params_dict.get('height')
            infotext_like_params["Model hash"] = loaded_params_dict.get('model_hash')
            infotext_like_params["Model"] = loaded_params_dict.get('model_name')
            infotext_like_params["VAE"] = loaded_params_dict.get('sd_vae_name')
            infotext_like_params["Denoising strength"] = loaded_params_dict.get('denoising_strength')
            infotext_like_params["Variation seed"] = loaded_params_dict.get('subseed')
            infotext_like_params["Variation seed strength"] = loaded_params_dict.get('subseed_strength')
            infotext_like_params["Seed resize from-1"] = loaded_params_dict.get('seed_resize_from_w')
            infotext_like_params["Seed resize from-2"] = loaded_params_dict.get('seed_resize_from_h')
            infotext_like_params["Clip skip"] = loaded_params_dict.get('clip_skip')
            infotext_like_params["Face restoration"] = loaded_params_dict.get('face_restoration')
            infotext_like_params["Tiling"] = loaded_params_dict.get('tiling')
            infotext_like_params["Image CFG scale"] = loaded_params_dict.get('image_cfg_scale')
            infotext_like_params["Mask blur"] = loaded_params_dict.get('mask_blur')
            # Mapping based on create_infotext, where inpainting_fill is stored as "Masked content"
            masked_content_val = loaded_params_dict.get('inpainting_fill')
            if masked_content_val == 0: infotext_like_params["Masked content"] = 'fill'
            elif masked_content_val == 1: infotext_like_params["Masked content"] = 'original'
            elif masked_content_val == 2: infotext_like_params["Masked content"] = 'latent noise'
            elif masked_content_val == 3: infotext_like_params["Masked content"] = 'latent nothing'

            inpaint_area_val = loaded_params_dict.get('inpaint_full_res') # This is 0 for "Whole picture", 1 for "Only masked"
            infotext_like_params["Inpaint area"] = "Whole picture" if inpaint_area_val == 0 else "Only masked"

            infotext_like_params["Masked area padding"] = loaded_params_dict.get('inpaint_full_res_padding')
            # Mapping for inpainting_mask_invert (0: Inpaint masked, 1: Inpaint not masked)
            infotext_like_params["Mask mode"] = "Inpaint masked" if loaded_params_dict.get('inpainting_mask_invert') == 0 else "Inpaint not masked"


            if loaded_params_dict.get('enable_hr', False):
                infotext_like_params["Hires upscale"] = loaded_params_dict.get('hr_scale')
                infotext_like_params["Hires upscaler"] = loaded_params_dict.get('hr_upscaler')
                infotext_like_params["Hires steps"] = loaded_params_dict.get('hr_second_pass_steps')
                infotext_like_params["Hires resize-1"] = loaded_params_dict.get('hr_resize_x')
                infotext_like_params["Hires resize-2"] = loaded_params_dict.get('hr_resize_y')
                infotext_like_params["Hires prompt"] = loaded_params_dict.get('hr_prompt')
                infotext_like_params["Hires negative prompt"] = loaded_params_dict.get('hr_negative_prompt')
                infotext_like_params["Hires checkpoint"] = loaded_params_dict.get('hr_checkpoint_name')
                infotext_like_params["Hires sampler"] = loaded_params_dict.get('hr_sampler_name')
                infotext_like_params["Hires schedule type"] = loaded_params_dict.get('hr_scheduler')
                infotext_like_params["Hires CFG Scale"] = loaded_params_dict.get('hr_cfg')
                infotext_like_params["Hires Distilled CFG Scale"] = loaded_params_dict.get('hr_distilled_cfg')
                # Denoising strength is often part of Hires fix section in UI, ensure it's included
                infotext_like_params["Denoising strength"] = loaded_params_dict.get('denoising_strength')


            if 'extra_generation_params' in loaded_params_dict and isinstance(loaded_params_dict['extra_generation_params'], dict):
                for k,v in loaded_params_dict['extra_generation_params'].items():
                    infotext_like_params[k] = v

            return infotext_like_params

        load_params_button.click(
            fn=load_parameters_from_gallery,
            inputs=[item_to_load_json_path],
            outputs=[current_gallery_selected_params]
        )

        # Register the function that JS will call to get all UI updates.
        # This is a Gradio "API" endpoint implicitly created by this.
        # The JS will use `gradio_client.js` or similar to call this. (Hypothetical for now, actual call is complex)
        # For now, we'll rely on the JS calling this via a hidden button or a direct Gradio JS call if possible.
        # This function `get_gallery_parameter_updates` will be called by JS after `current_gallery_selected_params` is updated.
        # The mechanism is: JS clicks load_params_button -> load_parameters_from_gallery runs, updates current_gallery_selected_params
        # -> JS sees current_gallery_selected_params changed (how? via another click or observing state change)
        # -> JS calls a Python function (which will be get_gallery_parameter_updates) using the new state value.

    return gallery_interface
