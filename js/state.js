import { loadRawState, saveRawState, clearRawState } from "./storage.js";

const DEFAULT_COLORS = ["#ff5722", "#2196f3", "#4caf50", "#ffc107", "#9c27b0", "#00bcd4"];

function uid() {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
  return "id-" + Date.now() + "-" + Math.random().toString(16).slice(2);
}

const loaded = loadRawState();

const state = {
  layers: loaded?.layers ?? [],
  segments: loaded?.segments ?? [],
  activeLayerId: loaded?.activeLayerId ?? null,
  currentSegmentId: null, // recording in progress -> not persisted across reload
};

const listeners = new Set();

function emit() {
  persist();
  for (const cb of listeners) cb(state);
}

function persist() {
  saveRawState({
    layers: state.layers,
    segments: state.segments,
    activeLayerId: state.activeLayerId,
  });
}

export function subscribe(cb) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export function getState() {
  return state;
}

export function nextDefaultColor() {
  const used = new Set(state.layers.map((l) => l.color));
  const free = DEFAULT_COLORS.find((c) => !used.has(c));
  return free ?? DEFAULT_COLORS[state.layers.length % DEFAULT_COLORS.length];
}

export function addLayer(name, color) {
  const layer = { id: uid(), name: name.trim() || "Katman", color, createdAt: Date.now() };
  state.layers.push(layer);
  if (!state.activeLayerId) state.activeLayerId = layer.id;
  emit();
  return layer;
}

export function removeLayer(id) {
  if (state.currentSegmentId) {
    const cur = state.segments.find((s) => s.id === state.currentSegmentId);
    if (cur && cur.layerId === id) return false; // kayit devam ederken silinemez
  }
  state.layers = state.layers.filter((l) => l.id !== id);
  state.segments = state.segments.filter((s) => s.layerId !== id);
  if (state.activeLayerId === id) {
    state.activeLayerId = state.layers[0]?.id ?? null;
  }
  emit();
  return true;
}

export function setActiveLayer(id) {
  state.activeLayerId = id;
  emit();
}

export function getActiveLayer() {
  return state.layers.find((l) => l.id === state.activeLayerId) ?? null;
}

export function getLayer(id) {
  return state.layers.find((l) => l.id === id) ?? null;
}

export function startSegment(layerId) {
  const segment = { id: uid(), layerId, points: [], createdAt: Date.now(), finishedAt: null };
  state.segments.push(segment);
  state.currentSegmentId = segment.id;
  emit();
  return segment;
}

export function appendPoint(segmentId, point) {
  const seg = state.segments.find((s) => s.id === segmentId);
  if (!seg) return;
  seg.points.push(point);
  emit();
}

export function finishSegment(segmentId) {
  const seg = state.segments.find((s) => s.id === segmentId);
  if (seg) seg.finishedAt = Date.now();
  if (state.currentSegmentId === segmentId) state.currentSegmentId = null;
  if (seg && seg.points.length < 2) {
    // tek nokta/bos segment - anlamsiz, temizle
    state.segments = state.segments.filter((s) => s.id !== segmentId);
  }
  emit();
}

export function getCurrentSegment() {
  return state.segments.find((s) => s.id === state.currentSegmentId) ?? null;
}

// keepCount kadar nokta birakip gerisini atar (0 ise segmenti tamamen kaldirir)
export function truncateSegmentPoints(segmentId, keepCount) {
  const seg = state.segments.find((s) => s.id === segmentId);
  if (!seg) return;
  seg.points = seg.points.slice(0, keepCount);
  if (seg.points.length === 0) {
    state.segments = state.segments.filter((s) => s.id !== segmentId);
    if (state.currentSegmentId === segmentId) state.currentSegmentId = null;
  }
  emit();
}

// bitmis bir segmentten tek bir noktayi kaldirir (2 noktanin altina duserse segment tamamen silinir)
export function removePointFromSegment(segmentId, idx) {
  const seg = state.segments.find((s) => s.id === segmentId);
  if (!seg) return;
  seg.points.splice(idx, 1);
  if (seg.points.length < 2) {
    state.segments = state.segments.filter((s) => s.id !== segmentId);
  }
  emit();
}

// iki nokta arasindaki baglantiyi keser, segmenti iki ayri cizgiye boler
export function splitSegmentAtEdge(segmentId, edgeIdx) {
  const idx = state.segments.findIndex((s) => s.id === segmentId);
  if (idx === -1) return;
  const seg = state.segments[idx];
  const firstPoints = seg.points.slice(0, edgeIdx + 1);
  const secondPoints = seg.points.slice(edgeIdx + 1);

  const replacements = [];
  if (firstPoints.length >= 2) {
    replacements.push({ id: uid(), layerId: seg.layerId, points: firstPoints, createdAt: seg.createdAt, finishedAt: Date.now() });
  }
  if (secondPoints.length >= 2) {
    replacements.push({ id: uid(), layerId: seg.layerId, points: secondPoints, createdAt: seg.createdAt, finishedAt: Date.now() });
  }
  state.segments.splice(idx, 1, ...replacements);
  emit();
}

export function clearAll() {
  state.layers = [];
  state.segments = [];
  state.activeLayerId = null;
  state.currentSegmentId = null;
  clearRawState();
  emit();
}
