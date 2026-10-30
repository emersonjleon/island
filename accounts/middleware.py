from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.middleware.locale import LocaleMiddleware
from django.utils import translation


class UserLocaleMiddleware(LocaleMiddleware):
    """LocaleMiddleware that prefers a signed-in user's saved language.

    Anonymous visitors get Django's normal cookie / Accept-Language detection.
    Must come after AuthenticationMiddleware.
    """

    def process_request(self, request: HttpRequest) -> None:
        user = getattr(request, "user", None)
        language = getattr(user, "preferred_language", "") if user and user.is_authenticated else ""
        if language and language in dict(settings.LANGUAGES):
            translation.activate(language)
            request.LANGUAGE_CODE = translation.get_language()
            return
        super().process_request(request)

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        response = super().process_response(request, response)
        language = getattr(request, "LANGUAGE_CODE", "")
        user = getattr(request, "user", None)
        if (
            user
            and user.is_authenticated
            and language
            and settings.LANGUAGE_COOKIE_NAME not in response.cookies
            and request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME) != language
        ):
            # Keep the cookie in step so the language survives logout.
            response.set_cookie(
                settings.LANGUAGE_COOKIE_NAME,
                language,
                max_age=settings.LANGUAGE_COOKIE_AGE,
                path=settings.LANGUAGE_COOKIE_PATH,
                samesite=settings.LANGUAGE_COOKIE_SAMESITE,
            )
        return response
