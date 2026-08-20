import { useCallback, useEffect, useState } from "react";
import LogSheetForm from "./components/LogSheetForm";
import LoginScreen from "./components/LoginScreen";
import QueueView from "./components/QueueView";
import SheetsView from "./components/SheetsView";
import { useTheme, ThemeChoice } from "./hooks/useTheme";
import { useOfflineQueue, flushQueue } from "./hooks/useOfflineQueue";
import { getToken, clearToken, onAuthCleared } from "./services/api";
import { useOnline } from "./hooks/useOnline";
import { usePath, navigate } from "./utils/router";

type View = "logsheet" | "queue" | "sheets";

// The nav is the source of truth for both directions: which path shows which
// view, and which path a tab navigates to. Keeping them in one place is what
// stops /sheets rendering the form because a string was updated in one of two
// places.
const PATHS: Record<View, string> = {
  logsheet: "/",
  queue: "/queue",
  sheets: "/sheets",
};

function viewForPath(path: string): View {
  const found = (Object.keys(PATHS) as View[]).find((v) => PATHS[v] === path);
  // An unknown path falls back to the form rather than a blank screen. This is
  // a field app opened from a pasted link; a 404 at a monument helps nobody.
  return found ?? "logsheet";
}

const THEME_ICON: Record<ThemeChoice, string> = {
  system: "◐",
  light: "☀",
  dark: "☾",
};

const THEME_LABEL: Record<ThemeChoice, string> = {
  system: "Theme: follow device",
  light: "Theme: light",
  dark: "Theme: dark",
};

export default function App() {
  const path = usePath();
  const view = viewForPath(path);
  const [authed, setAuthed] = useState<boolean>(() => getToken() !== null);
  const { choice, cycleTheme } = useTheme();
  const { pendingCount } = useOfflineQueue();
  const online = useOnline();

  const signOut = useCallback(() => {
    clearToken();
    setAuthed(false);
  }, []);

  // An expired token is cleared deep inside apiFetch. Without this subscription
  // App would never hear about it, leaving the operator on a form whose every
  // submit silently queues and whose queue can never drain.
  useEffect(() => onAuthCleared(() => setAuthed(false)), []);

  const onLoginSuccess = useCallback(() => {
    setAuthed(true);
    // Anything stranded by the expired token can go now. Without this the queue
    // waits for the next online/offline transition, which may not come for
    // hours — and the operator has just proven they have signal.
    void flushQueue();
  }, []);

  const themeButton = (
    <button
      type="button"
      className="theme-toggle"
      onClick={cycleTheme}
      aria-label={`${THEME_LABEL[choice]}. Activate to change.`}
      title={THEME_LABEL[choice]}
    >
      <span aria-hidden="true">{THEME_ICON[choice]}</span>
    </button>
  );

  if (!authed) {
    return (
      <div className="app-shell">
        <div className="app-header">
          <h1>MOVE Faults Field Ops</h1>
          {themeButton}
        </div>
        <LoginScreen onSuccess={onLoginSuccess} />
      </div>
    );
  }

  return (
    <div className="app-shell">
      <header>
        <div className="app-header">
          <h1>MOVE Faults Field Ops</h1>
          {themeButton}
        </div>

        {/* Connectivity is the single most important thing to know in the
            field, so it is stated rather than inferred from a failed submit. */}
        {!online && (
          <p className="msg msg-warn conn-banner">
            Offline — sheets are saved on this device, photo included, and sync
            when you have signal.
          </p>
        )}

        <nav className="view-nav">
          <button
            type="button"
            onClick={() => navigate(PATHS.logsheet)}
            className={view === "logsheet" ? "" : "is-inactive"}
            aria-current={view === "logsheet" ? "page" : undefined}
          >
            New Log Sheet
          </button>
          <button
            type="button"
            onClick={() => navigate(PATHS.queue)}
            className={view === "queue" ? "" : "is-inactive"}
            aria-current={view === "queue" ? "page" : undefined}
          >
            Queue{pendingCount > 0 ? ` (${pendingCount})` : ""}
          </button>
          <button
            type="button"
            onClick={() => navigate(PATHS.sheets)}
            className={view === "sheets" ? "" : "is-inactive"}
            aria-current={view === "sheets" ? "page" : undefined}
          >
            Sheets
          </button>
        </nav>
      </header>

      {/* Both stay mounted; only visibility changes.

          Unmounting the form threw away everything typed into it. An operator
          who tapped Queue mid-sheet — to check whether an earlier one had
          synced, which is a reasonable thing to do — came back to an empty
          form and had to start the station visit again from memory. On a
          phone, at a monument, that is the kind of loss that ends with the
          sheet not being filed at all.

          `hidden` rather than conditional rendering keeps react-hook-form's
          state, the selected photos, and any in-flight submit alive across the
          switch. Two small views make this cheap; if a third arrives that is
          expensive to keep mounted, revisit it then. */}
      <div hidden={view !== "logsheet"}>
        <LogSheetForm />
      </div>
      <div hidden={view !== "queue"}>
        <QueueView />
      </div>

      {/* Mounted only while shown, unlike the other two. Those hold typed input
          and queue state that must survive a tab switch; this one holds a
          fetched list, and keeping it mounted would mean a stale table sitting
          behind the form until something re-rendered it. Mounting on entry is
          also what makes it refetch when someone comes back to check. */}
      {view === "sheets" && <SheetsView />}

      <footer className="app-footer">
        <button type="button" className="link-btn" onClick={signOut}>
          Sign out
        </button>
      </footer>
    </div>
  );
}

