TASKS_MESSAGES_EN = {
    'en': {  
        'task_assigned': '''\n🎯 <b>New task!</b>

<b>{title}</b>

{description}''',
        
        'task_completed_success': '''🎉 <b>Perfect!</b>

Your response is saved. I will consider this in future analysis.

{feedback}''',
    'task_effect_analysis_result': '''🔍 <b>Task Impact Analysis</b>

{effect_description}

📊 <b>Estimated impact on daily mood:</b> {mood_impact} point(s)
💭 <b>Comment:</b> {comment}
🎯 <b>Recommendation:</b> {recommendation}''',

        'task_effect_analysis_started': '🔍 <i>The analysis of the task\'s impact on your day has started. The result will be sent separately.</i>',
        'task_no_active': '📭 You have no active tasks.',
        'task_skipped': '⏭ Task skipped.',
        'task_deleted': '🗑 Task deleted.',
        
        # === Task buttons ===
        'btn_complete_task': '✅ Complete',
        'btn_skip_task': '⏭ Skip task',
        'btn_try_again': '''🔄 Try Again''',
        'btn_delete_task': '🗑 Delete task',
        'btn_view_task': '👁 View',
        'btn_cancel_task': '❌ Cancel Task',
        'task_cancelled_confirmation': '✅ The task "<b>{title}</b>" has been successfully canceled (deleted).',
        'task_cancelled_simple_message': '📢 The task "<b>{title}</b>" has been canceled.',
        'task_not_found_for_cancellation': '⚠️ Task not found or has already been deleted.',
        'task_history_empty': '📭 Task history is empty.',
        'error_loading_task_details': '❌ Error loading task details.',
        'task_restored': '✅ Task restored and available again!',
        'task_not_found_or_not_skipped': '❌ Task not found or is not skipped.',
        'btn_restore_task': '🔄 Restore Task',

        'btn_detailed_analysis': '🔬 Detailed Analysis',
        'detailed_task_analysis_header': 'Detailed Analysis for Task "{task_title}"',
        'task_analysis_not_found': 'Detailed analysis for this task completion is not available yet.',
        'task_analysis_no_details': 'Detailed analysis for task "{task_title}" contains no information.',
        'task_completion_not_found': 'Task completion information not found.',
        'task_analysis_error': 'Error retrieving task analysis.',

            # === Task buttons ===
        'btn_complete_task': '✅ Complete',
        'btn_view_task': '👁 View',
        'btn_task_history': '📜 Task history',
        'btn_active_tasks': '🎯 Active tasks',
        'btn_task_impact_chart': '📊 Task Impact Chart',
        
        # === Task statuses ===
        'task_status_pending': 'Pending',
        'task_status_in_progress': 'In progress',
        'task_status_completed': 'Completed',
        'task_status_skipped': 'Skipped',
        'task_status_expired': 'Expired',
        
        # === Task types ===
        'task_type_daily': 'Daily',
        'task_type_reflection': 'Reflection',
        'task_type_cognitive': 'Cognitive',
        'task_type_creative': 'Creative',
        'task_type_behavioral': 'Behavioral',
        'task_type_mindfulness': 'Mindfulness',

        'confirm_delete_task': '❓ Are you sure you want to delete this task?',
        'confirm_skip_task': '❓ Are you sure you want to skip this task?',
        'confirm_complete_task': '❓ Are you sure you want to mark this task as completed?',
        'task_completed_success': '''🎉 <b>Perfect! Task completed!</b>

    Your response is saved and analyzed.

    📊 <b>Completion score:</b> {score}/10 - {mood}
    💭 <b>Comment:</b> {comment}
    🎯 <b>Recommendation:</b> {recommendation}''',
        
        'task_processing': '⏳ <i>Analyzing your entry and the impact of the completed task...</i>',
        'task_completion_saved': '✅ <b>Task completion saved!</b>',
        'task_completion_analysis': '🧠 <b>Task completion analysis</b>\n\n{analysis}',
        'task_completion_recommendation': '🎯 <b>Recommendation:</b> {recommendation}',
        
        # === Task error messages ===
        'task_not_found': '❌ Task not found or does not belong to you.',
        'task_already_completed': '✅ Task already completed.',
        'task_already_skipped': '⏭ Task already skipped.',
        'task_deleted': '🗑 Task deleted.',
        'task_skipped': '⏭ Task skipped.',
        'task_delete_cancelled': '❌ Task deletion cancelled.',
        'task_skip_cancelled': '❌ Task skip cancelled.',
            # === Task messages ===
    'ask_task_completion_with_context': '''Completing task: <b>{title}</b>\n\n{description}\n\nPlease describe how you completed this task

Now describe how you completed this task:
- What exactly did you do?
- What steps did you take?
- What was difficult or easy?''',
    
    'ask_feelings_description': '''💭 <b>Describe your feelings during task completion</b>

Tell me what you felt while completing:
- What emotions did you experience?
- What did you enjoy?
- What was difficult?''',

        'task_history_detail': '''📝 <b>Task: {title}</b>
🕒 <b>Assigned:</b> {assigned_at}
{completed_at}
📊 <b>Status:</b> {status}

<b>Description:</b>
{description}

<b>Completion:</b>
{completion_text}

<b>Feelings:</b>
{feelings_text}''',
        
        'completion_not_found': 'Completion not found',
        'feelings_not_found': 'Feelings not found',
        'completion_text_missing': 'Completion text missing',
        'feelings_text_missing': 'Feelings description missing',
        'completion_load_error': 'Error loading completion',
        'feelings_load_error': 'Error loading feelings',
        'error_loading_task_details': 'Error loading task details',
        'task_completed_at': '''✅ <b>Completed:</b> {completed_at}''',
        'no_effect_description': '''No effect description''',
        'task_summary': '{task_count} uncompleted tasks.',
        'task_summary_single': '1 uncompleted task.',
        'task_summary_few': '{task_count} uncompleted tasks.',
        'task_summary_many': '{task_count} uncompleted tasks.',
        'task_summary_zero': '',
        'task_completion_invalid': '''❌ <b>Task not counted</b>

Reason: {validation_comment}

Please complete the task more thoroughly and meaningfully.''',

    'settings_tasks_limit': 'Tasks limit: {limit}',
    'task_settings_menu': 'Task Settings\n\nMax tasks per day: {max_tasks}',
    'tasks_limit_increased': 'Tasks limit increased to {new_limit}',
    'tasks_limit_decreased': 'Tasks limit decreased to {new_limit}',
    'awareness_level_insufficient_for_tasks_current': (
            'Your awareness level ({current_level}) insufficient. Max tasks: {current_max_tasks}. '
            'Keep a diary to grow! 📓'
        ),
    'tasks_limit_max_reached': 'Maximum tasks limit reached',
    'tasks_limit_min_reached': 'Minimum tasks limit reached',

    'task_completion_invalid_formatted': '''<b>⚠️ Needs a Little Work</b>\n\n{validation_comment}\n\n<i>Try to describe the task completion in more detail - what exactly you did, what thoughts and feelings arose.</i>''',
    'task_completion_invalid_default_comment': 'Try to describe it in more detail, I believe in you!',
    'task_effect_analysis_result_formatted': '''<b>🎯 Task Completion Result</b>\n\n💫 <b>Effect:</b> {effect_description}\n\n😊 <b>Mood Impact:</b> {mood_impact}\n\n<b>Analysis:</b> {detailed_analysis}\n\n💭 <b>Comment:</b> {comment}\n\n🌟 <b>Recommendation:</b> {recommendation}\n\n<i>You did great with the task! Keep up the good work! 💪</i>''',
    'task_analysis_error_formatted': '''<b>❌ An Error Occurred</b>\n\nUnfortunately, we couldn't analyze the task completion.\nTry completing the task again or come back to it later.''',
    'task_tokens_awarded': '🎉 You earned <b>{tokens}</b> tokens for completing the task! Your balance: <b>{balance}</b>.',
    'task_impact_chart_caption': '📊 Chart of task impact on mood and task complexity over the last {days} days.',
}
}