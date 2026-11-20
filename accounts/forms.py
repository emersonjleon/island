from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils.translation import get_language, get_supported_language_variant

from .models import User


class SignUpForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "display_name", "preferred_language")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
        if not self.is_bound:
            # The full code: "zh-hans" must stay "zh-hans", and "en-us" becomes "en".
            self.fields["preferred_language"].initial = get_supported_language_variant(get_language() or "en")


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("display_name", "email", "preferred_language")
