from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("python", "0023_packageyank"),
    ]

    operations = [
        migrations.AddField(
            model_name="pythonrepository",
            name="error_on_reject",
            field=models.BooleanField(default=True),
        ),
    ]
