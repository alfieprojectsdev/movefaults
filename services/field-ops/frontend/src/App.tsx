import { useState } from "react";
import LogSheetForm from "./components/LogSheetForm";

type View = "logsheet" | "queue";

export default function App() {
  const [view, setView] = useState<View>("logsheet");

  return (
    <div style={{ maxWidth: 600, margin: "0 auto", padding: "1rem", fontFamily: "sans-serif" }}>
      <header style={{ marginBottom: "1.5rem" }}>
        <h1 style={{ fontSize: "1.25rem", fontWeight: "bold", color: "#1a56a4" }}>
          POGF Field Ops
        </h1>
        <nav style={{ display: "flex", gap: "1rem", marginTop: "0.5rem" }}>
          <button onClick={() => setView("logsheet")}
            style={{ fontWeight: view === "logsheet" ? "bold" : "normal" }}>
            New Log Sheet
          </button>
          <button onClick={() => setView("queue")}
            style={{ fontWeight: view === "queue" ? "bold" : "normal" }}>
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
      <p style={{ color: "#666" }}>
        Records saved here while offline will sync automatically when connectivity returns.
      </p>
      {/* TODO: render pending items from useOfflineQueue */}
    </div>
  );
}
