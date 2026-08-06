import { useCallback, useEffect, useState } from "react";
import LogSheetForm from "./components/LogSheetForm";
import LoginScreen from "./components/LoginScreen";
import QueueView from "./components/QueueView";
import { useTheme, ThemeChoice } from "./hooks/useTheme";
import { useOfflineQueue } from "./hooks/useOfflineQueue";
import { getToken, clearToken } from "./services/api";

type View = "logsheet" | "queue";

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
  const [view, setView] = useState<View>("logsheet");
  const [authed, setAuthed] = useState<boolean>(() => getToken() !== null);
  const { choice, cycleTheme } = useTheme();
  const { pendingCount } = useOfflineQueue();
  const online = useOnline();

  const signOut = useCallback(() => {
    clearToken();
    setAuthed(false);
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
          <h1>POGF Field Ops</h1>
          {themeButton}
        </div>
        <LoginScreen onSuccess={() => setAuthed(true)} />
      </div>
    );
  }

  return (
    <div className="app-shell">
      <header>
        <div className="app-header">
          <h1>POGF Field Ops</h1>
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
            onClick={() => setView("logsheet")}
            className={view === "logsheet" ? "" : "is-inactive"}
            aria-current={view === "logsheet" ? "page" : undefined}
          >
            New Log Sheet
          </button>
          <button
            type="button"
            onClick={() => setView("queue")}
            className={view === "queue" ? "" : "is-inactive"}
            aria-current={view === "queue" ? "page" : undefined}
          >
            Queue{pendingCount > 0 ? ` (${pendingCount})` : ""}
          </button>
        </nav>
      </header>

      {view === "logsheet" && <LogSheetForm />}
      {view === "queue" && <QueueView />}

      <footer className="app-footer">
        <button type="button" className="link-btn" onClick={signOut}>
          Sign out
        </button>
      </footer>
    </div>
  );
}

/** Live online/offline state — `navigator.onLine` alone does not re-render. */
function useOnline(): boolean {
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    const up = () => setOnline(true);
    const down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    return () => {
      window.removeEventListener("online", up);
      window.removeEventListener("offline", down);
    };
  }, []);
  return online;
}
