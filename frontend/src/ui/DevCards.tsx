// Development cards in the HUD: the dialog that lists the player's cards and plays
// them, and the "whom to rob" chooser after a knight picks its hex.
import type { TFunction } from "i18next";
import { useState } from "preact/hooks";

import type { BuildKind, DevCard, DevCardKind, Intent, Resource } from "../protocol/types";
import { DEV_KINDS, devPlayer, plentyCount, whyNot } from "../state/devcards";
import type { GameStore } from "../state/store";
import { Dialog, useEscape } from "./Dialog";
import { ResChips, ResIcon } from "./icons";
import { RESOURCES, canAfford, costOf, errorText } from "./model";

interface Props {
  store: GameStore;
  t: TFunction;
  now: () => number;
  send: (intent: Intent) => string | null;
  /** Knight: close the dialog and let the player pick the robber's hex on the board. */
  startRobber(): void;
  onClose(): void;
}

export function DevCardsDialog({ store, t, now, send, startRobber, onClose }: Props) {
  useEscape(onClose);
  const seat = store.seat!;
  const me = devPlayer(store.state, seat);
  const cards = me?.cards ?? [];
  const [picking, setPicking] = useState<DevCardKind | null>(null);
  const [plenty, setPlenty] = useState<Resource[]>(() => Array(plentyCount(store.settings)).fill("grain"));
  const [mono, setMono] = useState<Resource>("ore");

  const play = (kind: DevCardKind) => {
    if (kind === "knight") { onClose(); startRobber(); return; }
    if (kind === "year_of_plenty" || kind === "monopoly") { setPicking(kind); return; }
    send({ a: "play_dev_card", card: kind });
    onClose();
  };

  const byKind = DEV_KINDS.map((kind) => ({ kind, list: cards.filter((c) => c.kind === kind) }))
    .filter((g) => g.list.length);
  const reason = (list: DevCard[]): string | null => {
    if (!me || !store.state) return "dev.no_card";
    const reasons = list.map((c) => whyNot(c, me, store.state!, store.settings, now()));
    return reasons.includes(null) ? null : reasons[0]!;
  };

  return (
    <Dialog title={t("hud:dev.title")} t={t} closeKey="hud:dev.close" onClose={onClose}>
      <BuyCard store={store} t={t} send={send} />
      <h3>{t("hud:dev.yours")}</h3>
      {!byKind.length && <p class="muted">{t("hud:dev.none")}</p>}
      <ul class="dev-cards">
        {byKind.map(({ kind, list }) => {
          const why = reason(list);
          return (
            <li key={kind}>
              <span class="dev-name"><strong>{t(`hud:dev.kind.${kind}`)}</strong>{list.length > 1 && <> ×{list.length}</>}</span>
              <span class="dev-help">{why ? errorText(t, why, { card: kind }) : t(`hud:dev.help.${kind}`)}</span>
              <button type="button" class="primary" disabled={why !== null} onClick={() => play(kind)}>{t("hud:dev.play")}</button>
            </li>
          );
        })}
      </ul>
      {picking === "year_of_plenty" && (
        <form class="dev-pick" onSubmit={(e) => {
          e.preventDefault();
          send({ a: "play_dev_card", card: "year_of_plenty", resources: plenty });
          onClose();
        }}>
          <p>{t("hud:dev.pickPlenty", { count: plenty.length })}</p>
          {plenty.map((r, i) => (
            <ResourcePicker key={i} t={t} value={r} onChange={(v) => setPlenty(plenty.map((x, j) => (j === i ? v : x)))} />
          ))}
          <button type="submit" class="primary">{t("hud:dev.take")}</button>
        </form>
      )}
      {picking === "monopoly" && (
        <form class="dev-pick" onSubmit={(e) => {
          e.preventDefault();
          send({ a: "play_dev_card", card: "monopoly", resource: mono });
          onClose();
        }}>
          <p>{t("hud:dev.pickMonopoly")}</p>
          <ResourcePicker t={t} value={mono} onChange={setMono} />
          <button type="submit" class="primary">{t("hud:dev.take")}</button>
        </form>
      )}
    </Dialog>
  );
}

/** Buying a development card: its cost, how many are left, and the button. */
function BuyCard({ store, t, send }: Pick<Props, "store" | "t" | "send">) {
  const seat = store.seat!;
  const hand = store.player(seat)?.hand ?? {};
  const cost = costOf(store.settings, "dev_card" as BuildKind);
  const deckLeft = store.state?.dev_cards?.deck_left ?? 0;
  const refill = (store.settings["dev_cards"] as { refill?: boolean } | undefined)?.refill !== false;
  const why = !store.player(seat)?.setup.done ? "dev.setup_not_done"
    : deckLeft <= 0 && !refill ? "dev.deck_empty"
    : !canAfford(hand, cost) ? "dev.cannot_afford" : null;
  return (
    <section class="dev-buy">
      <div class="dev-buy-info">
        <strong>{t("hud:dev.buyTitle")}</strong>
        <span class="muted">{refill ? t("hud:dev.buyHelp") : t("hud:dev.deckLeft", { count: deckLeft })}</span>
      </div>
      <ResChips res={cost} have={hand} />
      <button type="button" class="primary buy-card" disabled={why !== null} onClick={() => send({ a: "buy_dev_card" })}>
        {t("hud:dev.buyNow")}
      </button>
      {why && why !== "dev.cannot_afford" && <p class="trade-why">{errorText(t, why)}</p>}
    </section>
  );
}

function ResourcePicker({ t, value, onChange }: { t: TFunction; value: Resource; onChange(r: Resource): void }) {
  return (
    <div class="choices">
      {RESOURCES.map((r) => (
        <button key={r} type="button" aria-pressed={r === value} title={t(`hud:res.${r}`)}
                class={`card res-${r}`} onClick={() => onChange(r)}>
          <ResIcon res={r} /><span class="label">{t(`hud:res.${r}`)}</span>
        </button>
      ))}
    </div>
  );
}

export function VictimDialog({ store, t, hex, victims, send, onClose }: {
  store: GameStore; t: TFunction; hex: number; victims: number[];
  send: (intent: Intent) => string | null; onClose(): void;
}) {
  useEscape(onClose);
  return (
    <Dialog title={t("hud:dev.victimTitle")} t={t} closeKey="hud:dev.close" onClose={onClose}>
      <div class="choices">
        {victims.map((v) => (
          <button key={v} type="button" onClick={() => { send({ a: "play_dev_card", card: "knight", hex, victim: v }); onClose(); }}>
            {store.player(v)?.name ?? "?"} · {t("hud:scores.cards", { count: store.player(v)?.hand_count ?? 0 })}
          </button>
        ))}
      </div>
    </Dialog>
  );
}
