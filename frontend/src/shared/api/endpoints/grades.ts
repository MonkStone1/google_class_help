/**
 * Grade matrices: the per-course overview, the teacher matrix and one student's
 * history. All three read the same cached submissions through the backend.
 */

import { request } from "../client.ts";
import type {
    CourseGrades,
    StudentGrades,
    TeacherGrades,
} from "../../types/index.ts";

export const grades = {
    getGrades: () => request<CourseGrades[]>("/grades"),
    getCourseGrades: (courseId: string, signal?: AbortSignal) =>
        request<TeacherGrades>(
            `/courses/${encodeURIComponent(courseId)}/grades`,
            { signal },
        ),
    getStudentGrades: (
        courseId: string,
        studentId: string,
        signal?: AbortSignal,
    ) =>
        request<StudentGrades>(
            `/courses/${encodeURIComponent(courseId)}/students/${encodeURIComponent(studentId)}/grades`,
            { signal },
        ),
};