import { NavLink } from 'react-router-dom';

const NAV_ITEMS = [
  { to: '/', label: 'Overview', icon: '◉' },
  { to: '/transactions', label: 'Transactions', icon: '⊞' },
  { to: '/recovery-queue', label: 'Recovery Queue', icon: '⊡' },
  { to: '/agent-replay', label: 'Agent Replay', icon: '⏱' },
  { to: '/policy-center', label: 'Policy Center', icon: '⛨' },
  { to: '/experiment-lab', label: 'Experiment Lab', icon: '⚗' },
];

export default function Sidebar() {
  return (
    <aside className="fixed left-0 top-0 bottom-0 w-56 bg-white border-r border-border flex flex-col z-20">
      {/* Logo */}
      <div className="h-14 flex items-center px-5 border-b border-border">
        <span className="text-lg font-bold text-accent">RecoverAI</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3 overflow-y-auto">
        {NAV_ITEMS.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-5 py-2.5 text-body transition-colors ${
                isActive
                  ? 'text-accent bg-accent/5 border-r-2 border-accent font-medium'
                  : 'text-text-secondary hover:text-text-primary hover:bg-background'
              }`
            }
          >
            <span className="text-base w-5 text-center">{icon}</span>
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-5 py-3 border-t border-border">
        <p className="text-caption text-text-secondary">v1.0 — Phase 12</p>
      </div>
    </aside>
  );
}
