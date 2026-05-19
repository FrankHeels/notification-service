import pytest

from src.redis import consume_guest_ws_ticket, create_guest_ws_ticket


@pytest.mark.asyncio
async def test_create_and_consume_guest_ticket():
    ticket = await create_guest_ws_ticket()
    assert isinstance(ticket, str)

    # Consume valid ticket
    is_valid = await consume_guest_ws_ticket(ticket)
    assert is_valid is True

    # Consume already used ticket
    is_valid_again = await consume_guest_ws_ticket(ticket)
    assert is_valid_again is False
