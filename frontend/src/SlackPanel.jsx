import React, { useState, useEffect } from "react";

export default function SlackPanel({ visible, onClose, alerts = [] }) {
  const [channel, setChannel] = useState("it-admin");
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");

  useEffect(() => {
    // when alerts prop updates, push high-priority alerts into IT admin channel
    if (alerts && alerts.length > 0) {
      const newMsgs = alerts.map(a => ({
        id: Date.now() + Math.random(),
        from: "system",
        text: a.message,
        time: new Date().toLocaleTimeString(),
        priority: "high",
      }));
      setMessages(prev => [...prev, ...newMsgs]);
    }
  }, [alerts]);

  if (!visible) return null;

  const users = [
    { id: "it-admin", name: "IT Admin", role: "admin" },
    { id: "emp-1", name: "Alice W.", role: "employee" },
    { id: "emp-2", name: "Marcus T.", role: "employee" },
  ];

  function sendMessage() {
    if (!text.trim()) return;
    setMessages(prev => [
      ...prev,
      { id: Date.now(), from: "you", text: text.trim(), time: new Date().toLocaleTimeString(), priority: "normal" },
    ]);
    setText("");
  }

  return (
    <div className="slack-overlay">
      <div className="slack-panel">
        <div className="slack-left">
          <div className="slack-left-header">Channels</div>
          <div className="slack-channels">
            <div className={`slack-channel ${channel === "it-admin" ? "active" : ""}`} onClick={() => setChannel("it-admin")}>#it-admin</div>
            <div className={`slack-channel ${channel === "operations" ? "active" : ""}`} onClick={() => setChannel("operations")}>#operations</div>
            <div className={`slack-channel ${channel === "alerts" ? "active" : ""}`} onClick={() => setChannel("alerts")}>#alerts</div>
          </div>
          <div className="slack-users-header">Users</div>
          <div className="slack-users">
            {users.map(u => <div key={u.id} className="slack-user">{u.name}</div>)}
          </div>
        </div>
        <div className="slack-center">
          <div className="slack-center-header">
            <div>#{channel}</div>
            <div style={{ marginLeft: "auto" }}>
              <button className="btn" onClick={onClose} style={{ padding: "6px 10px" }}>Close</button>
            </div>
          </div>
          <div className="slack-messages">
            {messages.length === 0 && <div className="slack-empty">No messages yet</div>}
            {messages.map(m => (
              <div key={m.id} className={`slack-msg ${m.priority === "high" ? "high" : ""}`}>
                <div className="slack-msg-meta"><strong>{m.from}</strong> <span>{m.time}</span></div>
                <div className="slack-msg-text">{m.text}</div>
              </div>
            ))}
          </div>
          <div className="slack-compose">
            <input value={text} onChange={e => setText(e.target.value)} placeholder="Message #channel..." />
            <button className="btn" onClick={sendMessage}>Send</button>
          </div>
        </div>
        <div className="slack-right">
          <div className="slack-right-header">Details</div>
          <div style={{ padding: 12, color: "#9aa7ad", fontSize: 13 }}>
            Click a high-priority alert to view details. This panel simulates a Slack-like workspace for IT Admins and employees.
          </div>
        </div>
      </div>
    </div>
  );
}

