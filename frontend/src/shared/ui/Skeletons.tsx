import type { ReactNode } from "react";

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden="true" />;
}

export function CardSkeleton() {
  return (
    <div className="card card-skeleton">
      <div className="card-skeleton-row">
        <Skeleton className="skeleton-chip" />
        <Skeleton className="skeleton-chip" />
      </div>
      <Skeleton className="skeleton-title" />
      <Skeleton className="skeleton-line" />
    </div>
  );
}

export function SectionSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="stack">
      {Array.from({ length: rows }, (_, index) => (
        <CardSkeleton key={index} />
      ))}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  subtitle,
  action,
}: {
  icon?: ReactNode;
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      {icon ? <div className="empty-state-icon">{icon}</div> : null}
      <div className="empty-state-title">{title}</div>
      {subtitle ? <div className="empty-state-subtitle">{subtitle}</div> : null}
      {action ? <div className="empty-state-action">{action}</div> : null}
    </div>
  );
}
