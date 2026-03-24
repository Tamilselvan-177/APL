# Generated manually — remove top-N promotion; cutoff only

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("contest", "0007_round_promotion_cutoff_score_round_promotion_top_n"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="round",
            name="promotion_top_n",
        ),
    ]
