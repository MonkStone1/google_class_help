# План: клиентский экспорт курса в Excel (пресеты + ExcelJS)

Статус: **выполнен полностью** (этапы 0–6, 2026-10-03)
Дата: 2026-10-03
Источник задачи: [`docs/prompt/exel_update/excel_update_prompt.md`](../prompt/exel_update/excel_update_prompt.md)
Принятое решение: `docs/adr/adr-0041-client-side-excel-export.md`
Правила слоёв фронтенда: [`docs/FRONTEND_STRUCTURE.md`](../../FRONTEND_STRUCTURE.md)

Одно изменение поверх ADR-0040: **ноль строк бэкенда**. Ни эндпоинта, ни
изменения `response_model`, ни дополнительного запроса к Google Classroom.

---

## 0.1 Что получилось (фактические числа)

| Этап | Итог |
|---|---|
| 0 | `docs/adr/adr-0041-client-side-excel-export.md` + строка в `docs/adr/README.md` |
| 1 | `exceljs@^4.4.0`; `engine/{types,registry,rows,filename,download}.ts` |
| 2 | `engine/workbook.ts`, `presets/ukranianDictionaryNz.ts` — зелёные и при `TZ=Europe/Kyiv`, и при `TZ=UTC` |
| 3 | 19 ключей `export.*` в трёх словарях; `I18N_KEY_COUNT` 395 → **414** |
| 4 | `model/useExportRows.ts`, `ui/ExcelExportDialog.tsx`, `ui/ExportPreviewTable.tsx`, `ui/ExcelExportButton.tsx` |
| 5 | кнопка в `TeacherCourse.tsx` (291 строка при бюджете 300), 12 правил `.export-*`; `cssSelectors()` 469 → **481**; `routes` без изменений |
| 6 | `docs/FRONTEND_STRUCTURE.md` обновлён; `npm test` — **322 теста в 45 файлах**, `npm run lint` и `npm run build` зелёные |

На фиче лежит **96 тестов** в 9 файлах — против 42 проверок, перечисленных в
§6 плана. `pytest` (501 тест) остался зелёным: бэкенд не тронут.

Отклонения от плана, сознательные:

* **`ExportColumn.text`** добавлен вместо `preset.transformTitle` /
  `preset.transformHomework`. Плановый `cellValue` по `column.kind` вынужден
  был бы различать колонки по ключам (`title` / `homework`) — то есть движок
  знал бы, какая колонка «контент». Функция на колонке убирает это знание
  совсем; §3.4 («значение вычисляет сама колонка») теперь выполнена буквально.
* **19 ключей, а не 18** — добавлен `export.close` для кнопки закрытия модалки
  (в плане она не была посчитана).
* **`engine/testFixture.ts`** — пресет для тестов движка, объявленный не в
  тесте, а отдельным файлом: его используют пять тестовых файлов, и дублировать
  его в каждом было бы пять копий одного и того же.
* **`filenameSuffix` без ведущего подчёркивания** (`"електронний_щоденник"`,
  а не `"_електронний_щоденник"`): разделитель между именем курса и суффиксом
  ставит `buildFilename`, поэтому автор пресета не должен был о нём думать.

---

## 0. Как читать этот план

| § | Что это | Состояние |
|---|---|---|
| 1 | Диагностика: что уже есть и куда встаёт экспорт | факт, снят с кода |
| 2 | Жёсткие ограничения, решение по `mitt` | факт + требования промпта |
| 3 | Целевая архитектура: поток, слои, контракты, спорные места | проектное решение |
| 4 | Карта файлов «создать / изменить / не трогать» | проектное решение |
| 5 | Этапы 0–6, порядок, что правится в том же коммите | не начат |
| 6 | Тестовая матрица (42 проверки) | проектное решение |
| 7 | Ограждения и baselines, которые придётся обновить | не начат |
| 8 | Проверка на каждом этапе | — |
| 9–12 | Риски и откат, альтернативы, чек-лист промпта, итог | факт |

Все пути в §4 — от `frontend/src/`, если не указано иное. Цифры §1 сняты с
рабочей копии на коммите `34f64f6`.

---

## 1. Диагностика (факты, снятые с кода)

### 1.1 Где живёт нужный Today: `pages/subject/ui/TeacherCourse.tsx`

| Факт | Где именно |
|---|---|
| Экран учительского курса | `frontend/src/pages/subject/ui/TeacherCourse.tsx` (284 строки) |
| Данные уже загружены | `useResource(\`course:${course.id}:coursework\`, …)` → `api.getCourseCoursework(course.id)` |
| Транспорт | `shared/api/endpoints/assignments.ts:30` → `GET /api/courses/{id}/coursework` (ADR-0024) |
| Кэш учительских чтений | `shared/hooks/useResource.ts`, TTL 60 с, дедупликация по ключу |
| Модалка-паттерн, который надо повторить | `features/assignment-modal/AssignmentModal.tsx`: `modal-backdrop` + `role="dialog"` + `aria-modal`, закрытие по Escape и по фону |
| Busy/error-состояние в диалоге | `shared/ui/ConfirmDialog.tsx` (пропсы `busy`, `error`) |
| Тосты | `sonner` + `app/toaster/Toaster.tsx` (ADR-0030) |

Ключевой вывод: **данные для экспорта уже в памяти страницы**. Промпт §3
(«frontend-only») и ADR-0024 здесь совпадают: ни одного нового `fetch`
не появляется, `useResource` не трогается.

### 1.2 Данные строки экспорта

`shared/types/assignment.ts` + `schema.d.ts` (`AssignmentOut`):

| Поле | Тип | Комментарий |
|---|---|---|
| `id` | `string` | ключ сортировки-хранитель при равных метках (§8 промпта) |
| `title` | `string` | источник `Зміст` |
| `description` | `string \| null` | источник `ДЗ`; `null` → пустая ячейка |
| `created_at` | `string \| null` | **дефолтная дата, и она nullable** |
| `due_at` | `string \| null` | в экспорте не участвует (промпт не просит) |
| `course_name` | `string` | есть и у assignment, и у `Course` |

`created_at` nullable — это и есть главный источник ошибки «invalid date»
(§16 промпта): у задания без даты создания дефолта нет.

### 1.3 Ограничения, которые навязывает уже сделанная реструктуризация

| Правило | Где записано | Что значит для экспорта |
|---|---|---|
| `shared/ ← entities/ ← features/ ← widgets/ ← pages/ ← app/` | ADR-0040 §2, `eslint.config.js`, `structure.test.ts` #2–#9 | экспорт — **фича** `features/excel-export/`, её зовёт страница |
| Публичный API слайса — только `index.ts` | guardrail #10 | наружу торчит один баррель фичи |
| Соседние слайсы не импортируют друг друга | guardrail #9 | пресет живёт **внутри** слайса, а не второй фичей |
| Бюджеты строк | `structure.test.ts` `LINE_BUDGETS` | `features/**` ≤ 300, `pages/**` ≤ 300, `shared/i18n/locales/**` ≤ 120 |
| Имена файлов | guardrail #11 | запрещены `utils.ts`, `helpers.ts`, `common.ts`, `misc.ts` |
| CSS только через `app/styles/index.css` | guardrail #12 | новые классы — в существующий `pages/subjects.css` |
| Три словаря синхронны | ADR-0011, `satisfies Record<I18nKey, string>` | три файла одним коммитом, иначе `tsc` падает |
| Baselines — эталоны | `baseline.test.ts` | 395 i18n-ключей и 469 CSS-селекторов придётся поднять **в том же коммите** |
| Минимум 204 `it(` и 33 файла тестов | `structure.test.ts` #15, `baseline.test.ts` | новые тесты только добавляют |
| CSP `script-src 'self'`, без CDN | ADR-0026 | exceljs грузится из собственного чанка, не с чужого домена |

### 1.4 Что в проекте уже доказало приём

* `features/assignments-filter/` — фича с собственным UI (drawer), моделью
  (`filters.ts`, `useSortedAssignments.ts`) и тестами рядом с модулями.
  Ровно та же форма, что нужна экспорту.
* `shared/i18n/locales/<lang>/<домен>.ts` — девять доменных словарей;
  новый домен добавляется десятью файлами (три языка + три `index.ts`).
* `app/styles/pages/subjects.css` — 184 строки, стили экрана курса;
  добавление ~60 строк далеко от бюджета.

---

## 2. Жёсткие ограничения

Из промпта (`excel_update_prompt.md`), обязательные без исключений:

1. **Ноль изменений бэкенда.** Нет эндпоинта экспорта, нет серверной
   генерации xlsx, нет хранения файла на сервере, нет нового вызова Google
   Classroom API.
2. **Только браузер.** Всё — выбор пресета, трансформация, сортировка,
   нумерация, превью, правка дат, сборка книги, форматирование, скачивание.
3. **Настоящий `.xlsx` через ExcelJS.** Не CSV с переименованным расширением.
4. **Исходные объекты coursework не мутируются** — ни заголовки, ни описания,
   ни `created_at`.
5. **Пресетная архитектура.** Общий движок не знает про
   `Номер | Дата | Зміст | ДЗ`; эта структура принадлежит пресету
   `ukranian_dictionary_nz`.
6. **UI-язык ≠ формат экспорта.** Английский UI + украинский пресет —
   валидная комбинация.
7. **`mitt` не добавляется** без реальной архитектурной потребности.
8. **Только `exceljs`** как новая зависимость.

Из проекта:

9. Никаких новых маршрутов (`baseline.test.ts` фиксирует 20 маршрутов) —
   экспорт живёт модалкой на существующем экране.
10. Никаких ручных зеркал бэкенд-схем: `schema.d.ts` не трогаем.
11. Все пользовательские строки — через `t()` (ADR-0011).

### 2.1 Решение по `mitt`: не добавляем

Аргумент «за Event Bus» обычно звучит так: «кнопка, модалка и превью должны
общаться». Здесь они общаются через **props и локальный state** одного
дерева: `ExcelExportDialog` владеет выбранным пресетом и картой
переопределений дат, `useExportRows` — единственный потребитель этих данных.
Второй канал связи рядом с props — это две правды о состоянии, а не
развязка.

Проверка по слоям (ADR-0040): `mitt` потребовался бы, если бы превью и
экспортёр жили в **разных слайсах** и не могли импортировать друг друга
(guardrail #9). Но пресет и движок — внутренние модули одного слайса
`features/excel-export/`, а кнопка вызывается со страницы через один
экспорт из `index.ts`. Проблемы, которую решает Event Bus, здесь нет.

Итог: `npm i exceljs` — и только. Решение фиксируется в ADR-0041, чтобы
следующий читатель не «достроил» шину по промпту.

---

## 3. Целевая архитектура

### 3.1 Поток (одна строка, как в промпте §1)

```text
coursework, уже загруженный на TeacherCourse
  → нормализация строк (движок: sort + number + preset)
  → превью (таблица, «Дата» редактируется)
  → ExcelJS: Workbook → Worksheet → writeBuffer
  → Blob → objectURL → <a download> → файл на диске
```

Ни одного шага, который требует сети.

### 3.2 Слои и файлы

```text
frontend/src/features/excel-export/
├── index.ts                      # публичный API слайса (guardrail #10)
├── engine/                       # общий движок: пресетов не знает
│   ├── types.ts                  # ExportPreset, ExportColumn, ExportRow
│   ├── registry.ts               # registerPreset / getPreset / listPresets
│   ├── rows.ts                   # buildRows: sort + number + values
│   ├── workbook.ts               # ExcelJS: buildWorkbookBuffer → ArrayBuffer
│   ├── filename.ts               # sanitizeFilename + buildFilename
│   └── download.ts               # saveBuffer (Blob → <a download>)
├── presets/
│   └── ukranianDictionaryNz.ts   # единственный пресет: правила и колонки
├── model/
│   └── useExportRows.ts          # React-состояние превью
├── ui/
│   ├── ExcelExportDialog.tsx     # модалка: пресет, превью, даты, кнопки
│   └── ExportPreviewTable.tsx    # таблица превью + input[type=date]
└── *.test.ts(x)                  # тест рядом с модулем (конвенция проекта)
```

Правила слоёв, которые это соблюдает:

* `features/excel-export/` не импортирует `pages/`, `widgets/`, `app/`
  (guardrail #5);
* `engine/` не импортирует `presets/` — иначе «общий движок» стал бы
  пресетным (проверяется тестом, §6.1 №13);
* наружу — только `features/excel-export/index.ts`;
* `shared/i18n`, `shared/ui`, `shared/types` — снизу, это разрешено.

### 3.3 Контракт пресета

```ts
// engine/types.ts
export type ExportColumnKind = "number" | "date" | "text";

export type ExportColumn = {
  key: string;              // "number" | "date" | "content" | "homework"
  header: string;           // UA-заголовок колонки, как в файле импорта
  kind: ExportColumnKind;
  width: number;            // ширина колонки в Excel
  wrap?: boolean;           // перенос строки
};

export type ExportPreset = {
  id: string;                          // "ukranian_dictionary_nz"
  labelKey: I18nKey;                   // локализованное имя в селекторе
  worksheetName: string;               // имя листа
  columns: ExportColumn[];             // ПОРЯДОК = порядок в файле
  numberFormat: Record<ExportColumnKind, string>;  // date → "dd.mm.yyyy"
  headerFill?: { fg: { argb: string }; font?: { bold: boolean } };
  sort: { primary: "createdAt"; tiebreak: "id" };
  filenameSuffix: string;              // "_електронний_щоденник"
  /** Заголовок задания → «Зміст». */
  transformTitle: (title: string) => string;
  /** Описание задания → «ДЗ». */
  transformHomework: (description: string | null | undefined) => string;
  /** Дата по умолчанию (creation date) → Date | null. */
  defaultDate: (createdAt: string | null | undefined) => Date | null;
};
```

Инварианты, которые проверяются тестами (§6), а не только договорённостью:

* `columns` — массив, порядок значим; движок не сортирует и не добавляет
  колонок;
* `header` — **не локализуется**: это формат файла для импорта, а не UI.
  Локализовано только то, что видит учитель в интерфейсе;
* `transformTitle` / `transformHomework` — чистые `(string) => string`,
  без побочных эффектов и без доступа к сети;
* любая трансформация получает значение из **копии** строки (движок строит
  новые объекты, §3.5).

### 3.4 Почему движок не знает про пресет

`engine/rows.ts` делает ровно три вещи и не знает, что за колонки:

```ts
// псевдокод, детали в §5
const sorted = [...assignments].sort(byCreatedAtThenId); // без мутации
return sorted.map((a, index) => ({
  assignmentId: a.id,
  values: Object.fromEntries(
    preset.columns.map((c) => [c.key, cellValue(c, a, index, preset)]),
  ),
}));
```

`cellValue` диспетчеризирует по `column.kind`: `number` → `index + 1`,
`date` → переопределение ?? `preset.defaultDate(...)`,
`text` → значение, вычисленное самой колонкой.

Проверка «движок не хардкодит `Зміст`» — тест, который читает текст
`engine/rows.ts` и `engine/workbook.ts` и требует отсутствия строк
`Зміст`, `ДЗ`, `Номер`. Стоит восемь строк и закрывает требование промпта §12.

### 3.5 Отсутствие мутации

```ts
// ❌ так нельзя
const sorted = assignments.sort(...);
const title = assignment.title.replace(...);

// ✅ так
const sorted = assignments.map((a) => ({ ...a })).sort(...);
const title = preset.transformTitle(assignment.title); // возвращает строку
```

Трансформации возвращают **новые строки** (`.replace()` уже так делает),
движок кладёт их в новые объекты строк. Тест «не мутирует источник» делает
снимок до вызова и сравнивает после.

### 3.6 Дата: дефолт, редактирование, запись в Excel

| Стадия | Что происходит | Где |
|---|---|---|
| Дефолт | `new Date(created_at)`; `null`/`NaN` → `null` | `presets/ukranianDictionaryNz.ts` |
| Сортировка | **по исходному** `createdAt`, до правок | `engine/rows.ts` |
| Правка | `Record<assignmentId, "YYYY-MM-DD">` в состоянии модалки | `ui/ExcelExportDialog.tsx` |
| Превью | `<input type="date">`, значение `YYYY-MM-DD` | `ui/ExportPreviewTable.tsx` |
| Excel | настоящий `Date` в ячейке + `numFmt: "dd.mm.yyyy"` | `engine/workbook.ts` |

Правка даты **не меняет** исходный `created_at` (промпт §8) и не влияет на
порядок строк: сортировка уже произошла по исходной метке.

**Про часовой пояс — важно.** ExcelJS конвертирует `Date` в серийный номер
Excel по UTC: `dateToExcel(d) = 25569 + d.getTime() / 86_400_000`
(`exceljs/lib/utils/utils.js`), без поправки на локальную зону. Наивный
`new Date("2026-09-20")` (UTC-полночь) в зоне UTC+3 покажет в Excel
`19.09.2026`. Поэтому день везде собирается как **локальная полночь**:

```ts
// "2026-09-20" → 20.09.2026 в любой зоне
const [y, m, d] = value.split("-").map(Number);
return new Date(y, m - 1, d);
```

`numFmt` ставится в той же ячейке. Тест на часовой пояс запускается с
`TZ=Europe/Kyiv` и с `TZ=UTC` — оба обязаны дать `20.09.2026`.

### 3.7 Форматирование Excel (промпт §14) — УТОЧНЕНО 2026-10-03

> Первая редакция плана предлагала «жирные заголовки с заливкой `FFF2F2F2`».
> **Требование изменилось**: файл должен быть без форматирования, всё одного
> размера. Жирного текста, заливки и своих кеглей в книге нет.

| Что | Решение | Почему |
|---|---|---|
| Заголовки | **обычным текстом, без заливки и без жирного** | требование заказчика; пресет не объявляет `headerFill` |
| Кегль | не задаётся нигде — вся книга в шрифте книги по умолчанию | «все одного размера» |
| Ширины | из пресета: `6 / 12 / 46 / 60` | «Зміст» и «Домашнє завдання» длинные |
| Перенос | `wrapText: true` у `Зміст`/`Домашнє завдання` | длинный текст остаётся читаемым; это не оформление, а разбивка строки |
| Дата | `Date` + `numFmt: "dd.mm.yyyy"` | требует промпт §9 |
| № | число (`index + 1`), не строка | импорт ожидает число |
| Технические колонки | **запрещены** | промпт §14 |
| Порядок колонок | ровно `preset.columns` | промпт §14 |

Оформление задаётся пресетом (`columns[].width/wrap`, необязательный `headerFill`,
`numberFormat`), а не захардкожено в движке: второй пресет с другими
колонками не должен ломать генератор.

### 3.8 Спорные места промпта и принятые решения

| Место промпта | Противоречие | Решение |
|---|---|---|
| §7 (заголовки `Номер/Дата/Зміст/ДЗ`) vs §15 (локализованные заголовки превью) | если локализовать колонки, файл перестанет импортироваться | **файл** — фиксированные UA-заголовки из пресета; **превью** — те же строки, они и есть формат. Локализованы кнопка, подпись колонки-даты, подсказка, статусы и ошибки |
| §9 «по умолчанию дата создания» vs §16 «некорректная дата» | у задания `created_at === null` | строка остаётся, ячейка даты пустая, счётчик пропущенных показывается в превью; экспорт не падает, ячейку можно заполнить вручную |
| §10 «если результат пуст — взять исходный заголовок» vs «удалить `Урок`» | `Урок 20.09.2026` → после удаления пусто | правило промпта: откат на исходный заголовок, зафиксировано тестом №20 |
| §13 имя файла `<course_name>_…` vs безопасность ФС | в имени курса бывают `/ \ : * ? " < > \|` | `sanitizeFilename`, ограничение длины (100 символов), запас `_course` при пустом результате |
| §5 `mitt` | — | не добавляем, §2.1 |
| §18 «ноль изменений бэкенда» vs `schema.d.ts` | — | `schema.d.ts` не перегенерируем: эндпоинтов нет, меняться нечему |

### 3.9 Трансформации пресета `ukranian_dictionary_nz`

`Зміст` (промпт §10), порядок правил:

1. убрать слово `Урок` (целиком, с границами слова, регистронезависимо);
2. убрать все даты `\d{1,2}\.\d{2}\.\d{4}`;
3. схлопнуть пробелы и переносы строк;
4. убрать «осиротевшую» пунктуацию от удаления (`:`, `,`, `-`, `—` в начале
   и в конце, повторы), **но сохранить** точку после номера урока
   (`15.` остаётся `15.`);
5. сохранить всё остальное значимое;
6. если результат пуст — исходный заголовок.

```ts
// "Урок 15. 20.09.2026 Алгоритми" → "15. Алгоритми"
```

`ДЗ` (промпт §11):

```ts
// "Прочитати матеріал https://example.com/test"
//   → "Прочитати матеріал (google classroom)"
const URL_RE = /\bhttps?:\/\/[^\s<>()[\]]+/gi;
const transformHomework = (d) =>
  (d ?? "").replace(URL_RE, "(google classroom)").trim();
```

* заменяются **все** URL, не только первый;
* `description === null` → пустая строка;
* исходный `description` не меняется.

### 3.10 Локализация

Новый домен `export` в трёх словарях. Ключи:

| Ключ | Смысл |
|---|---|
| `export.button` | «Експортувати у Excel» |
| `export.title` | заголовок модалки |
| `export.preset` | подпись селектора пресетов |
| `export.preset.ukranian_dictionary_nz` | имя пресета |
| `export.dateHint` | текст из промпта §7 (uk/ru/en дословно) |
| `export.dateColumn` | подпись колонки «Дата» в интерфейсе |
| `export.cancel` / `export.submit` | «Скасувати» / «Експортувати» |
| `export.working` | состояние загрузки |
| `export.done` | «Файл завантажено» |
| `export.empty` | «Немає завдань для експорту» |
| `export.missingDates` | «{count} завдань без дати» |
| `export.error.noAssignments` | нет заданий |
| `export.error.invalidPreset` | неизвестный пресет |
| `export.error.invalidData` | некорректные данные задания |
| `export.error.invalidDate` | некорректная дата |
| `export.error.build` | ошибка ExcelJS |
| `export.error.download` | ошибка скачивания |

Всего **18 ключей** в каждом из трёх словарей (`export.cancel` и
`export.submit` — два ключа в одной строке таблицы).

Тексты `export.dateHint` — дословно из промпта §7, по одному на язык.
Три файла `locales/{en,uk,ru}/export.ts` + три `index.ts` — **один коммит**
(ADR-0011: `satisfies Record<I18nKey, string>` упадёт на `tsc`).

Заголовки колонок (`Номер`, `Дата`, `Зміст`, `ДЗ`) в `export.*` **не**
попадают: это формат файла, а не UI.

---

## 4. Карта файлов

### 4.1 Создать

| Файл | Строк (план) | Назначение |
|---|---|---|
| `features/excel-export/index.ts` | ~25 | публичный API: `ExcelExportButton`, `ExcelExportDialog`, `useExportRows`, типы |
| `features/excel-export/engine/types.ts` | ~60 | `ExportPreset`, `ExportColumn`, `ExportRow`, `PresetId` |
| `features/excel-export/engine/registry.ts` | ~50 | `registerPreset`, `getPreset`, `listPresets`, `isPresetId` |
| `features/excel-export/engine/rows.ts` | ~90 | `buildRows(preset, assignments, overrides)` — sort + number + values |
| `features/excel-export/engine/workbook.ts` | ~90 | ExcelJS: `buildWorkbookBuffer(preset, rows)` → `ArrayBuffer` |
| `features/excel-export/engine/filename.ts` | ~45 | `sanitizeFilename`, `buildFilename(courseName, preset)` |
| `features/excel-export/engine/download.ts` | ~40 | `saveBuffer(buffer, filename, mime)` — Blob, objectURL, `<a download>` |
| `features/excel-export/presets/ukranianDictionaryNz.ts` | ~90 | пресет: колонки, трансформации, `defaultDate`, суффикс имени |
| `features/excel-export/model/useExportRows.ts` | ~80 | состояние: пресет, переопределения дат, busy, error |
| `features/excel-export/ui/ExcelExportDialog.tsx` | ~200 | модалка по паттерну `AssignmentModal` |
| `features/excel-export/ui/ExportPreviewTable.tsx` | ~90 | таблица превью, `<input type="date">` |
| `shared/i18n/locales/{en,uk,ru}/export.ts` | ~35 каждый | новый домен словаря |
| 9 файлов `*.test.ts(x)` | — | тестовая матрица, §6 |

### 4.2 Изменить

| Файл | Что меняется | Почему обязательно |
|---|---|---|
| `pages/subject/ui/TeacherCourse.tsx` | кнопка «Експортувати у Excel» в `page-header-actions` + рендер диалога; файл 284 строки при бюджете 300 | точка входа фичи |
| `shared/i18n/locales/{en,uk,ru}/index.ts` | импорт и spread `*_export` | иначе ключи не попадут в словарь |
| `app/styles/pages/subjects.css` | ~60 строк: `.export-dialog`, `.export-preview`, `.export-date`, `.export-actions` | guardrail #12 |
| `frontend/package.json` + `package-lock.json` | `+ "exceljs": "^4.4.0"` | §18 промпта |
| `src/test/baseline.test.ts` | `I18N_KEY_COUNT` 395 → 395 + 18; `cssSelectors()` 469 → 469 + M | baseline — эталон, меняется в том же коммите |
| `docs/FRONTEND_STRUCTURE.md` | новая фича в списке `features/` | карта слоёв |
| `docs/adr/adr-0041-client-side-excel-export.md` + `docs/adr/README.md` | решение + строка в таблице | конвенция ADR |

### 4.3 Не трогаем (и почему)

| Файл | Почему |
|---|---|
| `backend/**` | промпт §18: ноль изменений бэкенда |
| `shared/api/**` | нет ни одного нового запроса |
| `shared/api/schema.d.ts` | нет новых схем |
| `app/router/routes.tsx` | экспорт — модалка, не маршрут; baseline фиксирует 20 маршрутов |
| `shared/hooks/useResource.ts` | данные уже загружены |
| `entities/assignment/**` | домен не знает об экспорте |
| `shared/settings` | экспорт не настраиваемый (промпт не просит) |

---

## 5. Этапы 0–6

Порядок выбран так, чтобы **каждый этап был зелёным сам по себе** и ни один
коммит не оставлял полусломанное состояние в истории.

### Этап 0 — страховка и документация

**Что:** ADR-0041 и этот план.

| Файл | Действие |
|---|---|
| `docs/adr/adr-0041-client-side-excel-export.md` | новая: клиентский экспорт, пресеты, ExcelJS, решение по `mitt`, часовой пояс |
| `docs/adr/README.md` | строка ADR в таблице |

**ADR отвечает на четыре вопроса:** почему только браузер; почему пресеты;
почему без `mitt`; почему `Date` собирается как локальная полночь.

**Проверка:** `python tools/check_text_encoding.py` (job `text-encoding` в
CI), `git status` чист по коду.

---

### Этап 1 — зависимость и движок без пресетов

**Что:** `npm i exceljs`, типы, реестр, строки, имя файла, скачивание.
Пресетов и UI ещё нет.

| Файл | Действие |
|---|---|
| `frontend/package.json`, `package-lock.json` | `+ "exceljs": "^4.4.0"` в `dependencies` |
| `engine/types.ts` | контракт §3.3 |
| `engine/registry.ts` | `registerPreset` / `getPreset` / `listPresets` / `isPresetId`; `getPreset` бросает ошибку на неизвестный id |
| `engine/rows.ts` | `buildRows` |
| `engine/filename.ts` | `sanitizeFilename`, `buildFilename` |
| `engine/download.ts` | `saveBuffer` |
| `engine/*.test.ts` | тесты §6, колонки «движка» |

**Ключевое решение этапа:** движок проверяется на **тестовом пресете,
объявленном прямо в тесте**. Это и есть требование промпта §17
«возможность добавить другой пресет без изменения движка»: если
`buildRows`/`buildWorkbookBuffer` проходят с чужим набором колонок, они
generic по построению, а не по обещанию.

**В том же коммите:** ничего больше — ключей i18n и UI ещё нет.

**Проверка:** `npm run lint`, `npx vitest run rows filename registry`.

---

### Этап 2 — ExcelJS и пресет `ukranian_dictionary_nz`

**Что:** генератор книги и единственный пресет.

| Файл | Действие |
|---|---|
| `engine/workbook.ts` | `buildWorkbookBuffer(preset, rows)` |
| `presets/ukranianDictionaryNz.ts` | пресет целиком (§3.3, §3.9) |
| `engine/workbook.test.ts` | валидная книга, заголовки, порядок, даты, `dd.mm.yyyy`, длинный текст |
| `presets/ukranianDictionaryNz.test.ts` | трансформации, откат, URL, несколько дат |

**ExcelJS в тестах.** `writeBuffer()` возвращает `ArrayBuffer`; тест читает
его обратно через `new ExcelJS.Workbook().xlsx.load(buffer)` и проверяет
`getWorksheet(name)`, `getRow(1).values`, `numFmt` и `instanceof Date`.
Это проверка «настоящий xlsx», а не «массив похожих строк».

**Часовой пояс.** Тест на дату запускается дважды: `TZ=UTC` и
`TZ=Europe/Kyiv` (в PowerShell — `$env:TZ="Europe/Kyiv"; npx vitest run …`).
Оба обязаны дать `20.09.2026`.

**Проверка:** `npx vitest run workbook ukranianDictionaryNz`.

---

### Этап 3 — i18n

**Что:** десять файлов, один коммит.

| Файл | Действие |
|---|---|
| `shared/i18n/locales/{en,uk,ru}/export.ts` | новый домен, ключи §3.10 |
| `shared/i18n/locales/{en,uk,ru}/index.ts` | импорт + spread |
| `src/test/baseline.test.ts` | `I18N_KEY_COUNT = 395 + 18` |

**В том же коммите:** baseline. Иначе `baseline.test.ts` падает на
«ключей 395», и это выглядит как регресс.

**Проверка:** `npx vitest run baseline`, `npm run lint` (tsc проверит
паритет uk/ru против en — ошибка будет именно здесь).

---

### Этап 4 — UI фичи

**Что:** состояние, таблица превью, модалка.

| Файл | Действие |
|---|---|
| `model/useExportRows.ts` | `presetId`, `overrides: Record<string, string>`, `busy`, `error`, `run()` |
| `ui/ExportPreviewTable.tsx` | таблица; `<input type="date">` в колонке даты |
| `ui/ExcelExportDialog.tsx` | селектор пресета, подсказка про дату, «Скасувати» / «Експортувати», busy |
| `ui/*.test.tsx` | открытие, смена пресета, правка даты, отмена, ошибка, нет заданий |

**Состояние модалки:** `useState` для `presetId` и `overrides`. Навигации,
URL и localStorage нет — промпт этого не просит, `shared/settings` не
трогаем.

**Проверка:** `npx vitest run ExcelExport ExportPreviewTable useExportRows`.

---

### Этап 5 — подключение к странице и стили

**Что:** кнопка на экране учительского курса + CSS.

| Файл | Действие |
|---|---|
| `pages/subject/ui/TeacherCourse.tsx` | кнопка в `page-header-actions`, рендер `<ExcelExportDialog … />` |
| `app/styles/pages/subjects.css` | `.export-*` |
| `src/test/baseline.test.ts` | `cssSelectors()` 469 → 469 + M (M — фактическое число новых селекторов) |
| `src/test/baseline.test.ts` | маршруты **не меняются** (модалка, не маршрут) |
| `pages/subject/ui/TeacherCourse.test.tsx` | кнопка открывает модалку; данные приходят из `useResource` |

**В том же коммите:** baseline по CSS. Новые селекторы обязаны быть
посчитаны и вписаны.

**Проверка:** `npm test`, `npm run lint`, `npm run build`.

---

### Этап 6 — документация и финальная верификация

| Файл | Действие |
|---|---|
| `docs/FRONTEND_STRUCTURE.md` | фича в списке `features/`, рецепт §9 |
| этот план | этапы отмечены выполненными, числа — фактические |

**Финальная верификация (все команды обязательны):**

```powershell
cd frontend
npm ci --no-audit --no-fund
npm run lint      # eslint src && tsc --noEmit -p tsconfig.app.json
npm test          # vitest run
npm run build     # tsc -b && vite build
cd ..
pytest            # должно остаться зелёным: бэкенд не тронут
python tools/check_text_encoding.py
```

**Ручная проверка в браузере** (её не заменяет ни один тест):

1. Открыть курс, где пользователь — TEACHER, нажать «Експортувати у Excel».
2. Убедиться, что строки превью отсортированы по дате создания и
   пронумерованы `1, 2, 3…`.
3. Изменить дату в одной строке, экспортировать, открыть файл: «Дата» —
   выбранная дата, «Зміст» — `15. Алгоритми`, «ДЗ» —
   `(google classroom)` вместо ссылки.
4. Проверить в Excel, что «Дата» — **числовая дата** с форматом
   `dd.mm.yyyy`, а не текст.
5. Переключить язык интерфейса на English и повторить: пресет и колонки
   те же (проверка независимости UI и формата).
6. Открыть Network: при экспорте **ни одного нового запроса** к `/api`.

---

## 6. Тестовая матрица

Все тесты — `*.test.ts(x)` рядом с модулем (конвенция проекта), Vitest +
Testing Library, без новой инфраструктуры.

### 6.1 Движок и реестр (`engine/*.test.ts`)

| # | Проверка | Файл |
|---|---|---|
| 1 | `registerPreset` + `getPreset` возвращают зарегистрированный пресет | `registry.test.ts` |
| 2 | `getPreset("нет-такого")` бросает, `listPresets()` его не содержит | `registry.test.ts` |
| 3 | Сортировка детерминирована: три задания с разными `created_at` идут по возрастанию | `rows.test.ts` |
| 4 | При равных метках порядок по `id` (воспроизводим на том же входе) | `rows.test.ts` |
| 5 | Нумерация `1..N` подряд, без пропусков | `rows.test.ts` |
| 6 | Переопределение даты побеждает дефолт только в своей строке | `rows.test.ts` |
| 7 | Исходный массив **не мутируется**: снимок до вызова совпадает с исходным | `rows.test.ts` |
| 8 | Валидная книга: `xlsx.load(buffer)` проходит, лист с именем пресета есть | `workbook.test.ts` |
| 9 | **Второй пресет из теста** (другие колонки, лист, ширины) собирается без правок движка | `workbook.test.ts` |
| 10 | `sanitizeFilename` убирает `/ \ : * ? " < > \|`, обрезает длину, даёт `_course` на пустом | `filename.test.ts` |
| 11 | `saveBuffer` создаёт `<a download>` с верным `filename` и вызывает `revokeObjectURL` | `download.test.ts` |
| 12 | Ни один модуль `engine/` не содержит строк `Зміст`, `ДЗ`, `Номер` | `workbook.test.ts` |
| 13 | `engine/` не импортирует `presets/` (проверка текстом импортов) | `rows.test.ts` |

### 6.2 Пресет `ukranian_dictionary_nz`

| # | Проверка | Ожидание |
|---|---|---|
| 14 | Удаление `Урок` | `Урок 15. 20.09.2026 Алгоритми` → `15. Алгоритми` |
| 15 | Удаление `DD.MM.YYYY` | `20.09.2026` исчезает |
| 16 | Несколько дат в заголовке | все удалены |
| 17 | Дата в начале / середине / конце | удаляется в любой позиции |
| 18 | Заголовок без `Урок` | без изменений |
| 19 | Заголовок без даты | без изменений |
| 20 | `Урок 20.09.2026` (пусто после удаления) | откат на исходный заголовок |
| 21 | Один URL | `Прочитати матеріал https://example.com/test` → `Прочитати матеріал (google classroom)` |
| 22 | Несколько URL | заменены все |
| 23 | Пустое описание | ячейка пустая, не `undefined` и не «null» |
| 24 | Заголовки колонок | `["Номер","Дата","Зміст","ДЗ"]` |
| 25 | Порядок колонок | ровно как в пресете |
| 26 | Нумерация в книге | `1, 2, 3…` числами |
| 27 | Дата — настоящая | `cell.value instanceof Date` |
| 28 | Формат даты | `cell.numFmt === "dd.mm.yyyy"` |
| 29 | Длинное ДЗ (500+ символов) | сохраняется целиком, `alignment.wrapText === true` |
| 30 | Санитизация имени файла | `Математика 8/А` → `Математика 8_А_електронний_щоденник.xlsx` |
| 31 | Имя файла при пустом курсе | `_course_електронний_щоденник.xlsx` |

### 6.3 UI

| # | Проверка |
|---|---|
| 32 | Кнопка «Експортувати у Excel» рендерится на `TeacherCourse` и открывает модалку |
| 33 | Модалка показывает селектор пресета, подсказку про дату, таблицу и обе кнопки |
| 34 | Превью содержит строки в порядке `1, 2, 3` |
| 35 | Правка даты в строке меняет значение, но не исходный объект задания |
| 36 | «Скасувати» закрывает без вызова генератора |
| 37 | «Експортувати» вызывает `buildWorkbookBuffer` + `saveBuffer` с верным именем |
| 38 | Пустой список заданий → `export.empty`, кнопка экспорта заблокирована |
| 39 | Неизвестный `presetId` → локализованная ошибка, сырое исключение не показывается |
| 40 | Ошибка ExcelJS → `export.error.build`, модалка остаётся открытой |
| 41 | UI на английском + пресет `ukranian_dictionary_nz` → колонки те же |
| 42 | Все строки состояния переведены во всех трёх словарях (падает `tsc`) |

Итого **42 проверки**; `structure.test.ts` требует минимум 204 `it(` и
33 файла тестов — добавление только увеличивает числа.

---

## 7. Ограждения, которые придётся обновить

| Файл | Что именно | Почему |
|---|---|---|
| `src/test/baseline.test.ts` | `I18N_KEY_COUNT = 395` → `395 + 18` | новый домен `export` — 18 ключей (§3.10) |
| `src/test/baseline.test.ts` | `expect(cssSelectors().size).toBe(469)` → `469 + M` | новые `.export-*` правила (M — их фактическое число) |
| `src/test/baseline.test.ts` | маршруты, пол по `it()`, число файлов тестов, 100 000 символов CSS | **не меняются**, но проверяются на каждом прогоне |
| `src/test/structure.test.ts` | `LINE_BUDGETS` — без изменений | новые файлы укладываются в существующие лимиты (`features` ≤ 300) |
| `eslint.config.js` | без изменений | фича не нарушает ни одного из восьми правил `no-restricted-imports` |

Дополнительно проверяется самим прогоном тестов:

* `TeacherCourse.tsx` — 284 строки сейчас; кнопка и рендер диалога должны
  уложить его в бюджет 300. Если нет — выносить `CourseStudents` /
  `CourseGradesOverview` в соседние файлы `pages/subject/ui/`, а **не**
  поднимать бюджет (бюджет — храповик, `LINE_BUDGETS`);
* guardrail #11 — имена `engine/rows.ts`, `engine/filename.ts` вместо
  `helpers.ts`;
* guardrail #10 — наружу из фичи торчит только `index.ts`.

---

## 8. Проверка на каждом этапе

| Этап | Команды |
|---|---|
| 0 | `python tools/check_text_encoding.py` |
| 1 | `npm run lint` · `npx vitest run rows filename registry` |
| 2 | `npx vitest run workbook ukranianDictionaryNz` (плюс прогон с `TZ=Europe/Kyiv`) |
| 3 | `npx vitest run baseline` · `npm run lint` |
| 4 | `npx vitest run ExcelExport ExportPreviewTable useExportRows` · `npm run lint` |
| 5 | `npm test` · `npm run lint` · `npm run build` |
| 6 | полный список из §5, Этап 6, + ручная проверка |

`npm test` в `frontend/` — это `vitest run` (job `frontend` в CI), поэтому
каждый шаг совпадает с тем, что выполнит GitHub Actions.

---

## 9. Риски и откат

| Риск | Как обнаружится | Откат |
|---|---|---|
| Сдвиг даты на день из-за часового пояса | тест с двумя `TZ` + ручная проверка в Excel | сборка `Date` из локальной полночи в `rows.ts`/`workbook.ts` |
| ExcelJS не собрался в Vite (буфер/stream) | `npm run build` | зафиксировать `exceljs@4.4.0`; несовместимость — обсудить, а не молча менять стек |
| Файл не импортируется на `ukranian-dictionary-nz.ua` | ручная проверка | сверить структуру с эталоном; правка локальна в пресете, движок не трогаем |
| Рост бандла (exceljs ≈ 900 КБ gzip) | `npm run build`, размер чанка | `exceljs` подключается **динамически** (`await import("exceljs")` в `workbook.ts`): в начальном чанке его не будет |
| `baseline.test.ts` забыт | `npm test` | — |
| `TeacherCourse.tsx` переполнил бюджет | `structure.test.ts` #1 | вынести подкомпоненты, не поднимать лимит |

Откат в целом: удаление `features/excel-export/**`, трёх файлов `export.ts`,
одной строки в `TeacherCourse.tsx`, блока `.export-*` и зависимости —
это revert. Бэкенд не затронут, поэтому откат ничего не ломает в смежных
частях системы.

---

## 10. Альтернативы (почему не они)

| Альтернатива | Почему отклонена |
|---|---|
| Эндпоинт `/api/courses/{id}/export.xlsx` | промпт §1, §18: экспорт только на клиенте; лишняя нагрузка на сервер и хранение персональных данных заданий |
| `SheetJS` (`xlsx`) | промпт §4 предписывает ExcelJS; у `xlsx` заметно хуже запись стилей и форматирования |
| CSV + переименование в `.xlsx` | запрещено §4; такой файл не откроется как книга |
| `mitt` как шина событий | §2.1: канал связи не нужен, props достаточно |
| Глобальный контекст экспорта в `app/providers` | состояние живёт одну открытую модалку; контекст ради этого — лишняя глобальная точка правды |
| Дата создания из `due_at` | §9 требует именно `created_at` |
| Локализация заголовков колонок под язык UI | сломала бы импорт; §3.8 |
| Новый маршрут `/subjects/:id/export` | промпт §6 — кнопка и модалка на странице курса; маршрут упирается в baseline из 20 маршрутов |

---

## 11. Чек-лист требований промпта → где реализовано

| § промпта | Где в плане |
|---|---|
| 1. Архитектура экспорта, без мутации | §3.1, §3.5 |
| 2. Пресет `ukranian_dictionary_nz` | §3.3, §3.9, этап 2 |
| 3. Только фронтенд | §2 (1–4), §4.3 |
| 4. ExcelJS, формат дат, оформление | §3.6, §3.7, этапы 1–2 |
| 5. `mitt` не нужен | §2.1 |
| 6. Кнопка и интерфейс экспорта | §3.2, этапы 4–5 |
| 7. Превью, редактируемая дата, тексты | §3.6, §3.10 |
| 8. Порядок и нумерация | §3.3 (`sort`), §6.1 №3–5 |
| 9. Дата: дефолт, переопределение, `dd.mm.yyyy` | §3.6, §6.2 №27–28 |
| 10. `Зміст` | §3.9, §6.2 №14–20 |
| 11. `ДЗ` и URL | §3.9, §6.2 №21–23 |
| 12. Система пресетов | §3.3, §3.4, §6.1 №9, 12, 13 |
| 13. Имя файла | §3.8, §6.2 №30–31 |
| 14. Форматирование Excel | §3.7 |
| 15. Локализация | §3.10, этап 3 |
| 16. Ошибки | §3.10 (ключи), §6.3 №38–40 |
| 17. Тесты | §6 (42 проверки) |
| 18. Зависимости | §2 (7–8), этап 1 |

---

## 12. Итог

Семь коммитов поверх ADR-0040, ни одной строки Python, ноль новых
HTTP-запросов и одна новая зависимость — `exceljs`. Всё, что знает про
`ukranian_dictionary_nz`, лежит в одном файле `presets/ukranianDictionaryNz.ts`;
всё, что умеет превращать строки в книгу, — в `engine/`, который о пресете
не знает. Следующий пресет (русский или английский) добавляется одним файлом
и одной строкой в реестре — движок, тесты и страница при этом не меняются.