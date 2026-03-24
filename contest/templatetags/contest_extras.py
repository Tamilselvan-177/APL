from django import template

from ..time_display import format_duration_seconds

register = template.Library()


@register.filter(name="duration_fmt")
def duration_fmt(value):
    """Template: {{ seconds|duration_fmt }}"""
    return format_duration_seconds(value)
