"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Bell, Brain, Copy, Database, KeyRound, Landmark, LogOut, Plus, RotateCw, Save, Server, ShieldCheck, SlidersHorizontal, Sparkles, Star, Trash2, User } from "lucide-react";
import {
  accountsAPI, aiSettingsAPI, AISettingsStatus, API_BASE_URL, BrokerAccount, BrokerCredentialStatus, brokerSettingsAPI,
  DevService, errorMessage, healthAPI, mlAPI, ModelVersionSummary, systemAPI,
} from "@/lib/api";
import { DEFAULT_SETTINGS, useAppStore } from "@/lib/store";
import { useApi } from "@/lib/useApi";
import { fmtINR, fmtNum, timeAgo } from "@/lib/format";
import { Card, EmptyState, ErrorState, KeyValue, LoadingRows, PageHeader, SectionHeader } from "../ui";

const TOKEN_STATUS: Record<string, { label: string; cls: string; help: string }> = {
  valid: { label: "Valid", cls: "badge-bullish", help: "Market data is flowing from Upstox." },
  invalid: { label: "Rejected", cls: "badge-bearish", help: "Upstox rejected the token — generate a new analytics token in the Upstox developer console and update UPSTOX_ANALYTICS_TOKEN in backend/.env." },
  not_configured: { label: "Missing", cls: "badge-bearish", help: "Set UPSTOX_ANALYTICS_TOKEN in backend/.env and restart the backend." },
  error: { label: "Error", cls: "badge-bearish", help: "Upstox could not be reached. Check network connectivity." },
};

export default function SettingsView() {
  const { settings, updateSettings, user, isAuthenticated, logout, toast } = useAppStore();
  // This view only renders client-side (tabs are chosen after hydration), so window is available
  const [notifPermission, setNotifPermission] = useState<string>(() =>
    typeof window !== "undefined" && "Notification" in window ? Notification.permission : "unsupported"
  );

  const system = useApi(() => healthAPI.system(), [isAuthenticated]);
  const ready = useApi(() => healthAPI.ready(), []);
  const [restarting, setRestarting] = useState<DevService | null>(null);

  const restartService = async (serviceToRestart: DevService) => {
    const label = { backend: "the backend", frontend: "the frontend", both: "both dev servers" }[serviceToRestart];
    if (!window.confirm(`Restart ${label}? This briefly interrupts any in-progress requests (and, for the frontend, this page itself).`)) return;
    setRestarting(serviceToRestart);
    try {
      await systemAPI.restart(serviceToRestart);
      toast(`Restarting ${label}… give it a few seconds.`, "info");
    } catch (err) {
      toast(errorMessage(err, `Could not restart ${label}.`), "error");
    } finally {
      setTimeout(() => setRestarting(null), 5000);
    }
  };

  const toggleNotifications = async () => {
    if (settings.browserNotifications) {
      updateSettings({ browserNotifications: false });
      return toast("Browser notifications turned off", "info");
    }
    if (!("Notification" in window)) return toast("This browser does not support notifications.", "error");
    const permission = await Notification.requestPermission();
    setNotifPermission(permission);
    if (permission === "granted") {
      updateSettings({ browserNotifications: true });
      new Notification("StockMind AI", { body: "Browser notifications enabled for triggered alerts." });
      toast("Browser notifications enabled", "success");
    } else {
      toast("Notification permission was denied in the browser.", "error");
    }
  };

  const token = TOKEN_STATUS[system.data?.analytics_token] || null;
  const checks = ready.data?.checks || {};

  return (
    <div className="space-y-5">
      <PageHeader title="Settings" subtitle="Account, data connections, risk framework and display preferences" />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Account */}
        <Card>
          <SectionHeader icon={<User size={16} />} title="Account" />
          {isAuthenticated && user ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <KeyValue label="Name" value={user.full_name || "—"} />
                <KeyValue label="Email" value={<span className="break-all">{user.email}</span>} />
              </div>
              <button className="btn-secondary text-xs" onClick={() => { logout(); toast("Signed out", "info"); }}>
                <LogOut size={13} /> Sign out
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
                You&apos;re browsing as a guest. Market data, scanner, signals and analysis all work without an account.
                Sign in to save alerts and connect your Upstox portfolio.
              </p>
              <div className="flex gap-2">
                <Link href="/login?next=%2F%23settings" className="btn-primary text-xs">Sign in</Link>
                <Link href="/login?mode=register&next=%2F%23settings" className="btn-secondary text-xs">Create account</Link>
              </div>
            </div>
          )}
        </Card>

        {/* Market data */}
        <Card>
          <SectionHeader icon={<KeyRound size={16} />} title="Market data" />
          {system.loading ? (
            <LoadingRows rows={2} />
          ) : system.error ? (
            <p className="text-xs" style={{ color: "var(--color-bearish)" }}>{system.error}</p>
          ) : (
            <div className="space-y-3 text-xs">
              <div className="flex items-center justify-between">
                <span style={{ color: "var(--text-secondary)" }}>Analytics token (market data)</span>
                {token && <span className={`badge ${token.cls}`}>{token.label}</span>}
              </div>
              {token && <p style={{ color: "var(--text-muted)" }}>{token.help}</p>}
            </div>
          )}
        </Card>

        {/* Broker app credentials */}
        <Card className="lg:col-span-2">
          <SectionHeader
            icon={<KeyRound size={16} />}
            title="Broker API Credentials"
            subtitle="The app-level Upstox/Kite developer credentials used to let any user connect their own account. Configure these here instead of editing backend/.env."
          />
          <BrokerCredentialsPanel isAuthenticated={isAuthenticated} onSaved={() => system.reload()} />
        </Card>

        {/* AI commentary */}
        <Card className="lg:col-span-2">
          <SectionHeader
            icon={<Sparkles size={16} />}
            title="AI Commentary (Claude API)"
            subtitle="Powers the on-demand “AI take” button on Scanner, Daily Signals and Stock Report using the prompt from the AI Prompt tab. Only called when you click it — never automatic."
          />
          <AICommentarySettingsPanel isAuthenticated={isAuthenticated} />
        </Card>

        {/* Linked broker accounts */}
        <Card className="lg:col-span-2">
          <SectionHeader
            icon={<Landmark size={16} />}
            title="Linked Accounts"
            subtitle="Buy/Sell orders from the Scanner and Stock Report route to whichever account is marked active."
          />
          <AccountsPanel isAuthenticated={isAuthenticated} kiteConfigured={!!system.data?.kite_configured} />
        </Card>

        {/* Model training */}
        <Card className="lg:col-span-2">
          <SectionHeader
            icon={<Brain size={16} />}
            title="Model Training"
            subtitle="Trains a real LightGBM model per horizon from historical candles. Training never auto-activates a model — you promote a challenger to champion explicitly once you've reviewed its metrics."
          />
          <ModelTrainingPanel isAuthenticated={isAuthenticated} />
        </Card>

        {/* Risk */}
        <Card>
          <SectionHeader icon={<ShieldCheck size={16} />} title="Portfolio & risk" subtitle="Used for position sizing and capital deployment" />
          <RiskForm key={`${settings.capital}:${settings.riskPct}`} />
        </Card>

        {/* Display & notifications */}
        <Card>
          <SectionHeader icon={<SlidersHorizontal size={16} />} title="Display & notifications" />
          <div className="space-y-4">
            <div>
              <label className="field-label" htmlFor="set-refresh">Auto-refresh live data</label>
              <select
                id="set-refresh"
                className="input"
                value={settings.refreshSec}
                onChange={(e) => {
                  updateSettings({ refreshSec: Number(e.target.value) });
                  toast("Refresh interval updated", "success");
                }}
              >
                <option value={30}>Every 30 seconds</option>
                <option value={60}>Every minute</option>
                <option value={300}>Every 5 minutes</option>
                <option value={0}>Off (manual refresh)</option>
              </select>
            </div>
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold flex items-center gap-1.5" style={{ color: "var(--text-primary)" }}><Bell size={13} /> Browser notifications</p>
                <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                  {notifPermission === "denied"
                    ? "Blocked in browser settings — allow notifications for this site to enable."
                    : notifPermission === "unsupported"
                    ? "Not supported by this browser."
                    : "Show a desktop notification when an alert triggers."}
                </p>
              </div>
              <button
                className={settings.browserNotifications ? "btn-secondary text-xs" : "btn-primary text-xs"}
                onClick={toggleNotifications}
                disabled={notifPermission === "denied" || notifPermission === "unsupported"}
              >
                {settings.browserNotifications ? "Turn off" : "Enable"}
              </button>
            </div>
          </div>
        </Card>

        {/* System */}
        <Card className="lg:col-span-2">
          <SectionHeader icon={<Server size={16} />} title="System status" subtitle={`Backend: ${API_BASE_URL}`} />
          {ready.loading ? (
            <LoadingRows rows={2} />
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
              {[
                // /ready reports "degraded" when only the optional Redis cache is down
                ["API", ready.error ? "offline" : checks.database === "connected" ? "online" : ready.data?.status || "unknown"],
                ["Database", checks.database],
                ["Redis cache", checks.redis?.startsWith("error") ? "not running (optional)" : checks.redis],
                ["Environment", system.data?.environment],
              ].map(([k, v]) => (
                <div key={k} className="flex items-center gap-2">
                  <Database size={13} style={{ color: "var(--text-muted)" }} />
                  <span style={{ color: "var(--text-muted)" }}>{k}:</span>
                  <span style={{ color: "var(--text-primary)" }}>{v || "—"}</span>
                </div>
              ))}
            </div>
          )}

          <div className="mt-4 pt-4" style={{ borderTop: "1px solid var(--border-subtle)" }}>
            <p className="text-xs mb-2" style={{ color: "var(--text-muted)" }}>
              Dev server restart — local only, kills and relaunches the process. Does nothing against a Docker Compose deployment.
            </p>
            <div className="flex flex-wrap gap-2">
              {([
                ["backend", "Restart backend"],
                ["frontend", "Restart frontend"],
                ["both", "Restart both"],
              ] as [DevService, string][]).map(([svc, label]) => (
                <button
                  key={svc}
                  className="btn-secondary text-xs"
                  style={{ padding: "6px 12px" }}
                  disabled={!!restarting}
                  onClick={() => restartService(svc)}
                >
                  <RotateCw size={13} className={restarting === svc ? "animate-spin" : ""} /> {restarting === svc ? "Restarting…" : label}
                </button>
              ))}
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}

const PROVIDER_LABEL: Record<string, string> = { upstox: "Upstox", kite: "Kite" };

const BROKER_FIELD_LABELS: Record<"upstox" | "kite", { id: string; secret: string }> = {
  upstox: { id: "Client ID", secret: "Client Secret" },
  kite: { id: "API Key", secret: "API Secret" },
};

function BrokerCredentialsPanel({ isAuthenticated, onSaved }: { isAuthenticated: boolean; onSaved: () => void }) {
  const status = useApi(() => brokerSettingsAPI.get(), [], { enabled: isAuthenticated });

  if (!isAuthenticated) {
    return (
      <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
        Sign in to configure broker app credentials.
      </p>
    );
  }

  if (status.loading) return <LoadingRows rows={4} />;
  if (status.error) return <ErrorState message={status.error} onRetry={status.reload} />;

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
      <BrokerCredentialForm
        key={`upstox:${status.data!.upstox.client_id}:${status.data!.upstox.redirect_uri}`}
        provider="upstox"
        current={status.data!.upstox}
        onSaved={() => {
          status.reload();
          onSaved();
        }}
      />
      <BrokerCredentialForm
        key={`kite:${status.data!.kite.client_id}:${status.data!.kite.redirect_uri}`}
        provider="kite"
        current={status.data!.kite}
        onSaved={() => {
          status.reload();
          onSaved();
        }}
      />
    </div>
  );
}

function BrokerCredentialForm({
  provider,
  current,
  onSaved,
}: {
  provider: "upstox" | "kite";
  current: BrokerCredentialStatus;
  onSaved: () => void;
}) {
  const { toast } = useAppStore();
  const labels = BROKER_FIELD_LABELS[provider];
  const [clientId, setClientId] = useState(current.client_id);
  const [clientSecret, setClientSecret] = useState("");
  const [redirectUri, setRedirectUri] = useState(current.redirect_uri);
  const [saving, setSaving] = useState(false);

  const copyRedirectUri = async () => {
    try {
      await navigator.clipboard.writeText(redirectUri);
      toast("Redirect URI copied", "success");
    } catch {
      toast("Could not copy — select and copy the field manually.", "error");
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!clientId.trim()) return toast(`Enter the ${labels.id}.`, "error");
    if (!redirectUri.trim()) return toast("Enter the redirect URI.", "error");
    setSaving(true);
    try {
      const payload = { client_id: clientId.trim(), client_secret: clientSecret || undefined, redirect_uri: redirectUri.trim() };
      if (provider === "upstox") await brokerSettingsAPI.updateUpstox(payload);
      else await brokerSettingsAPI.updateKite(payload);
      toast(`${PROVIDER_LABEL[provider]} credentials saved`, "success");
      onSaved();
    } catch (err) {
      toast(errorMessage(err, `Could not save ${PROVIDER_LABEL[provider]} credentials.`), "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-3 p-3 rounded-lg" style={{ border: "1px solid var(--border-subtle)" }}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>{PROVIDER_LABEL[provider]}</span>
        <span className={`badge ${current.configured ? "badge-bullish" : "badge-neutral"}`}>
          {current.configured ? "Configured" : "Not configured"}
        </span>
      </div>
      <div>
        <label className="field-label">{labels.id}</label>
        <input className="input text-xs" value={clientId} onChange={(e) => setClientId(e.target.value)} />
      </div>
      <div>
        <label className="field-label">{labels.secret}</label>
        <input
          className="input text-xs"
          type="password"
          value={clientSecret}
          onChange={(e) => setClientSecret(e.target.value)}
          placeholder={current.has_secret ? "•••••••• (unchanged)" : "Not set"}
          autoComplete="new-password"
        />
      </div>
      <div>
        <label className="field-label">Redirect URI</label>
        <div className="flex gap-1.5">
          <input className="input text-xs font-mono" value={redirectUri} onChange={(e) => setRedirectUri(e.target.value)} />
          <button type="button" className="btn-ghost text-xs shrink-0" onClick={copyRedirectUri} title="Copy redirect URI">
            <Copy size={13} />
          </button>
        </div>
        <p className="text-[10px] mt-1" style={{ color: "var(--text-muted)" }}>
          Must be copied character-for-character into the &ldquo;Redirect URI&rdquo; field of your{" "}
          {PROVIDER_LABEL[provider]} developer app — a protocol, port, path or trailing-slash
          mismatch here is the #1 cause of a &ldquo;client_id and redirect_uri&rdquo; / invalid-config
          error from {PROVIDER_LABEL[provider]} when connecting.
        </p>
      </div>
      <button type="submit" className="btn-primary text-xs" disabled={saving}>
        <Save size={13} /> {saving ? "Saving…" : "Save"}
      </button>
    </form>
  );
}

function AICommentarySettingsPanel({ isAuthenticated }: { isAuthenticated: boolean }) {
  const { toast } = useAppStore();
  const status = useApi(() => aiSettingsAPI.get(), [], { enabled: isAuthenticated });

  if (!isAuthenticated) {
    return <p className="text-xs" style={{ color: "var(--text-secondary)" }}>Sign in to configure AI commentary.</p>;
  }
  if (status.loading) return <LoadingRows rows={3} />;
  if (status.error) return <ErrorState message={status.error} onRetry={status.reload} />;

  return (
    <AICommentaryForm
      key={`${status.data!.model}:${status.data!.has_key}`}
      current={status.data!}
      onSaved={() => {
        status.reload();
        toast("AI commentary settings saved", "success");
      }}
    />
  );
}

function AICommentaryForm({ current, onSaved }: { current: AISettingsStatus; onSaved: () => void }) {
  const { toast } = useAppStore();
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState(current.model);
  const [saving, setSaving] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await aiSettingsAPI.update({ api_key: apiKey || undefined, model });
      setApiKey("");
      onSaved();
    } catch (err) {
      toast(errorMessage(err, "Could not save AI commentary settings."), "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-3 max-w-md">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>Claude API</span>
        <span className={`badge ${current.configured ? "badge-bullish" : "badge-neutral"}`}>
          {current.configured ? "Configured" : "Not configured"}
        </span>
      </div>
      <div>
        <label className="field-label">API Key</label>
        <input
          className="input text-xs"
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder={current.has_key ? "•••••••• (unchanged)" : "sk-ant-..."}
          autoComplete="new-password"
        />
      </div>
      <div>
        <label className="field-label">Model</label>
        <select className="input text-xs" value={model} onChange={(e) => setModel(e.target.value)}>
          {Object.entries(current.pricing).map(([id, price]) => (
            <option key={id} value={id}>
              {id} — ${price.input.toFixed(2)} in / ${price.output.toFixed(2)} out per 1M tokens
            </option>
          ))}
        </select>
        <p className="text-[10px] mt-1" style={{ color: "var(--text-muted)" }}>
          Each click of &ldquo;AI take&rdquo; on an uncached stock costs roughly one request at this
          model&rsquo;s rate — results are cached per stock per day, so revisiting doesn&rsquo;t re-bill.
        </p>
      </div>
      <button type="submit" className="btn-primary text-xs" disabled={saving}>
        <Save size={13} /> {saving ? "Saving…" : "Save"}
      </button>
    </form>
  );
}

function AccountsPanel({ isAuthenticated, kiteConfigured }: { isAuthenticated: boolean; kiteConfigured: boolean }) {
  const { toast } = useAppStore();
  const accounts = useApi(() => accountsAPI.list(), [isAuthenticated], { enabled: isAuthenticated });
  const [connecting, setConnecting] = useState<"upstox" | "kite" | null>(null);
  const [nickname, setNickname] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  if (!isAuthenticated) {
    return (
      <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
        Sign in to link an Upstox or Kite account for live order placement.
      </p>
    );
  }

  const startConnect = async (provider: "upstox" | "kite") => {
    setConnecting(provider);
    try {
      const res = provider === "upstox" ? await accountsAPI.connectUpstox(nickname || undefined) : await accountsAPI.connectKite(nickname || undefined);
      window.location.href = res.data.authorization_url;
    } catch (err) {
      toast(errorMessage(err, `Could not start the ${PROVIDER_LABEL[provider]} connect flow.`), "error");
      setConnecting(null);
    }
  };

  const activate = async (id: string) => {
    setBusyId(id);
    try {
      await accountsAPI.activate(id);
      toast("Active account updated", "success");
      accounts.reload();
    } catch (err) {
      toast(errorMessage(err, "Could not activate this account."), "error");
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (id: string, label: string) => {
    if (!window.confirm(`Disconnect ${label}? You'll need to reconnect it to trade from this account again.`)) return;
    setBusyId(id);
    try {
      await accountsAPI.remove(id);
      toast(`${label} disconnected`, "success");
      accounts.reload();
    } catch (err) {
      toast(errorMessage(err, "Could not disconnect this account."), "error");
    } finally {
      setBusyId(null);
    }
  };

  const list: BrokerAccount[] = accounts.data || [];

  return (
    <div className="space-y-4">
      {accounts.loading ? (
        <LoadingRows rows={3} />
      ) : accounts.error ? (
        <ErrorState message={accounts.error} onRetry={accounts.reload} />
      ) : list.length === 0 ? (
        <EmptyState icon={<Landmark size={24} />} title="No broker accounts linked" description="Link an account to place live Buy/Sell orders from the Scanner and Stock Report." />
      ) : (
        <div className="space-y-2">
          {list.map((a) => {
            const label = a.nickname || `${PROVIDER_LABEL[a.provider]} account`;
            return (
              <div
                key={a.id}
                className="flex items-center justify-between gap-3 p-3 rounded-lg text-xs"
                style={{ background: "rgba(255,255,255,0.02)", border: "1px solid var(--border-subtle)" }}
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold" style={{ color: "var(--text-primary)" }}>{label}</span>
                    <span className="badge badge-neutral">{PROVIDER_LABEL[a.provider]}</span>
                    {a.is_active && <span className="badge badge-bullish"><Star size={10} /> Active</span>}
                  </div>
                  <p style={{ color: "var(--text-muted)" }}>
                    {a.account_user_name || a.account_email || "—"} ·{" "}
                    <span className={a.is_connected ? "text-bullish" : "text-bearish"}>{a.is_connected ? "Connected" : "Disconnected"}</span>
                    {a.provider === "kite" && " · Kite sessions expire daily — reconnect each morning"}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {!a.is_active && a.is_connected && (
                    <button className="btn-ghost text-xs" disabled={busyId === a.id} onClick={() => activate(a.id)}>
                      Make active
                    </button>
                  )}
                  <button className="btn-ghost text-xs" style={{ color: "var(--color-bearish)" }} disabled={busyId === a.id} onClick={() => remove(a.id, label)}>
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="pt-2 border-t space-y-2" style={{ borderColor: "var(--border-subtle)" }}>
        <input
          className="input text-xs"
          placeholder="Nickname for the next account you link (optional)"
          value={nickname}
          onChange={(e) => setNickname(e.target.value)}
          maxLength={100}
        />
        <div className="flex flex-wrap gap-2">
          <button className="btn-secondary text-xs" onClick={() => startConnect("upstox")} disabled={!!connecting}>
            <Plus size={13} /> Connect Upstox account
          </button>
          <button
            className="btn-secondary text-xs"
            onClick={() => startConnect("kite")}
            disabled={!kiteConfigured || !!connecting}
            title={kiteConfigured ? undefined : "Set KITE_API_KEY and KITE_API_SECRET in backend/.env first"}
          >
            <Plus size={13} /> Connect Kite account
          </button>
        </div>
        {connecting && <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>Redirecting to {PROVIDER_LABEL[connecting]}…</p>}
      </div>
    </div>
  );
}

const STATUS_BADGE: Record<string, string> = {
  champion: "badge-bullish",
  challenger: "badge-accent",
  training: "badge-neutral",
  validating: "badge-neutral",
  retired: "badge-neutral",
};

function ModelTrainingPanel({ isAuthenticated }: { isAuthenticated: boolean }) {
  const { toast } = useAppStore();
  const models = useApi(() => mlAPI.listModels(), [], { enabled: isAuthenticated });
  const [training, setTraining] = useState<{ runId: string; status: string } | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  if (!isAuthenticated) {
    return <p className="text-xs" style={{ color: "var(--text-secondary)" }}>Sign in to train or promote models.</p>;
  }

  const startTraining = async () => {
    try {
      const res = await mlAPI.train();
      setTraining({ runId: res.data.run_id, status: "running" });
      toast("Training started — this can take a while for the full universe.", "info");
      pollRef.current = setInterval(async () => {
        try {
          const run = await mlAPI.getRun(res.data.run_id);
          if (run.data.status !== "running") {
            if (pollRef.current) clearInterval(pollRef.current);
            setTraining({ runId: res.data.run_id, status: run.data.status });
            if (run.data.status === "completed") {
              toast(`Training completed — avg accuracy ${((run.data.metrics?.avg_accuracy || 0) * 100).toFixed(1)}%`, "success");
            } else {
              toast(run.data.error_message || "Training failed.", "error");
            }
            models.reload();
          }
        } catch {
          // transient poll failure — keep trying until the interval naturally stops
        }
      }, 5000);
    } catch (err) {
      toast(errorMessage(err, "Could not start training."), "error");
    }
  };

  const promote = async (id: string) => {
    try {
      await mlAPI.promote(id);
      toast("Model promoted to champion", "success");
      models.reload();
    } catch (err) {
      toast(errorMessage(err, "Could not promote this model."), "error");
    }
  };

  const rows: ModelVersionSummary[] = models.data || [];
  const champion = rows.find((m) => m.is_champion);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-xs" style={{ color: "var(--text-secondary)" }}>
          {champion ? (
            <span>
              Live champion: <strong style={{ color: "var(--text-primary)" }}>{champion.version}</strong> · accuracy{" "}
              {fmtNum((champion.accuracy || 0) * 100, 1)}% · promoted {timeAgo(champion.promoted_at)}
            </span>
          ) : (
            <span>No champion promoted yet — predictions use the statistical baseline.</span>
          )}
        </div>
        <button className="btn-primary text-xs" onClick={startTraining} disabled={!!training && training.status === "running"}>
          <Brain size={13} /> {training?.status === "running" ? "Training…" : "Train new model"}
        </button>
      </div>

      {models.loading ? (
        <LoadingRows rows={2} />
      ) : models.error ? (
        <ErrorState message={models.error} onRetry={models.reload} />
      ) : rows.length === 0 ? (
        <EmptyState icon={<Brain size={24} />} title="No training runs yet" description="Click “Train new model” to run the pipeline on the approved universe." />
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead><tr><th>Version</th><th>Status</th><th>Accuracy</th><th>Log loss</th><th>Trained</th><th></th></tr></thead>
            <tbody>
              {rows.map((m) => (
                <tr key={m.id}>
                  <td className="text-xs font-mono">{m.version}</td>
                  <td><span className={`badge ${STATUS_BADGE[m.status] || "badge-neutral"}`}>{m.status}</span></td>
                  <td className="tabular-nums">{m.accuracy != null ? `${fmtNum(m.accuracy * 100, 1)}%` : "—"}</td>
                  <td className="tabular-nums">{m.log_loss_score != null ? fmtNum(m.log_loss_score, 2) : "—"}</td>
                  <td className="text-xs">{timeAgo(m.created_at)}</td>
                  <td>
                    {m.status === "challenger" && (
                      <button className="btn-ghost text-xs" onClick={() => promote(m.id)}>Promote</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function RiskForm() {
  const { settings, updateSettings, toast } = useAppStore();
  const [capital, setCapital] = useState(String(settings.capital));
  const [riskPct, setRiskPct] = useState(String(settings.riskPct));

  const saveRisk = (e: React.FormEvent) => {
    e.preventDefault();
    const c = parseFloat(capital);
    const r = parseFloat(riskPct);
    if (!(c >= 10000)) return toast("Capital must be at least ₹10,000.", "error");
    if (!(r > 0 && r <= 5)) return toast("Risk per trade must be between 0 and 5%.", "error");
    updateSettings({ capital: c, riskPct: r });
    toast("Risk settings saved — signals and position sizes will update.", "success");
  };

  return (
    <form onSubmit={saveRisk} className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="field-label" htmlFor="set-capital">Capital (₹)</label>
          <input id="set-capital" className="input" type="number" min={10000} step={1000} value={capital} onChange={(e) => setCapital(e.target.value)} />
        </div>
        <div>
          <label className="field-label" htmlFor="set-risk">Risk per trade (%)</label>
          <input id="set-risk" className="input" type="number" min={0.1} max={5} step={0.05} value={riskPct} onChange={(e) => setRiskPct(e.target.value)} />
        </div>
      </div>
      <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
        Max loss per trade: {fmtINR(((parseFloat(capital) || 0) * (parseFloat(riskPct) || 0)) / 100, 0)}. High-conviction setups size at 1.33× and low-quality at 0.67× of this.
      </p>
      <div className="flex gap-2">
        <button type="submit" className="btn-primary text-xs"><Save size={13} /> Save</button>
        <button
          type="button"
          className="btn-ghost text-xs"
          onClick={() => {
            updateSettings({ capital: DEFAULT_SETTINGS.capital, riskPct: DEFAULT_SETTINGS.riskPct });
            toast("Risk settings reset to defaults", "info");
          }}
        >
          Reset to defaults
        </button>
      </div>
    </form>
  );
}
