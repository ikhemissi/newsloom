import { expect, test, vi } from "vitest";
import { runtimeConfig } from "./fixtures";

const mock = vi.hoisted(() => ({
  construct: vi.fn(), initialize: vi.fn(async () => undefined),
  handleRedirectPromise: vi.fn(async () => null),
  getActiveAccount: vi.fn(() => ({ homeAccountId: "fixture" })),
  getAllAccounts: vi.fn(() => []), setActiveAccount: vi.fn(),
  loginRedirect: vi.fn(async () => undefined), logoutRedirect: vi.fn(async () => undefined),
  acquireTokenSilent: vi.fn(async () => ({ accessToken: "authored-fixture-token" })),
}));
vi.mock("@azure/msal-browser", () => ({
  PublicClientApplication: class {
    constructor(config: unknown) { mock.construct(config); }
    initialize = mock.initialize; handleRedirectPromise = mock.handleRedirectPromise;
    getActiveAccount = mock.getActiveAccount; getAllAccounts = mock.getAllAccounts;
    setActiveAccount = mock.setActiveAccount; loginRedirect = mock.loginRedirect;
    logoutRedirect = mock.logoutRedirect; acquireTokenSilent = mock.acquireTokenSilent;
  },
  InteractionRequiredAuthError: class extends Error {},
  LogLevel: { Error: 0 },
}));
import { createAuth } from "../src/auth";

test("MSAL uses trusted authority, tab session cache, stable bridge and one audience", async () => {
  const config = runtimeConfig;
  const { session } = await createAuth(config, "https://ui.test");
  expect(mock.construct).toHaveBeenCalledWith(expect.objectContaining({
    cache: { cacheLocation: "sessionStorage" },
    auth: expect.objectContaining({
      clientId: config.clientId, authority: `https://login.microsoftonline.com/${config.tenantId}`,
      redirectUri: "https://ui.test/auth/callback",
    }),
  }));
  expect(mock.initialize).toHaveBeenCalledOnce();
  expect(mock.handleRedirectPromise).toHaveBeenCalledOnce();
  await session.token();
  expect(mock.acquireTokenSilent).toHaveBeenCalledWith({
    account: { homeAccountId: "fixture" }, scopes: [config.agentScope],
  });

  await session.signIn();
  expect(mock.loginRedirect).toHaveBeenCalledWith({
    scopes: [config.newsScope], redirectStartPage: "https://ui.test/",
  });
  await session.token("news");
  expect(mock.acquireTokenSilent).toHaveBeenLastCalledWith({
    account: { homeAccountId: "fixture" }, scopes: [config.newsScope],
  });
});

test("redirect restoration accepts only a same-origin validated item path", async () => {
  const id = crypto.randomUUID();
  window.history.replaceState(null, "", `/news/${id}?question=private#untrusted`);
  const { session } = await createAuth(runtimeConfig, "https://ui.test");
  await session.signIn("news");
  expect(mock.loginRedirect).toHaveBeenLastCalledWith({
    scopes: [runtimeConfig.newsScope], redirectStartPage: `https://ui.test/news/${id}`,
  });
  window.history.replaceState(null, "", "/news/not-a-uuid");
  await session.signIn("news");
  expect(mock.loginRedirect).toHaveBeenLastCalledWith({
    scopes: [runtimeConfig.newsScope], redirectStartPage: "https://ui.test/",
  });
});
