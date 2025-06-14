import inspect
import warnings
from functools import wraps
import logging

import gradio as gr
import gradio.component_meta


from modules import scripts, ui_tempdir, patches

logger = logging.getLogger(__name__)


class GradioDeprecationWarning(DeprecationWarning):
    pass


def add_classes_to_gradio_component(comp):
    """
    this adds gradio-* to the component for css styling (ie gradio-button to gr.Button), as well as some others
    """

    comp.elem_classes = [f"gradio-{comp.get_block_name()}", *(getattr(comp, 'elem_classes', None) or [])]

    if getattr(comp, 'multiselect', False):
        comp.elem_classes.append('multiselect')


def IOComponent_init(self, *args, **kwargs):
    self.webui_tooltip = kwargs.pop('tooltip', None)

    if scripts.scripts_current is not None:
        scripts.scripts_current.before_component(self, **kwargs)

    scripts.script_callbacks.before_component_callback(self, **kwargs)

    res = original_IOComponent_init(self, *args, **kwargs)

    add_classes_to_gradio_component(self)

    scripts.script_callbacks.after_component_callback(self, **kwargs)

    if scripts.scripts_current is not None:
        scripts.scripts_current.after_component(self, **kwargs)

    return res


def Block_get_config(self):
    config = original_Block_get_config(self)

    webui_tooltip = getattr(self, 'webui_tooltip', None)
    if webui_tooltip:
        config["webui_tooltip"] = webui_tooltip

    config.pop('example_inputs', None)

    return config


def BlockContext_init(self, *args, **kwargs):
    if scripts.scripts_current is not None:
        scripts.scripts_current.before_component(self, **kwargs)

    scripts.script_callbacks.before_component_callback(self, **kwargs)

    res = original_BlockContext_init(self, *args, **kwargs)

    add_classes_to_gradio_component(self)

    scripts.script_callbacks.after_component_callback(self, **kwargs)

    if scripts.scripts_current is not None:
        scripts.scripts_current.after_component(self, **kwargs)

    return res


def Blocks_get_config_file(self, *args, **kwargs):
    config = original_Blocks_get_config_file(self, *args, **kwargs)

    for comp_config in config["components"]:
        if "example_inputs" in comp_config:
            comp_config["example_inputs"] = {"serialized": []}

    return config


original_IOComponent_init = patches.patch(__name__, obj=gr.components.Component, field="__init__", replacement=IOComponent_init)
original_Block_get_config = patches.patch(__name__, obj=gr.blocks.Block, field="get_config", replacement=Block_get_config)
original_BlockContext_init = patches.patch(__name__, obj=gr.blocks.BlockContext, field="__init__", replacement=BlockContext_init)
original_Blocks_get_config_file = patches.patch(__name__, obj=gr.blocks.Blocks, field="get_config_file", replacement=Blocks_get_config_file)


ui_tempdir.install_ui_tempdir_override()


def gradio_component_meta_create_or_modify_pyi(component_class, class_name, events):
    if hasattr(component_class, 'webui_do_not_create_gradio_pyi_thank_you'):
        return

    gradio_component_meta_create_or_modify_pyi_original(component_class, class_name, events)


# this prevents creation of .pyi files in webui dir
gradio_component_meta_create_or_modify_pyi_original = patches.patch(__file__, gradio.component_meta, 'create_or_modify_pyi', gradio_component_meta_create_or_modify_pyi)

# this function is broken and does not seem to do anything useful
gradio.component_meta.updateable = lambda x: x


class EventWrapper:
    def __init__(self, replaced_event):
        self.replaced_event = replaced_event
        self.has_trigger = getattr(replaced_event, 'has_trigger', None)
        self.event_name = getattr(replaced_event, 'event_name', None)
        self.callback = getattr(replaced_event, 'callback', None)
        self.real_self = getattr(replaced_event, '__self__', None)

    def __call__(self, *args, **kwargs):
        if '_js' in kwargs:
            kwargs['js'] = kwargs['_js']
            del kwargs['_js']

        def _filter(x):
            if x is None:
                return None
            if isinstance(x, (list, tuple)):
                return [i for i in x if i is not None]
            return x

        if len(args) >= 2:
            args = list(args)
            args[1] = _filter(args[1])
            if len(args) >= 3:
                args[2] = _filter(args[2])
            args = tuple(args)

        if 'inputs' in kwargs:
            kwargs['inputs'] = _filter(kwargs['inputs'])
        if 'outputs' in kwargs:
            kwargs['outputs'] = _filter(kwargs['outputs'])

        if self.replaced_event is None:
            logger.warning("Skipping event registration because replaced_event is None")
            return None

        return self.replaced_event(*args, **kwargs)

    @property
    def __self__(self):
        return self.real_self


def repair(grclass):
    if not getattr(grclass, 'EVENTS', None):
        return

    @wraps(grclass.__init__)
    def __repaired_init__(self, *args, tooltip=None, source=None, original=grclass.__init__, **kwargs):
        if source:
            kwargs["sources"] = [source]

        allowed_kwargs = inspect.signature(original).parameters
        fixed_kwargs = {}
        for k, v in kwargs.items():
            if k in allowed_kwargs:
                fixed_kwargs[k] = v
            else:
                warnings.warn(f"unexpected argument for {grclass.__name__}: {k}", GradioDeprecationWarning, stacklevel=2)

        original(self, *args, **fixed_kwargs)

        self.webui_tooltip = tooltip

        for event in self.EVENTS:
            replaced_event = getattr(self, str(event))
            fun = EventWrapper(replaced_event)
            setattr(self, str(event), fun)

    grclass.__init__ = __repaired_init__
    grclass.update = gr.update


for component in set(gr.components.__all__ + gr.layouts.__all__):
    repair(getattr(gr, component, None))


class Dependency(gr.events.Dependency):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        def then(*xargs, _js=None, **xkwargs):
            if _js:
                xkwargs['js'] = _js

            return original_then(*xargs, **xkwargs)

        original_then = self.then
        self.then = then


gr.events.Dependency = Dependency

gr.Box = gr.Group

