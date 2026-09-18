# Google Class Help — Teacher Mode, Full Coursework & Student Grades

Implement a new teacher-oriented feature set in the existing Google Class Help application.

IMPORTANT:
- Do NOT assume the current folder structure.
- Do NOT recreate or reorganize the project architecture unless necessary.
- Inspect the existing project and integrate the feature into the current architecture.
- Preserve all existing student functionality.
- Do not break the current Google Classroom integration.
- Use the official Google Classroom API.
- Keep the application local-only and Windows-oriented as in the existing project.

## 1. Required Google Classroom OAuth scopes

Update the OAuth configuration to support both normal student functionality and teacher functionality.

Use these read-only scopes:

```python
SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.student-submissions.me.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.students.readonly",
    "https://www.googleapis.com/auth/classroom.rosters.readonly",
]
````

Optional scope:

```text
https://www.googleapis.com/auth/classroom.profile.emails
```

Use the optional email scope ONLY if the UI/backend actually needs student email addresses.

### Scope purposes

`classroom.courses.readonly`

* Read courses/classes.
* Determine the user's role in each course.
* Load course metadata.

`classroom.student-submissions.me.readonly`

* Read the authenticated user's own submissions.
* Preserve the existing student functionality.

`classroom.coursework.students.readonly` 
* **Don`t use, he sinergy with classroom.student-submissions.me.readonly, and now all functinoally only in classroom.student-submissions.me.readonly !!!**
* Allow a teacher to read coursework for students in a course.
* Read coursework that belongs to the teacher's course even when the authenticated teacher is not personally assigned to that coursework as a student.
* Read student submission and grading information required for teacher views.

`classroom.rosters.readonly`

* Read the students enrolled in a teacher's course.
* Allow the application to display students separately and associate submissions/grades with students.

`classroom.profile.emails`

* Only use if student email addresses are explicitly displayed.
* Do not request this scope unnecessarily.

Do NOT replace the read-only scopes with write-enabled scopes such as:

```text
https://www.googleapis.com/auth/classroom.coursework.students
https://www.googleapis.com/auth/classroom.rosters
https://www.googleapis.com/auth/classroom.courses
```

unless a future feature explicitly requires write access.

The application must remain read-only for Google Classroom data.

---

# 2. Detect teacher courses

For every course returned by Google Classroom, determine whether the authenticated user is a teacher of that course.

Do not assume that the user is either globally a student or globally a teacher.

The same Google account may have:

* student access to some courses;
* teacher access to other courses.

The UI and API behavior must therefore be determined per course.

For a teacher course, expose additional functionality.

For a normal student course, preserve the existing student behavior.

---

# 3. Critical coursework loading fix

The current implementation has an important limitation:

It loads only coursework personally assigned to the authenticated student.

This is NOT sufficient for teacher mode.

For a course where the authenticated user is a teacher, the application must load ALL coursework/assignments belonging to that course.

This includes assignments where:

* the teacher created the assignment;
* the teacher is not personally assigned as a student;
* the assignment is intended for students in the course;
* there are no personal student submissions belonging to the authenticated teacher.

Do NOT use the current student-only coursework logic for teacher courses.

Implement separate logic conceptually equivalent to:

```text
if current_user_is_teacher(course):
    load all coursework for the course
else:
    load the authenticated student's coursework
```

The exact implementation must follow the Google Classroom API semantics and the existing backend architecture.

---

# 4. Pagination

Do not assume that one Google Classroom API request returns all data.

Implement proper pagination for:

* courses;
* coursework;
* students/rosters;
* student submissions;
* any other paginated Classroom API resources used by the feature.

Continue requesting pages until there is no `nextPageToken`.

The UI must receive the complete dataset rather than only the first page.

Handle empty results correctly.

---

# 5. Teacher course page

When opening a course where the authenticated user is a teacher, provide an expanded course interface.

The teacher course page should contain at least:

* course information;
* all assignments/coursework;
* student list;
* grades overview;
* assignment navigation;
* assignment statistics where available.

Example conceptual layout:

```text
Course
────────────────────────────

Course information

Assignments
├── Assignment 1
├── Assignment 2
├── Assignment 3
└── Assignment 4

Students
├── Student A
├── Student B
├── Student C
└── ...

Grades
└── View all student grades
```

The exact visual design should match the existing application.

---

# 6. Teacher grades page

Add a dedicated teacher grades view.

The purpose is to allow the teacher to conveniently see grades for ALL students in the course.

The page should make it possible to understand:

* which students are enrolled;
* which assignments exist;
* which students submitted each assignment;
* which assignments are graded;
* what grade each student received;
* which assignments have not been submitted;
* which assignments have been submitted but not graded.

A spreadsheet-like/table view is appropriate.

Example conceptual structure:

```text
Student        Assignment 1    Assignment 2    Assignment 3
-------------------------------------------------------------
Student A      10/10           8/10             Not submitted
Student B      9/10            Not graded       10/10
Student C      Not submitted   7/10             9/10
```

Do not hard-code this layout.

Use the existing application's design system/components.

---

# 7. Student-specific grades

The teacher must also be able to open a specific student.

For example:

```text
Course
  → Grades
    → Student
```

The student-specific page should show that student's coursework and submission status.

Display:

* assignment title;
* due date;
* submission status;
* submission state;
* whether the assignment was submitted;
* whether it was returned;
* whether it was graded;
* earned points;
* maximum points;
* grade percentage where meaningful;
* submission timestamp where available.

Example:

```text
Student: Student A

Assignment 1
Submitted
Returned
Grade: 9 / 10

Assignment 2
Submitted
Not returned
Grade: Not graded

Assignment 3
Not submitted
```

---

# 8. Dedicated assignment page

Every teacher-course assignment must be clickable.

Opening an assignment must navigate to a dedicated assignment page.

Example:

```text
Course
  → Assignments
    → Assignment
```

The assignment page must contain the assignment's complete relevant information.

Display:

* title;
* description/instructions;
* creation/update information where available;
* due date;
* maximum points;
* materials;
* attached files;
* links;
* submission information;
* student submission list;
* grading information.

Do not require the teacher to open Google Classroom separately just to inspect submissions.

---

# 9. Assignment student submission overview

The assignment page must show the students associated with the assignment and their submission state.

Conceptually:

```text
Assignment: Homework 1

Student              Status             Grade
------------------------------------------------
Student A             Submitted          10/10
Student B             Submitted          8/10
Student C             Not submitted      —
Student D             Returned           9/10
Student E             Not graded        —
```

The actual states must be derived from Google Classroom API data.

Do not infer a grade from a submission merely because a submission exists.

---

# 10. Submission details

For each student submission, display relevant information such as:

* student name;
* submission state;
* whether submitted;
* whether returned/checked;
* whether graded;
* assigned grade;
* maximum grade;
* submission time;
* update time;
* attached files/materials;
* links where available.

Clearly distinguish:

```text
Not submitted
Submitted
Returned
Graded
Not graded
```

A submission existing does not automatically mean it has been graded.

A returned submission does not automatically mean it has a numeric grade.

Handle all combinations safely.

---

# 11. Attached files

If a student submission contains attached files, show them in the assignment/student submission view.

Display useful information such as:

* filename;
* file type;
* source/link where available.

Do not expose inaccessible/private data.

Respect the permissions returned by Google Classroom.

If the API provides a Drive file reference but the application cannot directly access its contents, display the available file/link information rather than pretending the file is downloadable.

---

# 12. Assignment materials

Assignments can contain materials.

Support relevant Classroom material types such as:

* Drive files;
* links;
* YouTube materials;
* other material types supported by the API.

Display them in the assignment page in a clean way.

Do not assume every assignment has materials.

---

# 13. Teacher vs student UI

Do not show teacher-only functionality to normal students.

For a teacher course, expose:

* All Assignments;
* Student Grades;
* Students;
* Assignment submission overview.

For a normal student course, preserve:

* My assignments;
* My submissions;
* My grades;
* Existing student functionality.

The application should not confuse the teacher's account with a student submission in a teacher course.

---

# 14. Backend API design

Integrate the feature into the existing backend rather than blindly creating duplicate APIs.

Conceptually, the backend should support operations equivalent to:

```text
GET /courses
GET /courses/{course_id}
GET /courses/{course_id}/coursework
GET /courses/{course_id}/students
GET /courses/{course_id}/grades

GET /courses/{course_id}/coursework/{coursework_id}
GET /courses/{course_id}/coursework/{coursework_id}/submissions

GET /courses/{course_id}/students/{student_id}/grades
```

These are conceptual endpoints.

Adapt the actual routes to the existing application's API conventions.

The backend should perform Google Classroom API communication.

The frontend should not contain Google OAuth credentials or directly implement sensitive Google API authentication logic.

---

# 15. Data normalization

Do not send raw Google Classroom API objects directly to the frontend if the existing architecture already uses DTOs/models.

Create or extend appropriate backend response models.

Normalize information such as:

```text
Course
Coursework
Student
Submission
Grade
Material
Attachment
```

Keep Google API-specific implementation details inside the backend/service layer.

---

# 16. Error handling

Handle these cases gracefully:

* user is not a teacher;
* course has no students;
* course has no assignments;
* assignment has no submissions;
* student has not submitted;
* submission is not graded;
* submission has no grade;
* assignment has no due date;
* assignment has no maximum points;
* API returns an empty page;
* API returns permission errors;
* OAuth token lacks required scope;
* Google Classroom API temporarily fails;
* network connection is unavailable.

Do not crash the entire application because one assignment or submission cannot be loaded.

Show useful user-facing error messages.

---

# 17. Performance

Avoid making unnecessary Google API requests.

Prefer efficient loading and caching where the existing application already supports caching.

Do not repeatedly fetch the same course roster every time the user changes tabs.

However, do not serve stale data indefinitely.

The implementation should provide a sensible refresh mechanism.

For example:

```text
Refresh
Last updated: 12:42
```

---

# 18. Privacy and security

This application is local-only.

Keep Google authentication tokens outside the frontend source code.

Do not expose:

* OAuth client secrets;
* access tokens;
* refresh tokens;

to the browser frontend unnecessarily.

Teacher/student information must only be displayed to the authenticated user who has the corresponding Google Classroom permissions.

Do not log access tokens or private student data.

---

# 19. Existing student functionality

This feature must NOT remove or break the existing student workflow.

Verify that:

* student courses still load;
* student's own assignments still load;
* student's own submissions still load;
* student's grades still load;
* course navigation still works;
* authentication still works;
* token refresh still works.

Teacher functionality is an extension of the existing application, not a replacement.

---

# 20. UI/UX requirements

Use the existing visual language of Google Class Help.

Do not introduce an unrelated design.

Teacher-specific pages should feel like a natural extension of the application.

Use:

* clear tables;
* readable status badges;
* assignment cards where appropriate;
* breadcrumbs/back navigation;
* loading states;
* empty states;
* error states;
* responsive layouts.

For example:

```text
Course → Grades → Student
Course → Assignments → Assignment
```

Navigation should always make it clear where the user currently is.

---

# 21. Status representation

Create a consistent status representation.

Possible statuses:

```text
Not submitted
Submitted
Turned in
Returned
Graded
Not graded
```

Do not display contradictory statuses.

For example, if the API says that a submission has no assigned grade, do not display `0/100`.

A missing grade is not the same as a zero grade.

---

# 22. Grade calculations

Do not invent grades.

Use the values returned by Google Classroom.

If maximum points are available:

```text
earned / maximum
```

can be displayed.

If a percentage is useful, calculate it only when both values are valid numeric values.

Do not calculate a percentage for an ungraded submission.

Handle zero/undefined maximum points safely.

---

# 23. Testing requirements

Test at least these scenarios:

### Student account

1. Login as a student.
2. Open a normal course.
3. Verify existing assignments still load.
4. Verify own submissions still load.
5. Verify own grades still load.

### Teacher account

1. Login as a teacher.
2. Open a teacher course.
3. Verify ALL coursework is loaded.
4. Verify coursework is not limited to assignments personally associated with the teacher.
5. Open the grades page.
6. Verify all students appear.
7. Verify assignments appear.
8. Verify grades are associated with the correct students.
9. Open a specific student.
10. Verify that student's submission/grade information.
11. Open a specific assignment.
12. Verify all relevant students appear.
13. Verify submission status.
14. Verify grades.
15. Verify returned/not-returned state.
16. Verify attached files/materials where available.

### Edge cases

Test:

* no submissions;
* partially submitted assignment;
* completely ungraded assignment;
* mixed graded/ungraded submissions;
* missing due date;
* missing maximum points;
* student with no submission;
* course with no students;
* course with no coursework;
* paginated coursework;
* paginated students;
* paginated submissions.

---

# 24. Important implementation principle

The most important requirement is:

DO NOT treat a teacher course as if the authenticated teacher were simply a student.

The existing implementation apparently retrieves coursework based on the authenticated student's personal coursework.

Teacher mode must instead retrieve the complete coursework belonging to the teacher's course and then retrieve the relevant student roster and student submissions for that coursework.

The resulting data flow should conceptually be:

```text
Teacher
   ↓
Courses
   ↓
Detect teacher course
   ↓
Load ALL coursework
   ↓
Load course roster
   ↓
Load submissions for coursework
   ↓
Combine:
    Course
    Coursework
    Students
    Submissions
    Grades
    Materials
   ↓
Frontend
   ↓
Teacher course
   ├── Assignments
   ├── Grades
   ├── Students
   └── Assignment details
```

For student mode:

```text
Student
   ↓
Courses
   ↓
Student course
   ↓
My coursework
   ↓
My submissions
   ↓
My grades
```

Keep these two data flows separate where necessary.

---

# 25. Acceptance criteria

The implementation is complete only when all of the following are true:

* [ ] Required read-only OAuth scopes are configured.
* [ ] Teacher courses are detected separately from student courses.
* [ ] Teacher courses load ALL coursework.
* [ ] Coursework is not restricted to assignments personally assigned to the teacher.
* [ ] Coursework pagination works.
* [ ] Student roster pagination works.
* [ ] Submission pagination works.
* [ ] Teacher grades page exists.
* [ ] All students can be viewed separately.
* [ ] Student-specific grade/submission page exists.
* [ ] Every assignment can be opened as a separate page.
* [ ] Assignment page displays relevant assignment information.
* [ ] Assignment page displays student submissions.
* [ ] Submission state is displayed correctly.
* [ ] Returned/checked state is displayed correctly.
* [ ] Graded/not-graded state is displayed correctly.
* [ ] Grades are displayed correctly.
* [ ] Attached files/materials are displayed where available.
* [ ] Student functionality remains intact.
* [ ] No write-enabled Classroom scopes are introduced unnecessarily.
* [ ] OAuth tokens are not exposed to the frontend.
* [ ] API errors are handled gracefully.
* [ ] Empty states are handled gracefully.
* [ ] The application does not crash when an assignment has no submissions.
* [ ] The application does not invent grades or submission states.
* [ ] The implementation follows the existing project architecture and UI.

Before modifying code, inspect the current authentication, Google Classroom service layer, course loading, coursework loading, grade loading, backend DTOs, frontend routing, and existing UI components.

Reuse existing abstractions wherever possible instead of creating duplicate authentication or Classroom API logic.

```
```
