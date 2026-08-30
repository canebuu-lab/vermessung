# GPS OCR Sokak Ayirici

"GPS Map Camera" ile cekilmis, EXIF GPS'i bos olan fotograflari OCR ile okuyup
gercek GPS koordinatini EXIF'e yazan ve fotograflari sokak adina gore
klasorleyen program. Hem masaustu (pencereli) hem komut satiri surumu vardir.

## Kurulum

1. Tesseract OCR'i kur (bir kere, isletim sistemine gore):
   - Windows: https://github.com/UB-Mannheim/tesseract/wiki (Almanca dil paketini de secin)
   - macOS: `brew install tesseract tesseract-lang`
   - Linux (Debian/Ubuntu): `sudo apt install tesseract-ocr tesseract-ocr-deu`

2. Python bagimliliklarini kur:
   ```
   pip install -r requirements.txt
   ```
   (Tkinter penceresi Python ile birlikte gelir, ekstra kurulum gerekmez.)

## Masaustu programi (onerilen)

```
python gui.py
```

Acilan pencerede kaynak ve hedef klasoru "Gözat…" ile secin, isterseniz
"kopyalamak yerine tasi" kutusunu isaretleyin ve "Başlat"a basin. Ilerleme
cubugu ve canli gunluk pencerede gorunur; bitince ozet mesaji cikar.

### Windows icin tek .exe olarak paketleme

.exe dosyasi sadece Windows uzerinde, Windows'ta uretilebilir (bu depo bir
Linux ortaminda hazirlandigi icin .exe burada olusturulamiyor). Kendi
bilgisayarinizda 3 adimda hazirlayabilirsiniz:

1. Python kurun (yoksa): https://www.python.org/downloads/ — kurulumda
   **"Add python.exe to PATH"** kutusunu mutlaka isaretleyin.
2. Tesseract OCR kurun: https://github.com/UB-Mannheim/tesseract/wiki
   (kurulum sirasinda "Additional language data" listesinden **German**'i de
   secin).
3. Bu klasoru (`tools/gps_ocr_sort`) bilgisayariniza indirip icine girin,
   `build_exe.bat` dosyasina **cift tiklayin**. Islem bitince
   `dist\SokakGPSAyirici.exe` dosyasi hazir olur — bunu masaustune veya
   istediginiz yere kopyalayip cift tiklayarak calistirabilirsiniz.

Not: `.exe` sadece programin kendisini paketler; Tesseract OCR yine de
hedef bilgisayarda 2. adimdaki gibi ayrica kurulu olmalidir.

## Komut satiri (CLI) kullanimi

```
python sirala.py /kaynak/klasor /hedef/klasor
```

- `--move` verilirse kopyalamak yerine kaynaktan tasir.
- `--lang` ile tesseract dil kodu elle verilebilir (varsayilan: otomatik).

## Ikisinin de yaptigi

- Kaynak klasordeki (alt klasorler dahil) tum `.jpg`, `.jpeg`, `.png` fotograflari tarar.
- Her fotografi hedef klasor altinda `<Sokak Adi>/dosya.jpg` olarak **kopyalar**
  (varsayilan; kaynaktaki dosyalara dokunmaz).
- Coordinati fotografin EXIF GPS alanina yazar; PNG dosyalar JPEG'e cevrilir
  (PNG standart EXIF desteklemedigi icin).
- **Ayni fotografin tekrarlarini atlar**: OCR'dan okunan koordinat (6 hane,
  ~11 cm hassasiyet) VE tarih/saat birebir ayniysa, ayni fotografin kopyasi
  kabul edilir; kac kopya olursa olsun sadece ilki islenir, digerleri
  `islem_log.csv`'de "ATLANDI" olarak isaretlenip atlanir (hedefe kopyalanmaz).
- OCR ile Lat/Long bulunamayan fotograflar `Bulunamayanlar` klasorune kopyalanir.
- Islem sonunda hedef klasore, her fotograf icin OCR sonucunu ve durumunu
  gosteren `islem_log.csv` yazilir — sonuclari toplu kontrol etmek icin kullanin.

## Bilinen sinirlamalar

- Sokak adi tamamen OCR'a dayanir; benzer harfler (orn. U/Y, l/I) bazen
  karisabilir. Sonuc klasor adlarini ve `islem_log.csv`'yi gozden gecirmeniz
  onerilir.
- Adres formati "GPS Map Camera" uygulamasinin varsayilan sablonuna gore
  ayarlanmistir (sehir basligi, ardindan acik adres, ardindan
  `Lat X, Long Y` satiri, ardindan tarih/saat). Farkli bir uygulama/sablon
  kullanildiysa cikarim basarisiz olabilir ve fotograf `Bulunamayanlar`
  klasorune duser.
- Tekrar tespiti koordinat + saat eslesmesine dayanir; OCR tarih/saati
  okuyamazsa (nadiren), sadece koordinat eslesmesi yeterli sayilir.
