import { wgs84ToTarget, TARGET_LABEL } from "./coords.js";

function sanitizeLayerName(name) {
  const cleaned = name.replace(/[<>/\\":;?*|=`]/g, "_").trim();
  return cleaned || "KATMAN";
}

function hexToTrueColorInt(hex) {
  const clean = hex.replace("#", "");
  return parseInt(clean, 16);
}

function dxfPair(code, value) {
  return `${code}\n${value}\n`;
}

function buildLayerTable(layers) {
  let out = "";
  out += dxfPair(0, "TABLE");
  out += dxfPair(2, "LAYER");
  out += dxfPair(70, layers.length);
  for (const layer of layers) {
    const trueColor = hexToTrueColorInt(layer.color);
    out += dxfPair(0, "LAYER");
    out += dxfPair(2, sanitizeLayerName(layer.name));
    out += dxfPair(70, 0);
    out += dxfPair(62, 7);
    out += dxfPair(6, "CONTINUOUS");
    out += dxfPair(420, trueColor);
  }
  out += dxfPair(0, "ENDTAB");
  return out;
}

function buildEntities(segments, layersById, pointMarkers) {
  let out = "";
  out += dxfPair(0, "SECTION");
  out += dxfPair(2, "ENTITIES");

  for (const segment of segments) {
    if (segment.points.length < 2) continue;
    const layer = layersById.get(segment.layerId);
    if (!layer) continue;
    const trueColor = hexToTrueColorInt(layer.color);
    const layerName = sanitizeLayerName(layer.name);

    out += dxfPair(0, "LWPOLYLINE");
    out += dxfPair(8, layerName);
    out += dxfPair(420, trueColor);
    out += dxfPair(90, segment.points.length);
    out += dxfPair(70, 0);
    out += dxfPair(43, 0);

    for (const p of segment.points) {
      const { x, y } = wgs84ToTarget(p.lat, p.lng);
      out += dxfPair(10, x.toFixed(3));
      out += dxfPair(20, y.toFixed(3));
    }
  }

  if (pointMarkers && pointMarkers.length > 0) {
    const pointsById = new Map();
    for (const segment of segments) {
      for (const p of segment.points) pointsById.set(p.id, p);
    }

    for (const pm of pointMarkers) {
      const layer = layersById.get(pm.layerId);
      const point = pointsById.get(pm.pointId);
      if (!layer || !point) continue;
      const trueColor = hexToTrueColorInt(layer.color);
      const { x, y } = wgs84ToTarget(point.lat, point.lng);

      out += dxfPair(0, "CIRCLE");
      out += dxfPair(8, sanitizeLayerName(layer.name));
      out += dxfPair(420, trueColor);
      out += dxfPair(10, x.toFixed(3));
      out += dxfPair(20, y.toFixed(3));
      out += dxfPair(40, "0.15");
    }
  }

  out += dxfPair(0, "ENDSEC");
  return out;
}

export function buildDxfString(layers, segments, pointMarkers = []) {
  const layersById = new Map(layers.map((l) => [l.id, l]));

  let out = "";

  out += dxfPair(0, "SECTION");
  out += dxfPair(2, "HEADER");
  out += dxfPair(9, "$ACADVER");
  out += dxfPair(1, "AC1015");
  out += dxfPair(9, "$INSUNITS");
  out += dxfPair(70, 6); // 6 = metre
  out += dxfPair(0, "ENDSEC");

  out += dxfPair(0, "SECTION");
  out += dxfPair(2, "TABLES");
  out += dxfPair(0, "TABLE");
  out += dxfPair(2, "LTYPE");
  out += dxfPair(70, 1);
  out += dxfPair(0, "LTYPE");
  out += dxfPair(2, "CONTINUOUS");
  out += dxfPair(70, 0);
  out += dxfPair(3, "Solid line");
  out += dxfPair(72, 65);
  out += dxfPair(73, 0);
  out += dxfPair(40, "0.0");
  out += dxfPair(0, "ENDTAB");
  out += buildLayerTable(layers);
  out += dxfPair(0, "ENDSEC");

  out += buildEntities(segments, layersById, pointMarkers);

  out += dxfPair(0, "EOF");
  return out;
}

export function downloadDxf(layers, segments, pointMarkers = []) {
  const usable = segments.filter((s) => s.points.length >= 2);
  if (usable.length === 0 && pointMarkers.length === 0) {
    alert("Disa aktarilacak tamamlanmis bir cizgi yok. Once en az bir olcum kaydet.");
    return false;
  }

  const dxfText = buildDxfString(layers, usable, pointMarkers);
  const blob = new Blob([dxfText], { type: "application/dxf" });
  const url = URL.createObjectURL(blob);

  const stamp = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const filename = `vermessung_${stamp.getFullYear()}${pad(stamp.getMonth() + 1)}${pad(
    stamp.getDate()
  )}_${pad(stamp.getHours())}${pad(stamp.getMinutes())}.dxf`;

  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  return true;
}

export { TARGET_LABEL };
