import { z } from "zod";

export type NewsRoute = { kind: "news" } | { kind: "detail"; id: string } | { kind: "feedback" } | { kind: "invalid" };

export function newsRoute(path: string): NewsRoute {
  if (path === "/") return { kind: "news" };
  if (path === "/feedback") return { kind: "feedback" };
  const match = /^\/news\/([^/]+)$/.exec(path);
  const id = z.uuid().safeParse(match?.[1]);
  return id.success ? { kind: "detail", id: id.data.toLowerCase() } : { kind: "invalid" };
}

export function returnPath(path: string): string {
  const route = newsRoute(path);
  return route.kind === "detail" ? `/news/${route.id}` : route.kind === "feedback" ? "/feedback" : "/";
}
