import "@/App.css";
import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider } from "@/lib/AuthContext";
import Landing from "@/pages/Landing";
import Login from "@/pages/Login";
import AuthCallback from "@/pages/AuthCallback";
import Dashboard from "@/pages/Dashboard";
import Emails from "@/pages/Emails";
import EmailDetail from "@/pages/EmailDetail";
import FollowUps from "@/pages/FollowUps";
import Settings from "@/pages/Settings";
import AppShell from "@/components/AppShell";

function AppRouter() {
  const location = useLocation();
  if (location.hash?.includes("session_id=")) {
    return <AuthCallback />;
  }
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/dashboard" element={<AppShell><Dashboard /></AppShell>} />
      <Route path="/emails" element={<AppShell><Emails /></AppShell>} />
      <Route path="/emails/:id" element={<AppShell><EmailDetail /></AppShell>} />
      <Route path="/follow-ups" element={<AppShell><FollowUps /></AppShell>} />
      <Route path="/settings" element={<AppShell><Settings /></AppShell>} />
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
