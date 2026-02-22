import React, { useState, useEffect } from "react";

export default function SlackPage({ alerts = [] }) {
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");

  useEffect(() => {
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
    <div className="slack-page">
      <div className="slack-panel" style={{ width: "100%", height: "100vh", borderRadius: 0 }}>
        <div className="slack-left">
          <div className="slack-left-header">Channels</div>
          <div className="slack-channels">
            <div className="slack-channel active">#it-admin</div>
            <div className="slack-channel">#operations</div>
            <div className="slack-channel">#alerts</div>
          </div>
          <div className="slack-users-header">Users</div>
          <div className="slack-users">
            {users.map(u => <div key={u.id} className="slack-user">{u.name}</div>)}
          </div>
        </div>

        <div className="slack-center">
          <div className="slack-center-header">
            <div>#it-admin</div>
            <div style={{ marginLeft: "auto" }}>
              <a href="#" onClick={(e) => { e.preventDefault(); window.location.hash = ""; }} className="btn">Back</a>
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
            <input value={text} onChange={e => setText(e.target.value)} placeholder="Message #it-admin..." />
            <button className="btn" onClick={sendMessage}>Send</button>
          </div>
        </div>

        <div className="slack-right">
          <div className="slack-right-header">Details</div>
          <div style={{ padding: 12, color: "#9aa7ad", fontSize: 13 }}>
            Simulated Slack-like workspace for IT Admins and employees.
          </div>
        </div>
      </div>
    </div>
  );
}

