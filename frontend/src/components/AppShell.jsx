import { Link, NavLink, useLocation, Navigate } from "react-router-dom";
import { CheckCheck, LogOut, LayoutDashboard, Mail, Send, Settings as SettingsIcon, Zap, MessageCircle, Menu, X } from "lucide-react";
import { useAuth } from "../lib/AuthContext";
import { logout } from "../lib/api";
import { useState, useEffect } from "react";

export default function AppShell({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  // Close mobile menu on route change
  useEffect(() => {
    setIsMobileMenuOpen(false);
  }, [location.pathname]);

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
    { to: "/active-mails", label: "Active Mails", icon: MessageCircle, testid: "nav-active-mails" },
    { to: "/automation", label: "Automation", icon: Zap, testid: "nav-automation" },
    { to: "/follow-ups", label: "Follow-ups", icon: Send, testid: "nav-followups" },
    { to: "/settings", label: "Settings", icon: SettingsIcon, testid: "nav-settings" },
  ];

  const SidebarContent = () => (
    <>
      <div className="p-6 border-b border-slate-50 mb-4 hidden lg:block">
        <Link to="/dashboard" className="flex items-center gap-2" data-testid="logo-link">
          <div className="w-8 h-8 bg-[#0A0A0A] flex items-center justify-center">
            <CheckCheck className="w-4 h-4 text-[#10B981]" strokeWidth={2.5} />
          </div>
          <span className="font-black tracking-tighter text-xl text-black">MailTrack</span>
        </Link>
      </div>
      <nav className="p-4 space-y-1">
        {links.map((l) => {
          const Icon = l.icon;
          return (
            <NavLink
              key={l.to}
              to={l.to}
              data-testid={l.testid}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-3 text-sm font-bold transition-all rounded-lg ${isActive
                  ? "bg-[#0A0A0A] text-white shadow-lg shadow-slate-200"
                  : "text-slate-600 hover:bg-slate-50 hover:text-black"
                }`
              }
            >
              <Icon className={`w-4 h-4 ${location.pathname === l.to ? "text-[#10B981]" : "text-slate-400"}`} />
              {l.label}
            </NavLink>
          );
        })}
      </nav>
    </>
  );

  return (
    <div className="min-h-screen bg-[#F8F9FA]">
      {/* Mobile Sidebar Overlay */}
      {isMobileMenuOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-[60] lg:hidden backdrop-blur-sm transition-opacity"
          onClick={() => setIsMobileMenuOpen(false)}
        />
      )}

      {/* Mobile Sidebar Panel */}
      <aside className={`fixed left-0 top-0 bottom-0 w-72 bg-white z-[70] lg:hidden transition-transform duration-300 ease-in-out ${isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="p-6 border-b border-slate-50 flex items-center justify-between">
          <Link to="/dashboard" className="flex items-center gap-2">
            <div className="w-7 h-7 bg-[#0A0A0A] flex items-center justify-center">
              <CheckCheck className="w-3.5 h-3.5 text-[#10B981]" strokeWidth={2.5} />
            </div>
            <span className="font-black tracking-tighter text-lg text-black">MailTrack</span>
          </Link>
          <button onClick={() => setIsMobileMenuOpen(false)} className="p-2 hover:bg-slate-50 rounded-full">
            <X className="w-5 h-5 text-slate-400" />
          </button>
        </div>
        <SidebarContent />
      </aside>

      {/* Desktop Sidebar - Fixed Full Height */}
      <aside className="fixed left-0 top-0 bottom-0 w-64 bg-white border-r border-slate-200 hidden lg:block z-50 shadow-sm">
        <SidebarContent />
      </aside>

      {/* Main Container (Shifted Right) */}
      <div className="lg:pl-64 flex flex-col min-h-screen">
        {/* Header - Fixed to Right of Sidebar */}
        <header className="fixed top-0 right-0 left-0 lg:left-64 h-16 bg-white/80 backdrop-blur-md border-b border-slate-200 z-40 flex items-center px-6 justify-between shadow-sm">
          <div className="flex items-center gap-4">
            <button
              onClick={() => setIsMobileMenuOpen(true)}
              className="lg:hidden p-2 -ml-2 hover:bg-slate-50 rounded-lg transition-colors"
            >
              <Menu className="w-6 h-6 text-slate-600" />
            </button>
            <div className="lg:hidden">
              <Link to="/dashboard" className="flex items-center gap-2">
                <span className="font-black tracking-tighter text-xl text-black">MT</span>
              </Link>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="text-right hidden sm:block">
              <div className="text-xs font-black leading-tight text-slate-900" data-testid="header-user-name">{user.name}</div>
              <div className="text-[9px] text-slate-400 font-bold uppercase tracking-widest leading-tight">{user.email}</div>
            </div>
            {user.picture && (
              <img src={user.picture} alt="" className="w-8 h-8 rounded-full border border-slate-200 ring-2 ring-slate-50" />
            )}
            <button
              onClick={logout}
              data-testid="logout-btn"
              className="p-2 hover:bg-slate-100 rounded-full transition-colors"
              title="Logout"
            >
              <LogOut className="w-4 h-4 text-slate-400 hover:text-red-500" />
            </button>
          </div>
        </header>

        {/* Content Area Area */}
        <main className="flex-1 pt-16 pb-10 px-4 lg:px-10">
          <div className="max-w-[1600px] mx-auto py-8">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
