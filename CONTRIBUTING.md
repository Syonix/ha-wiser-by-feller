# Contributing

Thank you for your interest in contributing to the Wiser by Feller Home Assistant integration.

## Getting started

### Prerequisites

- Python 3.12+
- A running Home Assistant instance or dev container (see `devcontainer/`)

### Set up a development environment

```bash
git clone https://github.com/Syonix/ha-wiser-by-feller.git
cd ha-wiser-by-feller
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements.dev.txt
```

Then run the setup script to prepare a local HA config directory:

```bash
./scripts/setup.sh
```

## Working with the aioWiserByFeller library

The integration depends on [aioWiserByFeller](https://github.com/Syonix/aioWiserByFeller). If you are making changes to both repos simultaneously, use the following workflow to avoid publishing a new library version just to test integration changes.

### Development (editable local library)

Bump the library version in its `pyproject.toml` to a dev suffix:

```toml
version = "1.0.1.dev0"
```

Update the requirement in `manifest.json` to match:

```json
"aiowiserbyfeller==1.0.1.dev0"
```

Install the library into this repo's venv in editable mode:

```bash
make dev
```

Home Assistant checks installed versions against `manifest.json` at startup. By aligning the dev version in both files, HA's requirement check passes and any change to the library source is reflected immediately without reinstalling.

### Switching to the published version

Before opening a PR, verify the integration works with the published library:

```bash
make prod
```

This installs the exact version currently pinned in `manifest.json`. Revert any temporary `manifest.json` changes to the published version pin first.

### Commit discipline

Keep `pyproject.toml` at `X.Y.Z.dev0` and `manifest.json` at `X.Y.Z.dev0` on the working branch. The `.dev0` suffix signals that the library has unpublished changes; remove it from both files once the library is published and before running release-it.

## Before committing

Run ruff to format and lint the code — the CI pipeline enforces both checks and will block your PR if they fail:

```bash
./scripts/lint.sh
```

This runs `ruff format` followed by `ruff check --fix` on the entire project. Make sure there are no remaining lint errors before pushing.

To check without auto-fixing:

```bash
ruff format --check --diff custom_components
ruff check custom_components
```

## Submitting changes

1. Fork the repository and create a branch from `main`.
2. Make your changes in `custom_components/wiser_by_feller/`.
3. Run `./scripts/lint.sh` and resolve any issues.
4. Run the test suite: `pytest`
5. Open a pull request against `main` with a clear description of what changed and why.

If your PR implements a new platform or device type, please also update the relevant section in `README.md`.

## Reporting bugs and requesting features

Use the GitHub issue templates:

- **Bug report** — for reproducible problems. Include your HA version, integration version, and µGateway generation.
- **Feature request** — for new functionality or device support.

## Code style

- All code must pass `ruff check` and `ruff format --check` (configured in `pyproject.toml`).
- Keep entity logic in the appropriate platform file (`light.py`, `cover.py`, etc.).
- Shared utilities belong in `util.py` or `entity.py`.
- Do not add comments that just describe what the code does — only add them when the *why* is non-obvious.
