/**
 * Russian dictionary. English is the source of truth: its keys define
 * `I18nKey`, and the other two dictionaries are checked against them
 * (`satisfies Record<I18nKey, string>`), so a missing or extra key fails
 * `tsc` instead of silently falling back at runtime (ADR-0011).
 */

import type { I18nKey } from "./en.ts";

export const ru = {
  "app.title": "Доска класса",

  "nav.dashboard": "Главная",
  "nav.subjects": "Предметы",
  "nav.assignments": "Задания",
  "nav.grades": "Оценки",
  "nav.calendar": "Календарь",
  "nav.settings": "Настройки",
  "nav.feedback": "Обратная связь",
  "nav.admin": "Администрирование",
  "nav.overdue.one": "1 просроченное задание",
  "nav.overdue.many": "{count} просроченных заданий",

  "topbar.searchPlaceholder": "Поиск заданий, предметов, учителей…  (Ctrl+K)",
  "topbar.neverSynced": "Никогда не синхронизировано",
  "topbar.lastSync": "Последняя синхронизация: {time}",
  "topbar.cachedData": "Кешированные данные",
  "topbar.sync": "Синхронизировать",
  "topbar.syncing": "Синхронизация…",
  "topbar.syncStuck":
    "Синхронизация идёт необычно долго и, возможно, зависла. Перезапуск прервёт текущую попытку и начнёт новую.",
  "topbar.syncRestart": "Перезапустить синхронизацию",
  "topbar.syncRestartHint":
    "Прервать текущую попытку и запустить синхронизацию заново. Кешированные данные останутся доступны, пока идёт новый запуск.",
  "topbar.signInAgain": "Войти снова",
  "topbar.needsReauthHint":
    "Доступ к Google истёк. Войдите снова, чтобы возобновить синхронизацию.",
  "topbar.notifications": "Уведомления",
  "topbar.toggleTheme": "Сменить тему",

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
  // Публичная главная страница (ADR-0029): показывается посетителям без
  // сессии — описание сайта, две точки входа и ссылка на политику
  // конфиденциальности.
  "landing.documentTitle":
    "Classroom Dashboard — ваш Google Classroom на одном экране",
  "landing.brand": "Classroom Dashboard",
  "landing.heroTitle": "Ваш Google Classroom на одном экране",
  "landing.heroLead":
    "Личный дашборд для Google Classroom: предметы, задания, дедлайны, оценки и напоминания — собраны на одном экране вместо того, чтобы искать их по вкладкам Classroom.",
  "landing.signIn": "Войти через Google",
  "landing.signInHint":
    "Нужен Google-аккаунт, в котором есть классы в Classroom. Запрашиваемый доступ — только для чтения.",

  "landing.whatTitle": "Что это за сайт",
  "landing.whatBody":
    "Это личный дашборд для Google Classroom. Войдите через свой Google-аккаунт — и сайт покажет вам ваши данные из Classroom: он читает то, к чему у вас и так есть доступ, поэтому вводить ничего дважды не нужно. Это удобный вид поверх Google Classroom, а не замена ему, и сайт никак не связан с Google.",

  "landing.featuresTitle": "Что он умеет",
  "landing.feature.subjects.title": "Предметы",
  "landing.feature.subjects.text":
    "Все ваши курсы на одном экране: преподаватели, количество заданий и средний балл по каждому предмету.",
  "landing.feature.assignments.title": "Задания и дедлайны",
  "landing.feature.assignments.text":
    "Все задания со сроком сдачи и статусом выполнения, с фильтрами по статусу, предмету или дате.",
  "landing.feature.grades.title": "Оценки",
  "landing.feature.grades.text":
    "Общий средний балл, оценки за каждое задание и таблица успеваемости по каждому предмету.",
  "landing.feature.calendar.title": "Календарь",
  "landing.feature.calendar.text":
    "Виды по месяцу, неделе и дню, чтобы все сроки сдачи были видны сразу.",
  "landing.feature.search.title": "Поиск и напоминания",
  "landing.feature.search.text":
    "Поиск по заданиям и предметам, а также список того, что просрочено, на сегодня и на завтра.",
  "landing.feature.teacher.title": "Режим преподавателя",
  "landing.feature.teacher.text":
    "Для курсов, которые вы ведёте: список студентов, сданные работы и таблица оценок по курсу.",

  "landing.howTitle": "Как это работает",
  "landing.how.signIn.title": "Вход",
  "landing.how.signIn.text":
    "Нажмите кнопку и подтвердите доступ на странице Google. Сайт никогда не видит ваш пароль.",
  "landing.how.sync.title": "Данные синхронизируются",
  "landing.how.sync.text":
    "Ваши курсы, задания и оценки загружаются на сервер и дальше обновляются автоматически в фоне.",
  "landing.how.dashboard.title": "Вы работаете в дашборде",
  "landing.how.dashboard.text":
    "Сроки, оценки и просроченные задания собраны в одном месте — и сайт ничего не меняет в самом Classroom.",

  "landing.dataTitle": "Ваши данные",
  "landing.data.readOnly":
    "Приложение запрашивает доступ только для чтения: ваши курсы, ваши задания и ваши собственные сданные работы. Больше ничего.",
  "landing.data.neverWrites":
    "Оно никогда не создаёт, не изменяет и не удаляет ничего в Google Classroom и никогда не пишет от вашего имени.",
  "landing.data.storage":
    "Ваш профиль, зашифрованные токены доступа и кеш данных Classroom хранятся на сервере и привязаны к вашей учётной записи. Кеш можно очистить в любой момент в настройках.",
  "landing.data.privacyLink": "Прочитать полную политику конфиденциальности",
  "landing.ctaTitle": "Готовы начать?",
  "landing.ctaText":
    "Войдите через Google-аккаунт, в котором есть ваши классы, — дашборд сам подхватит ваши данные.",
  "landing.challengeHint": "Пройдите проверку ниже, затем войдите.",
  "landing.languageLabel": "Язык",
  "landing.footer.privacy": "Политика конфиденциальности",
  "landing.footer.terms": "Условия использования",
  "landing.footer.notGoogle":
    "Google Classroom является товарным знаком Google LLC. Этот сервис не связан с Google LLC.",
  "landing.footer.contact": "Вопросы и запросы на удаление данных:",
  "landing.footer.repository": "github.com/MonkStone1/google_class_help",

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

  "badge.overdue": "Просрочено",
  "badge.graded": "Оценено",
  "badge.turnedIn": "Сдано",
  "badge.dueToday": "Сегодня",
  "badge.todo": "К выполнению",
  "badge.high": "Высокий",
  "badge.medium": "Средний",
  "badge.low": "Низкий",
  "badge.ungraded": "Не оценено",
  "badge.late": "С опозданием",

  "card.openInClassroom": "Открыть в Google Classroom",

  "modal.close": "Закрыть",
  "modal.dueDate": "Срок сдачи",
  "modal.noDueDate": "Без срока",
  "modal.submissionState": "Статус сдачи",
  "modal.notStarted": "Не начато",
  "modal.reclaimed": "Возвращено учеником",
  "modal.maxPoints": "Максимальный балл",
  "modal.description": "Описание",
  "modal.materials": "Материалы",
  "modal.material": "Материал",
  "modal.material.drive": "Файл Google Drive",
  "modal.material.link": "Ссылка",
  "modal.material.form": "Google Form",
  "modal.material.youtube": "Видео",
  "modal.at": "в {time}",

  "date.today": "Сегодня",
  "date.tomorrow": "Завтра",
  "date.yesterday": "Вчера",
  "date.daysOverdue": "просрочено на {count} дн.",
  "date.inDays": "Через {count} дн.",
  "date.noDueDate": "Без срока",

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
  "dash.signInHint":
    "Войдите в Google в разделе «Настройки» (или нажмите «Синхронизировать»), чтобы загрузить данные Classroom.",

  "subjects.title": "Предметы",
  "subjects.notSignedIn": "Вход не выполнен",
  "subjects.notSignedInHint":
    "Войдите в Google и синхронизируйте данные, чтобы загрузить курсы.",
  "subjects.empty": "Предметы не найдены",
  "subjects.emptyHint":
    "Нажмите «Синхронизировать», чтобы загрузить курсы Google Classroom.",

  "subject.back": "Все предметы",
  "subject.noTeacher": "Учитель не указан",
  "subject.assignments": "{count} заданий",
  "subject.todo": "{count} к выполнению",
  "subject.overdue": "{count} просрочено",
  "subject.avg": "ср. {value}%",
  "subject.notFound": "Предмет не найден",
  "subject.notFoundHint": "Возможно, он удалён из Google Classroom.",
  "subject.noMatch": "Нет заданий по этому фильтру",
  "subject.section.assignments": "заданий",
  "subject.section.todo": "к выполнению",
  "subject.section.overdue": "просрочено",

  "filter.sortBy": "Сортировать",
  "filter.all": "Все",
  "filter.todo": "К выполнению",
  "filter.overdue": "Просроченные",
  "filter.completed": "Выполненные",
  "filter.graded": "Оценённые",
  "filter.noDue": "Без срока сдачи",
  "filter.ungraded": "Не оценённые",
  "filter.open": "Фильтры",
  "filter.title": "Фильтры",
  "filter.byStatus": "По состоянию",
  "filter.byCourse": "По курсам",
  "filter.selectAll": "Включить все",
  "filter.clearAll": "Выключить все",
  "filter.coursesEmpty": "Курсов пока нет",
  "filter.byDue": "По сроку сдачи",
  "filter.hasDue": "Есть срок сдачи",
  "filter.combineHint":
    "Значения внутри одной секции объединяются по «или», разные секции — по «и».",
  "filter.removeChip": "Убрать фильтр «{value}»",
  "filter.reset": "Сбросить фильтры",
  "filter.noMatch": "Нет заданий по этим фильтрам",
  "filter.showing": "Показано {shown} из {total}",
  "sort.due": "Срок",
  "sort.priority": "Приоритет",
  "sort.grade": "Оценка",
  "sort.newest": "Сначала новые",
  "sort.oldest": "Сначала старые",

  "assignments.title": "Задания",
  "assignments.empty": "Задания не найдены",
  "assignments.emptyHint":
    "Нажмите «Синхронизировать», чтобы загрузить данные Google Classroom.",

  "grades.title": "Оценки",
  "grades.overall": "Общий средний балл: {value}%",
  "grades.empty": "Оценок пока нет",
  "grades.emptyHint":
    "Оценки появятся, когда учителя вернут проверенные работы в Google Classroom.",
  "grades.average": "Средний балл: {value}%",
  "grades.noGrades": "Оценок пока нет",

  "calendar.title": "Календарь",
  "calendar.month": "Месяц",
  "calendar.week": "Неделя",
  "calendar.day": "День",
  "calendar.previous": "Назад",
  "calendar.next": "Вперёд",
  "calendar.weekOf": "Неделя {date}",
  "calendar.empty": "Нет заданий для показа",
  "calendar.emptyHint": "Синхронизируйте данные, чтобы загрузить сроки сдачи.",
  "calendar.noDay": "На этот день заданий нет",
  "calendar.more": "ещё {count}",
  "calendar.points": "{count} баллов",

  "settings.title": "Настройки",
  "settings.googleAccount": "Аккаунт Google",
  "settings.connection": "Подключение",
  "settings.signedIn": "Вы вошли как {name}",
  "settings.signedInNoName": "Вход выполнен",
  "settings.notSignedIn": "Вход не выполнен",
  "settings.signOut": "Выйти",
  "settings.signIn": "Войти через Google",
  "settings.openConsent": "Открыть страницу входа Google",
  "settings.signOutConfirm":
    "Выйти и удалить сохранённый токен Google с этого ПК?",
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
  "settings.remindOverdue": "Напоминать о просроченных заданиях",
  "settings.remindToday": "Напоминать о заданиях на сегодня",
  "settings.remindTomorrow": "Напоминать о заданиях на завтра",
  "settings.localData": "Локальные данные",
  "settings.cachedData": "Кешированные данные Classroom",
  "settings.cachedHint":
    "Хранятся локально в data/classroom.db. Очистка удалит всё до следующей синхронизации.",
  "settings.clearData": "Очистить локальные данные",
  "settings.clearConfirm":
    "Удалить все кешированные задания, предметы и оценки? Это действие нельзя отменить.",
  "settings.cancel": "Отмена",
  "settings.confirmDelete": "Да, удалить",
  "settings.cleared": "Локальные данные очищены.",
  "settings.clearFailed": "Не удалось очистить кеш.",

  "teacher.role": "Преподаватель",
  "teacher.studentRole": "Студент",
  "teacher.tab.assignments": "Все задания",
  "teacher.tab.students": "Студенты",
  "teacher.tab.grades": "Оценки",
  "teacher.updated": "Обновлено {time}",
  "teacher.studentsCount": "{count} студентов",
  "teacher.assignmentsCount": "{count} заданий",
  "teacher.students.empty": "На этот курс никто не записан.",
  "teacher.assignments.empty": "В этом курсе ещё нет заданий.",
  "teacher.grades.title": "Оценки студентов",
  "teacher.grades.viewAll": "Все оценки студентов",
  "teacher.grades.overview": "Обзор оценок",
  "teacher.grades.classAverage": "Средний балл класса: {value}%",
  "teacher.grades.noAverage": "Оценок ещё нет",
  "teacher.grades.empty": "Нет студентов или заданий для показа.",
  "teacher.grades.studentColumn": "Студент",
  "teacher.grades.averageColumn": "Средний",
  "teacher.assignment.submittedCounter": "{submitted}/{total} сдано",
  "teacher.assignment.gradedCounter": "{graded} оценено",
  "teacher.backToCourse": "Назад к курсу",
  "teacher.backToGrades": "Назад к оценкам",
  "teacher.studentGrades": "Оценки: {name}",
  "teacher.noStudentItems": "У этого студента нет заданий в курсе.",
  "teacher.assignment.stats": "Статистика",
  "studentGrades.attachments": "Вложения ({count})",

  "status.not_submitted": "Не сдано",
  "status.turned_in": "Сдано",
  "status.returned": "Возвращено",
  "status.graded": "Оценено",

  "assignment.title": "Задание",
  "assignment.details": "Детали",
  "assignment.description": "Описание",
  "assignment.submissions": "Работы студентов",
  "assignment.createdAt": "Создано",
  "assignment.updatedAt": "Обновлено",
  "assignment.noSubmissions": "Работ пока нет",
  "assignment.column.student": "Студент",
  "assignment.column.status": "Статус",
  "assignment.column.grade": "Оценка",
  "assignment.column.submitted": "Сдано",
  "assignment.stats.submitted": "Сдано",
  "assignment.stats.graded": "Оценено",
  "assignment.stats.notSubmitted": "Не сдано",
  "assignment.notGraded": "Не оценено",
  "assignment.workState": "Статус задания",
  "workState.published": "Опубликовано",
  "workState.draft": "Черновик",
  "workState.unknown": "Неизвестный статус",

  // -------------------------------------------------------------- фидбек
  // ADR-0035. На точке входа два разных действия: «сообщить о проблеме» и
  // «прочитать свои обращения» — это разные намерения, и текст должен делать
  // это очевидным на каждом языке.

  "feedback.title": "Обратная связь",
  "feedback.subtitle":
    "Сообщите о проблеме или следите за тем, что уже сообщили.",
  "feedback.createTitle": "Создать обращение",
  "feedback.createText":
    "Опишите проблему или предложите улучшение. Ответ появится здесь.",
  "feedback.mineTitle": "Мои обращения",
  "feedback.mineText":
    "Следите за разговорами, которые вы начали, со всеми ответами в одном месте.",
  "feedback.newTitle": "Новое обращение",
  "feedback.newLead":
    "Ваш аккаунт Google уже известен, поэтому полей для имени и почты здесь нет.",
  "feedback.category": "Категория",
  "feedback.category.suggestion": "Предложение",
  "feedback.category.bug": "Ошибка",
  "feedback.category.problem": "Проблема",
  "feedback.category.other": "Другое",
  "feedback.subject": "Тема",
  "feedback.subjectPlaceholder": "Коротко, например «Оценки не обновляются»",
  "feedback.message": "Сообщение",
  "feedback.messagePlaceholder":
    "Опишите, что произошло. Поддерживается Markdown — **жирный**, `код`, списки.",
  "feedback.attachments": "Вложения",
  "feedback.attachmentsHint":
    "Необязательно. До 3 файлов по 5 МБ (jpg, png, gif, pdf, txt).",
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
  "feedback.reopenedNotice":
    "Обращение было закрыто; ваш ответ открыл его снова.",
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
  "admin.displayNameHint":
    "Пользователь видит это имя, но автором остаётся ваш аккаунт.",
  "admin.sendAnswer": "Отправить ответ",
  "admin.statusChanged": "Статус обновлён.",
  "admin.deleteTitle": "Удалить обращение навсегда?",
  "admin.deleteBody":
    "Это действие нельзя отменить. Переписка и её вложения будут удалены безвозвратно.",
  "admin.deleteConfirm": "Удалить навсегда",
  "admin.deleteCancel": "Отмена",
  "admin.deleteButton": "Удалить обращение",
  "admin.deleted": "Обращение удалено.",
  "admin.deleteFailed": "Не удалось удалить обращение.",
  "admin.notAvailable": "Этот раздел доступен только администраторам.",
  "admin.notAvailableHint":
    "У вашего аккаунта нет прав администратора. Если это неожиданно — напишите в поддержку.",
  "admin.by": "от {name}",
} satisfies Record<I18nKey, string>;
