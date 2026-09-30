@echo off
rem ============================================================
rem  GoogleClassHelp - production build pipeline
rem
rem  1. generate the application icon and the site favicons
rem  2. rebuild the frontend with `npm run build`
rem  3. embed the OAuth client config (no plaintext credentials
rem     in the release)
rem  4. compile backend/launcher.py with Nuitka into a single
rem     no-console GoogleClassHelp.exe (frontend/dist bundled)
rem  5. copy the executable into release\
rem
rem  Step 1 runs BEFORE step 2 on purpose: make_icon.py writes the
rem  favicons into frontend\public, and only the Vite build copies
rem  them into frontend\dist that gets bundled and shipped.
rem
rem  Requirements: .venv with backend requirements + nuitka,
rem  Node.js/npm for the frontend build step.
rem ============================================================
setlocal
cd /d "%~dp0"

set PY=.venv\Scripts\python.exe
set APP_VERSION=1.0.0

if not exist "%PY%" (
    echo ERROR: .venv not found. Create it and install backend\requirements.txt + nuitka.
    goto :fail
)

echo === [1/5] Application icon + site favicons ===
rem Runs first: the favicons must exist in frontend\public before Vite copies
rem that folder into frontend\dist.
set ICON_OPTS=
"%PY%" tools\make_icon.py
if exist assets\GoogleClassHelp.ico (
    set ICON_OPTS=--windows-icon-from-ico=assets/GoogleClassHelp.ico
) else (
    echo WARNING: icon generation failed; building without a custom icon.
)

echo === [2/5] Building frontend ===
if exist frontend\dist rmdir /s /q frontend\dist
if not exist frontend\node_modules (
    pushd frontend
    call npm install
    if errorlevel 1 (popd & goto :fail)
    popd
)
pushd frontend
call npm run build
if errorlevel 1 (popd & goto :fail)
popd
if not exist frontend\dist\index.html (
    echo ERROR: frontend\dist\index.html missing after npm run build.
    goto :fail
)
rem The favicons are copied by Vite; fail loudly rather than shipping a
rem release whose browser tab shows the generic page icon.
if not exist frontend\dist\favicon.svg (
    echo ERROR: frontend\dist\favicon.svg missing - icon step did not run first.
    goto :fail
)

echo === [3/5] Embedding OAuth client config ===
"%PY%" backend\build_secrets.py
if errorlevel 1 goto :fail

echo === [4/5] Nuitka build (this takes several minutes) ===
"%PY%" -m nuitka ^
    --standalone ^
    --onefile ^
    --windows-console-mode=disable ^
    --assume-yes-for-downloads ^
    --output-dir=build ^
    --output-filename=GoogleClassHelp.exe ^
    --include-data-dir=frontend/dist=frontend/dist ^
    --include-module=embedded_secrets ^
    --include-package=pystray ^
    --include-package=PIL ^
    --include-package=uvicorn ^
    --include-package=sqlalchemy.dialects.sqlite ^
    --include-package=googleapiclient ^
    --include-package=googleapiclient.discovery_cache ^
    --include-package-data=googleapiclient ^
    --include-package=google_auth_oauthlib ^
    --include-package=google.oauth2 ^
    --include-package=google.auth ^
    --include-package=google_auth_httplib2 ^
    --include-package-data=certifi ^
    %ICON_OPTS% ^
    --product-name=GoogleClassHelp ^
    --file-description="Google Classroom Dashboard" ^
    --file-version=%APP_VERSION% ^
    --product-version=%APP_VERSION% ^
    backend\launcher.py
if errorlevel 1 goto :fail

echo === [5/5] Release directory ===
if not exist release mkdir release
copy /y build\GoogleClassHelp.exe release\GoogleClassHelp.exe >nul
if errorlevel 1 goto :fail

echo.
echo BUILD OK: release\GoogleClassHelp.exe
goto :eof

:fail
echo.
echo BUILD FAILED
exit /b 1
