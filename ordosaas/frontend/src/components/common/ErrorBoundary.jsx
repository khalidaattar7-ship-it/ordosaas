import { Component } from 'react'

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-screen flex-col items-center justify-center gap-3 text-center">
          <h1 className="text-2xl font-semibold text-gray-800">Une erreur est survenue</h1>
          <p className="text-sm text-gray-500">{String(this.state.error?.message || this.state.error)}</p>
          <button className="btn-primary" onClick={() => window.location.reload()}>
            Recharger
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
