// Key settings screen: rebind any action, see conflicts, reset, save to the account.
import type { TFunction } from "i18next";
import { useEffect, useState } from "preact/hooks";

import { ACTIONS, type Action, type Bindings, DEFAULT_BINDINGS, comboOf, conflicts, saveBindings } from "../input/bindings";
import { Dialog, useEscape } from "./Dialog";
import { prettyCombo } from "./model";

const MODIFIER_CODES = new Set(["ShiftLeft", "ShiftRight", "ControlLeft", "ControlRight", "AltLeft", "AltRight", "MetaLeft", "MetaRight"]);
const MAX_COMBOS = 4;

export function KeySettings(props: { t: TFunction; bindings: Bindings; csrfToken: string; onChange(b: Bindings): void; onClose(): void }) {
  const { t } = props;
  const [b, setB] = useState<Bindings>(props.bindings);
  const [listening, setListening] = useState<Action | null>(null);
  const [saved, setSaved] = useState<"" | "ok" | "local">("");
  useEscape(listening ? () => setListening(null) : props.onClose);

  useEffect(() => {
    if (!listening) return;
    const onKey = (e: KeyboardEvent) => {
      if (MODIFIER_CODES.has(e.code) || e.code === "Escape") return;
      e.preventDefault();
      e.stopImmediatePropagation();
      const combo = comboOf(e);
      setB((old) => {
        const list = old[listening].includes(combo) ? old[listening] : [...old[listening], combo].slice(-MAX_COMBOS);
        const next = { ...old, [listening]: list };
        props.onChange(next);
        return next;
      });
      setSaved("");
      setListening(null);
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [listening]);

  const update = (next: Bindings) => { setB(next); props.onChange(next); setSaved(""); };
  const clash = conflicts(b);
  return (
    <Dialog title={t("hud:keys.title")} onClose={props.onClose} t={t} closeKey="hud:keys.close">
      <table class="keys">
        <tbody>
          {ACTIONS.map((a) => (
            <tr key={a}>
              <th scope="row">{t(`hud:action.${a}`)}</th>
              <td>
                {b[a].map((c) => (
                  <span key={c} class={`key${clash.has(c) ? " clash" : ""}`}
                        title={clash.has(c) ? t("hud:keys.conflict", { actions: clash.get(c)!.map((x) => t(`hud:action.${x}`)).join(", ") }) : undefined}>
                    {prettyCombo(c)}
                    <button type="button" class="quiet" aria-label={t("hud:keys.remove", { key: prettyCombo(c) })}
                            onClick={() => update({ ...b, [a]: b[a].filter((x) => x !== c) })}>×</button>
                  </span>
                ))}
                <button type="button" class="quiet add" onClick={() => setListening(a)}>
                  {listening === a ? t("hud:keys.press") : t("hud:keys.add")}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div class="dialog-buttons">
        <span class="saved">{saved === "ok" ? t("hud:keys.saved") : saved === "local" ? t("hud:keys.saveFailed") : ""}</span>
        <button type="button" onClick={() => update({ ...DEFAULT_BINDINGS })}>{t("hud:keys.reset")}</button>
        <button type="button" class="primary" onClick={async () => setSaved((await saveBindings(b, props.csrfToken)) ? "ok" : "local")}>
          {t("hud:keys.save")}
        </button>
      </div>
    </Dialog>
  );
}
