# Local Google Classroom Dashboard

Локальный дашборд Google Classroom: FastAPI + SQLite-кэш на бэкенде,
React (Vite) на фронтенде. Работает только на localhost, данные синхронизируются
с Google Classroom API (read-only scopes, см. `docs/adr/adr-0002`).

Два режима работы: **разработка** (два процесса: uvicorn + Vite dev-сервер)
и **production** (один exe-файл `GoogleClassHelp.exe` на Nuitka).

---

## DEVELOPMENT

Требования: Python 3.13 (`.venv`), Node.js + npm.

### Backend

```bat
cd D:\Documents\google_class_help
.venv\Scripts\activate
cd backend
uvicorn main:app --reload
```

Бэкенд: <http://127.0.0.1:8000> (Swagger: `/docs`).

### Frontend

```bat
cd D:\Documents\google_class_help\frontend
npm install
npm run dev
```

Vite dev-сервер: <http://localhost:5173> — проксирует `/api` на бэкенд
(см. `frontend/vite.config.ts`). Работать надо именно через `:5173`.

### OAuth в разработке

- положите OAuth-клиент (тип *Desktop app*) из Google Cloud Console в
  `backend/credentials.json` (файл git-ignored);
- токен после первой авторизации появится в `data/token.json`
  (git-ignored; каталог можно переопределить через `GC_DASHBOARD_DATA_DIR`).

### Конфигурация окружений (миграция на хостинг, §51)

Три слоя конфигурации разделены; прод-секреты не нужны ни для
разработки, ни для тестов:

| Слой | Запуск | Конфигурация |
| --- | --- | --- |
| **Local development** | `uvicorn main:app --reload` + `npm run dev` (как выше) | по умолчанию `APP_ENV=development`: Host-список — `localhost`/`127.0.0.1`, CORS — Vite-origins, БД — SQLite в `<проект>\data\`. Прод-переменные (`DATABASE_URL`, секреты Google) не читаются |
| **Hosted-разработка** (опционально) | те же команды + `GC_DASHBOARD_HOSTED=1` и `APP_BASE_URL=http://localhost:5173` | отдельный **development web OAuth-клиент** Google с redirect `http://localhost:5173/api/auth/callback` (Vite проксирует `/api` на бэкенд); локальный PostgreSQL или `DATABASE_URL` локального инстанса — прод-база не используется |
| **CI / тесты** | `pytest`, `ruff`, `pyright`, `npm run lint`, `npx vitest run` | герметично: `tests/conftest.py` поднимает свой `GC_DASHBOARD_DATA_DIR` и подставляет фейковые значения env; фронтенд-тесты (vitest) секретов не требуют вообще |
| **Production** | Docker/Compose (этап 10) | `.env` по `.env.example`: `APP_ENV=production`, `APP_BASE_URL`, web-клиент Google, `DATABASE_URL` (PostgreSQL), ключи шифрования. Секреты — только в env, никогда в Git и в ассетах |

Правила: локальная разработка **не зависит** от прод-базы и прод-секретов;
для Google OAuth в разработке используйте отдельный dev-клиент, а не
production web-клиент (`APP_ENV` и `GC_DASHBOARD_ALLOWED_HOSTS`/
`GC_DASHBOARD_CORS_ORIGINS` не задаются — дефолты development-режима).

---

## PRODUCTION BUILD

Production-сборка превращает проект в один файл `GoogleClassHelp.exe`:
FastAPI + встроенный фронтенд из `frontend/dist` + OAuth-клиент,
вшитый в бинарник (обфусцированный, без plaintext `credentials.json`).

Требования: то же, что для разработки + установленный в `.venv` Nuitka
(`.venv\Scripts\pip install nuitka`) и компилятор MSVC (Visual Studio Build
Tools); при их отсутствии Nuitka скачает MinGW64 сама
(`--assume-yes-for-downloads`).

### Сборка одной командой

```bat
build.bat
```

Скрипт выполняет:

1. чистит и пересобирает фронтенд: `npm run build` → `frontend/dist`;
2. встраивает OAuth-клиент: `backend/build_secrets.py` генерирует
   `backend/embedded_secrets.py` (XOR+base64 со случайным ключом) из
   `backend/credentials.json`;
3. генерирует иконку `assets/GoogleClassHelp.ico` (tools/make_icon.py);
4. компилирует `backend/launcher.py` в no-console onefile exe через Nuitka
   (фронтенд включается через `--include-data-dir=frontend/dist=frontend/dist`);
5. копирует результат в `release\GoogleClassHelp.exe`.

Ручной запуск этапов см. в самом `build.bat`.

### Где что лежит после сборки

| Артефакт | Путь |
| --- | --- |
| Итоговый exe | `release\GoogleClassHelp.exe` |
| Промежуточные файлы Nuitka | `build\` (можно удалять) |

### Запуск и тест release-сборки

1. Двойной клик `release\GoogleClassHelp.exe` (или запуск из терминала —
   консольное окно не появится).
2. Бэкенд стартует на `http://127.0.0.1:8000`; если порт занят чужим
   процессом — выбирается соседний свободный, браузер открывается на
   фактическом порту. Если exe уже запущен, второй инстанс **не** создаётся:
   запуск активирует работающий дашборд (фокус уже открытого окна, новая
   вкладка — только если окна нет) и завершается (ADR-0018). Если дашборд
   открыт в закреплённой/фоновой вкладке (её не видно в заголовке окна),
   новая вкладка показывает уведомление «дашборд уже открыт» с кнопкой
   *Switch to it*: переключение выполняется через service worker, потому что
   браузеры перемещают вкладку только при свежем клике — если автопопытка не
   удалась, достаточно нажать кнопку; при неудаче подсказка предложит закрыть
   вкладку вручную.
3. После старта в системном трее появляется иконка: **Open dashboard**
   (двойной клик) и **Exit**. Прячется она вместе с выходом приложения;
   без `pystray`/`Pillow` приложение работает как раньше, без иконки.
4. Для чистого теста «на машине без проекта»: скопируйте
   `release\GoogleClassHelp.exe` на любую машину с Windows и запустите.
   Нужен только доступ в интернет (Google OAuth/API).
5. Логи: `%LOCALAPPDATA%\GoogleClassHelp\logs\app.log`.

### Первый запуск / OAuth

- При отсутствии токена бэкенд поднимется, но данные появятся после
  авторизации: в дашборде нажмите вход — откроется браузер с согласием
  Google (read-only Classroom scopes, ADR-0002), токен сохранится в
  `%LOCALAPPDATA%\GoogleClassHelp\token.json`.
- Повторные запуски используют и обновляют существующий токен.
- Если браузер не открылся автоматически (например, при запуске exe под
  Wine), ссылка на страницу согласия есть в настройках дашборда и в
  `logs/app.log`: вход можно завершить по ней (ADR-0019).
- Обмен кода и обновление токена идут через httplib2 — тот же транспорт,
  которым ходят запросы к Classroom API; `requests`/`urllib3` остаётся первой
  попыткой, но его сбой больше не блокирует вход (ADR-0019).
- Проверить флоу без браузера: `.venv\Scripts\python.exe tools\check_oauth_flow.py`
  (поддельный код → Google отвечает `invalid_grant`).

### Хранение пользовательских данных (production)

```text
%LOCALAPPDATA%\GoogleClassHelp\
├── token.json        — OAuth-токен пользователя (не входит в exe)
├── classroom.db      — SQLite-кэш Classroom
├── app.lock          — pid/порт работающего инстанса (ADR-0018)
└── logs\app.log      — лог приложения (ротация 1 МБ × 3)
```

Каталог можно переопределить переменной `GC_DASHBOARD_DATA_DIR`.
В development-режиме те же файлы лежат в `<проект>\data\`.

### Ограничения и безопасность

- OAuth-клиент в exe хранится как base64-блок, а не XOR-«шифрование»:
  это кодирование, а не защита. Цель — не дать прочитать
  `credentials.json` в Блокноте; извлечь config из exe технически можно
  (это свойство любого installed-app OAuth-клиента). Если требуется
  настоящая защита секрета — не встраивайте его: положите
  `credentials.json` в `%LOCALAPPDATA%\GoogleClassHelp\` (или укажите
  `GC_DASHBOARD_CREDENTIALS`) при первом запуске, как это делают
  `gcloud` и `gh`.
- Токен каждого пользователя живёт только в `%LOCALAPPDATA%`, в exe не
  зашивается и через фронтенд не отдаётся.
- Бэкенд слушает только `127.0.0.1`.

#### Security model

- сервер слушает только `127.0.0.1`; запросы с чужим `Host` или `Origin`
  отклоняются middleware (DNS-rebinding / чужие веб-страницы);
- CORS сам по себе не защищает от не-браузерных клиентов: ограничение —
  именно локальный bind плюс Host/Origin-guard, а не CORS;
- любой локальный процесс пользователя может вызывать API (чтение кэша и
  запуск синхронизации) — приложение не защищает машину от своего же
  пользователя и на это не претендует;
- все OAuth-scopes — read-only; приложение никогда ничего не изменяет в
  Google Classroom.

### Windows-интеграция (опционально, не автоматизировано)

Ярлык в Пуск/на рабочий стол создаётся вручную из
`release\GoogleClassHelp.exe`; автозапуск и установщик намеренно не
настраиваются без отдельного запроса.
#   g o o g l e - c l a s s - h e l p 
 
