import { useCallback, useEffect, useState } from "react";
import LogSheetForm from "./components/LogSheetForm";
import TodayView from "./components/TodayView";
import ReviewSitesView from "./components/ReviewSitesView";
import LoginScreen from "./components/LoginScreen";
import QueueView from "./components/QueueView";
import SheetsView from "./components/SheetsView";
import { useTheme, ThemeChoice } from "./hooks/useTheme";
import { useOfflineQueue, flushQueue } from "./hooks/useOfflineQueue";
import { getToken, clearToken, onAuthCleared } from "./services/api";
import { useOnline } from "./hooks/useOnline";
import { usePath, navigate } from "./utils/router";
import { useCurrentUser } from "./hooks/useCurrentUser";

type View = "today" | "logsheet" | "queue" | "sheets" | "reviewSites";

// The nav is the source of truth for both directions: which path shows which
// view, and which path a tab navigates to. Keeping them in one place is what
// stops /sheets rendering the form because a string was updated in one of two
// places.
const PATHS: Record<View, string> = {
  today: "/",
  // Moved off "/" when Today took the landing slot. Nothing external links
  // here — the only references were the nav buttons below — and vercel.json
  // rewrites every non-/api path to index.html, so the new path needs no
  // hosting change. An old bookmark of "/" now lands on Today, which is the
  // intended behaviour rather than a regression.
  logsheet: "/new",
  queue: "/queue",
  sheets: "/sheets",
  reviewSites: "/review-sites",
};

function viewForPath(path: string): View {
  const found = (Object.keys(PATHS) as View[]).find((v) => PATHS[v] === path);
  // An unknown path falls back to Today rather than a blank screen. This is a
  // field app opened from a pasted link; a 404 at a monument helps nobody.
  // Today is the better landing than the form: it answers "where am I" without
  // requiring anything to be typed first.
  return found ?? "today";
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
  const { role } = useCurrentUser();

  /**
   * Whether to OFFER the review tab. Not whether the person may use it.
   *
   * The endpoints enforce admin and data_processor themselves, and nothing
   * here re-implements that — a check in the browser is a courtesy, never a
   * gate.
   *
   * A null role means /me has not answered, which offline is the normal case.
   * Offered anyway, following the rule useCurrentUser states: the role decides
   * a default view, never access. Hiding the tab on an unanswered /me would
   * hide it from the reviewer with the worst connection, and the screen
   * explains a 403 plainly if the guess was wrong.
   */
  const mayReview = role === null || role === "admin" || role === "data_processor";

  /**
   * The station Today asked the form to start a sheet for.
   *
   * A bare string is not enough. The form stays mounted across tab switches
   * (see below), so the only way it can learn about a later choice is a prop
   * change — and choosing the same station twice would not change a string.
   * The counter makes every tap distinct, so "start a sheet for PHIV" after
   * wandering back to Today still arrives.
   *
   * It sets the station and nothing else. Anything already typed survives,
   * because an operator who taps a station after half-filling a sheet has
   * corrected the station, not asked to start over.
   */
  const [stationRequest, setStationRequest] = useState<{
    code: string;
    nonce: number;
  } | null>(null);

  const startSheetFor = useCallback((stationCode: string) => {
    setStationRequest((prev) => ({ code: stationCode, nonce: (prev?.nonce ?? 0) + 1 }));
    navigate(PATHS.logsheet);
  }, []);

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
            onClick={() => navigate(PATHS.today)}
            className={view === "today" ? "" : "is-inactive"}
            aria-current={view === "today" ? "page" : undefined}
          >
            Today
          </button>
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
          {mayReview && (
            <button
              type="button"
              onClick={() => navigate(PATHS.reviewSites)}
              className={view === "reviewSites" ? "" : "is-inactive"}
              aria-current={view === "reviewSites" ? "page" : undefined}
            >
              Review sites
            </button>
          )}
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
      {/* Mounted only while shown, like Sheets below and for the same reason:
          it holds fetched lists and a search box, not typed sheet data. Its
          own state -- the search query, the show-all toggle -- is cheap to
          lose and stale to keep. */}
      {view === "today" && <TodayView onStartSheet={startSheetFor} />}

      <div hidden={view !== "logsheet"}>
        <LogSheetForm stationRequest={stationRequest} />
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

      {/* Mounted only while shown, like Sheets: a fetched list whose whole
          value is being current. Rendered on the route regardless of
          `mayReview` — that flag decides whether the tab is offered, and a
          pasted link from a colleague must still reach the screen, which
          explains a 403 better than a blank page does. */}
      {view === "reviewSites" && <ReviewSitesView />}

      <footer className="app-footer">
        <button type="button" className="link-btn" onClick={signOut}>
          Sign out
        </button>
      </footer>
    </div>
  );
}

