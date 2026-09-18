import { Component, type ReactNode } from "react";

type Props = { children: ReactNode };
type State = { error: Error | null };

/**
 * Render guard around the routes: an exception inside a page must not leave a
 * blank white window. The fallback keeps the shell (sidebar/topbar) usable and
 * offers a retry that re-mounts the subtree.
 */
export class DashboardBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error) {
    // The backend log is the primary record; this keeps the browser console
    // useful when running the dev server.
    console.error("Dashboard render error:", error);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="page">
          <div className="alert alert-error" role="alert">
            <div>{this.state.error.message || "Something went wrong."}</div>
            <button
              type="button"
              className="button"
              onClick={() => this.setState({ error: null })}
            >
              Reload view
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
