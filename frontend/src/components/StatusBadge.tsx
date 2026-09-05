interface Props {
  status: 'APPROVED' | 'BLOCKED' | 'ESCALATED' | string;
}

const COLORS: Record<string, string> = {
  APPROVED: 'bg-success/10 text-success border-success/30',
  BLOCKED: 'bg-danger/10 text-danger border-danger/30',
  ESCALATED: 'bg-warning/10 text-warning border-warning/30',
};

export default function StatusBadge({ status }: Props) {
  const cls = COLORS[status] || 'bg-background text-text-secondary border-border';
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-caption font-medium border ${cls}`}>
      {status}
    </span>
  );
}
