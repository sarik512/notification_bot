from aiogram.fsm.state import State, StatesGroup


class AddClient(StatesGroup):
    """States for adding a new client"""
    waiting_for_name = State()
    waiting_for_amount = State()
    waiting_for_currency = State()
    waiting_for_start_date = State()
    waiting_for_interval_type = State()
    waiting_for_interval_value = State()
    waiting_for_category = State()
    waiting_for_notes = State()


class EditClient(StatesGroup):
    """States for editing a client"""
    selecting_client = State()
    selecting_field = State()
    waiting_for_name = State()
    waiting_for_amount = State()
    waiting_for_currency = State()
    waiting_for_date = State()
    waiting_for_interval_type = State()
    waiting_for_interval_value = State()
    waiting_for_category = State()
    waiting_for_notes = State()


class PostponePayment(StatesGroup):
    """States for postponing a payment"""
    selecting_client = State()
    waiting_for_days = State()
    waiting_for_date = State()


class DeleteClient(StatesGroup):
    """States for deleting a client"""
    selecting_client = State()
    confirming = State()


class ViewHistory(StatesGroup):
    """States for viewing payment history"""
    selecting_client = State()


class SearchClient(StatesGroup):
    """States for searching clients"""
    waiting_for_query = State()

