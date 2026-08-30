# GPS OCR Sokak Ayirici

"GPS Map Camera" ile cekilmis, EXIF GPS'i bos olan fotograflari OCR ile okuyup
gercek GPS koordinatini EXIF'e yazan ve fotograflari sokak adina gore
klasorleyen standalone Python scripti.

## Kurulum

1. Tesseract OCR'i kur (bir kere, isletim sistemine gore):
   - Windows: https://github.com/UB-Mannheim/tesseract/wiki (Almanca dil paketini de secin)
   - macOS: `brew install tesseract tesseract-lang`
   - Linux (Debian/Ubuntu): `sudo apt install tesseract-ocr tesseract-ocr-deu`

2. Python bagimliliklarini kur:
   ```
   pip install -r requirements.txt
   ```

## Kullanim

```
python sirala.py /kaynak/klasor /hedef/klasor
```

- Kaynak klasordeki (alt klasorler dahil) tum `.jpg`, `.jpeg`, `.png` fotograflari tarar.
- Her fotografi hedef klasor altinda `<Sokak Adi>/dosya.jpg` olarak **kopyalar**
  (kaynaktaki dosyalara dokunmaz).
- `--move` verilirse kopyalamak yerine kaynaktan tasir.
- Coordinati fotografin EXIF GPS alanina yazar; PNG dosyalar JPEG'e cevrilir
  (PNG standart EXIF desteklemedigi icin).
- OCR ile Lat/Long bulunamayan fotograflar `Islenemedi` klasorune kopyalanir.
- Islem sonunda hedef klasore, her fotograf icin OCR sonucunu ve durumunu
  gosteren `islem_log.csv` yazilir — sonuclari toplu kontrol etmek icin kullanin.

## Bilinen sinirlamalar

- Sokak adi tamamen OCR'a dayanir; benzer harfler (orn. U/Y, l/I) bazen
  karisabilir. Sonuc klasor adlarini ve `islem_log.csv`'yi gozden gecirmeniz
  onerilir.
- Adres formati "GPS Map Camera" uygulamasinin varsayilan sablonuna gore
  ayarlanmistir (sehir basligi, ardindan acik adres, ardindan
  `Lat X, Long Y` satiri). Farkli bir uygulama/sablon kullanildiysa cikarim
  basarisiz olabilir ve fotograf `Islenemedi` klasorune duser.
