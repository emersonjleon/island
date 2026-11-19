from django.utils.translation import gettext_lazy as _

ERROR_MESSAGES = {
    "lobby.unknown_preset": _("That preset does not exist."),
    "lobby.invalid_settings": _("These settings are not valid together."),
    "lobby.board_impossible": _("An island cannot be generated with these settings."),
    "lobby.not_open": _("This game is no longer open."),
    "lobby.not_joined": _("You are not in this game."),
    "lobby.not_finished": _("This game has not finished yet."),
    "lobby.full": _("This game is full."),
    "lobby.bad_colour": _("Unknown colour."),
    "lobby.colour_taken": _("Another player already has that colour."),
    "lobby.not_host": _("Only the host can do that."),
    "lobby.too_few_players": _("More players need to join first."),
    "lobby.not_all_ready": _("Every player must be ready first."),
    "lobby.bad_bot_level": _("Unknown bot level."),
    "lobby.no_such_bot": _("That bot is no longer in the game."),
    "lobby.too_many_seated": _("More players are seated than these settings allow."),
    "lobby.saved_needs_name": _("Give the settings a name."),
    "lobby.saved_too_many": _("You have too many saved settings. Delete one first."),
    "lobby.no_such_saved": _("Those saved settings no longer exist."),
    "lobby.code_malformed": _("That settings code is not complete or not valid. Copy it again."),
    "lobby.code_too_long": _("That settings code is too long."),
    "lobby.code_too_new": _("That settings code was made by a newer version of the game."),
    "lobby.code_unknown_preset": _("That settings code uses a game type this server does not have."),
}


def error_message(code: str):
    return ERROR_MESSAGES.get(code, _("That action was refused."))


# Settings that do not fit together (codes of engine.settings validation errors).
VALIDATION_MESSAGES = {
    "settings.players.min_gt_max": _("More players are needed to start than fit at the table."),
    "settings.board.too_small_for_players": _("The island is too small for this many players."),
    "settings.setup.exceeds_pieces": _("The first settlements and roads need more pieces than a player has."),
    "settings.economy.bank_too_small": _("The bank cannot pay every player's starting materials."),
    "settings.board.token_out_of_range": _("Some number tokens cannot be rolled with these dice."),
    "settings.dev_cards.cooldown_ms_missing": _("Give the seconds between developments."),
    "settings.later_stage": _("This option is not available yet."),
}


def validation_message(code: str):
    return VALIDATION_MESSAGES.get(code, _("This value does not fit with the other settings."))
