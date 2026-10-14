"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";

const API = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

type User = { id: string; email: string; created_at: string };
type TokenResponse = { access_token: string; token_type: string; expires_in: number; user: User };
type Organization = { id: string; name: string; slug: string; plan: string; role?: string; created_at: string };
type Deployment = { id: string; service_id: string; status: string; output_url?: string | null; error_message?: string | null; created_at: string };
type Service = { id: string; project_id: string; name: string; slug: string; kind: string; runtime: string; status: string; source_repo?: string | null; branch?: string; image_ref?: string | null; internal_port: number; memory_mb: number; cpu_millicores: number; deploy_token?: string | null; latest_deployment?: Deployment | null; created_at: string };
type Project = { id: string; organization_id: string; name: string; slug: string; description?: string | null; created_at: string; updated_at?: string; services?: Service[] };
type Log = { id: string; level: string; message: string; created_at: string };
type Usage = { projects: number; services: number; deployments_last_30_days: number; configured_memory_mb: number; configured_cpu_millicores: number; deployment_driver: string };
type EnvVar = { key: string; value: string; is_secret: boolean };
type DashboardOverview = { organization: Organization; projects: Project[]; usage: Usage; recent_deployments: Deployment[] };

async function request<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers || {})
    },
    cache: "no-store"
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const data = await response.json();
      message = typeof data.detail === "string" ? data.detail : message;
    } catch { /* Non-JSON error */ }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function timeAgo(date?: string) {
  if (!date) return "Not deployed";
  const ms = Math.max(0, Date.now() - new Date(date).getTime());
  if (ms < 60000) return "Just now";
  if (ms < 3600000) return `${Math.floor(ms / 60000)}m ago`;
  if (ms < 86400000) return `${Math.floor(ms / 3600000)}h ago`;
  return `${Math.floor(ms / 86400000)}d ago`;
}

const initial = (email: string) => email.slice(0, 1).toUpperCase();

export default function HomePage() {
  const [token, setToken] = useState<string>(() => {
    if (typeof window !== "undefined") {
      return window.sessionStorage.getItem("ssc_access_token") || "";
    }
    return "";
  });
  const [user, setUser] = useState<User | null>(() => {
    if (typeof window !== "undefined") {
      const savedUser = window.sessionStorage.getItem("ssc_user");
      if (savedUser) {
        try {
          return JSON.parse(savedUser) as User;
        } catch {
          window.sessionStorage.clear();
        }
      }
    }
    return null;
  });
  const [authMode, setAuthMode] = useState<"login" | "register">("register");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [orgName, setOrgName] = useState("");

  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [activeOrgId, setActiveOrgId] = useState<string>("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [recentDeployments, setRecentDeployments] = useState<Deployment[]>([]);
  const [logs, setLogs] = useState<Log[]>([]);
  const [activeDeployment, setActiveDeployment] = useState("");
  const [isLiveStreaming, setIsLiveStreaming] = useState(false);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [activeView, setActiveView] = useState<"overview" | "projects" | "activity" | "settings">("overview");

  // Modals state
  const [showOrgForm, setShowOrgForm] = useState(false);
  const [newOrgName, setNewOrgName] = useState("");

  const [showProjectForm, setShowProjectForm] = useState(false);
  const [editingProject, setEditingProject] = useState<Project | null>(null);
  const [projectName, setProjectName] = useState("");
  const [projectDescription, setProjectDescription] = useState("");

  const [showServiceFor, setShowServiceFor] = useState("");
  const [editingService, setEditingService] = useState<Service | null>(null);
  const [serviceName, setServiceName] = useState("");
  const [serviceRepo, setServiceRepo] = useState("");
  const [serviceBranch, setServiceBranch] = useState("main");
  const [serviceRuntime, setServiceRuntime] = useState("python");

  const [envModalService, setEnvModalService] = useState<Service | null>(null);
  const [envVars, setEnvVars] = useState<EnvVar[]>([]);
  const [newEnvKey, setNewEnvKey] = useState("");
  const [newEnvVal, setNewEnvVal] = useState("");
  const [newEnvSecret, setNewEnvSecret] = useState(false);
  const [envTab, setEnvTab] = useState<"list" | "raw">("list");
  const [rawEnvText, setRawEnvText] = useState("");
  const [rawEnvMerge, setRawEnvMerge] = useState(false);

  const [webhookModalService, setWebhookModalService] = useState<Service | null>(null);
  const [runtimeLogsService, setRuntimeLogsService] = useState<Service | null>(null);
  const [runtimeLogs, setRuntimeLogs] = useState<string[]>([]);

  const activeOrg = useMemo(() => {
    return organizations.find(o => o.id === activeOrgId) || organizations[0] || null;
  }, [organizations, activeOrgId]);

  const allServices = useMemo(() => {
    return projects.flatMap(p => p.services || []);
  }, [projects]);

  const healthyServices = useMemo(() => {
    return allServices.filter(s => s.status === "healthy").length;
  }, [allServices]);

  // Load Dashboard via Composite Endpoint (1 Request)
  const loadDashboard = useCallback(async (authToken: string, orgId?: string) => {
    try {
      const orgParam = orgId ? `?organization_id=${orgId}` : "";
      const overview = await request<DashboardOverview>(`/v1/dashboard/overview${orgParam}`, authToken);
      setProjects(overview.projects);
      setUsage(overview.usage);
      setRecentDeployments(overview.recent_deployments);

      // Load organizations list for switcher
      const orgs = await request<Organization[]>("/v1/organizations", authToken);
      setOrganizations(orgs);
      if (!orgId && overview.organization) {
        setActiveOrgId(overview.organization.id);
      }
    } catch (e) {
      throw e;
    }
  }, []);

  useEffect(() => {
    if (!token || !user) return;
    let cancelled = false;
    void (async () => {
      try {
        await loadDashboard(token, activeOrgId);
      } catch (e: unknown) {
        if (!cancelled && e instanceof Error) {
          setError(e.message);
        }
      }
    })();
    return () => { cancelled = true; };
  }, [token, user, activeOrgId, loadDashboard]);

  async function handleAuth(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      const result = await request<TokenResponse>(
        `/v1/auth/${authMode === "register" ? "register" : "login"}`,
        "",
        {
          method: "POST",
          body: JSON.stringify(authMode === "register" ? { email, password, organization_name: orgName || undefined } : { email, password })
        }
      );
      window.sessionStorage.setItem("ssc_access_token", result.access_token);
      window.sessionStorage.setItem("ssc_user", JSON.stringify(result.user));
      setToken(result.access_token);
      setUser(result.user);
      setNotice("You are signed in.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not sign in");
    } finally {
      setBusy(false);
    }
  }

  function signOut() {
    window.sessionStorage.removeItem("ssc_access_token");
    window.sessionStorage.removeItem("ssc_user");
    setToken("");
    setUser(null);
    setOrganizations([]);
    setActiveOrgId("");
    setProjects([]);
    setUsage(null);
    setRecentDeployments([]);
    setLogs([]);
    setNotice("");
    setError("");
  }

  // Workspace / Organization
  async function createWorkspace(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError("");
    try {
      const org = await request<Organization>("/v1/organizations", token, {
        method: "POST",
        body: JSON.stringify({ name: newOrgName })
      });
      setNewOrgName("");
      setShowOrgForm(false);
      setActiveOrgId(org.id);
      setNotice(`Workspace '${org.name}' created.`);
      await loadDashboard(token, org.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create workspace");
    } finally {
      setBusy(false);
    }
  }

  // Projects CRUD
  async function saveProject(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError("");
    try {
      if (editingProject) {
        await request<Project>(`/v1/projects/${editingProject.id}`, token, {
          method: "PATCH",
          body: JSON.stringify({ name: projectName, description: projectDescription || null })
        });
        setNotice("Project updated.");
      } else {
        await request<Project>("/v1/projects", token, {
          method: "POST",
          body: JSON.stringify({ name: projectName, description: projectDescription || null, organization_id: activeOrgId || undefined })
        });
        setNotice("Project created.");
      }
      setProjectName("");
      setProjectDescription("");
      setShowProjectForm(false);
      setEditingProject(null);
      await loadDashboard(token, activeOrgId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save project");
    } finally {
      setBusy(false);
    }
  }

  async function deleteProject(project: Project) {
    if (!confirm(`Are you sure you want to delete project '${project.name}' and all its services?`)) return;
    setBusy(true); setError("");
    try {
      await request(`/v1/projects/${project.id}`, token, { method: "DELETE" });
      setNotice(`Project '${project.name}' deleted.`);
      await loadDashboard(token, activeOrgId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not delete project");
    } finally {
      setBusy(false);
    }
  }

  // Services CRUD
  async function saveService(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError("");
    try {
      if (editingService) {
        await request<Service>(`/v1/services/${editingService.id}`, token, {
          method: "PATCH",
          body: JSON.stringify({ name: serviceName, branch: serviceBranch, source_repo: serviceRepo })
        });
        setNotice("Service updated.");
      } else {
        if (!showServiceFor) return;
        const payload = {
          name: serviceName,
          runtime: serviceRuntime,
          kind: "web",
          source_repo: serviceRepo,
          branch: serviceBranch || "main",
          internal_port: serviceRuntime === "node" ? 3000 : 8000
        };
        await request<Service>(`/v1/projects/${showServiceFor}/services`, token, {
          method: "POST",
          body: JSON.stringify(payload)
        });
        setNotice("Service created. Trigger a deployment or use the Deploy Hook.");
      }
      setServiceName("");
      setServiceRepo("");
      setServiceBranch("main");
      setShowServiceFor("");
      setEditingService(null);
      await loadDashboard(token, activeOrgId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save service");
    } finally {
      setBusy(false);
    }
  }

  async function deleteService(service: Service) {
    if (!confirm(`Are you sure you want to delete service '${service.name}'?`)) return;
    setBusy(true); setError("");
    try {
      await request(`/v1/services/${service.id}`, token, { method: "DELETE" });
      setNotice(`Service '${service.name}' deleted.`);
      await loadDashboard(token, activeOrgId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not delete service");
    } finally {
      setBusy(false);
    }
  }

  // Environment Variables Manager
  async function openEnvModal(service: Service) {
    setEnvModalService(service);
    try {
      const vars = await request<EnvVar[]>(`/v1/services/${service.id}/env?reveal=true`, token);
      setEnvVars(vars);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load environment variables");
    }
  }

  async function addEnvVar() {
    if (!newEnvKey.trim()) return;
    const updated = [...envVars.filter(v => v.key !== newEnvKey.trim()), { key: newEnvKey.trim(), value: newEnvVal, is_secret: newEnvSecret }];
    setEnvVars(updated);
    setNewEnvKey("");
    setNewEnvVal("");
    setNewEnvSecret(false);
  }

  function removeEnvVar(key: string) {
    setEnvVars(envVars.filter(v => v.key !== key));
  }

  async function saveEnvVars() {
    if (!envModalService) return;
    setBusy(true); setError("");
    try {
      await request(`/v1/services/${envModalService.id}/env`, token, {
        method: "PUT",
        body: JSON.stringify({ variables: envVars })
      });
      setNotice("Environment variables updated.");
      setEnvModalService(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save environment variables");
    } finally {
      setBusy(false);
    }
  }

  async function importRawEnv() {
    if (!envModalService || !rawEnvText.trim()) return;
    setBusy(true); setError("");
    try {
      const vars = await request<EnvVar[]>(`/v1/services/${envModalService.id}/env/raw`, token, {
        method: "POST",
        body: JSON.stringify({ raw_env: rawEnvText, merge: rawEnvMerge })
      });
      setEnvVars(vars);
      setRawEnvText("");
      setEnvTab("list");
      setNotice("Environment variables imported from .env format.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not import .env file");
    } finally {
      setBusy(false);
    }
  }

  // Deploy Hooks
  async function regenerateDeployToken(service: Service) {
    setBusy(true); setError("");
    try {
      const updated = await request<Service>(`/v1/services/${service.id}/deploy-token`, token, { method: "POST" });
      setWebhookModalService(updated);
      setNotice("Deploy hook token regenerated.");
      await loadDashboard(token, activeOrgId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not regenerate token");
    } finally {
      setBusy(false);
    }
  }

  // Runtime Logs
  async function openRuntimeLogs(service: Service) {
    setRuntimeLogsService(service);
    setRuntimeLogs([]);
    try {
      const res = await request<{ container: string; driver: string; logs: string[] }>(
        `/v1/services/${service.id}/runtime-logs?tail=150`,
        token
      );
      setRuntimeLogs(res.logs || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not fetch runtime logs");
    }
  }

  // Deployments & Live Streaming
  function streamLogs(id: string) {
    if (!id) return;
    setActiveDeployment(id);
    setIsLiveStreaming(true);
    setLogs([]);

    try {
      const es = new EventSource(`${API}/v1/deployments/${id}/logs/stream?token=${encodeURIComponent(token)}`);
      es.onmessage = (event) => {
        try {
          const entry = JSON.parse(event.data);
          setLogs((prev) => {
            if (prev.some((p) => p.id === entry.id)) return prev;
            return [...prev, entry];
          });
        } catch { /* parse error */ }
      };

      es.addEventListener("done", () => {
        setIsLiveStreaming(false);
        es.close();
        loadDashboard(token, activeOrgId);
      });

      es.onerror = () => {
        setIsLiveStreaming(false);
        es.close();
        fetchLogs(id);
      };
    } catch {
      setIsLiveStreaming(false);
      fetchLogs(id);
    }
  }

  async function fetchLogs(id: string) {
    if (!id) return;
    try {
      setLogs(await request<Log[]>(`/v1/deployments/${id}/logs`, token));
      setActiveDeployment(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load logs");
    }
  }

  async function cancelDeployment(deploymentId: string) {
    setBusy(true); setError("");
    try {
      await request<Deployment>(`/v1/deployments/${deploymentId}/cancel`, token, { method: "POST" });
      setNotice("Deployment canceled.");
      await loadDashboard(token, activeOrgId);
      await fetchLogs(deploymentId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not cancel deployment");
    } finally {
      setBusy(false);
    }
  }

  async function deploy(service: Service) {
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await request<Deployment>(`/v1/services/${service.id}/deployments`, token, { method: "POST" });
      setNotice("Deployment queued.");
      await loadDashboard(token, activeOrgId);
      streamLogs(result.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Deployment request failed");
    } finally {
      setBusy(false);
    }
  }

  if (!user || !token) {
    return (
      <main className="auth-shell">
        <section className="auth-visual">
          <div className="brand-lockup"><div className="brand-mark">s.</div><span>small cloud</span></div>
          <div className="auth-hero-copy">
            <div className="eyebrow"><span className="eyebrow-dot"/> BUILT FOR THE SMALL THINGS THAT SHIP</div>
            <h1>Your software.<br/><em>Up and running.</em></h1>
            <p>One calm place to deploy, operate, and understand the small software you build.</p>
          </div>
          <div className="auth-mini-card">
            <div className="mini-card-top"><span className="mini-status"/> Deployment pipeline <span className="mini-time">Just now</span></div>
            <div className="mini-pipeline"><span className="pipeline-step done">01 <b>Source</b></span><span className="pipeline-line"/><span className="pipeline-step done">02 <b>Build</b></span><span className="pipeline-line"/><span className="pipeline-step active">03 <b>Deploy</b></span></div>
            <div className="mini-note">Small software deserves thoughtful infrastructure.</div>
          </div>
          <div className="auth-footer"><span>Independent developers, moving forward.</span><span>EST. 2026</span></div>
        </section>
        <section className="auth-panel">
          <div className="auth-panel-inner">
            <div className="auth-small-brand"><div className="brand-mark">s.</div><span>small cloud</span></div>
            <div className="auth-heading">
              <div className="eyebrow muted">YOUR WORKSPACE</div>
              <h2>{authMode === "register" ? "Start building." : "Welcome back."}</h2>
              <p>{authMode === "register" ? "Create an account to manage your projects." : "Sign in to return to your cloud workspace."}</p>
            </div>
            <form className="stack-form" onSubmit={handleAuth}>
              {authMode === "register" && (
                <label>Workspace name
                  <input value={orgName} onChange={e => setOrgName(e.target.value)} placeholder="e.g. Priyo Labs" maxLength={120}/>
                </label>
              )}
              <label>Email address
                <input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" autoComplete="email" required/>
              </label>
              <label>Password
                <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="At least 12 characters" autoComplete={authMode === "register" ? "new-password" : "current-password"} minLength={authMode === "register" ? 12 : 1} maxLength={128} required/>
                <span className="field-hint">{authMode === "register" ? "Use at least 12 characters." : "Keep your account credentials private."}</span>
              </label>
              {error && <div className="alert error">{error}</div>}
              <button className="button primary full" type="submit" disabled={busy}>
                {busy ? "Please wait…" : authMode === "register" ? "Create workspace" : "Sign in"}<span>↗</span>
              </button>
            </form>
            <div className="auth-switch">
              {authMode === "register" ? "Already have an account?" : "New to Small Cloud?"}{" "}
              <button onClick={() => { setAuthMode(authMode === "register" ? "login" : "register"); setError(""); }}>
                {authMode === "register" ? "Sign in" : "Create account"}
              </button>
            </div>
            <div className="auth-legal">Protected by token bucket rate limiting. Public workload hosting operates via Traefik reverse proxy.</div>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup"><div className="brand-mark">s.</div><span>small cloud</span><span className="brand-beta">BETA</span></div>

        {/* Multi-workspace Switcher */}
        <div className="workspace-switcher" style={{ cursor: "pointer" }} onClick={() => setShowOrgForm(true)} title="Click to switch or create workspace">
          <div className="workspace-avatar">{activeOrg ? initial(activeOrg.name) : initial(user.email)}</div>
          <div className="workspace-info">
            <strong>{activeOrg ? activeOrg.name : "My workspace"}</strong>
            <span>{activeOrg ? `${activeOrg.plan} · ${activeOrg.role || "owner"}` : "Workspace"} ▾</span>
          </div>
        </div>

        <div className="side-label">WORKSPACE</div>
        <nav className="side-nav">
          <button className={activeView === "overview" ? "active" : ""} onClick={() => setActiveView("overview")}><span className="nav-icon">◫</span> Overview</button>
          <button className={activeView === "projects" ? "active" : ""} onClick={() => setActiveView("projects")}><span className="nav-icon">▦</span> Projects <span className="nav-count">{projects.length}</span></button>
          <button className={activeView === "activity" ? "active" : ""} onClick={() => setActiveView("activity")}><span className="nav-icon">↗</span> Activity</button>
        </nav>
        <div className="side-label side-label-spaced">MANAGE</div>
        <nav className="side-nav">
          <button className={activeView === "settings" ? "active" : ""} onClick={() => setActiveView("settings")}><span className="nav-icon">⚙</span> Workspace settings</button>
        </nav>
        <div className="sidebar-bottom">
          <div className="support-card">
            <div className="support-glyph">✳</div>
            <strong>Built for focus.</strong>
            <p>Small software. Clear operations. Less overhead.</p>
            <span className="support-badge">CONTROL PLANE v0.3</span>
          </div>
          <button className="profile-button" onClick={signOut}>
            <div className="profile-avatar">{initial(user.email)}</div>
            <div className="profile-copy"><strong>{user.email}</strong><span>Signed in</span></div>
            <span className="signout-mark">↗</span>
          </button>
        </div>
      </aside>

      <section className="main-area">
        <header className="topbar">
          <div className="breadcrumbs">
            <span>{activeOrg ? activeOrg.name : "Workspace"}</span><i>/</i>
            <strong>{activeView === "overview" ? "Overview" : activeView === "projects" ? "Projects" : activeView === "activity" ? "Activity" : "Settings"}</strong>
          </div>
          <div className="topbar-actions">
            <span className="status-pill"><span className="status-pip"/> Ingress Engine online</span>
            <button className="icon-button" title="Refresh dashboard" onClick={() => loadDashboard(token, activeOrgId)}>↻</button>
            <div className="top-avatar">{initial(user.email)}</div>
          </div>
        </header>

        <div className="content-wrap">
          {error && <div className="alert error global-alert"><span>!</span>{error}<button onClick={() => setError("")}>×</button></div>}
          {notice && <div className="alert success global-alert"><span>✓</span>{notice}<button onClick={() => setNotice("")}>×</button></div>}

          {/* OVERVIEW VIEW */}
          {activeView === "overview" && (
            <>
              <PageIntro
                eyebrow={activeOrg ? activeOrg.name.toUpperCase() : "YOUR WORKSPACE"}
                title={<>Good work starts <em>here.</em></>}
                subtitle="Your software workspace, organized in one calm place."
                action={<button className="button primary" onClick={() => { setEditingProject(null); setProjectName(""); setProjectDescription(""); setShowProjectForm(true); }}>＋ New project</button>}
              />
              <div className="notice-banner">
                <div className="notice-symbol">i</div>
                <div>
                  <strong>Live Ingress & Real-Time Engine (v0.3)</strong>
                  <p>Server-Sent Events (SSE) live log streaming, deploy hooks, runtime container logs, and auth rate limiting enabled. Pluggable driver: <code>{usage?.deployment_driver}</code>.</p>
                </div>
                <a href={`${API}/docs`} target="_blank" rel="noreferrer">API docs ↗</a>
              </div>
              <div className="metric-grid">
                <Metric label="Projects" value={usage?.projects ?? projects.length} unit="total" foot="In active workspace" icon="▦"/>
                <Metric label="Services" value={usage?.services ?? allServices.length} unit="configured" foot={`${healthyServices} services ready/healthy`} icon="◈"/>
                <Metric label="Deployments" value={usage?.deployments_last_30_days ?? recentDeployments.length} unit="/ 30 days" foot="Queue and lifecycle history" icon="↗"/>
                <Metric label="Configured memory" value={usage?.configured_memory_mb ?? 0} unit="MB" foot="Resource allocation limit" icon="▤"/>
              </div>

              <div className="section-heading">
                <div><h2>Recent projects</h2><p>What you have been working on in {activeOrg?.name || "this workspace"}.</p></div>
                <button className="text-action" onClick={() => setActiveView("projects")}>View all projects <span>→</span></button>
              </div>

              {projects.length === 0 ? (
                <EmptyState onCreate={() => { setEditingProject(null); setProjectName(""); setProjectDescription(""); setShowProjectForm(true); }}/>
              ) : (
                <div className="project-grid">
                  {projects.slice(0, 6).map((project, index) => (
                    <ProjectCard
                      key={project.id}
                      project={project}
                      services={project.services || []}
                      onAddService={() => { setEditingService(null); setServiceName(""); setServiceRepo(""); setServiceBranch("main"); setShowServiceFor(project.id); }}
                      onEditProject={() => { setEditingProject(project); setProjectName(project.name); setProjectDescription(project.description || ""); setShowProjectForm(true); }}
                      onDeleteProject={() => deleteProject(project)}
                      onEditService={(s) => { setEditingService(s); setServiceName(s.name); setServiceRepo(s.source_repo || ""); setServiceBranch(s.branch || "main"); setShowServiceFor(project.id); }}
                      onDeleteService={deleteService}
                      onEnvService={openEnvModal}
                      onWebhookService={setWebhookModalService}
                      onRuntimeLogsService={openRuntimeLogs}
                      onDeploy={deploy}
                      onOpenLogs={streamLogs}
                      busy={busy}
                      index={index}
                    />
                  ))}
                </div>
              )}

              <div className="lower-grid">
                <div className="panel-card">
                  <div className="panel-heading"><div><h3>Deployment activity</h3><p>Recent lifecycle events</p></div><span className="panel-icon">↗</span></div>
                  {recentDeployments.length === 0 ? (
                    <div className="compact-empty">No deployments yet. Create a service to get started.</div>
                  ) : (
                    <ActivityList items={recentDeployments} onOpen={streamLogs} onCancel={cancelDeployment}/>
                  )}
                </div>
                <div className="panel-card resource-card">
                  <div className="panel-heading"><div><h3>Workspace limits</h3><p>Configured capacity overview</p></div><span className="panel-icon">⌁</span></div>
                  <Resource label="Memory budget" value={`${usage?.configured_memory_mb ?? 0} MB`} percent={Math.min(100, ((usage?.configured_memory_mb || 0) / 8192) * 100)}/>
                  <Resource label="CPU budget" value={`${((usage?.configured_cpu_millicores ?? 0) / 1000).toFixed(2)} vCPU`} percent={Math.min(100, ((usage?.configured_cpu_millicores || 0) / 8000) * 100)}/>
                  <div className="resource-foot">Dynamic cgroups enforcement applied on deployment.</div>
                </div>
              </div>
            </>
          )}

          {/* PROJECTS VIEW */}
          {activeView === "projects" && (
            <>
              <PageIntro
                eyebrow={activeOrg ? activeOrg.name.toUpperCase() : "YOUR WORKSPACE"}
                title={<>Projects <em>and services.</em></>}
                subtitle="Keep each small app and its operations organized."
                action={<button className="button primary" onClick={() => { setEditingProject(null); setProjectName(""); setProjectDescription(""); setShowProjectForm(true); }}>＋ New project</button>}
              />
              {projects.length === 0 ? (
                <EmptyState onCreate={() => { setEditingProject(null); setProjectName(""); setProjectDescription(""); setShowProjectForm(true); }}/>
              ) : (
                <div className="project-grid">
                  {projects.map((project, index) => (
                    <ProjectCard
                      key={project.id}
                      project={project}
                      services={project.services || []}
                      onAddService={() => { setEditingService(null); setServiceName(""); setServiceRepo(""); setServiceBranch("main"); setShowServiceFor(project.id); }}
                      onEditProject={() => { setEditingProject(project); setProjectName(project.name); setProjectDescription(project.description || ""); setShowProjectForm(true); }}
                      onDeleteProject={() => deleteProject(project)}
                      onEditService={(s) => { setEditingService(s); setServiceName(s.name); setServiceRepo(s.source_repo || ""); setServiceBranch(s.branch || "main"); setShowServiceFor(project.id); }}
                      onDeleteService={deleteService}
                      onEnvService={openEnvModal}
                      onWebhookService={setWebhookModalService}
                      onRuntimeLogsService={openRuntimeLogs}
                      onDeploy={deploy}
                      onOpenLogs={streamLogs}
                      busy={busy}
                      index={index}
                    />
                  ))}
                </div>
              )}
            </>
          )}

          {/* ACTIVITY VIEW */}
          {activeView === "activity" && (
            <>
              <PageIntro
                eyebrow="HISTORY"
                title={<>Deployment <em>activity.</em></>}
                subtitle="A transparent history of deployment requests and outcomes."
                action={<button className="button secondary" onClick={() => loadDashboard(token, activeOrgId)}>↻ Refresh</button>}
              />
              <div className="panel-card full-panel">
                {recentDeployments.length === 0 ? (
                  <div className="compact-empty">Activity will appear here when you deploy a service.</div>
                ) : (
                  <ActivityList items={recentDeployments} onOpen={streamLogs} onCancel={cancelDeployment}/>
                )}
              </div>
            </>
          )}

          {/* SETTINGS VIEW */}
          {activeView === "settings" && (
            <>
              <PageIntro eyebrow="CONFIGURATION" title={<>Workspace <em>settings.</em></>} subtitle="Account details, workspaces, and control-plane configuration."/>
              <div className="settings-grid">
                <div className="panel-card">
                  <PanelHeading title="Workspaces" subtitle="Switch or create new workspaces"/>
                  {organizations.map(org => (
                    <div key={org.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: "1px solid rgba(0,0,0,0.05)" }}>
                      <div>
                        <strong>{org.name}</strong> <small style={{ color: "#666" }}>({org.slug})</small>
                        <div style={{ fontSize: "12px", color: "#888" }}>Role: {org.role || "member"}</div>
                      </div>
                      {org.id === activeOrgId ? (
                        <span className="tag neutral">Active</span>
                      ) : (
                        <button className="button secondary" style={{ fontSize: "12px", padding: "4px 8px" }} onClick={() => setActiveOrgId(org.id)}>Switch</button>
                      )}
                    </div>
                  ))}
                  <button className="button secondary" style={{ marginTop: "12px" }} onClick={() => setShowOrgForm(true)}>＋ New workspace</button>
                </div>
                <div className="panel-card">
                  <PanelHeading title="Account" subtitle="Current signed-in identity"/>
                  <Setting label="Email" value={user.email}/>
                  <Setting label="User ID" value={user.id} mono/>
                  <Setting label="Account created" value={new Date(user.created_at).toLocaleDateString()}/>
                  <button className="button secondary" onClick={signOut}>Sign out</button>
                </div>
                <div className="panel-card">
                  <PanelHeading title="Control plane" subtitle="Platform status"/>
                  <Setting label="Deployment driver" value={usage?.deployment_driver || "mock"} mono/>
                  <Setting label="Ingress Proxy" value="Traefik v3 Dynamic Routing" mono/>
                  <Setting label="API version" value="v0.3.0" mono/>
                  <Setting label="API base URL" value={API} mono/>
                  <div className="settings-note">Rate limiting active. Self-healing queue worker active.</div>
                  <a className="button secondary link-button" href={`${API}/docs`} target="_blank" rel="noreferrer">Explore API docs ↗</a>
                </div>
              </div>
            </>
          )}

          {/* LOGS TERMINAL PANEL */}
          {activeDeployment && (
            <LogsPanel
              logs={logs}
              deploymentId={activeDeployment}
              isLiveStreaming={isLiveStreaming}
              onCancel={() => cancelDeployment(activeDeployment)}
            />
          )}

          <footer className="app-footer">
            <span>Small Cloud <i>·</i> Developer control plane v0.3</span>
            <span>Thoughtfully small, by design.</span>
          </footer>
        </div>
      </section>

      {/* WORKSPACE MODAL */}
      {showOrgForm && (
        <Modal title="Create workspace." eyebrow="ORGANIZATION" subtitle="A separate workspace for different teams or clients." onClose={() => setShowOrgForm(false)}>
          <form className="stack-form" onSubmit={createWorkspace}>
            <label>Workspace name
              <input value={newOrgName} onChange={e => setNewOrgName(e.target.value)} placeholder="e.g. Acme Studio" minLength={2} maxLength={120} required autoFocus/>
            </label>
            <div className="modal-actions">
              <button type="button" className="button secondary" onClick={() => setShowOrgForm(false)}>Cancel</button>
              <button type="submit" className="button primary" disabled={busy}>{busy ? "Creating…" : "Create workspace →"}</button>
            </div>
          </form>
        </Modal>
      )}

      {/* PROJECT MODAL (Create/Edit) */}
      {showProjectForm && (
        <Modal
          title={editingProject ? "Edit project." : "Make room for an idea."}
          eyebrow={editingProject ? "UPDATE PROJECT" : "NEW PROJECT"}
          subtitle="A project keeps related services together."
          onClose={() => { setShowProjectForm(false); setEditingProject(null); }}
        >
          <form className="stack-form" onSubmit={saveProject}>
            <label>Project name
              <input value={projectName} onChange={e => setProjectName(e.target.value)} placeholder="e.g. Customer API" minLength={2} maxLength={120} required autoFocus/>
            </label>
            <label>Description <span className="optional-label">OPTIONAL</span>
              <textarea value={projectDescription} onChange={e => setProjectDescription(e.target.value)} placeholder="What are you building?" rows={3} maxLength={500}/>
            </label>
            <div className="modal-actions">
              <button type="button" className="button secondary" onClick={() => { setShowProjectForm(false); setEditingProject(null); }}>Cancel</button>
              <button type="submit" className="button primary" disabled={busy}>{busy ? "Saving…" : editingProject ? "Save changes →" : "Create project →"}</button>
            </div>
          </form>
        </Modal>
      )}

      {/* SERVICE MODAL (Create/Edit) */}
      {showServiceFor && (
        <Modal
          title={editingService ? "Edit service." : "Bring a service in."}
          eyebrow={editingService ? "UPDATE SERVICE" : "NEW SERVICE"}
          subtitle="Configure the source metadata for this service."
          onClose={() => { setShowServiceFor(""); setEditingService(null); }}
        >
          <form className="stack-form" onSubmit={saveService}>
            <label>Service name
              <input value={serviceName} onChange={e => setServiceName(e.target.value)} placeholder="e.g. backend-api" minLength={2} maxLength={120} required autoFocus/>
            </label>
            {!editingService && (
              <label>Runtime
                <select value={serviceRuntime} onChange={e => setServiceRuntime(e.target.value)}>
                  <option value="python">Python</option>
                  <option value="node">Node.js</option>
                </select>
              </label>
            )}
            <label>Public Git repository URL
              <input type="url" value={serviceRepo} onChange={e => setServiceRepo(e.target.value)} placeholder="https://github.com/you/project" pattern="https://(github\.com|gitlab\.com|codeberg\.org)/.*" required/>
            </label>
            <label>Branch
              <input type="text" value={serviceBranch} onChange={e => setServiceBranch(e.target.value)} placeholder="main" required/>
            </label>
            <div className="settings-note">Supports Dockerfile detection or automatic non-root image synthesis.</div>
            <div className="modal-actions">
              <button type="button" className="button secondary" onClick={() => { setShowServiceFor(""); setEditingService(null); }}>Cancel</button>
              <button type="submit" className="button primary" disabled={busy}>{busy ? "Saving…" : editingService ? "Save changes →" : "Create service →"}</button>
            </div>
          </form>
        </Modal>
      )}

      {/* ENVIRONMENT VARIABLES MODAL */}
      {envModalService && (
        <Modal
          title={`Environment Variables: ${envModalService.name}`}
          eyebrow="CONFIGURATION"
          subtitle="Manage runtime environment variables and secrets."
          onClose={() => setEnvModalService(null)}
        >
          <div className="stack-form">
            <div style={{ display: "flex", gap: "8px", borderBottom: "1px solid rgba(0,0,0,0.1)", paddingBottom: "8px", marginBottom: "12px" }}>
              <button
                type="button"
                className={`button ${envTab === "list" ? "primary" : "secondary"}`}
                style={{ fontSize: "12px", padding: "4px 12px" }}
                onClick={() => setEnvTab("list")}
              >
                Key-Value List ({envVars.length})
              </button>
              <button
                type="button"
                className={`button ${envTab === "raw" ? "primary" : "secondary"}`}
                style={{ fontSize: "12px", padding: "4px 12px" }}
                onClick={() => setEnvTab("raw")}
              >
                Import / Paste .env
              </button>
            </div>

            {envTab === "raw" ? (
              <div>
                <label>Paste .env Content
                  <textarea
                    rows={8}
                    value={rawEnvText}
                    onChange={e => setRawEnvText(e.target.value)}
                    placeholder={`# Paste your env configuration\nPORT=8080\nDATABASE_URL=postgres://...\nJWT_SECRET=supersecret`}
                    style={{ fontFamily: "monospace", fontSize: "12px", width: "100%", marginTop: "6px" }}
                  />
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "12px", cursor: "pointer", marginTop: "8px" }}>
                  <input type="checkbox" checked={rawEnvMerge} onChange={e => setRawEnvMerge(e.target.checked)}/>
                  Merge with existing variables (leaves unmatched keys intact)
                </label>
                <div className="settings-note" style={{ marginTop: "6px" }}>
                  Automatically detects sensitive keys (e.g. PASSWORD, SECRET, KEY, TOKEN) and flags them as secrets.
                </div>
                <div className="modal-actions" style={{ marginTop: "16px" }}>
                  <button type="button" className="button secondary" onClick={() => setEnvTab("list")}>Back</button>
                  <button type="button" className="button primary" onClick={importRawEnv} disabled={busy || !rawEnvText.trim()}>
                    {busy ? "Importing…" : "Parse & Import .env →"}
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div style={{ maxHeight: "240px", overflowY: "auto", border: "1px solid rgba(0,0,0,0.1)", borderRadius: "6px", padding: "8px" }}>
                  {envVars.length === 0 ? (
                    <div style={{ padding: "12px", textAlign: "center", color: "#888", fontSize: "13px" }}>No environment variables set yet.</div>
                  ) : (
                    envVars.map(v => (
                      <div key={v.key} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid rgba(0,0,0,0.05)" }}>
                        <div style={{ fontFamily: "monospace", fontSize: "13px" }}>
                          <strong>{v.key}</strong> = {v.is_secret ? "••••••••" : v.value}
                          {v.is_secret && <span style={{ marginLeft: "8px", fontSize: "10px", color: "#e67e22" }}>[SECRET]</span>}
                        </div>
                        <button type="button" className="text-action" style={{ color: "#d9534f", fontSize: "12px" }} onClick={() => removeEnvVar(v.key)}>Remove</button>
                      </div>
                    ))
                  )}
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", gap: "8px", alignItems: "end", marginTop: "12px" }}>
                  <label style={{ margin: 0 }}>Key
                    <input value={newEnvKey} onChange={e => setNewEnvKey(e.target.value.toUpperCase())} placeholder="e.g. DATABASE_URL"/>
                  </label>
                  <label style={{ margin: 0 }}>Value
                    <input value={newEnvVal} onChange={e => setNewEnvVal(e.target.value)} placeholder="value"/>
                  </label>
                  <button type="button" className="button secondary" onClick={addEnvVar} style={{ height: "38px" }}>Add</button>
                </div>
                <label style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "12px", cursor: "pointer", marginTop: "4px" }}>
                  <input type="checkbox" checked={newEnvSecret} onChange={e => setNewEnvSecret(e.target.checked)}/> Mask as secret in logs and responses
                </label>

                <div className="modal-actions" style={{ marginTop: "16px" }}>
                  <button type="button" className="button secondary" onClick={() => setEnvModalService(null)}>Cancel</button>
                  <button type="button" className="button primary" onClick={saveEnvVars} disabled={busy}>{busy ? "Saving…" : "Save variables →"}</button>
                </div>
              </>
            )}
          </div>
        </Modal>
      )}

      {/* DEPLOY HOOK MODAL */}
      {webhookModalService && (
        <Modal
          title={`Deploy Hook: ${webhookModalService.name}`}
          eyebrow="CONTINUOUS DEPLOYMENT"
          subtitle="Trigger deployments from GitHub Actions, GitLab CI, or scripts."
          onClose={() => setWebhookModalService(null)}
        >
          <div className="stack-form">
            <label>Deploy Hook Webhook URL
              <input
                readOnly
                value={`${API}/v1/services/${webhookModalService.id}/deploy-hook?token=${webhookModalService.deploy_token || ""}`}
                style={{ fontFamily: "monospace", fontSize: "12px" }}
              />
            </label>
            <label>cURL Trigger Command
              <textarea
                readOnly
                rows={2}
                value={`curl -X POST "${API}/v1/services/${webhookModalService.id}/deploy-hook?token=${webhookModalService.deploy_token || ""}"`}
                style={{ fontFamily: "monospace", fontSize: "12px" }}
              />
            </label>
            <div className="settings-note">
              Anyone with this token can trigger a deployment. Keep it secret in GitHub Actions or CI environment variables.
            </div>
            <div className="modal-actions" style={{ justifyContent: "space-between" }}>
              <button type="button" className="button secondary" onClick={() => regenerateDeployToken(webhookModalService)} disabled={busy}>
                Regenerate token ↻
              </button>
              <button
                type="button"
                className="button primary"
                onClick={() => {
                  navigator.clipboard.writeText(`curl -X POST "${API}/v1/services/${webhookModalService.id}/deploy-hook?token=${webhookModalService.deploy_token || ""}"`);
                  setNotice("cURL command copied to clipboard!");
                  setWebhookModalService(null);
                }}
              >
                Copy command & close
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* RUNTIME CONTAINER LOGS MODAL */}
      {runtimeLogsService && (
        <Modal
          title={`Live Runtime Logs: ${runtimeLogsService.name}`}
          eyebrow="APPLICATION STDOUT / STDERR"
          subtitle={`Container output for service ${runtimeLogsService.slug}`}
          onClose={() => setRuntimeLogsService(null)}
        >
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px", fontSize: "12px", color: "#666" }}>
              <span>Displaying recent output lines:</span>
              <button className="text-action" onClick={() => openRuntimeLogs(runtimeLogsService)}>Refresh ↻</button>
            </div>
            <div className="log-terminal" style={{ maxHeight: "360px", overflowY: "auto" }}>
              {runtimeLogs.length === 0 ? (
                <div style={{ color: "#888", padding: "12px" }}>No output received yet from the application container.</div>
              ) : (
                runtimeLogs.map((line, i) => (
                  <div className="log-line" key={i} style={{ fontFamily: "monospace", fontSize: "12px" }}>
                    <span>{line}</span>
                  </div>
                ))
              )}
            </div>
            <div className="modal-actions" style={{ marginTop: "12px" }}>
              <button type="button" className="button secondary" onClick={() => setRuntimeLogsService(null)}>Close</button>
            </div>
          </div>
        </Modal>
      )}
    </main>
  );
}

function PageIntro({ eyebrow, title, subtitle, action }: { eyebrow: string; title: ReactNode; subtitle: string; action?: ReactNode }) {
  return <div className="page-intro"><div><div className="eyebrow muted">{eyebrow}</div><h1>{title}</h1><p>{subtitle}</p></div>{action}</div>;
}

function Metric({ label, value, unit, foot, icon }: { label: string; value: number; unit: string; foot: string; icon: string }) {
  return <div className="metric-card"><div className="metric-label">{label}<span className="metric-icon">{icon}</span></div><div className="metric-value">{value}<span className="metric-unit"> {unit}</span></div><div className="metric-foot">{foot}</div></div>;
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="empty-state">
      <div className="empty-art"><span>▦</span><i>＋</i></div>
      <h3>A little space for your next big thing.</h3>
      <p>Create a project to organize services, deployments and operational history.</p>
      <button className="button primary" onClick={onCreate}>Create your first project <span>→</span></button>
    </div>
  );
}

function ProjectCard({
  project,
  services,
  onAddService,
  onEditProject,
  onDeleteProject,
  onEditService,
  onDeleteService,
  onEnvService,
  onWebhookService,
  onRuntimeLogsService,
  onDeploy,
  onOpenLogs,
  busy,
  index
}: {
  project: Project;
  services: Service[];
  onAddService: () => void;
  onEditProject: () => void;
  onDeleteProject: () => void;
  onEditService: (s: Service) => void;
  onDeleteService: (s: Service) => void;
  onEnvService: (s: Service) => void;
  onWebhookService: (s: Service) => void;
  onRuntimeLogsService: (s: Service) => void;
  onDeploy: (service: Service) => void;
  onOpenLogs: (id: string) => void;
  busy: boolean;
  index: number;
}) {
  const palette = ["clay", "sage", "ochre", "slate"];
  const latest = services
    .map(s => s.latest_deployment ? { ...s.latest_deployment, serviceName: s.name } : null)
    .filter((d): d is Deployment & { serviceName: string } => d !== null)
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())[0];

  return (
    <article className="project-card">
      <div className="project-card-header">
        <div className={`project-symbol ${palette[index % palette.length]}`}>{project.name.slice(0, 1).toUpperCase()}</div>
        <div style={{ display: "flex", gap: "6px" }}>
          <button className="text-action" style={{ fontSize: "12px" }} onClick={onEditProject} title="Edit project">✎</button>
          <button className="text-action" style={{ fontSize: "12px", color: "#d9534f" }} onClick={onDeleteProject} title="Delete project">✕</button>
        </div>
      </div>
      <div className="project-title-row">
        <h3>{project.name}</h3>
        <span className="project-slug">/{project.slug}</span>
      </div>
      <p className="project-description">{project.description || "A focused space for your small software."}</p>
      <div className="project-stats">
        <span><i className="stat-service-icon">◈</i> {services.length} service{services.length === 1 ? "" : "s"}</span>
        <span className={`project-health ${services.some(s => s.status === "healthy") ? "healthy" : "quiet"}`}>
          <i/> {services.some(s => s.status === "healthy") ? "Live on Ingress" : "No active container"}
        </span>
      </div>

      {services.length > 0 && (
        <div className="service-mini-list">
          {services.map(s => (
            <div className="service-mini" key={s.id}>
              <span className={`service-type-icon ${s.runtime}`}>{s.runtime === "python" ? "Py" : s.runtime === "node" ? "JS" : "▣"}</span>
              <span className="service-mini-name">
                {s.name}
                <small>
                  {s.runtime} · {s.kind}
                  {s.latest_deployment?.output_url && (
                    <a href={s.latest_deployment.output_url} target="_blank" rel="noreferrer" style={{ marginLeft: "6px", color: "#2563eb", textDecoration: "underline" }}>
                      open ↗
                    </a>
                  )}
                </small>
              </span>
              <span className={`tag ${s.status === "failed" ? "failed" : "neutral"}`}>{s.status}</span>
              <button title="Deploy Hook (Webhook URL)" className="tiny-action" onClick={() => onWebhookService(s)} style={{ fontSize: "11px" }}>⚡</button>
              <button title="Runtime Output Logs" className="tiny-action" onClick={() => onRuntimeLogsService(s)} style={{ fontSize: "11px" }}>📄</button>
              <button title="Environment Variables" className="tiny-action" onClick={() => onEnvService(s)} style={{ fontSize: "11px" }}>⚙</button>
              <button title="Edit service" className="tiny-action" onClick={() => onEditService(s)} style={{ fontSize: "11px" }}>✎</button>
              <button title="Delete service" className="tiny-action" onClick={() => onDeleteService(s)} style={{ fontSize: "11px", color: "#d9534f" }}>✕</button>
              <button title="Trigger Deployment" className="tiny-action" disabled={busy} onClick={() => onDeploy(s)}>↗</button>
            </div>
          ))}
        </div>
      )}

      {latest && (
        <button className="last-deploy" onClick={() => onOpenLogs(latest.id)}>
          <span className={`activity-dot ${latest.status}`}/>
          <span>Last deploy <strong>{latest.status}</strong></span>
          <small>{timeAgo(latest.created_at)}</small>
          <b>→</b>
        </button>
      )}

      <div className="project-card-footer">
        <button className="text-action" onClick={onAddService}>＋ Add service</button>
        <span className="project-date">Created {new Date(project.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span>
      </div>
    </article>
  );
}

function ActivityList({ items, onOpen, onCancel }: { items: Deployment[]; onOpen: (id: string) => void; onCancel?: (id: string) => void }) {
  return (
    <div className="activity-list">
      {items.map(d => (
        <div className="activity-row" key={d.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <button onClick={() => onOpen(d.id)} style={{ all: "unset", display: "flex", alignItems: "center", gap: "10px", flex: 1, cursor: "pointer" }}>
            <span className={`activity-dot ${d.status}`}/>
            <span className="activity-text">
              <strong>{d.status === "healthy" ? "Deployment completed" : d.status === "failed" ? "Deployment failed" : d.status === "canceled" ? "Deployment canceled" : "Deployment in progress"}</strong>
              <small>{d.id.slice(0, 12)} · {timeAgo(d.created_at)}</small>
            </span>
            <span className={`tag ${d.status === "healthy" ? "neutral" : d.status}`}>{d.status}</span>
          </button>
          {(d.status === "queued" || d.status === "building" || d.status === "starting") && onCancel && (
            <button className="button secondary" style={{ fontSize: "11px", padding: "2px 8px", marginLeft: "8px" }} onClick={() => onCancel(d.id)}>Cancel</button>
          )}
          <span className="row-arrow" style={{ cursor: "pointer" }} onClick={() => onOpen(d.id)}>↗</span>
        </div>
      ))}
    </div>
  );
}

function Resource({ label, value, percent }: { label: string; value: string; percent: number }) {
  return (
    <div className="resource-line">
      <div><span>{label}</span><strong>{value}</strong></div>
      <div className="meter"><span style={{ width: `${percent}%` }}/></div>
    </div>
  );
}

function PanelHeading({ title, subtitle }: { title: string; subtitle: string }) {
  return <div className="panel-heading"><div><h3>{title}</h3><p>{subtitle}</p></div></div>;
}

function Setting({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div className="setting-row"><span>{label}</span>{mono ? <code>{value}</code> : <strong>{value}</strong>}</div>;
}

function LogsPanel({
  logs,
  deploymentId,
  isLiveStreaming,
  onCancel
}: {
  logs: Log[];
  deploymentId: string;
  isLiveStreaming?: boolean;
  onCancel?: () => void;
}) {
  return (
    <div className="panel-card logs-panel">
      <div className="panel-heading">
        <div>
          <h3>Deployment logs {isLiveStreaming && <span style={{ fontSize: "12px", color: "#10b981", fontWeight: "normal" }}>● LIVE STREAMING</span>}</h3>
          <p>Deployment <code>{deploymentId.slice(0, 12)}</code></p>
        </div>
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          {onCancel && <button className="button secondary" style={{ fontSize: "11px", padding: "3px 8px" }} onClick={onCancel}>Cancel job</button>}
          <span className="log-status">{logs.length} entries</span>
        </div>
      </div>
      {logs.length === 0 ? (
        <div className="compact-empty">Connecting to live log stream…</div>
      ) : (
        <div className="log-terminal">
          {logs.map(log => (
            <div className="log-line" key={log.id}>
              <time>{new Date(log.created_at).toLocaleTimeString()}</time>
              <span className={`log-level ${log.level.toLowerCase()}`}>{log.level}</span>
              <span>{log.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Modal({ title, eyebrow, subtitle, children, onClose }: { title: string; eyebrow: string; subtitle: string; children: ReactNode; onClose: () => void }) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-card" role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-heading">
          <div>
            <div className="eyebrow muted">{eyebrow}</div>
            <h2>{title}</h2>
            <p>{subtitle}</p>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close dialog">×</button>
        </div>
        {children}
      </div>
    </div>
  );
}
