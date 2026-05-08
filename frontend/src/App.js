import "./App.css";
import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider } from "@/lib/AuthContext";
import Landing from "@/pages/Landing";
import Login from "@/pages/Login";

import Dashboard from "@/pages/Dashboard";
import Emails from "@/pages/Emails";
import EmailDetail from "@/pages/EmailDetail";
import ActiveMails from "@/pages/ActiveMails";
import Automation from "@/pages/Automation";
import FollowUps from "@/pages/FollowUps";
import Settings from "@/pages/Settings";
import Privacy from "@/pages/Privacy";
import Terms from "@/pages/Terms";
import AppShell from "@/components/AppShell";

function AppRouter() {
  const location = useLocation();

  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/dashboard" element={<AppShell><Dashboard /></AppShell>} />
      <Route path="/emails" element={<AppShell><Emails /></AppShell>} />
      <Route path="/active-mails" element={<AppShell><ActiveMails /></AppShell>} />
      <Route path="/emails/:id" element={<AppShell><EmailDetail /></AppShell>} />
      <Route path="/automation" element={<AppShell><Automation /></AppShell>} />
      <Route path="/follow-ups" element={<AppShell><FollowUps /></AppShell>} />
      <Route path="/settings" element={<AppShell><Settings /></AppShell>} />
      <Route path="/privacy" element={<Privacy />} />
      <Route path="/terms" element={<Terms />} />
    </Routes>
  );
}

function App() {
  return (
    <div className="App">
      <AuthProvider>
        <BrowserRouter>
          <AppRouter />
          <Toaster position="top-right" richColors closeButton data-testid="toaster" />
        </BrowserRouter>
      </AuthProvider>
    </div>
  );
}

export default App;
