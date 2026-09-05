import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import StatusBadge from '../components/StatusBadge';

interface QueueItem {
  transaction_id: string;
  amount: number;
  payment_method: string;
  failure_code: string;
  action_type: string;
  original_verdict: string;
  is_override: boolean;
  reason_codes: string[];
  review_status: string;
  confidence: number | null;
  expected_value: number | null;
  evaluated_at: string;
  reviewed_at: string | null;
  reviewer: string | null;
  reviewer_notes: string | null;
}

interface QueueResponse {
  total_count: number;
  pending_count: number;
  approved_count: number;
  rejected_count: number;
  items: QueueItem[];
}

function ResolveModal({ item, onClose, onResolved }: { item: QueueItem; onClose: () => void; onResolved: () => void }) {
  const [verdict, setVerdict] = useState<'APPROVED' | 'REJECTED'>('APPROVED');
  const [reviewer, setReviewer] = useState('');
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!reviewer.trim()) { setError('Reviewer name is required'); return; }
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`/api/policies/recovery-queue/${item.transaction_id}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ verdict, reviewer: reviewer.trim(), notes: notes.trim() || null }),
      });
      if (!res.ok) throw new Error(await res.text());
      onResolved();
    } catch (e: any) {
      setError(e.message);
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg border border-border p-6 w-[28rem] shadow-lg">
        <h3 className="text-section text-text-primary mb-1">Resolve Queue Item</h3>
        <p className="text-caption text-text-secondary mb-4">
          {item.is_override
            ? '⚠ This is a BLOCKED item — approving means deliberately overriding a fired guardrail.'
            : 'This is an ESCALATED item — human judgment is the intended resolution path.'}
        </p>

        <div className="space-y-3 mb-4">
          <div>
            <label className="text-caption text-text-secondary block mb-1">Verdict</label>
            <select value={verdict} onChange={(e) => setVerdict(e.target.value as any)} className="w-full px-3 py-2 border border-border rounded text-body">
              <option value="APPROVED">APPROVED</option>
              <option value="REJECTED">REJECTED</option>
            </select>
          </div>
          <div>
            <label className="text-caption text-text-secondary block mb-1">Reviewer</label>
            <input value={reviewer} onChange={(e) => setReviewer(e.target.value)} placeholder="Your name" className="w-full px-3 py-2 border border-border rounded text-body focus:outline-none focus:border-accent" />
          </div>
          <div>
            <label className="text-caption text-text-secondary block mb-1">Notes (optional)</label>
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} className="w-full px-3 py-2 border border-border rounded text-body focus:outline-none focus:border-accent resize-none" />
          </div>
        </div>

        {error && <p className="text-caption text-danger mb-3">{error}</p>}

        <div className="flex gap-3 justify-end">
          <button onClick={onClose} disabled={submitting} className="px-4 py-2 border border-border rounded text-body hover:bg-background disabled:opacity-50">Cancel</button>
          <button onClick={submit} disabled={submitting} className="px-4 py-2 bg-accent text-white text-body rounded hover:bg-accent/90 disabled:opacity-50">
            {submitting ? 'Submitting…' : 'Submit'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function RecoveryQueue() {
  const [data, setData] = useState<QueueResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [resolving, setResolving] = useState<QueueItem | null>(null);
  const navigate = useNavigate();

  const load = () => {
    setLoading(true);
    fetch('/api/policies/recovery-queue')
      .then((r) => { if (!r.ok) throw new Error(`API ${r.status}`); return r.json(); })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <p className="text-danger font-medium">Failed to load recovery queue</p>
        <p className="text-caption text-text-secondary">{error}</p>
        <button onClick={load} className="text-accent text-body hover:underline">Retry</button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold text-text-primary">Recovery Queue</h2>

      {/* Counts bar */}
      {data && (
        <div className="flex gap-6 text-body">
          <span>Pending: <strong className="text-warning tabular-nums">{data.pending_count}</strong></span>
          <span>Approved: <strong className="text-success tabular-nums">{data.approved_count}</strong></span>
          <span>Rejected: <strong className="text-danger tabular-nums">{data.rejected_count}</strong></span>
          <span className="text-text-secondary">Total: {data.total_count}</span>
        </div>
      )}

      {/* Table */}
      <div className="bg-white border border-border rounded-lg overflow-hidden">
        <table className="w-full text-body">
          <thead>
            <tr className="border-b border-border bg-background">
              <th className="text-left px-4 py-3 text-caption text-text-secondary font-medium">Transaction</th>
              <th className="text-right px-4 py-3 text-caption text-text-secondary font-medium">Amount</th>
              <th className="text-left px-4 py-3 text-caption text-text-secondary font-medium">Type</th>
              <th className="text-left px-4 py-3 text-caption text-text-secondary font-medium">Verdict</th>
              <th className="text-left px-4 py-3 text-caption text-text-secondary font-medium">Reason Codes</th>
              <th className="text-left px-4 py-3 text-caption text-text-secondary font-medium">Status</th>
              <th className="text-left px-4 py-3 text-caption text-text-secondary font-medium">Action</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-text-secondary">Loading…</td></tr>
            ) : data && data.items.length > 0 ? (
              data.items.map((item) => (
                <tr key={item.transaction_id} className="border-b border-border hover:bg-background">
                  <td className="px-4 py-3 font-mono text-caption text-accent cursor-pointer" onClick={() => navigate(`/agent-replay/${item.transaction_id}`)}>
                    {item.transaction_id.substring(0, 8)}…
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">₹{item.amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                  <td className="px-4 py-3">{item.action_type}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={item.original_verdict} />
                    {item.is_override && <span className="text-caption text-danger ml-1">(override)</span>}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {item.reason_codes.map((code, i) => (
                        <span key={i} className="px-1.5 py-0.5 text-caption bg-background rounded font-mono text-text-secondary">{code}</span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    {item.review_status === 'PENDING_REVIEW' ? (
                      <span className="text-warning font-medium">Pending</span>
                    ) : item.review_status === 'APPROVED' ? (
                      <span className="text-success font-medium">Approved</span>
                    ) : (
                      <span className="text-danger font-medium">Rejected</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {item.review_status === 'PENDING_REVIEW' && (
                      <button onClick={() => setResolving(item)} className="text-accent text-body hover:underline">Resolve</button>
                    )}
                  </td>
                </tr>
              ))
            ) : (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-text-secondary">Queue empty — no ESCALATED or BLOCKED items</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {resolving && (
        <ResolveModal item={resolving} onClose={() => setResolving(null)} onResolved={() => { setResolving(null); load(); }} />
      )}
    </div>
  );
}
