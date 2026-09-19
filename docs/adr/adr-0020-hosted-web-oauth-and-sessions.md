# ADR-0020: Хостед-режим — web OAuth, серверные сессии и шифрование токенов

Дата: 2026-09-18
Статус: Accepted
Связанные: [ADR-0002](adr-0002-minimal-oauth-scopes.md), [ADR-0003](adr-0003-sqlite-cache-and-sync.md), [ADR-0016](adr-0016-production-nuitka-packaging.md), [ADR-0019](adr-0019-oauth-flow-owned-by-app.md)
Источник: `docs/migration/Web OAuth and Sessions Part 1/2 num in query 2.md` (§4–§9), аудит `docs/migration/audits/HOSTING_MIGRATION_AUDIT.md`.

## Контекст

Desktop-сборка аутентифицируется loopback OAuth-флоу (ADR-0019): клиент
Google типа «Desktop», callback на `127.0.0.1`, один `token.json` на
процесс. Для хостед-версии это неприемлемо (аудит §2):

- нет понятия «пользователь приложения»: все `/api/*`-ручки читают один
  общий SQLite-кэш, то есть без user-scoping это IDOR по умолчанию
  (аудит P3, риск 1);
- `TOKEN_FILE` — один набор креденшелов на процесс (A1, C1);
- `embedded_secrets.py` (base64) — не механизм хранения серверных
  секретов (C2, §9);
- глобальное состояние логина/рефреша/профиля не привязано к
  пользователю (A2, A3, P1, P2).

Этап 2 вводит модель приложения (§6):

```text
Google account → local User → OAuth credentials → session(s)
```

## Решение

### 1. Отдельный режим запуска, desktop не меняется

- Хостед-режим включается `GC_DASHBOARD_HOSTED=1` (`config.HOSTED_MODE`).
- `main.create_app(hosted: bool)` — фабрика приложения: desktop-путь
  остаётся прежним (loopback OAuth, host-guard, глобальный фоновый sync),
  hosted-путь монтирует `hosted_auth.router` и session-gate.
- Desktop и hosted сосуществуют в одном коде, но выбираются на уровне
  приложения, а не глобального мутабельного флага; desktop-тесты
  продолжают работать без hosted-переменных.

### 2. Web OAuth-флоу принадлежит серверу (§4, §5)

- Отдельный клиент Google типа **Web application**; конфигурация только
  из env (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
  `GOOGLE_REDIRECT_URI` или `APP_BASE_URL`). Desktop-клиент и
  `embedded_secrets.py` в hosted-контуре не используются.
- `GET /api/auth/login` → 302 на Google; `GET /api/auth/callback`
  обрабатывает redirect.
- На каждую попытку логина генерируются:
  - `state` — случайный, хранится серверно в таблице
    `oauth_login_states`, одноразовый;
  - browser-nonce — короткоживущая HttpOnly-cookie, привязывает попытку к
    инициировавшему браузеру;
  - PKCE S256 (`code_verifier` хранится рядом со `state`).
- Несовпадение/отсутствие state или nonce, истёкшая попытка и ошибка
  Google отклоняются; попытка сгорает при первой предъявленной
  callback-попытке. Код обменивается ровно один раз (запись state
  удаляется до сетевого обмена).
- Личность определяется по стабильному Google subject (`sub` из
  OIDC userinfo), не по email (§7). Email/имя — локальные поля профиля,
  обновляются при каждом входе; deactivated-пользователь отклоняется.
- Никаких `user_id` из фронтенда: identity берётся только у Google.

### 3. Сессии — серверные, opaque, отзываемые (§6)

- Cookie `gch_session`: `HttpOnly; Secure; SameSite=Lax; Path=/`, без
  `Domain`. `Secure` включается по схеме запроса (за Caddy —
  `X-Forwarded-Proto`).
- В БД хранится только SHA-256 хеш токена; сырой токен живёт лишь в
  cookie. Срок жизни — 14 дней, явное истечение; touch `last_seen_at` не
  чаще раза в минуту.
- Сессии отзываются независимо от Google-гранта.
- **Решение о logout:** logout отзывает текущую сессию, но **не** удаляет
  Google refresh token и не отзывает грант на стороне Google —
  refresh token остаётся на сервере, чтобы следующий вход не требовал
  повторного consent. Privacy-ориентированное удаление креденшелов —
  отдельное действие «удалить аккаунт» (будущее).
- Префикс `__Host-` пока не используется (нужен только HTTPS и
  `Path=/`); его добавление — предмет этапа 8.

### 4. Токены OAuth — в БД, зашифрованы (§8)

- `oauth_tokens(user_id PK, access_token, refresh_token, token_uri,
  scopes, expires_at, …)`, одна строка на пользователя.
- Шифрование — Fernet (аутентифицированное, `cryptography`), ключ
  `GC_DASHBOARD_OAUTH_TOKEN_ENCRYPTION_KEY` — только из env, вне БД и вне
  репозитория. Ciphertext помечается префиксом `enc.v1:`; расшифровка
  значения без префикса — ошибка, а не тихий пропуск plaintext.
- Обновление access token сериализуется per-user локом и сохраняется
  зашифрованным. Невалидный/отсутствующий refresh token → 401 и
  повторный consent.
- Токены никогда не возвращаются в JSON, не кладутся в cookie и не
  логируются.

### 5. Нормализация секретов (§9)

- `client_secret`, ключ шифрования токенов, пароль PostgreSQL — только
  env/secret-механизм хостинга; `.env.example` содержит лишь
  плейсхолдеры, реальный `.env` — в `.gitignore`.
- Сессионный signing-key не нужен: сессии opaque и хранятся серверно
  (решение зафиксировано здесь).
- Статический `SESSION_SECRET` из §30 не вводится.

### 6. Session-gate до user-scoping

В hosted-режиме middleware требует валидную сессию для всех `/api/*`,
кроме `/api/health` и `/api/auth/*`. Это закрывает доступ к данным без
входа (аудит, риск 1) **до** появления `get_current_user`-скоупинга в
каждой ручке (этап 4). Наружу hosted-версию до этапа 4 не выставлять.

### 7. Схема и хранилище

Новые таблицы (`users`, `sessions`, `oauth_tokens`,
`oauth_login_states`) создаются тем же `Base.metadata.create_all`, что и
кэш (ADR-0003). Переход на PostgreSQL и Alembic — этап 3; SQLite
остаётся совместимым до него.

## Последствия

- Плюс: появляется настоящая аутентификация и модель пользователя;
  токены защищены at-rest; desktop-поставка не затронута.
- Плюс: state/PKCE/nonce и одноразовость закрывают login-CSRF и подмену
  кода; `get_current_user`/`require_google_credentials` — готовые швы для
  этапов 4–5.
- Минус/долг: данные `/api/*` ещё не скоупированы по пользователю
  (этап 4); фоновый sync в hosted-режиме отключён до per-user планировщика
  (этап 5); CSRF-политика полная — этап 8; host/origin-валидация
  прод-домена — этап 7; `__Host-`-префикс и HSTS — этап 8.
- Профиль пользователя в hosted-режиме читается из `users`, кэш профиля
  процесса (P1/P2) в hosted-пути не используется.
- Глобальный `auth.py`-флоу сохранён для desktop; общие транспорты
  (`post_token_request`, `refresh_credentials`, `credentials_from_payload`)
  сделаны публичными, чтобы hosted-флоу их переиспользовал.
