from collections import defaultdict
import random
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.forms import AuthenticationForm
from .forms import RegistrationForm
import csv
import io
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from .models import Question
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.forms import AuthenticationForm
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
import json
from django.db import IntegrityError
from django.db.models import Sum, Q
from django.db.models.functions import Coalesce
from .forms import RegistrationForm
from .models import Participant, Question, Submission, QuizAttempt, Week, Round
from .time_display import format_duration_seconds


def get_active_week():
    return Week.objects.filter(is_active=True).first()


def get_active_round_for_week(week):
    if not week:
        return None
    return week.rounds.filter(is_active=True).order_by("order_number").first()


def effective_quiz_question_count(schedule_round):
    """How many questions the quiz shows for this round (same logic as ``quiz`` view)."""
    if not schedule_round:
        return None
    n = Question.objects.filter(round=schedule_round, is_active=True).count()
    cap = schedule_round.total_questions
    if n == 0:
        return cap
    return min(n, cap)


def shuffled_questions_for_attempt(attempt, active_round):
    """
    Question pool for this round (first N by ``order``, ``id``), then shuffled.

    Order is different per quiz attempt (each ``QuizAttempt`` has a unique id) but
    stable across page refreshes for the same attempt (seed = attempt.pk).
    """
    q_base = Question.objects.filter(
        is_active=True,
        round=active_round,
    ).order_by("order", "id")
    pool = list(q_base[: active_round.total_questions])
    rng = random.Random(int(attempt.pk))
    rng.shuffle(pool)
    return pool


def question_ids_for_attempt(attempt, active_round):
    """Set of question PKs the user is allowed to answer in this open attempt."""
    return {q.id for q in shuffled_questions_for_attempt(attempt, active_round)}


def build_answer_sheet_rows(attempt, schedule_r, submissions_qs):
    """
    Full quiz question list (same order as during the attempt via shuffle seed), including
    questions the user never submitted. Unanswered rows show the correct option in green only.
    """
    letters = ("A", "B", "C", "D")
    if schedule_r:
        questions = shuffled_questions_for_attempt(attempt, schedule_r)
    else:
        questions = list(
            Question.objects.filter(
                is_active=True,
                round_number=attempt.round_number,
            ).order_by("order", "id")[:500]
        )

    subs_by_qid = {s.question_id: s for s in submissions_qs.select_related("question")}
    rows = []
    for idx, q in enumerate(questions, start=1):
        sub = subs_by_qid.get(q.id)
        user_letter = ""
        if sub:
            user_letter = (sub.selected_answer or "").strip().upper()[:1]
        correct = q.correct_answer
        options = []
        for L in letters:
            text = getattr(q, f"option_{L.lower()}")
            if sub is None:
                kind = "correct_only" if L == correct else "neutral"
            elif L == correct and L == user_letter:
                kind = "correct_user"
            elif L == correct:
                kind = "correct_only"
            elif L == user_letter:
                kind = "wrong_user"
            else:
                kind = "neutral"
            options.append({"letter": L, "text": text, "kind": kind})
        rows.append(
            {
                "num": idx,
                "question": q,
                "submission": sub,
                "unanswered": sub is None,
                "options": options,
            }
        )
    return rows


def previous_schedule_rounds_completed(participant, schedule_round):
    """All earlier rounds in the same week must be completed before this one."""
    if not schedule_round:
        return False
    if schedule_round.order_number <= 1:
        return True
    earlier_ids = schedule_round.week.rounds.filter(
        order_number__lt=schedule_round.order_number
    ).order_by("order_number").values_list("id", flat=True)
    for rid in earlier_ids:
        if not QuizAttempt.objects.filter(
            participant=participant, schedule_round_id=rid, is_completed=True
        ).exists():
            return False
    return True


def get_open_quiz_attempt(participant, active_round, round_number):
    """Prefer attempts tied to the schedule Round (weekly model)."""
    if active_round:
        attempt = QuizAttempt.objects.filter(
            participant=participant,
            schedule_round=active_round,
            is_completed=False,
        ).first()
        if attempt:
            return attempt
    return QuizAttempt.objects.filter(
        participant=participant,
        round_number=round_number,
        schedule_round__isnull=True,
        is_completed=False,
    ).first()


def home(request):
    active_week = get_active_week()
    active_round = get_active_round_for_week(active_week)
    rounds_preview = []
    if active_week:
        rounds_preview = list(
            active_week.rounds.order_by("order_number", "id").values(
                "round_name", "order_number", "duration_seconds", "total_questions"
            )[:12]
        )
    return render(
        request,
        "home.html",
        {
            "active_week": active_week,
            "active_round": active_round,
            "rounds_preview": rounds_preview,
        },
    )

def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            try:
                user = form.save()
            except IntegrityError:
                form.add_error(
                    "email",
                    "This email is already registered. Please sign in or use another email.",
                )
                messages.error(request, "Could not create account — email may already be in use.")
            else:
                login(request, user)
                messages.success(
                    request,
                    f"Welcome {user.username}! Your account has been created.",
                )
                return redirect("dashboard")
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = RegistrationForm()
    
    return render(request, 'register.html', {'form': form})

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {username}!')
                return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = AuthenticationForm()
    
    return render(request, 'login.html', {'form': form})

def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out successfully.')
    return redirect('home')

@login_required
def dashboard(request):
    participant = request.user.participant

    active_week = get_active_week()
    active_round = get_active_round_for_week(active_week)

    ongoing_attempt = None
    if active_week:
        ongoing_attempt = QuizAttempt.objects.filter(
            participant=participant,
            is_completed=False,
            schedule_round__week=active_week,
        ).first()
    if ongoing_attempt is None:
        ongoing_attempt = QuizAttempt.objects.filter(
            participant=participant, is_completed=False
        ).first()

    round_rows = []
    if active_week:
        ordered = active_week.rounds.order_by("order_number", "id")
        for r in ordered:
            prev_done = True
            for prev in ordered:
                if prev.order_number >= r.order_number:
                    break
                if not QuizAttempt.objects.filter(
                    participant=participant,
                    schedule_round=prev,
                    is_completed=True,
                ).exists():
                    prev_done = False
                    break
            completed = QuizAttempt.objects.filter(
                participant=participant, schedule_round=r, is_completed=True
            ).exists()
            in_progress = QuizAttempt.objects.filter(
                participant=participant, schedule_round=r, is_completed=False
            ).exists()
            bank = Question.objects.filter(is_active=True, round=r).count()
            shown = min(bank, r.total_questions)
            round_rows.append(
                {
                    "schedule_round": r,
                    "completed": completed,
                    "in_progress": in_progress,
                    "previous_done": prev_done,
                    "question_count": shown,
                    "question_bank_count": bank,
                    "question_limit": r.total_questions,
                }
            )

    context = {
        'participant': participant,
        'ongoing_attempt': ongoing_attempt,
        'active_week': active_week,
        'active_round': active_round,
        'round_rows': round_rows,
    }
    return render(request, 'dashboard.html', context)


@login_required
def start_quiz(request, round_number):
    """Start a quiz for a specific round"""
    participant = request.user.participant
    active_week = get_active_week()
    active_round = get_active_round_for_week(active_week)

    if not active_week or not active_round:
        messages.error(request, 'No active week/round configured by admin')
        return redirect('dashboard')

    if active_round.order_number != round_number:
        messages.error(
            request,
            f'Only {active_round.round_name} is active for {active_week.title}'
        )
        return redirect('dashboard')

    if not previous_schedule_rounds_completed(participant, active_round):
        messages.error(request, "Complete earlier rounds in this week first.")
        return redirect("dashboard")

    if QuizAttempt.objects.filter(
        participant=participant, schedule_round=active_round, is_completed=True
    ).exists():
        messages.warning(request, "You have already completed this round.")
        return redirect("dashboard")

    existing_attempt = get_open_quiz_attempt(participant, active_round, round_number)
    if existing_attempt:
        return redirect('quiz', round_number=round_number)

    QuizAttempt.objects.create(
        participant=participant,
        round_number=round_number,
        schedule_round=active_round,
    )

    messages.success(request, f'{active_round.round_name} started! Good luck!')
    return redirect('quiz', round_number=round_number)


@login_required
def quiz(request, round_number):
    """Display quiz questions"""
    participant = request.user.participant
    active_week = get_active_week()
    active_round = get_active_round_for_week(active_week)
    if not active_week or not active_round:
        messages.error(request, 'No active week/round configured by admin')
        return redirect('dashboard')
    if round_number != active_round.order_number:
        messages.error(request, 'This round is not active right now')
        return redirect('dashboard')

    attempt = get_open_quiz_attempt(participant, active_round, round_number)
    if not attempt:
        messages.error(request, 'No active quiz attempt found')
        return redirect('dashboard')

    duration = active_round.duration_seconds

    # Same pool as DB order would give, but shuffled per attempt (stable for this attempt)
    questions = shuffled_questions_for_attempt(attempt, active_round)
    q_ids = [q.id for q in questions]

    subs_by_q = {
        s.question_id: s
        for s in Submission.objects.filter(
            participant=participant, question_id__in=q_ids
        ).select_related("question")
    }
    quiz_rows = []
    for q in questions:
        quiz_rows.append({"question": q, "submission": subs_by_q.get(q.id)})

    # Calculate elapsed time
    elapsed_seconds = int((timezone.now() - attempt.started_at).total_seconds())
    remaining_seconds = max(0, duration - elapsed_seconds)
    
    # Auto-submit if time expired
    if remaining_seconds == 0:
        return redirect('submit_quiz', round_number=round_number)
    
    context = {
        'participant': participant,
        'round_number': round_number,
        'active_round': active_round,
        'questions': questions,
        'quiz_rows': quiz_rows,
        'duration': duration,
        'elapsed_seconds': elapsed_seconds,
        'remaining_seconds': remaining_seconds,
        'attempt': attempt,
    }
    return render(request, 'quiz.html', context)


@login_required
@require_http_methods(["POST"])
def submit_answer(request):
    """Submit answer for a single question (AJAX)"""
    try:
        data = json.loads(request.body)
        question_id = data.get('question_id')
        selected_answer = data.get('selected_answer')
        time_taken = data.get('time_taken', 0)
        
        participant = request.user.participant
        question = get_object_or_404(Question, id=question_id)

        active_week = get_active_week()
        active_round = get_active_round_for_week(active_week)
        if not active_round:
            return JsonResponse(
                {"success": False, "message": "No active round."}, status=400
            )

        attempt = get_open_quiz_attempt(
            participant, active_round, active_round.order_number
        )
        if not attempt:
            return JsonResponse(
                {"success": False, "message": "No active quiz attempt."},
                status=400,
            )
        allowed_ids = question_ids_for_attempt(attempt, active_round)
        if question.id not in allowed_ids:
            return JsonResponse(
                {
                    "success": False,
                    "message": "This question is not part of your current quiz set.",
                },
                status=400,
            )

        if question.round_id:
            if question.round_id != active_round.id:
                return JsonResponse(
                    {"success": False, "message": "This question is not in the current round."},
                    status=400,
                )
        elif question.round_number != active_round.order_number:
            return JsonResponse(
                {"success": False, "message": "This question is not in the current round."},
                status=400,
            )

        # Check if already submitted
        existing_submission = Submission.objects.filter(
            participant=participant,
            question=question
        ).first()
        
        if existing_submission:
            return JsonResponse({
                'success': False,
                'message': 'Answer already submitted for this question'
            })
        
        # Create submission
        submission = Submission.objects.create(
            participant=participant,
            question=question,
            round_number=question.round_number,
            round=question.round,
            selected_answer=selected_answer,
            time_taken=time_taken
        )
        
        payload = {
            "success": True,
            "is_correct": submission.is_correct,
            "points_earned": submission.points_earned,
            "total_score": participant.total_score,
        }
        if not submission.is_correct:
            payload["correct_answer"] = question.correct_answer
        return JsonResponse(payload)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)


@login_required
def submit_quiz(request, round_number):
    """Submit entire quiz and mark as completed"""
    participant = request.user.participant
    active_week = get_active_week()
    active_round = get_active_round_for_week(active_week)
    attempt = None
    if active_round and active_round.order_number == round_number:
        attempt = QuizAttempt.objects.filter(
            participant=participant,
            schedule_round=active_round,
            is_completed=False,
        ).first()
    if attempt is None:
        attempt = QuizAttempt.objects.filter(
            participant=participant,
            round_number=round_number,
            is_completed=False,
        ).first()

    if not attempt:
        messages.error(request, 'No active quiz attempt found')
        return redirect('dashboard')

    time_taken = int((timezone.now() - attempt.started_at).total_seconds())

    schedule_r = attempt.schedule_round
    if schedule_r:
        total_score = (
            Submission.objects.filter(
                participant=participant, round=schedule_r, is_correct=True
            ).aggregate(total=Sum("points_earned"))["total"]
            or 0
        )
    else:
        total_score = (
            Submission.objects.filter(
                participant=participant,
                round_number=round_number,
                is_correct=True,
            ).aggregate(total=Sum("points_earned"))["total"]
            or 0
        )

    attempt.is_completed = True
    attempt.completed_at = timezone.now()
    attempt.time_taken = time_taken
    attempt.total_score = total_score
    attempt.save()

    if schedule_r:
        if schedule_r.order_number == 1:
            participant.round1_completed = True
            participant.round1_time_taken = time_taken
        elif schedule_r.order_number == 2:
            participant.round2_completed = True
            participant.round2_time_taken = time_taken
        participant.total_time_taken = (
            participant.round1_time_taken + participant.round2_time_taken
        )
        participant.save()

    messages.success(
        request,
        f"Round {round_number} completed! Your total score: {participant.total_score}",
    )
    return redirect('quiz_result', round_number=round_number)


@login_required
def quiz_result(request, round_number):
    """Display quiz results"""
    participant = request.user.participant
    active_week = get_active_week()
    attempt = None
    schedule_r = None
    if active_week:
        schedule_r = Round.objects.filter(
            week=active_week, order_number=round_number
        ).first()
    if schedule_r:
        attempt = QuizAttempt.objects.filter(
            participant=participant,
            schedule_round=schedule_r,
            is_completed=True,
        ).first()
    if attempt is None:
        attempt = QuizAttempt.objects.filter(
            participant=participant,
            round_number=round_number,
            is_completed=True,
        ).first()

    if not attempt:
        messages.error(request, 'Quiz attempt not found')
        return redirect('dashboard')

    # Prefer the schedule round tied to this attempt (stats stay correct if active week changes)
    if getattr(attempt, "schedule_round", None):
        schedule_r = attempt.schedule_round
    elif active_week:
        schedule_r = Round.objects.filter(
            week=active_week, order_number=round_number
        ).first()

    if schedule_r:
        submissions = Submission.objects.filter(
            participant=participant, round=schedule_r
        ).select_related("question")
    else:
        submissions = Submission.objects.filter(
            participant=participant, round_number=round_number
        ).select_related("question")
    
    correct_count = submissions.filter(is_correct=True).count()
    wrong_count = submissions.filter(is_correct=False).count()
    attempted_count = submissions.count()

    # Among questions the user actually submitted an answer for
    answer_accuracy = (
        (correct_count / attempted_count * 100) if attempted_count > 0 else 0.0
    )

    quiz_length = effective_quiz_question_count(schedule_r) if schedule_r else None
    unanswered_in_round = None
    if quiz_length is not None:
        unanswered_in_round = max(0, quiz_length - attempted_count)

    # Correct ÷ all questions in the round (matches the summary line "X% of full round")
    round_accuracy = None
    if quiz_length and quiz_length > 0:
        round_accuracy = round(100.0 * correct_count / quiz_length, 2)

    # Progress bar: full-round % when we know quiz size; otherwise attempts-only
    if round_accuracy is not None:
        bar_accuracy = float(round_accuracy)
    else:
        bar_accuracy = round(answer_accuracy, 2)

    accuracy = bar_accuracy

    # Category breakdown (Django templates — no Jinja selectattr)
    cat_labels = {
        "quantitative": "Quantitative",
        "logical": "Logical Reasoning",
        "verbal": "Verbal Reasoning",
    }
    cat_stats = defaultdict(lambda: {"correct": 0, "total": 0})
    for sub in submissions:
        c = sub.question.category
        cat_stats[c]["total"] += 1
        if sub.is_correct:
            cat_stats[c]["correct"] += 1
    category_breakdown = []
    for cat, d in sorted(cat_stats.items()):
        total_c = d["total"]
        correct_c = d["correct"]
        pct = round(100 * correct_c / total_c, 1) if total_c else 0.0
        category_breakdown.append(
            {
                "key": cat,
                "label": cat_labels.get(cat, cat),
                "correct": correct_c,
                "total": total_c,
                "percentage": pct,
            }
        )

    context = {
        'participant': participant,
        'round_number': round_number,
        'attempt': attempt,
        'submissions': submissions,
        'correct_count': correct_count,
        'wrong_count': wrong_count,
        'attempted_count': attempted_count,
        'quiz_length': quiz_length,
        'unanswered_in_round': unanswered_in_round,
        'answer_accuracy': round(answer_accuracy, 2),
        'round_accuracy': round_accuracy,
        'bar_accuracy': round(bar_accuracy, 2),
        'accuracy': round(accuracy, 2),
        'category_breakdown': category_breakdown,
    }
    return render(request, 'quiz_result.html', context)


@login_required
def quiz_answer_sheet(request, round_number):
    """Full answer sheet: all options, user's pick, correct answer (green/red)."""
    participant = request.user.participant
    active_week = get_active_week()
    attempt = None
    schedule_r = None
    if active_week:
        schedule_r = Round.objects.filter(
            week=active_week, order_number=round_number
        ).first()
    if schedule_r:
        attempt = QuizAttempt.objects.filter(
            participant=participant,
            schedule_round=schedule_r,
            is_completed=True,
        ).first()
    if attempt is None:
        attempt = QuizAttempt.objects.filter(
            participant=participant,
            round_number=round_number,
            is_completed=True,
        ).order_by("-completed_at", "-id").first()

    if not attempt:
        messages.error(request, "No completed quiz found for this round.")
        return redirect("dashboard")

    # Use the round from the attempt so question set matches the quiz you took (even if week changed)
    attempt_round = getattr(attempt, "schedule_round", None)
    if attempt_round is not None:
        schedule_r = attempt_round

    if schedule_r:
        submissions = Submission.objects.filter(
            participant=participant, round=schedule_r
        )
    else:
        submissions = Submission.objects.filter(
            participant=participant, round_number=round_number
        )

    sheet_rows = build_answer_sheet_rows(attempt, schedule_r, submissions)
    if not sheet_rows:
        messages.info(request, "No questions are configured for this round.")
        return redirect("dashboard")

    context = {
        "participant": participant,
        "round_number": round_number,
        "attempt": attempt,
        "schedule_round": schedule_r or getattr(attempt, "schedule_round", None),
        "sheet_rows": sheet_rows,
    }
    return render(request, "quiz_answer_sheet.html", context)


def _leaderboard_queryset(active_week, scope_round=None):
    """
    Ordered participants + aggregated submission score.

    - ``scope_round`` set: scores only for that round (must belong to ``active_week``).
    - ``scope_round`` None (“whole week” on the board): **all weeks combined** — sums
      every submission across past inactive weeks and the current active week, since only
      one week is active at a time but history should still count on the total board.
    """
    if scope_round is not None:
        if not active_week:
            return Participant.objects.none()
        return (
            Participant.objects.filter(submissions__round=scope_round)
            .annotate(leaderboard_score=Sum("submissions__score"))
            .order_by("-leaderboard_score", "total_time_taken")
            .distinct()
        )

    # All-time cumulative total (every Week / Round that has submissions)
    return (
        Participant.objects.annotate(
            leaderboard_score=Coalesce(Sum("submissions__score"), 0),
        )
        .filter(leaderboard_score__gt=0)
        .order_by("-leaderboard_score", "total_time_taken")
    )


@login_required
def leaderboard(request):
    """Leaderboard: one round (active week) or all-weeks cumulative total."""
    active_week = get_active_week()
    round_options = []
    scope_round = None

    if active_week:
        round_options = list(active_week.rounds.order_by("order_number", "id"))
        rid = request.GET.get("round_id")
        if rid:
            try:
                scope_round = active_week.rounds.get(pk=int(rid))
            except (ValueError, Round.DoesNotExist):
                scope_round = None

    participants = list(_leaderboard_queryset(active_week, scope_round))

    cp = request.user.participant
    your_rank = None
    your_board_score = 0
    for i, p in enumerate(participants, 1):
        if p.pk == cp.pk:
            your_rank = i
            your_board_score = getattr(p, "leaderboard_score", 0) or 0
            break

    if your_rank is None:
        if scope_round:
            your_board_score = (
                Submission.objects.filter(participant=cp, round=scope_round).aggregate(
                    t=Sum("score")
                )["t"]
                or 0
            )
        else:
            your_board_score = (
                Submission.objects.filter(participant=cp).aggregate(t=Sum("score"))[
                    "t"
                ]
                or 0
            )

    score_label = (
        f"{scope_round.round_name} score"
        if scope_round
        else "All weeks total score"
    )

    context = {
        "participants": participants,
        "current_participant": cp,
        "active_week": active_week,
        "round_options": round_options,
        "scope_round": scope_round,
        "your_rank": your_rank,
        "your_board_score": your_board_score,
        "score_label": score_label,
        "leaderboard_all_weeks_total": scope_round is None,
    }
    return render(request, "leaderboard.html", context)


@login_required
@require_http_methods(["GET"])
def leaderboard_api(request):
    """JSON leaderboard: ?round_id= optional. Omit round_id for cumulative score all weeks."""
    active_week = get_active_week()
    scope_round = None
    if active_week and request.GET.get("round_id"):
        try:
            scope_round = active_week.rounds.get(pk=int(request.GET["round_id"]))
        except (ValueError, Round.DoesNotExist):
            scope_round = None

    participants = list(_leaderboard_queryset(active_week, scope_round)[:50])

    data = []
    for idx, p in enumerate(participants, 1):
        tsec = p.total_time_taken
        data.append(
            {
                "rank": idx,
                "name": p.full_name,
                "username": p.user.username,
                "score": getattr(p, "leaderboard_score", 0) or 0,
                "round": p.current_round,
                "time": tsec,
                "time_display": format_duration_seconds(tsec),
                "is_current_user": p.user.id == request.user.id,
            }
        )

    return JsonResponse(
        {
            "leaderboard": data,
            "scope": "round" if scope_round else "all_weeks_cumulative",
            "round_id": scope_round.id if scope_round else None,
            "round_name": scope_round.round_name if scope_round else None,
            "active_week_title": active_week.title if active_week else None,
        }
    )