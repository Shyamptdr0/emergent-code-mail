import React from 'react';
import { Link } from 'react-router-dom';
import { CheckCheck, ArrowLeft } from 'lucide-react';
import { Button } from '../components/ui/button';

export default function Terms() {
  return (
    <div className="min-h-screen bg-[#F8F9FA] text-[#0A0A0A] font-sans">
      <header className="border-b border-slate-200 bg-white/80 backdrop-blur-xl sticky top-0 z-40">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2">
            <div className="w-8 h-8 bg-[#0A0A0A] flex items-center justify-center">
              <CheckCheck className="w-4 h-4 text-[#10B981]" strokeWidth={2.5} />
            </div>
            <span className="font-black tracking-tighter text-xl">MailTrack</span>
          </Link>
          <Link to="/">
            <Button variant="ghost" className="gap-2">
              <ArrowLeft className="w-4 h-4" /> Back to Home
            </Button>
          </Link>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-16">
        <h1 className="text-4xl font-black tracking-tight mb-8">Terms of Service</h1>
        <div className="prose prose-slate max-w-none space-y-6 text-slate-600">
          <p className="text-lg font-medium text-slate-900">Last Updated: May 8, 2026</p>
          
          <section>
            <h2 className="text-2xl font-bold text-slate-900 mb-4">1. Agreement to Terms</h2>
            <p>
              By accessing or using MailTrack, you agree to be bound by these Terms of Service. If you do not agree, please do not use our services.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-slate-900 mb-4">2. Description of Service</h2>
            <p>
              MailTrack provides email tracking and automation tools for Gmail. Our service includes tracking pixels, real-time notifications, and automated follow-up capabilities.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-slate-900 mb-4">3. User Responsibilities</h2>
            <p>
              You are responsible for your use of the service and for ensuring that your tracking activities comply with all applicable laws and regulations, including privacy laws in your jurisdiction.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-slate-900 mb-4">4. Limitation of Liability</h2>
            <p>
              MailTrack is provided "as is" without any warranties. We are not liable for any damages arising from your use of the service.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-slate-900 mb-4">5. Termination</h2>
            <p>
              We reserve the right to terminate or suspend your access to our service at any time, without prior notice, for any reason.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-slate-900 mb-4">6. Changes to Terms</h2>
            <p>
              We may update these Terms of Service from time to time. Your continued use of the service after changes are posted constitutes your acceptance of the new terms.
            </p>
          </section>
        </div>
      </main>

      <footer className="bg-[#0A0A0A] text-slate-400 border-t border-slate-800">
        <div className="max-w-4xl mx-auto px-6 py-8 text-xs flex justify-between">
          <span>© 2026 MailTrack</span>
          <div className="flex gap-4">
            <Link to="/privacy" className="hover:text-white">Privacy Policy</Link>
            <Link to="/terms" className="hover:text-white">Terms of Service</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
