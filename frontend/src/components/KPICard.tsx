interface KPICardProps {
  label: string;
  value: string;
  sublabel?: string;
  accent?: boolean;
}

export default function KPICard({ label, value, sublabel, accent }: KPICardProps) {
  return (
    <div className={`bg-white border rounded-lg p-5 ${accent ? 'border-accent/30 ring-1 ring-accent/10' : 'border-border'}`}>
      <p className="text-caption text-text-secondary mb-1">{label}</p>
      <p className={`text-kpi tabular-nums ${accent ? 'text-accent' : 'text-text-primary'}`}>
        {value}
      </p>
      {sublabel && (
        <p className="text-caption text-text-secondary mt-1">{sublabel}</p>
      )}
    </div>
  );
}
