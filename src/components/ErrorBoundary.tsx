/**
 * ErrorBoundary — catches render/runtime errors in its subtree and shows a calm,
 * recoverable fallback instead of letting a throw white-screen the window. The
 * WebGPU/GLTF viewport paths are the realistic crash source, so the app wraps
 * both the whole view and the viewport pane (a viewport crash then degrades to a
 * recoverable card rather than killing the editor).
 *
 * "Try again" clears the error and remounts the subtree; "Reload" restarts the
 * window. Caught errors are routed through the shared logger.
 */
import { Component, type ErrorInfo, type ReactNode } from "react";
import { RefreshCw, TriangleAlert } from "lucide-react";

import { logError } from "../lib/logger";
import { ACCENT_CTA } from "../lib/styles";

interface Props {
  children: ReactNode;
  /** Where the boundary sits, used in the log label (e.g. "viewport"). */
  label?: string;
}

interface State {
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    logError(`render error in ${this.props.label ?? "app"}`, error, {
      componentStack: info.componentStack ?? "",
    });
  }

  private reset = () => this.setState({ error: null });

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="grid h-full min-h-0 w-full flex-1 place-items-center bg-surface p-8">
        <div className="flex max-w-100 flex-col items-center gap-3 text-center">
          <span className="grid h-12 w-12 place-items-center rounded-xl border border-danger-line bg-danger-bg text-danger">
            <TriangleAlert size={26} strokeWidth={1.6} />
          </span>
          <h2 className="text-base font-bold tracking-snug text-ink">Something went wrong</h2>
          <p className="text-body leading-normal text-ink-2">
            This part of the app hit an unexpected error and stopped. Your work is saved; you can
            try again or reload the window.
          </p>
          {error.message && (
            <pre className="mt-1 max-h-28 w-full overflow-auto rounded-lg border border-line bg-surface-2 px-3 py-2 text-left font-mono text-caption text-ink-3">
              {error.message}
            </pre>
          )}
          <div className="mt-2 flex items-center gap-2">
            <button
              type="button"
              onClick={this.reset}
              className="inline-flex h-8 items-center gap-1.75 rounded-lg border border-line-2 bg-surface px-3 text-body font-medium text-ink-2 transition-colors duration-150 hover:border-line-3 hover:text-ink"
            >
              <RefreshCw size={14} strokeWidth={1.8} />
              Try again
            </button>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className={`${ACCENT_CTA} h-8 px-3`}
            >
              Reload
            </button>
          </div>
        </div>
      </div>
    );
  }
}
