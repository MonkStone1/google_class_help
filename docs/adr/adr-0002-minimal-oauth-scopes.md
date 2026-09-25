# ADR-0002: Минимальный набор OAuth scopes

Дата: 2026-09-14
Статус: Accepted

## Контекст

Приложению нужны: курсы, задания (courseWork), даты сдачи, баллы, описания,
материалы и собственные сабмишены студента. Промпт требует запрашивать
минимум прав и не обращаться к Google сверх них. Референсный скрипт
`backend/test_classroom.py` использовал `classroom.courses.readonly` и
`classroom.student-submissions.me.readonly`.

## Решение

Запрашиваются scopes двух разных групп.

### Идентификация пользователя

Hosted- и desktop-входы вызывают Google OIDC userinfo, чтобы получить
стабильный `sub`, имя и email. Для этого Google требует `openid` и `profile`;
для email дополнительно запрашивается `email`:

- `openid`
- `profile`
- `email`

Эти scopes используются только для профиля и не дают доступа к записи в
Google Classroom.

### Данные Classroom

Запрашиваются ровно четыре read-only Classroom scope:

- `classroom.courses.readonly`
- `classroom.student-submissions.me.readonly`
- `classroom.student-submissions.students.readonly`
- `classroom.rosters.readonly`

Основание: Google объединил права чтения coursework и собственных submissions —
scope `classroom.student-submissions.me.readonly` сейчас даёт тот же доступ,
что раньше давал `classroom.coursework.me.readonly`, поэтому отдельный
coursework-scope не запрашивается. Все Classroom scopes read-only: приложение
никогда ничего не изменяет в Google Classroom.

Токен получается через `InstalledAppFlow.run_local_server` (desktop flow) или
через server-owned web OAuth flow (hosted); в обоих случаях scopes хранятся в
общем `backend/oauth_transport.py`.

## Последствия

- Максимум приватности: нет доступа к Drive, почте, профилю сверх выданного.
- Desktop-токен, выпущенный до добавления `openid`/`profile`/`email`, не
  проходит проверку полного набора scopes и один раз потребует повторного
  Google consent; hosted-стенд с новой локальной БД начинается чисто.
- Если Google в будущем снова разъединит права coursework и submissions,
  понадобится добавить `classroom.coursework.me.readonly` и перелогиниться;
  точка изменения одна — `backend/oauth_transport.py` (`SCOPES`).

## Альтернативы

- Просить `classroom.coursework.me.readonly` отдельно «на всякий случай» —
  отклонено: лишние права противоречат промпту.
- Service account — отклонено: не работает для данных студента без
  domain-wide delegation.
