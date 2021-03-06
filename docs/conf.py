from sphinx_celery import conf

globals().update(conf.build_config(
    'jumpstarter', __file__,
    project='jumpstarter',
    version_dev='0.2',
    version_stable='0.1',
    canonical_url='http://docs.celeryproject.org',
    webdomain='celeryproject.org',
    github_project='celery/jumpstarter',
    author='Omer Katz & contributors',
    author_name='Omer Katz',
    copyright='2021',
    publisher='Celery Project',
    html_prepend_sidebars=['sidebardonations.html'],
))
