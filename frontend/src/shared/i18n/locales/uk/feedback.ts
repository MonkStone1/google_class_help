/**
 * The feedback strings, uk.
 *
 * Split out of the single dictionary (PLAN §3.4): five hundred lines in one
 * file is a file nobody can navigate. `locales/uk/index.ts` glues the
 * domains back together, so `useI18n` and every `t("...")` are unchanged.
 */

export const uk_feedback = {
  // -------------------------------------------------------------- фідбек
  // ADR-0035. На точці входу дві окремі дії: «повідомити про проблему» і
  // «прочитати свої звернення» — це різні наміри, і текст має робити це
  // очевидним у кожній мові.
  "feedback.title": "Зворотний зв'язок",
  "feedback.subtitle": "Повідомте про проблему або стежте за тим, що вже повідомили.",
  "feedback.createTitle": "Створити звернення",
  "feedback.createText": "Опишіть проблему або запропонуйте покращення. Відповідь з'явиться тут.",
  "feedback.mineTitle": "Мої звернення",
  "feedback.mineText": "Стежте за розмовами, які ви почали, з усіма відповідями в одному місці.",
  "feedback.newTitle": "Нове звернення",
  "feedback.newLead": "Ваш обліковий запис Google уже відомий, тому полів для імені та пошти тут немає.",
  "feedback.category": "Категорія",
  "feedback.category.suggestion": "Пропозиція",
  "feedback.category.bug": "Помилка",
  "feedback.category.problem": "Проблема",
  "feedback.category.other": "Інше",
  "feedback.subject": "Тема",
  "feedback.subjectPlaceholder": "Коротко, наприклад «Оцінки не оновлюються»",
  "feedback.message": "Повідомлення",
  "feedback.messagePlaceholder": "Опишіть, що сталося. Підтримується Markdown — **жирний**, `код`, списки.",
  "feedback.attachments": "Вкладення",
  "feedback.attachmentsHint": "Необов'язково. До 3 файлів по 5 МБ (jpg, png, gif, pdf, txt).",
  "feedback.addFile": "Додати файл",
  "feedback.removeFile": "Прибрати {name}",
  "feedback.submit": "Надіслати звернення",
  "feedback.submitting": "Надсилаємо…",
  "feedback.created": "Звернення надіслано.",
  "feedback.reply": "Відповісти",
  "feedback.replyPlaceholder": "Напишіть відповідь…",
  "feedback.sendReply": "Надіслати відповідь",
  "feedback.sending": "Надсилаємо…",
  "feedback.replied": "Відповідь надіслано.",
  "feedback.reopenedNotice": "Звернення було закрите; ваша відповідь відкрила його знову.",
  "feedback.listTitle": "Мої звернення",
  "feedback.empty": "Звернень ще немає.",
  "feedback.emptyHint": "Повідомте про проблему — відповідь з'явиться тут.",
  "feedback.loading": "Завантаження звернень…",
  "feedback.ticketNumber": "Звернення #{id}",
  "feedback.status.new": "Нове",
  "feedback.status.in_progress": "У роботі",
  "feedback.status.resolved": "Вирішено",
  "feedback.messagesCount": "повідомлень: {count}",
  "feedback.subjectRequired": "Введіть тему.",
  "feedback.messageRequired": "Опишіть проблему.",
  "feedback.loadFailed": "Не вдалося завантажити звернення.",
  "feedback.notFound": "Такого звернення не існує або воно не ваше.",
  "feedback.downloadFile": "Завантажити {name}",
  "feedback.you": "Ви",
  "feedback.supportBadge": "Підтримка",
} as const;
