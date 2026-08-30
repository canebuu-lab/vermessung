@echo off
echo ============================================
echo  Sokak GPS Ayirici - .exe olusturucu
echo ============================================
echo.
echo Python bagimliliklari kuruluyor (Pillow, pytesseract, piexif, pyinstaller)...
pip install -r requirements.txt pyinstaller
if errorlevel 1 (
    echo.
    echo HATA: pip kurulumu basarisiz oldu. Python kurulu mu ve PATH'e eklendi mi kontrol edin.
    pause
    exit /b 1
)

echo.
echo .exe olusturuluyor, bu birkac dakika surebilir...
pyinstaller --onefile --windowed --name SokakGPSAyirici gui.py
if errorlevel 1 (
    echo.
    echo HATA: .exe olusturulamadi, yukaridaki hata mesajina bakin.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  BITTI! Programiniz burada:
echo  dist\SokakGPSAyirici.exe
echo ============================================
pause
