import React, { useEffect, useState } from "react";
import PipelineFlow from "./PipelineFlow";
import SlackPanel from "./SlackPanel";
import SlackPage from "./SlackPage";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:5100";
const WS_BASE = API_BASE.replace(/^http/, "ws");

export default function App() {
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [customer, setCustomer] = useState("");
  const [resp, setResp] = useState(null);
  const [loading, setLoading] = useState(false);
  const [ticketId, setTicketId] = useState(null);
  const [logs, setLogs] = useState([]);
  const [activeStep, setActiveStep] = useState(-1);
  const [showSlack, setShowSlack] = useState(false);
  const [alerts, setAlerts] = useState([]);
  const [statusEvents, setStatusEvents] = useState([]);

  useEffect(() => {
    const ws = new WebSocket(`${WS_BASE}/ws/status`);
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setStatusEvents((prev) => [data, ...prev].slice(0, 100));

        // Trigger alerts for Flash Floods
        if (data.status === "master_incident") {
          setAlerts((prev) => [
            ...prev,
            { message: `[HIGH URGENCY] Flash-flood detected! ${data.similar_count} tickets suppressed into Master Incident.`, timestamp: data.timestamp }
          ]);
        }
      } catch {
        // ignore malformed events
      }
    };
    return () => ws.close();
  }, []);

  async function submit(e) {
    e.preventDefault();
    setLoading(true);
    setResp(null);
    try {
      const res = await fetch(`${API_BASE}/tickets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subject, body, customer }),
      });
      const data = await res.json();
      setResp({ status: res.status, data });
      setTicketId(data.ticket_id || null);
      // animate pipeline
      setActiveStep(0);
      const steps = [1, 2, 3, 4, 5, 6];
      steps.forEach((s, idx) => {
        setTimeout(() => setActiveStep(s), 600 * (idx + 1));
      });
      setTimeout(() => setActiveStep(-1), 600 * (steps.length + 2));
    } catch (err) {
      setResp({ status: "error", error: String(err) });
    } finally {
      setLoading(false);
    }
  }

  // Routing via hash: if #/slack show SlackPage
  const [route, setRoute] = useState(window.location.hash || "");
  React.useEffect(() => {
    const onHash = () => setRoute(window.location.hash || "");
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  // Auto-open Slack page when a high-priority alert arrives
  React.useEffect(() => {
    if (alerts && alerts.length > 0) {
      const last = alerts[alerts.length - 1];
      if (last && typeof last.message === "string" && last.message.toLowerCase().includes("high urgency")) {
        window.location.hash = "#/slack";
      }
    }
  }, [alerts]);

  if (route === "#/slack") {
    return <SlackPage alerts={alerts} />;
  }

  return (
    <div className="container">
      <h1>Ticket Router — UI</h1>
      <form onSubmit={submit} className="card">
        <label>
          Subject
          <input value={subject} onChange={(e) => setSubject(e.target.value)} required />
        </label>
        <label>
          Body
          <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={6} required />
        </label>
        <label>
          Customer
          <input value={customer} onChange={(e) => setCustomer(e.target.value)} placeholder="alice@example.com" />
        </label>
        <div className="actions">
          <button type="submit" disabled={loading}>
            {loading ? "Submitting..." : "Submit Ticket"}
          </button>
          <button type="button" className="btn" style={{ marginLeft: 8 }} onClick={() => { window.location.hash = "#/slack"; setShowSlack(true); }}>
            Open IT Panel
          </button>
        </div>
      </form>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }} className="card">
        <h2 style={{ marginTop: 0 }}>Live Pipeline</h2>
        <PipelineFlow activeStep={activeStep} />
      </div>
      {showSlack && <React.Suspense fallback={null}><SlackPanel visible={showSlack} onClose={() => { setShowSlack(false); window.location.hash = ""; }} alerts={alerts} /></React.Suspense>}

      <div className="card">
        <h3>Response</h3>
        <pre>{resp ? JSON.stringify(resp, null, 2) : "No response yet"}</pre>
        {ticketId && (
          <div style={{ marginTop: 12 }}>
            <h4>Live Status</h4>
            <div style={{ fontFamily: "monospace", fontSize: 13 }}>
              {(statusEvents.filter((e) => e.ticket_id === ticketId).slice(0, 8)).map((e, idx) => (
                <div key={`${e.timestamp || "ts"}-${idx}`}>
                  {new Date((e.timestamp || 0) * 1000).toLocaleTimeString()} - {e.status}
                </div>
              ))}
            </div>
          </div>
        )}
        {ticketId && (
          <div style={{ marginTop: 8 }}>
            <button onClick={async () => {
              const r = await fetch(`${API_BASE}/ticket_logs/${ticketId}`);
              const j = await r.json();
              setLogs(j.logs || []);
            }}>View Simulation</button>
          </div>
        )}
        {logs && logs.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <h4>Simulation Log</h4>
            <div style={{ maxHeight: 300, overflow: "auto", background: "rgba(0,0,0,0.6)", padding: 8, borderRadius: 6 }}>
              {logs.map((line, idx) => {
                const isSlow = line.toLowerCase().includes("m2 slow");
                const isM1 = line.startsWith("[M1]");
                const isM2 = line.startsWith("[M2]");
                const color = isSlow ? "#ef4444" : isM2 ? "#3b82f6" : isM1 ? "#10b981" : "#94a3b8";
                return <div key={idx} style={{ color, fontFamily: "monospace", padding: "4px 0" }}>{line}</div>;
              })}
            </div>
          </div>
        )}
      </div>

      <footer className="card small">
        <p>
          Frontend (Vite + React). Submit tickets to the Flask backend at <code>{API_BASE}/tickets</code>.
        </p>
      </footer>
    </div>
  );
}

