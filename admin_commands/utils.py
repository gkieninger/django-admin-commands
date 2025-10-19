import logging

from django.core.management import get_commands, load_command_class

from .app_settings import ADMIN_COMMANDS_CONFIG

DEFAULT_INCLUDE_PREFIXES = ['admin_commands']
DEFAULT_EXCLUDE_PREFIXES = ['django.server', 'django.request', 'django.db']

def sync_commands():
    from .models import ManagementCommand
    commands_dict = get_commands()
    allowed_commands = ADMIN_COMMANDS_CONFIG['allowed_commands']
    commands_in_db = list(ManagementCommand.objects.all().values_list('name', flat=True))
    default_args = ''
    if allowed_commands == 'all':
        commands = commands_dict.keys()
    else:
        commands = list(allowed_commands)

    for command in commands:
        if type(command) is tuple:
            command, default_args = command

        org_command = command
        real_command = command
        if '__' in command:
            command = command.split('__')[0]
            real_command = command
        app_label = commands_dict.get(command, None)

        command = org_command
        if not app_label:
            raise ValueError(f'Command {command} not found in management commands')
        else:
            command_class = load_command_class(app_label, real_command)
            c, created = ManagementCommand.objects.get_or_create(name=command, app_label=app_label)
            c.help = command_class.help
            c.default_args = default_args
            c.deleted = False
            c.save()
            if not created and command in commands_in_db:
                commands_in_db.remove(command)
    ManagementCommand.objects.filter(name__in=commands_in_db).update(deleted=True)

class SelectiveFilter(logging.Filter):
    """Filter that suppresses unwanted loggers unless their level is ERROR or higher."""
    def __init__(self, exclude_prefixes=None):
        super().__init__()
        self.exclude_prefixes = exclude_prefixes or []

    def filter(self, record):
        # Always allow ERROR and CRITICAL messages
        if record.levelno >= logging.ERROR:
            return True
        # Skip logs from excluded prefixes (e.g. Django internals)
        if any(record.name.startswith(prefix) for prefix in self.exclude_prefixes):
            return False
        return True


def attach_handler(handler, include_prefixes=None, exclude_prefixes=None):
    """
    Attach a log handler to selected loggers dynamically.

    Reads configuration from Django settings under ADMIN_COMMANDS_LOG,
    or uses sensible defaults if not defined.

    - include_prefixes: only attach handler to loggers starting with these names
    - exclude_prefixes: ignore these loggers (except for ERROR+ messages)
    - log_level: defines handler log level
    """
    cfg = ADMIN_COMMANDS_CONFIG
    include_prefixes = cfg.get("include_prefixes", include_prefixes or DEFAULT_INCLUDE_PREFIXES)
    exclude_prefixes = cfg.get("exclude_prefixes", exclude_prefixes or DEFAULT_EXCLUDE_PREFIXES)
    log_level = cfg.get("log_level", logging.INFO)

    # Configure the handler
    handler.setLevel(log_level)
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    handler.addFilter(SelectiveFilter(exclude_prefixes))

    active_loggers = []

    # Attach handler to selected loggers
    for name, logger in logging.root.manager.loggerDict.items():
        if not isinstance(logger, logging.Logger):
            continue

        # Skip if not in include list (unless include_prefixes is empty)
        if include_prefixes and not any(name.startswith(prefix) for prefix in include_prefixes):
            continue

        logger.addHandler(handler)
        active_loggers.append(logger)

    return active_loggers