import math
import os
import sys
import traceback
import random
import copy

import modules.scripts as scripts
import modules.images as images
import gradio as gr

from modules.processing import Processed, process_images
from PIL import Image
from modules.shared import opts, cmd_opts, state

try:
    from aaaaaa.p_method import get_i
except ImportError:
    print("Wildcards2 script: Could not import get_i from aaaaaa.p_method. Batch processing may not work correctly.")
    def get_i(p):
        if hasattr(p, "batch_index"):
            return p.batch_index
        return 0

class Script(scripts.Script):
    def title(self):
        return "Wildcards2"

    def ui(self, is_img2img):
        same_seed = gr.Checkbox(label='Use same seed for each image', value=False)

        return [same_seed]

    def run(self, p, same_seed):
        original_prompt = p.prompt[0] if type(p.prompt) == list else p.prompt
        
        all_prompts = []
        all_wildcard_texts = []

        for _ in range(p.batch_size * p.n_iter):
            wildcard_texts_for_image = []
            
            def replace_wildcard(chunk):
                if " " not in chunk:
                    file_dir = os.path.dirname(os.path.realpath("__file__"))
                    replacement_file = os.path.join(file_dir, f"scripts/wildcards/{chunk}.txt")
                    if os.path.exists(replacement_file):
                        with open(replacement_file, encoding="utf8") as f:
                            replacement = random.choice(f.read().splitlines())
                            wildcard_texts_for_image.append(replacement)
                            return replacement
                return chunk

            prompt = "".join(replace_wildcard(chunk) for chunk in original_prompt.split("__"))
            all_prompts.append(prompt)
            all_wildcard_texts.append(" ".join(wildcard_texts_for_image))

        if not hasattr(p, '_adetailer_patched_v2'):
            adetailer_script = None
            for script in p.scripts.alwayson_scripts:
                if hasattr(script, "title") and script.title() == "ADetailer":
                    adetailer_script = script
                    break

            if adetailer_script:
                original_get_prompt = adetailer_script.get_prompt
                original_extra_params = adetailer_script.extra_params

                def new_get_prompt(p, args):
                    prompt, negative_prompt = original_get_prompt(p, args)
                    
                    i = get_i(p)
                    if hasattr(p, '_all_wildcard_texts') and i < len(p._all_wildcard_texts):
                        wildcard_text = p._all_wildcard_texts[i]
                        for j in range(len(prompt)):
                            if prompt[j]:
                                prompt[j] = f"{prompt[j]}, {wildcard_text}"
                            else:
                                prompt[j] = wildcard_text

                    return prompt, negative_prompt

                def new_extra_params(arg_list):
                    params = original_extra_params(arg_list)
                    i = get_i(p)
                    if hasattr(p, '_all_wildcard_texts') and i < len(p._all_wildcard_texts):
                        wildcard_text = p._all_wildcard_texts[i]
                        for n, args in enumerate(arg_list):
                            param_key = f"ADetailer prompt{'' if n == 0 else f' {n+1}'}"
                            if params.get(param_key):
                                params[param_key] = f"{params[param_key]}, {wildcard_text}"
                            else:
                                params[param_key] = wildcard_text
                    return params

                adetailer_script.get_prompt = new_get_prompt
                adetailer_script.extra_params = new_extra_params
                p._adetailer_patched_v2 = True

        p._all_wildcard_texts = all_wildcard_texts

        all_seeds = []
        infotexts = []

        initial_seed = None
        initial_info = None

        print(f"Will process {p.batch_size * p.n_iter} images in {p.n_iter} batches.")

        state.job_count = p.n_iter
        p.n_iter = 1

        original_do_not_save_grid = p.do_not_save_grid

        p.do_not_save_grid = True

        output_images = []
        for batch_no in range(state.job_count):
            state.job = f"{batch_no+1} out of {state.job_count}"
            current_batch_prompts = all_prompts[batch_no*p.batch_size:(batch_no+1)*p.batch_size]
            p.prompt = current_batch_prompts
            p._current_wildcard_resolved_batch = current_batch_prompts
            if cmd_opts.enable_console_prompts:
                print(f"wildcards2.py: {p.prompt}")

            proc = process_images(p)
            output_images += proc.images
            infotext = "Wildcard prompt: "+original_prompt+"\nExample: "+proc.info
            all_seeds.append(proc.seed)
            infotexts.append(infotext)
            if initial_seed is None:
                initial_info = infotext
                initial_seed = proc.seed
            if not same_seed:
                p.seed = proc.seed+1

        p.do_not_save_grid = original_do_not_save_grid

        unwanted_grid_because_of_img_count = len(output_images) < 2 and opts.grid_only_if_multiple
        if (opts.return_grid or opts.grid_save) and not p.do_not_save_grid and not unwanted_grid_because_of_img_count:
            grid = images.image_grid(output_images, p.batch_size)

            if opts.return_grid:
                infotexts.insert(0, initial_info)
                all_seeds.insert(0, initial_seed)
                output_images.insert(0, grid)

            if opts.grid_save:
                images.save_image(grid, p.outpath_grids, "grid", all_seeds[0], original_prompt, opts.grid_format, info=initial_info, short_filename=not opts.grid_extended_filename, p=p, grid=True)

        return Processed(p, output_images, initial_seed, initial_info, all_prompts=all_prompts, all_seeds=all_seeds, infotexts=infotexts, index_of_first_image=0)