// ETRS89 / UTM Zone 32N — QGIS'te "Almanya UTM 32" olarak bilinen sistem (EPSG:25832).
// Baska bir EPSG kodu gerekiyorsa sadece bu tanimi degistirmek yeterli.
export const TARGET_EPSG = "EPSG:25832";
export const TARGET_LABEL = "ETRS89 / UTM Zone 32N (EPSG:25832)";

proj4.defs(
  TARGET_EPSG,
  "+proj=utm +zone=32 +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs +type=crs"
);

// WGS84 (GPS) lat/lng -> hedef projeksiyon [x, y] (metre)
export function wgs84ToTarget(lat, lng) {
  const [x, y] = proj4("EPSG:4326", TARGET_EPSG, [lng, lat]);
  return { x, y };
}
