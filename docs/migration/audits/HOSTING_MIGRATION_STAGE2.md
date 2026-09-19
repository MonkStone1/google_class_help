# Этап 2 — Web OAuth и сессии: результат

Реализация этапа 2 миграции на хостинг
(`docs/migration/Web OAuth and Sessions Part 1/2 num in query 2.md`, §4–§9).
Опорные документы: аудит `HOSTING_MIGRATION_AUDIT.md` (рядом, папка
`docs/migration/audits/`), решение
`docs/adr/adr-0020-hosted-web-oauth-and-sessions.md`.

Дата: 2026-09-18.

## 1. Что сделано (по пунктам промпта)

| Пункт | Требование | Реализация |
| --- | --- | --- |
| §4 | Отдельный Web-клиент Google, HTTPS redirect | `config.hosted_oauth_client_config()` — только из env (`GOOGLE_CLIENT_ID/SECRET/REDIRECT_URI`, redirect выводится из `APP_BASE_URL`); desktop-клиент не задействован |
| §5 | Серверный web OAuth-флоу | `GET /api/auth/login` → 302 на Google; `GET /api/auth/callback`; случайный `state` в БД, PKCE S256, привязка к браузеру через nonce-cookie, одноразовость, обмен кода один раз |
| §5 | Не доверять фронтенду | `user_id` нигде не принимается; личность — только `sub` из Google userinfo |
| §5 | Opaque-сессия в HttpOnly/Secure/SameSite cookie | cookie `gch_session`, хранится только SHA-256 хеш; троттлинг `last_seen_at` |
| §6 | `users` / `sessions` / `oauth_tokens` | `backend/models_auth.py`; сущность-владелец у токенов и у сессий |
| §6 | Сессии отзываются независимо от Google-гранта; решение по logout | logout отзывает сессию, refresh token остаётся серверно (ADR-0020) |
| §7 | Идентичность по стабильному subject | `_upsert_user` по `(provider, provider_subject)`; смена email обновляет профиль, не создаёт второго пользователя |
| §8 | Убрать единый `TOKEN_FILE` | токены в `oauth_tokens`, шифрование Fernet (`token_crypto.py`), ключ из env; desktop `token.json` не используется hosted-путём |
| §9 | Разделение секретов, `.env.example`, без утечек | `.env.example`, `.gitignore` (+`.env`), `tools/generate_hosted_secrets.py`; секреты только из env |

## 2. Файлы

Добавлено:

- `backend/hosted_auth.py` — web OAuth, сессии, `get_current_user`,
  `require_google_credentials`, `get_valid_credentials_for`, роутер `/api/auth/*`.
- `backend/models_auth.py` — `users`, `sessions`, `oauth_tokens`,
  `oauth_login_states`.
- `backend/token_crypto.py` — шифрование токенов at-rest (Fernet, `enc.v1:`).
- `tests/test_hosted_auth.py` — 19 тестов.
- `.env.example`, `.gitleaks.toml`, `tools/generate_hosted_secrets.py`,
  `docs/adr/adr-0020-hosted-web-oauth-and-sessions.md`.

Изменено (desktop-поведение сохранено):

- `backend/config.py` — `HOSTED_MODE`, env-конфиг web-клиента.
- `backend/main.py` — `create_app(hosted: bool)`; hosted-роутер + session-gate;
  desktop-ветка без изменений.
- `backend/auth.py` — `post_token_request`, `refresh_credentials`,
  `credentials_from_payload` сделаны публичными (переиспользование транспорта).
- `backend/database.py` — `init_db` создаёт и auth-таблицы; `get_db` типизирован.
- `backend/requirements.txt` — `cryptography>=42`.
- `tests/conftest.py` — герметичные hosted-env и фикстура `hosted_client`.
- `tools/check_oauth_flow.py` — вызов переименованной функции.
- `.gitignore` — `.env`, `backend/.env`.

## 3. Закрытые пункты аудита

| Аудит | Было | Стало |
| --- | --- | --- |
| A2 | глобальный `_login_state` | hosted: per-attempt `state` в БД + nonce-cookie |
| A3 | `_refresh_lock` без ключа | per-user refresh-лок (`_refresh_lock_for`) |
| A5 | `require_credentials()` (один пользователь) | `require_google_credentials` по сессии |
| A6 | после логина — глобальный sync | hosted: глобальный sync выключен (per-user — этап 5) |
| C1 | один `token.json` | `oauth_tokens` по `user_id` |
| C2 | `embedded_secrets` для секретов | hosted — только env; embedding не используется |
| P1/P2 | кэш профиля без ключа, статус одного аккаунта | hosted: профиль из `users`, статус из сессии |

Категории глобального состояния §4 аудита: 3–4 (кэш/пользовательское
состояние) перенесены в session/DB-слой; категории 1–2 сохранены.

## 4. Тесты

`tests/test_hosted_auth.py` (всего в проекте 36 тестов, все зелёные):

- gate: data-ручки → 401 без сессии; `/api/health` и `/api/auth/*` доступны;
  `POST /api/auth/login` в hosted → 405 (desktop-loopback недоступен);
- login: redirect содержит state/PKCE/redirect_uri/scope, cookie-nonce,
  запись в `oauth_login_states`; `redirect_to` не уводит на чужой origin;
- callback: неизвестный state, чужой nonce, отсутствие кода — отклоняются;
  state одноразовый;
- успешный вход: пользователь по `sub`, токены зашифрованы (`enc.v1:`),
  пароль-плейнтекста нет, сессия хранит только хеш, статус из БД, данные
  доступны;
- повторный вход = тот же пользователь; второй браузер = вторая сессия;
  смена email = тот же пользователь; deactivated → 401;
- logout: сессия отозвана, Google-грант сохранён;
- refresh: истёкший токен обновляется и перезаписывается шифрованно;
  неудачный refresh → signed-out; старый набор scopes → повторный consent;
  валидный токен не рефрешится;
- crypto: roundtrip, отказ на plaintext, отказ при неверном ключе.

## 5. Проверки

- `pytest`: 36 passed.
- `ruff check` / `ruff format --check`: чисто.
- `pyright` (1.1.390, `pyrightconfig.json`): 0 errors.
- `gitleaks` с проектным `.gitleaks.toml`: 0 находок.

## 6. Секреты: проверка и статус

- В отслеживаемых исходниках реальных секретов нет; в новом коде —
  только имена env-переменных.
- Реальный desktop client secret лежит локально в git-ignored файлах
  (`backend/credentials.json`, `backend/embedded_secrets.py`,
  `data/token.json`). Проверено: эти файлы не отслеживаются и **никогда не
  попадали в историю git** (`git log -S 'GOCSPX' --all` → 0 коммитов;
  удалённый `google_class_help.rar` в истории этот секрет не содержит).
  Ротация не требуется с точки зрения репозитория; desktop-клиент — не
  hosted web-клиент, и hosted-контур его не читает.
- `.gitleaks.toml` исключает из сканирования генерируемые артефакты и
  git-ignored локальные хранилища; отслеживаемые исходники сканируются
  как прежде.

## 7. Что осталось за пределами этапа 2 (и почему)

- **User-scoping данных** (`get_current_user` в каждой ручке, IDOR,
  `DELETE /api/cache`, purge) — этап 4. До него hosted-версию наружу не
  выставлять: session-gate закрывает `/api/*`, но данные ещё общие.
- **PostgreSQL + Alembic**, user-скоуп схемы — этап 3 (сейчас таблицы
  создаёт `create_all`, SQLite совместим).
- **Per-user sync/планировщик** — этап 5; в hosted-режиме глобальный цикл
  отключён.
- **Фронтенд (cookie/401), CORS/Host/trusted proxy** — этап 7;
  **CSRF, security headers, `__Host-`, HTTPS/HSTS** — этап 8.
- `__Host-`-префикс cookie и полная CSRF-политика не введены; базовая
  защита — `SameSite=Lax` (ADR-0020).