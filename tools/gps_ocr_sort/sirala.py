#!/usr/bin/env python3
"""GPS Map Camera fotograflarini OCR ile okuyup sokak adina gore klasorleyen script.

Kullanim:
    python sirala.py /kaynak/klasor /hedef/klasor

Ne yapar:
    - Kaynak klasordeki (alt klasorler dahil) tum .jpg/.jpeg/.png fotograflari tarar.
    - Fotograf uzerindeki "GPS Map Camera" yazi katmanini OCR ile okur.
    - "Lat ..., Long ..." koordinatini ve adres satirindan sokak adini cikarir.
    - Koordinati fotografin EXIF GPS alanina yazar (PNG dosyalar JPEG'e cevrilir,
      cunku PNG standart EXIF desteklemez).
    - Sonucu hedef klasor altinda <Sokak Adi>/dosya.jpg olarak kopyalar.
    - OCR/koordinat bulunamayan dosyalar "Bulunamayanlar" klasorune kopyalanir.
    - Ayni fotografin (koordinat + saat birebir ayni) tekrarlarini atlar, sadece
      birini isler.
    - Islem sonunda hedef klasore "islem_log.csv" yazilir (kontrol icin).
"""

import argparse
import csv
import os
import re
import shutil
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image
import pytesseract
import piexif

# Tesseract, tek bir cagrida bile OpenMP ile birden fazla is parcacigi
# kullanir. Biz paralel (thread havuzu ile ayni anda birden fazla fotografta)
# OCR calistirdigimizdan, tesseract'in kendi ic paralelligini kapatiyoruz
# (tek cagri = tek thread); yoksa N paralel fotograf x tesseract'in kendi
# ic threadleri, cekirdek sayisini kat kat asip islemciyi tikayarak islemi
# sirali calismadan bile yavaslatir.
os.environ.setdefault("OMP_THREAD_LIMIT", "1")

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
UNPROCESSED_FOLDER = "Bulunamayanlar"
REVIEW_FOLDER = "Sokak_Kontrolu_Gerekli"

# Kullanicinin elle sectigi tesseract.exe konumu burada saklanir, bir dahaki
# acilista tekrar sormamak icin.
CONFIG_PATH = Path.home() / ".sokak_gps_ayirici.json"


def load_saved_tesseract_cmd() -> bool:
    import json
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        cmd = data.get("tesseract_cmd")
        if cmd and Path(cmd).is_file():
            pytesseract.pytesseract.tesseract_cmd = cmd
            return True
    except Exception:
        pass
    return False


def save_tesseract_cmd(cmd: str):
    import json
    try:
        CONFIG_PATH.write_text(json.dumps({"tesseract_cmd": cmd}), encoding="utf-8")
    except Exception:
        pass


def configure_tesseract_path():
    """Tesseract PATH'te degilse (kurulum sirasinda PATH'e eklenmediyse veya
    program PATH guncellemesinden once acildiysa), once daha once kullanici
    tarafindan elle secilmis bir konum var mi bakar, sonra bilinen standart
    Windows kurulum klasorlerinde arar."""
    if shutil.which("tesseract"):
        return
    if load_saved_tesseract_cmd():
        return
    candidates = []
    for env_var in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "LOCALAPPDATA"):
        base = os.environ.get(env_var)
        if base:
            candidates.append(Path(base) / "Tesseract-OCR" / "tesseract.exe")
    for candidate in candidates:
        if candidate.is_file():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            return


configure_tesseract_path()

# Tarih/saat satirini yakalar, orn. "20/06/2026 12:09 PM" (haftanin gunu farkli
# dilde/alfabede basildigindan - orn. Kiril - onu yoksayip sadece tarih+saati alir).
DATETIME_RE = re.compile(r"(\d{1,2}/\d{1,2}/\d{2,4})[,\s]+(\d{1,2}:\d{2})\s*([AaPp][Mm])?")

# OCR genelde "Lat" kelimesini yanlis okur (orn. "tat", "Iat"), ama "Long" daha
# guvenilir cikiyor; bu yuzden asil ayirt edici çapa "Long" ve iki ondalikli sayidir.
LATLONG_STRICT_RE = re.compile(
    r"Lat[^0-9\-]{0,5}(-?\d{1,3}\.\d{3,8})[^0-9\-]{0,15}Lo?ng[^0-9\-]{0,5}(-?\d{1,3}\.\d{3,8})",
    re.IGNORECASE,
)
LATLONG_LOOSE_RE = re.compile(
    r"(-?\d{1,3}\.\d{3,8})[^0-9\-]{0,20}[Ll]?[o0]ng[^0-9\-]{0,5}(-?\d{1,3}\.\d{3,8})",
    re.IGNORECASE,
)

# Kucuk kirpma (yakin/temiz) once denenir; adres uzunsa (satirlar sarilmissa)
# daha buyuk kirpmaya gecilir. Ilk gecerli eslesmede durulur.
CROP_FRACTIONS = (0.25, 0.32, 0.4, 0.5, 0.65, 0.8, 1.0)

# GPS Map Camera overlay'inde sol altta kucuk bir harita resmi olur; bu resim
# OCR tarafindan gurultulu metin gibi okunup adres satirinin basina karisir.
# Once bu sutunu (goruntu genisliginin yaklasik ilk %24'u) disarida birakarak
# dene, bulunamazsa (bazi fotograflarda harita yoktur) tam genislikle tekrar dene.
LEFT_FRACTIONS = (0.24, 0.0)


def find_latlong(text: str, pattern=LATLONG_STRICT_RE):
    match = pattern.search(text)
    if not match:
        return None
    try:
        lat, lon = float(match.group(1)), float(match.group(2))
    except ValueError:
        return None
    if -90 <= lat <= 90 and -180 <= lon <= 180:
        return lat, lon, match
    return None


def extract_datetime(text: str) -> Optional[str]:
    match = DATETIME_RE.search(text)
    if not match:
        return None
    date_part, time_part, ampm = match.groups()
    return f"{date_part} {time_part} {ampm or ''}".strip()


@dataclass
class ExtractResult:
    lat: Optional[float] = None
    lon: Optional[float] = None
    street: Optional[str] = None
    street_confident: bool = False
    dt: Optional[str] = None
    raw_text: str = ""
    error: Optional[str] = None


def ocr_image(img: Image.Image, lang: str) -> str:
    return pytesseract.image_to_string(img, lang=lang, config="--psm 6")


# OCR icin kirpilan bolgenin buyutulmus genisligi bu degeri gecmez. Telefonla
# cekilen gercek fotograflar (orn. 2340x4160) test gorseline gore cok daha
# yuksek cozunurluklu oldugundan, sabit 2x buyutme devasa goruntuler
# uretip OCR'i ciddi yavaslatiyordu; OCR dogrulugu icin gereken cozunurluk
# zaten asilmis oluyor, bu yuzden buyutme faktoru genislige gore sinirlandirilir.
MAX_CROP_WIDTH = 2600


def preprocess_crop(img: Image.Image, bottom_fraction: float, left_fraction: float = 0.0) -> Image.Image:
    """Overlay yazisi genelde fotografin alt bandinda olur; o bolgeyi kirpip buyutur.

    left_fraction > 0 ise sol taraftaki kucuk harita resmini de disarida birakir.
    """
    w, h = img.size
    top = int(h * (1 - bottom_fraction))
    left = int(w * left_fraction)
    crop = img.crop((left, top, w, h)).convert("L")
    scale = min(2.0, MAX_CROP_WIDTH / crop.width) if crop.width else 2.0
    scale = max(scale, 1.0)
    crop = crop.resize((int(crop.width * scale), int(crop.height * scale)), Image.LANCZOS)
    return crop


def detect_ocr_lang() -> str:
    try:
        langs = set(pytesseract.get_languages(config=""))
    except Exception:
        return "eng"
    if "deu" in langs and "eng" in langs:
        return "deu+eng"
    return "eng"


def looks_like_street(name: Optional[str]) -> bool:
    """OCR gurultusunden (orn. 'Germany Rn LIED N ES') gercek sokak adini ayirt etmeye
    calisan kaba bir makul-mu kontrolu."""
    if not name or len(name) < 3:
        return False
    # Kisa ev numaralarina (orn. "Reimelsweg 12", "Uerdinger Str. 150", "147C")
    # izin ver, ama posta kodu gibi 5+ haneli sayilari reddet (adres satirinin
    # yanlis kismini yakalamis olabilir).
    if re.search(r"\d{5,}", name):
        return False
    lname = name.lower().strip()
    # "Germany"/"German" ulke adi sokak alanina sizmissa (OCR adres satirini
    # kaybedip bir alt/ust satiri yakalamis demektir) - hicbir zaman gercek
    # sokak adi degildir.
    if re.match(r"^(ge?rman(y)?|rmany)\b", lname):
        return False
    # Harf orani hesaplanirken rakamlar sayilmaz (kisa ev numaralari orani
    # haksiz yere dusurmesin diye); sadece harf-disi/rakam-disi gurultu
    # (@, ;, —, © gibi) orani dusurur.
    compact = "".join(ch for ch in name.replace(" ", "").replace("-", "") if not ch.isdigit())
    if not compact:
        return False
    letters = sum(ch.isalpha() for ch in compact)
    if letters / len(compact) < 0.85:
        return False
    words = name.split()
    if len(words) > 5:
        return False
    short_words = sum(1 for w in words if len(w) <= 2)
    if short_words >= 2:
        return False
    return True


def extract_street_from_lines(lines: list[str], lat_idx: int) -> Optional[str]:
    """Lat/Long satirinin hemen ustundeki adres satirindan sokak adini cikarir.

    GPS Map Camera overlay'i adresi tek satira sigmayinca sarar (word-wrap);
    hemen ustteki satir kisa/virgulsuzse (orn. sadece 'Germany') bir ust satirla
    birlestirilir.
    """
    if lat_idx <= 0:
        return None
    addr_line = lines[lat_idx - 1].strip()
    if lat_idx - 2 >= 0 and ("," not in addr_line or len(addr_line) < 15):
        addr_line = lines[lat_idx - 2].strip() + ", " + addr_line
    if not addr_line:
        return None
    first_part = addr_line.split(",")[0].strip()
    first_part = re.sub(r"^[^A-Za-zÀ-ÿ0-9]+", "", first_part)
    if len(first_part) < 3:
        return None
    return first_part


# Iki OCR denemesinin "ayni koordinatta hemfikir" sayilmasi icin izin verilen
# en buyuk fark (derece). ~0.0003 derece ~= 30 metre; gercek tek-hane OCR
# hatalari (orn. "51" -> "54") bunun onlarca-yuzlerce kati kadar sapma
# yarattigindan kolayca ayirt edilir, ama farkli kirpmalardaki kucuk
# yuvarlama farklarina tolerans taniniz.
COORD_CONFIRM_TOL = 0.0003


def find_confirmed_match(matches: list) -> Optional["ExtractResult"]:
    """Birbiriyle 'hemfikir' olan (COORD_CONFIRM_TOL icinde) ilk iki sonucu bulur.

    Tek bir OCR okumasi asla tek basina yeterli sayilmaz: koordinat, en az iki
    bagimsiz denemede (farkli kirpma/olcek) ayni cikmadikca guvenilir kabul
    edilmez. Bu, tek bir hanenin yanlis okunmasindan (orn. "51" -> "54")
    kaynaklanan, sayisal olarak "gecerli" ama gercekte yanlis konumlarin
    GPS'e yazilmasini engeller.
    """
    for i in range(len(matches)):
        for j in range(i + 1, len(matches)):
            a, b = matches[i], matches[j]
            if abs(a.lat - b.lat) <= COORD_CONFIRM_TOL and abs(a.lon - b.lon) <= COORD_CONFIRM_TOL:
                if b.street_confident and not a.street_confident:
                    return b
                return a
    return None


def extract_info(image_path: Path, lang: str) -> ExtractResult:
    try:
        img = Image.open(image_path)
        img = _apply_exif_orientation(img)
    except Exception as exc:
        return ExtractResult(error=f"Goruntu acilamadi: {exc}")

    def make_result(text: str, pattern) -> ExtractResult:
        found = find_latlong(text, pattern)
        lat, lon, _ = found
        lines = [ln.strip() for ln in text.splitlines()]
        lat_idx = next((i for i, ln in enumerate(lines) if find_latlong(ln, pattern)), None)
        street = extract_street_from_lines(lines, lat_idx) if lat_idx is not None else None
        result = ExtractResult(lat=lat, lon=lon, street=street, dt=extract_datetime(text), raw_text=text)
        if looks_like_street(result.street):
            result.street_confident = True
        return result

    # Harita sutunu disarida birakilan denemeler (LEFT_FRACTIONS sirasi) once
    # denenir, cunku adres satirina daha temiz sonuc verir. Bir koordinat,
    # ancak en az iki bagimsiz kirpma/olcek denemesi ayni sonucu verdiginde
    # ("hemfikir" oldugunda) guvenilir sayilir; bu yuzden ilk basarili
    # okumada hemen durulmaz, teyit icin en az bir tane daha aranir.
    strict_matches: list = []
    for left_fraction in LEFT_FRACTIONS:
        for bottom_fraction in CROP_FRACTIONS:
            try:
                if bottom_fraction == 1.0 and left_fraction == 0.0:
                    source = img
                else:
                    source = preprocess_crop(img, bottom_fraction, left_fraction)
                text = ocr_image(source, lang)
            except Exception as exc:
                return ExtractResult(error=f"OCR hatasi: {exc}")
            if find_latlong(text, LATLONG_STRICT_RE):
                strict_matches.append(make_result(text, LATLONG_STRICT_RE))
                confirmed = find_confirmed_match(strict_matches)
                if confirmed:
                    return confirmed

    confirmed = find_confirmed_match(strict_matches)
    if confirmed:
        return confirmed

    return ExtractResult(
        error="Koordinat guvenilir sekilde teyit edilemedi (tek okuma, ikinci bir denemeyle dogrulanamadi)"
    )


def _apply_exif_orientation(img: Image.Image) -> Image.Image:
    try:
        from PIL import ImageOps
        return ImageOps.exif_transpose(img)
    except Exception:
        return img


def sanitize_folder_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r'[\\/:*?"<>|]', "-", name)
    name = re.sub(r"\s+", " ", name)
    name = unicodedata.normalize("NFC", name)
    return name[:80] if name else "Bilinmeyen_Sokak"


def deg_to_dms_rational(deg_float: float):
    deg_float = abs(deg_float)
    degrees = int(deg_float)
    minutes_float = (deg_float - degrees) * 60
    minutes = int(minutes_float)
    seconds = round((minutes_float - minutes) * 60 * 100)
    return [(degrees, 1), (minutes, 1), (seconds, 100)]


def build_gps_exif_bytes(lat: float, lon: float) -> bytes:
    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: "N" if lat >= 0 else "S",
        piexif.GPSIFD.GPSLatitude: deg_to_dms_rational(lat),
        piexif.GPSIFD.GPSLongitudeRef: "E" if lon >= 0 else "W",
        piexif.GPSIFD.GPSLongitude: deg_to_dms_rational(lon),
    }
    exif_dict = {"GPS": gps_ifd}
    return piexif.dump(exif_dict)


def save_with_gps(image_path: Path, dest_path: Path, lat: float, lon: float) -> Path:
    """Fotografi hedefe GPS EXIF'i ile yazar. PNG ise JPEG'e cevirir (EXIF destegi icin).

    Donen deger gercek yazilan dosyanin yolu (uzanti degisebilir).
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    exif_bytes = build_gps_exif_bytes(lat, lon)

    if image_path.suffix.lower() in (".jpg", ".jpeg"):
        shutil.copy2(image_path, dest_path)
        piexif.insert(exif_bytes, str(dest_path))
        return dest_path

    dest_path = dest_path.with_suffix(".jpg")
    with Image.open(image_path) as img:
        img = _apply_exif_orientation(img)
        if img.mode in ("RGBA", "P", "LA"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            rgba = img.convert("RGBA")
            background.paste(rgba, mask=rgba.split()[-1])
            img = background
        else:
            img = img.convert("RGB")
        img.save(dest_path, "JPEG", quality=95, exif=exif_bytes)
    return dest_path


def iter_image_files(source_dir: Path):
    for path in sorted(source_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
            yield path


def unique_dest(dest_path: Path) -> Path:
    if not dest_path.exists():
        return dest_path
    stem, suffix, parent = dest_path.stem, dest_path.suffix, dest_path.parent
    i = 1
    while True:
        candidate = parent / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def dedupe_key(result: ExtractResult):
    """Ayni fotografin (kopya/tekrar) tekrarlarini yakalamak icin anahtar uretir.

    Koordinat 6 hane (~11 cm) hassasiyetinde ve OCR'dan okunan tarih/saat
    birebir ayniysa, ayni fotografin tekrari kabul edilir.
    """
    lat_key = round(result.lat, 6)
    lon_key = round(result.lon, 6)
    return (lat_key, lon_key, result.dt)


def run_ocr_parallel(files, lang: str, log=print, on_progress=None, max_workers=None):
    """Tum fotograflar icin OCR'i (extract_info) paralel calistirir.

    OCR'in agir kismi (tesseract) ayri bir isletim sistemi surecinde
    calistigi icin (pytesseract subprocess acar), Python'un GIL'i engel
    olmaz ve thread havuzu ile gercek paralellik saglanir. Bu, tek tek
    sirayla islemeye gore cok cekirdekli bilgisayarlarda birkaç kat hizlanma
    saglar.
    """
    import concurrent.futures

    total = len(files)
    results = [None] * total
    if max_workers is None:
        max_workers = os.cpu_count() or 4

    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {executor.submit(extract_info, path, lang): idx for idx, path in enumerate(files)}
        for future in concurrent.futures.as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as exc:
                results[idx] = ExtractResult(error=f"Beklenmeyen hata: {exc}")
            completed += 1
            if on_progress:
                on_progress(completed, total)
    return results


def find_coordinate_outliers(results, min_points=5, threshold_deg=0.02):
    """Diger fotograflara gore anormal uzaktaki koordinatlari isaretler.

    Ayni saha gezisindeki fotograflar genelde birbirine yakin (bir mahalle/
    birkac sokak) cikar. OCR bazen bir hane yanlis okuyup (orn. "51" yerine
    "54") koordinati onlarca-yuzlerce km kaydırabiliyor; bu, sayisal olarak
    gecerli (-90..90 / -180..180) oldugu icin normal dogrulamadan gecer ama
    gercekte yanlis konumdur. Bu fonksiyon, medyan konumdan asiri sapan
    (varsayilan 0.02 derece, ~2 km) sonuclarin indekslerini dondurur.
    """
    import statistics

    coords = [(i, r) for i, r in enumerate(results) if r and r.lat is not None and r.lon is not None]
    if len(coords) < min_points:
        return set()
    median_lat = statistics.median(r.lat for _, r in coords)
    median_lon = statistics.median(r.lon for _, r in coords)
    return {
        i for i, r in coords
        if abs(r.lat - median_lat) > threshold_deg or abs(r.lon - median_lon) > threshold_deg
    }


def process(source_dir: Path, dest_dir: Path, lang: str, move: bool, log=print, on_progress=None):
    dest_dir.mkdir(parents=True, exist_ok=True)
    log_rows = []
    files = list(iter_image_files(source_dir))
    total = len(files)
    if total == 0:
        log(f"Kaynak klasorde islenecek fotograf bulunamadi: {source_dir}")
        return

    workers = os.cpu_count() or 4
    log(f"{total} fotograf bulundu. OCR isleniyor ({workers} paralel islem)...")
    results = run_ocr_parallel(files, lang, log=log, on_progress=on_progress)
    outlier_indices = find_coordinate_outliers(results)
    if outlier_indices:
        log(f"UYARI: {len(outlier_indices)} fotografin koordinati digerlerinden anormal uzak (muhtemel OCR hatasi), '{UNPROCESSED_FOLDER}' klasorune ayriliyor.")

    log("OCR tamamlandi, sonuclar klasorlere yerlestiriliyor...")
    ok_count = 0
    dup_count = 0
    seen_keys = {}
    for i, path in enumerate(files, 1):
        result = results[i - 1]
        status = "OK"
        street_folder = UNPROCESSED_FOLDER
        written_path = None
        is_outlier = (i - 1) in outlier_indices
        has_coords = not result.error and result.lat is not None and result.lon is not None and not is_outlier

        if has_coords:
            key = dedupe_key(result)
            duplicate_of = seen_keys.get(key)
            if duplicate_of is not None:
                status = f"ATLANDI: '{duplicate_of}' ile ayni fotograf (koordinat+saat ayni)"
                street_folder = "(atlandi - tekrar)"
                dup_count += 1
                log_rows.append({
                    "dosya": str(path), "durum": status, "lat": result.lat, "long": result.lon,
                    "sokak": result.street or "", "hedef": "",
                })
                log(f"[{i}/{total}] {path.name} -> {street_folder} ({status})")
                continue
            seen_keys[key] = path.name

        if is_outlier:
            status = "HATA: Koordinat anormal uzak (muhtemel OCR hatasi), kontrol edin"
        elif not has_coords:
            status = f"HATA: {result.error or 'koordinat bulunamadi'}"
        else:
            street_folder = sanitize_folder_name(result.street) if result.street_confident else REVIEW_FOLDER
            try:
                dest_path = unique_dest(dest_dir / street_folder / path.name)
                written_path = save_with_gps(path, dest_path, result.lat, result.lon)
                ok_count += 1
            except Exception as exc:
                status = f"HATA: EXIF/kaydetme basarisiz: {exc}"
                street_folder = UNPROCESSED_FOLDER

        if written_path is None:
            try:
                dest_path = unique_dest(dest_dir / UNPROCESSED_FOLDER / path.name)
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest_path)
                written_path = dest_path
            except Exception as exc:
                status = f"HATA: kopyalanamadi: {exc}"

        if move and written_path is not None:
            try:
                path.unlink()
            except Exception:
                pass

        log_rows.append({
            "dosya": str(path),
            "durum": status,
            "lat": result.lat,
            "long": result.lon,
            "sokak": result.street or "",
            "hedef": str(written_path) if written_path else "",
        })
        log(f"[{i}/{total}] {path.name} -> {street_folder} ({status})")

    log_path = dest_dir / "islem_log.csv"
    with open(log_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["dosya", "durum", "lat", "long", "sokak", "hedef"])
        writer.writeheader()
        writer.writerows(log_rows)

    log(f"\nBitti: {ok_count}/{total} fotograf basariyla GPS'lendi ve klasorlendi.")
    if dup_count:
        log(f"{dup_count} fotograf, ayni koordinat/saate sahip baska bir fotografla ayni oldugu icin atlandi.")
    log(f"Log dosyasi: {log_path}")
    log(f"OCR/koordinat bulunamayan (veya konumu anormal) fotograflar '{UNPROCESSED_FOLDER}' klasorunde.")
    log(f"Sokak adindan emin olunamayan (ama GPS'i dogru yazilan) fotograflar '{REVIEW_FOLDER}' klasorunde.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("kaynak", type=Path, help="Fotograflarin bulundugu kaynak klasor")
    parser.add_argument("hedef", type=Path, help="Sokak klasorlerinin olusturulacagi hedef klasor")
    parser.add_argument("--move", action="store_true", help="Kopyalamak yerine kaynaktan tasi (varsayilan: kopyala)")
    parser.add_argument("--lang", default=None, help="Tesseract dil kodu (varsayilan: otomatik, deu+eng varsa)")
    args = parser.parse_args()

    if not args.kaynak.is_dir():
        print(f"Kaynak klasor bulunamadi: {args.kaynak}", file=sys.stderr)
        sys.exit(1)

    try:
        pytesseract.get_tesseract_version()
    except Exception:
        print(
            "Tesseract OCR bulunamadi. Kurulum icin:\n"
            "  Windows: https://github.com/UB-Mannheim/tesseract/wiki\n"
            "  macOS:   brew install tesseract tesseract-lang\n"
            "  Linux:   sudo apt install tesseract-ocr tesseract-ocr-deu\n",
            file=sys.stderr,
        )
        sys.exit(1)

    lang = args.lang or detect_ocr_lang()
    process(args.kaynak, args.hedef, lang, args.move)


if __name__ == "__main__":
    main()
