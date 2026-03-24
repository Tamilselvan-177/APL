"""
Create sample Weeks + Rounds if the schedule is empty.
Run: py manage.py seed_weeks
"""

from datetime import date, timedelta

from django.core.management.base import BaseCommand

from contest.models import Round, Week


class Command(BaseCommand):
    help = "Seed Week 1 / Week 2 with Round 1–3 (only if no weeks exist)."

    def handle(self, *args, **options):
        if Week.objects.exists():
            self.stdout.write(self.style.WARNING("Weeks already exist — nothing to seed."))
            return

        today = date.today()
        w1 = Week.objects.create(
            title="Week 1",
            start_date=today,
            end_date=today + timedelta(days=6),
            is_active=True,
        )
        for i in range(1, 4):
            Round.objects.create(
                week=w1,
                round_name=f"Round {i}",
                order_number=i,
                is_active=(i == 1),
            )

        w2_start = today + timedelta(days=7)
        w2 = Week.objects.create(
            title="Week 2",
            start_date=w2_start,
            end_date=w2_start + timedelta(days=6),
            is_active=False,
        )
        for i in range(1, 4):
            Round.objects.create(
                week=w2,
                round_name=f"Round {i}",
                order_number=i,
                is_active=False,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {Week.objects.count()} week(s) with rounds. "
                "Open Admin → Weeks to see the nested schedule."
            )
        )
