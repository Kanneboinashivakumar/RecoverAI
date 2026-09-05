import { useEffect, useState } from 'react';
import { getOverview, type OverviewData, type FailureBreakdown } from '../api/client';
import KPICard from '../components/KPICard';
import SimulationBadge from '../components/SimulationBadge';

function formatINR(n: number): string {
  const abs = Math.abs(n);
  const sign = n < 0 ? '-' : '';
  if (abs >= 1_00_000) {
    return `${sign}₹${abs.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
  }
  return `${sign}₹${abs.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// ---- Inline SVG Bar Chart for failure breakdown ----
function FailureChart({ data }: { data: FailureBreakdown[] }) {
  if (!data.length) return <p className="text-caption text-text-secondary">No failure data</p>;

  const max = Math.max(...data.map((d) => d.count));
  const top10 = data.slice(0, 10);

  return (
    <div className="space-y-2">
      {top10.map((item) => (
        <div key={item.failure_code} className="flex items-center gap-3">
          <span className="text-caption text-text-secondary w-48 truncate text-right font-mono">
            {item.failure_code}
          </span>
          <div className="flex-1 h-5 bg-background rounded overflow-hidden">
            <div
              className="h-full bg-accent/20 rounded"
              style={{ width: `${(item.count / max) * 100}%` }}
            />
          </div>
          <span className="text-caption tabular-nums text-text-primary w-10 text-right">
            {item.count}
          </span>
        </div>
      ))}
    </div>
  );
}

// ---- Inline SVG Line/Area chart for trend data ----
function TrendChart({ data }: { data: { date: string; events: number; recovered: number }[] }) {
  if (!data.length) return <p className="text-caption text-text-secondary">No trend data</p>;

  const W = 640;
  const H = 180;
  const PAD_L = 40;
  const PAD_R = 65;
  const PAD_Y = 25;

  const maxEvents = Math.max(...data.map((d) => d.events), 1);
  const maxRecovered = Math.max(...data.map((d) => d.recovered), 1);

  const plotW = W - PAD_L - PAD_R;
  const plotH = H - PAD_Y * 2;

  const pointsEvents = data.map((d, i) => {
    const x = PAD_L + (i / Math.max(data.length - 1, 1)) * plotW;
    const y = PAD_Y + (1 - d.events / maxEvents) * plotH;
    return `${x},${y}`;
  });

  const pointsRecovered = data.map((d, i) => {
    const x = PAD_L + (i / Math.max(data.length - 1, 1)) * plotW;
    const y = PAD_Y + (1 - d.recovered / maxRecovered) * plotH;
    return `${x},${y}`;
  });

  // Ticks at 0%, 50%, 100%
  const ticks = [0, 0.5, 1];

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" preserveAspectRatio="xMidYMid meet">
        {/* Grid lines & Axis Labels */}
        {ticks.map((frac) => {
          const y = PAD_Y + (1 - frac) * plotH;
          const eventVal = Math.round(frac * maxEvents);
          const recVal = Math.round((frac * maxRecovered) / 1000);
          return (
            <g key={frac}>
              <line x1={PAD_L} y1={y} x2={W - PAD_R} y2={y} stroke="#E4E7EC" strokeWidth="1" strokeDasharray="2 2" />
              {/* Left Axis: Events */}
              <text x={PAD_L - 8} y={y + 4} textAnchor="end" fontSize="10" fill="#3538CD" fontFamily="monospace">
                {eventVal}
              </text>
              {/* Right Axis: Recovered (₹) */}
              <text x={W - PAD_R + 8} y={y + 4} textAnchor="start" fontSize="10" fill="#12B76A" fontFamily="monospace">
                {`₹${recVal}k`}
              </text>
            </g>
          );
        })}

        {/* Events line (Indigo) */}
        <polyline
          points={pointsEvents.join(' ')}
          fill="none"
          stroke="#3538CD"
          strokeWidth="2"
          strokeLinejoin="round"
        />

        {/* Recovered line (Green Dashed) */}
        <polyline
          points={pointsRecovered.join(' ')}
          fill="none"
          stroke="#12B76A"
          strokeWidth="2.5"
          strokeLinejoin="round"
          strokeDasharray="5 3"
        />
      </svg>

      {/* Dual Axis Legend */}
      <div className="flex gap-8 mt-2 justify-center text-caption">
        <div className="flex items-center gap-2">
          <span className="w-4 h-0.5 bg-accent inline-block" />
          <span className="text-accent font-medium">Events (left axis)</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-4 h-0.5 bg-success inline-block" style={{ borderTop: '2px dashed #12B76A', height: 0 }} />
          <span className="text-success font-medium">Recovered ₹ (right axis)</span>
        </div>
      </div>
    </div>
  );
}

// ---- Batch Trigger Modal ----
function BatchTrigger({ onComplete }: { onComplete: () => void }) {
  const [open, setOpen] = useState(false);
  const [seed, setSeed] = useState('42');
  const [count, setCount] = useState('500');
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setRunning(true);
    setError(null);
    setProgress(10);

    // Simulate progress while waiting for the sync endpoint
    const interval = setInterval(() => {
      setProgress((p) => Math.min(p + 5, 90));
    }, 3000);

    try {
      const res = await fetch('/api/experiments/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ seed: parseInt(seed), count: parseInt(count) }),
        signal: AbortSignal.timeout(120_000),
      });
      clearInterval(interval);

      if (!res.ok) {
        const body = await res.text();
        throw new Error(body);
      }

      setProgress(100);
      setTimeout(() => {
        setOpen(false);
        setRunning(false);
        setProgress(0);
        onComplete();
      }, 500);
    } catch (e: any) {
      clearInterval(interval);
      setError(e.message || 'Experiment failed');
      setRunning(false);
      setProgress(0);
    }
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="px-4 py-2 bg-accent text-white text-body font-medium rounded hover:bg-accent/90 transition-colors"
      >
        Run Recovery Batch
      </button>
    );
  }

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg border border-border p-6 w-96 shadow-lg">
        <h3 className="text-section text-text-primary mb-4">Run Recovery Experiment</h3>

        <div className="space-y-3 mb-4">
          <div>
            <label className="text-caption text-text-secondary block mb-1">Seed</label>
            <input
              type="number"
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
              disabled={running}
              className="w-full px-3 py-2 border border-border rounded text-body tabular-nums focus:outline-none focus:border-accent"
            />
          </div>
          <div>
            <label className="text-caption text-text-secondary block mb-1">Transaction Count</label>
            <input
              type="number"
              value={count}
              onChange={(e) => setCount(e.target.value)}
              disabled={running}
              className="w-full px-3 py-2 border border-border rounded text-body tabular-nums focus:outline-none focus:border-accent"
            />
          </div>
        </div>

        {running && (
          <div className="mb-4">
            <div className="w-full h-2 bg-background rounded overflow-hidden">
              <div
                className="h-full bg-accent rounded transition-all duration-500"
                style={{ width: `${progress}%` }}
              />
            </div>
            <p className="text-caption text-text-secondary mt-1">Running experiment… this may take 30-60s</p>
          </div>
        )}

        {error && (
          <p className="text-caption text-danger mb-3">{error}</p>
        )}

        <div className="flex gap-3 justify-end">
          <button
            onClick={() => { setOpen(false); setError(null); }}
            disabled={running}
            className="px-4 py-2 border border-border text-body rounded hover:bg-background transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={run}
            disabled={running}
            className="px-4 py-2 bg-accent text-white text-body font-medium rounded hover:bg-accent/90 transition-colors disabled:opacity-50"
          >
            {running ? 'Running…' : 'Start'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---- Main Overview Page ----
export default function Overview() {
  const [data, setData] = useState<OverviewData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    setError(null);
    getOverview()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-text-secondary">Loading overview…</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <p className="text-danger font-medium">Failed to load dashboard data</p>
        <p className="text-caption text-text-secondary">{error}</p>
        <button onClick={load} className="text-accent text-body hover:underline">Retry</button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-text-primary">Overview</h2>
          {data.experiment_run_at && (
            <p className="text-caption text-text-secondary mt-0.5">
              Last experiment: seed={data.experiment_seed}, n={data.experiment_batch_size},{' '}
              {new Date(data.experiment_run_at).toLocaleString()}
            </p>
          )}
        </div>
        <BatchTrigger onComplete={load} />
      </div>

      {/* KPI cards row */}
      <div className="grid grid-cols-5 gap-4">
        <KPICard
          label="Simulated Net Incremental ₹ Recovered"
          value={formatINR(data.incremental_recovered)}
          sublabel={data.experiment_seed ? `Seed ${data.experiment_seed} · n=${data.experiment_batch_size}` : 'No experiment run yet'}
          accent
        />
        <KPICard
          label="Recovery Rate"
          value={`${data.recovery_rate}%`}
        />
        <KPICard
          label="Total Events"
          value={data.total_events.toLocaleString()}
        />
        <KPICard
          label="Escalations"
          value={data.escalation_count.toLocaleString()}
        />
        <KPICard
          label="Blocked"
          value={data.blocked_count.toLocaleString()}
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-2 gap-6">
        {/* Failure breakdown */}
        <div className="bg-white border border-border rounded-lg p-5">
          <h3 className="text-section text-text-primary mb-4">Failure Reason Breakdown</h3>
          <FailureChart data={data.failure_breakdown} />
        </div>

        {/* Trend chart */}
        <div className="bg-white border border-border rounded-lg p-5">
          <h3 className="text-section text-text-primary mb-4">Event & Recovery Trend</h3>
          <TrendChart data={data.trend_data} />
        </div>
      </div>
    </div>
  );
}
