# ICThub Authentik deployment

This directory implements the identity boundary described in `docs/plans/invite-registration-authentik.md`. It does not add authentication code to ComfyUI and does not store credentials in Git.

## Frozen policy

| Setting | Value |
| --- | --- |
| Authentik | `2026.5.5` |
| PostgreSQL | `16.11-alpine` |
| Invitation lifetime | 24 hours |
| Invitation use | Single use |
| Invitation email | Mandatory, stored in invitation `fixed_data` |
| User session | 30 days |
| Normal-user MFA | Optional |
| Administrator boundary | Existing Cloudflare GitHub IdP plus Authentik MFA |
| SMTP | Not ready; registration remains disabled |

The Authentik Compose stack is the supported small-deployment service set: PostgreSQL, Authentik server, and Authentik worker. It does not mount the Docker socket or expose PostgreSQL. Authentik HTTP is published only on `127.0.0.1:9000` for Cloudflare Tunnel.

## Files

- `compose.yml`: fixed images and loopback-only service exposure.
- `blueprints/icthub-auth.yaml`: branded invitation enrollment, `comfy-users`, strict OIDC provider, and 30-day enrollment session.
- `manage.py`: configuration validation, SMTP test/confirmation, invitation creation/revocation, registration switch, health checks, MFA audit, and public acceptance.
- `backup.sh` / `restore.sh`: age-encrypted backup and isolated restore.
- `custom-templates/` and `media/`: branded verification/recovery email and identity assets.
- `icthub-authentik*.service` / `.timer`: service and daily encrypted backup units.

## 1. Host prerequisites

The Pi needs Docker Engine, Docker Compose v2, `age`, OpenSSL, and Python 3. If these system packages are missing, install them as root instead of using user-local binaries:

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2 age openssl python3
```

Authentik's Compose installation requires at least 2 CPU cores and 2 GB RAM. Check available memory before enabling it beside ComfyUI.

## 2. Install without opening registration

Run from the ComfyUI checkout:

```bash
sudo deploy/authentik/install.sh deploy/authentik
```

The installer creates:

```text
/home/winbeau/services/authentik-deploy/  root-owned deployment copy
/home/winbeau/services/authentik-data/    PostgreSQL and Authentik data
/etc/icthub-auth/authentik.env            root-only secrets and runtime settings
/etc/icthub-auth/login-config.js          registration disabled by default
```

Edit `/etc/icthub-auth/authentik.env` with `sudoedit`. Before the first start, replace the exact Cloudflare team callback placeholder:

```text
ICTHUB_CLOUDFLARE_REDIRECT_URI=https://<team-name>.cloudflareaccess.com/cdn-cgi/access/callback
```

Do not configure a wildcard redirect URI. Leave the SMTP host empty until a sender domain and provider are ready.

Validate the non-SMTP settings, then start the identity service while registration is still disabled:

```bash
sudo python3 /home/winbeau/services/authentik-deploy/manage.py validate
sudo systemctl enable --now icthub-login.service icthub-authentik.service
```

Check that only loopback listeners exist:

```bash
sudo ss -lntp | grep -E '127\.0\.0\.1:(8190|9000)'
sudo python3 /home/winbeau/services/authentik-deploy/manage.py health --wait 30
```

Expected listeners:

```text
127.0.0.1:8190  login-root redirect, registration, and Studio landing pages
127.0.0.1:9000  Authentik login and identity endpoints
```

## 3. Initial Authentik setup

Do not expose the initial setup flow publicly. From an administrator workstation, create an SSH local forward to the Pi:

```bash
ssh -L 9000:127.0.0.1:9000 winbeau@<pi-address>
```

Open `http://127.0.0.1:9000/if/flow/initial-setup/`, set the initial administrator password, and verify under **Customization → Blueprints** (direct path `/if/admin/#/blueprints/instances`) that `ICThub invitation enrollment and Cloudflare Access` applied successfully. A failed blueprint is a stop condition; do not manually approximate missing objects without recording the difference.

Verify these objects:

- group `comfy-users`;
- flow `icthub-invitation-enrollment`;
- application/provider `ICThub Cloudflare Access`;
- brands for `auth.icthub.top` and `auth-admin.icthub.top`;
- invitation stage has **Continue flow without invitation** disabled;
- user write creates inactive users;
- email stage activates users only after verification;
- final enrollment login stage uses a 30-day session.

For the normal default authentication flow, set its User Login Stage session duration to 30 days. Keep the default optional-MFA validation behavior for normal users.

## 4. Administrator MFA

Before publishing `auth-admin.icthub.top`:

1. Enroll at least one TOTP or WebAuthn device for every Authentik superuser.
2. Store recovery codes offline, not in the repository or `/home/winbeau/services`.
3. Confirm the default authentication flow prompts configured superusers for MFA.
4. Run the local API audit with a short-lived administrator API token entered at the prompt:

```bash
sudo python3 /home/winbeau/services/authentik-deploy/manage.py audit-admin-mfa
```

`auth-admin.icthub.top` must then be protected by a separate Cloudflare Access application that allows only the existing GitHub administrator IdP. An incognito test must require both the GitHub Access boundary and Authentik MFA.

## 5. Cloudflare Tunnel and Access

Create the `auth-admin.icthub.top` Access application with the existing GitHub administrator IdP before adding its DNS route. Configure the `comfy.icthub.top` OIDC policy before removing the currently working administrator login method.

Then add the new DNS routes to the existing named Tunnel:

```bash
cloudflared tunnel route dns -f comfyui-pi5 register.icthub.top
cloudflared tunnel route dns -f comfyui-pi5 auth.icthub.top
cloudflared tunnel route dns -f comfyui-pi5 auth-admin.icthub.top
```

Install the updated `deploy/login-page/cloudflared-config.yml` and systemd units as documented in `deploy/login-page/README.md`.

### `auth.icthub.top`

- Public through Tunnel; do **not** put it behind an Access policy that depends on this Authentik instance.
- Apply WAF/rate limits to authentication, enrollment, verification, and recovery paths.
- Set `Referrer-Policy: no-referrer` and redact the `itoken` query parameter from Logpush, request analytics, support captures, and reverse-proxy access logs. The production Compose file also forces Authentik's log level to `warning` so its request logger does not retain invitation URLs.
- Do not add Bypass rules.

### `auth-admin.icthub.top`

- Separate Cloudflare Access self-hosted application.
- Existing GitHub administrator IdP only.
- No One-time PIN, public email-domain rule, or Bypass.
- Use a shorter administrator Access session than the user application where practical.

### `comfy.icthub.top`

Create one generic OIDC login method using the values generated in `/etc/icthub-auth/authentik.env`.

```text
Authorization URL: https://login.icthub.top/application/o/authorize/
Token URL:         https://login.icthub.top/application/o/token/
User info URL:     https://login.icthub.top/application/o/userinfo/
JWKS URL:          https://login.icthub.top/application/o/icthub-cloudflare-access/jwks/
Scopes:            openid profile email groups
```

The `login.icthub.top` Brand uses the ICThub authentication Flow, which renders username and password together. Users with a configured TOTP device receive one additional verification challenge. Direct login ends at `https://login.icthub.top/studio`; OIDC requests preserve their callback and return to the originating application.

Configure the Access application as follows:

- session duration: 30 days;
- login methods: the single Authentik OIDC method;
- Instant Auth: enabled;
- allow selector: OIDC claim `groups` contains exact value `comfy-users`;
- One-time PIN: removed;
- Bypass policies: removed;
- broad email-domain allow rules: removed.

The Authentik application also rejects OIDC authorization for active users outside `comfy-users`, providing defense in depth.

## 6. SMTP and registration activation

Registration must remain disabled until SMTP is configured and a test message is received. Configure these keys in `/etc/icthub-auth/authentik.env`:

```text
AUTHENTIK_EMAIL__HOST
AUTHENTIK_EMAIL__PORT
AUTHENTIK_EMAIL__USERNAME
AUTHENTIK_EMAIL__PASSWORD
AUTHENTIK_EMAIL__USE_TLS
AUTHENTIK_EMAIL__USE_SSL
AUTHENTIK_EMAIL__FROM
```

Use exactly one of STARTTLS or implicit TLS. Then:

```bash
sudo python3 /home/winbeau/services/authentik-deploy/manage.py validate --require-smtp
sudo python3 /home/winbeau/services/authentik-deploy/manage.py smtp-test --to <administrator-test-mailbox>
```

After confirming receipt in the mailbox:

```bash
sudo python3 /home/winbeau/services/authentik-deploy/manage.py mark-smtp --recipient <administrator-test-mailbox>
```

In Authentik, select `email/icthub-recovery.html` on the Email Stage bound to the default recovery flow. Confirm that recovery requests produce the same browser response for existing and nonexistent addresses and that a completed password reset invalidates an already-open old session. Stop rollout if either check fails.

Only after email verification, recovery, and administrator MFA pass:

```bash
sudo python3 /home/winbeau/services/authentik-deploy/manage.py registration enable
```

This writes the root-controlled public runtime flag and restarts only the branded entry service. Disable it immediately during an incident:

```bash
sudo python3 /home/winbeau/services/authentik-deploy/manage.py registration disable
```

The Authentik enrollment flow itself still requires a valid invitation, so directly opening the flow without a token cannot create an account.

## 7. Invitation operations

Create invitations only with the controlled tool. It requires SMTP confirmation and always creates a 24-hour, single-use invitation with a mandatory bound email:

```bash
sudo python3 /home/winbeau/services/authentik-deploy/manage.py invite create --email user@example.com
```

The tool prompts for a short-lived Authentik administrator API token and prints the invitation URL once. Do not redirect this output to logs or ticket systems.

Revoke an invitation without placing its token in shell history:

```bash
sudo python3 /home/winbeau/services/authentik-deploy/manage.py invite revoke
```

Verify all cases before production:

- no token;
- malformed token;
- expired token;
- revoked token;
- second use of a consumed token;
- browser-tampered email different from invitation `fixed_data`;
- valid bound email with successful verification.

All invalid invitation states must show the same non-diagnostic user message.

## 8. Backup and restore

Generate an age identity on an offline recovery system. Copy only its public recipient to the Pi:

```bash
sudo install -o root -g root -m 0640 deploy/authentik/backup.env.example /etc/icthub-auth/backup.env
sudoedit /etc/icthub-auth/backup.env
```

The private age identity must remain offline. Enable the daily encrypted backup only after replacing the recipient placeholder:

```bash
sudo systemctl enable --now icthub-authentik-backup.timer
sudo systemctl start icthub-authentik-backup.service
```

Each backup contains encrypted, separate database and file archives. The file archive includes the Authentik secret key environment, media, templates, and deployment configuration. Plaintext database dumps are never written to disk.

Perform one restore in an isolated host or network before production. Copy the selected encrypted backup and offline age identity into that environment, then run:

```bash
sudo AGE_IDENTITY_FILE=/root/recovery/icthub-auth.agekey \
  /home/winbeau/services/authentik-deploy/restore.sh /path/to/backup-directory
```

After restore, keep registration disabled and verify administrator login, MFA, OIDC, invitation state, and a database-backed user before recording the exercise as passed.

## 9. User incidents, upgrades, acceptance, and rollback

For a compromised or departing account, disable the user under **Directory → Users**, revoke every session under the user's session view, revoke any outstanding invitation, and confirm a fresh request to `comfy.icthub.top` is denied after the Cloudflare Access session is revoked. Do not delete the user until the audit and recovery window ends.

For an Authentik upgrade:

1. disable registration and stop issuing invitations;
2. create and verify an encrypted backup;
3. review the target Authentik release notes and its matching official Compose file;
4. change only the fixed image tags and any required schema changes;
5. pull and restart with `docker compose up -d --remove-orphans`;
6. run local/public acceptance and one disposable invitation registration;
7. retain the prior image tags and matching backup until the observation window ends.

Run local and public boundary checks:

```bash
sudo python3 /home/winbeau/services/authentik-deploy/manage.py health --wait 30
sudo python3 /home/winbeau/services/authentik-deploy/manage.py acceptance
```

Then exercise registration, verification, login, logout, password recovery, user disable, all-session revocation, invitation expiry/revocation/reuse, and backup restoration. Record the date, Authentik image, database image, ComfyUI commit, Cloudflare policy IDs, test results, and rollback version.

Rollback order:

1. Disable registration and stop issuing invitations.
2. Revoke outstanding invitations or pause the Enrollment Flow.
3. Keep Cloudflare Access protecting ComfyUI; never add Bypass.
4. If Authentik OIDC fails, temporarily restore the existing GitHub IdP for administrators only.
5. Restore the previous fixed images and matching encrypted database/files backup.
6. Verify administrator GitHub boundary plus Authentik MFA before restoring users.

Do not open production registration while SMTP is unconfigured, any blueprint is unhealthy, administrators lack MFA, unverified users can enter `comfy-users`, a Bypass policy exists, or the encrypted backup cannot be restored with its matching Authentik secret key.
