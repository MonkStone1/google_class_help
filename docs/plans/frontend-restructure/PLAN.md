# План реструктуризации фронтенда (ADR-0040)

Статус: план готов к исполнению (ни один этап не выполнен)
Дата: 2026-10-02
Источник проблемы: `frontend/src/` — 65 файлов исходников в четырёх плоских
папках (`pages/`, `components/`, `lib/`, `context/`) плюс 10 модулей в корне;
`pages/` и `components/` не различают «свой код фичи» и «общий код», а
`components/` импортируется отовсюду одинаково. Ни одного автоматического
ограничения, которое помешало бы этому повториться.

Полный план: [`docs/plans/frontend-restructure/PLAN.md`](PLAN.md) ·
Правила слоёв: [`docs/FRONTEND_STRUCTURE.md`](../../FRONTEND_STRUCTURE.md) ·
Решение: [`ADR-0040`](../../adr/adr-0040-layered-frontend-slices.md)

Бэкенд прошёл тот же путь: [`docs/plans/backend-restructure/PLAN.md`](../backend-restructure/PLAN.md),
[`docs/BACKEND_STRUCTURE.md`](../../BACKEND_STRUCTURE.md),
[ADR-0039](../../adr/adr-0039-layered-backend-packages.md). Этот план — его
фронтендовый двойник: та же форма, тот же приём (слои + правила + проверки в CI),
другие срезы.

---

## 0. Как читать этот план

| § | Что это | Состояние |
|---|---|---|
| 1 | Диагностика — что именно мешает редактировать | факт, снят с кода |
| 2 | Жёсткие ограничения — почему переезд вообще возможен | факт |
| 3 | Целевая структура `frontend/src/`: слои, правила, разбор `types.ts`, i18n, CSS | проектное решение |
| 4 | Этап 0: страховка и документация | не начат |
| 5 | Карта переездов «сейчас → станет» | проектное решение |
| 6 | Этапы 1–10, порядок, что правится в том же коммите | не начат |
| 7 | Ограждения: 18 проверок + eslint + CI | не начат |
| 8 | Бюджеты строк | проектное решение |
| 9 | Рецепт: добавить новую фичу | проектное решение |
| 10–12 | Что не трогаем, риски и откат, альтернативы | факт |
| 13 | Итог | — |

Цифры §1 сняты с рабочей копии на коммите `34511b9`; каждое утверждение о
порядке импортов проверено обходом всех 103 файлов под `frontend/src`.

**Эта редакция первая.** Ни один этап не выполнен — это план, а не отчёт.

---

## 1. Диагностика (факты, снятые с кода)

### 1.1 Масштаб

| Срез | Файлов | Строк |
|---|---|---|
| Исходники (без тестов и без `api-schema.d.ts`) | 65 | 11 754 |
| Тесты (`*.test.ts(x)`) | 33 | 5 185 |
| CSS (`styles/`) | 4 | 3 026 |
| `api-schema.d.ts` (генерируется, руками не правится) | 1 | 2 862 |

В тестах 48 `describe` и 204 `it` — покрытие есть, и оно переезжает вместе с
кодом, а не остаётся на старых путях.

### 1.2 Файлы-толстяки

| Строк | Файл | Смешанные ответственности |
|---|---|---|
| **537** | `context/DataContext.tsx` | auth + sync + courses + три контекста + поллинг OAuth + загрузка среза |
| **504 / 493 / 492** | `i18n/{en,ru,uk}.ts` | три словаря по 395 ключей, ключи не сгруппированы |
| **392** | `lib/assignmentFilters.ts` | парсинг URL + фильтрация + сортировка + нормализация настроек |
| **367** | `pages/Assignments.tsx` | страница + 16 импортов из `assignmentFilters` + URL-синхронизация |
| **362** | `pages/Settings.tsx` | три темы настроек в одном файле |
| **346** | `api.ts` | транспорт (`request`/`requestForm`/401-хук) + **34 метода** каталога |
| **328** | `components/Landing.tsx` | публичная страница, живёт в `components/` |
| **327** | `pages/AdminFeedback.tsx` | страница + own-copy словаря статусов |
| **317** | `pages/AdminAdmins.tsx` | реестр админов + модалка + подтверждение удаления |
| **316** | `components/TopBar.tsx` | поиск + синк + уведомления + `buildNotifications` |
| **308** | `types.ts` | wire-алиасы + UI-типы + предикаты ролей; импортируют **57 файлов** |
| **298** | `pages/CalendarPage.tsx` | три режима сетки в одном файле |
| **296** | `context/SettingsContext.tsx` | тема + язык + фильтры + уведомления + localStorage |
| **288** | `components/FilterPanel.tsx` | панель + свои словари facet-меток |
| **1 556** | `styles/pages.css` | 8 несвязанных блоков, от `.subject-grid` до реестра админов |
| **1 123** | `styles/components.css` | 13 блоков, от кнопок до центра уведомлений |

### 1.3 Дефекты, из-за которых редактировать неудобно

Это не «файлы большие» — это конкретные правки, которые ломаются или
дублируются. Каждый пункт проверен на коде.

1. **Страница импортирует страницу.** `pages/FeedbackTickets.tsx` экспортирует
   `STATUS_CLASS`, который импортируют `AdminDashboard`, `AdminFeedback`,
   `AdminFeedbackTicket` и `FeedbackTicket`. Словарь `STATUS_LABEL` при этом
   **скопирован** в тех же четырёх файлах (в `FeedbackTickets` — типизированный
   `Record<FeedbackStatus, I18nKey>`, в остальных — `Record<string, I18nKey>`).
   Правка статуса на бэкенде требует ручной правки пяти файлов, и одна из них
   забудется.

2. **Один и тот же fetch-эффект написан 6 раз.** `AdminAdmins`,
   `AdminDashboard`, `AdminFeedback`, `AdminFeedbackTicket`, `FeedbackTicket`,
   `FeedbackTickets` — в каждом `new AbortController()` + `let cancelled` +
   `.catch` с `status === 0` и `setError(...)`. При этом `lib/resource.ts` уже
   даёт дедупликацию, отмену и TTL, и он используется в 4 файлах. Шесть копий
   существуют не потому, что так лучше, а потому, что общего хука для
   «загрузить один раз» не было.

3. **`lib/` смешивает чистые функции и React.** `assignmentFilters`, `search`,
   `cn` — чистые; `resource` и `signInChallenge` импортируют `react`. Правило
   «lib-слой чистый» записано комментарием в `eslint.config.js` («The lib layer
   is deliberately pure») и **не проверяется ничем**.

4. **`lib/search.ts` и `lib/assignmentFilters.ts` зависят от `types.ts`**, то
   есть «низкий» слой тянет доменный тип. Следствие: `shared/lib` в любой
   схеме слоёв не сможет содержать эти файлы без нарушения правила.

5. **Три словаря i18n синхронизируются вручную.** 395 ключей × 3 языка,
   30 префиксов: `admin` — 48 ключей, `feedback` — 46, `settings` — 43,
   `landing` — 42. Ключи домена размазаны по трём файлам, и добавление
   «ещё одного ключа в фичу админов» трогает все три файла сразу. Типобезопасность
   есть (`satisfies Record<I18nKey, string>`), но **структуры** у словарей нет.

6. **282 уникальных литерала `className`** на 4 CSS-файла. `pages.css` —
   единый ком без границ по фичам. Стили админки лежат в том же файле, что и
   стили публичного лендинга.

7. **Нет ограждений вообще.** В `eslint.config.js` включены только
   `react-hooks/*` и `no-explicit-any`; `no-restricted-imports` не настроен.
   Структурного теста нет, бюджетов строк нет. Джоб `frontend` в CI
   (`.github/workflows/ci.yml`) выполняет `npm run lint` и `npm test`, но **не
   выполняет `npm run build`** — то есть `tsc -b` в CI не проверяется вовсе.

### 1.4 Что уже хорошо и обязано сохраниться

* `types.ts` опирается на **сгенерированную** `api-schema.d.ts`
  (`openapi-typescript`, `npm run gen:api:file`), а не на ручные зеркала
  бэкенд-схем. Это лучшее, что есть в слое типов; §3 строит структуру вокруг
  него, а не вместо него.
* Три узких контекста (`useAuth` / `useSync` / `useCourses`) уже выделены в
  `DataContext.tsx` — идея верная, не доведена до конца.
* 33 файла тестов лежат рядом с кодом, а не в отдельном дереве.
* CSS на дизайн-токенах, без Tailwind (ADR-0005) — не трогаем.

---

## 2. Жёсткие ограничения

Переезд возможен не потому, что файлов мало, а потому что соблюдены девять
условий. Каждое проверено на коде; нарушение любого из них делает «просто
переложить файлы» нерабочим вариантом.

1. **Контракт бэкенда не переезжает.** HTTP-пути, методы и `response_model`
   остаются как есть — фронтенд меняет только свои пути. `frontend/openapi.json`
   (2 438 строк) и `api-schema.d.ts` (2 862) генерируются из OpenAPI бэкенда;
   ни один хендлер не переименовывается.

2. **Типы остаются сгенерированными.** `types.ts` — тонкий слой над
   `api-schema.d.ts`, а не новый источник правды. Всё, что переезжает в
   `entities/`, продолжает выводиться из `Wire<>`/`DeepRequired<>`; ручные
   зеркала бэкенд-схем не появляются.

3. **`vitest.config.ts` ищет тесты по `src/**/*.test.{ts,tsx}`.** Тесты лежат
   рядом с кодом, поэтому переезд файла без его `.test` невозможен — они
   переезжают тем же коммитом. Всего 33 файла, 204 `it`.

4. **Моки привязаны к путям, и это главная хрупкость.** Проверено обходом:
   * `vi.mock("../api.ts")` — **3 файла** (`AdminAdmins`, `AdminFeedback`,
     `FeedbackTicket`);
   * импорт `{ api }` из `"../api.ts"` — **7 файлов**;
   * `vi.mock(".../context/DataContext.tsx")` — **10 файлов**;
   * `vi.mock(".../context/SettingsContext.tsx")` — **4 файла**;
   * `vi.mock(".../lib/signInChallenge.ts")` — **2 файла**.

   Путь в `vi.mock` — это строка: она не «следует» за символом. Каждый такой
   файл правится в том же коммите, что и код. Список — не «примерно», он
   полный: собран регексом по `frontend/src`.

5. **Порядок CSS фиксирован словами, а не конвенцией.** `main.tsx` импортирует
   `base.css` → `layout.css` → `components.css` → `pages.css`, и комментарий
   «Order matters: each layer may override the previous one (ADR-0005)» — это
   контракт: `pages.css` перекрывает `components.css` нарочно. Разбиение CSS
   (§3.4) сохраняет этот порядок и не меняет специфичность ни одного правила.

6. **`@uiw/react-md-editor` тянет CSS локально.** `MarkdownField.tsx` импортирует
   `markdown-editor.css` сам — из-за CSP `style-src 'self' 'unsafe-inline'`
   без CDN (ADR-0026). Этот импорт остаётся в `features/markdown/`, а не
   переносится в `app/styles`.

7. **Импорты пишутся с явным расширением.** `tsconfig.app.json` включает
   `allowImportingTsExtensions`, и ADR-0005 фиксирует это как правило. Новые
   пути пишутся как `"../shared/api/index.ts"`, а не `"../shared/api"`.

8. **Классы в тестах — часть контракта.** `DonateCards.test.tsx` ждёт
   `className === "donate-qr"`, `Sidebars.test.tsx` — `toContain("active")`,
   `TicketMessage.test.tsx` — `toContain("ticket-message-user")`. Переименование
   этих классов роняет тесты; значит, оно недопустимо молча.

9. **Названия слоёв не должны пересекаться с пакетами.** На бэкенде `google/`
   затенил бы `google-auth` из `site-packages`, и пришлось придумать `gapi/`
   (§3.1 backend-плана). Фронтенд под Node-резолвингом не имеет этого риска,
   но **названия проверяются всё равно** — `vite` резолвит через Node.

---

## 3. Целевая структура

### 3.1 Слои

Пять слоёв. Слой — это каталог верхнего уровня `src/`, а не подкаталог.

```text
frontend/src/
├── app/                        # сборка: провайдеры, роутер, layouts, стили
│   ├── main.tsx                # ← корень/src/main.tsx
│   ├── App.tsx                 # провайдеры + ветвление splash / landing / sign-in / shell
│   ├── router/
│   │   ├── routes.tsx          # маршруты как ДАННЫЕ: [{ path, element, guard }]
│   │   ├── guards.tsx          # RequireAdmin, RequireSuperAdmin, RequireAuth
│   │   └── AppRouter.tsx       # <Routes> по данным + Outlet в layout
│   ├── layouts/
│   │   ├── AppLayout.tsx       # sidebar + topbar + <main class="app-content">
│   │   └── AdminLayout.tsx     # admin-sidebar + Outlet, без TopBar (ADR-0036)
│   ├── providers/
│   │   └── AppProviders.tsx    # SettingsProvider → DataProvider → Toaster
│   ├── boot/
│   │   ├── BootSplash.tsx      # ← components/BootSplash.tsx
│   │   └── bootGate.ts         # вычисление hadSession / showLanding / signedOut
│   ├── toaster/
│   │   ├── Toaster.tsx         # ← components/Toaster.tsx
│   │   └── SyncToaster.tsx     # ← components/SyncToaster.tsx
│   └── styles/
│       ├── index.css           # @import-порядок (ADR-0005)
│       ├── tokens.css          # ← base.css: :root + [data-theme] + reset
│       ├── base.css            # типографика и элементы
│       ├── layout.css          # app-layout / app-main / app-content / page
│       ├── ui.css              # ← components.css: кнопки, карточки, бейджи, модалка
│       └── pages/*.css         # ← pages.css, разбит по слайсам (§3.4)
│
├── pages/                      # маршрут = папка { ui/, model/, page.css }
│   ├── dashboard/ grades/ calendar/ subjects/ subject/ assignments/
│   ├── assignment/ teacher-grades/ student-grades/ settings/
│   ├── feedback/
│   │   ├── home/ new/ tickets/ ticket/
│   └── admin/
│       ├── dashboard/ feedback/ ticket/ admins/
│
├── widgets/                    # крупные блоки оболочки, знают про контекст
│   ├── sidebar/                # Sidebar, SidebarNav, AdminSidebar, ITEMS
│   ├── topbar/                 # TopBar, SyncTime, SearchResults, NotificationCenter
│   ├── landing/                # Landing, SignIn, useSignInChallenge
│   └── markdown/               # Markdown (рендер) + MarkdownField (редактор)
│
├── features/                   # изолированные пользовательские действия
│   ├── assignments-filter/     # FilterPanel + assignmentFilters + URL-синхронизация
│   ├── assignment-modal/       # AssignmentModal + чтение через useResource
│   ├── global-search/          # search.ts + выпадающий список
│   ├── notifications/          # buildNotifications + центр уведомлений
│   ├── sync/                   # кнопка синка, restart зависшего, stuck-логика
│   ├── donate/                 # DonateCards + банки
│   └── feedback-ticket/        # TicketMessage, TicketConversation, AttachmentList
│
├── entities/                   # домен: типы + правила отображения, без fetcha
│   ├── assignment/             # типы, Badges (Status/Priority/Grade), SubmissionStatus
│   ├── course/                 # типы, SubjectCards, CourseCard
│   ├── feedback/               # типы, STATUS_CLASS, STATUS_LABEL, Attachment
│   ├── user/                   # AuthStatus, isAdminUser, isSuperAdminUser
│   └── grades/                 # типы, GradeBadge, GradeHistorySparkline
│
└── shared/                     # ноль домена, ноль React-компонентов
    ├── api/
    │   ├── client.ts           # request/requestForm/ApiError/401-хук (≤140)
    │   ├── endpoints/{auth,status,sync,courses,assignments,grades,feedback,admin}.ts
    │   ├── schema.d.ts         # ← api-schema.d.ts (ГЕНЕРИРУЕТСЯ, не правится)
    │   └── index.ts            # фасад `api` (≤60)
    ├── hooks/
    │   ├── useResource.ts      # ← lib/resource.ts
    │   └── useAsyncResource.ts # НОВЫЙ: общий хук, убивает 6 копий fetch-эффекта
    ├── lib/                    # ТОЛЬКО чистые функции, ноль react-импортов
    │   ├── cn.ts  dates.ts  url.ts
    ├── i18n/
    │   ├── index.ts            # useI18n, I18nKey, LANGUAGE_OPTIONS
    │   └── locales/{en,uk,ru}/{common,assignments,grades,settings,feedback,admin,landing}.ts
    ├── types/                  # ← types.ts, разбит по доменам
    └── config/
        └── constants.ts        # навигация, дефолты, TTL
```

### 3.2 Единственная разрешённая стрелка

```text
shared/  ←  entities/  ←  features/  ←  widgets/  ←  pages/  ←  app/
```

Правило, которое делает это не украшением:

* `shared/` **не знает** про домен: ни `entities/`, ни React-компонентов;
* `entities/` **не знает** про `fetch`: нет `api.*`, нет `useResource`, нет
  `pages/`, `widgets/`, `features/`;
* `features/` знает `entities/` и `shared/`, но не `widgets/` и не `pages/`;
* `widgets/` знает `features/`, но не `pages/`;
* `pages/` знает всё ниже себя, но не `app/`;
* `app/` знает `pages/` и ниже; **`app/` никогда не импортируется никем**,
  кроме `main.tsx`.

Соседние по уровню не импортируют друг друга: `features/feedback-ticket/` не
знает про `features/sync/`. Если двум фичам нужен один общий код — он
поднимается в `entities/` (правило поведения) или `shared/` (механизм).

### 3.3 Public API слайса

Каждая папка слайса имеет `index.ts`, и наружу торчит только он:

```ts
// ✅ внутри entities/feedback/:  from "./status.ts"
// ❌ снаружи:                     from "../../entities/feedback/status.ts"
```

Причина — не мода: правило «импортировать публичный API слоя» ровно то, что
позволяет переехать на другую внутреннюю структуру, не трогая 20 вызывающих
файлов. Без него каждый следующий рефакторинг снова упирается в 57
импортирующих `types.ts` (§1.2).

### 3.4 Что происходит с `shared/types.ts` и словарями i18n

Самое тонкое место — `types.ts`. Он импортируется **57 файлами**, поэтому его
нельзя «просто поделить и забыть»: сначала появляется фасад, который
перенаправляет старые имена, и только после переезда всех потребителей
исчезает.

```text
shared/types/
├── index.ts        # ФАСАД: реэкспортирует всё из доменных файлов (≤80)
├── wire.ts         # DeepRequired, Wire<K> — единственное место, знающее schema.d.ts
├── assignment.ts   # Assignment, AssignmentDetail, Submission, SubmissionStatus, Priority
├── course.ts       # Course, CourseDetail, UserRole
├── grades.ts       # GradeColumn, SubmissionCell, StudentGradeRow, TeacherGrades…
├── feedback.ts     # FeedbackStatus, TicketMessage, AdminTicket, Administrator
├── user.ts         # AuthStatus, SyncResult, isAdminUser, isSuperAdminUser
└── ui.ts           # AppSettings, ThemeMode, Language, SortKey, AssignmentsFilter…
```

`isAdminUser` / `isSuperAdminUser` уезжают в `entities/user/`, а не в
`shared/types/`: это правило предметной области, а не тип. В `shared/types`
остаются только объявления.

Словари i18n получают такую же сетку: `locales/<lang>/<домен>.ts`, а
`i18n/index.ts` склеивает семь файлов в один словарь и **по-прежнему
выводит** `I18nKey` из `en`. Проверка паритета `uk`/`ru` относительно `en`
сохраняется — `satisfies Record<I18nKey, string>` переезжает в
`locales/<lang>/index.ts`, иначе гарантия ADR-0011 («пропавшая трансляция
роняет сборку») ослабнет.

### 3.5 Как делится CSS

`pages.css` (1 556 строк) режется по уже проведённым в нём комментариям и
границам блоков — доменных секций девять, и восемь из них уже подписаны
(`Subjects`, `Calendar`, `Grades`, `Settings`, `Public landing`,
`feedback (ADR-0035)`, `Markdown editor`, `administrator registry (ADR-0036)`):

| Блок `pages.css` | Строки | Куда |
|---|---|---|
| `.subject-grid`, `.stack`, `.meta-*`, `.assignment-grid` | 1–32 | `app/styles/pages/common.css` |
| Subjects | 33–216 | `pages/subjects/page.css`, `pages/subject/page.css` |
| Calendar | 217–367 | `pages/calendar/page.css` |
| Grades + filter chips | 368–500 | `pages/grades/page.css`, `features/assignments-filter/chips.css` |
| Settings + Responsive | 501–808 | `pages/settings/page.css`, `app/styles/responsive.css` |
| Public landing | 809–1098 | `widgets/landing/landing.css` |
| Feedback (ADR-0035) | 1099–1259 | `features/feedback-ticket/*.css` |
| Markdown editor | 1260–1527 | `widgets/markdown/editor.css` |
| Administrator registry (ADR-0036) | 1528–1556 | `pages/admin/admins/page.css` |

Правила, без которых разбиение ломает страницу:

1. **`index.css` импортирует слои строго по порядку** `tokens → base → layout →
   ui → pages/common → pages/*`, и этот порядок — контракт ADR-0005.
2. **Файлы страниц подключаются из `index.css`, а не из компонентов**: иначе
   порядок зависит от графа импортов и «плавающего» CSS при сборке (Vite
   ставит стили в порядке обхода модулей).
3. **Специфичность не меняется.** Ни одно правило не получает новый селектор
   ради переезда. Класс, который сегодня один раз перекрывает `ui.css`,
   продолжает перекрывать его из `pages/*`.
4. **Токены не дублируются.** `tokens.css` — единственное место с `:root` и
   `[data-theme]`. Тёмная тема и `prepaint-init.js` (ADR-0034, нулевой FOUC)
   не меняются вообще.

Проверка «ничего не потерялось» — механическая: количество уникальных
селекторов в `app/styles/**` должно совпасть с 282 литералами `className`
и с прежним числом правил (снимается скриптом в Этапе 0, §4).

### 3.6 Чего в целевой структуре нет

* **`pages/` не содержит `fetch`.** Страница читает через хук из
  `features/`/`shared/hooks/`, а не вызывает `api.*` напрямую. Сегодня
  `api.*` вызывают **20** файлов из `pages/`, `components/` и их тестов
  (13 исходников + 7 тестов).
* **Нет `utils.ts`, `helpers.ts`, `common.ts`, `shared.ts`.** Общий код
  живёт в `shared/` с именем по назначению.
* **Нет barrel-файлов ради удобства.** `index.ts` существует в каждом слайсе
  (§3.3), но не переэкспортирует «всё подряд».
* **Нет новых рантайм-зависимостей.** Разбиение не добавляет ни одной
  библиотеки: TanStack Query из `docs/CODE_REVIEW_FRONTEND.md` §2.2 в этом
  плане не появляется (это отдельное решение, а не разбиение папок).

---

## 4. Этап 0 — страховка и документация

Переезд начинается не с переезда, а с того, что после него можно проверить.

1. **`docs/FRONTEND_STRUCTURE.md`** — карта слоёв, разрешённые стрелки, бюджеты
   строк, соглашения об именах, рецепт «добавить фичу». Двойник
   `docs/BACKEND_STRUCTURE.md` (ADR-0039).
2. **`docs/adr/adr-0040-layered-frontend-slices.md`** — решение: почему пять
   слоёв, почему не полный FSD, почему CSS остаётся рукописным (ADR-0005).
   Строка в `docs/adr/README.md` добавляется в этом же коммите.
3. **`src/test/structure.test.ts`** — проверки, которые должны стать зелёными
   **до** переезда (см. §11). Заводится в режиме «мягком»: одинаковые имена
   файлов проверяются, а переезд импортов ещё не проверяется. Без этого
   «мягкого» режима тест был бы красным на честном коде и его пришлось бы
   ослабить целиком.
4. **`src/test/baseline.test.ts`** — снапшоты, которые ломаются, если переезд
   что-то потерял: список маршрутов (20 элементов `<Route>` — 18 страниц и
2 catch-all редиректа `/admin/*`), число `it` в тестах (204),
   множество селекторов CSS, множество ключей i18n (395 × 3). После каждого
   этапа снапшот либо совпадает, либо меняется **осознанно** в том же коммите.
5. **`npm run build` в CI.** Джоб `frontend` получает третий шаг: сборка
   обязана проходить, иначе `tsc -b` ловится только локально.
6. **Скрипт-подсчёт** `tools/count_frontend_layers.ps1` (или npm-скрипт) —
   печатает размеры по слоям. Нужен, чтобы §1 не приходилось пересчитывать
   вручную; сегодня цифры сняты обходом PowerShell.

---

## 5. Карта переездов

Полная таблица «сейчас → станет». Обозначения: **а** — файл переезжает
целиком без изменения содержимого; **р** — требует разрезания; **х** — новый
файл.

### 5.1 `shared/`

| Сейчас | Станет | Строк | Действие |
|---|---|---|---|
| `api.ts` (транспорт: `BASE`, `request`, `requestForm`, `makeApiError`, 401-хук, `ApiError`, `LOGIN_URL`, `TurnstileConfig`) | `shared/api/client.ts` | ~140 | **р** |
| `api.ts` (объект `api`, 34 метода) | `shared/api/endpoints/{auth,status,sync,courses,assignments,grades,feedback,admin}.ts` | 8 × ~40 | **р** |
| — | `shared/api/index.ts` (фасад `api`) | ≤60 | **х** |
| `api-schema.d.ts` | `shared/api/schema.d.ts` | 2 862 | **а** (генерируется) |
| `lib/resource.ts` | `shared/hooks/useResource.ts` | 203 | **а** |
| — | `shared/hooks/useAsyncResource.ts` | ~90 | **х** |
| `lib/cn.ts` | `shared/lib/cn.ts` | 4 | **а** |
| `dates.ts` (кроме `useSortedAssignments`) | `shared/lib/dates.ts` | ~200 | **р** |
| `dates.ts::useSortedAssignments` | `features/assignments-filter/useSortedAssignments.ts` | ~20 | **р** |
| — | `shared/lib/url.ts` (`parseStatusFilter`, `parseDueFilter`, `parseCourseFilter` и форматтеры) | ~120 | **х** |
| `lib/assignmentFilters.ts` (остаток) | `features/assignments-filter/filters.ts` | ~250 | **р** |
| `i18n.ts` | `shared/i18n/index.ts` | 51 | **а** |
| `i18n/{en,ru,uk}.ts` | `shared/i18n/locales/<lang>/<домен>.ts` | 7 × ~70 × 3 | **р** |
| `types.ts` | `shared/types/{wire,assignment,course,grades,feedback,user,ui}.ts` + `index.ts` | 308 | **р** |
| `test/setup.ts`, `test/prepaintInit.test.ts` | `shared/test/` | 107 | **а** |

### 5.2 `entities/`

| Сейчас | Станет | Действие |
|---|---|---|
| `components/Badges.tsx` (Status/Priority/Grade/SubmissionStatus) | `entities/assignment/ui/Badges.tsx` | **а** |
| `components/SubjectCards.tsx` | `entities/course/ui/SubjectCards.tsx` | **а** |
| `types.ts::isAdminUser/isSuperAdminUser` | `entities/user/model/roles.ts` | **р** |
| `pages/FeedbackTickets.tsx::STATUS_CLASS` + `STATUS_LABEL` (4 копии) | `entities/feedback/model/status.ts` | **х** — **убивает дефект §1.3 п.1** |
| `components/TicketMessage.tsx`, `components/AttachmentList.tsx` | `entities/feedback/ui/` | **а** |
| — | `entities/{assignment,course,feedback,user,grades}/index.ts` | **х** |

### 5.3 `features/` и `widgets/`

| Сейчас | Станет | Действие |
|---|---|---|
| `components/FilterPanel.tsx` | `features/assignments-filter/ui/FilterPanel.tsx` | **а** |
| `lib/search.ts`, `components/SearchResults.tsx` | `features/global-search/` | **а** |
| `components/NotificationCenter.tsx` + `TopBar.tsx::buildNotifications` | `features/notifications/` | **р** |
| `components/DonateCards.tsx` | `features/donate/` | **а** |
| `components/AssignmentModal.tsx`, `components/AssignmentCard.tsx` | `features/assignment-modal/`, `entities/assignment/ui/` | **р** |
| — | `features/sync/useSyncState.ts` (stuck-логика из `DataContext`) | **х** |
| `components/Sidebar.tsx`, `AdminSidebar.tsx`, `SidebarNav.tsx` | `widgets/sidebar/` | **а** |
| `components/TopBar.tsx`, `SearchResults.tsx` | `widgets/topbar/` | **р** |
| `components/Landing.tsx`, `SignIn.tsx`, `lib/signInChallenge.ts` | `widgets/landing/` | **а** |
| `components/Markdown.tsx`, `MarkdownField.tsx` | `widgets/markdown/` (импорт CSS остаётся здесь — §2 п.6) | **а** |
| `components/CollapsibleCard.tsx`, `ConfirmDialog.tsx`, `Skeletons.tsx`, `StatCard.tsx`, `ErrorBoundary.tsx` | `shared/ui/` | **а** |

### 5.4 `pages/` и `app/`

| Сейчас | Станет | Строк | Действие |
|---|---|---|---|
| 18 файлов `pages/*.tsx` | 18 папок `pages/<route>/{ui,model}` | — | **р** |
| `App.tsx` (два `<Routes>` на 40 строк) | `app/router/routes.tsx` (данные) + `app/router/AppRouter.tsx` | ≤120 | **р** |
| `App.tsx::AppShell` / `AdminShell` | `app/layouts/AppLayout.tsx` / `AdminLayout.tsx` | ≤80 каждый | **р** |
| `App.tsx::isAdminPath`, `AppShell` (гейт) | `app/boot/bootGate.ts` | ~60 | **р** |
| `components/RequireAdmin.tsx`, `RequireSuperAdmin.tsx` | `app/router/guards.tsx` | 51 | **а** |
| `App.tsx::App` (провайдеры) | `app/providers/AppProviders.tsx` | ≤40 | **р** |
| `context/SettingsContext.tsx` | `app/providers/SettingsProvider.tsx` | 296 | **а** |
| `context/DataContext.tsx` | `app/providers/DataProvider.tsx` + `features/sync/useSyncState.ts` + `entities/user/model/auth.ts` | 537 | **р** |
| `main.tsx` | `app/main.tsx` | 20 | **а** |

---

## 6. Этапы 1–10

Порядок — **от нижнего слоя к верхнему**, обратный топологическому, как в
backend-плане (§7): сначала то, от чего никто не зависит, чтобы каждый шаг
двигал минимальное число файлов.

| Этап | Что переезжает | Коммитов | Что зелёное на выходе |
|---|---|---|---|
| **0** | страховка, ADR-0040, `FRONTEND_STRUCTURE.md`, baseline | 1 | `npm test`, `npm run build`, снапшоты |
| **1** | `shared/api` (client + 8 endpoints + фасад) | 1 | `api.test.ts`, 3 мокающих файла |
| **2** | `shared/lib`, `shared/hooks`, `shared/test` | 1 | `resource.test.ts`, `search.test.ts`, `dates.test.ts` |
| **3** | `shared/types` (8 файлов) + `shared/config` | 2 | `tsc`, 57 импортирующих файлов |
| **4** | `shared/i18n` (7 доменов × 3 языка) | 1 | паритет ключей, `npm test` |
| **5** | `entities/` (5 доменов) | 1 | `Badges`, `SubjectCards`, `TicketMessage` |
| **6** | `features/` (7 фич) | 2 | `FilterPanel.test`, `SearchResults`, 6 страниц с фидбеком |
| **7** | `widgets/` (4 виджета) | 1 | `Landing`, `TopBar`, `Markdown` |
| **8** | `pages/` (18 папок) | 2 | снапшот маршрутов |
| **9** | `app/` (роутер, layouts, providers, стили) | 2 | все снапшоты, `npm run build` |
| **10** | ограждения (тест структуры, eslint, CI) | 1 | все проверки жёсткие |

**Итого 11 коммитов.** Каждый — отдельная единица отката.

### 6.1 Правило переезда

1. **Один файл → одно место, без склейки и разрезания.** Разрезание (`р` в §5) —
   отдельный коммит после переезда, иначе при откате придётся откатывать смешанное.
2. **Тест едет вместе с кодом** в том же коммите, всегда (`vitest.config.ts`
   ищет `src/**/*.test.{ts,tsx}`).
3. **`vi.mock`-пути правятся в том же коммите.** Список — §2 п.4; он полный.
4. **Никаких «шимов на переходный период».** Ссылка на старый путь, которая
   протянет неделю, превращается в постоянную. Фасад `shared/api/index.ts`
   нужен один раз и навсегда как публичный API слоя, а не как костыль.
5. **`npm run lint` и `npm test` зелёные в каждом коммите.** Не «в конце».

### 6.2 Что правится в том же коммите

| Файл | Что меняется | Этап |
|---|---|---|
| `frontend/index.html` | путь `/src/main.tsx` → `/src/app/main.tsx` | 9 |
| `package.json` | `gen:api`/`gen:api:file` → `-o src/shared/api/schema.d.ts` | 1 |
| `eslint.config.js` | `ignores: ["src/api-schema.d.ts"]` → `["src/shared/api/schema.d.ts"]` | 1 |
| `.github/workflows/ci.yml` | добавить `npm run build` в джоб `frontend` | 0 |
| `tools/check_text_encoding.py` | новые файлы под git — проверка автоматическая | — |
| `README.md` | раздел «Структура frontend» + ссылка на `docs/FRONTEND_STRUCTURE.md` | 0 |
| `docs/adr/README.md` | строка ADR-0040 | 0 |
| `docs/BACKEND_STRUCTURE.md` | ссылка «фронтенд — ADR-0040» (в §«Слои») | 0 |

Отдельно: `tools/dump_openapi.py` (генерирует `frontend/openapi.json`) не
трогается — он пишет в корень `frontend/`, а не в `src/`.

### 6.3 Проверка на каждом этапе

```bat
cd frontend
npm run lint        :: eslint src + tsc --noEmit
npm test            :: vitest run — 33 файла, 204 it, ноль падений
npm run build       :: tsc -b + vite build (добавлен в Этапе 0)
```

Плюс `git diff --stat`: ни один этап не должен удалять тест. Если число `it`
уменьшилось — этап неверен, это не «упрощение».

---

## 7. Ограждения (Этап 10)

План без проверок размывается за один спринт — это ровно тот вывод, к
которому пришёл ADR-0039 для бэкенда. Проверки живут в
`frontend/src/test/structure.test.ts` и запускаются обычным `npm test`.

Каждая проверка объясняет **почему** нарушение важно. Проверка, которая
просто говорит «слишком много строк», удаляется первой же, когда мешает.

| # | Проверка | Что предотвращает |
|---|---|---|
| 1 | Ни один модуль не выше бюджета (§8) | возврат 537-строчного `DataContext` и 1 556-строчного `pages.css` |
| 2 | `shared/lib/**` не импортирует `react` | «чистый слой», который сегодня не чистый (§1.3 п.3) |
| 3 | `shared/**` не импортирует `entities/**`, `features/**`, `widgets/**`, `pages/**` | разворот главной стрелки |
| 4 | `entities/**` не импортирует `api.*`, `useResource`, `react-router-dom` | домен, который знает про транспорт и роутер |
| 5 | `features/**` не импортирует `widgets/**`, `pages/**`, `app/**` | фича, зависящая от страницы |
| 6 | `widgets/**` не импортирует `pages/**`, `app/**` | блок оболочки, знающий про маршруты |
| 7 | `pages/**` не импортирует `app/**` | страница, которая тянет сборку |
| 8 | `app/**` не импортируется никем, кроме `app/main.tsx` | `app/` как свалка |
| 9 | Соседние слои не импортируют друг друга напрямую (`features/sync` ⇄ `features/donate`) | дублирование вместо общего кода |
| 10 | Наружу торчат только `index.ts`: запрещён `from "../../entities/feedback/status.ts"` | 57 импортов, блокирующих следующий рефакторинг |
| 11 | Запрещены `utils.ts`, `helpers.ts`, `common.ts`, `misc.ts` | новая свалка под другим именем |
| 12 | `pages/*/page.css` подключается из `app/styles/index.css`, а не из компонентов | «плавающий» порядок CSS при сборке |
| 13 | `package.json::gen:api:file` указывает на `src/shared/api/schema.d.ts` | типовой файл, оторванный от кода |
| 14 | `index.html` ссылается на `/src/app/main.tsx` | мёртвая точка входа |
| 15 | Число `it(` в тестах не меньше 204 | «починили ослаблением» |
| 16 | Снапшот маршрутов совпадает с эталоном (20 `<Route>`) | потерянный маршрут при разбиении `App.tsx` |
| 17 | Множество ключей i18n равно 395 в каждом из 3 языков | потерянная трансляция (ADR-0011) |
| 18 | Число уникальных селекторов CSS совпадает с эталоном | потерянное правило при разбиении `pages.css` |

Парсинг — через TypeScript API (`typescript` уже в devDependencies), а не
регулярками: правило, которое срабатывает внутри строки или комментария, —
это правило, которое плачет.

Плюс:

* **`eslint.config.js`** — `no-restricted-imports` с теми же восемью
  ограничениями. ESLint даёт подсветку в редакторе, тест — защиту в CI;
  дублирование осознанное, как `ruff` + `test_backend_structure.py` на бэкенде.
* **CI** — `npm run build` в джоб `frontend` (Этап 0).
* **`docs/FRONTEND_STRUCTURE.md`** и **`README.md`** — ссылка на карту слоёв.

---

## 8. Бюджеты строк

| Что | Файл | Лимит |
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

Числа сняты из §1.2 так, чтобы каждый лимит был выше текущего размера
выбранной группы, но ниже размера, при котором возвращается смешение
ответственностей. Исключений нет: на бэкенде пришлось выдать исключение
`launcher.py` (Nuitka), здесь аналога нет — все файлы переезжают свободно.

---

## 9. Рецепт: добавить новую страницу или фичу

**Новая страница:**

1. `entities/<домен>/` — если появился новый доменный тип или правило
   отображения (`STATUS_CLASS`, бейдж, карточка). Если домен уже есть — шаг
   пропускается.
2. `features/<фича>/` — если у страницы есть **собственное действие**
   (панель фильтров, форма, модалка). Хук с загрузкой — в
   `features/<фича>/model/`.
3. `pages/<route>/{ui,model,page.css}` — компонент маршрута.
4. `app/router/routes.tsx` — одна строка в массиве маршрутов.
5. Ключи i18n — в `shared/i18n/locales/{en,uk,ru}/<домен>.ts`, **три файла
   одним коммитом** (иначе `tsc` упадёт на паритете — и это правильно).
6. Тест рядом: `pages/<route>/ui/<Route>.test.tsx`.

**Новая фича, общая для двух страниц:** `features/<фича>/`, и обе страницы
импортируют её `index.ts`. Фича не знает про страницы — проверка №5.

**Новое правило предметной области, нужное трём местам:** `entities/<домен>/model/`.

Ключевой вопрос при выборе места: *это про **что** (домен), про **действие**
(фича), про **блок интерфейса** (виджет) или про **маршрут** (страница)?**

---

## 10. Что не трогаем

* **`frontend/public/`** — иконки, `prepaint-init.js` (ADR-0034), QR-коды
  (ADR-0037), `privacy/`, `terms/`.
* **`frontend/openapi.json`**, `tools/dump_openapi.py`, `tools/make_icon.py`,
  `build.bat` — весь конвейер сборки.
* **Бэкенд целиком**: HTTP-контракт, `operationId`, порядок роутеров.
  ADR-0039 на фронтенд не распространяется и не переписывается.
* **`@uiw/react-md-editor`, `rehype-sanitize`, `sonner`, `lucide-react`** —
  список зависимостей не меняется (§3.6).
* **ADR-0005 (стек), ADR-0011 (i18n), ADR-0034 (язык документа), ADR-0035/0036
  (фидбек и админы), ADR-0026 (CSP)** — решения принимаются, а не пересматриваются.
* **`docs/CODE_REVIEW_FRONTEND.md`** — остаётся ревью. Пункты, которые план
  закрывает (самоописный React Query в §2.2, god-контекст в §2.1, `i18n.ts`
  в §1.8), помечаются ссылкой на ADR-0040 при следующем обновлении.

---

## 11. Риски и откат

| Риск | Что делаем |
|---|---|
| Тихая потеря маршрута при разбиении `App.tsx` | снапшот маршрутов (20 `<Route>`) + проверка №16 |
| Потерянное CSS-правило при разбиении `pages.css` | снапшот селекторов + проверка №18; порядок импорта зафиксирован в `index.css` |
| Потерянный ключ перевода | паритет `en`/`uk`/`ru` проверяется `tsc` (ADR-0011) + проверка №17 |
| Мок уехал в мёртвый модуль | список §2 п.4 полный; `vi.mock` на несуществующий путь падает сам — но **не всегда**: `vi.mock("../api.ts")` на несуществующем модуле не всегда ошибка, поэтому полагаемся на `npm test`, а не на сам факт патча |
| Циклический импорт между слоями | TS и Vite ловят это на этапе; проверки №3–9 не дают ему появиться |
| Цикл внутри одного слоя (например, `entities/feedback` ↔ `entities/user`) | единственное допустимое исключение — `entities/user` ← `entities/feedback` (роль автора в сообщении). Фиксируется комментарием и проверкой №9 как whitelist |
| `STATUS_CLASS`/`STATUS_LABEL` снова разъедутся | `entities/feedback/model/status.ts` + проверка «словарь статусов объявлен один раз» (дополняет №10) |
| Тесты «починили ослаблением» | проверка №15: число `it` не уменьшается |
| Порядок `vi.mock` сломался после переезда | тесты, мокающие `DataContext`, падают явно: `DataProvider` становится заглушкой, а `useAuth` — нет |
| `npm run build` не в CI | добавляется в Этапе 0, до переездов |

**Откат.** Каждый этап — отдельный коммит, откат — `git revert <sha>`.
Реверт работает и для файла, и для папки: файлы просто возвращаются на место,
никакой «разрегистрации» не требуется (в отличие от `sys.path` на бэкенде —
фронтенд не имеет глобального реестра модулей).

---

## 12. Альтернативы (почему не они)

* **Полный FSD (Segment: `ui/model/lib/api/config`) в каждом слайсе** —
  отклонён: на 11 754 строки это 5 уровней вложенности в папке из трёх файлов.
  Сегменты применяются выборочно: `model/` там, где есть состояние, `ui/` —
  где больше одного компонента.
* **Только `app/` + `shared/` (без `entities/features/widgets`)** — на один
  этап меньше, но `shared/` немедленно набирает 30 файлов, потому что
  «не домен» — это определение, которое нельзя проверить. Через полгода
  `shared/` станет новой `components/`, а переезд придётся повторять.
* **Только бэкенд-подход «пакеты внутри `src/`» (ADR-0039 один в один)** —
  слои заданы, но горизонтальные срезы (`features/`, `widgets/`) не выделены,
  поэтому страница админки и лендинг снова окажутся рядом и снова поделят
  `Badge`.
* **CSS Modules вместо разбиения по файлам** — отклонён: 282 литерала
  `className` привязаны к тестам (§2 п.8) и к ADR-0005. Переход на CSS Modules
  — это отдельное решение, а не разбиение папок.
* **Перенос на Next.js / файловый роутинг** — отклонён: приложение раздаётся
  как SPA статикой FastAPI (`edge/static.py`), маршруты живут в `history`
  и `SPAStaticFiles` делает fallback. Смена роутера ломает и деплой, и
  desktop-сборку Nuitka (ADR-0016).
* **TanStack Query вместо своего `useResource`** — отклонён **в этом плане**:
  это изменение поведения и зависимостей, а не структуры. `resource.ts` уже
  даёт дедупликацию, отмену и TTL; замена обсуждается отдельно, если
  `useAsyncResource` не покроет потребность.

---

## 13. Итог

Этапов — 10, коммитов — 11. Первые три (0–2) не меняют ни одного
пользовательского файла: они добавляют проверки и переносят нижний слой.
Каждый этап обратим; последний делает структуру невозможно испортить молча.