/**
 * The settings strings, ru.
 *
 * Split out of the single dictionary (PLAN §3.4): five hundred lines in one
 * file is a file nobody can navigate. `locales/ru/index.ts` glues the
 * domains back together, so `useI18n` and every `t("...")` are unchanged.
 */

export const ru_settings = {
  "settings.title": "Настройки",
  "settings.googleAccount": "Аккаунт Google",
  "settings.connection": "Подключение",
  "settings.signedIn": "Вы вошли как {name}",
  "settings.signedInNoName": "Вход выполнен",
  "settings.notSignedIn": "Вход не выполнен",
  "settings.signOut": "Выйти",
  "settings.signIn": "Войти через Google",
  "settings.openConsent": "Открыть страницу входа Google",
  "settings.signOutConfirm": "Выйти и удалить сохранённый токен Google с этого ПК?",
  "settings.signOutFailed": "Не удалось выйти. Попробуйте снова.",
  "settings.lastSync": "Последняя синхронизация",
  "settings.never": "Никогда",
  "settings.syncNow": "Синхронизировать сейчас",
  "settings.appearance": "Внешний вид",
  "settings.theme": "Тема",
  "settings.light": "Светлая",
  "settings.dark": "Тёмная",
  "settings.system": "Системная",
  "settings.language": "Язык",
  "settings.cards": "Карточки заданий",
  "settings.comfortable": "Удобные",
  "settings.compact": "Компактные",
  "settings.dashboard": "Главная страница",
  "settings.upcomingPeriod": "Период «ближайшее»",
  "settings.days": "{count} дн.",
  "settings.defaultSort": "Сортировка по умолчанию",
  "settings.visibleSections": "Видимые разделы",
  "settings.upcoming": "Ближайшие",
  "settings.stats": "Статистика",
  "settings.reminders": "Напоминания",
  // Шкала, по которой считается ось графика оценок (ADR-0042). Classroom хранит
  // сырые баллы и не сообщает, что они из, поэтому пользователь задаёт это сам.
  "settings.grading": "Оценивание",
  "settings.gradeScale": "Шкала оценивания",
  "settings.gradeScale12": "12 баллов",
  "settings.gradeScale100": "100 баллов",
  "settings.gradeScaleHint": "Применяется ко всем графикам оценок. Google Classroom хранит сырые баллы и не сообщает, что они из.",
  // Что показывает выставленная оценка в таблице «Все ученики» (ADR-0043).
  // Формат выбирает учитель: балл «12» читается не так, как «12 / 12».
  "settings.teacherMatrix": "Таблица «Все ученики»",
  "settings.teacherMatrixHint": "Как показывается выставленная оценка в таблице «Все ученики»: только балл, балл из максимума, только процент или всё вместе.",
  "settings.teacherMatrixPoints": "Только баллы",
  "settings.teacherMatrixRatio": "Балл из максимума",
  "settings.teacherMatrixPercent": "Только проценты",
  "settings.teacherMatrixBoth": "Баллы и проценты",
  "settings.remindOverdue": "Напоминать о просроченных заданиях",
  "settings.remindToday": "Напоминать о заданиях на сегодня",
  "settings.remindTomorrow": "Напоминать о заданиях на завтра",
  "settings.localData": "Локальные данные",
  "settings.cachedData": "Кешированные данные Classroom",
  "settings.cachedHint": "Хранятся локально в data/classroom.db. Очистка удалит всё до следующей синхронизации.",
  "settings.clearData": "Очистить локальные данные",
  "settings.clearConfirm": "Удалить все кешированные задания, предметы и оценки? Это действие нельзя отменить.",
  "settings.cancel": "Отмена",
  "settings.confirmDelete": "Да, удалить",
  "settings.cleared": "Локальные данные очищены.",
  "settings.clearFailed": "Не удалось очистить кеш.",
} as const;
