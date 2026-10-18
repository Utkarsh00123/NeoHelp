from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict
from datetime import datetime

class WorkItemCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    description: Optional[str] = None
    type: str = Field(default="task")  # incident, customer_issue, payment, compliance, task
    priority: str = Field(default="medium")  # low, medium, high, urgent
    team_id: str
    due_date: Optional[datetime] = None

class WorkItemUpdate(BaseModel):
    version: int
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[datetime] = None

class WorkItemTransition(BaseModel):
    target_status: str  # Open, In Progress, Awaiting Approval, Resolved, Closed
    comment: Optional[str] = None

class CommentCreate(BaseModel):
    comment: str = Field(..., min_length=1)

class ActivityEventResponse(BaseModel):
    id: str
    work_item_id: str
    actor_id: Optional[str]
    actor_name: Optional[str] = None
    event_type: str
    old_value: Optional[Dict[str, Any]] = None
    new_value: Optional[Dict[str, Any]] = None
    comment_body: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class WorkItemResponse(BaseModel):
    id: str
    title: str
    description: Optional[str]
    type: str
    priority: str
    status: str
    team_id: str
    team_name: Optional[str] = None
    assignee_id: Optional[str]
    assignee_name: Optional[str] = None
    created_by_id: str
    creator_name: Optional[str] = None
    due_date: Optional[datetime]
    version: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class PaginatedWorkItems(BaseModel):
    items: List[WorkItemResponse]
    next_cursor: Optional[str]
    has_more: bool
    total_count: Optional[int] = None
