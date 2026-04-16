from datetime import timedelta


def format_duration(td: timedelta) -> str:
    """Formate une durée (timedelta) en 'Xm' ou 'Xh Ym'."""
    total_seconds = int(td.total_seconds())
    if total_seconds < 0:
        return "0m"

    hours = total_seconds // 3600
    minutes = (total_seconds // 60) % 60

    if total_seconds < 3600:
        return f"{total_seconds // 60}m"
    else:
        # Affiche '1h 5m' ou '1h 0m' selon ta préférence
        return f"{hours}h {minutes}m"
