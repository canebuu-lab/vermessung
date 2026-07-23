const KEY = "vermessung.state.v1";

export function loadRawState() {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch (e) {
    console.warn("State okunamadi, sifirlaniyor.", e);
    return null;
  }
}

export function saveRawState(state) {
  try {
    localStorage.setItem(KEY, JSON.stringify(state));
  } catch (e) {
    console.warn("State kaydedilemedi.", e);
  }
}

export function clearRawState() {
  localStorage.removeItem(KEY);
}
