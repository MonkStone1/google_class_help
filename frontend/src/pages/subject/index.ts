/**
 * A course, from the teacher's side, and the student's own course page.
 *
 * Two screens in one slice because they are two tabs of the same subject: the
 * teacher sees the roster and every assignment, the student sees their own
 * work. Splitting them would put a tab switch and a course ID into two URLs
 * that both mean "this course".
 */

export { SubjectDetail } from "./ui/SubjectDetail.tsx";
export { TeacherCourse } from "./ui/TeacherCourse.tsx";