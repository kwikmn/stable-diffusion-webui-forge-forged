from functools import wraps

import gradio as gr
from modules import gradio_extensions  # noqa: F401


class FormComponent:
    webui_do_not_create_gradio_pyi_thank_you = True

    def get_expected_parent(self):
        return gr.components.Form


gr.Dropdown.get_expected_parent = FormComponent.get_expected_parent


class ToolButton(gr.Button, FormComponent):
    """Small button with single emoji as text, fits inside gradio forms"""

    @wraps(gr.Button.__init__)
    def __init__(self, value="", *args, elem_classes=None, **kwargs):
        elem_classes = elem_classes or []
        super().__init__(*args, elem_classes=["tool", *elem_classes], value=value, **kwargs)

    def get_block_name(self):
        return "button"


class ResizeHandleRow(gr.Row):
    """Same as gr.Row but fits inside gradio forms"""
    webui_do_not_create_gradio_pyi_thank_you = True

    @wraps(gr.Row.__init__)
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.elem_classes.append("resize-handle-row")

    def get_block_name(self):
        return "row"


class FormRow(gr.Row, FormComponent):
    """Same as gr.Row but fits inside gradio forms"""

    def get_block_name(self):
        return "row"


class FormColumn(gr.Column, FormComponent):
    """Same as gr.Column but fits inside gradio forms"""

    def get_block_name(self):
        return "column"


class FormGroup(gr.Group, FormComponent):
    """Same as gr.Group but fits inside gradio forms"""

    def get_block_name(self):
        return "group"


class FormHTML(gr.HTML, FormComponent):
    """Same as gr.HTML but fits inside gradio forms"""

    def get_block_name(self):
        return "html"


class FormColorPicker(gr.ColorPicker, FormComponent):
    """Same as gr.ColorPicker but fits inside gradio forms"""

    def get_block_name(self):
        return "colorpicker"


class DropdownMulti(gr.Dropdown, FormComponent):
    """Same as gr.Dropdown but always multiselect"""

    @wraps(gr.Dropdown.__init__)
    def __init__(self, **kwargs):
        kwargs['multiselect'] = True
        super().__init__(**kwargs)

    def get_block_name(self):
        return "dropdown"


class DropdownEditable(gr.Dropdown, FormComponent):
    """Same as gr.Dropdown but allows editing value"""

    @wraps(gr.Dropdown.__init__)
    def __init__(self, **kwargs):
        kwargs['allow_custom_value'] = True
        super().__init__(**kwargs)

    def get_block_name(self):
        return "dropdown"


class InputAccordionImpl(gr.Checkbox):
    """A gr.Accordion that can be used as an input - returns True if open, False if closed.

    Actually just a hidden checkbox, but creates an accordion that follows and is followed by the state of the checkbox.
    """

    webui_do_not_create_gradio_pyi_thank_you = True

    global_index = 0

    @wraps(gr.Checkbox.__init__)
    def __init__(self, value=None, setup=False, **kwargs):
        if not setup:
            # If not in setup mode, it's just a plain Checkbox, behavior is fine.
            # However, this path is not taken by InputAccordion() factory.
            super().__init__(value=value, **kwargs)
            return

        # The elem_id passed in kwargs is intended for the logical input component (the Checkbox)
        checkbox_elem_id = kwargs.get('elem_id')
        if checkbox_elem_id is None:
            # Ensure a unique ID if none is provided for the checkbox
            checkbox_elem_id = f"input-accordion-checkbox-{InputAccordionImpl.global_index}"
            # We still need a base for the accordion if no elem_id was given at all
            accordion_base_id = f"input-accordion-{InputAccordionImpl.global_index}"
            InputAccordionImpl.global_index += 1
        else:
            # Base the accordion ID on the checkbox ID if an elem_id was provided
            accordion_base_id = checkbox_elem_id

        # Define a distinct elem_id for the visible gr.Accordion
        # This makes it unique and identifiable if needed, but not the primary component ID
        self.visible_accordion_id = f"{accordion_base_id}-accordion-visual"

        # The InputAccordionImpl (self) is the gr.Checkbox.
        # It gets the primary elem_id passed to InputAccordion().
        kwargs_checkbox = {
            **kwargs, # Original kwargs, including any user-provided elem_id
            "elem_id": checkbox_elem_id, # Assign the main elem_id here
            "visible": False, # The checkbox is hidden
        }
        super().__init__(value=value, **kwargs_checkbox)

        # The JavaScript needs to target the visible accordion by its new, derived ID.
        self.change(fn=None, _js='function(checked){ inputAccordionChecked("' + self.visible_accordion_id + '", checked); }', inputs=[self])

        # The visible gr.Accordion component.
        # We remove 'elem_id' from kwargs if it was present to avoid conflicts, then set our derived one.
        kwargs_for_gr_accordion = {key: value for key, value in kwargs.items() if key != 'elem_id'}
        kwargs_accordion_final = {
            **kwargs_for_gr_accordion,
            "elem_id": self.visible_accordion_id, # Use the derived ID for the visible accordion
            "label": kwargs.get('label', 'Accordion'),
            "elem_classes": ['input-accordion'],
            "open": value,
        }
        self.accordion = gr.Accordion(**kwargs_accordion_final)

    def extra(self):
        """Allows you to put something into the label of the accordion.

        Use it like this:

        ```
        with InputAccordion(False, label="Accordion") as acc:
            with acc.extra():
                FormHTML(value="hello", min_width=0)

            ...
        ```
        """

        return gr.Column(elem_id=self.accordion_id + '-extra', elem_classes='input-accordion-extra', min_width=0)

    def __enter__(self):
        self.accordion.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.accordion.__exit__(exc_type, exc_val, exc_tb)

    def get_block_name(self):
        return "checkbox"


def InputAccordion(value=None, **kwargs):
    return InputAccordionImpl(value=value, setup=True, **kwargs)
