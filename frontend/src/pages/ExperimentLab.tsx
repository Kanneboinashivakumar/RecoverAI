import { useEffect, useState } from 'react';
import SimulationBadge from '../components/SimulationBadge';

interface ExperimentRow {
  id: string;
  seed: number;
  batch_size: number;
  policy_type: string;
  total_recovered: number | null;
  recovery_rate: number | null;
  incremental_recovered: number | null;
  run_at: string | null;
}

interface ExperimentPair {
  seed: number;
  batch_size: number;
  baseline: ExperimentRow | null;
  recoverai: ExperimentRow | null;
  net_incremental: number | null;
  run_at: string | null;
}

function formatINR(n: number): string {
  return `₹${n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function ExperimentLab() {
  const [experiments, setExperiments] = useState<ExperimentPair[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Run form
  const [seed, setSeed] = useState('42');
  const [count, setCount] = useState('500');
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [runError, setRunError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    fetch('/api/experiments')
      .then((r) => { if (!r.ok) throw new Error(`API ${r.status}`); return r.json(); })
      .then((data) => setExperiments(data.experiments))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const runExperiment = async () => {
    setRunning(true);
    setRunError(null);
    setProgress(10);
    const interval = setInterval(() => setProgress((p) => Math.min(p + 5, 90)), 3000);

    try {
      const res = await fetch('/api/experiments/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ seed: parseInt(seed), count: parseInt(count) }),
        signal: AbortSignal.timeout(120_000),
      });
      clearInterval(interval);
      if (!res.ok) throw new Error(await res.text());
      setProgress(100);
      setTimeout(() => { setRunning(false); setProgress(0); load(); }, 500);
    } catch (e: any) {
      clearInterval(interval);
      setRunError(e.message);
      setRunning(false);
      setProgress(0);
    }
  };

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <p className="text-danger font-medium">Failed to load experiments</p>
        <p className="text-caption text-text-secondary">{error}</p>
        <button onClick={load} className="text-accent text-body hover:underline">Retry</button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <h2 className="text-xl font-semibold text-text-primary">Experiment Lab</h2>
        <SimulationBadge />
      </div>

      {/* Re-run controls */}
      <div className="bg-white border border-border rounded-lg p-5">
        <h3 className="text-section text-text-primary mb-3">Run New Experiment</h3>
        <div className="flex gap-4 items-end">
          <div>
            <label className="text-caption text-text-secondary block mb-1">Seed</label>
            <input type="number" value={seed} onChange={(e) => setSeed(e.target.value)} disabled={running}
              className="px-3 py-2 border border-border rounded text-body tabular-nums w-28 focus:outline-none focus:border-accent" />
          </div>
          <div>
            <label className="text-caption text-text-secondary block mb-1">Count</label>
            <input type="number" value={count} onChange={(e) => setCount(e.target.value)} disabled={running}
              className="px-3 py-2 border border-border rounded text-body tabular-nums w-28 focus:outline-none focus:border-accent" />
          </div>
          <button onClick={runExperiment} disabled={running}
            className="px-4 py-2 bg-accent text-white text-body font-medium rounded hover:bg-accent/90 disabled:opacity-50">
            {running ? 'Running…' : 'Run A/B Comparison'}
          </button>
        </div>

        {running && (
          <div className="mt-3">
            <div className="w-full h-2 bg-background rounded overflow-hidden">
              <div className="h-full bg-accent rounded transition-all duration-500" style={{ width: `${progress}%` }} />
            </div>
            <p className="text-caption text-text-secondary mt-1">Running experiment… this may take 30-60s</p>
          </div>
        )}
        {runError && <p className="text-caption text-danger mt-2">{runError}</p>}
      </div>

      {/* Comparison table */}
      <div className="bg-white border border-border rounded-lg overflow-hidden">
        <table className="w-full text-body">
          <thead>
            <tr className="border-b border-border bg-background">
              <th className="text-left px-4 py-3 text-caption text-text-secondary font-medium">Seed</th>
              <th className="text-right px-4 py-3 text-caption text-text-secondary font-medium">Batch</th>
              <th className="text-right px-4 py-3 text-caption text-text-secondary font-medium">Baseline Recovered (₹)</th>
              <th className="text-right px-4 py-3 text-caption text-text-secondary font-medium">Baseline Rate</th>
              <th className="text-right px-4 py-3 text-caption text-text-secondary font-medium">RecoverAI Recovered (₹)</th>
              <th className="text-right px-4 py-3 text-caption text-text-secondary font-medium">RecoverAI Rate</th>
              <th className="text-right px-4 py-3 text-caption text-text-secondary font-medium">Net Incremental (₹)</th>
              <th className="text-left px-4 py-3 text-caption text-text-secondary font-medium">Run At</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-text-secondary">Loading…</td></tr>
            ) : experiments.length > 0 ? (
              experiments.map((pair) => (
                <tr key={pair.seed} className="border-b border-border hover:bg-background">
                  <td className="px-4 py-3 tabular-nums font-medium">{pair.seed}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{pair.batch_size}</td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {pair.baseline?.total_recovered != null ? formatINR(pair.baseline.total_recovered) : '—'}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {pair.baseline?.recovery_rate != null ? `${(pair.baseline.recovery_rate * 100).toFixed(1)}%` : '—'}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {pair.recoverai?.total_recovered != null ? formatINR(pair.recoverai.total_recovered) : '—'}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {pair.recoverai?.recovery_rate != null ? `${(pair.recoverai.recovery_rate * 100).toFixed(1)}%` : '—'}
                  </td>
                  <td className={`px-4 py-3 text-right tabular-nums font-medium ${
                    pair.net_incremental != null && pair.net_incremental > 0 ? 'text-success' :
                    pair.net_incremental != null && pair.net_incremental < 0 ? 'text-danger' : ''
                  }`}>
                    {pair.net_incremental != null ? formatINR(pair.net_incremental) : '—'}
                  </td>
                  <td className="px-4 py-3 text-caption text-text-secondary">
                    {pair.run_at ? new Date(pair.run_at).toLocaleString() : '—'}
                  </td>
                </tr>
              ))
            ) : (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-text-secondary">No experiments run yet. Use the form above to run your first A/B comparison.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <p className="text-caption text-text-secondary italic">
        All ₹ figures are simulated. RecoverAI batch decisioning uses the EV Engine + Policy Engine directly.
        Both policies evaluated on identical synthetic batches against the same hidden simulator.
      </p>
    </div>
  );
}
