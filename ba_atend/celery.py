# ba_atend/celery.py

import os
from celery import Celery

# Define o módulo de configurações do Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ba_atend.settings')

# Cria a instância da aplicação Celery
app = Celery('ba_atend')

# Carrega as configurações do Django para o Celery, usando o prefixo CELERY
# Isso significa que as configurações do Celery no settings.py devem começar com 'CELERY_'
app.config_from_object('django.conf:settings', namespace='CELERY')

# Descobre as tasks automaticamente em todos os apps instalados
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')