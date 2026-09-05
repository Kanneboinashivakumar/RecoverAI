import StatusBadge from './StatusBadge';

interface PolicyCheck {
  check_name: string;
  passed: boolean;
  reason_code: string | null;
}

interface DecisionData {
  decision_id: string;
  action_type: string;
  channel: string;
  delay_hours: number;
  amount: number;
  confidence_llm: number | null;
  expected_value_llm: number | null;
  expected_value_verified: number | null;
  reason_codes: string[] | null;
  policy_context: Record<string, any> | null;
  created_at: string;
}

interface Props {
  decision: DecisionData | null;
  policyVerdict: string | null;
  policyChecks: PolicyCheck[];
  verificationOutcome: string | null;
  recoveredAmount: number | null;
  compact?: boolean;
}

function formatINR(n: number): string {
  return `₹${Math.abs(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function DecisionReceipt({
  decision,
  policyVerdict,
  policyChecks,
  verificationOutcome,
  recoveredAmount,
  compact,
}: Props) {
  if (!decision) {
    return (
      <div className="bg-white border border-border rounded-lg p-5">
        <p className="text-text-secondary text-body">No decision recorded for this transaction.</p>
      </div>
    );
  }

  const evMismatch =
    decision.expected_value_llm != null &&
    decision.expected_value_verified != null &&
    Math.abs(decision.expected_value_llm - decision.expected_value_verified) > 0.01;

  const verdictBorder =
    policyVerdict === 'APPROVED'
      ? 'border-l-success'
      : policyVerdict === 'BLOCKED'
      ? 'border-l-danger'
      : policyVerdict === 'ESCALATED'
      ? 'border-l-warning'
      : 'border-l-border';

  return (
    <div className="space-y-0 bg-white border border-border rounded-lg overflow-hidden">
      {/* Section 1: AI Recommendation */}
      <div className="border-l-4 border-l-accent p-5">
        <h4 className="text-caption text-text-secondary uppercase tracking-wider mb-3 font-medium">
          AI Recommendation
        </h4>
        <div className={`grid ${compact ? 'grid-cols-3' : 'grid-cols-4'} gap-4`}>
          <div>
            <p className="text-caption text-text-secondary">Action</p>
            <p className="text-body font-medium text-text-primary">{decision.action_type}</p>
          </div>
          <div>
            <p className="text-caption text-text-secondary">Channel</p>
            <p className="text-body font-medium text-text-primary">{decision.channel}</p>
          </div>
          <div>
            <p className="text-caption text-text-secondary">Delay</p>
            <p className="text-body font-medium text-text-primary tabular-nums">{decision.delay_hours}h</p>
          </div>
          {!compact && (
            <div>
              <p className="text-caption text-text-secondary">Amount</p>
              <p className="text-body font-medium text-text-primary tabular-nums">{formatINR(decision.amount)}</p>
            </div>
          )}
          <div>
            <p className="text-caption text-text-secondary">LLM Confidence</p>
            <p className="text-body font-medium text-text-primary tabular-nums">
              {decision.confidence_llm != null ? `${(decision.confidence_llm * 100).toFixed(1)}%` : '—'}
            </p>
          </div>
          <div>
            <p className="text-caption text-text-secondary">LLM Expected Value</p>
            <p className="text-body font-medium text-text-primary tabular-nums">
              {decision.expected_value_llm != null ? formatINR(decision.expected_value_llm) : '—'}
            </p>
          </div>
        </div>
        {decision.reason_codes && decision.reason_codes.length > 0 && (
          <div className="mt-3">
            <p className="text-caption text-text-secondary mb-1">Reason Codes</p>
            <div className="flex flex-wrap gap-1">
              {decision.reason_codes.map((code, i) => (
                <span key={i} className="px-2 py-0.5 text-caption bg-background rounded font-mono text-text-secondary">
                  {code}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Divider */}
      <div className="border-t border-border" />

      {/* Section 2: Verification */}
      <div className="border-l-4 border-l-border p-5">
        <h4 className="text-caption text-text-secondary uppercase tracking-wider mb-3 font-medium">
          Backend Verification
        </h4>
        <div className="grid grid-cols-3 gap-4">
          <div>
            <p className="text-caption text-text-secondary">Verified EV</p>
            <p className={`text-body font-medium tabular-nums ${evMismatch ? 'text-danger' : 'text-text-primary'}`}>
              {decision.expected_value_verified != null ? formatINR(decision.expected_value_verified) : '—'}
            </p>
          </div>
          {evMismatch && (
            <div className="col-span-2">
              <p className="text-caption text-danger">
                ⚠ LLM claimed {formatINR(decision.expected_value_llm!)} but backend verified{' '}
                {formatINR(decision.expected_value_verified!)}
              </p>
            </div>
          )}
          {verificationOutcome && (
            <>
              <div>
                <p className="text-caption text-text-secondary">Outcome</p>
                <StatusBadge status={verificationOutcome === 'success' ? 'APPROVED' : 'BLOCKED'} />
              </div>
              {recoveredAmount != null && (
                <div>
                  <p className="text-caption text-text-secondary">Simulated Recovered</p>
                  <p className="text-body font-medium text-success tabular-nums">{formatINR(recoveredAmount)}</p>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Divider */}
      <div className="border-t border-border" />

      {/* Section 3: Policy Authorization */}
      <div className={`border-l-4 ${verdictBorder} p-5`}>
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-caption text-text-secondary uppercase tracking-wider font-medium">
            Policy Authorization
          </h4>
          {policyVerdict && <StatusBadge status={policyVerdict} />}
        </div>

        {policyChecks.length > 0 ? (
          <div className="space-y-1.5">
            {policyChecks.map((check, i) => (
              <div key={i} className="flex items-center gap-2 text-body">
                <span className={check.passed ? 'text-success' : 'text-danger'}>
                  {check.passed ? '✓' : '✗'}
                </span>
                <span className="text-text-primary">{check.check_name}</span>
                {check.reason_code === 'NA_NON_MANDATE' ? (
                  <span className="text-caption text-text-secondary italic ml-auto">
                    N/A — not a mandate transaction
                  </span>
                ) : check.reason_code ? (
                  <span className="text-caption text-text-secondary font-mono ml-auto">
                    {check.reason_code}
                  </span>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-caption text-text-secondary">No policy check details available</p>
        )}
      </div>
    </div>
  );
}

export type { DecisionData, PolicyCheck, Props as DecisionReceiptProps };
