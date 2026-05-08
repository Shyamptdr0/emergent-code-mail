import React from 'react';
import { Link } from 'react-router-dom';
import { CheckCheck, ArrowLeft } from 'lucide-react';
import { Button } from '../components/ui/button';

export default function Privacy() {
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
        <h1 className="text-4xl font-black tracking-tight mb-8">Privacy Policy</h1>
        <div className="prose prose-slate max-w-none space-y-6 text-slate-600">
          <p className="text-lg font-medium text-slate-900">Last Updated: May 8, 2026</p>
          
          <section>
            <h2 className="text-2xl font-bold text-slate-900 mb-4">1. Introduction</h2>
            <p>
              MailTrack ("we", "our", or "us") is committed to protecting your privacy. This Privacy Policy explains how we collect, use, and safeguard your information when you use our Gmail extension and website.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-slate-900 mb-4">2. Information We Collect</h2>
            <p>
              <strong>Email Tracking Data:</strong> We use a small, transparent tracking pixel embedded in your sent emails to notify you when they are opened. We collect the time of the open, the recipient's approximate location (via IP address), and the device type used.
            </p>
            <p>
              <strong>Account Information:</strong> When you sign in with Google, we collect your name and email address to provide our services.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-slate-900 mb-4">3. How We Use Your Information</h2>
            <p>
              We use the collected data exclusively to:
            </p>
            <ul className="list-disc pl-6 space-y-2">
              <li>Provide real-time email open notifications.</li>
              <li>Maintain your dashboard and history.</li>
              <li>Improve our services and user experience.</li>
            </ul>
            <p>
              <strong>We NEVER access your personal email content, read your messages, or sell your data to third parties.</strong>
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-slate-900 mb-4">4. Google OAuth</h2>
            <p>
              MailTrack's use and transfer to any other app of information received from Google APIs will adhere to <a href="https://developers.google.com/terms/api-services-user-data-policy#additional_requirements_for_specific_api_scopes" className="text-[#10B981] hover:underline" target="_blank" rel="noopener noreferrer">Google API Service User Data Policy</a>, including the Limited Use requirements.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-slate-900 mb-4">5. Contact Us</h2>
            <p>
              If you have any questions about this Privacy Policy, please contact us at support@tracker-mail.online.
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
