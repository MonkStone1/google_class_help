/**
 * The shell strings, uk.
 *
 * Split out of the single dictionary (PLAN §3.4): five hundred lines in one
 * file is a file nobody can navigate. `locales/uk/index.ts` glues the
 * domains back together, so `useI18n` and every `t("...")` are unchanged.
 */

export const uk_shell = {
  "topbar.searchPlaceholder": "Пошук завдань, предметів, вчителів…  (Ctrl+K)",
  "topbar.neverSynced": "Ніколи не синхронізовано",
  "topbar.lastSync": "Востаннє синхронізовано: {time}",
  "topbar.cachedData": "Кешовані дані",
  "topbar.sync": "Синхронізувати",
  "topbar.syncing": "Синхронізація…",
  "topbar.syncStuck": "Синхронізація триває незвично довго і, можливо, зависла. Перезапуск перерве поточну спробу та почне нову.",
  "topbar.syncRestart": "Перезапустити синхронізацію",
  "topbar.syncRestartHint": "Перервати поточну спробу та запустити синхронізацію заново. Кешовані дані залишаться доступними, доки триває новий запуск.",
  "topbar.signInAgain": "Увійти знову",
  "topbar.needsReauthHint": "Доступ до Google закінчився. Увійдіть знову, щоб відновити синхронізацію.",
  "topbar.notifications": "Сповіщення",
  "topbar.toggleTheme": "Змінити тему",
  "search.label": "Результати пошуку",
  "search.noResults": "Нічого не знайдено за «{query}»",
  "search.assignments": "Завдання",
  "search.subjects": "Предмети",
  "notif.title": "Нагадування",
  "notif.empty": "Нічого не потребує вашої уваги 🎉",
  "notif.overdue": "Прострочено",
  "notif.dueToday": "Має бути сьогодні",
  "notif.dueTomorrow": "Має бути завтра",
  "notif.clearAll": "Очистити всі",
  "notif.dismiss": "Приховати нагадування",
  "stat.total": "Усього завдань",
  "stat.completed": "Виконано",
  "stat.missing": "Не здано",
  "stat.overdue": "Прострочено",
  "stat.dueToday": "На сьогодні",
  "stat.average": "Середній бал",
  "dash.title": "Головна",
  "dash.showingCached": "Показано останні синхронізовані дані.",
  "dash.nothingOverdue": "Нічого не прострочено 🎉",
  "dash.caughtUp": "Ви все встигаєте.",
  "dash.today": "Сьогодні",
  "dash.noToday": "Сьогодні немає завдань 🎉",
  "dash.tomorrow": "Завтра",
  "dash.noTomorrow": "На завтра завдань немає",
  "dash.upcoming": "Найближчим часом ({days} дн.)",
  "dash.noUpcoming": "Найближчими {days} днями завдань немає",
  "dash.completed": "Нещодавно виконані",
  "dash.noCompleted": "Виконаних завдань ще немає",
  "dash.signInHint": "Увійдіть у Google у розділі «Налаштування» (або натисніть «Синхронізувати»), щоб завантажити дані Classroom.",
} as const;
