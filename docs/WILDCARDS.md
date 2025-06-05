# Wildcard Prompt Parsing

This repository includes a script for prompt wildcard replacement. Prompts can contain tokens wrapped with double underscores (e.g. `__haircolor__`). During generation these tokens are replaced with random entries from the corresponding text files in `scripts/wildcards`.

## How it works

1. **Input prompt** – A prompt may include `__token__` placeholders. Text files in `scripts/wildcards/` provide lists of replacement phrases for each token.
2. **Script execution** – `scripts/wildcards.py` runs before image generation. It reads the original prompt, stores it in `p.original_prompt_for_gallery`, replaces wildcard tokens, and stores the resolved prompt batch in `p._current_wildcard_resolved_batch`.
3. **Hi-Res fix** – If the user leaves the hires prompt empty, `modules/processing.py` copies the resolved prompts into `self.hr_prompts` for the hires pass so both passes use the same wildcard expansions.
4. **Gallery saving** – `modules/gallery_saver.py` writes the original and hires prompts to JSON alongside saved images for later reference.

The script enables consistent prompts across hires passes and allows galleries to show the original unparsed prompt.

