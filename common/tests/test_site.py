import json
import tempfile
from pathlib import Path

from django.template import Context, Template
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse


def render_entry(name: str) -> str:
    return Template('{% load vite %}{% vite_entry "' + name + '" %}').render(Context())


class ViteTagTests(SimpleTestCase):
    def test_dev_server(self):
        with override_settings(VITE_DEV_SERVER="http://localhost:5173/"):
            html = render_entry("lobby")
        self.assertIn('src="http://localhost:5173/@vite/client"', html)
        self.assertIn('src="http://localhost:5173/src/entries/lobby.ts"', html)

    def test_manifest(self):
        manifest = {
            "src/entries/game.ts": {"file": "assets/game-abc.js", "css": ["assets/game-abc.css"], "imports": ["_shared"]},
            "_shared": {"file": "assets/shared-1.js", "css": ["assets/shared-1.css"]},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(json.dumps(manifest))
            with override_settings(VITE_DEV_SERVER="", VITE_MANIFEST_PATH=path):
                html = render_entry("game")
        self.assertIn('<script type="module" src="/static/dist/assets/game-abc.js"></script>', html)
        self.assertLess(html.index("shared-1.css"), html.index("game-abc.css"))

    def test_missing_build_renders_comment(self):
        with override_settings(VITE_DEV_SERVER="", VITE_MANIFEST_PATH="/nonexistent/manifest.json"):
            self.assertEqual(render_entry("game"), "<!-- vite entry game not built -->")


class SiteTests(TestCase):
    def test_home_renders(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Ages of the Island")
        self.assertContains(response, reverse("accounts:signup"))

    def test_asgi_application_loads(self):
        from config.asgi import application

        self.assertIn("websocket", application.application_mapping)
