from django.db import models
class ProcessedFile(models.Model):
    file_name = models.CharField(max_length=255)
    status = models.CharField(max_length=50, default='Processando')
    upload_date = models.DateTimeField(auto_now_add=True)
    download_url = models.CharField(max_length=255, null=True, blank=True)
    task_id = models.CharField(max_length=50, null=True, blank=True)

    def __str__(self):
        return self.file_name