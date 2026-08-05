import { useState } from "react";
import LogSheetForm from "./components/LogSheetForm";
import { useTheme, ThemeChoice } from "./hooks/useTheme";

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
  const { choice, cycleTheme } = useTheme();

  return (
    <div className="app-shell">
      <header>
        <div className="app-header">
          <h1>POGF Field Ops</h1>
          <button
            type="button"
            className="theme-toggle"
            onClick={cycleTheme}
            aria-label={`${THEME_LABEL[choice]}. Activate to change.`}
            title={THEME_LABEL[choice]}
          >
            <span aria-hidden="true">{THEME_ICON[choice]}</span>
          </button>
        </div>
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
            Offline Queue
          </button>
        </nav>
      </header>

      {view === "logsheet" && <LogSheetForm />}
      {view === "queue" && <QueueView />}
    </div>
  );
}

function QueueView() {
  return (
    <div>
      <h2>Offline Queue</h2>
      <p className="msg msg-info">
        Records saved here while offline will sync automatically when connectivity returns.
      </p>
      {/* TODO: render pending items from useOfflineQueue */}
    </div>
  );
}
