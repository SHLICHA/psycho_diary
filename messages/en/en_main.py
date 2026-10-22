MAIN_MESSAGES_EN = {
    'en': {
        'welcome': '''🧠 <b>Hi! This is your psychological diary.</b>

Here you can keep records of your days, and I will help you understand your emotions and thoughts.

I will be your digital psychologist who will remember your features and understand you better each day.

Let's start?''',
        
        'welcome_back': '👋 Welcome back, {username}! Good to see you again.',
        'welcome_back_reactivated': "Welcome back, {first_name}! 🎉\n\nWe are glad you are back! Keep working on yourself — it's an important and valuable journey. You are doing great!",

        # === Menu and navigation ===
        'main_menu': '''🧠 <b>Your psychological diary</b>

Choose an action:''',
        
        'archive_menu': '📅 <b>Entry archive</b>',
        'tasks_menu': '🎯 <b>My tasks</b>',
        'progress_menu': '📊 <b>My progress</b>',
        
        # === Menu buttons ===
        'btn_new_entry': '📝 New entry',
        'btn_archive': '📅 Archive',
        'btn_tasks': '🎯 Tasks',
        'btn_progress': '📊 Progress',
        'btn_settings': '⚙️ Settings',
        'btn_help': '❓ Help',
        'btn_back': '''🔙 Back''',
        'btn_cancel': '❌ Cancel',
        'feedback': '''📩 <b>Feedback</b>

Write to us about:
• Bot operation issues
• Improvement suggestions
• Functionality questions

You can send text or voice message.''',
    'btn_add_screenshot': '''📷 Add screenshot''',
    'btn_send_without_photo': '''➡️ Send without photo''',
    'screenshot_prompt': '''Would you like to attach a screenshot for clarity?''',
    'screenshot_instructions': '''🖼 <b>Send screenshot</b>

Simply send a photo or image that will help understand your issue/suggestion.''',
    'feedback_thanks': '''✅ <b>Thank you for your feedback!</b>

Your message has been successfully sent to the developers.
We will review it shortly.''',
    'voice_message_accepted': '''🎤 <b>Voice message accepted!</b>

Would you like to attach a screenshot for better understanding?''',
'support_response': '''📩 Support response to your request #{feedback_id}:\n\n{message_text}''',
        'current_streak_info': '''🔥 <b>Current streak:</b> {current_streak} days in a row!''',
        'streak_at_risk': '''🔥 <b>Streak:</b> {current_streak} days. But it will break if you don't write today!''',
        'max_streak_info': '''🏆 <b>Best streak:</b> {max_streak} days!''',
        'no_current_streak': '''📅 <b>You haven't written today yet.</b> Start now!''',
        'keep_going_1_day': ''' Great start! Keep going!''',
        'keep_going_few_days': ''' Keep up the good work!''',
        'keep_going_streak': ''' Impressive! Keep it up!''',
        'main_menu_welcome_back': '''👋 Hi, <b>{first_name}</b>!

📊 <b>Awareness level:</b> {awareness_level}
📝 <b>Total entries:</b> {entries_count}
💰 <b>Tokens:</b> {token_balance}

{streak_info}
{max_streak_info}

Ready to share your thoughts?''',
        'user_default_name': '''Friend''',
        'streak_restore_hint': 'Keep your streak going! Missed a day? Restore it in the "Progress" section.',
        'streak_restore_hint_single_day': '📅 <b>Day {date} missed</b>!\nKeep your streak going! Restore it in the "Progress" section.',
        'streak_restore_hint_two_days': '📅 <b>Days {dates} missed</b>!\nKeep your streak going! Restore them in the "Progress" section.',
        'premium_days_remaining': 'Days remaining: <b>{days}</b>',
        'premium_expired': '👑 Subscription <b>expired</b>',
        'premium_active_info': '👑 <b>Subscription active</b>\n{days_info}',
        'main_menu_welcome_back_with_premium': '''👋 Hi, <b>{first_name}</b>!

📊 <b>Awareness level:</b> {awareness_level}
📝 <b>Total entries:</b> {entries_count}
💰 <b>Tokens:</b> {token_balance}
{premium_info}

{streak_info}
{max_streak_info}

Ready to share your thoughts?''',

'unexpected_text_message': '''💬 It seems you'd like to chat with me!\n\nIf you want to have a conversation on any topic — tap "💬 Talk to Psychologist" in the main menu.\n\nIf you'd like to make a diary entry for analysis and inclusion in your psychological profile — choose "📝 New Entry".''',
'unexpected_voice_message': '''💬 Voice message received!\n\nTo have it analyzed as a diary entry — choose "📝 New Entry".\n\nIf you just want to talk — tap "💬 Talk to Psychologist".''',

        # === Web Auth ===
        'web_link_generated': '''🌐 <b>Web Login Link</b>

Click the link to authorize:
{auth_url}

Link expires in 5 minutes.''',
        'web_link_invalid': '❌ Invalid link. Try getting a new one.',
        'web_link_expired': '⏰ Link expired. Type /web to get a new one.',
        'web_link_telegram_already_linked': '❌ This Telegram is already linked to another account.',
        'web_link_account_already_linked': '❌ This account already has another Telegram linked.',
        'web_link_success': '✅ <b>Telegram successfully linked!</b>\n\nNow you can use {username} in both the bot and web.',
        'web_link_max_success': '✅ <b>MAX successfully linked!</b>\n\nNow you can use {username} in both the bot and web.',
        'web_link_max_already_linked': '❌ This MAX account is already linked to another user.',
        'web_access_claim_prompt': '🔐 Request to open Psycho Diary on the web and set a password for your account. Confirm if this was you.',
        'web_access_claim_btn_yes': '✅ It\'s me',
        'web_access_claim_btn_no': '❌ No',
        'web_access_claim_confirmed': '✅ Confirmed. Set your password here (link expires soon):\n{set_password_url}',
        'web_access_claim_cancelled': '❌ Web access request declined.',

    }
}