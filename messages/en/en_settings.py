SETTINGS_MESSAGES_EN = {
    'en': {  
        'settings_menu': '''⚙️ <b>Settings</b>

Here you can customize the diary for yourself:''',      
        'settings_language': '🌍 Language: {language}',
        'settings_notifications': '🔔 Notifications: {status}',
        'settings_auto_analysis': '📈 Auto-analysis: {status}',
        'settings_premium': '👑 Premium: {status}',
        
        'language_changed': '✅ Language successfully changed',
        'notifications_enabled': '✅ Notifications enabled',
        'notifications_disabled': '✅ Notifications disabled',
        'btn_change_timezone_after_first_entry': '🌍 Change Timezone',
        'btn_enter_city': '🏙 Enter city',
        'settings_timezone': '🌍 Timezone: {timezone}',
        'timezone_changed': '✅ Timezone successfully changed to {timezone}',
        'timezone_not_changed': '❌ Failed to change timezone. Please try again.',
        'timezone_reminder': '''🌍 <b>Don't forget to set your timezone!</b>

You are still using the default timezone (UTC). 
For more accurate bot operation, we recommend setting your local timezone in the settings.''',

        'settings_analysis_time': '⏰ Analysis time: {time}',
        'ask_timezone_selection': '🌍 <b>Select your time zone</b>\n\nCurrent time zone: {current_timezone}\n\nSetting the correct time zone is important for accurately displaying entry times, correct analytics operation, and timely delivery of notifications.',
        'analysis_time_changed': '✅ Automatic analysis time set to {time}',
        'profile_menu': '''👤 <b>Your Profile</b>
📝 <b>Name:</b> {first_name}
📧 <b>Email:</b> {email}
🎂 <b>Date of Birth:</b> {date_of_birth}
🎯 <b>Hobbies:</b> {hobbies}
📌 <b>Life Facts:</b> {life_facts}

Choose what you want to change:''',
        'btn_edit_profile': '👤 Edit Profile',
        'btn_edit_name': '📝 Edit Name',
        'btn_edit_email': '📧 Edit Email',
        'btn_edit_dob': '🎂 Edit Date of Birth',
        'btn_edit_hobbies': '🎯 Edit Hobbies',
        'btn_edit_life_facts': '📌 Edit Life Facts',
        'ask_new_name': '📝 <b>Enter your new name:</b>',
        'ask_new_email': '📧 <b>Enter your new email:</b>',
        'ask_new_dob': '🎂 <b>Enter your new date of birth (DD.MM.YYYY):</b>',
        'ask_new_hobbies': '🎯 <b>Enter your hobbies separated by commas:</b>',
        'ask_new_life_facts': '📌 <b>Enter facts about your life separated by commas:</b>',
        'profile_updated': '✅ Profile updated successfully!',
        'invalid_email_format': '❌ Invalid email format. Please try again.',
        'invalid_date_format': '❌ Invalid date format. Use DD.MM.YYYY.',
        'invalid_date_future': '❌ Date of birth cannot be in the future.',
        'delete_account': '🗑 Delete account',
        'account_deletion_menu': '''🗑 <b>Account Deletion</b>

You are about to delete your account and all associated data.

⚠️ <b>Important:</b>
• This action cannot be undone.
• All your entries, tasks, and personal data will be deleted.
• {balance_info}

Choose an action:''',

        'account_balance_info_positive': 'Your balance is <b>{balance} RUB</b>. These funds will be lost if you delete your account.',
        'account_balance_info_zero': 'Your balance is zero.',
        'account_balance_info_negative': 'You have a negative balance of {balance} RUB.',

        'btn_delete_account_and_funds': '🗑 Delete Account and Funds',
        'btn_contact_support_for_refund': '📞 Contact Support',
        'btn_cancel_deletion': '❌ Cancel',

        'confirm_account_deletion': '''❓ <b>Confirm Account Deletion</b>

Are you sure you want to delete your account?
This action cannot be undone.

After deletion:
• All your data will be deleted.
• Access to the account will be lost.
• {balance_warning}

Type "DELETE MY ACCOUNT" to confirm:''',

        'balance_warning_positive': 'You will lose <b>{balance} RUB</b> from your balance.',
        'balance_warning_zero_or_negative': 'All data will be deleted.',

        'account_deletion_cancelled': '✅ Account deletion cancelled.',
        'account_deletion_confirmed': '''✅ <b>Account Deleted</b>

Your account and all associated data have been successfully deleted.
Thank you for using our service.''',
        'account_deletion_error': '❌ An error occurred while deleting the account. Please try again later or contact support.',
        
        # === Messages for timezone selection ===
        'ask_timezone_selection': '🌍 <b>Select your timezone</b>\n\nCurrent timezone: {current_timezone}\n\nYou can choose from a list of popular timezones or enter your own.',
        'btn_select_common_timezones': '📋 Select from list',
        'btn_enter_custom_timezone': '✍️ Enter manually',
        'btn_detect_timezone': '🧭 Detect automatically', # If implemented later
        
        # === Messages for timezone list ===
        'select_timezone_title': '🌍 <b>Select your timezone</b>\n\nCurrent timezone: {current_timezone}',
        'btn_timezone_utc': 'UTC',
        'btn_timezone_moscow': 'Europe/Moscow (MSK)',
        'btn_timezone_yekaterinburg': 'Asia/Yekaterinburg',
        'btn_timezone_omsk': 'Asia/Omsk',
        'btn_timezone_krasnoyarsk': 'Asia/Krasnoyarsk',
        'btn_timezone_irkutsk': 'Asia/Irkutsk',
        'btn_timezone_yakutsk': 'Asia/Yakutsk',
        'btn_timezone_vladivostok': 'Asia/Vladivostok',
        'btn_timezone_magadan': 'Asia/Magadan',
        # Add other popular world timezones
        'btn_timezone_new_york': 'America/New_York (EST/EDT)',
        'btn_timezone_london': 'Europe/London (GMT/BST)',
        'btn_timezone_berlin': 'Europe/Berlin (CET/CEST)',
        'btn_timezone_tokyo': 'Asia/Tokyo (JST)',
        
        # === Messages for manual entry ===
        'ask_enter_custom_timezone': '✍️ <b>Enter your timezone</b>\n\nEnter the timezone identifier (e.g., `Europe/Moscow`, `America/New_York`).\n\nCurrent timezone: {current_timezone}',
        'error_invalid_timezone': '❌ Invalid timezone format. Please use the `Region/City` format (e.g., `Europe/Moscow`).',
        'error_unknown_timezone': '❌ The specified timezone was not found. Please check the entered value.',  
        'ask_entry_edit': '📝 <b>Edit your entry:</b>\n\n<i>Current text:</i>\n{old_text}', 
        'entry_updated': '✅ <b>Entry updated!</b>\n\n📊 <b>Day score:</b> {score}/10 - {mood}\n💭 <b>Comment:</b> {comment}\n🎯 <b>Recommendation:</b> {recommendation}',     
        # === Statuses ===
        'status_enabled': 'ON',
        'status_disabled': 'OFF',
        'status_active': 'Active',
        'status_inactive': 'Inactive',

        'enter_city': '''🏙 <b>Enter your city name</b>\nFor example: London, New York, Berlin''',
        'please_enter_city': '''Please, enter city''',
        'timezone_found': '''🏙 Timezone found for city <b>{city_name}</b>, <b>{country}</b>:\n\n🕒 <code>{timezone}</code>''',
        'searching_timezone': '''⏳ Searching for timezone for the specified city...''',
        'timezone_error': '''Error determining timezone''',
        'city_not_found': '''City not found''',
        'multiple_cities_found': '''🏙 Several options found. Select the correct one:''',
        'selection_failed': '''❌ Failed to get selection options''',
        'timezone_detection_failed': '''❌ Failed to determine timezone''',
        'invalid_timezone': '''❌ Invalid timezone determined''',
        'wrong_timezone': '''❌ Invalid timezone''',
        'current_hobbies': '''\n\n<i>Current hobbies:</i> <code>{current_hobbies}</code>''',
        'current_facts': '''\n\n<i>Current facts:</i> <code>{current_facts}</code>''',
        'delete_account_btn': '''DELETE MY ACCOUNT''',
        'invalid_confirmation_text': '''❌ Invalid confirmation text. Please enter the exact phrase.''',
        'btn_subscribe': '''💳 Subscribe'''
    }
}