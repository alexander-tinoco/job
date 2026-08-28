import { useEffect, useState } from "react";

/**
 * Two surfaces, one bundle. A router dependency would be four times the code of
 * the thing it routes.
 */
export type Route =
  | { name: "panel" }
  | { name: "apply"; slug: string }
  | { name: "applied"; slug: string; reference: string };

export function parse(pathname: string): Route {
  const applied = pathname.match(/^\/apply\/([^/]+)\/received\/([^/]+)\/?$/);
  if (applied?.[1] && applied[2]) {
    return { name: "applied", slug: applied[1], reference: applied[2] };
  }
  const apply = pathname.match(/^\/apply\/([^/]+)\/?$/);
  if (apply?.[1]) return { name: "apply", slug: apply[1] };
  return { name: "panel" };
}

export function navigate(to: string): void {
  window.history.pushState({}, "", to);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parse(window.location.pathname));
  useEffect(() => {
    const update = () => setRoute(parse(window.location.pathname));
    window.addEventListener("popstate", update);
    return () => window.removeEventListener("popstate", update);
  }, []);
  return route;
}
