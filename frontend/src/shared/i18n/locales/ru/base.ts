/**
 * The strings every screen needs, ru.
 *
 * Split out of the single dictionary (PLAN §3.4): five hundred lines in one
 * file is a file nobody can navigate. `locales/ru/index.ts` glues the
 * domains back together, so `useI18n` and every `t("...")` are unchanged.
 */

export const ru_base = {
  "app.title": "Доска класса",
  "nav.dashboard": "Главная",
  "nav.subjects": "Предметы",
  "nav.assignments": "Задания",
  "nav.grades": "Оценки",
  "nav.calendar": "Календарь",
  "nav.settings": "Настройки",
  "nav.feedback": "Помощь",
  "nav.admin": "Администрирование",
  "nav.adminTickets": "Тикеты",
  "nav.admins": "Администраторы",
  "nav.overdue.one": "1 просроченное задание",
  "nav.overdue.many": "{count} просроченных заданий",
  // Тосты (ADR-0030). `region` и `dismiss` заменяют собственные английские
  // aria-метки sonner, поэтому скринридер не услышит непереведённую строку.
  "toast.region": "Уведомления",
  "toast.dismiss": "Закрыть уведомление",
  "toast.syncCompleted": "Синхронизация завершена",
  "toast.syncCompletedAt": "Данные Classroom обновлены в {time}",
  "toast.syncFailed": "Не удалось синхронизировать",
  "toast.syncNeedsReauth": "Доступ к Google истёк",
  "signin.turnstileRequired": "Пройдите проверку, чтобы продолжить вход.",
  "signin.turnstilePending": "Перед входом требуется проверка.",
  "card.openInClassroom": "Открыть в Google Classroom",
  "date.today": "Сегодня",
  "date.tomorrow": "Завтра",
  "date.yesterday": "Вчера",
  "date.daysOverdue": "просрочено на {count} дн.",
  "date.inDays": "Через {count} дн.",
  "date.noDueDate": "Без срока",
} as const;
