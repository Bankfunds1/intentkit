import logging
from decimal import Decimal
from typing import List, Optional, Tuple

from epyxid import XID
from fastapi import HTTPException
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.config import config
from models.credit import (
    DEFAULT_PLATFORM_ACCOUNT_ADJUSTMENT,
    DEFAULT_PLATFORM_ACCOUNT_FEE,
    DEFAULT_PLATFORM_ACCOUNT_RECHARGE,
    DEFAULT_PLATFORM_ACCOUNT_REWARD,
    CreditAccount,
    CreditAccountTable,
    CreditDebit,
    CreditEvent,
    CreditEventTable,
    CreditTransactionTable,
    CreditType,
    Direction,
    EventType,
    OwnerType,
    TransactionType,
    UpstreamType,
)

logger = logging.getLogger(__name__)


async def recharge(
    session: AsyncSession,
    user_id: str,
    amount: Decimal,
    upstream_tx_id: str,
    note: Optional[str] = None,
) -> CreditAccount:
    """
    Recharge credits to a user account.

    Args:
        session: Async session to use for database operations
        user_id: ID of the user to recharge
        amount: Amount of credits to recharge
        upstream_tx_id: ID of the upstream transaction
        note: Optional note for the transaction

    Returns:
        Updated user credit account
    """
    # Check for idempotency - prevent duplicate transactions
    await CreditEvent.check_upstream_tx_id_exists(
        session, UpstreamType.API, upstream_tx_id
    )

    if amount <= Decimal("0"):
        raise ValueError("Recharge amount must be positive")

    # 1. Update user account - add credits
    user_account = await CreditAccount.income_in_session(
        session=session,
        owner_type=OwnerType.USER,
        owner_id=user_id,
        amount=amount,
        credit_type=CreditType.PERMANENT,  # Recharge adds to permanent credits
    )

    # 2. Update platform recharge account - deduct credits
    platform_account = await CreditAccount.deduction_in_session(
        session=session,
        owner_type=OwnerType.PLATFORM,
        owner_id=DEFAULT_PLATFORM_ACCOUNT_RECHARGE,
        credit_type=CreditType.PERMANENT,
        amount=amount,
    )

    # 3. Create credit event record
    event_id = str(XID())
    event = CreditEventTable(
        id=event_id,
        event_type=EventType.RECHARGE,
        upstream_type=UpstreamType.API,
        upstream_tx_id=upstream_tx_id,
        direction=Direction.INCOME,
        account_id=user_account.id,
        total_amount=amount,
        credit_type=CreditType.PERMANENT,
        balance_after=user_account.credits
        + user_account.free_credits
        + user_account.reward_credits,
        base_amount=amount,
        base_original_amount=amount,
        note=note,
    )
    session.add(event)
    await session.flush()

    # 4. Create credit transaction records
    # 4.1 User account transaction (credit)
    user_tx = CreditTransactionTable(
        id=str(XID()),
        account_id=user_account.id,
        event_id=event_id,
        tx_type=TransactionType.RECHARGE,
        credit_debit=CreditDebit.CREDIT,
        change_amount=amount,
        credit_type=CreditType.PERMANENT,
    )
    session.add(user_tx)

    # 4.2 Platform recharge account transaction (debit)
    platform_tx = CreditTransactionTable(
        id=str(XID()),
        account_id=platform_account.id,
        event_id=event_id,
        tx_type=TransactionType.RECHARGE,
        credit_debit=CreditDebit.DEBIT,
        change_amount=amount,
        credit_type=CreditType.PERMANENT,
    )
    session.add(platform_tx)

    # Commit all changes
    await session.commit()

    return user_account


async def reward(
    session: AsyncSession,
    user_id: str,
    amount: Decimal,
    upstream_tx_id: str,
    note: Optional[str] = None,
) -> CreditAccount:
    """
    Reward a user account with reward credits.

    Args:
        session: Async session to use for database operations
        user_id: ID of the user to reward
        amount: Amount of reward credits to add
        upstream_tx_id: ID of the upstream transaction
        note: Optional note for the transaction

    Returns:
        Updated user credit account
    """
    # Check for idempotency - prevent duplicate transactions
    await CreditEvent.check_upstream_tx_id_exists(
        session, UpstreamType.API, upstream_tx_id
    )

    if amount <= Decimal("0"):
        raise ValueError("Reward amount must be positive")

    # 1. Update user account - add reward credits
    user_account = await CreditAccount.income_in_session(
        session=session,
        owner_type=OwnerType.USER,
        owner_id=user_id,
        amount=amount,
        credit_type=CreditType.REWARD,  # Reward adds to reward credits
    )

    # 2. Update platform reward account - deduct credits
    platform_account = await CreditAccount.deduction_in_session(
        session=session,
        owner_type=OwnerType.PLATFORM,
        owner_id=DEFAULT_PLATFORM_ACCOUNT_REWARD,
        credit_type=CreditType.REWARD,
        amount=amount,
    )

    # 3. Create credit event record
    event_id = str(XID())
    event = CreditEventTable(
        id=event_id,
        event_type=EventType.REWARD,
        upstream_type=UpstreamType.API,
        upstream_tx_id=upstream_tx_id,
        direction=Direction.INCOME,
        account_id=user_account.id,
        total_amount=amount,
        credit_type=CreditType.REWARD,
        balance_after=user_account.credits
        + user_account.free_credits
        + user_account.reward_credits,
        base_amount=amount,
        base_original_amount=amount,
        note=note,
    )
    session.add(event)
    await session.flush()

    # 4. Create credit transaction records
    # 4.1 User account transaction (credit)
    user_tx = CreditTransactionTable(
        id=str(XID()),
        account_id=user_account.id,
        event_id=event_id,
        tx_type=TransactionType.REWARD,
        credit_debit=CreditDebit.CREDIT,
        change_amount=amount,
        credit_type=CreditType.REWARD,
    )
    session.add(user_tx)

    # 4.2 Platform reward account transaction (debit)
    platform_tx = CreditTransactionTable(
        id=str(XID()),
        account_id=platform_account.id,
        event_id=event_id,
        tx_type=TransactionType.REWARD,
        credit_debit=CreditDebit.DEBIT,
        change_amount=amount,
        credit_type=CreditType.REWARD,
    )
    session.add(platform_tx)

    # Commit all changes
    await session.commit()

    return user_account


async def adjustment(
    session: AsyncSession,
    user_id: str,
    credit_type: CreditType,
    amount: Decimal,
    upstream_tx_id: str,
    note: str,
) -> CreditAccount:
    """
    Adjust a user account's credits (can be positive or negative).

    Args:
        session: Async session to use for database operations
        user_id: ID of the user to adjust
        credit_type: Type of credit to adjust (FREE, REWARD, or PERMANENT)
        amount: Amount to adjust (positive for increase, negative for decrease)
        upstream_tx_id: ID of the upstream transaction
        note: Required explanation for the adjustment

    Returns:
        Updated user credit account
    """
    # Check for idempotency - prevent duplicate transactions
    await CreditEvent.check_upstream_tx_id_exists(
        session, UpstreamType.API, upstream_tx_id
    )

    if amount == Decimal("0"):
        raise ValueError("Adjustment amount cannot be zero")

    if not note:
        raise ValueError("Adjustment requires a note explaining the reason")

    # Determine direction based on amount sign
    is_income = amount > Decimal("0")
    abs_amount = abs(amount)
    direction = Direction.INCOME if is_income else Direction.EXPENSE
    credit_debit_user = CreditDebit.CREDIT if is_income else CreditDebit.DEBIT
    credit_debit_platform = CreditDebit.DEBIT if is_income else CreditDebit.CREDIT

    # 1. Update user account
    if is_income:
        user_account = await CreditAccount.income_in_session(
            session=session,
            owner_type=OwnerType.USER,
            owner_id=user_id,
            amount=abs_amount,
            credit_type=credit_type,
        )
    else:
        # Deduct the credits using deduction_in_session
        # For adjustment, we don't check if the user has enough credits
        # It can be positive or negative
        user_account = await CreditAccount.deduction_in_session(
            session=session,
            owner_type=OwnerType.USER,
            owner_id=user_id,
            credit_type=credit_type,
            amount=abs_amount,
        )

    # 2. Update platform adjustment account
    if is_income:
        platform_account = await CreditAccount.deduction_in_session(
            session=session,
            owner_type=OwnerType.PLATFORM,
            owner_id=DEFAULT_PLATFORM_ACCOUNT_ADJUSTMENT,
            credit_type=credit_type,
            amount=abs_amount,
        )
    else:
        platform_account = await CreditAccount.income_in_session(
            session=session,
            owner_type=OwnerType.PLATFORM,
            owner_id=DEFAULT_PLATFORM_ACCOUNT_ADJUSTMENT,
            amount=abs_amount,
            credit_type=credit_type,
        )

    # 3. Create credit event record
    event_id = str(XID())
    event = CreditEventTable(
        id=event_id,
        event_type=EventType.ADJUSTMENT,
        upstream_type=UpstreamType.API,
        upstream_tx_id=upstream_tx_id,
        direction=direction,
        account_id=user_account.id,
        total_amount=abs_amount,
        credit_type=credit_type,
        balance_after=user_account.credits
        + user_account.free_credits
        + user_account.reward_credits,
        base_amount=abs_amount,
        base_original_amount=abs_amount,
        note=note,
    )
    session.add(event)
    await session.flush()

    # 4. Create credit transaction records
    # 4.1 User account transaction
    user_tx = CreditTransactionTable(
        id=str(XID()),
        account_id=user_account.id,
        event_id=event_id,
        tx_type=TransactionType.ADJUSTMENT,
        credit_debit=credit_debit_user,
        change_amount=abs_amount,
        credit_type=credit_type,
    )
    session.add(user_tx)

    # 4.2 Platform adjustment account transaction
    platform_tx = CreditTransactionTable(
        id=str(XID()),
        account_id=platform_account.id,
        event_id=event_id,
        tx_type=TransactionType.ADJUSTMENT,
        credit_debit=credit_debit_platform,
        change_amount=abs_amount,
        credit_type=credit_type,
    )
    session.add(platform_tx)

    # Commit all changes
    await session.commit()

    return user_account


async def update_daily_quota(
    session: AsyncSession,
    user_id: str,
    free_quota: Optional[Decimal] = None,
    refill_amount: Optional[Decimal] = None,
    upstream_tx_id: str = "",
    note: str = "",
) -> CreditAccount:
    """
    Update the daily quota and refill amount of a user's credit account.

    Args:
        session: Async session to use for database operations
        user_id: ID of the user to update
        free_quota: Optional new daily quota value
        refill_amount: Optional amount to refill hourly, not exceeding free_quota
        upstream_tx_id: ID of the upstream transaction (for logging purposes)
        note: Explanation for changing the daily quota

    Returns:
        Updated user credit account
    """
    # Log the upstream_tx_id for record keeping
    logger.info(
        f"Updating quota settings for user {user_id} with upstream_tx_id: {upstream_tx_id}"
    )

    # Check that at least one parameter is provided
    if free_quota is None and refill_amount is None:
        raise ValueError("At least one of free_quota or refill_amount must be provided")

    # Get current account to check existing values and validate
    user_account = await CreditAccount.get_or_create_in_session(
        session, OwnerType.USER, user_id, for_update=True
    )

    # Use existing values if not provided
    if free_quota is None:
        free_quota = user_account.free_quota
    elif free_quota <= Decimal("0"):
        raise ValueError("Daily quota must be positive")

    if refill_amount is None:
        refill_amount = user_account.refill_amount
    elif refill_amount < Decimal("0"):
        raise ValueError("Refill amount cannot be negative")

    # Ensure refill_amount doesn't exceed free_quota
    if refill_amount > free_quota:
        raise ValueError("Refill amount cannot exceed daily quota")

    if not note:
        raise ValueError("Quota update requires a note explaining the reason")

    # Already got the user account above, no need to get it again

    # Update the free_quota field
    stmt = (
        update(CreditAccountTable)
        .where(
            CreditAccountTable.owner_type == OwnerType.USER,
            CreditAccountTable.owner_id == user_id,
        )
        .values(free_quota=free_quota, refill_amount=refill_amount)
        .returning(CreditAccountTable)
    )
    result = await session.scalar(stmt)
    if not result:
        raise ValueError("Failed to update user account")

    user_account = CreditAccount.model_validate(result)

    # No credit event needed for updating account settings

    # Commit all changes
    await session.commit()

    return user_account


async def list_credit_events_by_user(
    session: AsyncSession,
    user_id: str,
    direction: Direction,
    cursor: Optional[str] = None,
    limit: int = 20,
    event_type: Optional[EventType] = None,
) -> Tuple[List[CreditEvent], Optional[str], bool]:
    """
    List credit events for a user account with cursor pagination.

    Args:
        session: Async database session.
        user_id: The ID of the user.
        direction: The direction of the events (INCOME or EXPENSE).
        cursor: The ID of the last event from the previous page.
        limit: Maximum number of events to return per page.
        event_type: Optional filter for specific event type.

    Returns:
        A tuple containing:
        - A list of CreditEvent models.
        - The cursor for the next page (ID of the last event in the list).
        - A boolean indicating if there are more events available.
    """
    # 1. Find the account for the owner
    account = await CreditAccount.get_in_session(session, OwnerType.USER, user_id)
    if not account:
        # Decide if returning empty or raising error is better. Empty list seems reasonable.
        # Or raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{owner_type.value.capitalize()} account not found")
        return [], None, False

    # 2. Build the query
    stmt = (
        select(CreditEventTable)
        .where(CreditEventTable.account_id == account.id)
        .where(CreditEventTable.direction == direction.value)
        .order_by(desc(CreditEventTable.id))
        .limit(limit + 1)  # Fetch one extra to check if there are more
    )

    # 3. Apply event type filter if provided
    if event_type:
        stmt = stmt.where(CreditEventTable.event_type == event_type.value)

    # 4. Apply cursor filter if provided
    if cursor:
        stmt = stmt.where(CreditEventTable.id < cursor)

    # 5. Execute query
    result = await session.execute(stmt)
    events_data = result.scalars().all()

    # 6. Determine pagination details
    has_more = len(events_data) > limit
    events_to_return = events_data[:limit]  # Slice to the requested limit

    next_cursor = events_to_return[-1].id if events_to_return else None

    # 7. Convert to Pydantic models
    events_models = [CreditEvent.model_validate(event) for event in events_to_return]

    return events_models, next_cursor, has_more


async def list_fee_events_by_agent(
    session: AsyncSession,
    agent_id: str,
    cursor: Optional[str] = None,
    limit: int = 20,
) -> Tuple[List[CreditEvent], Optional[str], bool]:
    """
    List fee events for an agent with cursor pagination.
    These events represent income for the agent from users' expenses.

    Args:
        session: Async database session.
        agent_id: The ID of the agent.
        cursor: The ID of the last event from the previous page.
        limit: Maximum number of events to return per page.

    Returns:
        A tuple containing:
        - A list of CreditEvent models.
        - The cursor for the next page (ID of the last event in the list).
        - A boolean indicating if there are more events available.
    """
    # 1. Find the account for the agent
    agent_account = await CreditAccount.get_in_session(session, OwnerType.AGENT, agent_id)
    if not agent_account:
        return [], None, False

    # 2. Build the query to find events where fee_agent_amount > 0 and fee_agent_account = agent_account.id
    stmt = (
        select(CreditEventTable)
        .where(CreditEventTable.fee_agent_account == agent_account.id)
        .where(CreditEventTable.fee_agent_amount > 0)
        .order_by(desc(CreditEventTable.id))
        .limit(limit + 1)  # Fetch one extra to check if there are more
    )

    # 3. Apply cursor filter if provided
    if cursor:
        stmt = stmt.where(CreditEventTable.id < cursor)

    # 4. Execute query
    result = await session.execute(stmt)
    events_data = result.scalars().all()

    # 5. Determine pagination details
    has_more = len(events_data) > limit
    events_to_return = events_data[:limit]  # Slice to the requested limit

    next_cursor = events_to_return[-1].id if events_to_return else None

    # 6. Convert to Pydantic models
    events_models = [CreditEvent.model_validate(event) for event in events_to_return]

    return events_models, next_cursor, has_more


async def fetch_credit_event_by_upstream_tx_id(
    session: AsyncSession,
    upstream_tx_id: str,
) -> CreditEvent:
    """
    Fetch a credit event by its upstream transaction ID.

    Args:
        session: Async database session.
        upstream_tx_id: ID of the upstream transaction.

    Returns:
        The credit event if found.

    Raises:
        HTTPException: If the credit event is not found.
    """
    # Build the query to find the event by upstream_tx_id
    stmt = select(CreditEventTable).where(
        CreditEventTable.upstream_tx_id == upstream_tx_id
    )

    # Execute query
    result = await session.scalar(stmt)

    # Raise 404 if not found
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Credit event with upstream_tx_id '{upstream_tx_id}' not found",
        )

    # Convert to Pydantic model and return
    return CreditEvent.model_validate(result)


async def expense_message(
    session: AsyncSession,
    agent_id: str,
    user_id: str,
    message_id: str,
    start_message_id: str,
    base_llm_amount: Decimal,
    agent_fee_percentage: Decimal,
    agent_owner_id: str,
) -> CreditAccount:
    """
    Deduct credits from a user account for message expenses.

    Args:
        session: Async session to use for database operations
        agent_id: ID of the agent to deduct credits from
        user_id: ID of the user to deduct credits from
        amount: Amount of credits to deduct
        upstream_tx_id: ID of the upstream transaction
        message_id: ID of the message that incurred the expense
        start_message_id: ID of the starting message in a conversation
        base_llm_amount: Amount of LLM costs

    Returns:
        Updated user credit account
    """
    # Check for idempotency - prevent duplicate transactions
    await CreditEvent.check_upstream_tx_id_exists(
        session, UpstreamType.EXECUTOR, message_id
    )

    if base_llm_amount < Decimal("0"):
        raise ValueError("Base LLM amount must be non-negative")

    # Calculate amount
    base_original_amount = base_llm_amount
    base_amount = base_original_amount
    fee_platform_amount = base_amount * Decimal(
        str(config.payment_fee_platform_percentage)
    )
    fee_agent_amount = (
        base_amount * agent_fee_percentage
        if user_id != agent_owner_id
        else Decimal("0")
    )
    total_amount = base_amount + fee_platform_amount + fee_agent_amount

    # 1. Update user account - deduct credits
    user_account, credit_type = await CreditAccount.expense_in_session(
        session=session,
        owner_type=OwnerType.USER,
        owner_id=user_id,
        amount=total_amount,
    )

    # 2. Update fee account - add credits
    platform_account = await CreditAccount.income_in_session(
        session=session,
        owner_type=OwnerType.PLATFORM,
        owner_id=DEFAULT_PLATFORM_ACCOUNT_FEE,
        credit_type=credit_type,
        amount=fee_platform_amount,
    )
    if fee_agent_amount > 0:
        agent_account = await CreditAccount.income_in_session(
            session=session,
            owner_type=OwnerType.AGENT,
            owner_id=agent_id,
            credit_type=credit_type,
            amount=fee_agent_amount,
        )

    # 3. Create credit event record
    event_id = str(XID())
    event = CreditEventTable(
        id=event_id,
        account_id=user_account.id,
        event_type=EventType.MESSAGE,
        upstream_type=UpstreamType.EXECUTOR,
        upstream_tx_id=message_id,
        direction=Direction.EXPENSE,
        agent_id=agent_id,
        message_id=message_id,
        start_message_id=start_message_id,
        total_amount=total_amount,
        credit_type=credit_type,
        balance_after=user_account.credits
        + user_account.free_credits
        + user_account.reward_credits,
        base_amount=base_amount,
        base_original_amount=base_original_amount,
        base_llm_amount=base_llm_amount,
        fee_platform_amount=fee_platform_amount,
        fee_agent_amount=fee_agent_amount,
        fee_agent_account=agent_account.id if fee_agent_amount > 0 else None,
    )
    session.add(event)
    await session.flush()

    # 4. Create credit transaction records
    # 4.1 User account transaction (debit)
    user_tx = CreditTransactionTable(
        id=str(XID()),
        account_id=user_account.id,
        event_id=event_id,
        tx_type=TransactionType.PAY,
        credit_debit=CreditDebit.DEBIT,
        change_amount=total_amount,
        credit_type=credit_type,
    )
    session.add(user_tx)

    # 4.2 Platform fee account transaction (credit)
    platform_tx = CreditTransactionTable(
        id=str(XID()),
        account_id=platform_account.id,
        event_id=event_id,
        tx_type=TransactionType.RECEIVE_FEE_PLATFORM,
        credit_debit=CreditDebit.CREDIT,
        change_amount=fee_platform_amount,
        credit_type=credit_type,
    )
    session.add(platform_tx)

    # 4.3 Agent fee account transaction (credit)
    if fee_agent_amount > 0:
        agent_tx = CreditTransactionTable(
            id=str(XID()),
            account_id=agent_account.id,
            event_id=event_id,
            tx_type=TransactionType.RECEIVE_FEE_AGENT,
            credit_debit=CreditDebit.CREDIT,
            change_amount=fee_agent_amount,
            credit_type=credit_type,
        )
        session.add(agent_tx)

    # Commit all changes
    await session.commit()

    return user_account
