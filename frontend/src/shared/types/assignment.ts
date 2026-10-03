import type { UserRole } from "./course.ts";
import type { WithStatus, Wire } from "./wire.ts";

type AssignmentWire = Wire<"AssignmentOut">;

type PriorityLevel = "high" | "medium" | "low";

/** Material attached to an assignment or a submission. */
export type Material = Wire<"MaterialOut">;

/** Derived submission status; missing grade is never rendered as 0. */
export type SubmissionStatus =
    "not_submitted" | "turned_in" | "returned" | "graded";

export type Student = Wire<"StudentOut">;

/** One student's submission for one assignment (teacher view). */
export type Submission = WithStatus<Wire<"SubmissionOut">, SubmissionStatus>;

export type Assignment = Omit<AssignmentWire, "priority" | "role"> & {
    priority: PriorityLevel;
    role: UserRole;
};

/** Assignment page payload: metadata plus every student's submission state. */
export type AssignmentDetail = Omit<
    Wire<"AssignmentDetailOut">,
    "priority" | "role" | "submissions"
> & {
    priority: PriorityLevel;
    role: UserRole;
    submissions: Submission[];
};