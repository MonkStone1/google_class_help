/**
 * The strings every screen needs, uk.
 *
 * Split out of the single dictionary (PLAN §3.4): five hundred lines in one
 * file is a file nobody can navigate. `locales/uk/index.ts` glues the
 * domains back together, so `useI18n` and every `t("...")` are unchanged.
 */

export const uk_base = {
  "app.title": "Дошка класу",
  "nav.dashboard": "Головна",
  "nav.subjects": "Предмети",
  "nav.assignments": "Завдання",
  "nav.grades": "Оцінки",
  "nav.calendar": "Календар",
  "nav.settings": "Налаштування",
  "nav.feedback": "Підтримка",
  "nav.admin": "Адміністрування",
  "nav.adminTickets": "Тикети",
  "nav.admins": "Адміністратори",
  "nav.overdue.one": "1 прострочене завдання",
  "nav.overdue.many": "{count} прострочених завдань",
  // Тости (ADR-0030). `region` і `dismiss` замінюють власні англійські
  // aria-мітки sonner, тож скринридер не почує неперекладеного рядка.
  "toast.region": "Сповіщення",
  "toast.dismiss": "Закрити сповіщення",
  "toast.syncCompleted": "Синхронізацію завершено",
  "toast.syncCompletedAt": "Дані Classroom оновлено о {time}",
  "toast.syncFailed": "Не вдалося синхронізувати",
  "toast.syncNeedsReauth": "Доступ до Google сплив",
  "signin.turnstileRequired": "Пройдіть перевірку, щоб продовжити вхід.",
  "signin.turnstilePending": "Перед входом потрібна перевірка.",
  "card.openInClassroom": "Відкрити в Google Classroom",
  "date.today": "Сьогодні",
  "date.tomorrow": "Завтра",
  "date.yesterday": "Вчора",
  "date.daysOverdue": "прострочено на {count} дн.",
  "date.inDays": "Через {count} дн.",
  "date.noDueDate": "Немає терміну",
} as const;
