// Create-game form: live summaries of each game type for the chosen table size,
// and the custom rules (shown only for the Custom type).
import { hasCode } from "./share";

export type KnobValue = number | boolean;
export type Values = Record<string, KnobValue>;

export interface PresetsData {
  presets: Record<string, { players: number; label?: string; values: Record<string, Values> }>;
  stats: { label: string; knobs: string[] }[];
  custom: string;
}

/** A field as the form reports it: a checkbox state, or the text typed (maybe blank). */
export type FieldReading = boolean | string | undefined;

/** The custom game's values: what the host typed, else the base (Classic) value. */
export function customValues(base: Values, read: (name: string) => FieldReading): Values {
  const out: Values = {};
  for (const [name, fallback] of Object.entries(base)) {
    const reading = read(name);
    if (typeof fallback === "boolean") {
      out[name] = typeof reading === "boolean" ? reading : fallback;
    } else {
      const text = typeof reading === "string" ? reading.trim() : "";
      out[name] = /^\d+$/.test(text) ? Number(text) : fallback;
    }
  }
  return out;
}

/** The values of ``preset`` for ``players``, or null when the data has none.
 * The custom type starts from ``base``, the game type chosen before it. */
export function presetValues(
  data: PresetsData, preset: string, players: number, read: (name: string) => FieldReading,
  base: string = "classic",
): Values | null {
  const isCustom = preset === data.custom;
  const values = data.presets[isCustom ? base : preset]?.values[String(players)];
  if (!values) return null;
  return isCustom ? customValues(values, read) : values;
}

/** One summary line: the knobs' values joined with " / ", booleans as yes/no words. */
export function formatStat(values: Values, knobs: string[], yes: string, no: string): string {
  return knobs
    .map((k) => {
      const v = values[k];
      if (typeof v === "boolean") return v ? yes : no;
      return v === undefined ? "?" : String(v);
    })
    .join(" / ");
}

export function initCreateForm(form: HTMLFormElement, data: PresetsData): void {
  const players = form.elements.namedItem("max_players") as HTMLSelectElement | null;
  const stats = form.querySelector<HTMLElement>("#preset-stats");
  if (!players) return;
  form.classList.add("js");
  const yes = stats?.dataset.yes ?? "yes";
  const no = stats?.dataset.no ?? "no";

  const read = (name: string): FieldReading => {
    const el = form.elements.namedItem(name);
    if (!(el instanceof HTMLInputElement)) return undefined;
    return el.type === "checkbox" ? el.checked : el.value;
  };
  const chosen = (): string =>
    form.querySelector<HTMLInputElement>('input[name="preset"]:checked')?.value ?? "classic";
  const baseField = form.elements.namedItem("base");
  const base = (): string => (baseField instanceof HTMLInputElement && baseField.value) || "classic";
  const baseLabel = form.querySelector<HTMLElement>("[data-base-label]");

  const fill = (root: ParentNode, values: Values) => {
    for (const el of root.querySelectorAll<HTMLElement>("[data-knobs]")) {
      el.textContent = formatStat(values, (el.dataset.knobs ?? "").split(" "), yes, no);
    }
  };

  const render = () => {
    const code = form.elements.namedItem("config");
    form.classList.toggle("from-code", code instanceof HTMLInputElement && hasCode(code.value));
    const preset = chosen();
    const count = Number(players.value);
    form.dataset.preset = preset;
    for (const card of form.querySelectorAll<HTMLElement>("[data-card]")) {
      const name = card.dataset.card ?? "";
      card.classList.toggle("selected", name === preset);
      const values = presetValues(data, name, count, read, base());
      if (values) fill(card, values);
    }
    const values = presetValues(data, preset, count, read, base());
    if (values && stats) fill(stats, values);
    if (baseLabel) baseLabel.textContent = data.presets[base()]?.label ?? base();
    const baseValues = data.presets[base()]?.values[String(count)];
    if (baseValues) {
      for (const [name, value] of Object.entries(baseValues)) {
        const el = form.elements.namedItem(name);
        if (el instanceof HTMLInputElement && el.type !== "checkbox") el.placeholder = String(value);
      }
    }
  };

  // Yes/no rules follow the base type until the host opens Custom and changes them.
  const setBaseChecks = (values: Values | undefined) => {
    for (const [name, value] of Object.entries(values ?? {})) {
      const el = form.elements.namedItem(name);
      if (el instanceof HTMLInputElement && el.type === "checkbox" && typeof value === "boolean") el.checked = value;
    }
  };

  form.addEventListener("change", (event) => {
    const target = event.target as HTMLInputElement;
    if (target.name === "preset" && target.value !== data.custom) {
      if (baseField instanceof HTMLInputElement) baseField.value = target.value;
      setBaseChecks(data.presets[target.value]?.values[players.value]);
      const size = data.presets[target.value]?.players;
      if (size && [...players.options].some((o) => o.value === String(size))) players.value = String(size);
    }
    render();
  });
  form.addEventListener("input", render);
  render();
}
