import { Link } from "react-router-dom";

export function NotFoundPage(): JSX.Element {
  return (
    <section className="panel">
      <h1>Page not found</h1>
      <Link className="text-link" to="/">
        Return to dashboard
      </Link>
    </section>
  );
}

