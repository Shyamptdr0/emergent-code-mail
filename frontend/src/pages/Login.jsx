import { CheckCheck } from "lucide-react";
import { useGoogleLogin } from "@react-oauth/google";
import { api } from "../lib/api";
import { useAuth } from "../lib/AuthContext";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import axios from "axios";

export default function Login() {
  const { setUser } = useAuth();
  const navigate = useNavigate();

  const login = useGoogleLogin({
    flow: "auth-code",
    scope: "https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.insert https://www.googleapis.com/auth/gmail.settings.basic https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.labels https://www.googleapis.com/auth/gmail.addons.current.action.compose https://www.googleapis.com/auth/gmail.addons.current.message.readonly",
    prompt: "consent",
    onSuccess: async (codeResponse) => {
      try {
        const { data } = await api.post("/auth/google-native", {
          code: codeResponse.code
        });
        setUser(data);
        navigate("/dashboard", { replace: true, state: { user: data } });
      } catch (e) {
        toast.error("Login failed. Please try again.");
      }
    },
  });

  return (
    <div className="min-h-screen bg-[#F8F9FA] flex items-center justify-center px-4 relative overflow-hidden">
      {/* Subtle background decoration */}
      <div className="absolute top-0 left-0 w-full h-full overflow-hidden pointer-events-none">
        <div className="absolute -top-[10%] -left-[10%] w-[40%] h-[40%] rounded-full bg-[#10B981]/5 blur-[120px]" />
        <div className="absolute -bottom-[10%] -right-[10%] w-[40%] h-[40%] rounded-full bg-black/5 blur-[120px]" />
      </div>

      <div className="max-w-[440px] w-full z-10">
        <div className="bg-white border border-slate-200 shadow-[0_8px_30px_rgb(0,0,0,0.04)] p-8 sm:p-12 rounded-2xl">
          <div className="flex flex-col items-center text-center mb-10">
            <div className="w-14 h-14 bg-[#0A0A0A] rounded-2xl flex items-center justify-center mb-6 shadow-lg shadow-black/10">
              <CheckCheck className="w-7 h-7 text-[#10B981]" strokeWidth={3} />
            </div>
            <h1 className="text-3xl font-black tracking-tight text-slate-900 mb-3">Welcome to MailTrack</h1>
            <p className="text-slate-500 text-[15px] leading-relaxed max-w-[280px]">
              High-precision email tracking for professional communicators.
            </p>
          </div>

          <div className="space-y-6">
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <span className="w-full border-t border-slate-100"></span>
              </div>
              <div className="relative flex justify-center text-xs uppercase">
                <span className="bg-white px-4 text-slate-400 tracking-widest font-bold">Secure Access</span>
              </div>
            </div>

            <button
              onClick={() => login()}
              className="w-full flex items-center justify-center gap-4 bg-black hover:bg-slate-900 py-4 px-8 rounded-full transition-all duration-200 shadow-lg shadow-black/10 group"
            >
              <div className="bg-white p-1 rounded-full flex items-center justify-center">
                <svg className="w-5 h-5" viewBox="0 0 24 24">
                  <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
                  <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                  <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05" />
                  <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
                </svg>
              </div>
              <span className="text-base font-bold text-white">
                Continue with Google
              </span>
            </button>

            <div className="bg-slate-50 rounded-xl p-4 border border-slate-100">
              <p className="text-[11px] text-slate-500 leading-normal text-center font-medium">
                We value your privacy. MailTrack only monitors opens via tracking pixels and never accesses your personal email content.
              </p>
            </div>
          </div>
        </div>

        <p className="mt-8 text-center text-xs text-slate-400 font-medium tracking-wide uppercase">
          Trusted by 5,000+ professionals
        </p>
      </div>
    </div>
  );
}


