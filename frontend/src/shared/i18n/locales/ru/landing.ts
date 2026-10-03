/**
 * The landing strings, ru.
 *
 * Split out of the single dictionary (PLAN §3.4): five hundred lines in one
 * file is a file nobody can navigate. `locales/ru/index.ts` glues the
 * domains back together, so `useI18n` and every `t("...")` are unchanged.
 */

export const ru_landing = {
  // Публичная главная страница (ADR-0029): показывается посетителям без
  // сессии — описание сайта, две точки входа и ссылка на политику
  // конфиденциальности.
  "landing.documentTitle": "Classroom Dashboard — ваш Google Classroom на одном экране",
  "landing.brand": "Classroom Dashboard",
  "landing.heroTitle": "Ваш Google Classroom на одном экране",
  "landing.heroLead": "Личный дашборд для Google Classroom: предметы, задания, дедлайны, оценки и напоминания — собраны на одном экране вместо того, чтобы искать их по вкладкам Classroom.",
  "landing.signIn": "Войти через Google",
  "landing.signInHint": "Нужен Google-аккаунт, в котором есть классы в Classroom. Запрашиваемый доступ — только для чтения.",
  "landing.whatTitle": "Что это за сайт",
  "landing.whatBody": "Это личный дашборд для Google Classroom. Войдите через свой Google-аккаунт — и сайт покажет вам ваши данные из Classroom: он читает то, к чему у вас и так есть доступ, поэтому вводить ничего дважды не нужно. Это удобный вид поверх Google Classroom, а не замена ему, и сайт никак не связан с Google.",
  "landing.featuresTitle": "Что он умеет",
  "landing.feature.subjects.title": "Предметы",
  "landing.feature.subjects.text": "Все ваши курсы на одном экране: преподаватели, количество заданий и средний балл по каждому предмету.",
  "landing.feature.assignments.title": "Задания и дедлайны",
  "landing.feature.assignments.text": "Все задания со сроком сдачи и статусом выполнения, с фильтрами по статусу, предмету или дате.",
  "landing.feature.grades.title": "Оценки",
  "landing.feature.grades.text": "Общий средний балл, оценки за каждое задание и таблица успеваемости по каждому предмету.",
  "landing.feature.calendar.title": "Календарь",
  "landing.feature.calendar.text": "Виды по месяцу, неделе и дню, чтобы все сроки сдачи были видны сразу.",
  "landing.feature.search.title": "Поиск и напоминания",
  "landing.feature.search.text": "Поиск по заданиям и предметам, а также список того, что просрочено, на сегодня и на завтра.",
  "landing.feature.teacher.title": "Режим преподавателя",
  "landing.feature.teacher.text": "Для курсов, которые вы ведёте: список студентов, сданные работы и таблица оценок по курсу.",
  "landing.howTitle": "Как это работает",
  "landing.how.signIn.title": "Вход",
  "landing.how.signIn.text": "Нажмите кнопку и подтвердите доступ на странице Google. Сайт никогда не видит ваш пароль.",
  "landing.how.sync.title": "Данные синхронизируются",
  "landing.how.sync.text": "Ваши курсы, задания и оценки загружаются на сервер и дальше обновляются автоматически в фоне.",
  "landing.how.dashboard.title": "Вы работаете в дашборде",
  "landing.how.dashboard.text": "Сроки, оценки и просроченные задания собраны в одном месте — и сайт ничего не меняет в самом Classroom.",
  "landing.dataTitle": "Ваши данные",
  "landing.data.readOnly": "Приложение запрашивает доступ только для чтения: ваши курсы, ваши задания и ваши собственные сданные работы. Больше ничего.",
  "landing.data.neverWrites": "Оно никогда не создаёт, не изменяет и не удаляет ничего в Google Classroom и никогда не пишет от вашего имени.",
  "landing.data.storage": "Ваш профиль, зашифрованные токены доступа и кеш данных Classroom хранятся на сервере и привязаны к вашей учётной записи. Кеш можно очистить в любой момент в настройках.",
  "landing.data.privacyLink": "Прочитать полную политику конфиденциальности",
  "landing.ctaTitle": "Готовы начать?",
  "landing.ctaText": "Войдите через Google-аккаунт, в котором есть ваши классы, — дашборд сам подхватит ваши данные.",
  "landing.challengeHint": "Пройдите проверку ниже, затем войдите.",
  "landing.languageLabel": "Язык",
  "landing.footer.privacy": "Политика конфиденциальности",
  "landing.footer.terms": "Условия использования",
  "landing.footer.notGoogle": "Google Classroom является товарным знаком Google LLC. Этот сервис не связан с Google LLC.",
  "landing.footer.contact": "Вопросы и запросы на удаление данных:",
  "landing.footer.repository": "github.com/MonkStone1/google_class_help",
  // Донаты (ADR-0037). Один текст, две поверхности: секция на лендинге и
  // карточка в настройках отдают один и тот же блок.
  "donate.title": "Поддержать проект",
  "donate.note": "Эти деньги пойдут на поддержание и развитие проекта.",
  "donate.qrAlt": "QR-код для доната в {bank}",
  "donate.preview": "Увеличить QR-код {bank}",
  "donate.bank.monobank": "Monobank",
  "donate.bank.privatbank": "PrivatBank",
} as const;
