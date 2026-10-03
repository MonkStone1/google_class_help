/**
 * The feedback strings, ru.
 *
 * Split out of the single dictionary (PLAN §3.4): five hundred lines in one
 * file is a file nobody can navigate. `locales/ru/index.ts` glues the
 * domains back together, so `useI18n` and every `t("...")` are unchanged.
 */

export const ru_feedback = {
  // -------------------------------------------------------------- фидбек
  // ADR-0035. На точке входа два разных действия: «сообщить о проблеме» и
  // «прочитать свои обращения» — это разные намерения, и текст должен делать
  // это очевидным на каждом языке.
  "feedback.title": "Обратная связь",
  "feedback.subtitle": "Сообщите о проблеме или следите за тем, что уже сообщили.",
  "feedback.createTitle": "Создать обращение",
  "feedback.createText": "Опишите проблему или предложите улучшение. Ответ появится здесь.",
  "feedback.mineTitle": "Мои обращения",
  "feedback.mineText": "Следите за разговорами, которые вы начали, со всеми ответами в одном месте.",
  "feedback.newTitle": "Новое обращение",
  "feedback.newLead": "Ваш аккаунт Google уже известен, поэтому полей для имени и почты здесь нет.",
  "feedback.category": "Категория",
  "feedback.category.suggestion": "Предложение",
  "feedback.category.bug": "Ошибка",
  "feedback.category.problem": "Проблема",
  "feedback.category.other": "Другое",
  "feedback.subject": "Тема",
  "feedback.subjectPlaceholder": "Коротко, например «Оценки не обновляются»",
  "feedback.message": "Сообщение",
  "feedback.messagePlaceholder": "Опишите, что произошло. Поддерживается Markdown — **жирный**, `код`, списки.",
  "feedback.attachments": "Вложения",
  "feedback.attachmentsHint": "Необязательно. До 3 файлов по 5 МБ (jpg, png, gif, pdf, txt).",
  "feedback.addFile": "Добавить файл",
  "feedback.removeFile": "Убрать {name}",
  "feedback.submit": "Отправить обращение",
  "feedback.submitting": "Отправляем…",
  "feedback.created": "Обращение отправлено.",
  "feedback.reply": "Ответить",
  "feedback.replyPlaceholder": "Напишите ответ…",
  "feedback.sendReply": "Отправить ответ",
  "feedback.sending": "Отправляем…",
  "feedback.replied": "Ответ отправлен.",
  "feedback.reopenedNotice": "Обращение было закрыто; ваш ответ открыл его снова.",
  "feedback.listTitle": "Мои обращения",
  "feedback.empty": "Обращений пока нет.",
  "feedback.emptyHint": "Сообщите о проблеме — ответ появится здесь.",
  "feedback.loading": "Загрузка обращений…",
  "feedback.ticketNumber": "Обращение #{id}",
  "feedback.status.new": "Новое",
  "feedback.status.in_progress": "В работе",
  "feedback.status.resolved": "Решено",
  "feedback.messagesCount": "сообщений: {count}",
  "feedback.subjectRequired": "Введите тему.",
  "feedback.messageRequired": "Опишите проблему.",
  "feedback.loadFailed": "Не удалось загрузить обращения.",
  "feedback.notFound": "Такого обращения не существует или оно не ваше.",
  "feedback.downloadFile": "Скачать {name}",
  "feedback.you": "Вы",
  "feedback.supportBadge": "Поддержка",
} as const;
