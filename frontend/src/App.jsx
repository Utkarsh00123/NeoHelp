import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { 
  Activity, 
  Database, 
  Server, 
  Layers, 
  Clock, 
  CheckCircle2, 
  AlertTriangle, 
  RefreshCw,
  GitBranch,
  ShieldCheck,
  Zap
} from 'lucide-react'
import { fetchHealth } from './api/client'
import './App.css'

export default function App() {
  const { data: health, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['system-health'],
    queryFn: fetchHealth,
    refetchInterval: 15000,
  })

  // Sample timeline operational activities representing chronology
  const sampleTimelineEvents = [
    {
      id: 'OP-1042',
      title: 'Database Failover Drill Initiated',
      type: 'Compliance',
      priority: 'urgent',
      time: '10 mins ago',
      author: 'Sarah Chen (Lead)',
      summary: 'Automated failover protocol initiated across US-East replicas to verify zero-downtime replication.',
    },
    {
      id: 'OP-1041',
      title: 'API Gateway Rate-Limit Policy Shift',
      type: 'Incident',
      priority: 'active',
      time: '34 mins ago',
      author: 'Marcus Vance (Member)',
      summary: 'Spike in inbound requests on /v1/telemetry mitigated via dynamic token bucket throttle adjustment.',
    },
    {
      id: 'OP-1039',
      title: 'Audit Log Archival & Signature Verification',
      type: 'Compliance',
      priority: 'resolved',
      time: '2 hours ago',
      author: 'System Outbox Worker',
      summary: 'Monthly cryptographic checksum verification complete. Zero integrity discrepancies detected.',
    },
  ]

  const dbStatus = health?.database?.includes('healthy') ? 'healthy' : isError ? 'error' : 'degraded'
  const redisStatus = health?.redis?.includes('healthy') ? 'healthy' : isError ? 'error' : 'degraded'
  const apiStatus = (!isLoading && !isError) ? 'healthy' : isLoading ? 'degraded' : 'error'

  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header">
        <div className="brand-wrapper">
          <div className="brand-logo-badge" id="brand-logo">
            <Zap size={24} />
          </div>
          <div>
            <h1 className="brand-title">NeoHelp</h1>
            <p className="brand-tagline">Operational Task & Incident Chronology Platform</p>
          </div>
        </div>

        {/* Global Connection Ribbon */}
        <div className="status-ribbon" id="system-status-ribbon">
          <div className="status-indicator-item">
            <span className={`status-dot ${apiStatus}`} />
            <span>FastAPI Backend</span>
          </div>
          <div className="status-indicator-item">
            <span className={`status-dot ${dbStatus}`} />
            <span>PostgreSQL</span>
          </div>
          <div className="status-indicator-item">
            <span className={`status-dot ${redisStatus}`} />
            <span>Redis</span>
          </div>
        </div>
      </header>

      {/* Main Grid: Timeline feed + System Info Panel */}
      <main className="dashboard-grid">
        {/* Timeline Event Feed */}
        <section className="timeline-section">
          <div className="section-header">
            <h2 className="section-title">
              <Clock size={20} color="var(--accent-primary)" />
              Operational Timeline Feed
            </h2>
            <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
              Phase 1 Scaffold Active
            </span>
          </div>

          <div className="timeline-list">
            <div className="timeline-line" />
            {sampleTimelineEvents.map((event) => (
              <article key={event.id} className="timeline-card glass-panel" id={`item-${event.id}`}>
                <div className="timeline-card-anchor">
                  <div className="timeline-dot" />
                </div>
                <div className="timeline-card-header">
                  <div>
                    <span className={`timeline-badge ${event.priority}`}>{event.priority}</span>
                    <span style={{ marginLeft: '0.5rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                      #{event.id} • {event.type}
                    </span>
                  </div>
                  <span className="timeline-time">{event.time}</span>
                </div>
                <h3 className="timeline-item-title">{event.title}</h3>
                <p className="timeline-item-desc">{event.summary}</p>
                <div className="timeline-meta-bar">
                  <span>Actor: <strong style={{ color: 'var(--text-primary)' }}>{event.author}</strong></span>
                  <span>•</span>
                  <span>State: Open</span>
                </div>
              </article>
            ))}
          </div>
        </section>

        {/* Sidebar Info & Health Check */}
        <aside className="sidebar-section">
          <div className="glass-panel health-panel" id="health-check-panel">
            <h2 className="panel-title">
              <Activity size={18} color="var(--accent-secondary)" />
              Infrastructure Diagnostics
            </h2>

            <div className="health-metrics-grid">
              <div className="metric-row">
                <span className="metric-label">
                  <Server size={16} /> Backend API
                </span>
                <span className="metric-val" style={{ color: apiStatus === 'healthy' ? 'var(--accent-success)' : 'var(--accent-warning)' }}>
                  {isLoading ? 'Checking...' : isError ? 'Unreachable' : 'Online'}
                </span>
              </div>

              <div className="metric-row">
                <span className="metric-label">
                  <Database size={16} /> PostgreSQL
                </span>
                <span className="metric-val" style={{ color: dbStatus === 'healthy' ? 'var(--accent-success)' : 'var(--accent-muted)' }}>
                  {health?.database || (isLoading ? 'Connecting...' : 'Pending')}
                </span>
              </div>

              <div className="metric-row">
                <span className="metric-label">
                  <Layers size={16} /> Redis Cache
                </span>
                <span className="metric-val" style={{ color: redisStatus === 'healthy' ? 'var(--accent-success)' : 'var(--accent-muted)' }}>
                  {health?.redis || (isLoading ? 'Connecting...' : 'Pending')}
                </span>
              </div>

              <div className="metric-row">
                <span className="metric-label">
                  <ShieldCheck size={16} /> Environment
                </span>
                <span className="metric-val">
                  {health?.environment || 'development'}
                </span>
              </div>
            </div>

            <button 
              id="refetch-health-btn" 
              className="action-btn-primary" 
              onClick={() => refetch()} 
              disabled={isFetching}
            >
              <RefreshCw size={16} className={isFetching ? 'spin' : ''} />
              {isFetching ? 'Verifying Services...' : 'Refresh Health Check'}
            </button>
          </div>

          {/* Blueprint Step 1 Verification Summary */}
          <div className="glass-panel health-panel" style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
            <h3 className="panel-title" style={{ fontSize: '0.95rem' }}>
              <GitBranch size={16} color="var(--accent-primary)" />
              Monorepo Architecture
            </h3>
            <p>
              Phase 1 setup complete:
            </p>
            <ul style={{ paddingLeft: '1.2rem', marginTop: '0.5rem', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <li><strong>/backend:</strong> FastAPI, Async SQLAlchemy, Redis, Pytest</li>
              <li><strong>/frontend:</strong> React, Vite, TanStack Query</li>
              <li><strong>docker-compose.yml:</strong> Multi-service containerization</li>
            </ul>
          </div>
        </aside>
      </main>
    </div>
  )
}
