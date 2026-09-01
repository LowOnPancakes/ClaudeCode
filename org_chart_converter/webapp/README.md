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

### Deploying on a Linux VPS (CentOS/RHEL/Rocky) with systemd

`deploy/` has everything for this: a systemd unit, an install script, and an
nginx reverse-proxy config. On the server, as root:

```bash
git clone <this-repo-url>
cd <repo>/org_chart_converter
sudo bash webapp/deploy/install_centos.sh
```

That script:
- installs Python/pip if missing
- creates a dedicated, no-login `orgchart` system user
- copies the app to `/opt/org-chart-webapp`, builds a virtualenv there, and
  installs dependencies + gunicorn
- installs and starts `org-chart-webapp.service`, listening on
  `127.0.0.1:8000` (not exposed externally yet)

Then put nginx in front of it so the team can actually reach it:

```bash
sudo cp webapp/deploy/nginx-org-chart.conf /etc/nginx/conf.d/org-chart.conf
sudo sed -i 's/orgchart.example.com/your.actual.domain/' /etc/nginx/conf.d/org-chart.conf
sudo nginx -t && sudo systemctl reload nginx
sudo firewall-cmd --permanent --add-service=http && sudo firewall-cmd --reload
```

(Swap `--add-service=http` for `--add-service=https` once you've set up TLS
— see the note at the bottom of `nginx-org-chart.conf`.)

To redeploy after a code change: `git pull` on the server, then re-run
`sudo bash webapp/deploy/install_centos.sh` — it overwrites `/opt/org-chart-webapp`
and restarts the service. Useful commands afterward:

```bash
sudo systemctl status org-chart-webapp   # is it running
sudo journalctl -u org-chart-webapp -f   # tail its logs
sudo systemctl restart org-chart-webapp  # restart after a manual change
```

This was written and syntax-checked in a sandbox without a real CentOS
target to install onto, so treat the first run on your actual server as a
verification pass, not a guaranteed no-touch install.

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

### Deploying via cPanel (e.g. a domain like tacoknight.com)

Most cPanel hosts run Python apps through Phusion Passenger via a **"Setup
Python App"** tool (sometimes labeled "Python Selector" or "Application
Manager") under the Software section. `passenger_wsgi.py` in this folder is
the entry point it looks for.

1. In cPanel, open **Setup Python App** and click **Create Application**.
2. Set:
   - **Python version**: 3.9+ (whatever's newest available)
   - **Application root**: a folder name, e.g. `orgchart` — cPanel creates
     `~/orgchart` and a matching virtualenv
   - **Application URL**: either a subdomain (e.g. `orgchart.tacoknight.com`
     — simplest option) or a path (e.g. `tacoknight.com/orgchart`)
   - **Application startup file**: `passenger_wsgi.py`
   - **Application Entry point**: `application`
3. Click **Create**. cPanel shows a command like:
   ```
   source /home/<user>/virtualenv/orgchart/3.9/bin/activate && cd /home/<user>/orgchart
   ```
   Copy it — you'll run it over SSH (or the cPanel **Terminal** app if SSH
   isn't enabled) any time you need to install/update dependencies.
4. Upload these files into that application root (File Manager, or SFTP)
   **flattened into one directory** (no `webapp/` subfolder):
   - `app.py`, `passenger_wsgi.py`, `requirements.txt`, `templates/` (from
     this `webapp/` folder)
   - `org_chart_converter.py` (from the parent folder, one level up)
5. Run the activation command from step 3, then:
   ```bash
   pip install -r requirements.txt
   ```
6. Back in cPanel's Setup Python App page, click **Restart**.
7. Visit the Application URL you chose in step 2.

Exact wording varies a little by host, but "Setup Python App" + Passenger is
the standard cPanel pattern this follows. If your specific cPanel skin
doesn't have that tool, your host doesn't support Python apps and you'd need
a different approach (e.g. a subdomain proxied to a small VM running
gunicorn instead).

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
