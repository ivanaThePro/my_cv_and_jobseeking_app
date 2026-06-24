# Ivana Jovic CV Website

A Django-based CV site with an optional job-search dashboard.

## Setup

1. Create a virtual environment:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Copy environment file:
   ```powershell
   copy .env.example .env
   ```

4. Run migrations:
   ```bash
   python manage.py migrate
   ```

5. Start the dev server:
   ```bash
   python manage.py runserver
   ```

Visit `http://127.0.0.1:8000/cv/general/` for the CV, or `/jobs/market/` for the job dashboard.

## Tests

```powershell
python manage.py test
```

## Repository

https://github.com/ivanaThePro/my_cv_and_jobseeking_app

## Notes

- Set `CV_ACCESS_PASSWORD` in `.env` if you want password protection locally.
