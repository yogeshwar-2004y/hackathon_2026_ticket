import React, { useState } from "react";

export default function App() {
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [customer, setCustomer] = useState("");
  const [resp, setResp] = useState(null);
  const [loading, setLoading] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setLoading(true);
    setResp(null);
    try {
      const res = await fetch("http://127.0.0.1:5000/tickets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subject, body, customer }),
      });
      const data = await res.json();
      setResp({ status: res.status, data });
    } catch (err) {
      setResp({ status: "error", error: String(err) });
    } finally {
      setLoading(false);
    }
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
        </div>
      </form>

      <div className="card">
        <h3>Response</h3>
        <pre>{resp ? JSON.stringify(resp, null, 2) : "No response yet"}</pre>
      </div>

      <footer className="card small">
        <p>
          Frontend (Vite + React). Submit tickets to the Flask backend at <code>http://127.0.0.1:5000/tickets</code>.
        </p>
      </footer>
    </div>
  );
}

