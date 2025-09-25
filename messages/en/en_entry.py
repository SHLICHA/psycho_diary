ENTRY_MESSAGES_EN = {
    'en': {
                 # === Creating entries ===
        'ask_entry': '📝 <b>Tell me how your day went...</b>',
        'ask_voice_entry': '🎙 <b>Send a voice message about your day...</b>',
        'processing': '⏳ <i>Processing your entry...</i>',
        'entry_saved': '''✅ <b>Entry saved and analyzed!</b>

📊 <b>Day score:</b> {score}/10 - {mood}
💭 <b>Comment:</b> {comment}
🎯 <b>Recommendation:</b> {recommendation}''',

        'full_day_analysis_header': '🔬 Full Day Analysis for {date}',
        'no_full_analysis_yet': '🔬 Full day analysis has not been performed yet. Click "Recalculate day analysis".',

        # === Error messages ===
        'error_processing': '❌ An error occurred during processing. Please try again later.',
        'rate_limit': '🕐 Please wait a moment before your next entry.',
        'rate_limit_exceeded': '⚠️ You have exceeded the message limit. Please wait a moment.',
        'error_generic': '❌ An error occurred. Please try again later.',
        'invalid_input': '🤔 I didn\'t understand your message. Please send text or voice message.',
        'invalid_input_type': "Please send a text message or a voice message.",
        'text_too_short': "The text is too short. Please write a bit more.",
        'text_too_long': "The text is too long. Please shorten it.",
        'voice_too_short': "The voice message is too short. Please record a longer message.",
        'voice_too_long': "The voice message is too long. Please record a shorter message.",
        'validation_error_text': "Error validating text. Please try again.",
        'validation_error_voice': "Error validating voice message. Please try again.",
        'validation_error_message': "Error validating message. Please try again.",
        'confirm_delete_entire_day_prompt': "❓ Are you sure you want to delete ALL entries for {date}?",

        'day_deleted_success': "🗑 Day successfully deleted.",
        # Кнопки
        'btn_delete_entry': '🗑 Delete',
        'btn_analyze_again': '🔄 Re-analyze',
        'btn_edit_entry': '✏️ Edit',
        'btn_confirm_delete': '✅ Yes, delete',
        'btn_cancel_delete': '❌ No, cancel',
        'btn_confirm_delete_entry': '✅ Yes, delete entry',
        'btn_confirm_delete_day': "✅ Yes, delete the day",
        'btn_skip_clarification': '➡️ Skip questions',
        'reminder_clarification': '📝 You did not respond to the clarifying questions sent earlier. Please reply to get a more accurate analysis.',
        'new_ai_task': '''\n📌 <b>New task:</b>\n<b>{title}</b>\n{preview}'''
        }
}