export default function SimulationBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-caption font-medium bg-warning/10 text-warning border border-warning/30">
      <span className="inline-block w-1.5 h-1.5 rounded-full bg-warning animate-pulse" />
      Simulation / Test Mode
    </span>
  );
}
