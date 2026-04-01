from django.db import models


class LogisticTask(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=120)
    status = models.CharField(max_length=30, default="PENDIENTE")
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "logistic_task"

    def __str__(self) -> str:
        return self.name
