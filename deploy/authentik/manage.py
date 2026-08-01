#!/usr/bin/env python3
import argparse
import getpass
import hashlib
import json
import os
import re
import smtplib
import ssl
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

DEFAULT_ENV = Path("/etc/icthub-auth/authentik.env")
DEFAULT_SMTP_MARKER = Path("/etc/icthub-auth/smtp-verified.json")
DEFAULT_LOGIN_CONFIG = Path("/etc/icthub-auth/login-config.js")
ENROLLMENT_SLUG = "icthub-invitation-enrollment"
PLACEHOLDER_PREFIXES = ("GENERATE_", "CHANGE-ME")
BASE_REQUIRED = {
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "AUTHENTIK_POSTGRESQL__HOST",
    "AUTHENTIK_POSTGRESQL__NAME",
    "AUTHENTIK_POSTGRESQL__USER",
    "AUTHENTIK_POSTGRESQL__PASSWORD",
    "AUTHENTIK_SECRET_KEY",
    "ICTHUB_OIDC_CLIENT_ID",
    "ICTHUB_OIDC_CLIENT_SECRET",
    "ICTHUB_CLOUDFLARE_REDIRECT_URI",
}
SMTP_REQUIRED = {
    "AUTHENTIK_EMAIL__HOST",
    "AUTHENTIK_EMAIL__PORT",
    "AUTHENTIK_EMAIL__FROM",
}


class ConfigError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def load_env(path):
    values = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigError(f"{path}:{line_number}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def bool_value(value):
    return value.strip().lower() in {"1", "true", "yes", "on"}


def validate_permissions(path, maximum, kind):
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & ~maximum:
        raise ConfigError(f"{path}: {kind} mode {mode:04o} exceeds {maximum:04o}")


def validate_env(path, require_smtp=False):
    if not path.is_file():
        raise ConfigError(f"missing environment file: {path}")
    validate_permissions(path.parent, 0o750, "directory")
    validate_permissions(path, 0o640, "file")
    env = load_env(path)

    required = BASE_REQUIRED | (SMTP_REQUIRED if require_smtp else set())
    missing = sorted(key for key in required if not env.get(key))
    if missing:
        raise ConfigError("missing required settings: " + ", ".join(missing))
    placeholders = sorted(key for key in required if env[key].startswith(PLACEHOLDER_PREFIXES))
    if placeholders:
        raise ConfigError("placeholder values remain: " + ", ".join(placeholders))
    if env["POSTGRES_PASSWORD"] != env["AUTHENTIK_POSTGRESQL__PASSWORD"]:
        raise ConfigError("PostgreSQL passwords do not match")
    if len(env["POSTGRES_PASSWORD"]) < 32:
        raise ConfigError("PostgreSQL password must be at least 32 characters")
    if len(env["AUTHENTIK_SECRET_KEY"]) < 50:
        raise ConfigError("AUTHENTIK_SECRET_KEY must be at least 50 characters")
    if len(env["ICTHUB_OIDC_CLIENT_SECRET"]) < 32:
        raise ConfigError("OIDC client secret must be at least 32 characters")
    redirect_uri = env["ICTHUB_CLOUDFLARE_REDIRECT_URI"]
    if not re.fullmatch(r"https://[a-z0-9-]+\.cloudflareaccess\.com/cdn-cgi/access/callback", redirect_uri):
        raise ConfigError("Cloudflare OIDC redirect URI must be the exact team callback URL")

    if require_smtp:
        use_tls = bool_value(env.get("AUTHENTIK_EMAIL__USE_TLS", "false"))
        use_ssl = bool_value(env.get("AUTHENTIK_EMAIL__USE_SSL", "false"))
        if use_tls == use_ssl:
            raise ConfigError("SMTP must enable exactly one of STARTTLS or implicit TLS")
        try:
            port = int(env["AUTHENTIK_EMAIL__PORT"])
        except ValueError as error:
            raise ConfigError("SMTP port must be an integer") from error
        if not 1 <= port <= 65535:
            raise ConfigError("SMTP port is outside the valid range")
        username = env.get("AUTHENTIK_EMAIL__USERNAME", "")
        password = env.get("AUTHENTIK_EMAIL__PASSWORD", "")
        if bool(username) != bool(password):
            raise ConfigError("SMTP username and password must either both be set or both be empty")
    return env


def http_request(url, method="GET", token=None, payload=None, host=None, follow_redirects=True, timeout=15, extra_headers=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if host:
        headers["Host"] = host
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener() if follow_redirects else urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read()
            payload = json.loads(body) if body and response.headers.get_content_type() == "application/json" else body or None
            return response.status, response.headers, payload
    except urllib.error.HTTPError as error:
        body = error.read()
        detail = body.decode("utf-8", "replace")[:500]
        if follow_redirects:
            raise ConfigError(f"HTTP {error.code} from {url}: {detail}") from error
        return error.code, error.headers, None
    except urllib.error.URLError as error:
        raise ConfigError(f"request failed for {url}: {error.reason}") from error


def api_token():
    token = os.environ.get("AUTHENTIK_API_TOKEN") or getpass.getpass("Authentik admin API token: ")
    if not token:
        raise ConfigError("an Authentik admin API token is required")
    return token


def api_results(base_url, path, token):
    _, _, payload = http_request(base_url.rstrip("/") + path, token=token, host="auth.icthub.top")
    if isinstance(payload, dict) and "results" in payload:
        return payload["results"]
    if isinstance(payload, list):
        return payload
    raise ConfigError(f"unexpected API response from {path}")


def require_smtp_marker(path):
    if not path.is_file():
        raise ConfigError(f"SMTP receipt has not been confirmed: {path}")
    marker = json.loads(path.read_text(encoding="utf-8"))
    if marker.get("confirmed_received") is not True:
        raise ConfigError("SMTP marker does not confirm receipt")
    return marker


def smtp_test(args):
    env = validate_env(args.env, require_smtp=True)
    message = EmailMessage()
    message["Subject"] = "ICThub Authentik SMTP verification"
    message["From"] = env["AUTHENTIK_EMAIL__FROM"]
    message["To"] = args.to
    message.set_content("This message verifies SMTP delivery for ICThub Authentik. No credentials or invitation tokens are included.")

    context = ssl.create_default_context()
    host = env["AUTHENTIK_EMAIL__HOST"]
    port = int(env["AUTHENTIK_EMAIL__PORT"])
    if bool_value(env.get("AUTHENTIK_EMAIL__USE_SSL", "false")):
        connection = smtplib.SMTP_SSL(host, port, timeout=10, context=context)
    else:
        connection = smtplib.SMTP(host, port, timeout=10)
    with connection as smtp:
        if bool_value(env.get("AUTHENTIK_EMAIL__USE_TLS", "false")):
            smtp.starttls(context=context)
        username = env.get("AUTHENTIK_EMAIL__USERNAME", "")
        if username:
            smtp.login(username, env["AUTHENTIK_EMAIL__PASSWORD"])
        smtp.send_message(message)
    print("SMTP server accepted the test message. Confirm receipt before enabling registration.")


def mark_smtp(args):
    validate_env(args.env, require_smtp=True)
    if os.geteuid() != 0:
        raise ConfigError("mark-smtp must run as root")
    confirmation = input('Type "SMTP TEST RECEIVED" after checking the mailbox: ')
    if confirmation != "SMTP TEST RECEIVED":
        raise ConfigError("SMTP receipt was not confirmed")
    domain = args.recipient.rsplit("@", 1)[-1].lower()
    payload = {
        "confirmed_received": True,
        "recipient_domain": domain,
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
    }
    args.marker.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.chmod(args.marker, 0o640)
    print(f"Wrote SMTP verification marker: {args.marker}")


def set_registration(args):
    if os.geteuid() != 0:
        raise ConfigError("registration changes must run as root")
    enabled = args.state == "enable"
    if enabled:
        validate_env(args.env, require_smtp=True)
        require_smtp_marker(args.marker)
    content = "window.ICTHUB_AUTH_CONFIG = Object.freeze({\n  registrationEnabled: %s,\n});\n" % str(enabled).lower()
    args.login_config.write_text(content, encoding="utf-8")
    os.chmod(args.login_config, 0o640)
    os.chown(args.login_config, 0, 1000)
    subprocess.run(["systemctl", "restart", "icthub-login.service"], check=True)
    print(f"Invitation registration is {'enabled' if enabled else 'disabled'}.")


def create_invitation(args):
    validate_env(args.env, require_smtp=True)
    require_smtp_marker(args.marker)
    email = args.email.strip().casefold()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ConfigError("a valid bound email address is required")
    token = api_token()
    flows = api_results(args.base_url, f"/api/v3/flows/instances/?slug={ENROLLMENT_SLUG}", token)
    if len(flows) != 1:
        raise ConfigError(f"expected one enrollment flow, found {len(flows)}")
    flow_id = flows[0].get("pk")
    expires = datetime.now(timezone.utc) + timedelta(hours=24)
    payload = {
        "name": "ICThub invitation " + datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires": expires.isoformat(),
        "single_use": True,
        "flow": flow_id,
        "fixed_data": {"email": email},
    }
    _, _, invitation = http_request(
        args.base_url.rstrip("/") + "/api/v3/stages/invitation/invitations/",
        method="POST",
        token=token,
        payload=payload,
        host="auth.icthub.top",
    )
    invitation_token = invitation.get("pk") if isinstance(invitation, dict) else None
    if not invitation_token:
        raise ConfigError("invitation API did not return a token")
    url = "https://auth.icthub.top/if/flow/%s/?itoken=%s" % (ENROLLMENT_SLUG, urllib.parse.quote(str(invitation_token), safe=""))
    print("Share this URL only with the bound recipient; it will not be shown again by this tool:")
    print(url)


def revoke_invitation(args):
    token = api_token()
    invitation_token = getpass.getpass("Invitation token to revoke: ").strip()
    if not invitation_token:
        raise ConfigError("an invitation token is required")
    path_token = urllib.parse.quote(invitation_token, safe="")
    http_request(
        args.base_url.rstrip("/") + f"/api/v3/stages/invitation/invitations/{path_token}/",
        method="DELETE",
        token=token,
        host="auth.icthub.top",
    )
    print("Invitation revoked.")


def local_health(args):
    checks = [
        ("authentik live", "http://127.0.0.1:9000/-/health/live/", "auth.icthub.top"),
        ("authentik ready", "http://127.0.0.1:9000/-/health/ready/", "auth.icthub.top"),
        ("login page", "http://127.0.0.1:8190/", "login.icthub.top"),
        ("registration page", "http://127.0.0.1:8190/", "register.icthub.top"),
    ]
    deadline = time.monotonic() + args.wait
    for name, url, host in checks:
        while True:
            try:
                status, _, _ = http_request(url, host=host, follow_redirects=False)
                if status in {200, 204, 302}:
                    print(f"{name}: HTTP {status}")
                    break
            except (ConfigError, OSError):
                status = None
            if time.monotonic() >= deadline:
                raise ConfigError(f"{name} did not become healthy; last status: {status}")
            time.sleep(2)


def public_acceptance(args):
    checks = [
        ("login", "https://login.icthub.top", {200}, None),
        ("register", "https://register.icthub.top", {200}, None),
        ("auth", "https://auth.icthub.top", {200, 302}, "not-access"),
        ("auth-admin", "https://auth-admin.icthub.top", {302, 403}, "access"),
        ("comfy", "https://comfy.icthub.top", {302, 403}, "access"),
    ]
    browser_headers = {
        "Accept": "text/html",
        "User-Agent": "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    }
    for name, url, expected, boundary in checks:
        status, headers, _ = http_request(url, follow_redirects=False, extra_headers=browser_headers)
        location = headers.get("Location", "")
        is_access = "cloudflareaccess.com" in location or "/cdn-cgi/access/" in location
        if status not in expected:
            raise ConfigError(f"{name} returned HTTP {status}, expected {sorted(expected)}")
        if boundary == "access" and not is_access:
            raise ConfigError(f"{name} is not protected by Cloudflare Access")
        if boundary == "not-access" and is_access:
            raise ConfigError("auth.icthub.top must not be protected by the Authentik-dependent Access policy")
        print(f"{name}: HTTP {status}")


def admin_mfa_audit(args):
    token = api_token()
    users = api_results(args.base_url, "/api/v3/core/users/?is_superuser=true", token)
    if not users:
        raise ConfigError("no Authentik superuser was found")
    missing = []
    for user in users:
        user_id = user.get("pk")
        devices = api_results(args.base_url, f"/api/v3/authenticators/all/?user={urllib.parse.quote(str(user_id), safe='')}", token)
        if not devices:
            missing.append(user.get("username", str(user_id)))
    if missing:
        raise ConfigError("superusers without MFA: " + ", ".join(missing))
    print(f"All {len(users)} Authentik superuser(s) have at least one MFA device.")


def parse_args():
    parser = argparse.ArgumentParser(description="Manage the ICThub Authentik deployment without storing credentials in Git.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    validate_parser.add_argument("--require-smtp", action="store_true")
    validate_parser.set_defaults(func=lambda args: (validate_env(args.env, args.require_smtp), print("Configuration is valid.")))

    health_parser = subparsers.add_parser("health")
    health_parser.add_argument("--wait", type=int, default=0, help="seconds to wait for services")
    health_parser.set_defaults(func=local_health)

    smtp_parser = subparsers.add_parser("smtp-test")
    smtp_parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    smtp_parser.add_argument("--to", required=True)
    smtp_parser.set_defaults(func=smtp_test)

    mark_parser = subparsers.add_parser("mark-smtp")
    mark_parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    mark_parser.add_argument("--marker", type=Path, default=DEFAULT_SMTP_MARKER)
    mark_parser.add_argument("--recipient", required=True)
    mark_parser.set_defaults(func=mark_smtp)

    registration_parser = subparsers.add_parser("registration")
    registration_parser.add_argument("state", choices=("enable", "disable"))
    registration_parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    registration_parser.add_argument("--marker", type=Path, default=DEFAULT_SMTP_MARKER)
    registration_parser.add_argument("--login-config", type=Path, default=DEFAULT_LOGIN_CONFIG)
    registration_parser.set_defaults(func=set_registration)

    invitation_parser = subparsers.add_parser("invite")
    invitation_subparsers = invitation_parser.add_subparsers(dest="invite_command", required=True)
    create_parser = invitation_subparsers.add_parser("create")
    create_parser.add_argument("--email", required=True)
    create_parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    create_parser.add_argument("--marker", type=Path, default=DEFAULT_SMTP_MARKER)
    create_parser.add_argument("--base-url", default="http://127.0.0.1:9000")
    create_parser.set_defaults(func=create_invitation)
    revoke_parser = invitation_subparsers.add_parser("revoke")
    revoke_parser.add_argument("--base-url", default="http://127.0.0.1:9000")
    revoke_parser.set_defaults(func=revoke_invitation)

    acceptance_parser = subparsers.add_parser("acceptance")
    acceptance_parser.set_defaults(func=public_acceptance)

    mfa_parser = subparsers.add_parser("audit-admin-mfa")
    mfa_parser.add_argument("--base-url", default="http://127.0.0.1:9000")
    mfa_parser.set_defaults(func=admin_mfa_audit)

    return parser.parse_args()


def main():
    args = parse_args()
    try:
        args.func(args)
    except (ConfigError, OSError, smtplib.SMTPException, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
