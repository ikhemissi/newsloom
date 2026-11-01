import { PublicClientApplication } from "@azure/msal-browser";
import { authConfiguration } from "../src/auth";
import { runtimeConfig } from "./fixtures";

const config = runtimeConfig;
const authority = `https://login.microsoftonline.com/${config.tenantId}`;
const settings = authConfiguration(config, location.origin);
settings.auth.knownAuthorities = ["login.microsoftonline.com"];
settings.auth.authorityMetadata = JSON.stringify({
  authorization_endpoint: `${authority}/oauth2/v2.0/authorize`,
  token_endpoint: `${authority}/oauth2/v2.0/token`,
  issuer: `${authority}/v2.0`,
  jwks_uri: `${authority}/discovery/v2.0/keys`,
  end_session_endpoint: `${authority}/oauth2/v2.0/logout`,
});
settings.auth.onRedirectNavigate = (url) => {
  const target = new URL(url);
  const result = document.getElementById("result");
  if (result) result.textContent = target.origin === "https://login.microsoftonline.com"
    && target.searchParams.get("redirect_uri") === `${location.origin}/auth/callback`
    && target.searchParams.get("code_challenge_method") === "S256"
    ? "Redirect preflight passed" : "Unexpected authorization contract";
  return false;
};
const instance = new PublicClientApplication(settings);
await instance.initialize();
document.getElementById("login")?.addEventListener("click", () => {
  const result = document.getElementById("result");
  void instance.loginRedirect({
    scopes: [config.agentScope],
  }).catch(() => { if (result) result.textContent = "Redirect preflight failed"; });
});
