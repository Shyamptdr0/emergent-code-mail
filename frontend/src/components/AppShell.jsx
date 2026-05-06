import { Link, NavLink, useLocation, Navigate } from "react-router-dom";
import { CheckCheck, LogOut, LayoutDashboard, Mail, Send, Settings as SettingsIcon } from "lucide-react";
import { useAuth } from "../lib/AuthContext";
import { logout } from "../lib/api";

export default function AppShell({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F8F9FA] text-slate-500 font-mono text-sm">
        Loading…
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;

  const links = [
    { to: "/dashboard", label: "Overview", icon: LayoutDashboard, testid: "nav-overview" },
    { to: "/emails", label: "Tracked emails", icon: Mail, testid: "nav-emails" },
    { to: "/follow-ups", label: "Follow-ups", icon: Send, testid: "nav-followups" },
    { to: "/settings", label: "Settings", icon: SettingsIcon, testid: "nav-settings" },
  ];

  return (
    <div className="min-h-screen bg-[#F8F9FA] text-[#0A0A0A]">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link to="/dashboard" className="flex items-center gap-2" data-testid="logo-link">
            <div className="w-8 h-8 bg-[#0A0A0A] flex items-center justify-center">
              <CheckCheck className="w-4 h-4 text-[#10B981]" strokeWidth={2.5} />
            </div>
            <span className="font-black tracking-tighter text-xl">MailTrack</span>
          </Link>
          <div className="flex items-center gap-3">
            <div className="text-right hidden sm:block">
              <div className="text-sm font-medium leading-tight" data-testid="header-user-name">{user.name}</div>
              <div className="text-xs text-slate-500 font-mono leading-tight">{user.email}</div>
            </div>
            {user.picture && (
              <img src={user.picture} alt="" className="w-9 h-9 rounded-full border border-slate-200" />
            )}
            <button
              onClick={logout}
              data-testid="logout-btn"
              className="ml-2 p-2 hover:bg-slate-100 transition-colors"
              title="Logout"
            >
              <LogOut className="w-4 h-4 text-slate-600" />
            </button>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 grid grid-cols-12 gap-8 py-10">
        <aside className="col-span-12 md:col-span-3">
          <nav className="bg-white border border-slate-200 p-2 sticky top-24">
            {links.map((l) => {
              const Icon = l.icon;
              return (
                <NavLink
                  key={l.to}
                  to={l.to}
                  data-testid={l.testid}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-4 py-3 text-sm font-medium transition-colors ${
                      isActive
                        ? "bg-[#0A0A0A] text-white"
                        : "text-slate-700 hover:bg-slate-100"
                    }`
                  }
                >
                  <Icon className="w-4 h-4" />
                  {l.label}
                </NavLink>
              );
            })}
          </nav>
        </aside>
        <main className="col-span-12 md:col-span-9">{children}</main>
      </div>
    </div>
  );
}
