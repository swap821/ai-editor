import re

def slugify(title):
    title = title.lower()
    title = re.sub(r'[^a-z0-9 ]', '', title)
    title = re.sub(r'\s+', '-', title)
    return title.strip('-')