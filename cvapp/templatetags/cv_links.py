from django import template

from cvapp.course_links import course_syllabus_url

register = template.Library()


@register.simple_tag
def syllabus_url(course_code: str) -> str:
    return course_syllabus_url(course_code)


@register.simple_tag
def syllabus_backup_url(course_code: str) -> str:
    return course_syllabus_backup_path(course_code)
