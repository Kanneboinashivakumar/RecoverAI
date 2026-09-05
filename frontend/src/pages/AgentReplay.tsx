import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';

interface AuditStep {
  step: number;
  event_id: string;
  event_type: string;
  timestamp: string;
  actor: string;
  input_snapshot: Record<string, any> | null;
  output_snapshot: Record<string, any> | null;
  reason_codes: string[];
  policy_result: string | null;
}

const EVENT_COLORS: Record<string, string> = {
  EVENT_RECEIVED: 'bg-text-secondary',
  RISK_SCORED: 'bg-accent',
  DIAGNOSIS_COMPLETED: 'bg-accent',
  PROBABILITY_PREDICTED: 'bg-accent',
  DECISION_RECOMMENDED: 'bg-accent',
  POLICY_EVALUATED: 'bg-warning',
  ACTION_EXECUTED: 'bg-success',
  OUTCOME_VERIFIED: 'bg-success',
  HUMAN_REVIEW_DECIDED: 'bg-warning',
};

function JsonPanel({ label, data }: { label: string; data: any }) {
  const [open, setOpen] = useState(false);
  if (!data || Object.keys(data).length === 0) return null;
  return (
    <div className="mt-2">
      <button onClick={() => setOpen(!open)} className="text-caption text-accent hover:underline">
        {open ? '▼' : '▶'} {label}
      </button>
      {open && (
        <pre className="mt-1 p-3 bg-background rounded text-caption font-mono overflow-x-auto max-h-48 overflow-y-auto">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}

export default function AgentReplay() {
  const { transactionId } = useParams<{ transactionId: string }>();
  const navigate = useNavigate();
  const [timeline, setTimeline] = useState<AuditStep[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchId, setSearchId] = useState(transactionId || '');

  const load = (txId: string) => {
    if (!txId) return;
    setLoading(true);
    setError(null);
    fetch(`/api/agent-replay/${txId}`)
      .then((r) => { if (!r.ok) throw new Error(`API ${r.status}`); return r.json(); })
      .then(setTimeline)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (transactionId) {
      setSearchId(transactionId);
      load(transactionId);
    } else {
      setLoading(false);
    }
  }, [transactionId]);

  const doSearch = () => {
    if (searchId.trim()) {
      navigate(`/agent-replay/${searchId.trim()}`);
      load(searchId.trim());
    }
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <h2 className="text-xl font-semibold text-text-primary">Agent Replay</h2>
      <p className="text-caption text-text-secondary">Forensic timeline reconstructed from audit_events. Timestamps represent simulated pipeline progression.</p>

      {/* Search */}
      <div className="flex gap-2">
        <input
          value={searchId}
          onChange={(e) => setSearchId(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && doSearch()}
          placeholder="Enter transaction UUID"
          className="flex-1 px-3 py-2 border border-border rounded text-body font-mono focus:outline-none focus:border-accent"
        />
        <button onClick={doSearch} className="px-4 py-2 bg-accent text-white text-body rounded hover:bg-accent/90">
          Load Replay
        </button>
      </div>

      {loading && <p className="text-text-secondary py-8 text-center">Loading timeline…</p>}

      {error && (
        <div className="text-center py-8">
          <p className="text-danger font-medium">Failed to load replay</p>
          <p className="text-caption text-text-secondary">{error}</p>
        </div>
      )}

      {!loading && !error && timeline.length === 0 && transactionId && (
        <p className="text-text-secondary py-8 text-center">No audit events found for this transaction.</p>
      )}

      {!loading && !error && !transactionId && timeline.length === 0 && (
        <p className="text-text-secondary py-8 text-center">Enter a transaction ID above, or click "View Agent Replay" from a transaction detail page.</p>
      )}

      {/* Timeline */}
      {timeline.length > 0 && (
        <div className="relative pl-8">
          {/* Vertical line */}
          <div className="absolute left-3 top-0 bottom-0 w-0.5 bg-border" />

          {timeline.map((step) => {
            const dotColor = EVENT_COLORS[step.event_type] || 'bg-text-secondary';
            return (
              <div key={step.event_id} className="relative mb-6">
                {/* Dot */}
                <div className={`absolute -left-5 top-1 w-3 h-3 rounded-full ${dotColor} border-2 border-white`} />

                {/* Content */}
                <div className="bg-white border border-border rounded-lg p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-body font-medium text-text-primary">
                        Step {step.step}: {step.event_type}
                      </span>
                      {step.policy_result && (
                        <span className={`px-2 py-0.5 rounded text-caption font-medium ${
                          step.policy_result === 'APPROVED' ? 'bg-success/10 text-success' :
                          step.policy_result === 'BLOCKED' ? 'bg-danger/10 text-danger' :
                          step.policy_result === 'ESCALATED' ? 'bg-warning/10 text-warning' :
                          'bg-background text-text-secondary'
                        }`}>
                          {step.policy_result}
                        </span>
                      )}
                    </div>
                    <span className="text-caption text-text-secondary tabular-nums">
                      {new Date(step.timestamp).toLocaleTimeString()}
                    </span>
                  </div>

                  <p className="text-caption text-text-secondary mb-1">Actor: {step.actor}</p>

                  {step.reason_codes.length > 0 && (
                    <div className="flex flex-wrap gap-1 mb-2">
                      {step.reason_codes.map((code, i) => (
                        <span key={i} className="px-1.5 py-0.5 text-caption bg-background rounded font-mono text-text-secondary">{code}</span>
                      ))}
                    </div>
                  )}

                  <JsonPanel label="Input Snapshot" data={step.input_snapshot} />
                  <JsonPanel label="Output Snapshot" data={step.output_snapshot} />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
