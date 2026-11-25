// The in-game guide for new players: a small panel under the dice clock with the
// next step (setup) or a tip (later), and a "How to play" dialog with the rules
// and controls. Numbers come from the game's settings, never from the code.
import type { TFunction } from "i18next";
import { useState } from "preact/hooks";

import type { BuildKind, ResMap } from "../protocol/types";
import type { GameStore } from "../state/store";
import { Dialog, useEscape } from "./Dialog";
import { guideStep, type GuideStep } from "./guide";
import { costOf, formatRes, rollInterval, victoryTarget } from "./model";

const HIDDEN_KEY = "island.guide.hidden";

function readHidden(): boolean {
  try {
    return window.localStorage.getItem(HIDDEN_KEY) === "1";
  } catch {
    return false;
  }
}

function writeHidden(hidden: boolean): void {
  try {
    if (hidden) window.localStorage.setItem(HIDDEN_KEY, "1");
    else window.localStorage.removeItem(HIDDEN_KEY);
  } catch {
    // Private windows may refuse storage: the guide simply shows again next time.
  }
}

function num(settings: Record<string, unknown>, group: string, ...path: string[]): number | undefined {
  let cur: unknown = settings[group];
  for (const k of path) cur = cur && typeof cur === "object" ? (cur as Record<string, unknown>)[k] : undefined;
  return typeof cur === "number" ? cur : undefined;
}

/** Values the guide and help texts interpolate (costs, target, ratios). */
export function ruleParams(t: TFunction, settings: Record<string, unknown>): Record<string, unknown> {
  const cost = (kind: string) => formatRes(t, costOf(settings, kind as BuildKind));
  return {
    road: cost("road"), settlement: cost("settlement"), city: cost("city"), card: cost("dev_card"),
    target: victoryTarget(settings) ?? 10,
    seconds: Math.round((rollInterval(settings) ?? 20000) / 1000),
    limit: num(settings, "robber", "card_limit") ?? 7,
    ratio: num(settings, "economy", "trade", "bank_ratio") ?? 4,
    age2: formatRes(t, ageCost(settings, "age2")), age3: formatRes(t, ageCost(settings, "age3")),
    population: num(settings, "settlers", "largest_population", "points") ?? 2,
  };
}

function ageCost(settings: Record<string, unknown>, slot: "age2" | "age3"): ResMap | undefined {
  const ages = settings["ages"] as Record<string, Record<string, unknown>> | undefined;
  return ages?.[slot]?.["cost"] as ResMap | undefined;
}

/** The help lines for the variations this game plays (ages, settlers, fog, hidden numbers). */
export function variantHelpKeys(settings: Record<string, unknown>): string[] {
  const group = (name: string) => (settings[name] ?? {}) as Record<string, unknown>;
  const ages = group("ages")["enabled"] === true;
  const settlers = group("settlers")["leave_after_setup"] === false;
  const vis = group("visibility");
  const keys: string[] = [];
  if (ages) keys.push("ages");
  if (settlers) keys.push("settlers");
  if (settlers) keys.push("population");
  if (vis["map"] && vis["map"] !== "open") keys.push("fog");
  if (vis["hidden_numbers"] === true) keys.push("numbers");
  return keys;
}

function stepText(t: TFunction, step: GuideStep, params: Record<string, unknown>): string {
  switch (step.key) {
    case "tip": return t(`hud:guide.tips.${step.tip}`, params);
    case "building": return t("hud:guide.building", { kind: t(`hud:build.${step.kind}`).toLowerCase() });
    case "wait_clock": return t("hud:guide.wait_clock");
    default: return t(`hud:guide.${step.key}`, { step: step.step, total: step.total });
  }
}

export function GuidePanel({ store, t, touch, onHelp }: { store: GameStore; t: TFunction; touch: boolean; onHelp(): void }) {
  const [hidden, setHidden] = useState(readHidden);
  const s = store.state;
  const step = s ? guideStep(s, store.seat, store.settings) : null;
  const toggle = (value: boolean) => { setHidden(value); writeHidden(value); };
  if (hidden || !step) {
    return (
      <div class="hud-guide-buttons">
        {step && <button type="button" onClick={() => toggle(false)}>{t("hud:guide.show")}</button>}
        <button type="button" class="help-open" onClick={onHelp} aria-label={t("hud:guide.help")} title={t("hud:guide.help")}>?</button>
      </div>
    );
  }
  const setup = step.key === "setup_settlement" || step.key === "setup_road";
  return (
    <div class="hud-panel hud-guide" role="status" aria-live="polite">
      <header>
        <h2>{t("hud:guide.title")}</h2>
        <button type="button" class="quiet help-open" onClick={onHelp} aria-label={t("hud:guide.help")} title={t("hud:guide.help")}>?</button>
        <button type="button" class="quiet" onClick={() => toggle(true)} aria-label={t("hud:guide.hide")} title={t("hud:guide.hide")}>×</button>
      </header>
      <p>{stepText(t, step, ruleParams(t, store.settings))}</p>
      {setup && <p class="controls">{t(touch ? "hud:guide.touch" : "hud:guide.keys")}</p>}
    </div>
  );
}

export function HelpDialog({ store, t, touch, helpUrl, onClose }: {
  store: GameStore; t: TFunction; touch: boolean; helpUrl: string; onClose(): void;
}) {
  useEscape(onClose);
  const p = ruleParams(t, store.settings);
  return (
    <Dialog title={t("hud:help.title")} t={t} closeKey="hud:help.close" onClose={onClose}>
      <ul class="help-rules">
        {(["goal", "dice", "setup", "build", "robber", "trade", "cards"] as const).map((k) => <li key={k}>{t(`hud:help.${k}`, p)}</li>)}
      </ul>
      {variantHelpKeys(store.settings).length > 0 && <>
        <h3>{t("hud:help.variants")}</h3>
        <ul class="help-rules">
          {variantHelpKeys(store.settings).map((k) => <li key={k}>{t(`hud:help.v.${k}`, p)}</li>)}
        </ul>
      </>}
      <h3>{t("hud:help.controls")}</h3>
      <p>{t(touch ? "hud:help.touch" : "hud:help.keys")}</p>
      <p><a href={helpUrl} target="_blank" rel="noopener">{t("hud:help.full")}</a></p>
    </Dialog>
  );
}
