/**
 * The shell strings, ru.
 *
 * Split out of the single dictionary (PLAN §3.4): five hundred lines in one
 * file is a file nobody can navigate. `locales/ru/index.ts` glues the
 * domains back together, so `useI18n` and every `t("...")` are unchanged.
 */

export const ru_shell = {
  "topbar.searchPlaceholder": "Поиск заданий, предметов, учителей…  (Ctrl+K)",
  "topbar.neverSynced": "Никогда не синхронизировано",
  "topbar.lastSync": "Последняя синхронизация: {time}",
  "topbar.cachedData": "Кешированные данные",
  "topbar.sync": "Синхронизировать",
  "topbar.syncing": "Синхронизация…",
  "topbar.syncStuck": "Синхронизация идёт необычно долго и, возможно, зависла. Перезапуск прервёт текущую попытку и начнёт новую.",
  "topbar.syncRestart": "Перезапустить синхронизацию",
  "topbar.syncRestartHint": "Прервать текущую попытку и запустить синхронизацию заново. Кешированные данные останутся доступны, пока идёт новый запуск.",
  "topbar.signInAgain": "Войти снова",
  "topbar.needsReauthHint": "Доступ к Google истёк. Войдите снова, чтобы возобновить синхронизацию.",
  "topbar.notifications": "Уведомления",
  "topbar.toggleTheme": "Сменить тему",
  "search.label": "Результаты поиска",
  "search.noResults": "Ничего не найдено по «{query}»",
  "search.assignments": "Задания",
  "search.subjects": "Предметы",
  "notif.title": "Напоминания",
  "notif.empty": "Ничего не требует внимания 🎉",
  "notif.overdue": "Просрочено",
  "notif.dueToday": "Сдать сегодня",
  "notif.dueTomorrow": "Сдать завтра",
  "notif.clearAll": "Очистить всё",
  "notif.dismiss": "Убрать напоминание",
  "stat.total": "Всего заданий",
  "stat.completed": "Выполнено",
  "stat.missing": "Не сдано",
  "stat.overdue": "Просрочено",
  "stat.dueToday": "На сегодня",
  "stat.average": "Средний балл",
  "dash.title": "Главная",
  "dash.showingCached": "Показаны последние синхронизированные данные.",
  "dash.nothingOverdue": "Ничего не просрочено 🎉",
  "dash.caughtUp": "Вы всё успеваете.",
  "dash.today": "Сегодня",
  "dash.noToday": "На сегодня заданий нет 🎉",
  "dash.tomorrow": "Завтра",
  "dash.noTomorrow": "На завтра заданий нет",
  "dash.upcoming": "Ближайшие ({days} дн.)",
  "dash.noUpcoming": "В ближайшие {days} дней заданий нет",
  "dash.completed": "Недавно выполненные",
  "dash.noCompleted": "Выполненных заданий пока нет",
  "dash.signInHint": "Войдите в Google в разделе «Настройки» (или нажмите «Синхронизировать»), чтобы загрузить данные Classroom.",
} as const;
