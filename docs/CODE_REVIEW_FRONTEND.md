# 🔥 GRILL ME — Frontend (GoogleClassHelp) · с решениями

> Ревью в стиле FAANG: без реверансов. Файлы: `src/api.ts`, `App.tsx`, `context/DataContext.tsx`,
> `context/SettingsContext.tsx`, `lib/resource.ts`, `lib/tabPresence.ts`, `lib/assignmentFilters.ts`,
> `lib/search.ts`, `dates.ts`, `i18n.ts`, `pages/*`, `components/*`, `public/sw.js`.
>
> После каждого пункта — блок **✅ Решение** с конкретным кодом под этот проект.
>
> Дата ревью: по состоянию рабочей копии (ветка `master`, коммитов ещё нет).

**Приговор коротко:** фронтенд — самая сильная часть проекта: strict TS без единой
ошибки, dependency-free i18n и фильтры с честной семантикой, продуманная
двухтабная presence через Web Locks + Service Worker. Но: `useResource` кэш —
рассинхронизированные `useState`-тени, `loadData` молча съедает различие между
«нет сети» и «нет аутентификации», `logout` может упасть незаметно, а
`NotificationCenter` пересоздаёт список на каждый рендер. И — барабан — **ноль
тестов** при том, что lib-слой специально спроектирован как чистые функции для
тестируемости. Тестируемость, которая не тестируется, — это не дизайн, это
намерение.

---

## 1. 🐛 Баги и их решения

### 1.1 🔴 `useResource`: два источника правды, рассинхрон при смене ключа

`lib/resource.ts`:

```tsx
const cached = read<T>(key);                          // читается НА КАЖДЫЙ рендер
const [data, setData] = useState<T | null>(cached ? cached.value : null);
...
useEffect(() => {
  const hit = read<T>(key);
  setData(hit ? hit.value : null);
  ...
  void load(false);
}, [key, load]);
```

`read(key)` в теле компонента влияет только на первый маунт; при смене `key`
(`course:A` → `course:B`) state обновляется эффектом — а между рендером с новым
key и запуском эффекта компонент **один рендер показывает данные старого курса**
под заголовком нового. Классический derived-state-from-props разрыв.

**✅ Решение** — кэш читать не в теле, а в ленивом инициализаторе state, а смену
ключа обрабатывать синхронно во время рендера (паттерн «adjust state during
render» из документации React):

```tsx
export function useResource<T>(key: string, fetcher: () => Promise<T>): Resource<T> {
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  // prevKey + prevData: синхронный reset при смене ключа, без эффекта.
  const [state, setState] = useState<{
    key: string;
    data: T | null;
    updatedAt: number | null;
  }>(() => {
    const hit = read<T>(key);   // единственное чтение кэша: инициализатор
    return { key, data: hit ? hit.value : null, updatedAt: hit ? hit.at : null };
  });

  if (state.key !== key) {
    // Смена ключа обрабатывается ВО ВРЕМЯ рендера — React отбрасывает
    // текущий рендер и перерисовывает сразу с новыми данными. Окно, в
    // котором показываются данные старого курса, закрыто.
    const hit = read<T>(key);
    setState({
      key,
      data: hit ? hit.value : null,
      updatedAt: hit ? hit.at : null,
    });
  }

  const loading = state.data === null; // упрощение; см. полный вариант ниже
  ...
}
```

Полный рабочий вариант без упрощений:

```tsx
export type Resource<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
  updatedAt: number | null;
  refresh: () => void;
};

export function useResource<T>(key: string, fetcher: () => Promise<T>): Resource<T> {
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const [entry, setEntry] = useState<Entry<T> | null>(() => read<T>(key));
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(() => !read<T>(key));

  const keyRef = useRef(key);
  if (keyRef.current !== key) {
    keyRef.current = key;
    const hit = read<T>(key);
    setEntry(hit);
    setLoading(!hit);
    setError(null);
  }

  const load = useCallback(async (force: boolean) => {
    const currentKey = keyRef.current;
    const hit = read<T>(currentKey);
    if (hit && !force && Date.now() - hit.at < RESOURCE_TTL_MS) {
      setEntry(hit);
      setError(null);
      setLoading(false);
      return;
    }
    if (!hit) setLoading(true);
    try {
      const value = await fetcherRef.current();
      const at = Date.now();
      const fresh: Entry<T> = { value, at };
      store.set(currentKey, fresh);
      if (keyRef.current === currentKey) setEntry(fresh); // защита от гонки с unmount/сменой ключа
      setError(null);
    } catch (err) {
      if (keyRef.current === currentKey) {
        setError(err instanceof Error ? err.message : "The data could not be loaded.");
      }
    } finally {
      if (keyRef.current === currentKey) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(false);
  }, [key, load]);

  const refresh = useCallback(() => void load(true), [load]);

  return {
    data: entry?.value ?? null,
    loading,
    error,
    updatedAt: entry?.at ?? null,
    refresh,
  };
}
```

Что изменилось по существу: (1) кэш — единственный источник истины, state лишь
его зеркало; (2) смена ключа обрабатывается синхронно в рендере — окно «старые
данные под новым заголовком» исчезло; (3) ответы после unmount/смены ключа
игнорируются проверкой `keyRef.current === currentKey`.

---

### 1.2 🔴 `loadData` не различает «backend мёртв» и «не залогинен»

`Promise.all` из четырёх запросов: падение любого роняет все четыре, а
дашборд, чья фишка — «показывай кэш офлайн», сам выбрасывает три успешных
ответа при частичном сбое.

**✅ Решение** — `Promise.allSettled` + гранулярная установка состояния:

```tsx
const loadData = useCallback(async () => {
  const results = await Promise.allSettled([
    api.getAuthStatus(),
    api.getStatus(),
    api.getCourses(),
    api.getAssignments(),
  ] as const);

  const [authRes, statusRes, coursesRes, assignmentsRes] = results;

  if (authRes.status === "fulfilled") setAuth(authRes.value);
  if (statusRes.status === "fulfilled") setStatus(statusRes.value);
  if (coursesRes.status === "fulfilled") setCourses(coursesRes.value);
  if (assignmentsRes.status === "fulfilled") setAssignments(assignmentsRes.value);

  const firstError = results.find((r) => r.status === "rejected");
  setError(
    firstError && firstError.status === "rejected"
      ? firstError.reason instanceof Error
        ? firstError.reason.message
        : "Google Classroom could not be reached. Showing your last synchronized data."
      : null,
  );
  setLoading(false);
}, []);
```

Теперь при упавшем `/auth/status` (backend перезапускается) курсы и задания
останутся на экране, а ошибка покажется одна и по делу.

---

### 1.3 🟠 `logout` без обработки ошибок + кэш стирается до запроса

```tsx
const logout = useCallback(async () => {
  invalidateAllResources();
  await api.logout();
  await loadData();
}, [loadData]);
```

Упал `api.logout()` → unhandled rejection, UI молчит, `error` остаётся старым,
а кэш уже стёрт.

**✅ Решение** — симметрично `login`/`syncNow`: try/catch + инвалидация только
после успешного ответа:

```tsx
const logout = useCallback(async () => {
  try {
    await api.logout();
    invalidateAllResources(); // кэш учителя стираем только когда выход прошёл
    await loadData();
  } catch (err) {
    setError(
      err instanceof Error
        ? err.message
        : "Sign-out failed. Please try again.",
    );
  }
}, [loadData]);
```

---

### 1.4 🟠 Поллинг логина: мёртвый реф и лишняя нагрузка

`loginPoll.current` дублирует cleanup эффекта и никогда не читается; каждый тик
запускает `loadData()` со всеми четырьмя запросами, один из которых (backend →
Google) — сетевой roundtrip.

**✅ Решение** — убрать реф, поллить только лёгкий `/auth/status` и
останавливаться по результату, а не по таймеру:

```tsx
// Поллинг во время OAuth: только статус входа, никаких /courses и /assignments.
useEffect(() => {
  if (!auth?.login_in_progress) return;
  let cancelled = false;
  const timer = window.setInterval(async () => {
    try {
      const status = await api.getAuthStatus();
      if (cancelled) return;
      setAuth(status);
      if (!status.login_in_progress) {
        window.clearInterval(timer);
        await loadData(); // финальная загрузка один раз, после входа
      }
    } catch {
      // сеть моргнула — следующий тик повторит; ошибки статуса не блокируют UI
    }
  }, 1500);
  return () => {
    cancelled = true;
    window.clearInterval(timer);
  };
}, [auth?.login_in_progress, loadData]);
```

Что исправлено: (1) реф удалён — cleanup эффекта единственный владелец таймера;
(2) тик стоит 1 дешёвый запрос вместо 4; (3) финальный `loadData()` — один раз
по факту входа, а не каждые 1.5 с.

---

### 1.5 🟠 `sw.js` — фокус уходит в первый попавшийся клиент

`clients.find((client) => client.id !== senderId)` при `includeUncontrolled:
true`: если открыто несколько вкладок origin (дашборд + забытая `/settings`),
`focus()` получит произвольную вкладку в порядке перечисления, а не
таб-владелец Web Lock.

**✅ Решение** — выбирать по контракту, а не по порядку: фильтровать по URL
дашборда и предпочитаем видимый клиент:

```js
async function focusAnotherTab(sender) {
  const senderId = sender && sender.id ? sender.id : null;
  const clients = await self.clients.matchAll({
    type: "window",
    includeUncontrolled: true,
  });
  const others = clients.filter((client) => client.id !== senderId);
  if (others.length === 0) {
    if (sender && sender.postMessage) sender.postMessage({ type: "focus-result", ok: false });
    return;
  }

  // Контракт tabPresence: владелец держит Web Lock и живёт по URL дашборда.
  // Приоритет: видимый дашборд → любой дашборд → (fallback) первая вкладка.
  const isDashboard = (url) =>
    url === "/" ||
    url.startsWith("/subjects") ||
    url.startsWith("/assignments") ||
    url.startsWith("/grades") ||
    url.startsWith("/calendar") ||
    url.startsWith("/settings");

  const target =
    others.find((c) => c.visibilityState === "visible" && isDashboard(new URL(c.url).pathname)) ||
    others.find((c) => isDashboard(new URL(c.url).pathname)) ||
    others[0];

  let ok = false;
  if (target) {
    try {
      await target.focus();
      ok = true;
    } catch {
      ok = false; // нет transient activation — переключит кнопка
    }
  }
  if (sender && sender.postMessage) {
    sender.postMessage({ type: "focus-result", ok });
  }
}
```

---

### 1.6 🟡 `sortAssignments`: NaN-ловушка в `new Date(created_at)`

```ts
const due = (a: Assignment) => parseDue(a.due_at)?.getTime() ?? Infinity; // аккуратно
case "newest":
  sorted.sort((a, b) => new Date(b.created_at ?? 0).getTime() - ...);     // сырой Date
```

Невалидная строка `created_at` даёт `NaN` в comparator — сортировка становится
недетерминированной.

**✅ Решение** — единый стандарт аккуратности, тот же, что у `parseDue`:

```ts
function parseCreated(value: string | null | undefined): number {
  if (!value) return 0;
  const time = new Date(value).getTime();
  return Number.isNaN(time) ? 0 : time;
}

case "newest":
  sorted.sort((a, b) => parseCreated(b.created_at) - parseCreated(a.created_at));
  break;
case "oldest":
  sorted.sort((a, b) => parseCreated(a.created_at) - parseCreated(b.created_at));
  break;
```

---

### 1.7 🟡 Поиск живёт в `useState` над роутером

F5 сбрасывает запрос, ссылкой не поделиться, назад браузером не отменяется —
хотя для фильтров вы уже сделали URL-синхронизацию образцово.

**✅ Решение** — один источник состояния, URL:

```tsx
// App.tsx
import { useSearchParams } from "react-router-dom";

export default function App() {
  return (
    <SettingsProvider>
      <DataProvider>
        <AppShell />
      </DataProvider>
    </SettingsProvider>
  );
}

function AppShell() {
  const { t } = useI18n();
  const [searchParams, setSearchParams] = useSearchParams();
  const search = searchParams.get("q") ?? "";
  const onSearch = (value: string) =>
    setSearchParams(
      (prev) => {
        if (value) prev.set("q", value);
        else prev.delete("q");
        return prev;
      },
      { replace: true },
    );
  ...
}
```

Осторожность: не дублировать `q` в `/assignments?status=...` — `setSearchParams`
с функцией сохранит существующие параметры, конфликтов нет.

---

### 1.8 🟡 `i18n.ts`: 827 строк, три языка в одном модуле

Правка одной строки — правка 800-строчного файла; весь перевод грузится для
всех языков сразу.

**✅ Решение** — разрезать по языкам, сохранив dependency-free подход:

```text
src/i18n/
  index.ts    # хук useI18n + тип I18nKey (без изменений публичного API)
  en.ts
  uk.ts
  ru.ts
```

```ts
// src/i18n/index.ts
import { useSettings } from "../context/SettingsContext.tsx";
import type { Language } from "../types.ts";
import { LOCALE } from "../dates.ts";
import { en } from "./en.ts";
import { ru } from "./ru.ts";
import { uk } from "./uk.ts";

const DICTIONARIES = { en, uk, ru } as const;
export type I18nKey = keyof typeof en; // тип ключей выводится из базового словаря

export function useI18n() {
  const { language } = useSettings();
  const dict = DICTIONARIES[language] ?? en;
  const t = (key: I18nKey, vars?: Record<string, string | number>) => { /* как сейчас */ };
  return { t, language };
}
```

`I18nKey` остаётся выведенным из словаря — вся типобезопасность сохраняется,
файл под талый `< 300 строк`, а Vite и так бандлит только используемое.

---

## 2. 🏗️ Архитектура и её решения

### 2.1 🟠 DataContext — god-контекст

Любое изменение статуса синка перерисовывает всё дерево, `useMemo` на 11 полей
сбрасывается почти всегда.

**✅ Решение** — разделить на три контекста, оставив `useData()` фасадом для
страниц, чтобы не переписывать 10 файлов разом:

```tsx
// context/DataContext.tsx — фасад остаётся, внутри всё разделено
const AuthContext = createContext<AuthState | null>(null);
const SyncContext = createContext<SyncState | null>(null);
const CoursesContext = createContext<CoursesState | null>(null);

export function DataProvider({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <SyncProvider>
        <CoursesProvider>{children}</CoursesProvider>
      </SyncProvider>
    </AuthProvider>
  );
}

export function useData(): DataState {
  const auth = useContextSafe(AuthContext, "useData");
  const sync = useContextSafe(SyncContext, "useData");
  const courses = useContextSafe(CoursesContext, "useData");
  return { ...auth, ...sync, ...courses };
}
```

Постепенно страницы переводятся на `useAuth()` / `useCourses()`; таблица оценок
учителя перестаёт перерисовываться от тика синка.

### 2.2 🟠 `resource.ts` — самописный React Query без дедупликации и отмены

Два компонента с одним `key` — два запроса; ответ после unmount пишет в state
размонтированного компонента; нет retry.

**✅ Решение A (рекомендуемое)** — TanStack Query:

```bash
npm i @tanstack/react-query
```

```tsx
// main.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000 } } });

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter><App /></BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
```

```tsx
// pages/StudentGrades.tsx
const grades = useQuery({
  queryKey: ["course", courseId, "student", studentId],
  queryFn: () => api.getStudentGrades(courseId, studentId),
  staleTime: 60_000,
});
// после sync:
queryClient.invalidateQueries({ queryKey: ["course"] });
```

**✅ Решение B (если «без зависимостей» — принцип)** — оставить свой кэш, но
убрать гонки: добавить in-flight дедупликацию и AbortController:

```tsx
const inflight = new Map<string, Promise<unknown>>();

function fetchDedup<T>(key: string, fetcher: () => Promise<T>): Promise<T> {
  const running = inflight.get(key);
  if (running) return running as Promise<T>;
  const promise = fetcher().finally(() => inflight.delete(key));
  inflight.set(key, promise);
  return promise;
}

// в load(): abort при unmount/смене ключа
const controller = new AbortController();
try {
  const value = await fetchWithSignal(controller.signal);
  ...
} catch (err) {
  if (controller.signal.aborted) return; // смена ключа — не ошибка
  ...
}
```

### 2.3 🟡 `tabPresence.ts`: двойные таймауты и синглтон

`FOCUS_RESULT_TIMEOUT_MS` обслуживают два независимых таймера; `handoff`
создаётся всегда; модульный синглтон с побочным эффектом.

**✅ Решение** — один таймаут-хелпер, ленивый fallback, честный DI:

```ts
function withTimeout(promise: Promise<boolean>, ms: number): Promise<boolean> {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(false), ms);
    promise.then((ok) => { clearTimeout(timer); resolve(ok); },
                 () => { clearTimeout(timer); resolve(false); });
  });
}

// внутри createServiceWorkerBridge:
requestFocus(): Promise<boolean> {
  return withTimeout((async () => {
    if (worker.controller) worker.controller.postMessage({ type: "focus" });
    else (await worker.ready).active?.postMessage({ type: "focus" });
    return new Promise<boolean>((resolve) => { resolveResult = resolve; });
  })(), FOCUS_RESULT_TIMEOUT_MS);
}
```

И создать `handoff` лениво — только когда он реально нужен:

```ts
let handoff: FocusBridge | null = null;
function getHandoff(): FocusBridge {
  return (handoff ??= createChannelHandoff(channel, {
    isOwner: () => !duplicate,
    focusWindow,
  }));
}
// requestFocus(): return bridge ? bridge.requestFocus() : getHandoff().requestFocus();
```

### 2.4 🟡 Нет ErrorBoundary — любое исключение рендера это белый экран

**✅ Решение** — граница вокруг роутов + одна честная проверка контракта:

```tsx
// components/ErrorBoundary.tsx
import { Component, type ReactNode } from "react";

type State = { error: Error | null };

export class DashboardBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error) {
    console.error("Dashboard render error:", error); // попадёт в app.log launcher'а через консоль браузера только локально; основной лог — backend
  }

  render() {
    if (this.state.error) {
      return (
        <div className="page">
          <div className="alert alert-error" role="alert">
            {this.state.error.message || "Something went wrong."}
            <button type="button" className="button" onClick={() => this.setState({ error: null })}>
              Reload view
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

// App.tsx
<main className="app-content">
  <DashboardBoundary>
    <Routes>...</Routes>
  </DashboardBoundary>
</main>
```

Плюс защита точки из §3.9:

```tsx
// pages/StudentGrades.tsx — контракт: student есть всегда, но проверяем
const studentName = data?.student?.full_name || studentId;
```

### 2.5 🟡 `types.ts` дублирует backend-схемы вручную

Поле поменяли в `schemas.py` — tsc молчит.

**✅ Решение** — генерация из OpenAPI, который FastAPI отдаёт бесплатно:

```bash
npm i -D openapi-typescript
```

```jsonc
// package.json
"scripts": {
  "gen:api": "openapi-typescript http://127.0.0.1:8000/openapi.json -o src/api-schema.d.ts"
}
```

```ts
// types.ts — доменные алиасы поверх сгенерированных типов
import type { components } from "./api-schema.d.ts";
export type Assignment = components["schemas"]["AssignmentOut"];
export type Course = components["schemas"]["CourseOut"];
export type Submission = components["schemas"]["SubmissionOut"];
```

Ручные типы остаются только там, где это доменные фильтры (`AssignmentsFilter`,
`SortKey`), а не зеркала бэкенда. Поменяли поле в Pydantic → `npm run gen:api`
→ tsc сам покажет каждую сломанную страницу.

---

## 3. 👮 Допрос — ответы и где фиксы

1. **«`read(key)` в теле рендера — а если кэш заполнился между рендером и эффектом?»** —
   Кэш стал единственной истиной, state — его зеркало; смена ключа обрабатывается
   синхронно (§1.1).
2. **«Почему `Promise.all`, а не `allSettled`?»** — Смысла нет, кэш больше не
   выбрасывается (§1.2).
3. **«Где try/catch у logout?»** — Добавлен, кэш стирается после успеха (§1.3).
4. **«`sw.js`: а если других клиентов два?»** — Фильтр по URL дашборда + приоритет
   видимого клиента (§1.5).
5. **«Два таймера на один `FOCUS_RESULT_TIMEOUT_MS` — зачем?»** — Незачем; один
   хелпер `withTimeout` (§2.3).
6. **«`no_due checked alone selects nothing` — где тест?»** — Он появился (§4.5),
   вместе с Vitest.
7. **«Фильтры в URL, поиск — нет. Выбор или забывчивость?»** — Теперь всё в URL (§1.7).
8. **«2098 строк CSS в одном файле — где граница?»** — Разделить по слоям и
   проверить, что классы страниц не пересекаются:

   ```text
   src/styles/
     base.css        # токены (тема), reset, типографика — то, что сейчас в :root
     layout.css      # app-layout, app-main, app-content, page
     components.css  # кнопки, карточки, бейджи, alert
     pages.css       # специфичное для страниц (teacher-grades, notification-center)
   ```

   ```css
   /* main.tsx — порядок критичен: base → layout → components → pages */
   import "./styles/base.css";
   import "./styles/layout.css";
   import "./styles/components.css";
   import "./styles/pages.css";
   ```

9. **«`data?.student.full_name` — а если `student` отсутствует?»** —
   `data?.student?.full_name` + ErrorBoundary (§2.4).
10. **«Ни eslint, ни prettier, ни тестов, ни CI — `tsc -b` всё?»** — Нет; полный
    набор в §4.5.

---

## 4. 💡 Порядок починки (по убыванию цены ошибки)

### 4.1 §1.1–§1.3 — кэш-ресурс и data-loading (один вечер)

Код в §1.1 (полный вариант), §1.2, §1.3. Это самые дорогие баги: их видно
пользователю каждый день.

### 4.2 §1.4 + §1.5 — поллинг и переключение вкладок

Код выше; вместе ~40 минут. Уменьшает нагрузку на backend/Google и чинит
«переключилось не туда».

### 4.3 §2.4 — ErrorBoundary (30 минут)

Код в §2.4; первый же сбой рендера перестаёт быть белым экраном.

### 4.4 §1.6 + §1.7 + §1.8 — мелочи с большим коэффициентом дезинфекции

NaN-ловушка, поиск в URL, разрезание i18n. ~1 час суммарно.

### 4.5 Тесты и инфраструктура — то, чего нет совсем (главный минус)

```bash
npm i -D vitest @testing-library/react @testing-library/jest-dom jsdom
npm i -D eslint @eslint/js typescript-eslint eslint-plugin-react-hooks
npm i -D prettier
```

```jsonc
// package.json (дополнение)
"scripts": {
  "test": "vitest run",
  "lint": "eslint src && tsc --noEmit -p tsconfig.app.json",
  "format": "prettier --write src"
}
```

Первые тесты — на самое хрупкое, что держится на комментариях:

```ts
// src/lib/assignmentFilters.test.ts
import { describe, expect, it } from "vitest";
import { filterAssignments } from "./assignmentFilters.ts";
import type { Assignment } from "../types.ts";

const base = {
  id: "a1", course_id: "c1", course_name: "Math", title: "HW",
  submitted: false, graded: false, is_overdue: false,
  priority: "low", role: "STUDENT",
} as Assignment;

describe("matchesPanelStatuses semantics", () => {
  it("no_due checked alone selects nothing", () => {
    const undated = { ...base, due_at: null };
    expect(filterAssignments([undated], { statuses: ["no_due"], courses: null })).toHaveLength(0);
  });

  it("undated todo task shows when no_due + todo are checked", () => {
    const undated = { ...base, due_at: null };
    expect(
      filterAssignments([undated], { statuses: ["no_due", "todo"], courses: null }),
    ).toHaveLength(1);
  });

  it("dated tasks never match no_due", () => {
    const dated = { ...base, due_at: "2026-01-01T12:00:00" };
    expect(filterAssignments([dated], { statuses: ["no_due", "todo"], courses: null })).toHaveLength(0);
  });
});
```

```ts
// src/lib/tabPresence.test.ts — логика инъектируема специально для этого
import { describe, expect, it } from "vitest";
import { createTabPresence } from "./tabPresence.ts";

function fakeLocks(taken: boolean) {
  return {
    request: (_name: string, _opts: unknown, cb: (lock: object | null) => unknown) => {
      return Promise.resolve(cb(taken ? null : {}));
    },
  };
}

it("second tab with a taken lock is a duplicate", async () => {
  const presence = createTabPresence({ locks: fakeLocks(true) });
  await expect(presence.ready).resolves.toEqual({ duplicate: true });
});

it("first tab owns the lock", async () => {
  const presence = createTabPresence({ locks: fakeLocks(false) });
  await expect(presence.ready).resolves.toEqual({ duplicate: false });
});
```

CI (GitHub Actions, `.github/workflows/ci.yml`): `npm run lint` + `npm test` +
`cd backend && ruff check .` — четыре строки, которые навсегда закрывают
вопрос «а ты это вообще запускал?».

## 5. 📊 Оценка

| Категория | Оценка | Комментарий |
| --- | --- | --- |
| Качество кода | **6.5/10** | Строгий TS, чистые lib-функции; но гонки в resource-кэше и мёртвый loginPoll |
| Читаемость | **7.5/10** | Комментарии уровня «почему», не «что» — редкость; спасает i18n-монолит |
| Производительность | **6/10** | God-контекст перерисовывает всё; поллинг 1.5s бьёт в Google |
| Архитектура | **6/10** | Хорошая декомпозиция lib/pages, но god-context + NIH-кэш + дубли схем |
| Надёжность UX | **6/10** | Сильный offline-нарратив, ослабленный Promise.all и отсутствием ErrorBoundary |
| Инфраструктура | **3/10** | Ноль тестов, ноль линтеров, ноль CI при 12k строк |

**Резюме:** это лучший модуль проекта — фронтенд можно показывать на собеседовании
как пример аккуратного кода (самописный кэш — единственная крупная
самодеятельность). Но «тестируемость намеренно» без единого теста и
«устойчивость к офлайн» через `Promise.all` — это лозунги вместо кода. §1.1–§1.3
+ ErrorBoundary + 10 тестов на lib — два вечера, после которых фронтенд реально
станет образцом. Пока — **«отличный фундамент, накрытый обещаниями, а не
тестами»**.
