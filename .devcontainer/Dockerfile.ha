FROM ghcr.io/home-assistant/home-assistant:2026.4.0

COPY custom_components/wiser_by_feller/manifest.json /tmp/manifest.json

RUN python3 -c "import json,subprocess,sys; reqs=json.load(open('/tmp/manifest.json')).get('requirements',[]); subprocess.run([sys.executable,'-m','uv','pip','install','--quiet','--index-strategy','unsafe-first-match']+reqs) if reqs else None"
