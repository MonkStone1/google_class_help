# ADR-0017: Teacher-режим — отдельный маршрут чтения курса

Дата: 2026-09-16
Статус: Accepted
Связанные: [ADR-0002](adr-0002-minimal-oauth-scopes.md), [ADR-0003](adr-0003-sqlite-cache-and-sync.md), [ADR-0004](adr-0004-derived-fields-server-side.md), [ADR-0010](adr-0010-student-sync-route.md), [ADR-0014](adr-0014-parallel-staged-sync.md)

## Контекст

Дашборд умел показывать только **собственные** задания пользователя:
маршрут студента (`studentSubmissions.list(userId="me")` + точечные
`courseWork.get`, см. ADR-0010) по определению не возвращает coursework,
на который у пользователя нет сабмишена. Из-за этого курс, который
пользователь **преподаёт**, отображался пустым: у учителя нет собственных
сабмишенов, а `courseWork.list` студентам недоступен (403).

При этом один Google-аккаунт может одновременно учиться на одних курсах и
преподавать другие, поэтому «учитель/студент» — свойство **курса**, а не
аккаунта.

## Решение

### Scope

К двум существующим **Classroom** read-only scope добавляются ещё два
read-only Classroom scope (промпт-блок `Required scopes`); отдельно общий
OAuth flow также запрашивает OIDC identity scopes `openid`, `profile` и
`email` для userinfo:

- `classroom.student-submissions.students.readonly` — даёт учителю
  `courseWork.list` (все задания курса) и
  `studentSubmissions.list` **по всем ученикам**;
- `classroom.rosters.readonly` — `students.list` (список учеников курса).

Опциональный `classroom.profile.emails` **не** запрашивается: email-адреса
учеников не выводятся, только имена.

> Примечание о фактических scope. Промпт предлагал
> `classroom.coursework.students.readonly`, но Google при согласии
> подменяет его на `classroom.student-submissions.students.readonly`
> (предупреждение «Scope has changed from … to …»): `.students.`-scope'ы
> coursework и submissions слиты так же, как раньше были слены `.me.`-scope'ы
> (ADR-0002). Запрашивать `coursework.students.readonly` поэтому бессмысленно —
> он никогда не будет выдан, а subset-проверка токена в
> `get_valid_credentials()` бесконечно разлогинивала бы пользователя.
> Запрашивается тот scope, который Google реально выдаёт.
>
> Примечание к промпту. В `docs/prompt/Teacher_update.md` есть противоречие:
> блок со списком scope включает `coursework.students.readonly`, а прозаическая
> сноска под ним утверждает, что этот scope использовать не нужно, потому что
> всё покрыто `student-submissions.me.readonly`. Последнее неверно: `.me.`-scope
> даёт доступ только к собственным работам пользователя-студента, а
> `courseWork.list` без учительского `.students.`-scope возвращает 403.
> Реализация следует **блоку со списком scope** (он и технически необходим) с
> поправкой на фактическое имя выдаваемого scope (см. выше):
> `student-submissions.me.readonly` сохраняет студенческий маршрут,
> `student-submissions.students.readonly` открывает учительский. Все
> **Classroom** scopes read-only; OIDC identity scopes нужны только userinfo.

### Определение роли курса

`courses.list(teacherId="me")` возвращает курсы, где пользователь —
преподаватель. Пересечение этого множества с `courses.list()` (все видимые
курсы) даёт роль **на каждый курс**: TEACHER или STUDENT. Курсы, видимые не
как студент и не как учитель (например, доменный администратор), остаются на
студенческом маршруте — поведение не меняется.

### Схема кэша

Новые таблицы в дополнение к существующим (существующие не меняются, чтобы
старый кэш и студенческий маршрут остались валидными без миграций):

- `courses.user_role` — TEACHER/STUDENT;
- `course_students` — ростер учительского курса (student_id, имя, email, фото);
- `coursework_submissions` — сабмишены **всех** учеников, PK
  (course_id, coursework_id, student_id). Отдельно от `submissions`
  (PK course_id+coursework_id) — это сабмишен самого пользователя-студента.

### Синхронизация

Стадийная параллельная синхронизация (ADR-0014) сохранена; меняется только
состав запросов на курс:

```text
TEACHER: courseWork.list(all states) + students.list + studentSubmissions.list(-)  + teachers.list
STUDENT: studentSubmissions.list(userId=me) → точечные courseWork.get        + teachers.list
```

Списки-методы возвращают `None` при HTTP-ошибке, поэтому ошибка загрузки
ростра/сабмишенов **не** затирает кэш (в отличие от пустого ответа, который
значит «данных нет» и приводит к очистке устаревших строк). Внутрикурсовая
зеркальная очистка (удаление coursework/ростера/сабмишенов, которых больше
нет в ответе API) выполняется только для учительских курсов — там список
авторитетен. Студенческий маршрут оставлен байт-в-байт как был.

### API и разделение потоков

Промпт-эндпоинты адаптированы к конвенции `/api`:

```text
GET /api/courses/{course_id}
GET /api/courses/{course_id}/coursework
GET /api/courses/{course_id}/students
GET /api/courses/{course_id}/grades
GET /api/courses/{course_id}/coursework/{coursework_id}
GET /api/courses/{course_id}/coursework/{coursework_id}/submissions
GET /api/courses/{course_id}/students/{student_id}/grades
```

Учительские эндпоинты (`students`, `grades`) запрещены (403) для
студенческого курса. Два потока данных остаются раздельными: общий
`/api/assignments`, дашборд, календарь и `/api/status` фильтруют
`role == STUDENT`, поэтому coursework учителя не попадает в студенческие
агрегаты («мои задания»), а доступен только через страницы курса.
Специфичные производные поля считаются на бэкенде (ADR-0004):
`status ∈ {not_submitted, turned_in, returned, graded}`; отсутствие оценки —
это `not_submitted`/`returned`, а не `0`.

## Последствия

- Курс-учителя показывает **все** задания, ростер и оценки всех учеников;
  студенческий маршрут и его кэш не изменены.
- Токен с двумя старыми scope (`get_valid_credentials` проверяет подмножество)
  считается недействительным → при следующем запуске пользователь проходит
  согласие заново и получает расширенный токен.
- `courseWork.list` учителя может вернуть сотни заданий; список и ростер
  пагинируются, сабмишены по курсу — одним `courseWorkId="-"`-обходом.
- Производные поля учителя (`submission_count`, `graded_count`,
  `average_percent`) сознательно не подмешиваются в личные поля
  (`submitted`/`graded`): учитель не является учеником своего курса.

## Альтернативы

- Определять роль через `teachers.list` и сравнение userId — лишний запрос
  на курс; `courses.list(teacherId="me")` даёт то же одним вызовом.
- Не фильтровать учительский coursework из `/api/assignments` (показывать всё
  вперемешку) — отклонено: ломает студенческие счётчики «to do»/«overdue».
- Показывать e-mail учеников через `classroom.profile.emails` — отклонено:
  промпт просит не запрашивать scope без необходимости, в UI хватает имён.
