@echo off
setlocal
echo ============================================
echo  Sokak GPS Ayirici - .exe olusturucu
echo ============================================
echo.

set PYCMD=
where python >nul 2>nul
if %errorlevel%==0 set PYCMD=python
if "%PYCMD%"=="" (
    where py >nul 2>nul
    if %errorlevel%==0 set PYCMD=py
)

if "%PYCMD%"=="" (
    echo HATA: Python bulunamadi.
    echo.
    echo 1) https://www.python.org/downloads/ adresinden Python'u indirip kurun.
    echo 2) Kurulum ekraninin EN ALTINDAKI "Add python.exe to PATH" kutusunu
    echo    mutlaka isaretleyin.
    echo 3) Kurulum bitince bu bilgisayari YENIDEN BASLATIN ^(veya en azindan
    echo    tum pencereleri kapatip yeniden acin^) ve bu dosyayi tekrar calistirin.
    pause
    exit /b 1
)

echo Python bulundu: %PYCMD%
echo.
echo Python bagimliliklari kuruluyor (Pillow, pytesseract, piexif, pyinstaller)...
%PYCMD% -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
    echo.
    echo HATA: pip kurulumu basarisiz oldu. Yukaridaki hata mesajina bakin.
    pause
    exit /b 1
)

echo.
echo .exe olusturuluyor, bu birkac dakika surebilir...
%PYCMD% -m PyInstaller --onefile --windowed --name SokakGPSAyirici gui.py
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
