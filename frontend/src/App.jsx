import React, { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { 
  Zap,
  Clock, 
  CheckCircle2, 
  AlertTriangle, 
  RefreshCw,
  UserCheck,
  ShieldCheck,
  Filter,
  Plus,
  Send,
  MessageSquare,
  ArrowRight,
  User,
  Tag,
  AlertCircle,
  FileText,
  Search,
  ExternalLink,
  ChevronDown,
  Layers,
  History,
  X,
  Lock,
  Unlock
} from 'lucide-react'
import { 
  fetchHealth,
  loginUser,
  switchUser,
  fetchUsers,
  fetchMe,
  fetchItems,
  fetchItem,
  createItem,
  claimItem,
  updateItem,
  transitionItem,
  fetchItemActivity,
  addComment
} from './api/client'
import './App.css'

const VALID_TRANSITIONS = {
  'Open': ['In Progress'],
  'In Progress': ['Open', 'Awaiting Approval'],
  'Awaiting Approval': ['In Progress', 'Resolved'],
  'Resolved': ['Closed', 'In Progress'],
  'Closed': []
}

export default function App() {
  const queryClient = useQueryClient()

  // App State
  const [selectedQueue, setSelectedQueue] = useState('all') // 'all' | 'assigned' | 'urgent' | 'approval'
  const [selectedTeam, setSelectedTeam] = useState('')
  const [selectedStatus, setSelectedStatus] = useState('')
  const [selectedPriority, setSelectedPriority] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedItemId, setSelectedItemId] = useState(null)
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [isEditModalOpen, setIsEditModalOpen] = useState(false)
  const [conflictBanner, setConflictBanner] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [commentText, setCommentText] = useState('')
  const [transitionComment, setTransitionComment] = useState('')
  const [targetTransitionStatus, setTargetTransitionStatus] = useState(null)

  // System Health
  const { data: health } = useQuery({
    queryKey: ['system-health'],
    queryFn: fetchHealth,
    refetchInterval: 20000,
  })

  // Users Directory for Role-Switcher
  const { data: users = [] } = useQuery({
    queryKey: ['users-directory'],
    queryFn: fetchUsers,
  })

  // Current User Profile
  const { data: currentUser, refetch: refetchMe } = useQuery({
    queryKey: ['current-user'],
    queryFn: fetchMe,
    retry: false,
  })

  // Initial Auth Bootstrap: auto-login as Diana (Incident Lead) or Alice (Admin) if no token
  useEffect(() => {
    const token = localStorage.getItem('neohelp_token')
    if (!token && users.length > 0) {
      const defaultUser = users.find(u => u.email === 'lead.incident@neohelp.io') || users[0]
      loginUser(defaultUser.email, 'password123').then(() => {
        refetchMe()
        queryClient.invalidateQueries({ queryKey: ['items'] })
      })
    }
  }, [users, refetchMe, queryClient])

  // Work Items List Query with Cursor
  const { 
    data: itemsData, 
    isLoading: isLoadingItems, 
    isFetching: isFetchingItems,
    refetch: refetchItems 
  } = useQuery({
    queryKey: ['items', selectedQueue, selectedTeam, selectedStatus, selectedPriority, searchQuery, currentUser?.id],
    queryFn: () => fetchItems({
      teamId: selectedTeam || undefined,
      queue: selectedQueue !== 'all' ? selectedQueue : undefined,
      status: selectedStatus || undefined,
      priority: selectedPriority || undefined,
      q: searchQuery || undefined,
      limit: 30
    }),
    enabled: !!currentUser,
    refetchInterval: 15000,
  })

  // Selected Item Detail Query
  const { data: selectedItem, refetch: refetchSelectedItem } = useQuery({
    queryKey: ['item', selectedItemId],
    queryFn: () => fetchItem(selectedItemId),
    enabled: !!selectedItemId,
  })

  // Selected Item Activity Timeline Query
  const { data: itemActivity = [], refetch: refetchActivity } = useQuery({
    queryKey: ['item-activity', selectedItemId],
    queryFn: () => fetchItemActivity(selectedItemId),
    enabled: !!selectedItemId,
    refetchInterval: 10000,
  })

  // Auto-select first item if none selected and items loaded
  useEffect(() => {
    if (!selectedItemId && itemsData?.items?.length > 0) {
      setSelectedItemId(itemsData.items[0].id)
    }
  }, [itemsData, selectedItemId])

  // Switch User Handler
  const handleSwitchUser = async (userId) => {
    try {
      await switchUser(userId)
      setConflictBanner(null)
      setActionError(null)
      await refetchMe()
      await queryClient.invalidateQueries({ queryKey: ['items'] })
      if (selectedItemId) {
        await queryClient.invalidateQueries({ queryKey: ['item', selectedItemId] })
      }
    } catch (err) {
      setActionError(err.message)
    }
  }

  // Claim Item Mutation
  const claimMutation = useMutation({
    mutationFn: () => claimItem(selectedItemId, `claim-${selectedItemId}-${Date.now()}`),
    onSuccess: (updated) => {
      setConflictBanner(null)
      setActionError(null)
      queryClient.setQueryData(['item', selectedItemId], updated)
      refetchItems()
      refetchActivity()
    },
    onError: (err) => {
      if (err.status === 409) {
        setConflictBanner({
          type: '409 Conflict',
          message: err.message || 'Work item was claimed by another operator concurrently.',
          action: () => {
            refetchSelectedItem()
            refetchItems()
            setConflictBanner(null)
          }
        })
      } else {
        setActionError(err.message)
      }
    }
  })

  // Transition Item Mutation
  const transitionMutation = useMutation({
    mutationFn: ({ targetStatus, comment }) => 
      transitionItem(selectedItemId, { target_status: targetStatus, comment }, `trans-${selectedItemId}-${targetStatus}-${Date.now()}`),
    onSuccess: (updated) => {
      setConflictBanner(null)
      setActionError(null)
      setTargetTransitionStatus(null)
      setTransitionComment('')
      queryClient.setQueryData(['item', selectedItemId], updated)
      refetchItems()
      refetchActivity()
    },
    onError: (err) => {
      if (err.status === 403) {
        setActionError(`Permission Denied: ${err.message}`)
      } else if (err.status === 409) {
        setConflictBanner({
          type: '409 Conflict',
          message: err.message || 'Item was updated by another operator.',
          action: () => {
            refetchSelectedItem()
            refetchItems()
            setConflictBanner(null)
          }
        })
      } else {
        setActionError(err.message)
      }
    }
  })

  // Add Comment Mutation
  const commentMutation = useMutation({
    mutationFn: (text) => addComment(selectedItemId, text),
    onSuccess: () => {
      setCommentText('')
      setActionError(null)
      refetchActivity()
    },
    onError: (err) => {
      setActionError(err.message)
    }
  })

  // Helpers for RBAC checks
  const currentMembership = currentUser?.memberships?.find(m => m.team_id === selectedItem?.team_id)
  const isTeamLeadOrAdmin = currentMembership?.role === 'Lead' || currentMembership?.role === 'Admin'
  const isViewer = currentMembership?.role === 'Viewer'

  // Calculate Next Attention text
  const getNextAttentionText = (item) => {
    if (!item) return ''
    if (!item.assignee_id) {
      return 'Unassigned — Needs immediate operator claim to begin operational triage.'
    }
    if (item.status === 'Open') {
      return 'Assigned & Open — Transition to "In Progress" when active investigation begins.'
    }
    if (item.status === 'In Progress') {
      return 'Active Investigation — Execute mitigation steps and transition to "Awaiting Approval".'
    }
    if (item.status === 'Awaiting Approval') {
      return isTeamLeadOrAdmin 
        ? 'Approval Gate — Awaiting your Lead/Admin decision to Resolve this item.' 
        : 'Approval Gate — Awaiting review by Team Lead or Admin.'
    }
    if (item.status === 'Resolved') {
      return isTeamLeadOrAdmin 
        ? 'Verification Complete — Close item to archive operational log.' 
        : 'Resolved — Pending final Lead verification.'
    }
    return 'Archived — All operational criteria satisfied.'
  }

  const dbStatus = health?.database?.includes('healthy') ? 'healthy' : 'degraded'
  const redisStatus = health?.redis?.includes('healthy') ? 'healthy' : 'degraded'
  const apiStatus = health ? 'healthy' : 'degraded'

  return (
    <div className="app-container">
      {/* Top Header */}
      <header className="app-header glass-panel">
        <div className="brand-wrapper">
          <div className="brand-logo-badge" id="brand-logo">
            <Zap size={24} />
          </div>
          <div>
            <h1 className="brand-title">NeoHelp</h1>
            <p className="brand-tagline">Timeline-First Operational Command Platform</p>
          </div>
        </div>

        {/* Global Connection Ribbon */}
        <div className="status-ribbon" id="system-status-ribbon">
          <div className="status-indicator-item">
            <span className={`status-dot ${apiStatus}`} />
            <span>FastAPI</span>
          </div>
          <div className="status-indicator-item">
            <span className={`status-dot ${dbStatus}`} />
            <span>PostgreSQL</span>
          </div>
          <div className="status-indicator-item">
            <span className={`status-dot ${redisStatus}`} />
            <span>Redis Outbox</span>
          </div>
        </div>

        {/* User Role Switcher Dropdown */}
        <div className="user-switcher-container">
          <div className="current-user-info">
            <div className="user-avatar-circle">
              <User size={16} />
            </div>
            <div>
              <div className="user-name-display">{currentUser?.full_name || 'Loading...'}</div>
              <div className="user-role-display">
                {currentUser?.memberships?.map(m => `${m.team_name}: ${m.role}`).join(' • ') || 'No Teams'}
              </div>
            </div>
          </div>

          <select 
            className="user-select-dropdown"
            value={currentUser?.id || ''}
            onChange={(e) => handleSwitchUser(e.target.value)}
            id="role-switcher-dropdown"
          >
            {users.map(u => (
              <option key={u.id} value={u.id}>
                {u.full_name} ({u.email.split('@')[0]})
              </option>
            ))}
          </select>
        </div>
      </header>

      {/* Conflict / Concurrency Alert Toast */}
      {conflictBanner && (
        <div className="alert-banner conflict-alert" id="conflict-toast-banner">
          <div className="alert-content">
            <AlertCircle size={20} color="var(--accent-warning)" />
            <div>
              <strong>{conflictBanner.type}:</strong> {conflictBanner.message}
            </div>
          </div>
          <button className="btn btn-warning-sm" onClick={conflictBanner.action}>
            <RefreshCw size={14} /> Reload Latest Server State
          </button>
        </div>
      )}

      {/* Permission / Action Error Toast */}
      {actionError && (
        <div className="alert-banner error-alert" id="action-error-banner">
          <div className="alert-content">
            <AlertTriangle size={20} color="var(--accent-danger)" />
            <div>{actionError}</div>
          </div>
          <button className="btn-icon" onClick={() => setActionError(null)}>
            <X size={16} />
          </button>
        </div>
      )}

      {/* Actionable Queues Bar */}
      <section className="queues-navbar glass-panel">
        <div className="queues-tabs">
          <button 
            className={`queue-tab ${selectedQueue === 'all' ? 'active' : ''}`}
            onClick={() => setSelectedQueue('all')}
            id="tab-all-items"
          >
            <Layers size={16} />
            All Items
          </button>
          <button 
            className={`queue-tab ${selectedQueue === 'assigned' ? 'active' : ''}`}
            onClick={() => setSelectedQueue('assigned')}
            id="tab-assigned-to-me"
          >
            <UserCheck size={16} />
            Assigned to Me
          </button>
          <button 
            className={`queue-tab ${selectedQueue === 'urgent' ? 'active' : ''}`}
            onClick={() => setSelectedQueue('urgent')}
            id="tab-unassigned-urgent"
          >
            <AlertTriangle size={16} />
            Unassigned Urgent
          </button>
          <button 
            className={`queue-tab ${selectedQueue === 'approval' ? 'active' : ''}`}
            onClick={() => setSelectedQueue('approval')}
            id="tab-awaiting-approval"
          >
            <ShieldCheck size={16} />
            Awaiting Approval
          </button>
        </div>

        <button 
          className="btn btn-primary"
          onClick={() => setIsCreateModalOpen(true)}
          id="btn-create-work-item"
        >
          <Plus size={16} />
          New Work Item
        </button>
      </section>

      {/* Main Workspace Layout: Left Sidebar Filter + Items List + Right Timeline Detail */}
      <div className="workspace-layout">
        {/* Left Column: Filter & Items Feed */}
        <section className="items-list-pane glass-panel">
          {/* Filter Bar */}
          <div className="filter-controls">
            <div className="search-box">
              <Search size={16} className="search-icon" />
              <input 
                type="text" 
                placeholder="Search items by title..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="search-input"
              />
              {searchQuery && (
                <button className="btn-icon" onClick={() => setSearchQuery('')}>
                  <X size={14} />
                </button>
              )}
            </div>

            <div className="filter-selects">
              <select 
                value={selectedTeam} 
                onChange={(e) => setSelectedTeam(e.target.value)}
                className="filter-select"
              >
                <option value="">All Permitted Teams</option>
                {currentUser?.memberships?.map(m => (
                  <option key={m.team_id} value={m.team_id}>{m.team_name} ({m.role})</option>
                ))}
              </select>

              <select 
                value={selectedPriority} 
                onChange={(e) => setSelectedPriority(e.target.value)}
                className="filter-select"
              >
                <option value="">Any Priority</option>
                <option value="urgent">Urgent</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>

              <select 
                value={selectedStatus} 
                onChange={(e) => setSelectedStatus(e.target.value)}
                className="filter-select"
              >
                <option value="">Any Status</option>
                <option value="Open">Open</option>
                <option value="In Progress">In Progress</option>
                <option value="Awaiting Approval">Awaiting Approval</option>
                <option value="Resolved">Resolved</option>
                <option value="Closed">Closed</option>
              </select>
            </div>
          </div>

          {/* Items Scrollable List */}
          <div className="items-scroll-area">
            {isLoadingItems ? (
              <div className="pane-loader">
                <RefreshCw size={24} className="spin-icon" />
                <span>Fetching items...</span>
              </div>
            ) : itemsData?.items?.length === 0 ? (
              <div className="pane-empty">
                <FileText size={32} color="var(--text-muted)" />
                <p>No operational items match this queue or filter.</p>
              </div>
            ) : (
              itemsData?.items?.map(item => {
                const isSelected = item.id === selectedItemId
                return (
                  <article 
                    key={item.id}
                    className={`item-summary-card ${isSelected ? 'selected' : ''}`}
                    onClick={() => {
                      setSelectedItemId(item.id)
                      setConflictBanner(null)
                      setActionError(null)
                    }}
                    id={`item-card-${item.id}`}
                  >
                    <div className="item-card-top">
                      <span className={`priority-pill ${item.priority}`}>
                        {item.priority}
                      </span>
                      <span className={`status-pill ${item.status.toLowerCase().replace(/\s+/g, '-')}`}>
                        {item.status}
                      </span>
                      <span className="version-pill">v{item.version}</span>
                    </div>

                    <h3 className="item-card-title">{item.title}</h3>

                    <div className="item-card-meta">
                      <span className="item-meta-team">{item.team_name}</span>
                      <span className="item-meta-assignee">
                        {item.assignee_name ? `Assignee: ${item.assignee_name}` : 'Unassigned'}
                      </span>
                    </div>
                  </article>
                )
              })
            )}
          </div>
        </section>

        {/* Right Column: Timeline-First Detail View */}
        <section className="timeline-detail-pane glass-panel">
          {selectedItem ? (
            <div className="item-detail-content">
              {/* Item Header & Metadata */}
              <div className="item-detail-header">
                <div className="item-detail-badges">
                  <span className={`priority-pill ${selectedItem.priority}`}>{selectedItem.priority}</span>
                  <span className={`status-pill ${selectedItem.status.toLowerCase().replace(/\s+/g, '-')}`}>
                    {selectedItem.status}
                  </span>
                  <span className="version-pill">v{selectedItem.version}</span>
                  <span className="type-pill">{selectedItem.type}</span>
                </div>

                <div className="item-detail-actions-top">
                  <button 
                    className="btn btn-secondary-sm"
                    onClick={() => setIsEditModalOpen(true)}
                    disabled={isViewer}
                  >
                    Edit Details
                  </button>
                </div>
              </div>

              <h2 className="item-detail-title">{selectedItem.title}</h2>
              <p className="item-detail-description">{selectedItem.description}</p>

              {/* What Requires Attention Next Banner */}
              <div className="attention-card glass-panel">
                <div className="attention-header">
                  <Clock size={18} color="var(--accent-primary)" />
                  <strong>What requires attention next:</strong>
                </div>
                <p className="attention-body">{getNextAttentionText(selectedItem)}</p>

                {/* Inline Action Bar */}
                <div className="attention-action-bar">
                  {/* Claim Button */}
                  {!selectedItem.assignee_id && (
                    <button 
                      className="btn btn-primary-sm"
                      onClick={() => claimMutation.mutate()}
                      disabled={claimMutation.isPending || isViewer}
                      id="btn-claim-item"
                    >
                      <UserCheck size={14} />
                      {claimMutation.isPending ? 'Claiming...' : 'Claim Item'}
                    </button>
                  )}

                  {/* Valid State Transitions */}
                  {VALID_TRANSITIONS[selectedItem.status]?.map(targetStatus => {
                    const requiresLead = ['Resolved', 'Closed'].includes(targetStatus)
                    const canAdvance = !requiresLead || isTeamLeadOrAdmin
                    return (
                      <button 
                        key={targetStatus}
                        className={`btn btn-secondary-sm ${requiresLead ? 'btn-lead-gate' : ''}`}
                        onClick={() => setTargetTransitionStatus(targetStatus)}
                        disabled={transitionMutation.isPending || isViewer || !canAdvance}
                        title={requiresLead && !isTeamLeadOrAdmin ? 'Lead/Admin role required' : ''}
                      >
                        {requiresLead && <ShieldCheck size={14} />}
                        Move to {targetStatus}
                      </button>
                    )
                  })}
                </div>
              </div>

              {/* Transition Confirmation Dialog */}
              {targetTransitionStatus && (
                <div className="transition-confirm-panel glass-panel">
                  <h4>Confirm State Transition: {selectedItem.status} → {targetTransitionStatus}</h4>
                  <input 
                    type="text" 
                    placeholder="Optional transition reason or sign-off note..."
                    value={transitionComment}
                    onChange={(e) => setTransitionComment(e.target.value)}
                    className="form-input"
                  />
                  <div className="modal-actions">
                    <button 
                      className="btn btn-secondary-sm" 
                      onClick={() => setTargetTransitionStatus(null)}
                    >
                      Cancel
                    </button>
                    <button 
                      className="btn btn-primary-sm"
                      onClick={() => transitionMutation.mutate({ 
                        targetStatus: targetTransitionStatus, 
                        comment: transitionComment 
                      })}
                      disabled={transitionMutation.isPending}
                    >
                      {transitionMutation.isPending ? 'Advancing...' : 'Confirm Transition'}
                    </button>
                  </div>
                </div>
              )}

              {/* Vertical Chronological Timeline */}
              <div className="activity-timeline-section">
                <div className="timeline-header-bar">
                  <h3 className="timeline-section-heading">
                    <History size={18} color="var(--accent-secondary)" />
                    Activity & Audit Chronology ({itemActivity.length} events)
                  </h3>
                </div>

                <div className="vertical-timeline-container">
                  <div className="vertical-timeline-track" />
                  
                  {itemActivity.map((event, idx) => (
                    <div key={event.id || idx} className="timeline-event-row">
                      <div className="timeline-event-marker">
                        <div className={`event-marker-dot ${event.event_type}`} />
                      </div>
                      <div className="timeline-event-card glass-panel">
                        <div className="event-meta-line">
                          <span className="event-actor-name">{event.actor_name || 'System Operator'}</span>
                          <span className={`event-type-badge ${event.event_type}`}>{event.event_type}</span>
                          <span className="event-timestamp">
                            {new Date(event.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' })}
                          </span>
                        </div>

                        {event.comment_body && (
                          <div className="event-body-text">{event.comment_body}</div>
                        )}

                        {event.old_value && event.new_value && (
                          <div className="event-diff-block">
                            {Object.keys(event.new_value).map(k => (
                              <div key={k} className="diff-item">
                                <span className="diff-key">{k}:</span> 
                                <span className="diff-old">{String(event.old_value?.[k] ?? '—')}</span>
                                <ArrowRight size={12} className="diff-arrow" />
                                <span className="diff-new">{String(event.new_value?.[k])}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Add Comment Input Box */}
                <div className="timeline-add-comment glass-panel">
                  <input 
                    type="text"
                    placeholder={isViewer ? 'Viewer role is read-only' : 'Post operational update or timeline comment...'}
                    value={commentText}
                    onChange={(e) => setCommentText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && commentText.trim() && !isViewer) {
                        commentMutation.mutate(commentText)
                      }
                    }}
                    disabled={isViewer || commentMutation.isPending}
                    className="comment-input"
                  />
                  <button 
                    className="btn btn-primary-sm"
                    onClick={() => commentMutation.mutate(commentText)}
                    disabled={!commentText.trim() || isViewer || commentMutation.isPending}
                  >
                    <Send size={14} />
                    {commentMutation.isPending ? 'Posting...' : 'Post'}
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="pane-empty">
              <Clock size={36} color="var(--text-muted)" />
              <p>Select an operational work item from the feed to view its chronology.</p>
            </div>
          )}
        </section>
      </div>

      {/* New Work Item Modal */}
      {isCreateModalOpen && (
        <CreateItemModal 
          currentUser={currentUser}
          onClose={() => setIsCreateModalOpen(false)}
          onSuccess={(newItem) => {
            setIsCreateModalOpen(false)
            queryClient.invalidateQueries({ queryKey: ['items'] })
            setSelectedItemId(newItem.id)
          }}
        />
      )}

      {/* Edit Work Item Modal (with Optimistic Locking) */}
      {isEditModalOpen && selectedItem && (
        <EditItemModal 
          item={selectedItem}
          onClose={() => setIsEditModalOpen(false)}
          onSuccess={(updated) => {
            setIsEditModalOpen(false)
            setConflictBanner(null)
            queryClient.setQueryData(['item', selectedItem.id], updated)
            refetchItems()
            refetchActivity()
          }}
          onConflict={(err) => {
            setIsEditModalOpen(false)
            setConflictBanner({
              type: '409 Conflict',
              message: err.message || 'Item was updated by another operator while you were editing.',
              action: () => {
                refetchSelectedItem()
                refetchItems()
                setConflictBanner(null)
              }
            })
          }}
        />
      )}
    </div>
  )
}

// Modal Component for Creating Work Item
function CreateItemModal({ currentUser, onClose, onSuccess }) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [type, setType] = useState('incident')
  const [priority, setPriority] = useState('high')
  const [teamId, setTeamId] = useState(currentUser?.memberships?.[0]?.team_id || '')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState(null)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setIsSubmitting(true)
    setError(null)

    try {
      const idempotencyKey = `create-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`
      const newItem = await createItem({
        title,
        description,
        type,
        priority,
        team_id: teamId,
      }, idempotencyKey)
      onSuccess(newItem)
    } catch (err) {
      setError(err.message)
      setIsSubmitting(false)
    }
  }

  return (
    <div className="modal-backdrop">
      <div className="modal-dialog glass-panel">
        <div className="modal-header">
          <h3>Create Operational Work Item</h3>
          <button className="btn-icon" onClick={onClose}><X size={18} /></button>
        </div>

        {error && <div className="alert-banner error-alert">{error}</div>}

        <form onSubmit={handleSubmit} className="modal-form">
          <div className="form-group">
            <label>Title</label>
            <input 
              type="text" 
              required
              value={title} 
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Core API Latency Spike in EU-West"
              className="form-input"
            />
          </div>

          <div className="form-group">
            <label>Description</label>
            <textarea 
              rows={3}
              value={description} 
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Context, symptoms, and impact..."
              className="form-input"
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Team Scope</label>
              <select 
                value={teamId} 
                onChange={(e) => setTeamId(e.target.value)}
                className="form-input"
                required
              >
                {currentUser?.memberships?.map(m => (
                  <option key={m.team_id} value={m.team_id}>{m.team_name}</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label>Type</label>
              <select value={type} onChange={(e) => setType(e.target.value)} className="form-input">
                <option value="incident">Incident</option>
                <option value="customer_issue">Customer Issue</option>
                <option value="payment">Payment</option>
                <option value="compliance">Compliance</option>
                <option value="task">Task</option>
              </select>
            </div>

            <div className="form-group">
              <label>Priority</label>
              <select value={priority} onChange={(e) => setPriority(e.target.value)} className="form-input">
                <option value="urgent">Urgent</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
            </div>
          </div>

          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={isSubmitting}>
              {isSubmitting ? 'Creating...' : 'Create Item'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// Modal Component for Editing Item with Optimistic Locking
function EditItemModal({ item, onClose, onSuccess, onConflict }) {
  const [title, setTitle] = useState(item.title)
  const [description, setDescription] = useState(item.description)
  const [priority, setPriority] = useState(item.priority)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState(null)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setIsSubmitting(true)
    setError(null)

    try {
      const idempotencyKey = `edit-${item.id}-${Date.now()}`
      const updated = await updateItem(item.id, {
        version: item.version, // Required for optimistic lock check
        title,
        description,
        priority
      }, idempotencyKey)
      onSuccess(updated)
    } catch (err) {
      if (err.status === 409) {
        onConflict(err)
      } else {
        setError(err.message)
        setIsSubmitting(false)
      }
    }
  }

  return (
    <div className="modal-backdrop">
      <div className="modal-dialog glass-panel">
        <div className="modal-header">
          <h3>Edit Work Item (Current Version: v{item.version})</h3>
          <button className="btn-icon" onClick={onClose}><X size={18} /></button>
        </div>

        {error && <div className="alert-banner error-alert">{error}</div>}

        <form onSubmit={handleSubmit} className="modal-form">
          <div className="form-group">
            <label>Title</label>
            <input 
              type="text" 
              required
              value={title} 
              onChange={(e) => setTitle(e.target.value)}
              className="form-input"
            />
          </div>

          <div className="form-group">
            <label>Description</label>
            <textarea 
              rows={4}
              value={description} 
              onChange={(e) => setDescription(e.target.value)}
              className="form-input"
            />
          </div>

          <div className="form-group">
            <label>Priority</label>
            <select value={priority} onChange={(e) => setPriority(e.target.value)} className="form-input">
              <option value="urgent">Urgent</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>

          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={isSubmitting}>
              {isSubmitting ? 'Saving v' + (item.version + 1) + '...' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
