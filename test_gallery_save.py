import os
import json
import datetime
import hashlib
from PIL import Image
from unittest.mock import MagicMock, patch, mock_open
import sys
import importlib

class MockOpts:
    def __init__(self):
        self.enable_pnginfo = True
        self.CLIP_stop_at_last_layers = 1

class MockSharedModule:
    def __init__(self):
        self.opts = MockOpts()

class MockImagesModule:
    def __init__(self):
        self.save_image_with_geninfo = MagicMock()

shared_mock_instance = MockSharedModule()
images_mock_instance = MockImagesModule()

sys.modules['modules.shared'] = shared_mock_instance
sys.modules['modules.images'] = images_mock_instance

try:
    import torch
    if not hasattr(torch, 'cuda'):
        torch.cuda = MagicMock()
    torch.cuda.is_available = MagicMock(return_value=False)
except ImportError: pass
except Exception as e: print(f"Error during torch pre-patching: {e}")

class MockStableDiffusionProcessing:
    def __init__(self):
        self.prompt = ""; self.negative_prompt = ""; self.steps = 20; self.seed = 12345; self.cfg_scale = 7.0
        self.width = 512; self.height = 512; self.sampler_name = "Euler a"; self.scheduler = "Karras"
        self.sd_model_hash = "hash123"; self.sd_model_name = "model.safetensors"; self.sd_vae_name = "vae.pt"
        self.sd_vae_hash = "vaehash456"; self.denoising_strength = 0.7; self.subseed = -1; self.subseed_strength = 0
        self.seed_resize_from_w = 0; self.seed_resize_from_h = 0; self.extra_generation_params = {}
        self.original_prompt_for_gallery = None; self.original_negative_prompt_for_gallery = None
        self.enable_hr = False; self.hr_scale = 2.0; self.hr_upscaler = "Latent"; self.hr_second_pass_steps = 0
        self.hr_resize_x = 0; self.hr_resize_y = 0; self.hr_prompt = ""; self.hr_negative_prompt = ""
        self.user_left_hr_prompt_empty = True; self.user_left_hr_negative_prompt_empty = True
        self.hr_checkpoint_name = None; self.hr_sampler_name = None; self.hr_scheduler = None; self.hr_cfg = None
        self.hr_distilled_cfg = None; self.restore_faces = False; self.tiling = False; self.image_cfg_scale = None
        self.mask_blur = 4; self.inpainting_fill = 1; self.inpaint_full_res = True; self.inpaint_full_res_padding = 32
        self.inpainting_mask_invert = 0

results = {}
mock_p_instance = MockStableDiffusionProcessing()
mock_p_instance.prompt = "a detailed photo of a cat"; mock_p_instance.negative_prompt = "blurry, ugly"
mock_p_instance.steps = 25; mock_p_instance.seed = 5555; mock_p_instance.cfg_scale = 7.5
mock_p_instance.width = 768; mock_p_instance.height = 512; mock_p_instance.sampler_name = "DPM++ 2M Karras"
mock_p_instance.sd_model_hash = "modelhash123"
mock_p_instance.original_prompt_for_gallery = "a detailed photo of a __animal__"
mock_p_instance.original_negative_prompt_for_gallery = "blurry, ugly, text, watermark, __artifact__"
mock_p_instance.extra_generation_params = {"custom_param": "value1", "another_param": 123}
mock_image_obj = Image.new("RGB", (mock_p_instance.width, mock_p_instance.height), color="blue")

mock_json_file_handle = mock_open().return_value
mock_gitignore_handle = mock_open().return_value
mock_other_file_handle = mock_open().return_value

def open_side_effect(filename, *args, **kwargs):
    if filename.endswith(".json"):
        mock_json_file_handle.reset_mock()
        return mock_json_file_handle
    elif filename == ".gitignore":
        mock_gitignore_handle.reset_mock()
        return mock_gitignore_handle
    else:
        mock_other_file_handle.reset_mock()
        return mock_other_file_handle

@patch('os.makedirs') # 1st arg: mock_os_makedirs_global
@patch('os.path.exists') # 2nd arg: mock_os_path_exists_global
@patch('builtins.open', side_effect=open_side_effect) # 3rd arg: mock_builtin_open_via_side_effect
@patch('modules.gallery_saver.os.path.join', side_effect=lambda *args: '/'.join(args)) # 4th arg: mock_os_path_join_gs
@patch('modules.gallery_saver.hashlib.md5') # 5th arg: mock_hashlib_md5_gs
@patch('modules.gallery_saver.datetime.datetime') # 6th arg: mock_datetime_datetime_gs
def run_test(mock_os_makedirs_global, mock_os_path_exists_global, mock_builtin_open_via_side_effect,
             mock_os_path_join_gs, mock_hashlib_md5_gs, mock_datetime_datetime_gs):

    from modules import gallery_saver
    importlib.reload(gallery_saver)

    mock_os_makedirs_global.assert_any_call("gallery", exist_ok=True)

    mock_now = MagicMock()
    mock_now.strftime.return_value = "20230101120000000000"
    mock_datetime_datetime_gs.now.return_value = mock_now # Use the correct mock object

    mock_md5_obj = MagicMock()
    mock_md5_obj.hexdigest.return_value = "prompt123"
    mock_hashlib_md5_gs.return_value = mock_md5_obj # Use the correct mock object

    expected_unique_base = f"{mock_now.strftime.return_value}_{mock_md5_obj.hexdigest.return_value[:8]}"
    # Use mock_os_path_join_gs for paths constructed *inside* gallery_saver's functions
    expected_image_path = mock_os_path_join_gs("gallery", f"{expected_unique_base}.png")
    expected_json_path = mock_os_path_join_gs("gallery", f"{expected_unique_base}.json")


    image_path_res, json_path_res = gallery_saver.save_to_gallery(
        mock_image_obj, mock_p_instance,
        mock_p_instance.original_prompt_for_gallery,
        mock_p_instance.original_negative_prompt_for_gallery
    )

    results['image_path_res'] = image_path_res; results['json_path_res'] = json_path_res
    results['expected_image_path'] = expected_image_path; results['expected_json_path'] = expected_json_path

    mock_hashlib_md5_gs.assert_called_with((mock_p_instance.original_prompt_for_gallery or "").encode('utf-8'))

    expected_infotext_for_png = f"{mock_p_instance.original_prompt_for_gallery}\nNegative prompt: {mock_p_instance.original_negative_prompt_for_gallery}\nSteps: {mock_p_instance.steps}, Seed: {mock_p_instance.seed}, CFG scale: {mock_p_instance.cfg_scale}, Size: {mock_p_instance.width}x{mock_p_instance.height}, Model hash: {mock_p_instance.sd_model_hash}, Sampler: {mock_p_instance.sampler_name}"
    images_mock_instance.save_image_with_geninfo.assert_called_with(
        mock_image_obj, expected_infotext_for_png, expected_image_path, pnginfo_section_name="parameters"
    )

    mock_builtin_open_via_side_effect.assert_any_call(expected_json_path, 'w', encoding='utf-8')

    written_chunks = [call_args[0][0] for call_args in mock_json_file_handle.write.call_args_list if call_args]
    written_json_str = "".join(written_chunks)

    if not written_json_str:
         raise AssertionError(f"JSON file {expected_json_path} was opened, but nothing was written to it by json.dump, or write capture failed.")

    saved_params = json.loads(written_json_str)
    results['saved_params'] = saved_params

    assert saved_params["original_prompt"] == mock_p_instance.original_prompt_for_gallery
    assert saved_params["original_negative_prompt"] == mock_p_instance.original_negative_prompt_for_gallery
    assert saved_params["steps"] == mock_p_instance.steps
    assert saved_params["seed"] == mock_p_instance.seed
    assert saved_params["sampler_name"] == mock_p_instance.sampler_name
    assert saved_params["clip_skip"] == shared_mock_instance.opts.CLIP_stop_at_last_layers
    assert saved_params["extra_generation_params"] == mock_p_instance.extra_generation_params
    assert not saved_params.get("enable_hr")

    return results

original_sys_modules_shared_before_test = sys.modules.get('modules.shared')
original_sys_modules_images_before_test = sys.modules.get('modules.images')

try:
    test_results = run_test()
    print(f"Test image path result: {test_results['image_path_res']}")
    print(f"Test json path result: {test_results['json_path_res']}")
    print(f"Expected image path: {test_results['expected_image_path']}")
    print(f"Expected json path: {test_results['expected_json_path']}")
    print(f"Saved original_prompt: {test_results['saved_params']['original_prompt']}")
    print("Test completed successfully.")
except AssertionError as e:
    print(f"Test assertion failed: {e}")
except Exception as e:
    print(f"An error occurred during the test: {e}")
    import traceback
    print(traceback.format_exc())
finally:
    if original_sys_modules_shared_before_test:
        sys.modules['modules.shared'] = original_sys_modules_shared_before_test
    elif 'modules.shared' in sys.modules:
        del sys.modules['modules.shared']

    if original_sys_modules_images_before_test:
        sys.modules['modules.images'] = original_sys_modules_images_before_test
    elif 'modules.images' in sys.modules:
        del sys.modules['modules.images']
