/** Previous/next over a server-paged list; the total comes with the page. */
export function AdminPagination({
    offset,
    total,
    pageSize,
    onChange,
}: {
    offset: number;
    total: number;
    pageSize: number;
    onChange: (offset: number) => void;
}) {
    return (
        <div className="admin-pagination">
            <button
                type="button"
                className="button"
                disabled={offset === 0}
                onClick={() => onChange(Math.max(0, offset - pageSize))}
            >
                ←
            </button>
            <span className="updated-label">
                {offset + 1}–{Math.min(offset + pageSize, total)} / {total}
            </span>
            <button
                type="button"
                className="button"
                disabled={offset + pageSize >= total}
                onClick={() => onChange(offset + pageSize)}
            >
                →
            </button>
        </div>
    );
}