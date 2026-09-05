import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import StatusBadge from '../components/StatusBadge';

interface TransactionSummary {
  id: string;
  amount: number;
  currency: string;
  payment_method: string;
  failure_code: string | null;
  action_type: string | null;
  policy_verdict: string | null;
  recovery_outcome: string | null;
  recovered_amount: number | null;
  created_at: string;
}

interface TransactionListResponse {
  total_count: number;
  items: TransactionSummary[];
}

const PAYMENT_METHODS = ['', 'UPI', 'CARD', 'NETBANKING', 'MANDATE'];
const VERDICTS = ['', 'APPROVED', 'BLOCKED', 'ESCALATED'];

export default function Transactions() {
  const [data, setData] = useState<TransactionListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  // Filters
  const [method, setMethod] = useState('');
  const [verdict, setVerdict] = useState('');
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const limit = 25;

  const load = () => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams();
    if (method) params.set('payment_method', method);
    if (verdict) params.set('verdict', verdict);
    if (search) params.set('search', search);
    params.set('limit', String(limit));
    params.set('offset', String(offset));

    fetch(`/api/transactions?${params}`)
      .then((r) => { if (!r.ok) throw new Error(`API ${r.status}`); return r.json(); })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [method, verdict, offset]);

  const doSearch = () => { setOffset(0); load(); };

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <p className="text-danger font-medium">Failed to load transactions</p>
        <p className="text-caption text-text-secondary">{error}</p>
        <button onClick={load} className="text-accent text-body hover:underline">Retry</button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold text-text-primary">Transaction Explorer</h2>

      {/* Filters */}
      <div className="flex gap-3 items-end flex-wrap">
        <div>
          <label className="text-caption text-text-secondary block mb-1">Payment Method</label>
          <select
            value={method}
            onChange={(e) => { setMethod(e.target.value); setOffset(0); }}
            className="px-3 py-2 border border-border rounded text-body bg-white focus:outline-none focus:border-accent"
          >
            <option value="">All</option>
            {PAYMENT_METHODS.filter(Boolean).map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>
        <div>
          <label className="text-caption text-text-secondary block mb-1">Policy Verdict</label>
          <select
            value={verdict}
            onChange={(e) => { setVerdict(e.target.value); setOffset(0); }}
            className="px-3 py-2 border border-border rounded text-body bg-white focus:outline-none focus:border-accent"
          >
            <option value="">All</option>
            {VERDICTS.filter(Boolean).map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
        </div>
        <div>
          <label className="text-caption text-text-secondary block mb-1">Search (UUID prefix)</label>
          <div className="flex gap-1">
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && doSearch()}
              placeholder="e.g. a1b2c3d4"
              className="px-3 py-2 border border-border rounded text-body font-mono focus:outline-none focus:border-accent w-52"
            />
            <button onClick={doSearch} className="px-3 py-2 bg-accent text-white text-body rounded hover:bg-accent/90">
              Search
            </button>
          </div>
        </div>
      </div>

      {/* Results count */}
      {data && (
        <p className="text-caption text-text-secondary">
          {data.total_count.toLocaleString()} transactions found · showing {offset + 1}–{Math.min(offset + limit, data.total_count)}
        </p>
      )}

      {/* Table */}
      <div className="bg-white border border-border rounded-lg overflow-hidden">
        <table className="w-full text-body">
          <thead>
            <tr className="border-b border-border bg-background">
              <th className="text-left px-4 py-3 text-caption text-text-secondary font-medium">Transaction ID</th>
              <th className="text-right px-4 py-3 text-caption text-text-secondary font-medium">Amount</th>
              <th className="text-left px-4 py-3 text-caption text-text-secondary font-medium">Method</th>
              <th className="text-left px-4 py-3 text-caption text-text-secondary font-medium">Failure Code</th>
              <th className="text-left px-4 py-3 text-caption text-text-secondary font-medium">Action</th>
              <th className="text-left px-4 py-3 text-caption text-text-secondary font-medium">Verdict</th>
              <th className="text-left px-4 py-3 text-caption text-text-secondary font-medium">Outcome</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-text-secondary">Loading…</td></tr>
            ) : data && data.items.length > 0 ? (
              data.items.map((tx) => (
                <tr
                  key={tx.id}
                  onClick={() => navigate(`/transactions/${tx.id}`)}
                  className="border-b border-border hover:bg-background cursor-pointer transition-colors"
                >
                  <td className="px-4 py-3 font-mono text-caption text-accent">{tx.id.substring(0, 8)}…</td>
                  <td className="px-4 py-3 text-right tabular-nums">₹{tx.amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                  <td className="px-4 py-3">{tx.payment_method}</td>
                  <td className="px-4 py-3 font-mono text-caption">{tx.failure_code || '—'}</td>
                  <td className="px-4 py-3">{tx.action_type || '—'}</td>
                  <td className="px-4 py-3">{tx.policy_verdict ? <StatusBadge status={tx.policy_verdict} /> : '—'}</td>
                  <td className="px-4 py-3">
                    {tx.recovery_outcome === 'success' ? (
                      <span className="text-success font-medium tabular-nums">
                        ₹{tx.recovered_amount?.toLocaleString('en-IN', { minimumFractionDigits: 2 }) || '—'}
                      </span>
                    ) : tx.recovery_outcome === 'failure' ? (
                      <span className="text-text-secondary">Not recovered</span>
                    ) : '—'}
                  </td>
                </tr>
              ))
            ) : (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-text-secondary">No transactions found</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {data && data.total_count > limit && (
        <div className="flex justify-center gap-3">
          <button
            onClick={() => setOffset(Math.max(0, offset - limit))}
            disabled={offset === 0}
            className="px-4 py-2 border border-border rounded text-body hover:bg-background disabled:opacity-30"
          >
            ← Previous
          </button>
          <button
            onClick={() => setOffset(offset + limit)}
            disabled={offset + limit >= data.total_count}
            className="px-4 py-2 border border-border rounded text-body hover:bg-background disabled:opacity-30"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
