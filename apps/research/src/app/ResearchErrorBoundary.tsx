import { Component, type ErrorInfo, type ReactNode } from "react";

interface State {
  failed: boolean;
}

export class ResearchErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("research_ui_render_failed", error, info.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="research-fatal-error">
        <img src="/logo-mark-v2.png" alt="" />
        <h1>Research workspace could not render</h1>
        <p>No alternate tenant data was loaded. Reload the secured workspace or return to the queue.</p>
        <span>
          <button onClick={() => window.location.reload()} type="button">Reload workspace</button>
          <a href="/queue">Return to queue</a>
        </span>
      </main>
    );
  }
}
