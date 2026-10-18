import React, { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
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
  addComment,
  clearAllItems,
  reseedItems
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

  // App Filter States (Server-side queries only)
  const [selectedQueue, setSelectedQueue] = useState('all') // 'all' | 'assigned' | 'urgent' | 'approval'
  const [selectedTeam, setSelectedTeam] = useState('')
  const [selectedStatus, setSelectedStatus] = useState('')
  const [selectedPriority, setSelectedPriority] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedItemId, setSelectedItemId] = useState(null)

  // Modals & User Input States
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [isEditModalOpen, setIsEditModalOpen] = useState(false)
  const [reconciliationPrompt, setReconciliationPrompt] = useState(null)
  const [actionNotice, setActionNotice] = useState(null)
  const [commentInput, setCommentInput] = useState('')
  const [transitionPrompt, setTransitionPrompt] = useState(null)
  const [transitionNote, setTransitionNote] = useState('')

  // System Health
  const { data: health } = useQuery({
    queryKey: ['system-health'],
    queryFn: fetchHealth,
    refetchInterval: 30000,
  })

  // Seeded Users Directory for Role-Switcher
  const { data: users = [] } = useQuery({
    queryKey: ['users-directory'],
    queryFn: fetchUsers,
  })

  // Authenticated User Profile
  const { data: currentUser, refetch: refetchMe } = useQuery({
    queryKey: ['current-user'],
    queryFn: fetchMe,
    retry: false,
  })

  // Auto-login default user if no token exists
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

  // Server-side filtered items query with cursor pagination support
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

  // Selected item detail query
  const { data: selectedItem, refetch: refetchSelectedItem } = useQuery({
    queryKey: ['item', selectedItemId],
    queryFn: () => fetchItem(selectedItemId),
    enabled: !!selectedItemId,
  })

  // Master vertical activity timeline query
  const { data: itemActivity = [], refetch: refetchActivity } = useQuery({
    queryKey: ['item-activity', selectedItemId],
    queryFn: () => fetchItemActivity(selectedItemId),
    enabled: !!selectedItemId,
    refetchInterval: 10000,
  })

  // Auto-select first item when items load if none selected
  useEffect(() => {
    if (!selectedItemId && itemsData?.items?.length > 0) {
      setSelectedItemId(itemsData.items[0].id)
    }
  }, [itemsData, selectedItemId])

  // Role Switcher
  const handleSwitchUser = async (userId) => {
    try {
      await switchUser(userId)
      setReconciliationPrompt(null)
      setActionNotice(null)
      await refetchMe()
      await queryClient.invalidateQueries({ queryKey: ['items'] })
      if (selectedItemId) {
        await queryClient.invalidateQueries({ queryKey: ['item', selectedItemId] })
      }
    } catch (err) {
      setActionNotice(`User switch error: ${err.message}`)
    }
  }

  // Reload Changed Item (Reconciliation Action)
  const handleReloadItem = async () => {
    setReconciliationPrompt(null)
    await refetchSelectedItem()
    await refetchItems()
    await refetchActivity()
  }

  // OPTIMISTIC MUTATION: Claim Item with Automatic Rollback
  const claimMutation = useMutation({
    mutationFn: () => claimItem(selectedItemId, `claim-${selectedItemId}-${Date.now()}`),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: ['item', selectedItemId] })
      await queryClient.cancelQueries({ queryKey: ['item-activity', selectedItemId] })
      const previousItem = queryClient.getQueryData(['item', selectedItemId])
      const previousActivity = queryClient.getQueryData(['item-activity', selectedItemId])

      // Optimistic update: Assign to current user immediately
      if (previousItem) {
        queryClient.setQueryData(['item', selectedItemId], {
          ...previousItem,
          assignee_id: currentUser.id,
          assignee_name: currentUser.full_name,
          version: previousItem.version + 1,
        })
      }

      // Optimistically append claim event to timeline
      if (previousActivity) {
        const optimisticEvent = {
          id: `opt-claim-${Date.now()}`,
          actor_id: currentUser.id,
          actor_name: currentUser.full_name,
          event_type: 'claimed',
          comment_body: `Item claimed by ${currentUser.full_name}.`,
          created_at: new Date().toISOString(),
        }
        queryClient.setQueryData(['item-activity', selectedItemId], [optimisticEvent, ...previousActivity])
      }

      return { previousItem, previousActivity }
    },
    onError: (err, variables, context) => {
      // Automatic Rollback to previous state
      if (context?.previousItem) {
        queryClient.setQueryData(['item', selectedItemId], context.previousItem)
      }
      if (context?.previousActivity) {
        queryClient.setQueryData(['item-activity', selectedItemId], context.previousActivity)
      }

      // User-friendly prompt to reload
      if (err.status === 409) {
        setReconciliationPrompt({
          title: 'Concurrency Conflict (409)',
          message: 'This task was already claimed by another operator concurrently. The optimistic update has been rolled back.',
        })
      } else {
        setActionNotice(`Claim failed: ${err.message}`)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['item', selectedItemId] })
      queryClient.invalidateQueries({ queryKey: ['items'] })
      queryClient.invalidateQueries({ queryKey: ['item-activity', selectedItemId] })
    }
  })

  // OPTIMISTIC MUTATION: Transition State with Automatic Rollback
  const transitionMutation = useMutation({
    mutationFn: ({ targetStatus, comment }) => 
      transitionItem(selectedItemId, { target_status: targetStatus, comment }, `trans-${selectedItemId}-${targetStatus}-${Date.now()}`),
    onMutate: async ({ targetStatus, comment }) => {
      await queryClient.cancelQueries({ queryKey: ['item', selectedItemId] })
      await queryClient.cancelQueries({ queryKey: ['item-activity', selectedItemId] })
      const previousItem = queryClient.getQueryData(['item', selectedItemId])
      const previousActivity = queryClient.getQueryData(['item-activity', selectedItemId])

      // Optimistic update: Update status immediately
      if (previousItem) {
        queryClient.setQueryData(['item', selectedItemId], {
          ...previousItem,
          status: targetStatus,
          version: previousItem.version + 1,
        })
      }

      // Optimistically add transition to timeline
      if (previousActivity) {
        const optimisticEvent = {
          id: `opt-trans-${Date.now()}`,
          actor_id: currentUser.id,
          actor_name: currentUser.full_name,
          event_type: 'transitioned',
          old_value: { status: previousItem?.status },
          new_value: { status: targetStatus },
          comment_body: comment || `State moved from ${previousItem?.status} to ${targetStatus}.`,
          created_at: new Date().toISOString(),
        }
        queryClient.setQueryData(['item-activity', selectedItemId], [optimisticEvent, ...previousActivity])
      }

      setTransitionPrompt(null)
      setTransitionNote('')
      return { previousItem, previousActivity }
    },
    onError: (err, variables, context) => {
      // Automatic Rollback to previous state
      if (context?.previousItem) {
        queryClient.setQueryData(['item', selectedItemId], context.previousItem)
      }
      if (context?.previousActivity) {
        queryClient.setQueryData(['item-activity', selectedItemId], context.previousActivity)
      }

      if (err.status === 409) {
        setReconciliationPrompt({
          title: 'Stale Edit Conflict (409)',
          message: 'The item state was modified by another operator. Optimistic change rolled back. Please reload.',
        })
      } else if (err.status === 403) {
        setActionNotice(`Authorization Error (403): ${err.message}. Optimistic change rolled back.`)
      } else {
        setActionNotice(`Transition failed: ${err.message}`)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['item', selectedItemId] })
      queryClient.invalidateQueries({ queryKey: ['items'] })
      queryClient.invalidateQueries({ queryKey: ['item-activity', selectedItemId] })
    }
  })

  // OPTIMISTIC MUTATION: Add Comment to Timeline
  const commentMutation = useMutation({
    mutationFn: (text) => addComment(selectedItemId, text),
    onMutate: async (text) => {
      await queryClient.cancelQueries({ queryKey: ['item-activity', selectedItemId] })
      const previousActivity = queryClient.getQueryData(['item-activity', selectedItemId])

      if (previousActivity) {
        const optimisticEvent = {
          id: `opt-comment-${Date.now()}`,
          actor_id: currentUser.id,
          actor_name: currentUser.full_name,
          event_type: 'commented',
          comment_body: text,
          created_at: new Date().toISOString(),
        }
        queryClient.setQueryData(['item-activity', selectedItemId], [optimisticEvent, ...previousActivity])
      }
      setCommentInput('')
      return { previousActivity }
    },
    onError: (err, variables, context) => {
      if (context?.previousActivity) {
        queryClient.setQueryData(['item-activity', selectedItemId], context.previousActivity)
      }
      setActionNotice(`Failed to post comment: ${err.message}`)
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['item-activity', selectedItemId] })
    }
  })

  // RBAC checks for selected item
  const currentMembership = currentUser?.memberships?.find(m => m.team_id === selectedItem?.team_id)
  const isTeamLeadOrAdmin = currentMembership?.role === 'Lead' || currentMembership?.role === 'Admin'
  const isViewer = currentMembership?.role === 'Viewer'

  const handleClearAll = async () => {
    if (!window.confirm("Are you sure you want to clear all work items to start with a blank board?")) return;
    try {
      await clearAllItems();
      setSelectedItemId(null);
      queryClient.invalidateQueries({ queryKey: ['items'] });
      setActionNotice("All tasks cleared! The board is now a completely blank slate for testing.");
    } catch (err) {
      setActionNotice(`Failed to clear items: ${err.message}`);
    }
  };

  const handleReseed = async () => {
    try {
      await reseedItems(20);
      queryClient.invalidateQueries({ queryKey: ['items'] });
      setActionNotice("Seeded 20 sample items into the board.");
    } catch (err) {
      setActionNotice(`Failed to reseed: ${err.message}`);
    }
  };

  return (
    <div className="layout-root">
      {/* Top Application Bar */}
      <header className="app-topbar">
        <div className="brand-group">
          <span className="brand-name">NeoHelp</span>
          <span className="brand-pipe">/</span>
          <span className="brand-subtitle">Timeline Operations</span>
        </div>

        {/* System Health Indicators */}
        <div className="health-status-bar">
          <span className="health-item">
            API: <strong className="highlight-text">{health ? 'Connected' : 'Degraded'}</strong>
          </span>
          <span className="health-separator">•</span>
          <span className="health-item">
            Database: <strong className="highlight-text">{health?.database?.includes('healthy') ? 'Active' : 'Degraded'}</strong>
          </span>
          <span className="health-separator">•</span>
          <span className="health-item">
            Outbox: <strong className="highlight-text">{health?.redis?.includes('healthy') ? 'Running' : 'Degraded'}</strong>
          </span>
        </div>

        {/* User Role Switcher */}
        <div className="role-switcher-box">
          <span className="role-label">Active User:</span>
          <select 
            value={currentUser?.id || ''}
            onChange={(e) => handleSwitchUser(e.target.value)}
            className="user-selector"
          >
            {users.map(u => (
              <option key={u.id} value={u.id}>
                {u.full_name} ({u.email})
              </option>
            ))}
          </select>
        </div>
      </header>

      {/* Reconciliation Prompt (409 Conflict / 403 Forbidden Rollback Alert) */}
      {reconciliationPrompt && (
        <div className="banner-reconcile">
          <div>
            <strong>{reconciliationPrompt.title}:</strong> {reconciliationPrompt.message}
          </div>
          <button className="btn-action-primary" onClick={handleReloadItem}>
            Reload Changed Item
          </button>
        </div>
      )}

      {/* Action / Authorization Notice */}
      {actionNotice && (
        <div className="banner-notice">
          <div>{actionNotice}</div>
          <button className="btn-text-close" onClick={() => setActionNotice(null)}>Dismiss</button>
        </div>
      )}

      {/* Predefined Actionable Queue Views */}
      <nav className="queue-nav-bar">
        <div className="queue-links">
          <button 
            className={`queue-btn ${selectedQueue === 'all' ? 'active' : ''}`}
            onClick={() => setSelectedQueue('all')}
          >
            All Items
          </button>
          <button 
            className={`queue-btn ${selectedQueue === 'assigned' ? 'active' : ''}`}
            onClick={() => setSelectedQueue('assigned')}
          >
            Assigned to me
          </button>
          <button 
            className={`queue-btn ${selectedQueue === 'urgent' ? 'active' : ''}`}
            onClick={() => setSelectedQueue('urgent')}
          >
            Unassigned urgent
          </button>
          <button 
            className={`queue-btn ${selectedQueue === 'approval' ? 'active' : ''}`}
            onClick={() => setSelectedQueue('approval')}
          >
            Awaiting my approval
          </button>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <button 
            className="btn-action-secondary"
            onClick={handleClearAll}
            title="Wipe all tasks to start with a blank board"
            style={{ fontSize: '0.825rem', padding: '0.45rem 0.85rem' }}
          >
            Clear All Tasks (Blank Slate)
          </button>
          <button 
            className="btn-create-task"
            onClick={() => setIsCreateModalOpen(true)}
          >
            + New Task
          </button>
        </div>
      </nav>

      {/* Master 2-Column Split View: Filtered Dashboard (Left) + Master Timeline (Right) */}
      <main className="main-content-split">
        {/* Left Column: Server-Side Filtered Feed & Cursor List */}
        <section className="feed-pane">
          <div className="feed-filter-bar">
            <input 
              type="text" 
              placeholder="Search items by title..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="feed-search-input"
            />

            <div className="feed-select-row">
              <select 
                value={selectedTeam} 
                onChange={(e) => setSelectedTeam(e.target.value)}
                className="feed-select"
              >
                <option value="">All Teams</option>
                {currentUser?.memberships?.map(m => (
                  <option key={m.team_id} value={m.team_id}>{m.team_name} ({m.role})</option>
                ))}
              </select>

              <select 
                value={selectedStatus} 
                onChange={(e) => setSelectedStatus(e.target.value)}
                className="feed-select"
              >
                <option value="">All Statuses</option>
                <option value="Open">Open</option>
                <option value="In Progress">In Progress</option>
                <option value="Awaiting Approval">Awaiting Approval</option>
                <option value="Resolved">Resolved</option>
                <option value="Closed">Closed</option>
              </select>

              <select 
                value={selectedPriority} 
                onChange={(e) => setSelectedPriority(e.target.value)}
                className="feed-select"
              >
                <option value="">All Priorities</option>
                <option value="urgent">Urgent</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
            </div>
          </div>

          <div className="feed-items-list">
            {isLoadingItems ? (
              <div className="empty-state-text">Loading operational queue...</div>
            ) : itemsData?.items?.length === 0 ? (
              <div className="empty-state-text">No items found for this filter.</div>
            ) : (
              itemsData?.items?.map(item => {
                const isSelected = item.id === selectedItemId
                return (
                  <div 
                    key={item.id}
                    className={`feed-item-card ${isSelected ? 'selected' : ''}`}
                    onClick={() => {
                      setSelectedItemId(item.id)
                      setReconciliationPrompt(null)
                      setActionNotice(null)
                    }}
                  >
                    <div className="item-card-header">
                      <span className="item-card-title">{item.title}</span>
                      <span className="item-version-tag">v{item.version}</span>
                    </div>

                    <div className="item-card-sub">
                      <span>Status: <strong>{item.status}</strong></span>
                      <span>•</span>
                      <span>Priority: <strong>{item.priority}</strong></span>
                      <span>•</span>
                      <span>{item.team_name}</span>
                    </div>

                    <div className="item-card-footer">
                      <span>{item.assignee_name ? `Assigned to: ${item.assignee_name}` : 'Unassigned'}</span>
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </section>

        {/* Right Column: Master Timeline & Core Details */}
        <section className="timeline-pane">
          {selectedItem ? (
            <div className="timeline-content">
              {/* Item Details Header */}
              <div className="item-summary-box">
                <div className="summary-top-row">
                  <div>
                    <h2 className="item-main-title">{selectedItem.title}</h2>
                    <div className="item-badges-line">
                      <span className="badge-pill">Status: {selectedItem.status}</span>
                      <span className="badge-pill">Priority: {selectedItem.priority}</span>
                      <span className="badge-pill">Type: {selectedItem.type}</span>
                      <span className="badge-pill">Team: {selectedItem.team_name}</span>
                      <span className="badge-pill">Version: v{selectedItem.version}</span>
                    </div>
                  </div>

                  <div className="summary-actions">
                    <button 
                      className="btn-action-secondary"
                      onClick={() => setIsEditModalOpen(true)}
                      disabled={isViewer}
                    >
                      Edit
                    </button>
                  </div>
                </div>

                <p className="item-main-description">{selectedItem.description}</p>

                {/* Next Action & Interactive Controls */}
                <div className="action-control-bar">
                  {!selectedItem.assignee_id && (
                    <button 
                      className="btn-action-primary"
                      onClick={() => claimMutation.mutate()}
                      disabled={claimMutation.isPending || isViewer}
                    >
                      Claim Task
                    </button>
                  )}

                  {VALID_TRANSITIONS[selectedItem.status]?.map(targetStatus => {
                    const requiresLead = ['Resolved', 'Closed'].includes(targetStatus)
                    const canAdvance = !requiresLead || isTeamLeadOrAdmin
                    return (
                      <button 
                        key={targetStatus}
                        className={`btn-action-secondary ${requiresLead ? 'btn-highlight' : ''}`}
                        onClick={() => setTransitionPrompt(targetStatus)}
                        disabled={transitionMutation.isPending || isViewer || !canAdvance}
                        title={requiresLead && !isTeamLeadOrAdmin ? 'Lead or Admin role required' : ''}
                      >
                        Advance to {targetStatus}
                      </button>
                    )
                  })}
                </div>

                {/* State Transition Modal Input */}
                {transitionPrompt && (
                  <div className="transition-prompt-box">
                    <div>Confirm State Jump: <strong>{selectedItem.status} → {transitionPrompt}</strong></div>
                    <input 
                      type="text" 
                      placeholder="Optional transition reason or sign-off note..."
                      value={transitionNote}
                      onChange={(e) => setTransitionNote(e.target.value)}
                      className="transition-note-input"
                    />
                    <div className="transition-prompt-btns">
                      <button 
                        className="btn-action-secondary" 
                        onClick={() => setTransitionPrompt(null)}
                      >
                        Cancel
                      </button>
                      <button 
                        className="btn-action-primary"
                        onClick={() => transitionMutation.mutate({ 
                          targetStatus: transitionPrompt, 
                          comment: transitionNote 
                        })}
                        disabled={transitionMutation.isPending}
                      >
                        Confirm
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* Master Vertical Timeline */}
              <div className="master-timeline-section">
                <h3 className="timeline-title">
                  Activity Timeline ({itemActivity.length} events recorded)
                </h3>

                <div className="timeline-stream">
                  {itemActivity.map((event, idx) => (
                    <div key={event.id || idx} className="timeline-entry">
                      <div className="timeline-marker" />
                      <div className="timeline-card">
                        <div className="timeline-card-meta">
                          <span className="timeline-actor">{event.actor_name || 'System'}</span>
                          <span className="timeline-event-type">{event.event_type}</span>
                          <span className="timeline-time">
                            {new Date(event.created_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })}
                          </span>
                        </div>

                        {event.comment_body && (
                          <div className="timeline-comment">{event.comment_body}</div>
                        )}

                        {event.old_value && event.new_value && (
                          <div className="timeline-diff">
                            {Object.keys(event.new_value).map(k => (
                              <div key={k} className="diff-line">
                                <span>{k}:</span>
                                <span className="diff-old">{String(event.old_value?.[k] ?? '—')}</span>
                                <span>→</span>
                                <span className="diff-new">{String(event.new_value?.[k])}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Post Comment Input */}
                <div className="comment-composer">
                  <input 
                    type="text" 
                    placeholder={isViewer ? 'Viewer role is read-only' : 'Post operational update or comment to timeline...'}
                    value={commentInput}
                    onChange={(e) => setCommentInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && commentInput.trim() && !isViewer) {
                        commentMutation.mutate(commentInput)
                      }
                    }}
                    disabled={isViewer || commentMutation.isPending}
                    className="composer-input"
                  />
                  <button 
                    className="btn-action-primary"
                    onClick={() => commentMutation.mutate(commentInput)}
                    disabled={!commentInput.trim() || isViewer || commentMutation.isPending}
                  >
                    Post Comment
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="empty-state-text">Select an item from the queue to view its activity timeline.</div>
          )}
        </section>
      </main>

      {/* Create Task Modal */}
      {isCreateModalOpen && (
        <CreateTaskModal 
          currentUser={currentUser}
          onClose={() => setIsCreateModalOpen(false)}
          onSuccess={(newItem) => {
            setIsCreateModalOpen(false)
            queryClient.invalidateQueries({ queryKey: ['items'] })
            setSelectedItemId(newItem.id)
          }}
        />
      )}

      {/* Edit Task Modal (with Optimistic Locking) */}
      {isEditModalOpen && selectedItem && (
        <EditTaskModal 
          item={selectedItem}
          onClose={() => setIsEditModalOpen(false)}
          onSuccess={(updated) => {
            setIsEditModalOpen(false)
            setReconciliationPrompt(null)
            queryClient.setQueryData(['item', selectedItem.id], updated)
            refetchItems()
            refetchActivity()
          }}
          onConflict={() => {
            setIsEditModalOpen(false)
            setReconciliationPrompt({
              title: 'Stale Edit Conflict (409)',
              message: 'This task was modified by another operator while you were editing. Please reload.',
            })
          }}
        />
      )}
    </div>
  )
}

// Modal for Creating Tasks
function CreateTaskModal({ currentUser, onClose, onSuccess }) {
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
    <div className="modal-overlay">
      <div className="modal-card">
        <div className="modal-title-row">
          <h3>Create Operational Task</h3>
          <button className="btn-text-close" onClick={onClose}>✕</button>
        </div>

        {error && <div className="banner-notice">{error}</div>}

        <form onSubmit={handleSubmit} className="modal-fields">
          <div className="field-group">
            <label>Title</label>
            <input 
              type="text" 
              required
              value={title} 
              onChange={(e) => setTitle(e.target.value)}
              className="text-input"
            />
          </div>

          <div className="field-group">
            <label>Description</label>
            <textarea 
              rows={3}
              value={description} 
              onChange={(e) => setDescription(e.target.value)}
              className="text-input"
            />
          </div>

          <div className="field-row">
            <div className="field-group">
              <label>Team</label>
              <select value={teamId} onChange={(e) => setTeamId(e.target.value)} className="text-input" required>
                {currentUser?.memberships?.map(m => (
                  <option key={m.team_id} value={m.team_id}>{m.team_name}</option>
                ))}
              </select>
            </div>

            <div className="field-group">
              <label>Type</label>
              <select value={type} onChange={(e) => setType(e.target.value)} className="text-input">
                <option value="incident">Incident</option>
                <option value="customer_issue">Customer Issue</option>
                <option value="payment">Payment</option>
                <option value="compliance">Compliance</option>
                <option value="task">Task</option>
              </select>
            </div>

            <div className="field-group">
              <label>Priority</label>
              <select value={priority} onChange={(e) => setPriority(e.target.value)} className="text-input">
                <option value="urgent">Urgent</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
            </div>
          </div>

          <div className="modal-btn-row">
            <button type="button" className="btn-action-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-action-primary" disabled={isSubmitting}>
              {isSubmitting ? 'Creating...' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// Modal for Editing Tasks (Optimistic Locking)
function EditTaskModal({ item, onClose, onSuccess, onConflict }) {
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
        version: item.version,
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
    <div className="modal-overlay">
      <div className="modal-card">
        <div className="modal-title-row">
          <h3>Edit Task (Version: v{item.version})</h3>
          <button className="btn-text-close" onClick={onClose}>✕</button>
        </div>

        {error && <div className="banner-notice">{error}</div>}

        <form onSubmit={handleSubmit} className="modal-fields">
          <div className="field-group">
            <label>Title</label>
            <input 
              type="text" 
              required
              value={title} 
              onChange={(e) => setTitle(e.target.value)}
              className="text-input"
            />
          </div>

          <div className="field-group">
            <label>Description</label>
            <textarea 
              rows={3}
              value={description} 
              onChange={(e) => setDescription(e.target.value)}
              className="text-input"
            />
          </div>

          <div className="field-group">
            <label>Priority</label>
            <select value={priority} onChange={(e) => setPriority(e.target.value)} className="text-input">
              <option value="urgent">Urgent</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>

          <div className="modal-btn-row">
            <button type="button" className="btn-action-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-action-primary" disabled={isSubmitting}>
              {isSubmitting ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
