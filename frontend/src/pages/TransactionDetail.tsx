import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import DecisionReceipt from '../components/DecisionReceipt';
import SimulationBadge from '../components/SimulationBadge';

interface TransactionDetailData {
  id: string;
  customer_id: string;
  merchant_id: string;
  amount: number;
  currency: string;
  payment_method: string;
  status: string;
  failure_code: string | null;
  created_at: string;
  customer_language: string | null;
  customer_channel: string | null;
  diagnosis_source: string | null;
  diagnosis_confidence: number | null;
  diagnosis_reason_codes: string[] | null;
  recovery_probability: number | null;
  model_version: string | null;
  decision: any | null;
  policy_verdict: string | null;
  policy_checks: { check_name: string; passed: boolean; reason_code: string | null }[];
  action_status: string | null;
  verification_outcome: string | null;
  recovered_amount: number | null;
}

export default function TransactionDetail() {
  const { transactionId } = useParams<{ transactionId: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<TransactionDetailData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!transactionId) return;
    setLoading(true);
    fetch(`/api/transactions/${transactionId}`)
      .then((r) => { if (!r.ok) throw new Error(`API ${r.status}`); return r.json(); })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [transactionId]);

  if (loading) return <div className="flex justify-center py-16"><p className="text-text-secondary">Loading…</p></div>;
  if (error || !data) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <p className="text-danger font-medium">Failed to load transaction</p>
        <p className="text-caption text-text-secondary">{error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button onClick={() => navigate('/transactions')} className="text-accent hover:underline text-body">
          ← Transactions
        </button>
        <h2 className="text-xl font-semibold text-text-primary">Transaction Detail</h2>
        <SimulationBadge />
      </div>

      {/* Transaction Info */}
      <div className="bg-white border border-border rounded-lg p-5">
        <h3 className="text-section text-text-primary mb-3">Transaction</h3>
        <div className="grid grid-cols-4 gap-4">
          <div>
            <p className="text-caption text-text-secondary">ID</p>
            <p className="text-body font-mono">{data.id.substring(0, 8)}…</p>
          </div>
          <div>
            <p className="text-caption text-text-secondary">Amount</p>
            <p className="text-body font-medium tabular-nums">₹{data.amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</p>
          </div>
          <div>
            <p className="text-caption text-text-secondary">Payment Method</p>
            <p className="text-body">{data.payment_method}</p>
          </div>
          <div>
            <p className="text-caption text-text-secondary">Failure Code</p>
            <p className="text-body font-mono">{data.failure_code || '—'}</p>
          </div>
          <div>
            <p className="text-caption text-text-secondary">Customer Language</p>
            <p className="text-body">{data.customer_language || '—'}</p>
          </div>
          <div>
            <p className="text-caption text-text-secondary">Diagnosis Source</p>
            <p className="text-body">{data.diagnosis_source || '—'}</p>
          </div>
          <div>
            <p className="text-caption text-text-secondary">Recovery Probability</p>
            <p className="text-body tabular-nums">
              {data.recovery_probability != null ? `${(data.recovery_probability * 100).toFixed(1)}%` : '—'}
            </p>
          </div>
          <div>
            <p className="text-caption text-text-secondary">Model</p>
            <p className="text-body font-mono text-caption">{data.model_version || '—'}</p>
          </div>
        </div>
      </div>

      {/* Decision Receipt */}
      <div>
        <h3 className="text-section text-text-primary mb-3">Decision Receipt</h3>
        <DecisionReceipt
          decision={data.decision}
          policyVerdict={data.policy_verdict}
          policyChecks={data.policy_checks}
          verificationOutcome={data.verification_outcome}
          recoveredAmount={data.recovered_amount}
        />
      </div>

      {/* Link to Agent Replay */}
      <div className="flex gap-3">
        <button
          onClick={() => navigate(`/agent-replay/${data.id}`)}
          className="px-4 py-2 border border-accent text-accent text-body rounded hover:bg-accent/5 transition-colors"
        >
          View Agent Replay →
        </button>
      </div>
    </div>
  );
}
