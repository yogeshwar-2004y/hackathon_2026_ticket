import React from "react";

export default function PipelineFlow({ activeStep = -1 }) {
  const steps = [
    { id: 0, icon: "📨", label: "Ticket Ingested", sub: "REST API" },
    { id: 1, icon: "🧠", label: "ML Classifier", sub: "DistilBERT" },
    { id: 2, icon: "📊", label: "Urgency Score", sub: "0.0 → 1.0" },
    { id: 3, icon: "🗃️", label: "Priority Queue", sub: "Redis Sorted Set" },
    { id: 4, icon: "🔔", label: "Alert Check", sub: "> 0.8 Threshold" },
    { id: 5, icon: "🔗", label: "Dedup Engine", sub: "Cosine Similarity" },
    { id: 6, icon: "👤", label: "Agent Router", sub: "Skill Matching" },
  ];

  return (
    <div className="pipeline-root">
      {steps.map((s, i) => (
        <div key={s.id} className="pipeline-segment">
          <div
            className={`pipeline-node ${activeStep === s.id ? "active" : activeStep >= s.id ? "done" : ""}`}
          >
            <div className="pipeline-icon">{s.icon}</div>
          </div>
          <div className="pipeline-text">
            <div className="pipeline-label">{s.label}</div>
            <div className="pipeline-sub">{s.sub}</div>
          </div>
          {i < steps.length - 1 && (
            <div className={`pipeline-connector ${activeStep > s.id ? "filled" : ""}`} />
          )}
        </div>
      ))}
    </div>
  );
}

