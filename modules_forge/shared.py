import os
import argparse

from backend import utils
from modules.paths_internal import models_path
from pathlib import Path


parser = argparse.ArgumentParser()

parser.add_argument(
    "--controlnet-dir",
    type=Path,
    help="Path to directory with ControlNet models",
    default=None,
)
parser.add_argument(
    "--controlnet-preprocessor-models-dir",
    type=Path,
    help="Path to directory with annotator model directories",
    default=None,
)

cmd_opts = parser.parse_known_args()[0]

if cmd_opts.controlnet_dir:
    controlnet_dir = str(cmd_opts.controlnet_dir)
else:
    controlnet_dir = os.path.join(models_path, 'ControlNet')
os.makedirs(controlnet_dir, exist_ok=True)

if cmd_opts.controlnet_preprocessor_models_dir:
    preprocessor_dir = str(cmd_opts.controlnet_preprocessor_models_dir)
else:
    preprocessor_dir = os.path.join(models_path, 'ControlNetPreprocessor')
os.makedirs(preprocessor_dir, exist_ok=True)

diffusers_dir = os.path.join(models_path, 'diffusers')
os.makedirs(diffusers_dir, exist_ok=True)

supported_preprocessors = {}

class NonePreprocessor:
    def __init__(self):
        self.name = "None"
        self.tags = [] 
        self.slider_resolution = 512 
        self.slider_1_text = ""
        self.slider_1_min = 0
        self.slider_1_max = 0
        self.slider_1_value = 0
        self.slider_2_text = ""
        self.slider_2_min = 0
        self.slider_2_max = 0
        self.slider_2_value = 0
        self.slider_3_text = ""
        self.slider_3_min = 0
        self.slider_3_max = 0
        self.slider_3_value = 0
        self.sorting_priority = -1 # Or other suitable default

    def __call__(self, img, res=None, slider_1=None, slider_2=None, slider_3=None, **kwargs):
        if img is None:
            # For "None" preprocessor, simply returning None if img is None might be okay.
            # Let's assume it should pass through, and errors for None image are handled upstream or it's not called with None.
            return img, {} # Return image and an empty dict for info
        return img, {}

supported_preprocessors["None"] = NonePreprocessor()
supported_control_models = []


def add_supported_preprocessor(preprocessor):
    global supported_preprocessors
    p = preprocessor
    supported_preprocessors[p.name] = p
    return


def add_supported_control_model(control_model):
    global supported_control_models
    supported_control_models.append(control_model)
    return


def try_load_supported_control_model(ckpt_path):
    global supported_control_models
    state_dict = utils.load_torch_file(ckpt_path, safe_load=True)
    for supported_type in supported_control_models:
        state_dict_copy = {k: v for k, v in state_dict.items()}
        model = supported_type.try_build_from_state_dict(state_dict_copy, ckpt_path)
        if model is not None:
            return model
    return None
