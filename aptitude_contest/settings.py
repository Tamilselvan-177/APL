
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'arq-contest-KEY-IF-YOU-ARE-READING-THIS-YOUR-KEY-IS-IN-DANGER-I-KNOW'

DEBUG = True

# Host header is ONLY the domain (no "https://"). ngrok URLs change each run unless you use a reserved domain.
ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "metastatic-nonrevoltingly-maryalice.ngrok-free.dev",
    ".ngrok-free.dev",  # any *.ngrok-free.dev tunnel (free tier)
    "apl-1-kqah.onrender.com",
    ".onrender.com",  # other Render services / preview deploys
    "172.16.78.233",
]

# Required for POST/login behind HTTPS (e.g. ngrok). Include scheme — unlike ALLOWED_HOSTS.
# When ngrok gives a new URL, add it here (or set env DJANGO_CSRF_TRUSTED_ORIGINS=comma-separated).
CSRF_TRUSTED_ORIGINS = [
    "http://172.16.78.233:80",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "https://metastatic-nonrevoltingly-maryalice.ngrok-free.dev",
    "https://apl-1-kqah.onrender.com",
]
_extra_csrf = os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "")
if _extra_csrf:
    CSRF_TRUSTED_ORIGINS.extend(
        o.strip() for o in _extra_csrf.split(",") if o.strip()
    )

INSTALLED_APPS = [
        "jazzmin",

    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'contest',  # Our app
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'aptitude_contest.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]
JAZZMIN_SETTINGS = {
    "site_title": "Aptitude Contest Admin",
    "site_header": "Aptitude Contest",
    "site_brand": "Contest Dashboard",
    # Logo to appear in the top left (optional)
    # "site_logo": "images/logo.png", 
    "welcome_sign": "Welcome to the Contest Control Panel",
    "copyright": "Aptitude Contest",
    "search_model": ["auth.User", "contest.Participant"],

    "topmenu_links": [
        {"name": "Home", "url": "admin:index"},
        {"model": "auth.User"},
        {"app": "contest"},
    ],

    "show_sidebar": True,
    "navigation_expanded": True,
    "order_with_respect_to": ["auth", "contest"],
    
    "icons": {
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "contest.participant": "fas fa-user-graduate",
        "contest.question": "fas fa-brain",
        "contest.submission": "fas fa-file-signature",
    },
    # Use "cyborg" for a deeper black background than "darkly"
    "theme": "cyborg",
}

JAZZMIN_UI_TWEAKS = {
    # The 'cyborg' theme is the darkest available Bootswatch theme
    "theme": "cyborg",
    
    # UI Components
    "navbar": "navbar-dark",
    "no_navbar_border": True,
    "sidebar": "sidebar-dark-primary",
    "accent": "accent-primary",
    
    # Sidebar styling
    "sidebar_nav_child_indent": True,
    "sidebar_nav_compact_style": True,
    "sidebar_nav_small_text": False,
    "brand_small_text": False,
    
    # Dark UI (replaces deprecated dark_mode_theme in Jazzmin 3+)
    "default_theme_mode": "dark",
    "layout_boxed": False,
}

WSGI_APPLICATION = 'aptitude_contest.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Required when DEBUG=False: Django does not serve /static/; WhiteNoise does.
# True = use app static (Jazzmin) without running collectstatic (fine for dev/ngrok).
# In production after collectstatic, set DJANGO_WHITENOISE_FINDERS=false for efficiency.
WHITENOISE_USE_FINDERS = os.environ.get(
    "DJANGO_WHITENOISE_FINDERS", "true"
).lower() in ("1", "true", "yes")

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'home'
