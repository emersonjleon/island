import json

from django.conf import settings
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from accounts.keybindings import KeybindingsError, validate_keybindings
from accounts.models import User

PASSWORD = "tidal-basalt-91"


def make_user(username: str = "ana", **extra) -> User:
    return User.objects.create_user(username, f"{username}@example.com", PASSWORD, **extra)


class SignUpTests(TestCase):
    def test_signup_creates_user_and_logs_in(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "username": "ana",
                "email": "ana@example.com",
                "display_name": "Ana",
                "preferred_language": "es",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )
        self.assertRedirects(response, reverse("home"))
        user = User.objects.get(username="ana")
        self.assertEqual(user.display_name, "Ana")
        self.assertEqual(user.preferred_language, "es")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_signup_requires_email(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {"username": "ana", "email": "", "preferred_language": "en", "password1": PASSWORD, "password2": PASSWORD},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_signup_defaults_language_to_current(self):
        response = self.client.get(reverse("accounts:signup"), HTTP_ACCEPT_LANGUAGE="es")
        self.assertEqual(response.context["form"].fields["preferred_language"].initial, "es")

    def test_signed_in_user_is_redirected_away_from_signup(self):
        self.client.force_login(make_user())
        self.assertRedirects(self.client.get(reverse("accounts:signup")), reverse("home"))


class LoginLogoutTests(TestCase):
    def test_login_and_logout(self):
        make_user()
        response = self.client.post(reverse("accounts:login"), {"username": "ana", "password": PASSWORD})
        self.assertRedirects(response, reverse("home"))
        self.assertIn("_auth_user_id", self.client.session)
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("home"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_honours_next(self):
        make_user()
        target = reverse("accounts:profile")
        response = self.client.post(
            reverse("accounts:login") + f"?next={target}", {"username": "ana", "password": PASSWORD, "next": target}
        )
        self.assertRedirects(response, target)

    def test_profile_requires_login(self):
        response = self.client.get(reverse("accounts:profile"))
        self.assertRedirects(response, reverse("accounts:login") + "?next=" + reverse("accounts:profile"))


class PasswordResetTests(TestCase):
    def test_reset_flow(self):
        user = make_user()
        response = self.client.post(reverse("accounts:password_reset"), {"email": "ana@example.com"})
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        link = next(line for line in mail.outbox[0].body.splitlines() if "/password/reset/" in line)
        path = link.split("testserver", 1)[1]
        response = self.client.get(path, follow=True)
        self.assertTrue(response.context["validlink"])
        new = "coral-reef-meadow-7"
        response = self.client.post(response.redirect_chain[-1][0], {"new_password1": new, "new_password2": new})
        self.assertRedirects(response, reverse("accounts:password_reset_complete"))
        user.refresh_from_db()
        self.assertTrue(user.check_password(new))

    def test_unknown_email_sends_nothing(self):
        self.client.post(reverse("accounts:password_reset"), {"email": "nobody@example.com"})
        self.assertEqual(len(mail.outbox), 0)


class ProfileTests(TestCase):
    def test_edit_profile(self):
        user = make_user()
        self.client.force_login(user)
        response = self.client.post(
            reverse("accounts:profile"),
            {"display_name": "Capitana", "email": "new@example.com", "preferred_language": "es"},
        )
        self.assertRedirects(response, reverse("accounts:profile"))
        user.refresh_from_db()
        self.assertEqual((user.display_name, user.email, user.preferred_language), ("Capitana", "new@example.com", "es"))

    def test_public_name_falls_back_to_username(self):
        self.assertEqual(make_user().public_name, "ana")
        self.assertEqual(make_user("bo", display_name="Bo!").public_name, "Bo!")


class LanguageTests(TestCase):
    def test_signed_in_user_gets_saved_language(self):
        self.client.force_login(make_user(preferred_language="es"))
        response = self.client.get(reverse("home"), HTTP_ACCEPT_LANGUAGE="en")
        self.assertContains(response, '<html lang="es">')
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME].value, "es")

    def test_anonymous_uses_accept_language(self):
        response = self.client.get(reverse("home"), HTTP_ACCEPT_LANGUAGE="es")
        self.assertContains(response, '<html lang="es">')

    def test_switcher_saves_preference_for_signed_in_user(self):
        user = make_user()
        self.client.force_login(user)
        response = self.client.post(reverse("accounts:set_language"), {"language": "es", "next": "/"})
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        user.refresh_from_db()
        self.assertEqual(user.preferred_language, "es")
        self.assertContains(self.client.get("/"), '<html lang="es">')

    def test_switcher_for_anonymous_sets_cookie(self):
        response = self.client.post(reverse("accounts:set_language"), {"language": "es", "next": "/"})
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME].value, "es")

    def test_switcher_ignores_unknown_language(self):
        user = make_user()
        self.client.force_login(user)
        self.client.post(reverse("accounts:set_language"), {"language": "xx", "next": "/"})
        user.refresh_from_db()
        self.assertEqual(user.preferred_language, "en")


class KeybindingsEndpointTests(TestCase):
    url = reverse("accounts:keybindings")

    def put(self, body):
        data = body if isinstance(body, (bytes, str)) else json.dumps(body)
        return self.client.put(self.url, data, content_type="application/json")

    def test_requires_login(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_get_put_roundtrip(self):
        user = make_user()
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.url).json(), {"keybindings": {}})
        bindings = {"build_road": ["KeyR"], "camera_pan_up": ["Shift+KeyW", "ArrowUp"]}
        response = self.put({"keybindings": bindings})
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.keybindings, bindings)
        self.assertEqual(self.client.get(self.url).json(), {"keybindings": bindings})

    def test_rejects_bad_payloads(self):
        self.client.force_login(make_user())
        self.assertEqual(self.put(b"{not json").json(), {"error": "keybindings.bad_json"})
        self.assertEqual(self.put({"keybindings": []}).json(), {"error": "keybindings.not_object"})
        self.assertEqual(self.put({"keybindings": {"Bad Name": ["KeyA"]}}).json(), {"error": "keybindings.bad_action"})
        self.assertEqual(self.put({"keybindings": {"ok": "KeyA"}}).json(), {"error": "keybindings.bad_combos"})
        self.assertEqual(self.put({"keybindings": {"ok": ["<script>"]}}).json(), {"error": "keybindings.bad_combo"})
        self.assertEqual(self.put(b"x" * (17 * 1024)).status_code, 413)

    def test_csrf_is_enforced(self):
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        client.force_login(make_user())
        response = client.put(self.url, json.dumps({"keybindings": {}}), content_type="application/json")
        self.assertEqual(response.status_code, 403)

    def test_post_not_allowed(self):
        self.client.force_login(make_user())
        self.assertEqual(self.client.post(self.url).status_code, 405)


class KeybindingsValidatorTests(TestCase):
    def test_limits(self):
        with self.assertRaises(KeybindingsError):
            validate_keybindings({f"a{i}": [] for i in range(101)})
        with self.assertRaises(KeybindingsError):
            validate_keybindings({"a": ["KeyA"] * 5})
        self.assertEqual(validate_keybindings({"select_index_1": ["Digit1"]}), {"select_index_1": ["Digit1"]})


class SpanishCatalogueTests(TestCase):
    def test_pages_render_in_spanish(self):
        response = self.client.get(reverse("accounts:login"), HTTP_ACCEPT_LANGUAGE="es")
        self.assertContains(response, "Iniciar sesión")
        self.assertContains(response, "¿Olvidaste tu contraseña?")
