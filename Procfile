release: flask db upgrade
web: gunicorn run:app --workers 2 --timeout 60 --log-file -