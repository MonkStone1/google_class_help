/**
 * The admin strings, ru.
 *
 * Split out of the single dictionary (PLAN §3.4): five hundred lines in one
 * file is a file nobody can navigate. `locales/ru/index.ts` glues the
 * domains back together, so `useI18n` and every `t("...")` are unchanged.
 */

export const ru_admin = {
  // ----------------------------------------------------------------- админ
  // Показывается только когда бэкенд сообщил is_admin=true (ADR-0035).
  "admin.title": "Администрирование",
  "admin.dashboardTitle": "Панель обращений",
  "admin.total": "Всего",
  "admin.backToAdmin": "К администрированию",
  "admin.ticketListTitle": "Все обращения",
  "admin.filterStatus": "Статус",
  "admin.filterCategory": "Категория",
  "admin.filterAny": "Любой",
  "admin.searchPlaceholder": "Поиск по теме или сообщению…",
  "admin.search": "Найти",
  "admin.clearFilters": "Сбросить фильтры",
  "admin.empty": "По этим фильтрам обращений нет.",
  "admin.reporter": "Автор",
  "admin.loadFailed": "Не удалось загрузить обращения.",
  "admin.replyTitle": "Ответ",
  "admin.displayName": "Имя, которое видит пользователь",
  "admin.displayNameHint": "Пользователь видит это имя, но автором остаётся ваш аккаунт.",
  "admin.sendAnswer": "Отправить ответ",
  "admin.statusChanged": "Статус обновлён.",
  "admin.deleteTitle": "Удалить обращение навсегда?",
  "admin.deleteBody": "Это действие нельзя отменить. Переписка и её вложения будут удалены безвозвратно.",
  "admin.deleteConfirm": "Удалить навсегда",
  "admin.deleteCancel": "Отмена",
  "admin.deleteButton": "Удалить обращение",
  "admin.deleted": "Обращение удалено.",
  "admin.deleteFailed": "Не удалось удалить обращение.",
  "admin.notAvailable": "Этот раздел доступен только администраторам.",
  "admin.notAvailableHint": "У вашего аккаунта нет прав администратора. Если это неожиданно — напишите в поддержку.",
  "admin.by": "от {name}",
  "admin.adminsTitle": "Администраторы",
  "admin.adminsAdd": "Добавить администратора",
  "admin.adminsEmail": "E-mail",
  "admin.adminsEmailHint": "Имя в списке генерируется из этого адреса. Доступ сохранится, пока вы его не отозвали.",
  "admin.adminsName": "Имя",
  "admin.adminsAddedAt": "Дата добавления",
  "admin.adminsActions": "Действия",
  "admin.adminsDelete": "Удалить",
  "admin.adminsEmpty": "Администраторов пока нет.",
  "admin.adminsEmptyHint": "Добавьте по e-mail. Они смогут отвечать на тикеты и удалять их, но не управлять другими администраторами.",
  "admin.adminsLoadFailed": "Не удалось загрузить список администраторов.",
  "admin.adminsAdded": "Администратор добавлен.",
  "admin.adminsAddFailed": "Не удалось добавить администратора.",
  "admin.adminsRemoved": "Администратор удалён.",
  "admin.adminsDeleteFailed": "Не удалось удалить администратора.",
  "admin.adminsDeleteTitle": "Удалить администратора?",
  "admin.adminsDeleteBody": "{email} потеряет доступ администратора к GoogleClassHelp. Это действие необратимо.",
  "admin.adminsDeleteConfirm": "Удалить администратора",
  "admin.adminsDeleteCancel": "Отмена",
} as const;
