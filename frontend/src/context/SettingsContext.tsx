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
} from "../lib/assignmentFilters.ts";
import {
  DEFAULT_SETTINGS,
  type AppSettings,
  type AssignmentStatusFilter,
  type CalendarViewMode,
  type Language,
  type ThemeMode,
} from "../types.ts";
import { LOCALE, detectLanguage, setLocale } from "../dates.ts";

const STORAGE_KEY = "gc-settings";

const CALENDAR_VIEWS: readonly CalendarViewMode[] = ["month", "week", "day"];
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

type SettingsState = AppSettings & {
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
      language: parsed.language ?? detectLanguage(),
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

function applyTheme(mode: ThemeMode) {
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const dark = mode === "dark" || (mode === "system" && prefersDark);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<AppSettings>(loadSettings);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    applyTheme(settings.theme);
    setLocale(LOCALE[settings.language]);
  }, [settings]);

  // Follow OS preference changes while in "system" mode.
  useEffect(() => {
    if (settings.theme !== "system") {
      return;
    }
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const listener = () => applyTheme("system");
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
