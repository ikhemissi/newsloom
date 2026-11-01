import {
  PublicClientApplication, InteractionRequiredAuthError, LogLevel,
} from "@azure/msal-browser";
import type { Configuration } from "@azure/msal-browser";
import type { AuthSession } from "./domain";
import { UiFailure } from "./domain";
import type { RuntimeConfig } from "./config";

export function authConfiguration(config: RuntimeConfig, origin: string): Configuration {
  return {
    auth: {
      clientId: config.clientId,
      authority: `https://login.microsoftonline.com/${config.tenantId}`,
      redirectUri: `${origin}/auth/callback`,
      postLogoutRedirectUri: `${origin}/`,
    },
    cache: { cacheLocation: "sessionStorage" },
    system: { loggerOptions: {
      logLevel: LogLevel.Error, piiLoggingEnabled: false, loggerCallback: () => undefined,
    } },
  };
}

export async function createAuth(config: RuntimeConfig, origin: string): Promise<{
  instance: PublicClientApplication; session: AuthSession;
}> {
  const instance = new PublicClientApplication(authConfiguration(config, origin));
  try {
    await instance.initialize();
    const result = await instance.handleRedirectPromise();
    if (result?.account) instance.setActiveAccount(result.account);
  } catch { throw new UiFailure("authorization"); }
  const account = () => instance.getActiveAccount()
    ?? (instance.getAllAccounts().length === 1 ? instance.getAllAccounts()[0] : null);
  return {
    instance,
    session: {
      signedIn: () => !!account(),
      signIn: async (resource = "news") => {
        try {
          await instance.loginRedirect({
            scopes: [resource === "news" ? config.mcpScope : config.agentScope],
            redirectStartPage: `${origin}/`,
          });
        } catch { throw new UiFailure("authorization"); }
      },
      signOut: async () => {
        try { await instance.logoutRedirect({ account: account() ?? null }); }
        catch { throw new UiFailure("authorization"); }
      },
      token: async (resource = "agent") => {
        const selected = account();
        if (!selected) throw new UiFailure("authorization");
        try {
          const result = await instance.acquireTokenSilent({
            account: selected, scopes: [resource === "news" ? config.mcpScope : config.agentScope],
          });
          if (!result.accessToken) throw new UiFailure("authorization");
          return result.accessToken;
        } catch (error) {
          throw new UiFailure(error instanceof InteractionRequiredAuthError ? "interaction" : "authorization");
        }
      },
    },
  };
}
