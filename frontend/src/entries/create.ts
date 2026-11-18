// Lobby list entry: the create-game form.
import { initCreateForm, type EditorData, type PresetsData } from "../lobby/create";

const form = document.getElementById("create-game");
const script = document.getElementById("presets-data");
if (form instanceof HTMLFormElement && script?.textContent) {
  const editor = document.getElementById("editor-data")?.textContent;
  initCreateForm(form, JSON.parse(script.textContent) as PresetsData, editor ? (JSON.parse(editor) as EditorData) : undefined);
}
