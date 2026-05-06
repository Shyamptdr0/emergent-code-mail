import { Link } from "react-router-dom";
import { Check, CheckCheck, Bell, Send, Zap, ArrowRight } from "lucide-react";
import { Button } from "../components/ui/button";
import { useAuth } from "../lib/AuthContext";

export default function Landing() {
  const { user } = useAuth();
  return (
    <div className="min-h-screen bg-[#F8F9FA] text-[#0A0A0A]">
      {/* Nav */}
      <header className="border-b border-slate-200 bg-white/80 backdrop-blur-xl sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-[#0A0A0A] flex items-center justify-center">
              <CheckCheck className="w-4 h-4 text-[#10B981]" strokeWidth={2.5} />
            </div>
            <span className="font-black tracking-tighter text-xl">MailTrack</span>
          </div>
          <nav className="flex items-center gap-4">
            {user ? (
              <Link to="/dashboard" data-testid="nav-dashboard-link">
                <Button className="bg-[#0A0A0A] text-white hover:bg-slate-800 rounded-sm">Dashboard</Button>
              </Link>
            ) : (
              <Link to="/login" data-testid="nav-login-link">
                <Button className="bg-[#0A0A0A] text-white hover:bg-slate-800 rounded-sm" data-testid="nav-login-btn">
                  Sign in
                </Button>
              </Link>
            )}
          </nav>
        </div>
      </header>

      {/* Hero */}
      <section className="max-w-7xl mx-auto px-6 pt-20 pb-32">
        <div className="grid lg:grid-cols-12 gap-12 items-end">
          <div className="lg:col-span-7">
            <p className="text-xs tracking-[0.25em] uppercase font-bold text-slate-500 mb-6">
              Email Tracking · Real-time
            </p>
            <h1 className="text-5xl sm:text-6xl lg:text-7xl tracking-tighter font-black leading-[0.95]">
              Know the moment<br />
              your email is <span className="text-[#10B981]">opened.</span>
            </h1>
            <p className="mt-8 text-lg text-slate-600 max-w-xl leading-relaxed">
              A Gmail extension that adds gray and green ticks beside every sent email. Get an instant
              notification the second your recipient opens it — and schedule smart follow-ups when they don't reply.
            </p>
            <div className="mt-10 flex flex-wrap gap-4">
              <Link to={user ? "/dashboard" : "/login"} data-testid="hero-cta-btn">
                <Button className="bg-[#0A0A0A] text-white hover:bg-slate-800 rounded-sm h-12 px-8 text-base">
                  Get started — it's free <ArrowRight className="ml-2 w-4 h-4" />
                </Button>
              </Link>
              <a href="#how" className="inline-block">
                <Button variant="outline" className="border-slate-300 hover:bg-slate-50 rounded-sm h-12 px-8 text-base">
                  How it works
                </Button>
              </a>
            </div>
          </div>

          {/* Inbox preview card */}
          <div className="lg:col-span-5">
            <div className="bg-white border border-slate-200 shadow-sm p-6 font-mono text-sm">
              <div className="text-xs tracking-[0.2em] uppercase font-bold text-slate-500 mb-4">
                Sent · Today
              </div>
              <Row name="Ram Sharma" subject="Proposal for Q2 partnership" opened ago="2m ago" />
              <Row name="Priya Mehta" subject="Updated invoice attached" opened ago="14m ago" />
              <Row name="Anil Verma" subject="Re: Onboarding next steps" />
              <Row name="Neha Kapoor" subject="Quick question about deadline" />
              <div className="mt-6 pt-4 border-t border-slate-100 flex items-center justify-between">
                <span className="text-xs text-slate-500">Live tracking</span>
                <span className="flex items-center gap-1 text-xs font-medium text-[#10B981]">
                  <span className="w-2 h-2 bg-[#10B981] rounded-full animate-pulse" /> active
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="how" className="max-w-7xl mx-auto px-6 pb-32">
        <p className="text-xs tracking-[0.25em] uppercase font-bold text-slate-500 mb-4">How it works</p>
        <h2 className="text-3xl sm:text-5xl tracking-tight font-black mb-16 max-w-3xl">
          Three things you'll love.
        </h2>
        <div className="grid md:grid-cols-3 gap-6">
          <Feature
            icon={<CheckCheck className="w-6 h-6" />}
            title="Gray tick → Green tick"
            text="Every sent email gets a gray double-tick. The instant your recipient opens it, the tick turns green."
          />
          <Feature
            icon={<Bell className="w-6 h-6" />}
            title="Real-time notifications"
            text="A desktop notification fires the moment your email is opened. Know exactly who's engaged — and when."
          />
          <Feature
            icon={<Send className="w-6 h-6" />}
            title="Smart follow-ups"
            text="Recipient didn't reply? Schedule a custom follow-up that auto-sends after N days, right from Gmail."
          />
        </div>
      </section>

      {/* CTA */}
      <section className="bg-[#0A0A0A] text-white">
        <div className="max-w-7xl mx-auto px-6 py-24 grid md:grid-cols-2 gap-8 items-center">
          <div>
            <h2 className="text-3xl sm:text-5xl tracking-tight font-black leading-tight">
              Start tracking in<br />under 60 seconds.
            </h2>
          </div>
          <div className="md:text-right">
            <Link to={user ? "/dashboard" : "/login"} data-testid="footer-cta-btn">
              <Button className="bg-[#10B981] text-white hover:bg-emerald-600 rounded-sm h-12 px-8 text-base">
                Sign in with Google <Zap className="ml-2 w-4 h-4" />
              </Button>
            </Link>
          </div>
        </div>
      </section>

      <footer className="bg-[#0A0A0A] text-slate-400 border-t border-slate-800">
        <div className="max-w-7xl mx-auto px-6 py-8 text-xs flex justify-between">
          <span>© 2026 MailTrack</span>
          <span className="font-mono">v0.1 · MVP</span>
        </div>
      </footer>
    </div>
  );
}

function Row({ name, subject, opened, ago }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-slate-100 last:border-0">
      <div className="min-w-0">
        <div className="font-medium text-[#0A0A0A] truncate">{name}</div>
        <div className="text-xs text-slate-500 truncate">{subject}</div>
      </div>
      <div className="flex items-center gap-2 ml-3 shrink-0">
        {opened ? (
          <>
            <span className="text-[10px] text-slate-500">{ago}</span>
            <CheckCheck className="w-4 h-4 text-[#10B981]" strokeWidth={2.5} />
          </>
        ) : (
          <CheckCheck className="w-4 h-4 text-slate-300" strokeWidth={2.5} />
        )}
      </div>
    </div>
  );
}

function Feature({ icon, title, text }) {
  return (
    <div className="bg-white border border-slate-200 p-8 hover:shadow-md transition-shadow">
      <div className="w-10 h-10 bg-[#0A0A0A] text-white flex items-center justify-center mb-6">{icon}</div>
      <h3 className="text-xl font-bold tracking-tight mb-2">{title}</h3>
      <p className="text-sm text-slate-600 leading-relaxed">{text}</p>
    </div>
  );
}
