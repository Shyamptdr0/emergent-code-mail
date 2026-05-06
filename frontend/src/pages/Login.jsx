import { CheckCheck } from "lucide-react";
import { Button } from "../components/ui/button";
import { login } from "../lib/api";

export default function Login() {
  return (
    <div className="min-h-screen bg-[#F8F9FA] flex items-center justify-center px-4">
      <div className="bg-white border border-slate-200 max-w-md w-full p-10">
        <div className="w-12 h-12 bg-[#0A0A0A] flex items-center justify-center mb-8">
          <CheckCheck className="w-6 h-6 text-[#10B981]" strokeWidth={2.5} />
        </div>
        <h1 className="text-3xl font-black tracking-tighter mb-2">Sign in</h1>
        <p className="text-sm text-slate-600 mb-8">
          Use your Google account to start tracking emails.
        </p>
        <Button
          onClick={login}
          data-testid="google-login-btn"
          className="w-full bg-[#0A0A0A] text-white hover:bg-slate-800 rounded-sm h-12 text-base"
        >
          Continue with Google
        </Button>
        <p className="mt-6 text-xs text-slate-500 leading-relaxed font-mono">
          By signing in you agree to the terms. We never read your inbox.
        </p>
      </div>
    </div>
  );
}
