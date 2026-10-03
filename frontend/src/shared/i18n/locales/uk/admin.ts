/**
 * The admin strings, uk.
 *
 * Split out of the single dictionary (PLAN §3.4): five hundred lines in one
 * file is a file nobody can navigate. `locales/uk/index.ts` glues the
 * domains back together, so `useI18n` and every `t("...")` are unchanged.
 */

export const uk_admin = {
  // ----------------------------------------------------------------- адмін
  // Показується лише тоді, коли бекенд повідомив is_admin=true (ADR-0035).
  "admin.title": "Адміністрування",
  "admin.dashboardTitle": "Панель звернень",
  "admin.total": "Усього",
  "admin.backToAdmin": "До адміністрування",
  "admin.ticketListTitle": "Усі звернення",
  "admin.filterStatus": "Статус",
  "admin.filterCategory": "Категорія",
  "admin.filterAny": "Будь-який",
  "admin.searchPlaceholder": "Пошук за темою або повідомленням…",
  "admin.search": "Знайти",
  "admin.clearFilters": "Очистити фільтри",
  "admin.empty": "За цими фільтрами звернень немає.",
  "admin.reporter": "Автор",
  "admin.loadFailed": "Не вдалося завантажити звернення.",
  "admin.replyTitle": "Відповідь",
  "admin.displayName": "Ім'я, яке бачить користувач",
  "admin.displayNameHint": "Користувач бачить це ім'я, але автором лишається ваш обліковий запис.",
  "admin.sendAnswer": "Надіслати відповідь",
  "admin.statusChanged": "Статус оновлено.",
  "admin.deleteTitle": "Видалити звернення назавжди?",
  "admin.deleteBody": "Цю дію не можна скасувати. Розмова та її вкладення буде видалено остаточно.",
  "admin.deleteConfirm": "Видалити назавжди",
  "admin.deleteCancel": "Скасувати",
  "admin.deleteButton": "Видалити звернення",
  "admin.deleted": "Звернення видалено.",
  "admin.deleteFailed": "Не вдалося видалити звернення.",
  "admin.notAvailable": "Цей розділ доступний лише адміністраторам.",
  "admin.notAvailableHint": "У вашого облікового запису немає прав адміністратора. Якщо це неочікувано — напишіть у підтримку.",
  "admin.by": "від {name}",
  "admin.adminsTitle": "Адміністратори",
  "admin.adminsAdd": "Додати адміністратора",
  "admin.adminsEmail": "E-mail",
  "admin.adminsEmailHint": "Ім'я в списку генерується з цієї адреси. Доступ зберігатиметься, доки ви його не заберете.",
  "admin.adminsName": "Ім'я",
  "admin.adminsAddedAt": "Дата додання",
  "admin.adminsActions": "Дії",
  "admin.adminsDelete": "Видалити",
  "admin.adminsEmpty": "Адміністраторів ще немає.",
  "admin.adminsEmptyHint": "Додайте за e-mail. Вони зможуть відповідати на тикети та видаляти їх, але не керувати іншими адміністраторами.",
  "admin.adminsLoadFailed": "Не вдалося завантажити список адміністраторів.",
  "admin.adminsAdded": "Адміністратора додано.",
  "admin.adminsAddFailed": "Не вдалося додати адміністратора.",
  "admin.adminsRemoved": "Адміністратора видалено.",
  "admin.adminsDeleteFailed": "Не вдалося видалити адміністратора.",
  "admin.adminsDeleteTitle": "Видалити адміністратора?",
  "admin.adminsDeleteBody": "{email} втратить доступ адміністратора до GoogleClassHelp. Цю дію не можна скасувати.",
  "admin.adminsDeleteConfirm": "Видалити адміністратора",
  "admin.adminsDeleteCancel": "Скасувати",
} as const;
