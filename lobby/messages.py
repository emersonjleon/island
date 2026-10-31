from django.utils.translation import gettext_lazy as _

ERROR_MESSAGES = {
    "lobby.unknown_preset": _("That preset does not exist."),
    "lobby.invalid_settings": _("These settings are not valid together."),
    "lobby.board_impossible": _("An island cannot be generated with these settings."),
    "lobby.not_open": _("This game is no longer open."),
    "lobby.not_joined": _("You are not in this game."),
    "lobby.full": _("This game is full."),
    "lobby.bad_colour": _("Unknown colour."),
    "lobby.colour_taken": _("Another player already has that colour."),
    "lobby.not_host": _("Only the host can do that."),
    "lobby.too_few_players": _("More players need to join first."),
    "lobby.not_all_ready": _("Every player must be ready first."),
}


def error_message(code: str):
    return ERROR_MESSAGES.get(code, _("That action was refused."))
