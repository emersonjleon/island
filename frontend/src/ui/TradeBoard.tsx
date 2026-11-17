// The player trade board in the Trade dialog: open offers (accept or withdraw) and a
// form to post a new one. Offers stay up until someone takes them, their poster
// withdraws them or, when the game says so, they expire.
import type { TFunction } from "i18next";
import { useState } from "preact/hooks";

import type { Intent, ResMap, Resource, TradeOffer } from "../protocol/types";
import { playerColour } from "../render2d/palette";
import type { GameStore } from "../state/store";
import { compact, offersOf, whyNotAccept, whyNotPost } from "../state/tradeboard";
import { ResChips, ResIcon, TradeArrow } from "./icons";
import { RESOURCES, errorText, formatRes } from "./model";

interface Props {
  store: GameStore;
  t: TFunction;
  now: () => number;
  send: (intent: Intent) => string | null;
}

export function TradeBoard({ store, t, now, send }: Props) {
  const s = store.state!;
  const seat = store.seat!;
  const hand = store.player(seat)?.hand ?? {};
  const [give, setGive] = useState<ResMap>({});
  const [get, setGet] = useState<ResMap>({});
  const why = whyNotPost(s, seat, store.settings, give, get);
  const offers = offersOf(s);

  const post = () => {
    send({ a: "post_offer", give: compact(give), get: compact(get) });
    setGive({});
    setGet({});
  };

  return (
    <div class="trade-board">
      <h3>{t("hud:offers.open")}</h3>
      {!offers.length && <p class="muted">{t("hud:offers.none")}</p>}
      <ul class="offers">
        {offers.map((o) => <OfferRow key={o.id} store={store} t={t} now={now} send={send} offer={o} />)}
      </ul>
      <h3>{t("hud:offers.new")}</h3>
      <div class="offer-form">
        <Counter t={t} label={t("hud:offers.youGive")} value={give} onChange={setGive} have={hand} side="give" />
        <TradeArrow />
        <Counter t={t} label={t("hud:offers.youGet")} value={get} onChange={setGet} side="get" />
      </div>
      {why && why !== "offer.empty" && <p class="trade-why">{errorText(t, why)}</p>}
      <div class="dialog-buttons">
        <button type="button" class="primary post-offer" disabled={why !== null} onClick={post}>
          {t("hud:offers.post")}
        </button>
      </div>
    </div>
  );
}

function OfferRow({ store, t, now, send, offer }: Props & { offer: TradeOffer }) {
  const seat = store.seat!;
  const mine = offer.seat === seat;
  const who = mine ? t("hud:you") : store.player(offer.seat)?.name ?? "?";
  const why = mine ? null : whyNotAccept(store.state!, seat, offer);
  const left = offer.expires_at === null ? null : Math.max(0, Math.ceil((offer.expires_at - now()) / 1000));
  // Seen from the viewer: what they would hand over on the left, what they would get on the right.
  const youGive = mine ? offer.give : offer.get;
  const youGet = mine ? offer.get : offer.give;
  const hand = store.player(seat)?.hand ?? {};
  const colour = store.player(offer.seat)?.colour;
  return (
    <li class={`offer seat-${offer.seat}${mine ? " mine" : ""}`}
        aria-label={t("hud:offers.line", { who, give: formatRes(t, offer.give), get: formatRes(t, offer.get) })}>
      <span class="offer-who">
        {colour && <span class="swatch" style={{ background: `#${playerColour(colour).toString(16).padStart(6, "0")}` }} />}
        <strong>{who}</strong>
        {left !== null && <small>{t("hud:offers.left", { count: left })}</small>}
      </span>
      <span class="offer-deal">
        <span class="offer-part"><small>{t("hud:offers.youGive")}</small><ResChips res={youGive} have={mine ? undefined : hand} /></span>
        <TradeArrow small />
        <span class="offer-part"><small>{t("hud:offers.youGet")}</small><ResChips res={youGet} /></span>
      </span>
      {why && <small class="trade-why">{errorText(t, why)}</small>}
      {mine
        ? <button type="button" class="cancel-offer" onClick={() => send({ a: "cancel_offer", offer: offer.id })}>
            {t("hud:offers.withdraw")}
          </button>
        : <button type="button" class="primary accept-offer" disabled={why !== null}
                  onClick={() => send({ a: "accept_offer", offer: offer.id })}>
            {t("hud:offers.accept")}
          </button>}
    </li>
  );
}

function Counter({ t, label, value, onChange, have, side }: {
  t: TFunction; label: string; value: ResMap; onChange(m: ResMap): void; have?: ResMap; side: "give" | "get";
}) {
  const set = (r: Resource, n: number) => onChange({ ...value, [r]: Math.max(0, n) });
  return (
    <fieldset class={`offer-side ${side}`}>
      <legend>{label}</legend>
      {RESOURCES.map((r) => {
        const n = value[r] ?? 0;
        const max = have ? have[r] ?? 0 : Infinity;
        return (
          <div key={r} class={`offer-res res-${r}${n > 0 ? " picked" : ""}`}>
            <ResIcon res={r} />
            <span class="label">{t(`hud:res.${r}`)}</span>
            <button type="button" aria-label={t("hud:offers.less", { res: t(`hud:res.${r}`) })}
                    disabled={n === 0} onClick={() => set(r, n - 1)}>−</button>
            <span class="count">{n}</span>
            <button type="button" aria-label={t("hud:offers.more", { res: t(`hud:res.${r}`) })}
                    disabled={n >= max} onClick={() => set(r, n + 1)}>+</button>
          </div>
        );
      })}
    </fieldset>
  );
}
