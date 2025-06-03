// javascript/gallery.js

function selectGalleryItem(json_path) {
    console.log("[Gallery] Selected item, JSON path:", json_path);

    const jsonPathTextbox = gradioApp().querySelector('#prompt_gallery_item_to_load_json_path textarea');
    if (jsonPathTextbox) {
        jsonPathTextbox.value = json_path;
        updateInput(jsonPathTextbox);
    } else {
        console.error("[Gallery] JSON path textbox not found.");
        return;
    }

    const loadButton = gradioApp().getElementById('prompt_gallery_load_params_button');
    if (loadButton) {
        // Step 1: Trigger Python to load parameters into the gr.State object
        loadButton.click();
        console.log("[Gallery] Triggered Python to load parameters into state.");

        // Step 2: After a short delay, trigger Python to apply those parameters from state to the UI
        setTimeout(() => {
            const applyButton = gradioApp().getElementById('prompt_gallery_apply_params_to_ui_button');
            const jsDummyTrigger = gradioApp().querySelector('#prompt_gallery_js_dummy_trigger textarea'); // Ensure this ID matches what's in ui.py

            if (applyButton && jsDummyTrigger) {
                // Update the dummy trigger to ensure the Python callback for applyButton re-fetches the state.
                jsDummyTrigger.value = new Date().getTime().toString(); // Change value to ensure event fires
                updateInput(jsDummyTrigger);

                console.log("[Gallery] Triggering Python to apply parameters to UI.");
                applyButton.click();

                showNotification("Applying parameters from gallery...", "info", 3000);

                const txt2imgTabButton = gradioApp().querySelector('#tab_txt2img button');
                if (txt2imgTabButton) {
                    txt2imgTabButton.click();
                }

            } else {
                if (!applyButton) console.error("[Gallery] Apply params button (prompt_gallery_apply_params_to_ui_button) not found.");
                if (!jsDummyTrigger) console.error("[Gallery] JS Dummy Trigger (prompt_gallery_js_dummy_trigger) for gallery apply not found.");
                showNotification("Error: Could not apply gallery parameters (UI elements missing).", "error", 5000);
            }
        }, 350); // Increased delay slightly to 350ms for state to potentially settle.

    } else {
        console.error("[Gallery] Load params button (prompt_gallery_load_params_button) not found.");
        showNotification("Error: Could not load gallery parameters (button missing).", "error", 5000);
        return;
    }
}

function showNotification(message, type = 'info', duration = 3000) {
    // Try to find a common notification container used by Gradio themes/extensions
    let notificationContainer = gradioApp().querySelector('.toast-container, #gr-notifications, .gradio-notifications');

    if (notificationContainer && window.Toast) { // Specifically for toastify if available
        new Toast({message: message, type: type, duration: duration});
    } else if (notificationContainer) { // Generic container found
        const toast = document.createElement('div');
        let toastClass = 'toast';
        if (type === 'error') toastClass += ' error';
        else if (type === 'warning') toastClass += ' warning';
        else toastClass += ' info';

        toast.className = toastClass;
        toast.textContent = message;

        // Simple close button
        const closeButton = document.createElement('button');
        closeButton.innerHTML = '&times;';
        closeButton.style.marginLeft = '10px';
        closeButton.style.border = 'none';
        closeButton.style.background = 'transparent';
        closeButton.style.cursor = 'pointer';
        closeButton.style.float = 'right';
        closeButton.onclick = () => toast.remove();
        toast.appendChild(closeButton);

        notificationContainer.prepend(toast); // Prepend to show at the top
        setTimeout(() => {
            if (toast.parentElement) toast.remove();
        }, duration);
    } else {
        // Fallback if no known notification system is found
        console.log(`[Gallery Notification] (${type}): ${message}`);
        // As a last resort, use an alert for errors, but it's disruptive.
        if (type === 'error') {
            alert(`ERROR: ${message}`);
        }
    }
}
