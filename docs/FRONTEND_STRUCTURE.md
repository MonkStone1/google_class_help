# Структура фронтенда

Карта слоёв, разрешённые направления импортов и бюджеты строк. Решение —
[ADR-0040](adr/adr-0040-layered-frontend-slices.md), план работ —
[`docs/plans/frontend-restructure/PLAN.md`](plans/frontend-restructure/PLAN.md).
Бэкенд прошёл тот же путь: [ADR-0039](adr/adr-0039-layered-backend-packages.md),
[`docs/BACKEND_STRUCTURE.md`](BACKEND_STRUCTURE.md).

## Слои

```text
shared/  ←  entities/  ←  features/  ←  widgets/  ←  pages/  ←  app/
```

| Слой | Что в нём | Чего быть не должно |
|---|---|---|
| `shared/` | `api/` (транспорт + эндпоинты + `schema.d.ts`), `hooks/`, `lib/` (чистые функции), `i18n/`, `types/`, `config/`, `test/`, `ui/` | домена, знания о маршрутах |
| `entities/` | `assignment/`, `course/`, `grades/`, `feedback/`, `user/`: доменные типы и правила отображения | `fetch`, `useResource`, `react-router-dom` |
| `features/` | `assignments-filter/`, `assignment-modal/`, `excel-export/`, `global-search/`, `notifications/`, `sync/`, `donate/`, `feedback-ticket/` | знания о `widgets/`, `pages/`, `app/` |
| `widgets/` | `sidebar/`, `topbar/`, `landing/`, `markdown/`: крупные блоки оболочки | знания о `pages/`, `app/` |
| `pages/` | маршрут = папка `{ui/, model/, page.css}` | `fetch` напрямую, знания о `app/` |
| `app/` | `router/`, `layouts/`, `providers/`, `boot/`, `toaster/`, `styles/`, `main.tsx` | чего-либо, кроме как импортируемого из `app/main.tsx` |

Правила, которые делают стрелку проверяемой, а не украшением:

* `shared/` **не знает** про домен: ни `entities/`, ни React-компонентов; в
  `shared/lib/` не бывает импорта `react` вовсе — там только чистые функции;
* `entities/` **не знает** про транспорт: нет `api.*`, `useResource`,
  `react-router-dom`;
* `features/` знает `entities/` и `shared/`, но не `widgets/` и не `pages/`;
* `widgets/` знает `features/`, но не `pages/`;
* `pages/` знает всё ниже себя, но не `app/`;
* `app/` знает `pages/` и ниже, и **никогда не импортируется никем**, кроме
  `app/main.tsx`.

Соседние по уровню не импортируют друг друга: `features/sync/` не знает про
`features/donate/`. Если двум фичам нужен один общий код, он поднимается в
`entities/` (правило поведения) или `shared/` (механизм).

## Публичный API слайса

Наружу у каждой папки-слайса торчит только `index.ts`:

```ts
// ✅ внутри entities/feedback/:  from "./status.ts"
// ❌ снаружи:                     from "../../entities/feedback/status.ts"
```

Это не мода: правило «импортировать публичный API слоя» — ровно то, что
позволяет переехать на другую внутреннюю структуру, не трогая десятки
вызывающих файлов. Без него каждый следующий рефакторинг снова упирается в
`shared/types`, который импортировали десятки модулей.

## Бюджеты строк

| Что | Где | Лимит |
|---|---|---|
| Транспорт API | `shared/api/client.ts` | ≤ 140 |
| Эндпоинты | `shared/api/endpoints/*` | ≤ 120 |
| Фасад API | `shared/api/index.ts` | ≤ 60 |
| Фасад типов | `shared/types/index.ts` | ≤ 80 |
| Словарь языка | `shared/i18n/locales/<lang>/*` | ≤ 120 |
| Хук | `shared/hooks/*` | ≤ 250 |
| Чистая функция | `shared/lib/*` | ≤ 250 |
| Правило домена | `entities/<домен>/**` | ≤ 250 |
| Фича | `features/<фича>/**` | ≤ 300 |
| Виджет | `widgets/<виджет>/**` | ≤ 320 |
| Страница | `pages/<route>/**` | ≤ 300 |
| Сборка приложения | `app/**` | ≤ 200 |
| CSS | `app/styles/**` | ≤ 400 |

Автоматическая проверка — `frontend/src/test/structure.test.ts` (18 тестов),
плюс те же ограничения в `eslint.config.js` через `no-restricted-imports`:
ESLint даёт подсветку в редакторе, тест — защиту в CI.

## CSS

Порядок подключения задан обходом `app/styles/index.css`, а не графом
импортов — иначе он «плавал» бы при сборке (Vite ставит стили в порядке
обхода модулей), а порядок слоёв CSS здесь контракт (ADR-0005: каждый слой
может перекрывать предыдущий):

```text
tokens → base → layout → ui → pages/common → pages/*
```

Правила разбиения, без которых страница ломается:

1. **`tokens.css` — единственное место с `:root` и `[data-theme]`.** Тёмная
   тема и `prepaint-init.js` (ADR-0034, нулевой FOUC) не меняются вообще.
2. **Файлы страниц подключаются из `index.css`, а не из компонентов.**
3. **Специфичность не меняется:** ни одно правило не получает новый селектор
   ради переезда. Класс, который сегодня перекрывает `ui.css`, продолжает
   перекрывать его из `pages/*`.

`@uiw/react-md-editor` подтягивает свой CSS локально (CSP `style-src 'self'`
без CDN, ADR-0026) — этот импорт остаётся в `widgets/markdown/`, а не
переносится в `app/styles`.

## Соглашения об именах

* `<домен>` в `entities/`, `<фича>` в `features/`, `<виджет>` в `widgets/` и
  `<route>` в `pages/` — по назначению, а не по размеру: `feedback-ticket`, а
  не `misc`.
* Никаких `utils.ts`, `helpers.ts`, `common.ts`, `misc.ts` нигде в `src/`.
  Общий код живёт в `shared/` с именем по назначению.
* Имя файла = имя, которое импортируют; `index.ts` не переэкспортирует «всё
  подряд».
* Импорты пишутся **с явным расширением** (`"../shared/api/index.ts"`):
  `tsconfig.app.json` включает `allowImportingTsExtensions`, и это зафиксировано
  как правило в ADR-0005.

## Рецепт: добавить новую страницу или фичу

1. `entities/<домен>/` — если появился новый доменный тип или правило
   отображения (`STATUS_CLASS`, бейдж, карточка). Если домен уже есть — шаг
   пропускается.
2. `features/<фича>/` — если у страницы есть **собственное действие** (панель
   фильтров, форма, модалка). Хук с загрузкой — в `features/<фича>/model/`.
3. `pages/<route>/{ui,model,page.css}` — компонент маршрута.
4. `app/router/routes.tsx` — одна строка в массиве маршрутов.
5. Ключи i18n — в `shared/i18n/locales/{en,uk,ru}/<домен>.ts`, **три файла
   одним коммитом**: `tsc` упадёт на паритете, и это правильно (ADR-0011).
6. Тест рядом: `pages/<route>/ui/<Route>.test.tsx`. Путь в `vi.mock` — строка,
   она не «следует» за символом, поэтому правится в том же коммите.

Ключевой вопрос при выборе места: *это про **что** (домен), про **действие**
(фича), про **блок интерфейса** (виджет) или про **маршрут** (страница)?*

### Рецепт: добавить формат экспорта

`features/excel-export/` (ADR-0041) разделён так, что новый формат — это
**один файл плюс одна строка**:

1. `features/excel-export/presets/<имя>.ts` — колонки и их порядок, правила
   преобразования текста, формат даты, ширины, имя листа, суффикс имени файла.
   Текстовые колонки несут собственную функцию `text: (source) => string`,
   поэтому движок не знает, какая колонка «контент», а какая «домашняя
   работа».
2. `model/useExportRows.ts` — одна строка `registerPreset(<пресет>)`.
3. `shared/i18n/locales/{en,uk,ru}/export.ts` — ключ `export.preset.<ид>`,
   **три файла одним коммитом**.

`engine/`, тесты движка, страница и `baseline.test.ts` при этом **не
меняются**. Заголовки колонок в пресете остаются на языке формата: это контракт
с внешним импортом, а не интерфейс, поэтому локализовать их нельзя.

## Контракт, который нельзя ломать переездом

* HTTP-пути, методы и `response_model` бэкенда: `frontend/openapi.json`
  генерируется `tools/dump_openapi.py`, а `src/shared/api/schema.d.ts` —
  через `npm run gen:api:file` (`openapi-typescript`). Ни один хендлер не
  переименовывается, ручные зеркала бэкенд-схем не появляются.
* Классы, на которые смотрят тесты: `donate-qr`, `active`,
  `ticket-message-user`. Их переименование роняет тесты — значит оно
  недопустимо молча.
* `prepaint-init.js` и порядок CSS (ADR-0005, ADR-0034).
* `frontend/openapi.json`, `tools/dump_openapi.py`, `build.bat` — конвейер
  сборки не переезжает.