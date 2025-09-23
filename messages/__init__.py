HELP_MESSAGES = {
    'ru': {},
    'en': {}
}
from .ru import (
    HELP_MESSAGES_RU
)
from .en import (
    HELP_MESSAGES_EN
)
HELP_MESSAGES['ru'].update(HELP_MESSAGES_RU['ru'])
HELP_MESSAGES['en'].update(HELP_MESSAGES_EN['en'])

from .messages_utils import (
    get_button_text,
    get_message,
    get_mood_text,
    get_status_text
)


__all__ = [
    'get_button_text',
    'get_message',
    'get_mood_text',
    'get_status_text'
]