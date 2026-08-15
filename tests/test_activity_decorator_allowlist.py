"""P2: TG handlers не должны декорировать шумовые activity_type."""

from pathlib import Path
import re

from diary.services.activity_service import ACTIVITY_ALLOWLIST, is_allowed_activity_type

REPO_ROOT = Path(__file__).resolve().parents[1]
HANDLERS_DIR = REPO_ROOT / 'bot' / 'handlers'

DECORATOR_RE = re.compile(
    r"@log_user_activity\(\s*['\"](?P<atype>[^'\"]+)['\"]",
    re.M,
)


def test_all_tg_activity_decorators_are_allowlisted():
    offenders: list[str] = []
    for path in sorted(HANDLERS_DIR.rglob('*.py')):
        text = path.read_text(encoding='utf-8')
        for match in DECORATOR_RE.finditer(text):
            atype = match.group('atype')
            if not is_allowed_activity_type(atype):
                offenders.append(f'{path.relative_to(REPO_ROOT)}: {atype}')
    assert offenders == [], 'Noise decorators still present:\n' + '\n'.join(offenders)


def test_known_noise_types_absent_from_handlers():
    noise = {
        'help_open',
        'fallback',
        'button',
        'settings',
        'task',
        'task_chart_viewed',
        'entry_process',
        'entry_invalide',
        'edit_profile',
        'delete_profile',
    }
    found: list[str] = []
    for path in HANDLERS_DIR.rglob('*.py'):
        text = path.read_text(encoding='utf-8')
        for match in DECORATOR_RE.finditer(text):
            atype = match.group('atype')
            if atype in noise:
                found.append(f'{path.name}:{atype}')
    assert found == []
    # sanity: allowlist still includes core product events
    assert 'entry_created' in ACTIVITY_ALLOWLIST
    assert 'task_completed' in ACTIVITY_ALLOWLIST
