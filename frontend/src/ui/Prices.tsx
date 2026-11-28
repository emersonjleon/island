// Price list: what each purchase costs, big and easy to read (a reference card).
import type { TFunction } from "i18next";

import type { BuildKind, ResMap, Resource } from "../protocol/types";
import type { GameStore } from "../state/store";
import { ageStep, agesOn } from "../state/ages";
import { tiersOn } from "../state/devcards";
import { settlersStay } from "../state/settlers";
import { Dialog, useEscape } from "./Dialog";
import { ResIcon } from "./icons";
import { RESOURCES, canAfford, costOf } from "./model";

/** The purchases of this game, in the order of the hand bar; the megacity and the
 * settler only when the game has them. */
export function priceKinds(settings: GameStore["settings"]): BuildKind[] {
  const kinds = ["road", "settlement", "city"] as BuildKind[];
  if (megacitiesOn(settings)) kinds.push("megacity" as BuildKind);
  kinds.push("dev_card" as BuildKind);
  return settlersStay(settings) ? [...kinds, "settler" as BuildKind] : kinds;
}

function megacitiesOn(settings: GameStore["settings"]): boolean {
  const pieces = settings["pieces"] as Record<string, unknown> | undefined;
  return typeof pieces?.["megacities"] === "number" && (pieces["megacities"] as number) > 0;
}

export interface PriceRow { key: string; name: string; params?: Record<string, unknown>; cost: ResMap }

/** Every row of the price list: the purchases (with the advanced developments after the
 * first tier when the game has them), then the ages when the game has them. */
export function priceRows(settings: GameStore["settings"]): PriceRow[] {
  const rows: PriceRow[] = [];
  for (const kind of priceKinds(settings)) {
    rows.push({ key: kind, name: NAME[kind] ?? kind, cost: costOf(settings, kind) });
    if (kind === ("dev_card" as BuildKind) && tiersOn(settings)) {
      for (const tier of [2, 3]) {
        rows.push({ key: `dev_card_tier${tier}`, name: `hud:dev.tierName.${tier}`, cost: costOf(settings, `dev_card_tier${tier}` as BuildKind) });
      }
    }
  }
  if (agesOn(settings)) {
    for (const age of [2, 3]) {
      const step = ageStep(settings, age);
      if (step) rows.push({ key: `age${age}`, name: "hud:prices.age", params: { n: age === 2 ? "II" : "III" }, cost: step.cost });
    }
  }
  return rows;
}

/** The resources of a cost, one entry per card, in hand order. */
export function priceCards(cost: ResMap): Resource[] {
  return RESOURCES.flatMap((r) => Array.from({ length: cost[r] ?? 0 }, () => r));
}

const NAME: Record<string, string> = {
  road: "hud:build.road", settlement: "hud:build.settlement", city: "hud:build.city",
  megacity: "hud:prices.megacity", dev_card: "hud:dev.button", settler: "hud:settler.button",
};

export function PricesDialog({ store, t, onClose }: { store: GameStore; t: TFunction; onClose(): void }) {
  useEscape(onClose);
  const hand = store.seat !== null ? store.player(store.seat)?.hand : undefined;
  return (
    <Dialog title={t("hud:prices.title")} t={t} closeKey="hud:prices.close" onClose={onClose}>
      <table class="price-table">
        <tbody>
          {priceRows(store.settings).map(({ key, name, params, cost }) => {
            const ok = hand ? canAfford(hand, cost) : false;
            return (
              <tr key={key} class={ok ? "can" : ""}>
                <th scope="row">{t(name, params)}</th>
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
