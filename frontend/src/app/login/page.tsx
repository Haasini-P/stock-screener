"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Brain, Eye, EyeOff, Shield, Sparkles, Zap } from "lucide-react";
import Link from "next/link";

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}

/** Only same-origin relative paths are allowed as post-login redirect targets. */
function safeNext(target: string | null): string {
  return target && target.startsWith("/") && !target.startsWith("//") ? target : "/";
}

function LoginForm() {
  const searchParams = useSearchParams();
  const next = safeNext(searchParams.get("next"));
  const notice = searchParams.get("expired") ? "Your session expired. Please sign in again." : "";
  const [isRegister, setIsRegister] = useState(searchParams.get("mode") === "register");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const { authAPI } = await import("@/lib/api");
      const { useAppStore } = await import("@/lib/store");

      let response;
      if (isRegister) {
        response = await authAPI.register(email, password, fullName || undefined);
      } else {
        response = await authAPI.login(email, password);
      }

      const data = response.data;
      useAppStore.getState().setUser(data.user, data.access_token);
      window.location.href = next;
    } catch (err: any) {
      const { errorMessage } = await import("@/lib/api");
      setError(errorMessage(err, "Authentication failed. Please try again."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="min-h-screen flex items-center justify-center px-4"
      style={{ background: "var(--bg-primary)" }}
    >
      {/* Background effects */}
      <div
        className="fixed inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse 60% 50% at 50% 30%, rgba(99, 102, 241, 0.12), transparent)",
        }}
      />

      <div className="w-full max-w-[420px] relative z-10">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8 animate-fade-in">
          <div
            className="w-14 h-14 rounded-2xl flex items-center justify-center mb-4"
            style={{
              background: "linear-gradient(135deg, var(--accent-indigo), #7c3aed)",
              boxShadow: "0 8px 30px rgba(99, 102, 241, 0.3)",
            }}
          >
            <Brain size={28} className="text-white" />
          </div>
          <h1 className="text-2xl font-bold gradient-text">StockMind AI</h1>
          <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
            Institutional-Grade Stock Intelligence
          </p>
        </div>

        {/* Form Card */}
        <div className="glass-card-static p-6 animate-fade-in" style={{ animationDelay: "0.1s" }}>
          <h2 className="text-lg font-bold mb-1" style={{ color: "var(--text-primary)" }}>
            {isRegister ? "Create Account" : "Welcome Back"}
          </h2>
          <p className="text-xs mb-5" style={{ color: "var(--text-muted)" }}>
            {isRegister
              ? "Set up your analyst dashboard"
              : "Sign in to access your intelligence platform"}
          </p>

          {notice && !error && (
            <div
              className="p-3 rounded-lg mb-4 text-xs"
              style={{ background: "var(--color-info-bg)", border: "1px solid rgba(59,130,246,0.25)", color: "var(--color-info)" }}
            >
              {notice}
            </div>
          )}

          {error && (
            <div
              className="p-3 rounded-lg mb-4 text-xs"
              style={{
                background: "var(--color-bearish-bg)",
                border: "1px solid var(--color-bearish-border)",
                color: "var(--color-bearish)",
              }}
            >
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="flex flex-col gap-3">
            {isRegister && (
              <div>
                <label className="text-xs font-medium mb-1 block" style={{ color: "var(--text-secondary)" }}>
                  Full Name
                </label>
                <input
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-lg text-sm outline-none"
                  style={{
                    background: "var(--bg-card)",
                    border: "1px solid var(--border-default)",
                    color: "var(--text-primary)",
                  }}
                  placeholder="Your name"
                />
              </div>
            )}

            <div>
              <label className="text-xs font-medium mb-1 block" style={{ color: "var(--text-secondary)" }}>
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full px-4 py-2.5 rounded-lg text-sm outline-none"
                style={{
                  background: "var(--bg-card)",
                  border: "1px solid var(--border-default)",
                  color: "var(--text-primary)",
                }}
                placeholder="analyst@example.com"
              />
            </div>

            <div>
              <label className="text-xs font-medium mb-1 block" style={{ color: "var(--text-secondary)" }}>
                Password
              </label>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={6}
                  className="w-full px-4 py-2.5 rounded-lg text-sm outline-none pr-10"
                  style={{
                    background: "var(--bg-card)",
                    border: "1px solid var(--border-default)",
                    color: "var(--text-primary)",
                  }}
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2"
                  style={{ color: "var(--text-muted)" }}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full mt-2"
              style={{ opacity: loading ? 0.7 : 1 }}
            >
              {loading ? (
                <span className="animate-pulse">Processing...</span>
              ) : isRegister ? (
                <>
                  <Sparkles size={16} /> Create Account
                </>
              ) : (
                <>
                  <Zap size={16} /> Sign In
                </>
              )}
            </button>
          </form>

          <div className="mt-4 text-center">
            <button
              onClick={() => {
                setIsRegister(!isRegister);
                setError("");
              }}
              className="text-xs font-medium"
              style={{ color: "var(--text-accent)" }}
            >
              {isRegister ? "Already have an account? Sign in" : "Don't have an account? Register"}
            </button>
          </div>
          <div className="mt-2 text-center">
            <Link href={next} className="text-xs" style={{ color: "var(--text-muted)" }}>
              Continue as guest →
            </Link>
          </div>
        </div>

        {/* Security Notice */}
        <div className="flex items-center justify-center gap-2 mt-4 animate-fade-in" style={{ animationDelay: "0.2s" }}>
          <Shield size={12} style={{ color: "var(--text-muted)" }} />
          <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>
            Upstox tokens encrypted at rest. Access tokens never sent to browser.
          </p>
        </div>
      </div>
    </div>
  );
}
