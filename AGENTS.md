Repository Overview
Main code resides in Python modules under modules/ and modules_forge/.

Tests are located primarily in extensions-builtin/adetailer/tests/.

Documentation lives in docs/, with docs/WILDCARDS.md explaining wildcard prompt parsing.

Working Guidelines
Run existing tests
Execute pytest -q from the repository root. Note that some tests may require additional dependencies.

Style and Linting

The project uses Ruff (see pyproject.toml) for linting.

Apply ruff --fix before committing to auto-correct trivial issues.

Commit Etiquette

Keep commit messages concise and descriptive.

Ensure the working directory is clean (git status should show no changes) before submitting a pull request.

Documentation Updates

Update README.md or files under docs/ whenever new functionality or command-line options are introduced.

If the change affects wildcard handling or prompt parsing, also revise docs/WILDCARDS.md.

Testing Additions

When adding new functionality, supplement it with unit tests in extensions-builtin/adetailer/tests/ or create new test modules as appropriate.

Non-Versioned Data

Generated gallery images and metadata are written under the gallery/ directory.

The directory is automatically added to .gitignore by modules/gallery_saver.py; ensure gallery data is never committed.

