import math
import os
import sys
import traceback
import random

import modules.scripts as scripts
import modules.images as images
import gradio as gr

from modules.processing import Processed, process_images
from PIL import Image
from modules.shared import opts, cmd_opts, state


class Script(scripts.Script):
    def title(self):
        return "Wildcards"

    def ui(self, is_img2img):
        same_seed = gr.Checkbox(label='Use same seed for each image', value=False)

        return [same_seed]

    def run(self, p, same_seed):
        def replace_wildcard(chunk):
            if " " not in chunk:
                file_dir = os.path.dirname(os.path.realpath("__file__"))
                replacement_file = os.path.join(file_dir, f"scripts/wildcards/{chunk}.txt")
                if os.path.exists(replacement_file):
                    with open(replacement_file, encoding="utf8") as f:
                        return random.choice(f.read().splitlines())
            return chunk
        
        original_prompt = p.prompt[0] if isinstance(p.prompt, list) else p.prompt
        p.original_prompt_for_gallery = original_prompt

        original_negative_prompt = (
            p.negative_prompt[0] if isinstance(p.negative_prompt, list) else p.negative_prompt
        )
        p.original_negative_prompt_for_gallery = original_negative_prompt
        all_prompts = ["".join(replace_wildcard(chunk) for chunk in original_prompt.split("__")) for _ in range(p.batch_size * p.n_iter)]

        # TODO: Pregenerate seeds to prevent overlaps when batch_size is > 1
        # Known issue: Clicking "recycle seed" on an image in a batch_size > 1 may not get the correct seed.
        # (unclear if this is an issue with this script or not, but pregenerating would prevent). However,
        # filename and exif data on individual images match correct seeds (testable via sending png info to txt2img).
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
                print(f"wildcards.py: {p.prompt}")
            proc = process_images(p)
            output_images += proc.images
            # TODO: Also add wildcard data to exif of individual images, currently only appear on the saved grid.
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
