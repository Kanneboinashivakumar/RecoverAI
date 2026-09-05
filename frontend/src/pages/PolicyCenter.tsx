import { useEffect, useState } from 'react';

interface PolicyConfig {
  config: Record<string, number>;
  version: number;
}

const POLICY_DESCRIPTIONS: Record<string, string> = {
  low_tier_max: 'Maximum amount (₹) for auto-approval without confidence gate',
  mid_tier_max: 'Maximum amount (₹) before escalation is required',
  mid_tier_min_confidence: 'Minimum ML confidence for mid-tier transactions',
  max_retries: 'Maximum retry attempts per transaction',
  max_contacts_24h: 'Maximum customer contacts in 24-hour window',
  max_discount_pct: 'Maximum discount percentage allowed',
};

export default function PolicyCenter() {
  const [config, setConfig] = useState<PolicyConfig | null>(null);
  const [editing, setEditing] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const load = () => {
    setLoading(true);
    fetch('/api/policy-center/config')
      .then((r) => { if (!r.ok) throw new Error(`API ${r.status}`); return r.json(); })
      .then((data) => {
        setConfig(data);
        const editValues: Record<string, string> = {};
        for (const [k, v] of Object.entries(data.config)) {
          editValues[k] = String(v);
        }
        setEditing(editValues);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const save = async () => {
    setSaving(true);
    setSaved(false);
    try {
      const updates: Record<string, number> = {};
      for (const [k, v] of Object.entries(editing)) {
        updates[k] = parseFloat(v);
      }
      const res = await fetch('/api/policy-center/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ config: updates }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setConfig(data);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="flex justify-center py-16"><p className="text-text-secondary">Loading…</p></div>;
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <p className="text-danger font-medium">Failed to load policy config</p>
        <p className="text-caption text-text-secondary">{error}</p>
        <button onClick={load} className="text-accent text-body hover:underline">Retry</button>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-text-primary">Policy Center</h2>
          {config && <p className="text-caption text-text-secondary">Version {config.version}</p>}
        </div>
        <div className="flex items-center gap-3">
          {saved && <span className="text-success text-body font-medium">✓ Saved</span>}
          <button
            onClick={save}
            disabled={saving}
            className="px-4 py-2 bg-accent text-white text-body font-medium rounded hover:bg-accent/90 disabled:opacity-50"
          >
            {saving ? 'Saving…' : 'Save Changes'}
          </button>
        </div>
      </div>

      {/* Guardrail limits table */}
      <div className="bg-white border border-border rounded-lg overflow-hidden">
        <table className="w-full text-body">
          <thead>
            <tr className="border-b border-border bg-background">
              <th className="text-left px-4 py-3 text-caption text-text-secondary font-medium">Guardrail</th>
              <th className="text-left px-4 py-3 text-caption text-text-secondary font-medium">Description</th>
              <th className="text-right px-4 py-3 text-caption text-text-secondary font-medium w-32">Value</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(editing).map(([key, value]) => (
              <tr key={key} className="border-b border-border">
                <td className="px-4 py-3 font-mono text-caption">{key}</td>
                <td className="px-4 py-3 text-text-secondary">{POLICY_DESCRIPTIONS[key] || ''}</td>
                <td className="px-4 py-3 text-right">
                  <input
                    type="number"
                    step="any"
                    value={value}
                    onChange={(e) => setEditing({ ...editing, [key]: e.target.value })}
                    className="w-28 px-2 py-1 border border-border rounded text-body tabular-nums text-right focus:outline-none focus:border-accent"
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Check descriptions */}
      <div className="bg-white border border-border rounded-lg p-5">
        <h3 className="text-section text-text-primary mb-3">Policy Checks (6 total)</h3>
        <div className="space-y-2 text-body text-text-secondary">
          <p><strong className="text-text-primary">1. Idempotency</strong> — Prevents duplicate decisions for the same transaction</p>
          <p><strong className="text-text-primary">2. Amount Tier</strong> — Low tier (&lt;₹5k): auto-approved. Mid tier: requires min confidence. High tier (&gt;₹25k): escalated</p>
          <p><strong className="text-text-primary">3. Retry Limit</strong> — Max {editing.max_retries || '2'} retries per transaction</p>
          <p><strong className="text-text-primary">4. Contact Cap</strong> — Max {editing.max_contacts_24h || '2'} customer contacts in 24h</p>
          <p><strong className="text-text-primary">5. Discount Limit</strong> — Discount actions capped at {((parseFloat(editing.max_discount_pct) || 0.1) * 100).toFixed(0)}% of transaction amount</p>
          <p><strong className="text-text-primary">6. Mandate Compliance</strong> — NPCI mandate state machine checks (cooling-off window, revocation, expiry)</p>
        </div>
      </div>
    </div>
  );
}
