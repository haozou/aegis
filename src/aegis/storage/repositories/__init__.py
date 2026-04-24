"""Storage repositories."""

from dataclasses import dataclass

from ..database import Database
from .agents import AgentRepository
from .api_keys import ApiKeyRepository
from .channels import ChannelConnectionRepository
from .conversations import ConversationRepository
from .knowledge import KnowledgeDocRepository
from .messages import MessageRepository
from .scheduled_tasks import ScheduledTaskRepository
from .sessions import SessionRepository
from .users import UserRepository
from .webhooks import WebhookRepository


@dataclass
class Repositories:
    conversations: ConversationRepository
    messages: MessageRepository
    sessions: SessionRepository
    users: UserRepository
    agents: AgentRepository
    api_keys: ApiKeyRepository
    webhooks: WebhookRepository
    scheduled_tasks: ScheduledTaskRepository
    knowledge: KnowledgeDocRepository
    channels: ChannelConnectionRepository


def get_repositories(db: Database) -> Repositories:
    """Create all repositories from a database instance."""
    return Repositories(
        conversations=ConversationRepository(db),
        messages=MessageRepository(db),
        sessions=SessionRepository(db),
        users=UserRepository(db),
        agents=AgentRepository(db),
        api_keys=ApiKeyRepository(db),
        webhooks=WebhookRepository(db),
        scheduled_tasks=ScheduledTaskRepository(db),
        knowledge=KnowledgeDocRepository(db),
        channels=ChannelConnectionRepository(db),
    )
