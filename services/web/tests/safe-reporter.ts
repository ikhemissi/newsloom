import type { FullResult, Reporter, TestCase, TestResult } from "@playwright/test/reporter";

export default class SafeReporter implements Reporter {
  private completed = 0;
  onTestEnd(_test: TestCase, result: TestResult) {
    const errors = result.errors.map((error) => {
      if (error.message?.includes("Executable doesn't exist")) return "browser_not_installed";
      if (error.message?.includes("Host system is missing dependencies")) return "browser_dependencies_missing";
      const library = /error while loading shared libraries: ([a-zA-Z0-9_.-]+):/.exec(error.message ?? "");
      if (library) return `browser_dependencies_missing:${library[1]}`;
      if (error.message?.includes("browserType.launch")) return "browser_launch_failed";
      const accessibility = /ui_accessibility:([a-z0-9,_-]+)/.exec(error.message ?? "");
      if (accessibility) return accessibility[0];
      const location = /(?:local|azure)\.spec\.ts:(\d+):\d+/.exec(error.stack ?? "");
      return (result.status === "timedOut" ? "browser_timeout" : "browser_check_failed")
        + (location ? `:line_${location[1]}` : "");
    });
    process.stdout.write(JSON.stringify({ case: ++this.completed, status: result.status, errors }) + "\n");
  }
  onEnd(result: FullResult) {
    process.stdout.write(JSON.stringify({ cases: this.completed, status: result.status }) + "\n");
  }
  onError() { process.stdout.write('{"status":"runner_error"}\n'); }
  onStdOut() {}
  onStdErr() {}
}
