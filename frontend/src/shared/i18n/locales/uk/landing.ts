/**
 * The landing strings, uk.
 *
 * Split out of the single dictionary (PLAN §3.4): five hundred lines in one
 * file is a file nobody can navigate. `locales/uk/index.ts` glues the
 * domains back together, so `useI18n` and every `t("...")` are unchanged.
 */

export const uk_landing = {
  // Публічна головна сторінка (ADR-0029): показується відвідувачам без сесії —
  // опис сайту, дві точки входу та посилання на політику конфіденційності.
  "landing.documentTitle": "Classroom Dashboard — ваш Google Classroom на одному екрані",
  "landing.brand": "Classroom Dashboard",
  "landing.heroTitle": "Ваш Google Classroom на одному екрані",
  "landing.heroLead": "Особистий дашборд для Google Classroom: предмети, завдання, дедлайни, оцінки та нагадування — зібрані на одному екрані замість того, щоб шукати їх у вкладках Classroom.",
  "landing.signIn": "Увійти через Google",
  "landing.signInHint": "Потрібен Google-акаунт, у якому є класи в Classroom. Запитуваний доступ — лише для читання.",
  "landing.whatTitle": "Що це за сайт",
  "landing.whatBody": "Це особистий дашборд для Google Classroom. Увійдіть через власний Google-акаунт — і сайт покаже вам ваші дані з Classroom: він читає те, до чого ви й так маєте доступ, тож нічого вводити двічі не потрібно. Це зручний вигляд поверх Google Classroom, а не заміна йому, і сайт не має жодного стосунку до Google.",
  "landing.featuresTitle": "Що він уміє",
  "landing.feature.subjects.title": "Предмети",
  "landing.feature.subjects.text": "Усі ваші курси на одному екрані: викладачі, кількість завдань і середній бал за кожним предметом.",
  "landing.feature.assignments.title": "Завдання й дедлайни",
  "landing.feature.assignments.text": "Усі завдання з терміном здачі та станом виконання, з фільтрами за статусом, предметом або датою.",
  "landing.feature.grades.title": "Оцінки",
  "landing.feature.grades.text": "Загальний середній бал, оцінки за кожним завданням і таблиця успішності з кожного предмета.",
  "landing.feature.calendar.title": "Календар",
  "landing.feature.calendar.text": "Перегляд за місяцем, тижнем і днем, щоб усі терміни здачі було видно одразу.",
  "landing.feature.search.title": "Пошук і нагадування",
  "landing.feature.search.text": "Пошук серед завдань і предметів, а також список того, що прострочено, на сьогодні й на завтра.",
  "landing.feature.teacher.title": "Режим викладача",
  "landing.feature.teacher.text": "Для курсів, які ви ведете: список студентів, здані роботи та таблиця оцінок за курсом.",
  "landing.howTitle": "Як це працює",
  "landing.how.signIn.title": "Вхід",
  "landing.how.signIn.text": "Натисніть кнопку й підтвердіть доступ на сторінці Google. Сайт ніколи не бачить ваш пароль.",
  "landing.how.sync.title": "Дані синхронізуються",
  "landing.how.sync.text": "Ваші курси, завдання та оцінки завантажуються на сервер і далі оновлюються автоматично у фоні.",
  "landing.how.dashboard.title": "Ви працюєте в дашборді",
  "landing.how.dashboard.text": "Терміни, оцінки й прострочені завдання зібрані в одному місці — і сайт ніколи нічого не змінює в самому Classroom.",
  "landing.dataTitle": "Ваші дані",
  "landing.data.readOnly": "Застосунок просить доступ лише для читання: ваші курси, ваші завдання та власні здані роботи. Нічого іншого.",
  "landing.data.neverWrites": "Він ніколи не створює, не змінює і не видаляє нічого в Google Classroom і ніколи не пише від вашого імені.",
  "landing.data.storage": "Ваш профіль, зашифровані токени доступу та кеш даних Classroom зберігаються на сервері й прив'язані до вашого облікового запису. Кеш можна очистити будь-коли в налаштуваннях.",
  "landing.data.privacyLink": "Прочитати повну політику конфіденційності",
  "landing.ctaTitle": "Готові почати?",
  "landing.ctaText": "Увійдіть через Google-акаунт, у якому є ваші класи, — дашборд сам підхопить ваші дані.",
  "landing.challengeHint": "Пройдіть перевірку нижче, потім увійдіть.",
  "landing.languageLabel": "Мова",
  "landing.footer.privacy": "Політика конфіденційності",
  "landing.footer.terms": "Умови використання",
  "landing.footer.notGoogle": "Google Classroom є товарним знаком Google LLC. Цей сервіс не має відношення до Google LLC.",
  "landing.footer.contact": "Питання та запити на видалення даних:",
  "landing.footer.repository": "github.com/MonkStone1/google_class_help",
  // Донати (ADR-0037). Один текст, дві поверхні: секція на лендингу та
  // картка в налаштуваннях віддають той самий блок.
  "donate.title": "Підтримати проєкт",
  "donate.note": "Ці гроші підуть на підтримання та розвиток проєкту.",
  "donate.qrAlt": "QR-код для донату в {bank}",
  "donate.preview": "Збільшити QR-код {bank}",
  "donate.bank.monobank": "Monobank",
  "donate.bank.privatbank": "PrivatBank",
} as const;
