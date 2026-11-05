"""Database side of the game host (synchronous ORM; the runner calls it through threads)."""
from django.db import transaction
from django.utils import timezone

from engine import codec
from engine import game as engine
from engine.settings import GameSettings
from engine.sim.runner import CommandRecord, resume
from engine.state import SeatInfo
from lobby.models import Game, GamePlayer, GameStatus

from . import conf
from .core import GameCore
from .models import GameCommand, GameSnapshot


def seats_for(game: Game) -> list[SeatInfo]:
    players = game.players.select_related("user").exclude(seat=None).order_by("seat")
    return [SeatInfo(seat=p.seat, user_id=p.user_id, name=p.user.public_name, colour=p.colour) for p in players]


def create_core(game: Game) -> GameCore:
    """Build the initial state of a STARTING game, store the start snapshot and set RUNNING."""
    settings = GameSettings.model_validate(game.settings)
    state, _events = engine.new_game(settings, seats_for(game), game.seed)
    core = GameCore(game.pk, state)
    with transaction.atomic():
        save_snapshot(core, GameSnapshot.Kind.START)
        Game.objects.filter(pk=game.pk).update(status=GameStatus.RUNNING, started_at=timezone.now())
    return core


def restore_core(game: Game) -> GameCore:
    """Latest snapshot plus the commands logged after it (deterministic replay)."""
    snap = GameSnapshot.objects.filter(game=game).order_by("-cmd_seq", "-id").first()
    if snap is None:
        raise LookupError(f"game {game.code} has no snapshot")
    rows = list(GameCommand.objects.filter(game=game, cmd_seq__gt=snap.cmd_seq).order_by("cmd_seq"))
    state = resume(snap.state, [CommandRecord(r.game_ms, r.seat, r.payload) for r in rows])
    cmd_seq = rows[-1].cmd_seq if rows else snap.cmd_seq
    return GameCore(game.pk, state, cmd_seq=cmd_seq, seqs=dict(snap.seqs))


def flush_commands(core: GameCore) -> int:
    pending = core.take_pending()
    GameCommand.objects.bulk_create(
        GameCommand(game_id=core.game_id, cmd_seq=n, game_ms=rec.at, seat=rec.seat, payload=rec.payload)
        for n, rec in pending
    )
    return len(pending)


@transaction.atomic
def save_snapshot(core: GameCore, kind: str) -> GameSnapshot:
    flush_commands(core)
    snap = GameSnapshot.objects.create(
        game_id=core.game_id, kind=kind, cmd_seq=core.cmd_seq, game_ms=core.state.now_ms,
        state=codec.dump(core.state), state_hash=codec.state_hash(core.state), seqs=dict(core.seqs),
    )
    core.rolls_since_snapshot = 0
    keep = conf.get("SNAPSHOTS_KEPT")
    old = GameSnapshot.objects.filter(game_id=core.game_id).order_by("-cmd_seq", "-id").values_list("id", flat=True)[keep:]
    GameSnapshot.objects.filter(id__in=list(old)).delete()
    return snap


@transaction.atomic
def finish_game(core: GameCore) -> None:
    """Write results to the seats, the final snapshot, and status FINISHED."""
    save_snapshot(core, GameSnapshot.Kind.END)
    state = core.state
    for p in state.players:
        GamePlayer.objects.filter(game_id=core.game_id, seat=p.seat).update(
            final_points=p.points, is_winner=(p.seat == state.winner)
        )
    Game.objects.filter(pk=core.game_id).update(status=GameStatus.FINISHED, finished_at=timezone.now())


def abort_game(game_id: int) -> None:
    Game.objects.filter(pk=game_id, status=GameStatus.STARTING).update(status=GameStatus.ABORTED)


def games_to_take() -> tuple[list[int], list[int]]:
    """(STARTING game ids, RUNNING game ids) the host should own."""
    starting = list(Game.objects.filter(status=GameStatus.STARTING).values_list("id", flat=True))
    running = list(Game.objects.filter(status=GameStatus.RUNNING).values_list("id", flat=True))
    return starting, running


def get_game(game_id: int) -> Game | None:
    return Game.objects.filter(pk=game_id).first()
