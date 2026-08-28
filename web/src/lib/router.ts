import { useEffect, useState } from "react";

/**
 * Three surfaces, one bundle.
 *
 * `/`            the public site
 * `/apply/{slug}` an opening — shared on LinkedIn, so it stays clean and readable
 * `/{panel}`      sign-in and the review panel
 *
 * The panel's segment comes from the build, so a deployment can choose its own
 * and never link to it. That keeps the admin surface out of sight and out of
 * search results; it is **not** a security control, and nothing here depends on
 * the path being secret. The sign-in is what protects the panel.
 */
export const PANEL_PATH = (import.meta.env.VITE_PANEL_PATH as string | undefined) ?? "panel";

export type Route =
  | { name: "home" }
  | { name: "panel" }
  | { name: "apply"; slug: string }
  | { name: "applied"; slug: string; reference: string }
  | { name: "missing" };

export function parse(pathname: string): Route {
  const path = pathname.replace(/\/+$/, "") || "/";

  if (path === "/") return { name: "home" };
  if (path === `/${PANEL_PATH}`) return { name: "panel" };

  const applied = path.match(/^\/apply\/([^/]+)\/received\/([^/]+)$/);
  if (applied?.[1] && applied[2]) {
    return { name: "applied", slug: applied[1], reference: applied[2] };
  }
  const apply = path.match(/^\/apply\/([^/]+)$/);
  if (apply?.[1]) return { name: "apply", slug: apply[1] };

  return { name: "missing" };
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
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [route.name]);
  return route;
}
