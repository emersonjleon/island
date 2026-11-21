// Price list: what each purchase costs, big and easy to read (a reference card).
import type { TFunction } from "i18next";

import type { BuildKind, ResMap, Resource } from "../protocol/types";
import type { GameStore } from "../state/store";
import { settlersStay } from "../state/settlers";
import { Dialog, useEscape } from "./Dialog";
import { ResIcon } from "./icons";
import { RESOURCES, canAfford, costOf } from "./model";

/** The purchases of this game, in the order of the hand bar (settler last, when the game has them). */
export function priceKinds(settings: GameStore["settings"]): BuildKind[] {
  const kinds = ["road", "settlement", "city", "dev_card"] as BuildKind[];
  return settlersStay(settings) ? [...kinds, "settler" as BuildKind] : kinds;
}

/** The resources of a cost, one entry per card, in hand order. */
export function priceCards(cost: ResMap): Resource[] {
  return RESOURCES.flatMap((r) => Array.from({ length: cost[r] ?? 0 }, () => r));
}

const NAME: Record<string, string> = {
  road: "hud:build.road", settlement: "hud:build.settlement", city: "hud:build.city",
  dev_card: "hud:dev.button", settler: "hud:settler.button",
};

export function PricesDialog({ store, t, onClose }: { store: GameStore; t: TFunction; onClose(): void }) {
  useEscape(onClose);
  const hand = store.seat !== null ? store.player(store.seat)?.hand : undefined;
  return (
    <Dialog title={t("hud:prices.title")} t={t} closeKey="hud:prices.close" onClose={onClose}>
      <table class="price-table">
        <tbody>
          {priceKinds(store.settings).map((kind) => {
            const cost = costOf(store.settings, kind);
            const ok = hand ? canAfford(hand, cost) : false;
            return (
              <tr key={kind} class={ok ? "can" : ""}>
                <th scope="row">{t(NAME[kind] ?? kind)}</th>
                <td>
                  <span class="price-cards" aria-label={priceCards(cost).map((r) => t(`hud:res.${r}`)).join(", ")}>
                    {priceCards(cost).map((r, i) => <span key={i} class={`price-card res-${r}`}><ResIcon res={r} size={22} /></span>)}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p class="help">{t("hud:prices.help")}</p>
    </Dialog>
  );
}
