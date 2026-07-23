# Org Chart Wireframe - Web App

A browser front-end for `org_chart_converter.py`. Anyone with the URL can
drop in a "Manager - Level N / Employee" Excel export and get:

- an interactive, collapsible org chart on the page (search box included)
- a "Download Excel wireframe" link for the same staircase workbook the CLI
  produces

Nothing is written to disk on the server - the upload is parsed in memory
per-request and the response includes the generated file as a download link.

## Run it locally

```bash
cd webapp
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000`.

## Share it with the PX team

The dev server above (`python app.py`) is fine for trying it out, but isn't
meant for real traffic. For team-wide use, run it with a production WSGI
server on a machine reachable from your network:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

Then share `http://<that-machine's-address>:8000` with the team.

### Docker

A `Dockerfile` is included. Build it from the `org_chart_converter/` directory
(one level up from this file, since it needs both `app.py` and the shared
`org_chart_converter.py`):

```bash
cd ..   # into org_chart_converter/
docker build -f webapp/Dockerfile -t org-chart-webapp .
docker run -p 8000:8000 org-chart-webapp
```

This wasn't runnable in the sandbox this was built in (no Docker daemon
available there), so double-check the build once on a machine with Docker
before relying on it.

### Where to actually host it

Pick whatever your team already uses to run small internal tools - a shared
VM, an internal Kubernetes namespace, Render/Railway/Fly.io, etc. A few
things worth keeping in mind given this handles real reporting-line data:

- **Keep it off the open internet**, or put it behind your normal auth (VPN,
  SSO reverse proxy, IP allowlist). The app itself has no login.
- **Uploads aren't persisted** - each request is parsed and discarded, so
  there's nothing sitting on disk to secure after the fact.
- Increase `MAX_CONTENT_LENGTH` in `app.py` if someone's export is larger
  than 25 MB.
