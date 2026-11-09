import { z } from "zod";

export type NewsRoute = { kind: "news" } | { kind: "detail"; id: string } | { kind: "feedback" } | { kind: "invalid" }
  | { kind: "radar" } | { kind: "product"; id: string } | { kind: "stack" };

/** With the radar enabled, "/" is the radar and the list moves to "/news". */
export function newsRoute(path: string, radar = false): NewsRoute {
  if (path === "/") return { kind: radar ? "radar" : "news" };
  if (path === "/news" && radar) return { kind: "news" };
  if (path === "/stack" && radar) return { kind: "stack" };
  if (path === "/feedback") return { kind: "feedback" };
  const product = /^\/products\/([^/]+)$/.exec(path);
  if (product && radar) {
    const id = z.uuid().safeParse(product[1]);
    return id.success ? { kind: "product", id: id.data.toLowerCase() } : { kind: "invalid" };
  }
  const match = /^\/news\/([^/]+)$/.exec(path);
  const id = z.uuid().safeParse(match?.[1]);
  return id.success ? { kind: "detail", id: id.data.toLowerCase() } : { kind: "invalid" };
}

export function returnPath(path: string, radar = false): string {
  const route = newsRoute(path, radar);
  return route.kind === "detail" ? `/news/${route.id}` : route.kind === "feedback" ? "/feedback"
    : route.kind === "product" ? `/products/${route.id}` : route.kind === "stack" ? "/stack"
      : route.kind === "news" && radar ? "/news" : "/";
}
