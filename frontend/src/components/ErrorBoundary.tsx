import { Component, type ErrorInfo, type ReactNode } from 'react';

/**
 * The last thing between a render-time throw and a blank white page.
 *
 * The app had no boundary at all, which made every other defect worse than
 * itself: React unmounts the whole tree on an uncaught render error, so a
 * single bad field turned the product into a white rectangle with no way
 * back but a manual reload. There is a live path to exactly that — a FastAPI
 * 422 returns `detail` as an *array*, and a page that renders it directly
 * throws "Objects are not valid as a React child" on the login screen, where
 * a founder has no navigation to escape with.
 *
 * This is deliberately a class component: `componentDidCatch` has no hook
 * equivalent, and `<BrowserRouter>` is the declarative router, so there is no
 * `errorElement` to hang this on.
 *
 * What it must never do is claim to know what went wrong. It says the screen
 * failed, offers the two things that actually recover (try again, go home),
 * and shows the technical text only behind a disclosure — a founder should
 * not have to read a stack trace, but the one forwarding a bug report needs
 * it to be copyable.
 */

interface Props {
  children: ReactNode;
  /** Where "go back" should lead. The app shell overrides this per area. */
  homeHref?: string;
}

interface State {
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // No logging service is wired yet; the console is what a founder can be
    // asked to screenshot, and swallowing this entirely is how a defect
    // becomes unreportable.
    console.error('[Saibyl] a screen failed to render', error, info.componentStack);
  }

  private reset = () => this.setState({ error: null });

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    const home = this.props.homeHref ?? '/app/home';

    return (
      <div className="min-h-screen bg-saibyl-paper flex items-center justify-center p-6">
        <div className="glass rounded-2xl max-w-lg w-full p-8 text-center">
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-saibyl-muted">
            This screen
          </p>
          <h1 className="text-h2 text-saibyl-ink mt-2">This screen did not load</h1>
          <p className="text-[13.5px] text-saibyl-silver mt-2.5 leading-relaxed">
            Something on this page failed while it was being drawn. Nothing you
            were doing was lost, and no credits were spent on this. Try it
            again — if it keeps happening, the details below are what to send
            us.
          </p>

          <div className="flex items-center justify-center gap-3 mt-6">
            <button
              type="button"
              onClick={this.reset}
              className="inline-flex items-center gap-1.5 px-5 py-2 rounded-xl bg-saibyl-blue text-white font-semibold text-[13px] hover:bg-saibyl-gold-hover transition-colors"
            >
              Try this screen again
            </button>
            <a
              href={home}
              className="text-[13px] text-saibyl-muted hover:text-saibyl-ink transition-colors"
            >
              Go to your products
            </a>
          </div>

          <details className="mt-6 text-left">
            <summary className="cursor-pointer text-[12px] text-saibyl-muted hover:text-saibyl-blue transition-colors">
              What went wrong, in technical terms
            </summary>
            <pre className="mt-2 p-3 rounded-xl border border-saibyl-border-light bg-white text-[11px] text-saibyl-silver whitespace-pre-wrap break-words">
              {error.message || String(error)}
            </pre>
          </details>
        </div>
      </div>
    );
  }
}
