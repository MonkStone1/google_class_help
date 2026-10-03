import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  normalizeCollapsedCourses,
  normalizeCourseFilter,
  normalizeDueFilter,
  normalizeStatusFilter,
} from "../lib/url.ts";
import {
  DEFAULT_SETTINGS,
  type AppSettings,
  type AssignmentStatusFilter,
  type CalendarViewMode,
  type Language,
  type ThemeMode,
} from "../../shared/types/index.ts";
import { LOCALE, detectLanguage, setLocale } from "../../shared/lib/dates.ts";

const STORAGE_KEY = "gc-settings";

const CALENDAR_VIEWS: readonly CalendarViewMode[] = ["month", "week", "day"];

const LANGUAGES: readonly Language[] = ["en", "uk", "ru"];

/**
 * The theme actually painted on `<html>`, as opposed to the `system` /
 * `light` / `dark` mode the user picked. Components that must hand a literal
 * `"light" | "dark"` to a third-party API (sonner's `Toaster`) read this from
 * the context instead of sniffing `document.documentElement` during render:
 * the attribute is written by an effect, so a render triggered by the mode
 * change would still observe the previous value.
 */
export type ResolvedTheme = "light" | "dark";
// The subject page keeps its own tab set; the "has due / no due" pair is a
// separate facet of the assignments filter panel (ADR-0013).
const SUBJECT_TABS: readonly (AssignmentStatusFilter | "all")[] = [
  "all",
  "todo",
  "overdue",
  "completed",
  "graded",
  "ungraded",
];

/** A saved value that is no longer valid falls back to the default. */
function normalizeCalendarView(
  value: AppSettings["calendarView"] | undefined,
): CalendarViewMode {
  return CALENDAR_VIEWS.includes(value as CalendarViewMode)
    ? (value as CalendarViewMode)
    : DEFAULT_SETTINGS.calendarView;
}

/** Same guard for the subject detail tab. */
function normalizeSubjectTab(
  value: AppSettings["subjectTab"] | undefined,
): AssignmentStatusFilter | "all" {
  return SUBJECT_TABS.includes(value as AssignmentStatusFilter)
    ? (value as AssignmentStatusFilter | "all")
    : DEFAULT_SETTINGS.subjectTab;
}

/**
 * A language that is not (or no longer) one of the three dictionaries falls
 * back to the browser preference instead of being trusted: it feeds the
 * dictionary lookup, the date locale AND `<html lang>`, so a stale value in
 * localStorage would otherwise leak a `lang="de"` into the document.
 */
function normalizeLanguage(value: unknown): Language {
  return LANGUAGES.includes(value as Language)
    ? (value as Language)
    : detectLanguage();
}

type SettingsState = AppSettings & {
  /** The theme currently painted on `<html>` (see {@link ResolvedTheme}). */
  resolvedTheme: ResolvedTheme;
  setTheme: (theme: ThemeMode) => void;
  setLanguage: (language: Language) => void;
  update: (patch: Partial<AppSettings>) => void;
  updateSection: (key: keyof AppSettings["sections"], value: boolean) => void;
  updateNotification: (
    key: keyof AppSettings["notifications"],
    value: boolean,
  ) => void;
  dismissNotification: (assignmentId: string) => void;
  dismissAllNotifications: (assignmentIds: string[]) => void;
  reset: () => void;
};

const SettingsContext = createContext<SettingsState | null>(null);

function loadSettings(): AppSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return { ...DEFAULT_SETTINGS, language: detectLanguage() };
    }
    const parsed = JSON.parse(raw) as Partial<AppSettings>;
    return {
      ...DEFAULT_SETTINGS,
      ...parsed,
      // First run (or settings saved before languages existed): follow the OS.
      language: normalizeLanguage(parsed.language),
      sections: { ...DEFAULT_SETTINGS.sections, ...parsed.sections },
      notifications: {
        ...DEFAULT_SETTINGS.notifications,
        ...parsed.notifications,
      },
      dismissedNotifications: Array.isArray(parsed.dismissedNotifications)
        ? parsed.dismissedNotifications.filter(
            (id): id is string => typeof id === "string",
          )
        : DEFAULT_SETTINGS.dismissedNotifications,
      assignmentsFilter: {
        statuses: normalizeStatusFilter(parsed.assignmentsFilter?.statuses),
        due: normalizeDueFilter(parsed.assignmentsFilter?.due),
        courses: normalizeCourseFilter(parsed.assignmentsFilter?.courses),
      },
      calendarView: normalizeCalendarView(parsed.calendarView),
      collapsedGradeCourses: normalizeCollapsedCourses(
        parsed.collapsedGradeCourses,
      ),
      subjectTab: normalizeSubjectTab(parsed.subjectTab),
    };
  } catch {
    return { ...DEFAULT_SETTINGS, language: detectLanguage() };
  }
}

function applyTheme(mode: ThemeMode): ResolvedTheme {
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const dark = mode === "dark" || (mode === "system" && prefersDark);
  const resolved: ResolvedTheme = dark ? "dark" : "light";
  document.documentElement.dataset.theme = resolved;
  return resolved;
}

/**
 * Declare the interface language on `<html>` — the same value the dictionary
 * and the date locale come from.
 *
 * This is the whole point of the helper: a page whose text is Ukrainian while
 * the document still says `lang="en"` is a page browsers (and Google
 * Translate) believe is untranslated, so the translator offers to "translate"
 * a page that is already in the reader's language. `index.html` ships
 * `lang="en"` as a static default and `public/prepaint-init.js` corrects it
 * before the first paint; this keeps it truthful for the rest of the session,
 * including a language switch made on any surface (ADR-0034).
 */
function applyDocumentLanguage(language: Language): void {
  document.documentElement.lang = language;
}

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<AppSettings>(loadSettings);
  // The pre-paint script has already applied the correct theme before the
  // first React render, so the attribute is a truthful seed here and the first
  // paint of a toast never flickers to the wrong side.
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>(
    () => (document.documentElement.dataset.theme === "dark" ? "dark" : "light"),
  );

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    setResolvedTheme(applyTheme(settings.theme));
    setLocale(LOCALE[settings.language]);
    // The document language follows the setting on EVERY surface, not just
    // the landing: this effect is the single owner, so a switch made in
    // Settings (or anywhere else) cannot leave `<html lang>` behind
    // (ADR-0034).
    applyDocumentLanguage(settings.language);
  }, [settings]);

  // Follow OS preference changes while in "system" mode.
  useEffect(() => {
    if (settings.theme !== "system") {
      return;
    }
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const listener = () => setResolvedTheme(applyTheme("system"));
    media.addEventListener("change", listener);
    return () => media.removeEventListener("change", listener);
  }, [settings.theme]);

  const update = useCallback((patch: Partial<AppSettings>) => {
    setSettings((prev) => ({ ...prev, ...patch }));
  }, []);

  const setTheme = useCallback(
    (theme: ThemeMode) => {
      update({ theme });
    },
    [update],
  );

  const setLanguage = useCallback(
    (language: Language) => {
      update({ language });
    },
    [update],
  );

  const updateSection = useCallback(
    (key: keyof AppSettings["sections"], value: boolean) => {
      setSettings((prev) => ({
        ...prev,
        sections: { ...prev.sections, [key]: value },
      }));
    },
    [],
  );

  const updateNotification = useCallback(
    (key: keyof AppSettings["notifications"], value: boolean) => {
      setSettings((prev) => ({
        ...prev,
        notifications: { ...prev.notifications, [key]: value },
      }));
    },
    [],
  );

  /** Hides one reminder by its "kind:assignmentId" key. */
  const dismissNotification = useCallback((key: string) => {
    setSettings((prev) => ({
      ...prev,
      dismissedNotifications: prev.dismissedNotifications.includes(key)
        ? prev.dismissedNotifications
        : [...prev.dismissedNotifications, key],
    }));
  }, []);

  /** Hides several reminders by their "kind:assignmentId" keys. */
  const dismissAllNotifications = useCallback((keys: string[]) => {
    setSettings((prev) => ({
      ...prev,
      dismissedNotifications: [
        ...new Set([...prev.dismissedNotifications, ...keys]),
      ],
    }));
  }, []);

  const reset = useCallback(() => {
    setSettings(DEFAULT_SETTINGS);
  }, []);

  const value = useMemo(
    () => ({
      ...settings,
      resolvedTheme,
      setTheme,
      setLanguage,
      update,
      updateSection,
      updateNotification,
      dismissNotification,
      dismissAllNotifications,
      reset,
    }),
    [
      settings,
      resolvedTheme,
      setTheme,
      setLanguage,
      update,
      updateSection,
      updateNotification,
      dismissNotification,
      dismissAllNotifications,
      reset,
    ],
  );

  return (
    <SettingsContext.Provider value={value}>
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings(): SettingsState {
  const context = useContext(SettingsContext);
  if (!context) {
    throw new Error("useSettings must be used inside SettingsProvider");
  }
  return context;
}
