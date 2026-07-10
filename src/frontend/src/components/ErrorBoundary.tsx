import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-full flex-col items-center justify-center gap-4 p-8 text-center">
          <span className="text-4xl">⚠️</span>
          <h2 className="text-xl font-semibold text-gray-800 dark:text-gray-200">
            Something went wrong
          </h2>
          <p className="text-sm text-gray-500">The API may be unreachable.</p>
          <button
            onClick={() => this.setState({ hasError: false })}
            className="rounded-lg bg-[#003087] px-4 py-2 text-sm text-white hover:bg-[#00236e]"
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
