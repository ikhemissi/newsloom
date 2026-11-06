import { createRoot } from "react-dom/client";
import { MsalProvider } from "@azure/msal-react";
import { App } from "./App";
import { loadConfig } from "./config";
import { createAuth } from "./auth";
import { A2aResearch } from "./research";
import { HttpCatalog } from "./catalog";
import { HttpFeedback } from "./feedback";
import { failureMessage } from "./domain";
import "./style.css";

const container = document.getElementById("root");
if (!container) throw new Error("Missing application root");
const root = createRoot(container);

async function start() {
  try {
    if (window.location.pathname === "/auth/callback") {
      root.render(<main className="startup"><h1>Newsloom</h1><p role="status">Completing sign-in...</p></main>);
      const { broadcastResponseToMainFrame } = await import("@azure/msal-browser/redirect-bridge");
      await broadcastResponseToMainFrame();
      return;
    }
    root.render(<main className="startup"><h1>Newsloom</h1><p role="status">Preparing your browser session...</p></main>);
    const config = await loadConfig();
    const { instance, session } = await createAuth(config, window.location.origin);
    root.render(<MsalProvider instance={instance}>
      <App auth={session} research={new A2aResearch(config, session)} catalog={new HttpCatalog(config, session)}
        feedback={new HttpFeedback(config, session)} />
    </MsalProvider>);
  } catch (error) {
    root.render(<main className="startup"><h1>Newsloom</h1><p role="alert">{failureMessage(error)}</p><a href="/">Return to Newsloom</a></main>);
  }
}
void start();
