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
  deleteSegment,
  truncateSegmentPoints,
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

const SAMPLE_WINDOW_MS = 3000; // nokta eklerken ortalamasi alinacak son okuma penceresi
const MARKER_SMOOTHING = 0.35; // haritadaki konum noktasi titremesini azaltmak icin (0-1)

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
const btnFinishLine = el("btnFinishLine");
const btnSwitchLayer = el("btnSwitchLayer");
const recordInfo = el("recordInfo");
const toast = el("toast");

const layerPickerOverlay = el("layerPickerOverlay");
const layerPickerList = el("layerPickerList");
const btnClosePicker = el("btnClosePicker");

// ---- runtime (persist edilmeyen) durum ----
let lastPosition = null; // en son ham GPS okumasi (marker/durum icin)
let recentSamples = []; // nokta eklerken ortalama almak icin son okumalar
let smoothedMarkerPos = null; // haritadaki mavi nokta icin yumusatilmis konum
let recordDistance = 0;

function isLineInProgress() {
  return getCurrentSegment() != null;
}

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
      if (isLineInProgress() && getCurrentSegment()?.layerId === layer.id) {
        alert("Devam eden cizgi bu katmanda. Once 'Bitir' ile cizgiyi tamamla.");
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
      if (layer.id === state.activeLayerId) return;
      if (isLineInProgress()) {
        finishCurrentLine();
      }
      setActiveLayer(layer.id);
    });

    item.appendChild(swatch);
    item.appendChild(name);
    item.appendChild(del);
    layerListEl.appendChild(item);
  }
}

// ---- bitmis bir cizgiye tiklaninca komple sil ----
function handleDeleteFinishedSegment(segmentId) {
  const state = getState();
  const seg = state.segments.find((s) => s.id === segmentId);
  if (!seg) return;
  const layer = state.layers.find((l) => l.id === seg.layerId);
  const name = layer ? layer.name : "bilinmeyen katman";
  if (confirm(`"${name}" katmanindaki bu cizgi tamamen silinsin mi? (${seg.points.length} nokta)`)) {
    deleteSegment(segmentId);
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
    drawFinishedSegment(seg, layer.color, handleDeleteFinishedSegment);
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
  const lineActive = isLineInProgress();
  if (lineActive && active) {
    activeLayerTag.textContent = `● ${active.name}`;
  } else if (active) {
    activeLayerTag.textContent = active.name;
  } else {
    activeLayerTag.textContent = "Katman secilmedi";
  }

  btnRecord.disabled = !active;
  btnRecord.classList.toggle("recording", lineActive);
  btnFinishLine.disabled = !lineActive;
  btnSwitchLayer.disabled = state.layers.length === 0;
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
  if (!isLineInProgress()) {
    recordInfo.textContent = "";
    return;
  }
  const seg = getCurrentSegment();
  const count = seg ? seg.points.length : 0;
  recordInfo.textContent = `${count} nokta · ${recordDistance.toFixed(1)} m`;
}

// ---- son GPS okumalarinin ortalamasini alarak daha stabil bir nokta uret ----
function getAveragedPosition() {
  if (recentSamples.length === 0) return lastPosition;
  const sum = recentSamples.reduce(
    (acc, p) => {
      acc.lat += p.lat;
      acc.lng += p.lng;
      acc.accuracy = Math.min(acc.accuracy, p.accuracy ?? Infinity);
      return acc;
    },
    { lat: 0, lng: 0, accuracy: Infinity }
  );
  const n = recentSamples.length;
  return {
    lat: sum.lat / n,
    lng: sum.lng / n,
    alt: recentSamples[recentSamples.length - 1].alt,
    accuracy: sum.accuracy,
    t: Date.now(),
  };
}

// ---- GPS izleme baslat (harita ustundeki konum + durum gostergesi icin surekli) ----
startWatch(
  (pos) => {
    setGpsStatus(pos.accuracy);

    const now = Date.now();
    recentSamples.push(pos);
    recentSamples = recentSamples.filter((p) => now - (p.t ?? now) < SAMPLE_WINDOW_MS);

    if (!smoothedMarkerPos) {
      smoothedMarkerPos = { lat: pos.lat, lng: pos.lng };
    } else {
      smoothedMarkerPos.lat += (pos.lat - smoothedMarkerPos.lat) * MARKER_SMOOTHING;
      smoothedMarkerPos.lng += (pos.lng - smoothedMarkerPos.lng) * MARKER_SMOOTHING;
    }
    updateUserMarker(smoothedMarkerPos.lat, smoothedMarkerPos.lng, pos.accuracy);
    centerOnUserOnce(pos.lat, pos.lng);

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

// ---- cizgiyi tamamla ----
function finishCurrentLine() {
  const seg = getCurrentSegment();
  if (!seg) return;
  clearLive();
  recordInfo.textContent = "";
  finishSegment(seg.id);
  renderTopStatus();
}

// ---- kisa bilgi baloncugu ----
let toastTimer = null;
function showToast(message) {
  toast.textContent = message;
  toast.classList.remove("hidden");
  requestAnimationFrame(() => toast.classList.add("show"));
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => toast.classList.add("hidden"), 250);
  }, 1500);
}

// ---- hizli katman degistirme popup'i ----
function openLayerPicker() {
  const state = getState();
  layerPickerList.innerHTML = "";
  for (const layer of state.layers) {
    const item = document.createElement("div");
    item.className = "layer-picker-item" + (layer.id === state.activeLayerId ? " active" : "");

    const swatch = document.createElement("div");
    swatch.className = "layer-swatch";
    swatch.style.background = layer.color;

    const name = document.createElement("div");
    name.textContent = layer.name;

    item.appendChild(swatch);
    item.appendChild(name);
    item.addEventListener("click", () => {
      if (layer.id !== state.activeLayerId) {
        if (isLineInProgress()) finishCurrentLine();
        setActiveLayer(layer.id);
      }
      closeLayerPicker();
    });
    layerPickerList.appendChild(item);
  }
  layerPickerOverlay.classList.remove("hidden");
}
function closeLayerPicker() {
  layerPickerOverlay.classList.add("hidden");
}
btnSwitchLayer.addEventListener("click", openLayerPicker);
btnClosePicker.addEventListener("click", closeLayerPicker);
layerPickerOverlay.addEventListener("click", (e) => {
  if (e.target === layerPickerOverlay) closeLayerPicker();
});

// ---- aktif cizginin toplam mesafesini noktalardan yeniden hesapla ----
function recalcRecordDistance(points) {
  let dist = 0;
  for (let i = 1; i < points.length; i++) {
    dist += haversineMeters(points[i - 1].lat, points[i - 1].lng, points[i].lat, points[i].lng);
  }
  return dist;
}

// ---- aktif cizginin bir noktasina tiklaninca o noktadan sonrasini sil ----
function handleDeleteVertex(segmentId, idx) {
  const seg = getCurrentSegment();
  if (!seg || seg.id !== segmentId) return;

  const removedCount = seg.points.length - idx;
  if (removedCount > 1) {
    if (!confirm(`Son ${removedCount} nokta silinecek. Emin misin?`)) return;
  }

  truncateSegmentPoints(segmentId, idx);
  const updated = getCurrentSegment();

  if (updated && updated.points.length > 0) {
    recordDistance = recalcRecordDistance(updated.points);
    setLivePoints(updated.points, getActiveLayer()?.color ?? "#ff5722", (i) =>
      handleDeleteVertex(updated.id, i)
    );
  } else {
    clearLive();
    recordDistance = 0;
  }

  renderRecordInfo();
  renderTopStatus();
}

// ---- + : aktif katmana nokta ekle (onceki nokta varsa duz cizgiyle baglar) ----
btnRecord.addEventListener("click", () => {
  const active = getActiveLayer();
  if (!active) return;

  const point = getAveragedPosition();
  if (!point) {
    alert("GPS konumu henuz alinamadi, birazdan tekrar dene.");
    return;
  }

  let seg = getCurrentSegment();
  if (!seg) {
    recordDistance = 0;
    seg = startSegment(active.id);
  } else {
    const last = seg.points[seg.points.length - 1];
    const dist = haversineMeters(last.lat, last.lng, point.lat, point.lng);
    if (dist < MIN_POINT_DISTANCE_M) {
      alert("Bu nokta oncekiyle neredeyse ayni yerde, biraz hareket edip tekrar dene.");
      return;
    }
    recordDistance += dist;
  }

  appendPoint(seg.id, point);
  setLivePoints(seg.points, active.color, (idx) => handleDeleteVertex(seg.id, idx));
  renderRecordInfo();
  renderTopStatus();
});

// ---- Bitir ve Kaydet: mevcut cizgiyi kapatir (veri zaten surekli localStorage'a yazilir) ----
btnFinishLine.addEventListener("click", () => {
  finishCurrentLine();
  showToast("Kaydedildi ✓");
});

// ---- DXF export ----
btnExportDxf.addEventListener("click", () => {
  if (isLineInProgress()) {
    alert("Once 'Bitir' ile devam eden cizgiyi tamamla, sonra disa aktar.");
    return;
  }
  const state = getState();
  downloadDxf(state.layers, state.segments);
});

// ---- hepsini sil ----
btnClearAll.addEventListener("click", () => {
  if (isLineInProgress()) {
    alert("Once 'Bitir' ile devam eden cizgiyi tamamla.");
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
