import type { ReactNode } from "react";

export function StatCard({
    label,
    value,
    tone,
    icon,
}: {
    label: string;
    value: string | number;
    tone?: "default" | "danger" | "success" | "warning";
    icon?: ReactNode;
}) {
    return (
        <div className={`stat-card stat-${tone ?? "default"}`}>
            {icon ? <div className="stat-icon">{icon}</div> : null}
            <div>
                <div className="stat-value">{value}</div>
                <div className="stat-label">{label}</div>
            </div>
        </div>
    );
}
