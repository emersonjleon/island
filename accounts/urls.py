from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

app_name = "accounts"


def _tpl(name: str) -> str:
    return f"accounts/{name}.html"


urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("login/", auth_views.LoginView.as_view(template_name=_tpl("login"), redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("profile/", views.profile, name="profile"),
    path("language/", views.set_language, name="set_language"),
    path("keybindings/", views.keybindings, name="keybindings"),
    path(
        "password/change/",
        auth_views.PasswordChangeView.as_view(
            template_name=_tpl("password_change"), success_url=reverse_lazy("accounts:password_change_done")
        ),
        name="password_change",
    ),
    path(
        "password/change/done/",
        auth_views.PasswordChangeDoneView.as_view(template_name=_tpl("password_change_done")),
        name="password_change_done",
    ),
    path(
        "password/reset/",
        auth_views.PasswordResetView.as_view(
            template_name=_tpl("password_reset"),
            email_template_name="accounts/password_reset_email.txt",
            subject_template_name="accounts/password_reset_subject.txt",
            success_url=reverse_lazy("accounts:password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "password/reset/done/",
        auth_views.PasswordResetDoneView.as_view(template_name=_tpl("password_reset_done")),
        name="password_reset_done",
    ),
    path(
        "password/reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name=_tpl("password_reset_confirm"), success_url=reverse_lazy("accounts:password_reset_complete")
        ),
        name="password_reset_confirm",
    ),
    path(
        "password/reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(template_name=_tpl("password_reset_complete")),
        name="password_reset_complete",
    ),
]
