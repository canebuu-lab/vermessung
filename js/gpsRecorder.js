export const MIN_POINT_DISTANCE_M = 0.5; // titremeyi azaltmak icin min hareket mesafesi
export const ACCURACY_WARN_M = 8; // sari uyari esigi
export const ACCURACY_BAD_M = 20; // kirmizi uyari esigi

export function haversineMeters(lat1, lng1, lat2, lng2) {
  const R = 6371000;
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

export function startWatch(onPosition, onError) {
  if (!("geolocation" in navigator)) {
    onError?.(new Error("Bu tarayici konum servisini desteklemiyor."));
    return null;
  }
  return navigator.geolocation.watchPosition(
    (pos) => {
      onPosition({
        lat: pos.coords.latitude,
        lng: pos.coords.longitude,
        alt: pos.coords.altitude,
        accuracy: pos.coords.accuracy,
        t: pos.timestamp,
      });
    },
    (err) => onError?.(err),
    { enableHighAccuracy: true, maximumAge: 0, timeout: 15000 }
  );
}

export function stopWatch(watchId) {
  if (watchId != null) navigator.geolocation.clearWatch(watchId);
}
