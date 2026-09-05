import { useEffect, useState } from 'react';
import SimulationBadge from './SimulationBadge';

export default function TopBar() {
  const [healthy, setHealthy] = useState<boolean | null>(null);

  useEffect(() => {
    const check = () =>
      fetch('/health')
        .then((r) => setHealthy(r.ok))
        .catch(() => setHealthy(false));
    check();
    const id = setInterval(check, 30_000);
    return () => clearInterval(id);
  }, []);

  return (
    <header className="fixed top-0 left-56 right-0 h-14 bg-white border-b border-border flex items-center justify-between px-6 z-10">
      <div className="flex items-center gap-4">
        <h1 className="text-section text-text-primary">Revenue Recovery Console</h1>
        <SimulationBadge />
      </div>

      <div className="flex items-center gap-2">
        <span
          className={`inline-block w-2 h-2 rounded-full ${
            healthy === true ? 'bg-success' : healthy === false ? 'bg-danger' : 'bg-text-secondary'
          }`}
        />
        <span className="text-caption text-text-secondary">
          {healthy === true ? 'System Healthy' : healthy === false ? 'Backend Unreachable' : 'Checking…'}
        </span>
      </div>
    </header>
  );
}
