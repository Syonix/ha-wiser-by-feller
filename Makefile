PUBLISHED_VERSION := $(shell python3 -c "import json; print([r for r in json.load(open('custom_components/wiser_by_feller/manifest.json'))['requirements'] if 'aiowiserbyfeller' in r][0].split('==')[1])")

dev:
	.venv/bin/pip install -e ../aioWiserByFeller

prod:
	.venv/bin/pip install aiowiserbyfeller==$(PUBLISHED_VERSION)
