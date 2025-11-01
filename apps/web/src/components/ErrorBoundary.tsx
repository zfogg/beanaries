import { Component, ErrorInfo, ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

/**
 * Error Boundary component to catch and handle React errors gracefully.
 *
 * Wraps the application to prevent the entire app from crashing when an error occurs.
 * Instead, shows a user-friendly error message with options to recover.
 */
class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  }

  public static getDerivedStateFromError(error: Error): State {
    // Update state so the next render will show the fallback UI
    return { hasError: true, error }
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // Log error to console in development
    console.error('Uncaught error:', error, errorInfo)

    // In production, you would send this to an error tracking service like Sentry
    // Example: Sentry.captureException(error, { contexts: { react: { componentStack: errorInfo.componentStack } } })
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  private handleReload = () => {
    window.location.reload()
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
          <div className="max-w-md w-full">
            <div className="card p-8 text-center">
              {/* Error Icon */}
              <div className="mb-4 flex justify-center">
                <div className="rounded-full bg-red-100 p-3">
                  <svg
                    className="h-8 w-8 text-red-600"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                    />
                  </svg>
                </div>
              </div>

              {/* Error Message */}
              <h1 className="text-2xl font-bold text-gray-900 mb-2">Something went wrong</h1>
              <p className="text-gray-600 mb-6">
                We encountered an unexpected error. This has been logged and we'll look into it.
              </p>

              {/* Error Details (development only) */}
              {import.meta.env.DEV && this.state.error && (
                <details className="mb-6 text-left">
                  <summary className="cursor-pointer text-sm text-gray-500 hover:text-gray-700 mb-2">
                    Show error details
                  </summary>
                  <div className="bg-gray-100 p-3 rounded text-xs font-mono text-gray-800 overflow-auto max-h-40">
                    <div className="font-bold mb-1">{this.state.error.name}:</div>
                    <div>{this.state.error.message}</div>
                    {this.state.error.stack && (
                      <pre className="mt-2 text-gray-600">{this.state.error.stack}</pre>
                    )}
                  </div>
                </details>
              )}

              {/* Action Buttons */}
              <div className="flex gap-3 justify-center">
                <button
                  onClick={this.handleReset}
                  className="btn btn-secondary"
                >
                  Try Again
                </button>
                <button
                  onClick={this.handleReload}
                  className="btn btn-primary"
                >
                  Reload Page
                </button>
              </div>

              {/* Back to Home */}
              <div className="mt-4">
                <a
                  href="/"
                  className="text-sm text-primary-600 hover:text-primary-700"
                >
                  ← Back to Home
                </a>
              </div>
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}

export default ErrorBoundary
