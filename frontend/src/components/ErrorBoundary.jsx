import { Component } from "react";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("Unhandled UI error", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="error-boundary" role="alert">
          <h2>Something went wrong</h2>
          <p>{this.state.error.message}</p>
          <button onClick={() => window.location.reload()}>Reload DevFlow</button>
        </div>
      );
    }
    return this.props.children;
  }
}
