import argparse
import contextlib
import http.client
import importlib.util
import io
import re
import threading
import unittest
from unittest import mock
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
AUTHENTIK = ROOT / "deploy" / "authentik"
LOGIN = ROOT / "deploy" / "login-page"


class BlueprintLoader(yaml.SafeLoader):
    pass


def tagged(loader, suffix, node):
    if isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node)
    elif isinstance(node, yaml.MappingNode):
        value = loader.construct_mapping(node)
    else:
        value = loader.construct_scalar(node)
    return {"tag": suffix, "value": value}


BlueprintLoader.add_multi_constructor("!", tagged)


def load_yaml(path, loader=yaml.SafeLoader):
    return yaml.load(path.read_text(encoding="utf-8"), Loader=loader)


def entries_by_model(blueprint, model):
    return [entry for entry in blueprint["entries"] if entry["model"] == model]


class LoginPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("icthub_login_server", LOGIN / "server.py")
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)
        manage_spec = importlib.util.spec_from_file_location("icthub_manage", AUTHENTIK / "manage.py")
        cls.manage = importlib.util.module_from_spec(manage_spec)
        manage_spec.loader.exec_module(cls.manage)
        cls.log = io.StringIO()
        cls.module.sys.stderr = cls.log
        handler = partial(cls.module.LoginPageHandler, directory=str(LOGIN))
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join()

    def request(self, path, host):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1])
        connection.request("GET", path, headers={"Host": host})
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        headers = dict(response.getheaders())
        connection.close()
        return response.status, headers, body

    def test_host_routes_and_security_headers(self):
        status, headers, body = self.request("/", "login.icthub.top")
        self.assertEqual(status, 200)
        self.assertIn("登录工作台", body)
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")

        status, _, body = self.request("/", "register.icthub.top")
        self.assertEqual(status, 200)
        self.assertIn("使用邀请码注册", body)

    def test_non_public_files_are_not_served_and_queries_are_redacted(self):
        status, _, _ = self.request("/README.md", "login.icthub.top")
        self.assertEqual(status, 404)
        token = "secret-invitation-token"
        status, _, _ = self.request(f"/?itoken={token}", "register.icthub.top")
        self.assertEqual(status, 200)
        self.assertNotIn(token, self.log.getvalue())

    def test_health_helper_accepts_html_pages(self):
        url = f"http://127.0.0.1:{self.server.server_address[1]}/"
        status, _, body = self.manage.http_request(
            url,
            host="login.icthub.top",
            follow_redirects=False,
            extra_headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
        )
        self.assertEqual(status, 200)
        self.assertIsInstance(body, bytes)

    def test_invitation_name_is_slug_safe(self):
        captured = {}

        def request(*args, **kwargs):
            captured.update(kwargs["payload"])
            return 201, {}, {"pk": "invitation-token"}

        args = argparse.Namespace(
            env=Path("/unused/env"),
            marker=Path("/unused/marker"),
            email="Test+Invite@Example.com",
            base_url="http://127.0.0.1:9000",
        )
        with (
            mock.patch.object(self.manage, "validate_env"),
            mock.patch.object(self.manage, "require_smtp_marker"),
            mock.patch.object(self.manage, "api_token", return_value="api-token"),
            mock.patch.object(self.manage, "api_results", return_value=[{"pk": "flow-id"}]),
            mock.patch.object(self.manage, "http_request", side_effect=request),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.manage.create_invitation(args)

        self.assertRegex(captured["name"], re.compile(r"^[a-z0-9-]+$"))
        self.assertTrue(captured["single_use"])
        self.assertEqual(captured["fixed_data"], {"email": "test+invite@example.com"})

    def test_registration_is_disabled_by_default(self):
        runtime_config = (LOGIN / "runtime-config.js").read_text(encoding="utf-8")
        registration = (LOGIN / "register.html").read_text(encoding="utf-8")
        self.assertIn("registrationEnabled: false", runtime_config)
        self.assertIn('name="itoken"', registration)
        self.assertIn("disabled", registration)
        self.assertNotIn('type="password"', registration)
        self.assertIn("https://auth.icthub.top/if/flow/icthub-invitation-enrollment/", registration)

    def test_return_path_requires_the_comfy_origin(self):
        app = (LOGIN / "app.js").read_text(encoding="utf-8")
        self.assertIn('destination.origin === "https://comfy.icthub.top"', app)
        self.assertNotIn("localStorage", app)
        self.assertNotIn("sessionStorage", app)


class AuthentikDeploymentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compose = load_yaml(AUTHENTIK / "compose.yml")
        cls.blueprint = load_yaml(AUTHENTIK / "blueprints" / "icthub-auth.yaml", BlueprintLoader)

    def test_compose_is_fixed_and_loopback_only(self):
        services = self.compose["services"]
        self.assertEqual(set(services), {"postgresql", "server", "worker"})
        self.assertEqual(services["server"]["image"], "ghcr.io/goauthentik/server:2026.5.5")
        self.assertEqual(services["worker"]["image"], "ghcr.io/goauthentik/server:2026.5.5")
        self.assertEqual(services["postgresql"]["image"], "postgres:16.11-alpine")
        self.assertEqual(services["server"]["ports"], ["127.0.0.1:9000:9000"])
        self.assertNotIn("ports", services["postgresql"])
        self.assertNotIn("/var/run/docker.sock", (AUTHENTIK / "compose.yml").read_text(encoding="utf-8"))
        self.assertEqual(services["server"]["environment"]["AUTHENTIK_LOG_LEVEL"], "warning")
        self.assertEqual(services["worker"]["environment"]["AUTHENTIK_LOG_LEVEL"], "warning")

    def test_installer_preserves_bind_mount_directories(self):
        installer = (AUTHENTIK / "install.sh").read_text(encoding="utf-8")
        self.assertIn("for mounted_dir in blueprints custom-templates media", installer)
        for name in ("blueprints", "custom-templates", "media"):
            self.assertIn(f"! -name {name}", installer)

    def test_enrollment_is_invitation_only_and_email_gated(self):
        invitation = entries_by_model(self.blueprint, "authentik_stages_invitation.invitationstage")[0]
        self.assertFalse(invitation["attrs"]["continue_flow_without_invitation"])
        user_write = entries_by_model(self.blueprint, "authentik_stages_user_write.userwritestage")[0]
        self.assertTrue(user_write["attrs"]["create_users_as_inactive"])
        self.assertEqual(user_write["attrs"]["user_type"], "internal")
        email = entries_by_model(self.blueprint, "authentik_stages_email.emailstage")[0]
        self.assertTrue(email["attrs"]["activate_user_on_success"])
        login = entries_by_model(self.blueprint, "authentik_stages_user_login.userloginstage")[0]
        self.assertEqual(login["attrs"]["session_duration"], "days=30")
        prompts = entries_by_model(self.blueprint, "authentik_stages_prompt.prompt")
        self.assertTrue(all(set(prompt["identifiers"]) == {"name"} for prompt in prompts))
        email_prompt = next(prompt for prompt in prompts if prompt["attrs"]["field_key"] == "email")
        self.assertEqual(email_prompt["attrs"]["type"], "hidden")
        bindings = entries_by_model(self.blueprint, "authentik_flows.flowstagebinding")
        self.assertEqual([binding["identifiers"]["order"] for binding in bindings], [10, 20, 30, 40, 50])
        self.assertTrue(bindings[0]["attrs"]["evaluate_on_plan"])

    def test_password_and_group_policies(self):
        password = entries_by_model(self.blueprint, "authentik_policies_password.passwordpolicy")[0]
        self.assertGreaterEqual(password["attrs"]["length_min"], 12)
        self.assertTrue(password["attrs"]["error_message"])
        self.assertFalse(password["attrs"]["check_have_i_been_pwned"])
        expressions = "\n".join(
            entry["attrs"]["expression"]
            for entry in entries_by_model(self.blueprint, "authentik_policies_expression.expressionpolicy")
        )
        self.assertIn('email = str(data.get("email"', expressions)
        self.assertNotIn('request.context.get("invitation")', expressions)
        self.assertIn('Group.objects.get(name="comfy-users")', expressions)
        self.assertIn('filter(name="comfy-users")', expressions)
        self.assertNotIn("ak_groups", (AUTHENTIK / "blueprints" / "icthub-auth.yaml").read_text(encoding="utf-8"))

    def test_brand_media_paths_are_authentik_relative(self):
        brands = entries_by_model(self.blueprint, "authentik_brands.brand")
        for brand in brands:
            self.assertFalse(brand["attrs"]["default"])
            self.assertEqual(brand["attrs"]["branding_logo"], "icthub/logo.svg")
            self.assertEqual(brand["attrs"]["branding_favicon"], "icthub/favicon.svg")
            self.assertEqual(
                brand["attrs"]["branding_custom_css"],
                {"tag": "File", "value": "/data/media/public/icthub/brand.css"},
            )

    def test_oidc_redirect_is_strict_and_secret_is_external(self):
        provider = entries_by_model(self.blueprint, "authentik_providers_oauth2.oauth2provider")[0]
        self.assertEqual(provider["attrs"]["redirect_uris"][0]["matching_mode"], "strict")
        self.assertEqual(provider["attrs"]["grant_types"], ["authorization_code"])
        self.assertEqual(provider["attrs"]["client_secret"]["tag"], "Env")
        env_example = (AUTHENTIK / "authentik.env.example").read_text(encoding="utf-8")
        self.assertIn("GENERATE_A_RANDOM_OIDC_CLIENT_SECRET", env_example)
        self.assertNotRegex(env_example, r"(?i)(password|secret)=([A-Za-z0-9+/]{32,})")

    def test_tunnel_contains_all_boundaries(self):
        tunnel = load_yaml(LOGIN / "cloudflared-config.yml")
        hosts = [entry.get("hostname") for entry in tunnel["ingress"] if "hostname" in entry]
        self.assertEqual(
            hosts,
            ["login.icthub.top", "register.icthub.top", "auth.icthub.top", "auth-admin.icthub.top", "comfy.icthub.top"],
        )
        services = {entry.get("hostname"): entry["service"] for entry in tunnel["ingress"] if "hostname" in entry}
        self.assertEqual(services["auth.icthub.top"], "http://127.0.0.1:9000")
        self.assertEqual(services["auth-admin.icthub.top"], "http://127.0.0.1:9000")
        origins = {entry.get("hostname"): entry.get("originRequest", {}) for entry in tunnel["ingress"] if "hostname" in entry}
        self.assertEqual(origins["register.icthub.top"]["httpHostHeader"], "register.icthub.top")
        self.assertEqual(origins["auth-admin.icthub.top"]["httpHostHeader"], "auth-admin.icthub.top")


if __name__ == "__main__":
    unittest.main()
