"""Integration tests for repositories."""

import pytest
import pytest_asyncio

from aegis.auth.models import UserCreate
from aegis.storage.repositories.agents import AgentCreate, AgentUpdate
from aegis.storage.repositories.conversations import ConversationCreate, ConversationUpdate
from aegis.storage.repositories.messages import MessageCreate


# ── User Repository ──────────────────────────────────


@pytest.mark.asyncio
async def test_create_user(repos):
    user = await repos.users.create(
        email="alice@test.com", username="alice",
        password_hash="hash123", display_name="Alice",
    )
    assert user.id.startswith("usr_")
    assert user.email == "alice@test.com"
    assert user.username == "alice"
    assert user.display_name == "Alice"


@pytest.mark.asyncio
async def test_get_user(repos):
    user = await repos.users.create(
        email="bob@test.com", username="bob", password_hash="hash",
    )
    found = await repos.users.get(user.id)
    assert found is not None
    assert found.id == user.id
    assert found.email == "bob@test.com"


@pytest.mark.asyncio
async def test_get_user_not_found(repos):
    found = await repos.users.get("usr_nonexistent")
    assert found is None


@pytest.mark.asyncio
async def test_get_by_email(repos):
    await repos.users.create(
        email="find@test.com", username="findme", password_hash="hash",
    )
    found = await repos.users.get_by_email("find@test.com")
    assert found is not None
    assert found.username == "findme"


@pytest.mark.asyncio
async def test_get_by_email_with_password(repos):
    await repos.users.create(
        email="pwd@test.com", username="pwduser", password_hash="secrethash",
    )
    result = await repos.users.get_by_email_with_password("pwd@test.com")
    assert result is not None
    user, pwd_hash = result
    assert pwd_hash == "secrethash"


# ── Agent Repository ─────────────────────────────────


@pytest.mark.asyncio
async def test_create_agent(repos):
    user = await repos.users.create(
        email="agentowner@test.com", username="agentowner", password_hash="h",
    )
    agent = await repos.agents.create(AgentCreate(
        user_id=user.id, name="MyBot", slug="mybot",
        system_prompt="Be helpful.", allowed_tools=["web_fetch"],
    ))
    assert agent.id.startswith("agt_")
    assert agent.name == "MyBot"
    assert agent.slug == "mybot"
    assert agent.status == "active"
    assert agent.allowed_tools == ["web_fetch"]


@pytest.mark.asyncio
async def test_list_agents_by_user(repos):
    user = await repos.users.create(
        email="lister@test.com", username="lister", password_hash="h",
    )
    await repos.agents.create(AgentCreate(
        user_id=user.id, name="Bot1", slug="bot1",
    ))
    await repos.agents.create(AgentCreate(
        user_id=user.id, name="Bot2", slug="bot2",
    ))
    agents = await repos.agents.list_by_user(user.id)
    assert len(agents) == 2


@pytest.mark.asyncio
async def test_update_agent(repos):
    user = await repos.users.create(
        email="updater@test.com", username="updater", password_hash="h",
    )
    agent = await repos.agents.create(AgentCreate(
        user_id=user.id, name="OldName", slug="old",
    ))
    updated = await repos.agents.update(agent.id, AgentUpdate(
        name="NewName", temperature=0.3,
    ))
    assert updated is not None
    assert updated.name == "NewName"
    assert updated.temperature == 0.3


@pytest.mark.asyncio
async def test_delete_agent(repos):
    user = await repos.users.create(
        email="deleter@test.com", username="deleter", password_hash="h",
    )
    agent = await repos.agents.create(AgentCreate(
        user_id=user.id, name="Doomed", slug="doomed",
    ))
    assert await repos.agents.delete(agent.id) is True
    assert await repos.agents.get(agent.id) is None


@pytest.mark.asyncio
async def test_agent_slug_unique_per_user(repos):
    user = await repos.users.create(
        email="slugtest@test.com", username="slugtest", password_hash="h",
    )
    await repos.agents.create(AgentCreate(
        user_id=user.id, name="Bot", slug="sameslug",
    ))
    with pytest.raises(Exception):  # IntegrityError
        await repos.agents.create(AgentCreate(
            user_id=user.id, name="Bot2", slug="sameslug",
        ))


# ── Conversation Repository ──────────────────────────


@pytest.mark.asyncio
async def test_create_conversation(repos):
    user = await repos.users.create(
        email="convowner@test.com", username="convowner", password_hash="h",
    )
    conv = await repos.conversations.create(ConversationCreate(
        title="Test Chat", user_id=user.id,
    ))
    assert conv.id.startswith("conv_")
    assert conv.title == "Test Chat"


@pytest.mark.asyncio
async def test_list_conversations_by_user(repos):
    user = await repos.users.create(
        email="convuser@test.com", username="convuser", password_hash="h",
    )
    await repos.conversations.create(ConversationCreate(
        title="Chat 1", user_id=user.id,
    ))
    await repos.conversations.create(ConversationCreate(
        title="Chat 2", user_id=user.id,
    ))
    convs = await repos.conversations.list_all(user_id=user.id)
    assert len(convs) == 2


@pytest.mark.asyncio
async def test_conversation_tenant_isolation(repos):
    user1 = await repos.users.create(
        email="u1@test.com", username="u1", password_hash="h",
    )
    user2 = await repos.users.create(
        email="u2@test.com", username="u2", password_hash="h",
    )
    await repos.conversations.create(ConversationCreate(
        title="User1 Chat", user_id=user1.id,
    ))
    await repos.conversations.create(ConversationCreate(
        title="User2 Chat", user_id=user2.id,
    ))
    u1_convs = await repos.conversations.list_all(user_id=user1.id)
    u2_convs = await repos.conversations.list_all(user_id=user2.id)
    assert len(u1_convs) == 1
    assert len(u2_convs) == 1
    assert u1_convs[0].title == "User1 Chat"
    assert u2_convs[0].title == "User2 Chat"


@pytest.mark.asyncio
async def test_update_conversation(repos):
    conv = await repos.conversations.create(ConversationCreate(title="Old"))
    updated = await repos.conversations.update(conv.id, ConversationUpdate(title="New"))
    assert updated.title == "New"


@pytest.mark.asyncio
async def test_delete_conversation(repos):
    conv = await repos.conversations.create(ConversationCreate(title="Doomed"))
    await repos.conversations.delete(conv.id)
    with pytest.raises(Exception):
        await repos.conversations.get(conv.id)


# ── Message Repository ───────────────────────────────


@pytest.mark.asyncio
async def test_create_and_list_messages(repos):
    conv = await repos.conversations.create(ConversationCreate(title="MsgTest"))
    msg = await repos.messages.create(MessageCreate(
        conversation_id=conv.id, role="user", content="Hello",
    ))
    assert msg.id.startswith("msg_")
    assert msg.role == "user"

    msgs = await repos.messages.get_by_conversation(conv.id)
    assert len(msgs) == 1
    assert msgs[0].get_text_content() == "Hello"


# ── API Key Repository ───────────────────────────────


@pytest.mark.asyncio
async def test_create_and_verify_api_key(repos):
    user = await repos.users.create(
        email="keyuser@test.com", username="keyuser", password_hash="h",
    )
    result = await repos.api_keys.create(user.id, name="my-key")
    assert result.secret.startswith("ak_")
    assert result.api_key.name == "my-key"

    # Verify the key
    verified = await repos.api_keys.verify(result.secret)
    assert verified is not None
    assert verified.user_id == user.id


@pytest.mark.asyncio
async def test_verify_invalid_api_key(repos):
    verified = await repos.api_keys.verify("ak_doesnotexist")
    assert verified is None


@pytest.mark.asyncio
async def test_revoke_api_key(repos):
    user = await repos.users.create(
        email="revoker@test.com", username="revoker", password_hash="h",
    )
    result = await repos.api_keys.create(user.id)

    assert await repos.api_keys.revoke(result.api_key.id, user.id) is True

    # Key should no longer verify
    verified = await repos.api_keys.verify(result.secret)
    assert verified is None


@pytest.mark.asyncio
async def test_list_api_keys(repos):
    user = await repos.users.create(
        email="keylist@test.com", username="keylist", password_hash="h",
    )
    await repos.api_keys.create(user.id, name="key1")
    await repos.api_keys.create(user.id, name="key2")

    keys = await repos.api_keys.list_by_user(user.id)
    assert len(keys) == 2
    names = {k.name for k in keys}
    assert names == {"key1", "key2"}
