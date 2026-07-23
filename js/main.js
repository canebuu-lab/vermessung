import {
  getState,
  subscribe,
  addLayer,
  removeLayer,
  setActiveLayer,
  getActiveLayer,
  startSegment,
  appendPoint,
  finishSegment,
  getCurrentSegment,
  clearAll,
  nextDefaultColor,
} from "./state.js";
import {
  initMap,
  centerOnUserOnce,
  updateUserMarker,
  drawFinishedSegment,
  clearAllSegments,
  setLivePoints,
  clearLive,
} from "./mapView.js";
import {
  startWatch,
  haversineMeters,
  MIN_POINT_DISTANCE_M,
  ACCURACY_WARN_M,
  ACCURACY_BAD_M,
} from "./gpsRecorder.js";
import { downloadDxf } from "./dxfExport.js";

// ---- DOM ----
const el = (id) => document.getElementById(id);
const btnMenu = el("btnMenu");
const btnCloseSidebar = el("btnCloseSidebar");
const sidebar = el("sidebar");
const sidebarOverlay = el("sidebarOverlay");

const layerListEl = el("layerList");
const btnAddLayer = el("btnAddLayer");
const addLayerForm = el("addLayerForm");
const newLayerName = el("newLayerName");
const newLayerColor = el("newLayerColor");
const btnCancelLayer = el("btnCancelLayer");
const btnSaveLayer = el("btnSaveLayer");

const statSegments = el("statSegments");
const statPoints = el("statPoints");
const btnExportDxf = el("btnExportDxf");
const btnClearAll = el("btnClearAll");

const gpsDot = el("gpsDot");
const gpsAccuracyText = el("gpsAccuracyText");

const activeLayerTag = el("activeLayerTag");
const btnRecord = el("btnRecord");
const recordInfo = el("recordInfo");

// ---- runtime (persist edilmeyen) durum ----
let isRecording = false;
let lastPosition = null;
let recordDistance = 0;

// ---- harita ----
initMap();

// ---- sidebar (mobil) ----
function openSidebar() {
  sidebar.classList.add("open");
  sidebarOverlay.classList.remove("hidden");
}
function closeSidebar() {
  sidebar.classList.remove("open");
  sidebarOverlay.classList.add("hidden");
}
btnMenu.addEventListener("click", openSidebar);
btnCloseSidebar.addEventListener("click", closeSidebar);
sidebarOverlay.addEventListener("click", closeSidebar);

// ---- katman ekleme formu ----
btnAddLayer.addEventListener("click", () => {
  newLayerColor.value = nextDefaultColor();
  newLayerName.value = "";
  addLayerForm.classList.remove("hidden");
  newLayerName.focus();
});
btnCancelLayer.addEventListener("click", () => {
  addLayerForm.classList.add("hidden");
});
btnSaveLayer.addEventListener("click", () => {
  const name = newLayerName.value.trim();
  if (!name) {
    newLayerName.focus();
    return;
  }
  addLayer(name, newLayerColor.value);
  addLayerForm.classList.add("hidden");
});
newLayerName.addEventListener("keydown", (e) => {
  if (e.key === "Enter") btnSaveLayer.click();
});

// ---- katman listesi render ----
function renderLayers() {
  const state = getState();
  layerListEl.innerHTML = "";

  if (state.layers.length === 0) {
    const empty = document.createElement("p");
    empty.className = "hint";
    empty.textContent = "Henuz katman yok. Once bir katman ekle (ornegin Asfalt, Toprak).";
    layerListEl.appendChild(empty);
  }

  for (const layer of state.layers) {
    const item = document.createElement("div");
    item.className = "layer-item" + (layer.id === state.activeLayerId ? " active" : "");

    const swatch = document.createElement("div");
    swatch.className = "layer-swatch";
    swatch.style.background = layer.color;

    const name = document.createElement("div");
    name.className = "layer-name";
    name.textContent = layer.name;

    const del = document.createElement("button");
    del.className = "layer-del";
    del.textContent = "✕";
    del.title = "Katmani sil";
    del.addEventListener("click", (e) => {
      e.stopPropagation();
      if (isRecording && getCurrentSegment()?.layerId === layer.id) {
        alert("Kayit devam ederken bu katman silinemez. Once kaydi durdur.");
        return;
      }
      const count = state.segments.filter((s) => s.layerId === layer.id).length;
      const msg =
        count > 0
          ? `"${layer.name}" katmaninda ${count} cizim var. Katman ve cizimler silinsin mi?`
          : `"${layer.name}" katmani silinsin mi?`;
      if (confirm(msg)) removeLayer(layer.id);
    });

    item.addEventListener("click", () => {
      if (isRecording) {
        alert("Kayit devam ederken katman degistirilemez. Once kaydi durdur.");
        return;
      }
      setActiveLayer(layer.id);
    });

    item.appendChild(swatch);
    item.appendChild(name);
    item.appendChild(del);
    layerListEl.appendChild(item);
  }
}

// ---- bitmis segmentleri haritada ciz ----
function renderSegmentsOnMap() {
  const state = getState();
  clearAllSegments();
  const layersById = new Map(state.layers.map((l) => [l.id, l]));
  for (const seg of state.segments) {
    if (seg.id === state.currentSegmentId) continue; // aktif kayit live line ile cizilir
    if (seg.points.length < 2) continue;
    const layer = layersById.get(seg.layerId);
    if (!layer) continue;
    drawFinishedSegment(seg, layer.color);
  }
}

// ---- ust bilgi / durum ----
function renderTopStatus() {
  const state = getState();
  const finished = state.segments.filter((s) => s.points.length >= 2).length;
  const totalPoints = state.segments.reduce((sum, s) => sum + s.points.length, 0);
  statSegments.textContent = String(finished);
  statPoints.textContent = String(totalPoints);

  const active = getActiveLayer();
  if (isRecording && active) {
    activeLayerTag.textContent = `● ${active.name}`;
  } else if (active) {
    activeLayerTag.textContent = active.name;
  } else {
    activeLayerTag.textContent = "Katman secilmedi";
  }

  btnRecord.disabled = !active;
}

function renderAll() {
  renderLayers();
  renderSegmentsOnMap();
  renderTopStatus();
}

subscribe(renderAll);
renderAll();

// ---- GPS durum gostergesi ----
function setGpsStatus(accuracy) {
  gpsDot.classList.remove("ok", "warn", "bad");
  if (accuracy == null) {
    gpsAccuracyText.textContent = "GPS bekleniyor…";
    return;
  }
  const rounded = accuracy.toFixed(1);
  gpsAccuracyText.textContent = `±${rounded} m`;
  if (accuracy <= ACCURACY_WARN_M) gpsDot.classList.add("ok");
  else if (accuracy <= ACCURACY_BAD_M) gpsDot.classList.add("warn");
  else gpsDot.classList.add("bad");
}

// ---- kayit bilgisi (nokta sayisi / mesafe) ----
function renderRecordInfo() {
  if (!isRecording) {
    recordInfo.textContent = "";
    return;
  }
  const seg = getCurrentSegment();
  const count = seg ? seg.points.length : 0;
  recordInfo.textContent = `${count} nokta · ${recordDistance.toFixed(1)} m`;
}

// ---- GPS izleme baslat ----
startWatch(
  (pos) => {
    setGpsStatus(pos.accuracy);
    updateUserMarker(pos.lat, pos.lng, pos.accuracy);
    centerOnUserOnce(pos.lat, pos.lng);

    if (isRecording) {
      const seg = getCurrentSegment();
      if (seg) {
        const last = seg.points[seg.points.length - 1];
        const dist = last ? haversineMeters(last.lat, last.lng, pos.lat, pos.lng) : Infinity;
        if (!last || dist >= MIN_POINT_DISTANCE_M) {
          if (last) recordDistance += dist;
          appendPoint(seg.id, pos);
          setLivePoints(seg.points, getActiveLayer()?.color ?? "#ff5722");
          renderRecordInfo();
        }
      }
    }

    lastPosition = pos;
  },
  (err) => {
    console.warn(err);
    gpsDot.classList.remove("ok", "warn");
    gpsDot.classList.add("bad");
    gpsAccuracyText.textContent =
      err.code === 1 ? "Konum izni reddedildi" : "GPS hatasi";
  }
);

// ---- kayit start/stop ----
btnRecord.addEventListener("click", () => {
  const active = getActiveLayer();
  if (!active) return;

  if (!isRecording) {
    if (!lastPosition) {
      alert("GPS konumu henuz alinamadi, birazdan tekrar dene.");
      return;
    }
    isRecording = true;
    recordDistance = 0;
    const seg = startSegment(active.id);
    appendPoint(seg.id, lastPosition);
    setLivePoints(seg.points, active.color);
    btnRecord.classList.add("recording");
    renderRecordInfo();
    renderTopStatus();
  } else {
    const seg = getCurrentSegment();
    isRecording = false;
    btnRecord.classList.remove("recording");
    clearLive();
    recordInfo.textContent = "";
    if (seg) finishSegment(seg.id);
    renderTopStatus();
  }
});

// ---- DXF export ----
btnExportDxf.addEventListener("click", () => {
  if (isRecording) {
    alert("Once devam eden kaydi durdur, sonra disa aktar.");
    return;
  }
  const state = getState();
  downloadDxf(state.layers, state.segments);
});

// ---- hepsini sil ----
btnClearAll.addEventListener("click", () => {
  if (isRecording) {
    alert("Once devam eden kaydi durdur.");
    return;
  }
  if (confirm("Tum katmanlar ve olcumler kalici olarak silinecek. Emin misin?")) {
    clearAll();
    clearAllSegments();
    clearLive();
  }
});

// ---- service worker (PWA) ----
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("sw.js").catch((e) => console.warn("SW kayit hatasi", e));
  });
}
