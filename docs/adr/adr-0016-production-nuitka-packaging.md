# ADR-0016: Production-сборка — единый exe на Nuitka с встроенным фронтендом

Дата: 2026-09-15
Статус: Accepted

## Контекст

Приложение используется на одном Windows-ПК; запуск через `.venv` + uvicorn +
Vite — это developer experience, недопустимая для повседневного
использования. Требуется один запуск двойным кликом без Python, Node.js и
консольного окна.

## Решение

- Единая точка входа `backend/launcher.py`: поднимает uvicorn на
  `127.0.0.1` (порт 8000 или ближайший свободный), дожидается готовности
  `/api/health`, открывает браузер, гасит сервер при выходе. Компилируется
  Nuitka (`--standalone --onefile --windows-console-mode=disable`) в
  `GoogleClassHelp.exe`; фронтенд из `frontend/dist` включается как data
  files и раздаётся FastAPI с SPA-фолбэком на `index.html`. Повторный запуск
  exe активирует работающий дашборд вместо второго инстанса — см.
  [ADR-0018](adr-0018-single-instance-launcher.md).
- Разделение путей (`path_config.py`): read-only `RESOURCE_DIR` (бандл)
  против перезаписываемого `DATA_DIR` — в compiled-сборке
  `%LOCALAPPDATA%\GoogleClassHelp\` (token.json, classroom.db, logs).
  В development пути прежние (`<проект>\data\`). ADR-0003 не нарушен:
  SQLite-кэш остаётся стратегией хранения, меняется только каталог.
- OAuth-клиент не распространяется отдельным `credentials.json`:
  `build_secrets.py` на этапе сборки генерирует `embedded_secrets.py`
  (XOR+base64, случайный ключ), конфиг расшифровывается в памяти. Это
  обфускация от случайного просмотра, не защита от реверс-инжиниринга.
- Скоупы OAuth не меняются (ADR-0002), слоистая архитектура (ADR-0001)
  не трогается: новый код — только launcher/paths/build pipeline.

## Последствия

- Пользователь: двойной клик → браузер → дашборд; данные и токены живут
  в профиле пользователя и переживают переустановку.
- Разработка не меняется: `uvicorn main:app --reload` + `npm run dev`
  работают как раньше; production-сборка отдельна (`build.bat`).
- Появился генерируемый артефакт `embedded_secrets.py` (git-ignored);
  его отсутствие в dev не ломает приложение (fallback на файл).

## Альтернативы

- PyInstaller — отклонён требованием промпта (Nuitka лучше оптимизирует и
  компилирует в C).
- WebView/Tauri/Electron — отклонено: лишний рантайм при уже готовом
  браузерном UI.
- Плоский `credentials.json` рядом с exe — отклонено: читается в Блокноте.
