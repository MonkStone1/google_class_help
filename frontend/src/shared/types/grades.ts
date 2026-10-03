import type { SubmissionStatus } from "./assignment.ts";
import type { WithStatus, Wire } from "./wire.ts";

export type GradeColumn = Wire<"GradeColumn">;

export type SubmissionCell = WithStatus<Wire<"SubmissionCell">, SubmissionStatus>;

export type StudentGradeRow = Omit<Wire<"StudentGradeRow">, "cells"> & {
    cells: SubmissionCell[];
};

/** Teacher grade matrix: students (rows) × assignments (columns). */
export type TeacherGrades = Omit<
    Wire<"TeacherGradesOut">,
    "rows" | "assignments"
> & {
    assignments: GradeColumn[];
    rows: StudentGradeRow[];
};

export type StudentGradeItem = WithStatus<
    Wire<"StudentGradeItem">,
    SubmissionStatus
>;

export type StudentGrades = Omit<Wire<"StudentGradesOut">, "items"> & {
    items: StudentGradeItem[];
};

export type GradeItem = Wire<"GradeItem">;

export type CourseGrades = Wire<"CourseGrades">;