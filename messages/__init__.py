ALL_MESSAGES = {
    'ru': {},
    'en': {}
}
from .ru import (
    HELP_MESSAGES_RU,
    SETTINGS_MESSAGES_RU,
    TASKS_MESSAGES_RU,
    ENTRY_MESSAGES_RU,
    MAIN_MESSAGES_RU,
    ARCHIVE_MESSAGES_RU,
    PROGRESS_MESSAGES_RU,
    ONBOARDING_MESSAGES_RU,
    PROFILE_MESSAGES_RU
)
from .en import (
    HELP_MESSAGES_EN,
    SETTINGS_MESSAGES_EN,
    TASKS_MESSAGES_EN,
    ENTRY_MESSAGES_EN,
    MAIN_MESSAGES_EN,
    ARCHIVE_MESSAGES_EN,
    PROGRESS_MESSAGES_EN,
    ONBOARDING_MESSAGES_EN,
    PROFILE_MESSAGES_EN
)
ALL_MESSAGES['ru'].update(HELP_MESSAGES_RU['ru'])
ALL_MESSAGES['en'].update(HELP_MESSAGES_EN['en'])
ALL_MESSAGES['ru'].update(SETTINGS_MESSAGES_RU['ru'])
ALL_MESSAGES['en'].update(SETTINGS_MESSAGES_EN['en'])
ALL_MESSAGES['ru'].update(TASKS_MESSAGES_RU['ru'])
ALL_MESSAGES['en'].update(TASKS_MESSAGES_EN['en'])
ALL_MESSAGES['ru'].update(ENTRY_MESSAGES_RU['ru'])
ALL_MESSAGES['en'].update(ENTRY_MESSAGES_EN['en'])
ALL_MESSAGES['ru'].update(MAIN_MESSAGES_RU['ru'])
ALL_MESSAGES['en'].update(MAIN_MESSAGES_EN['en'])
ALL_MESSAGES['ru'].update(ARCHIVE_MESSAGES_RU['ru'])
ALL_MESSAGES['en'].update(ARCHIVE_MESSAGES_EN['en'])
ALL_MESSAGES['ru'].update(PROGRESS_MESSAGES_RU['ru'])
ALL_MESSAGES['en'].update(PROGRESS_MESSAGES_EN['en'])
ALL_MESSAGES['ru'].update(ONBOARDING_MESSAGES_RU['ru'])
ALL_MESSAGES['en'].update(ONBOARDING_MESSAGES_EN['en'])
ALL_MESSAGES['ru'].update(PROFILE_MESSAGES_RU['ru'])
ALL_MESSAGES['en'].update(PROFILE_MESSAGES_EN['en'])

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