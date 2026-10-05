/**
 * The settings strings, uk.
 *
 * Split out of the single dictionary (PLAN §3.4): five hundred lines in one
 * file is a file nobody can navigate. `locales/uk/index.ts` glues the
 * domains back together, so `useI18n` and every `t("...")` are unchanged.
 */

export const uk_settings = {
  "settings.title": "Налаштування",
  "settings.googleAccount": "Обліковий запис Google",
  "settings.connection": "З'єднання",
  "settings.signedIn": "Увійшли як {name}",
  "settings.signedInNoName": "Виконано вхід",
  "settings.notSignedIn": "Не виконано вхід",
  "settings.signOut": "Вийти",
  "settings.signIn": "Увійти через Google",
  "settings.openConsent": "Відкрити сторінку входу Google",
  "settings.signOutConfirm": "Вийти та видалити збережений токен Google з цього ПК?",
  "settings.signOutFailed": "Не вдалося вийти. Спробуйте ще раз.",
  "settings.lastSync": "Остання синхронізація",
  "settings.never": "Ніколи",
  "settings.syncNow": "Синхронізувати зараз",
  "settings.appearance": "Зовнішній вигляд",
  "settings.theme": "Тема",
  "settings.light": "Світла",
  "settings.dark": "Темна",
  "settings.system": "Системна",
  "settings.language": "Мова",
  "settings.cards": "Картки завдань",
  "settings.comfortable": "Зручні",
  "settings.compact": "Компактні",
  "settings.dashboard": "Головна сторінка",
  "settings.upcomingPeriod": "Період «найближчим часом»",
  "settings.days": "{count} дн.",
  "settings.defaultSort": "Сортування за замовчуванням",
  "settings.visibleSections": "Видимі розділи",
  "settings.upcoming": "Найближчі",
  "settings.stats": "Статистика",
  "settings.reminders": "Нагадування",
  // Шкала, за якою рахується вісь графіка оцінок (ADR-0042). Classroom зберігає
  // сирі бали й не каже, з чого вони, тож користувач задає це сам.
  "settings.grading": "Оцінювання",
  "settings.gradeScale": "Шкала оцінювання",
  "settings.gradeScale12": "12 балів",
  "settings.gradeScale100": "100 балів",
  "settings.gradeScaleHint": "Застосовується до всіх графіків оцінок. Google Classroom зберігає сирі бали й не каже, з чого вони.",
  // Що показує виставлена оцінка в таблиці «Усі учні» (ADR-0043).
  // Формат обирає вчитель: бал «12» читається не так, як «12 / 12».
  "settings.teacherMatrix": "Таблиця «Усі учні»",
  "settings.teacherMatrixHint": "Як показується виставлена оцінка в таблиці «Усі учні»: лише бал, бал із максимуму, лише відсоток або все разом.",
  "settings.teacherMatrixPoints": "Лише бали",
  "settings.teacherMatrixRatio": "Бал із максимуму",
  "settings.teacherMatrixPercent": "Лише відсотки",
  "settings.teacherMatrixBoth": "Бали і відсотки",
  "settings.remindOverdue": "Нагадувати про прострочені завдання",
  "settings.remindToday": "Нагадувати про завдання на сьогодні",
  "settings.remindTomorrow": "Нагадувати про завдання на завтра",
  "settings.localData": "Локальні дані",
  "settings.cachedData": "Кешовані дані Classroom",
  "settings.cachedHint": "Зберігаються локально у data/classroom.db. Очищення видалить усе до наступної синхронізації.",
  "settings.clearData": "Очистити локальні дані",
  "settings.clearConfirm": "Видалити всі кешовані завдання, предмети та оцінки? Цю дію неможливо скасувати.",
  "settings.cancel": "Скасувати",
  "settings.confirmDelete": "Так, видалити",
  "settings.cleared": "Локальні дані очищено.",
  "settings.clearFailed": "Не вдалося очистити кеш.",
} as const;
