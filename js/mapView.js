let map;
let segmentLayers = new Map(); // segmentId -> L.LayerGroup
let liveLine = null;
let liveVertexMarkers = [];
let userMarker = null;
let userAccuracyCircle = null;
let hasCenteredOnUser = false;

export function initMap() {
  map = L.map("map", { zoomControl: true }).setView([51.1657, 10.4515], 6);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 20,
    attribution: "&copy; OpenStreetMap katkida bulunanlar",
  }).addTo(map);

  return map;
}

export function getMap() {
  return map;
}

export function centerOnUserOnce(lat, lng, zoom = 19) {
  if (hasCenteredOnUser) return;
  hasCenteredOnUser = true;
  map.setView([lat, lng], zoom);
}

export function updateUserMarker(lat, lng, accuracy) {
  if (!userMarker) {
    userMarker = L.circleMarker([lat, lng], {
      radius: 7,
      color: "#38bdf8",
      weight: 2,
      fillColor: "#38bdf8",
      fillOpacity: 0.9,
    }).addTo(map);
  } else {
    userMarker.setLatLng([lat, lng]);
  }

  if (accuracy && accuracy > 0) {
    if (!userAccuracyCircle) {
      userAccuracyCircle = L.circle([lat, lng], {
        radius: accuracy,
        color: "#38bdf8",
        weight: 1,
        fillColor: "#38bdf8",
        fillOpacity: 0.08,
      }).addTo(map);
    } else {
      userAccuracyCircle.setLatLng([lat, lng]);
      userAccuracyCircle.setRadius(accuracy);
    }
  }
}

function latLngsFromPoints(points) {
  return points.map((p) => [p.lat, p.lng]);
}

export function drawFinishedSegment(segment, color, onClick) {
  const existing = segmentLayers.get(segment.id);
  if (existing) map.removeLayer(existing);
  if (segment.points.length < 2) return;

  const latlngs = latLngsFromPoints(segment.points);
  const group = L.layerGroup().addTo(map);
  // dokunma alanini genisletmek icin gorunmez kalin bir "hit" cizgisi
  const hitLine = L.polyline(latlngs, { color, weight: 22, opacity: 0 }).addTo(group);
  const visibleLine = L.polyline(latlngs, { color, weight: 4, opacity: 0.9 }).addTo(group);

  if (onClick) {
    const handler = (e) => {
      L.DomEvent.stopPropagation(e);
      onClick(segment.id);
    };
    hitLine.on("click", handler);
    visibleLine.on("click", handler);
  }

  segmentLayers.set(segment.id, group);
}

export function removeSegment(segmentId) {
  const existing = segmentLayers.get(segmentId);
  if (existing) {
    map.removeLayer(existing);
    segmentLayers.delete(segmentId);
  }
}

export function clearAllSegments() {
  for (const line of segmentLayers.values()) map.removeLayer(line);
  segmentLayers.clear();
}

export function setLivePoints(points, color, onVertexClick) {
  const latlngs = latLngsFromPoints(points);
  if (!liveLine) {
    liveLine = L.polyline(latlngs, {
      color,
      weight: 5,
      opacity: 0.95,
      dashArray: "1 8",
      lineCap: "round",
    }).addTo(map);
  } else {
    liveLine.setLatLngs(latlngs);
    liveLine.setStyle({ color });
  }

  for (const m of liveVertexMarkers) map.removeLayer(m);
  liveVertexMarkers = points.map((p, idx) => {
    const marker = L.circleMarker([p.lat, p.lng], {
      radius: 9,
      color: "#fff",
      weight: 2,
      fillColor: color,
      fillOpacity: 1,
    }).addTo(map);
    if (onVertexClick) {
      marker.on("click", (e) => {
        L.DomEvent.stopPropagation(e);
        onVertexClick(idx);
      });
    }
    return marker;
  });
}

export function clearLive() {
  if (liveLine) {
    map.removeLayer(liveLine);
    liveLine = null;
  }
  for (const m of liveVertexMarkers) map.removeLayer(m);
  liveVertexMarkers = [];
}

export function panTo(lat, lng) {
  map.panTo([lat, lng]);
}
