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

Запрашиваются ровно два scope:

- `classroom.courses.readonly`
- `classroom.student-submissions.me.readonly`

Основание: Google объединил права чтения coursework и собственных submissions —
scope `classroom.student-submissions.me.readonly` сейчас даёт тот же доступ,
что раньше давал `classroom.coursework.me.readonly`, поэтому отдельный
coursework-scope не запрашивается. Все scope read-only: приложение никогда
ничего не изменяет в Google Classroom.

Токен получается через `InstalledAppFlow.run_local_server` (desktop flow):
локальный сервер на случайном порту, браузер открывается автоматически, токен
хранится в `data/token.json` (вне git), освежается автоматически по
refresh-токену.

## Последствия

- Максимум приватности: нет доступа к Drive, почте, профилю сверх выданного.
- Если Google в будущем снова разъединит права coursework и submissions,
  понадобится добавить `classroom.coursework.me.readonly` и перелогиниться;
  точка изменения одна — `backend/auth.py` (SCOPES).

## Альтернативы

- Просить `classroom.coursework.me.readonly` отдельно «на всякий случай» —
  отклонено: лишние права противоречат промпту.
- Service account — отклонено: не работает для данных студента без
  domain-wide delegation.
