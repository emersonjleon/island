// Development cards in the HUD: the dialog that lists the player's cards and plays
// them, and the "whom to rob" chooser after a knight picks its hex.
import type { TFunction } from "i18next";
import { useState } from "preact/hooks";

import type { BuildKind, DevCard, DevCardKind, Intent, Resource } from "../protocol/types";
import { agePlayer } from "../state/ages";
import { DEV_KINDS, KNIGHT_KINDS, TIERS, architectCount, cardHelpValues, devPlayer, harvestRule, plentyCount, tierCostKey,
  tiersOn, whyNot } from "../state/devcards";
import type { GameStore } from "../state/store";
import { Dialog, useEscape } from "./Dialog";
import { ResChips, ResIcon } from "./icons";
import { RESOURCES, canAfford, costOf, errorText } from "./model";

interface Props {
  store: GameStore;
  t: TFunction;
  now: () => number;
  send: (intent: Intent) => string | null;
  /** Knight (or veteran / elite knight): close the dialog and let the player pick the robber's hex on the board. */
  startRobber(card: DevCardKind): void;
  onClose(): void;
}

export function DevCardsDialog({ store, t, now, send, startRobber, onClose }: Props) {
  useEscape(onClose);
  const seat = store.seat!;
  const me = devPlayer(store.state, seat);
  const cards = me?.cards ?? [];
  const [picking, setPicking] = useState<DevCardKind | null>(null);
  const [plenty, setPlenty] = useState<Resource[]>(() => Array(plentyCount(store.settings)).fill("grain"));
  const harvest = harvestRule(store.settings);
  const [crop, setCrop] = useState<Resource[]>(() => Array(harvest.count).fill("grain"));
  const [discount, setDiscount] = useState<Resource[]>(() => Array(architectCount(store.settings)).fill("ore"));
  const [mono, setMono] = useState<Resource>("ore");
  const cropFish = crop.filter((r) => r === "fish").length;

  const play = (kind: DevCardKind) => {
    if (KNIGHT_KINDS.includes(kind)) { onClose(); startRobber(kind); return; }
    if (kind === "year_of_plenty" || kind === "monopoly" || kind === "bountiful_harvest" || kind === "architect") {
      setPicking(kind);
      return;
    }
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
              <span class="dev-help">{why ? errorText(t, why, { card: kind }) : t(`hud:dev.help.${kind}`, cardHelpValues(store.settings, kind))}</span>
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
      {picking === "bountiful_harvest" && (
        <form class="dev-pick" onSubmit={(e) => {
          e.preventDefault();
          send({ a: "play_dev_card", card: "bountiful_harvest", resources: crop });
          onClose();
        }}>
          <p>{t("hud:dev.pickHarvest", { count: crop.length, fish: harvest.fish })}</p>
          {crop.map((r, i) => (
            <ResourcePicker key={i} t={t} value={r} onChange={(v) => setCrop(crop.map((x, j) => (j === i ? v : x)))} />
          ))}
          {cropFish > harvest.fish && <p class="trade-why">{errorText(t, "dev.too_much_fish", { max: harvest.fish })}</p>}
          <button type="submit" class="primary" disabled={cropFish > harvest.fish}>{t("hud:dev.take")}</button>
        </form>
      )}
      {picking === "architect" && (
        <form class="dev-pick" onSubmit={(e) => {
          e.preventDefault();
          send({ a: "play_dev_card", card: "architect", resources: discount });
          onClose();
        }}>
          <p>{t("hud:dev.pickArchitect", { count: discount.length })}</p>
          {discount.map((r, i) => (
            <ResourcePicker key={i} t={t} value={r} noFish onChange={(v) => setDiscount(discount.map((x, j) => (j === i ? v : x)))} />
          ))}
          <button type="submit" class="primary">{t("hud:dev.play")}</button>
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

/** Buying development cards: one row per tier the game has (advanced developments with
 * ages), each with its cost and button; a tier above the player's age is locked. */
function BuyCard({ store, t, send }: Pick<Props, "store" | "t" | "send">) {
  const tiers = tiersOn(store.settings) ? TIERS : [1];
  return <>{tiers.map((tier) => <BuyTier key={tier} store={store} t={t} send={send} tier={tier} many={tiers.length > 1} />)}</>;
}

function BuyTier({ store, t, send, tier, many }: Pick<Props, "store" | "t" | "send"> & { tier: number; many: boolean }) {
  const seat = store.seat!;
  const hand = store.player(seat)?.hand ?? {};
  const cost = costOf(store.settings, tierCostKey(tier) as BuildKind);
  const view = store.state?.dev_cards;
  const deckLeft = tier === 1 ? view?.deck_left ?? 0 : view?.decks_left?.[String(tier)] ?? 0;
  const refill = (store.settings["dev_cards"] as { refill?: boolean } | undefined)?.refill !== false;
  const age = agePlayer(store.state, seat).age;
  const why = tier > age ? "dev.tier_locked"
    : !store.player(seat)?.setup.done ? "dev.setup_not_done"
    : deckLeft <= 0 && !refill ? "dev.deck_empty"
    : !canAfford(hand, cost) ? "dev.cannot_afford" : null;
  const title = many ? t(`hud:dev.tierName.${tier}`) : t("hud:dev.buyTitle");
  const help = many ? t(`hud:dev.tierHelp.${tier}`) : t("hud:dev.buyHelp");
  return (
    <section class={`dev-buy dev-tier-${tier}`}>
      <div class="dev-buy-info">
        <strong>{title}</strong>
        <span class="muted">{refill ? help : t("hud:dev.deckLeft", { count: deckLeft })}</span>
      </div>
      <ResChips res={cost} have={hand} />
      <button type="button" class="primary buy-card" disabled={why !== null}
              onClick={() => send(tier === 1 ? { a: "buy_dev_card" } : { a: "buy_dev_card", tier })}>
        {why === "dev.tier_locked" ? t("hud:dev.tierLocked", { n: ["I", "II", "III"][tier - 1] }) : t("hud:dev.buyNow")}
      </button>
      {why && why !== "dev.cannot_afford" && why !== "dev.tier_locked" && <p class="trade-why">{errorText(t, why)}</p>}
    </section>
  );
}

function ResourcePicker({ t, value, onChange, noFish }: { t: TFunction; value: Resource; onChange(r: Resource): void; noFish?: boolean }) {
  return (
    <div class="choices">
      {RESOURCES.filter((r) => !noFish || r !== "fish").map((r) => (
        <button key={r} type="button" aria-pressed={r === value} title={t(`hud:res.${r}`)}
                class={`card res-${r}`} onClick={() => onChange(r)}>
          <ResIcon res={r} /><span class="label">{t(`hud:res.${r}`)}</span>
        </button>
      ))}
    </div>
  );
}

export function VictimDialog({ store, t, hex, victims, card = "knight", send, onClose }: {
  store: GameStore; t: TFunction; hex: number; victims: number[]; card?: DevCardKind;
  send: (intent: Intent) => string | null; onClose(): void;
}) {
  useEscape(onClose);
  return (
    <Dialog title={t("hud:dev.victimTitle")} t={t} closeKey="hud:dev.close" onClose={onClose}>
      <div class="choices">
        {victims.map((v) => (
          <button key={v} type="button" onClick={() => { send({ a: "play_dev_card", card, hex, victim: v }); onClose(); }}>
            {store.player(v)?.name ?? "?"} · {t("hud:scores.cards", { count: store.player(v)?.hand_count ?? 0 })}
          </button>
        ))}
      </div>
    </Dialog>
  );
}
