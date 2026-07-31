# ICThub login page

Static branded entry page for `login.icthub.top`. It does not authenticate users or collect credentials. The primary action redirects to the Cloudflare Access protected ComfyUI application at `https://comfy.icthub.top`.

## Preview

```bash
python3 -m http.server 8080 --bind 127.0.0.1 --directory deploy/login-page
```

Open `http://127.0.0.1:8080`.

An optional safe relative return path is supported:

```text
http://127.0.0.1:8080/?returnTo=/workflows
```

## Deployment boundary

- `login.icthub.top` serves this public static page on `127.0.0.1:8190`.
- `comfy.icthub.top` remains protected by Cloudflare Access.
- The page never handles passwords, one-time codes, API keys, or Access tokens.
- Do not add a Cloudflare Access bypass rule to the ComfyUI application.

## Pi 5 system services

After the Pi pulls this commit, install the root-owned units and local Tunnel configuration:

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
sudo systemctl enable --now icthub-login.service cloudflared-icthub.service
```

Route the public login hostname to the existing Tunnel before switching services:

```bash
export HTTP_PROXY=http://127.0.0.1:10808
export HTTPS_PROXY=http://127.0.0.1:10808
cloudflared tunnel route dns -f comfyui-pi5 login.icthub.top
```

Expected local listeners:

```text
127.0.0.1:8188  ComfyUI
127.0.0.1:8190  branded login page
```
