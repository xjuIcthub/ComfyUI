# ICThub authentication entry pages

Static branded registration navigation for `register.icthub.top`. It never authenticates users, checks invitation validity, or stores passwords, invitations, API keys, OIDC secrets, or identity tokens.

- `login.icthub.top`: sends users without a session to the ICThub Authentik Flow and users with an Authentik session to `/studio`.
- `login.icthub.top/studio`: provides the post-login Studio landing page with ComfyUI, TOTP setup, and account settings links.
- `register.icthub.top`: collects an invitation token and submits it directly to the Authentik invitation Enrollment Flow.
- Registration is disabled by default and is enabled only through `/etc/icthub-auth/login-config.js` after SMTP acceptance.

## Preview

```bash
python3 deploy/login-page/server.py --bind 127.0.0.1 --port 8080
```

Preview the registration page with its Host header:

```bash
curl -H 'Host: register.icthub.top' http://127.0.0.1:8080/
```

The server exposes only the public HTML/CSS/JavaScript allowlist, adds browser security headers, rejects unknown hosts, and removes query strings from access logs.

## Deployment boundary

- the fixed login-root redirect plus public registration and Studio landing pages listen locally on `127.0.0.1:8190`;
- Authentik serves every other `login.icthub.top` path and `auth.icthub.top` on `127.0.0.1:9000`;
- ComfyUI remains protected by Cloudflare Access on `127.0.0.1:8188`;
- `auth.icthub.top` is public through Tunnel but must not use an Access policy that depends on Authentik;
- `auth-admin.icthub.top` uses the existing GitHub administrator IdP and Authentik MFA;
- no Cloudflare Access Bypass rule is permitted.

## Pi 5 system services

After the Pi pulls the deployment changes, install the root-owned units and Tunnel configuration:

```bash
sudo install -o root -g root -m 0644 \
  deploy/login-page/icthub-login.service \
  /etc/systemd/system/icthub-login.service

sudo install -o root -g root -m 0644 \
  deploy/login-page/cloudflared-icthub.service \
  /etc/systemd/system/cloudflared-icthub.service

sudo install -o root -g winbeau -m 0640 \
  deploy/login-page/cloudflared-config.yml \
  /etc/cloudflared/config.yml

sudo systemctl daemon-reload
sudo systemctl disable --now cloudflared.service cloudflared-comfyui.service 2>/dev/null || true
sudo systemctl enable --now icthub-login.service icthub-authentik.service cloudflared-icthub.service
```

Route the additional hostnames to the existing named Tunnel before switching services:

```bash
cloudflared tunnel route dns -f comfyui-pi5 login.icthub.top
cloudflared tunnel route dns -f comfyui-pi5 register.icthub.top
cloudflared tunnel route dns -f comfyui-pi5 auth.icthub.top
cloudflared tunnel route dns -f comfyui-pi5 auth-admin.icthub.top
```

Do not put invitations into a route command, URL sent to the static server, shell log, or analytics system.

Expected local listeners:

```text
127.0.0.1:8188  ComfyUI
127.0.0.1:8190  login-root redirect, registration, and Studio landing pages
127.0.0.1:9000  Authentik
```

See `deploy/authentik/README.md` for SMTP activation, invitation operations, Cloudflare OIDC configuration, backup/restore, acceptance, and rollback.
