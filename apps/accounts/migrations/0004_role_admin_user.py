from django.db import migrations, models


def backfill_role(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(is_staff=True).update(role="admin")
    User.objects.filter(is_superuser=True).update(role="admin")
    User.objects.exclude(is_staff=True).exclude(is_superuser=True).update(role="user")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_alter_user_role'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(choices=[('admin', 'Admin'), ('user', 'User')], default='user', max_length=32),
        ),
        migrations.RunPython(backfill_role, noop),
    ]
