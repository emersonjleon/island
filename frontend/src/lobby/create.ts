// Create-game form: live summaries of each game type for the chosen table size,
// and the custom rules (shown only for the Custom type).

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

/** Placeholders of the "all settings" inputs for each base game type, by input name. */
export interface EditorData {
  placeholders: Record<string, Record<string, string>>;
}

/** The text of a select's "keep" option: the base type's choice in brackets. */
export function keepText(options: { value: string; text: string }[], base: string | undefined): string {
  const chosen = options.find((o) => o.value !== "" && o.value === base);
  return chosen ? `(${chosen.text})` : "–";
}

function fillEditor(form: HTMLFormElement, placeholders: Record<string, string> | undefined): void {
  if (!placeholders) return;
  for (const el of form.querySelectorAll<HTMLInputElement | HTMLSelectElement>("[data-setting]")) {
    const base = placeholders[el.name];
    if (el instanceof HTMLSelectElement) {
      const keep = el.options[0];
      if (keep) keep.text = keepText([...el.options].map((o) => ({ value: o.value, text: o.text })), base);
    } else if (base !== undefined) {
      el.placeholder = base;
    }
  }
}

export function initCreateForm(form: HTMLFormElement, data: PresetsData, editor?: EditorData): void {
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
    const preset = chosen();
    const count = Number(players.value);
    form.dataset.preset = preset;
    for (const card of form.querySelectorAll<HTMLElement>("[data-card]")) {
      const name = card.dataset.card ?? "";
      card.classList.toggle("selected", name === preset);
      // Only the chosen card follows the table size; the others keep their own numbers.
      const own = data.presets[name === data.custom ? base() : name]?.players ?? count;
      const values = presetValues(data, name, name === preset ? count : own, read, base());
      if (values) fill(card, values);
    }
    const values = presetValues(data, preset, count, read, base());
    if (values && stats) fill(stats, values);
    if (baseLabel) baseLabel.textContent = data.presets[base()]?.label ?? base();
    fillEditor(form, editor?.placeholders[base()]);
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

  const statsBox = form.querySelector<HTMLDetailsElement>("#stats-box");
  // "Start from" chips in Custom: every game type a custom game can start from.
  const buttons = [...form.querySelectorAll<HTMLButtonElement>("[data-base-choice]")];

  const setBase = (name: string, followSize: boolean) => {
    if (baseField instanceof HTMLInputElement) baseField.value = name;
    setBaseChecks(data.presets[name]?.values[players.value]);
    const seats = data.presets[name]?.players;
    if (followSize && seats && [...players.options].some((o) => o.value === String(seats))) {
      players.value = String(seats);
    }
    for (const b of buttons) {
      const on = b.dataset.baseChoice === name;
      b.classList.toggle("selected", on);
      b.setAttribute("aria-pressed", String(on));
    }
  };

  for (const button of buttons) {
    button.addEventListener("click", () => {
      setBase(button.dataset.baseChoice ?? "classic", true);
      render();
    });
  }

  form.addEventListener("change", (event) => {
    const target = event.target as HTMLInputElement;
    if (target.name === "preset") {
      if (statsBox) statsBox.open = target.value === data.custom;
      if (target.value !== data.custom) setBase(target.value, true);
    }
    render();
  });
  form.addEventListener("input", render);
  form.addEventListener("keydown", (event) => onEnter(form, event));
  render();
}

/** Enter in the "save as" box saves the settings instead of creating the game. */
export function savesOnEnter(key: string, inputName: string | undefined): boolean {
  return key === "Enter" && inputName === "save_name";
}

function onEnter(form: HTMLFormElement, event: KeyboardEvent): void {
  const target = event.target as HTMLInputElement | null;
  const save = form.querySelector<HTMLButtonElement>('button[name="save_as"]');
  if (!save || !savesOnEnter(event.key, target?.name)) return;
  event.preventDefault();
  form.requestSubmit(save);
}
