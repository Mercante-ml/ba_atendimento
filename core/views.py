from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.core.files.storage import FileSystemStorage
from django.conf import settings
import os
from .models import ProcessedFile
from .tasks import processar_planilha_com_ia

def upload_file(request):
    if request.method == 'POST' and request.FILES['documento']:
        # Lida com o upload do arquivo
        uploaded_file = request.FILES['documento']
        fs = FileSystemStorage(location=os.path.join(settings.BASE_DIR, 'media'))
        filename = fs.save(uploaded_file.name, uploaded_file)
        
        # Cria um registro no banco de dados e inicia a tarefa Celery
        new_file = ProcessedFile.objects.create(file_name=filename)
        task = processar_planilha_com_ia.delay(new_file.id)
        new_file.task_id = task.id
        new_file.save()

        return redirect('file_status', file_id=new_file.id)
    
    return render(request, 'core/upload.html')

def file_status(request, file_id):
    processed_file = get_object_or_404(ProcessedFile, id=file_id)
    context = {'file': processed_file}
    return render(request, 'core/status.html', context)

def download_file(request, file_id):
    processed_file = get_object_or_404(ProcessedFile, id=file_id)
    file_path = os.path.join(settings.MEDIA_ROOT, processed_file.download_url)
    
    if os.path.exists(file_path):
        with open(file_path, 'rb') as fh:
            response = HttpResponse(fh.read(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            response['Content-Disposition'] = 'inline; filename=' + os.path.basename(file_path)
            return response
    raise Http404