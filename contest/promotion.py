"""
Promotion helpers: move participants from one schedule Round to eligibility for the next.
"""

from django.db.models import Sum
from django.utils import timezone

from .models import Participant, QuizAttempt, Round, Submission


def promote_participants_to_next_round(participant_ids, source_round):
    """
    Mark ``source_round`` as completed for each participant and set their progress
    to the next round in the same week (so they can play when that round is active).

    Returns ``(count_promoted, error_message)``. ``error_message`` is None on success.
    """
    next_round = Round.objects.filter(
        week=source_round.week,
        order_number=source_round.order_number + 1,
    ).first()
    if not next_round:
        return None, (
            f"No next round in {source_round.week.title}. "
            f"Create a round with order {source_round.order_number + 1} first."
        )

    count = 0
    for pid in participant_ids:
        try:
            participant = Participant.objects.get(pk=pid)
        except Participant.DoesNotExist:
            continue

        total_on_round = (
            Submission.objects.filter(
                participant=participant,
                round=source_round,
            ).aggregate(t=Sum("score"))["t"]
            or 0
        )

        att, created = QuizAttempt.objects.get_or_create(
            participant=participant,
            schedule_round=source_round,
            defaults={
                "round_number": source_round.order_number,
                "is_completed": True,
                "completed_at": timezone.now(),
                "time_taken": 0,
                "total_score": total_on_round,
            },
        )
        if not created:
            att.is_completed = True
            att.completed_at = timezone.now()
            att.total_score = total_on_round
            att.save()

        if source_round.order_number == 1:
            participant.round1_completed = True
        elif source_round.order_number == 2:
            participant.round2_completed = True

        participant.current_round = next_round.order_number
        if next_round.order_number >= 2:
            participant.can_access_round2 = True
        participant.save()
        count += 1

    return count, None
