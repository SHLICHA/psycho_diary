PROGRESS_MESSAGES_EN = {
    'en': {
        'progress_title': '🎯 <b>Your Progress</b>\n\n🧠 Awareness Level: {awareness_level}/10\n📝 Entries: {entries_count}\n✅ Tasks: {tasks_completed}/{tasks_assigned} ({tasks_completion_percentage:.1f}%)\n🔥 Streak Days: {streak_days}',
        'progress_detailed': '''📊 <b>Detailed statistics</b>

📉 <b>Mood dynamics:</b>
{mood_chart}

🔥 <b>Frequent themes:</b>
{frequent_themes}

💡 <b>New insights:</b>
{new_insights}''',

'weekly_analysis_title': '''📈 <b>Weekly Analysis</b>
Week: {week_start_date} - {week_end_date}
Awareness Level: {awareness_level}/10
''',
'weekly_analysis_summary': '''🧠 <b>Week Summary:</b>
{summary_text}
''',
'weekly_analysis_progress': '''📊 <b>Progress:</b>
Mood Trend: {mood_trend_display}
{progress_notes}
''',
'weekly_analysis_stats': '''📈 <b>Statistics:</b>
• Entries: {total_entries}
• Streak Days (this week): {streak_days_current}
• Avg. Mood Score: {avg_mood_score}
• Tasks Assigned: {tasks_assigned}
• Tasks Completed: {tasks_completed}
''',
'weekly_analysis_no_data': '📭 No data to display for this week.',
'weekly_analysis_not_found': 'Analysis for this week has not been performed yet.',
'weekly_analysis_comparison': '''⚖️ <b>Comparison with Previous Week:</b>
{progress_comment}
''',
'weekly_analysis_comparison_mood': 'Mood: {mood_comparison}',
'weekly_analysis_comparison_consistency': 'Consistency: {consistency_comparison}',

'btn_weekly_details': '🔬 Weekly Analysis',
'btn_next_week': '⏭ Next Week',
'btn_prev_week': '⏮ Prev. Week',
'btn_weekly_progress': '📊 Weekly Progress',
'btn_mood_chart': '📈 Mood Chart',
'btn_detailed_progress': 'Detailed Progress',
'mood_chart_caption': 'Your mood dynamics for the last {days} days.',
'dynamics': '''\n\n📊 <b>Dynamics:</b> ''',
'weekly_analysis_not_performed_yet': '''\n\nℹ️ <b>Progress analysis is performed once a week.</b> Continue keeping a diary, and over time you will see your changes here.''',
'changes': '''<b>Changes:</b> {summary}''',
'key_changes': '''<b>Key changes:</b>\n{changes_list}''',
'stable_traits': '''<b>Stable traits:</b>\n{stable_list}''',
'detailed_progress': '''📋 <b>Detailed progress for {week_start_date} - {week_end_date}</b>\n\n{changes_text}''',
        'restore_streak_info': '''You missed one or two days in a row. You can restore your streak by creating a blank entry for the missed day. This will cost <b>{tokens_cost}</b> tokens.''',
        'restore_streak_confirm': '''Are you sure you want to restore your streak for <b>{tokens_cost}</b> tokens?''',
        'restore_streak_success': '''Streak restored! Entry for <b>{date}</b> created.''',
        'restore_streak_success_multiple': '''Streak restored! Entries for <b>{dates}</b> created.''',
        'restore_streak_no_tokens': '''Not enough tokens to restore the streak.''',
        'restore_streak_unavailable': '''Streak restoration is currently unavailable.''',
        'restore_streak_cost_info': '''(cost: {tokens_cost} tokens)''',
        'btn_restore_streak': '🔄 Restore Streak',
        'btn_restore_streak_for_date': '🔄 Restore {date}',
        # --- Buttons ---
        'btn_confirm': '✅ Confirm',
    }
}