
# Create your models here.
# MODULE 2: USER AUTHENTICATION SYSTEM
# ======================================

# ==============================================
# FILE: contest/models.py
# ==============================================

from django.db import models
from django.db.models import Q
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class Week(models.Model):
    """Weekly contest window. Only one week can be active."""

    title = models.CharField(max_length=100, unique=True)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)

    class Meta:
        ordering = ["-start_date"]
        verbose_name = "Week"
        verbose_name_plural = "Weeks (schedule)"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.is_active:
            Week.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)


class Round(models.Model):
    """Dynamic rounds inside a week."""

    week = models.ForeignKey(Week, on_delete=models.CASCADE, related_name="rounds")
    round_name = models.CharField(max_length=100)
    order_number = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=False)
    duration_seconds = models.PositiveIntegerField(
        default=1800,
        help_text="Quiz timer for this round (seconds). Default 1800 = 30 minutes.",
    )
    total_questions = models.PositiveIntegerField(
        default=30,
        help_text="Max number of questions to show in this round (picks first N by order).",
    )
    promotion_cutoff_score = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Minimum total score on this round to qualify for the next round. "
            "Admin uses this for promotion (list action + button). Leave empty to disable."
        ),
    )

    class Meta:
        ordering = ["week", "order_number", "id"]
        unique_together = [("week", "order_number"), ("week", "round_name")]
        verbose_name = "Round"
        verbose_name_plural = "Rounds (all weeks)"

    def __str__(self):
        return f"{self.week.title} - {self.round_name}"

    def save(self, *args, **kwargs):
        if self.is_active:
            Round.objects.filter(week=self.week).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)


class Participant(models.Model):
    """Extended user profile for contest participants"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='participant')
    full_name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    
    # Contest Status
    total_score = models.IntegerField(default=0)
    current_round = models.IntegerField(
        default=1,
        help_text="Last / furthest round order (display hint). Real progress: Quiz attempts.",
    )
    # Legacy booleans from the old fixed 2-round contest; still updated for R1/R2 for backwards compatibility.
    round1_completed = models.BooleanField(
        default=False,
        help_text="Legacy: set when schedule round order 1 is completed.",
    )
    round2_completed = models.BooleanField(
        default=False,
        help_text="Legacy: set when schedule round order 2 is completed.",
    )

    # Timing
    round1_time_taken = models.IntegerField(default=0)  # in seconds
    round2_time_taken = models.IntegerField(default=0)  # in seconds
    total_time_taken = models.IntegerField(default=0)  # in seconds

    # Access Control
    can_access_round2 = models.BooleanField(
        default=False,
        help_text="Legacy: old gate for round 2; weekly flow uses QuizAttempt + Round.",
    )
    
    # Timestamps
    registered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-total_score', 'total_time_taken']
    
    def __str__(self):
        return f"{self.full_name} ({self.user.username})"
    
    @property
    def rank(self):
        """Calculate current rank based on score and time"""
        participants = Participant.objects.all().order_by('-total_score', 'total_time_taken')
        for idx, participant in enumerate(participants, 1):
            if participant.id == self.id:
                return idx
        return None


class Question(models.Model):
    """Question model for quiz"""
    
    CATEGORY_CHOICES = [
        ('quantitative', 'Quantitative'),
        ('logical', 'Logical Reasoning'),
        ('verbal', 'Verbal Reasoning'),
    ]
    
    round_number = models.PositiveIntegerField(
        default=1,
        help_text="Legacy mirror of round order; prefer setting Round below.",
    )
    round = models.ForeignKey(
        Round,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="questions",
        help_text="Which schedule round (and thus which week) this question belongs to.",
    )
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    question_text = models.TextField(help_text="The question to be asked")
    
    # Options
    option_a = models.CharField(max_length=500)
    option_b = models.CharField(max_length=500)
    option_c = models.CharField(max_length=500)
    option_d = models.CharField(max_length=500)
    
    # Correct Answer
    ANSWER_CHOICES = [
        ('A', 'Option A'),
        ('B', 'Option B'),
        ('C', 'Option C'),
        ('D', 'Option D'),
    ]
    correct_answer = models.CharField(max_length=1, choices=ANSWER_CHOICES)
    
    # Metadata
    difficulty = models.CharField(max_length=10, choices=[
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ], default='medium')
    
    points = models.IntegerField(default=4, help_text="Points for this question")
    
    # Order
    order = models.IntegerField(default=0, help_text="Display order in quiz")
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["round__week", "round__order_number", "order", "category"]
        verbose_name = "Question"
        verbose_name_plural = "Questions"
    
    def __str__(self):
        if self.round_id:
            return f"{self.round.week.title} / {self.round.round_name} — {self.get_category_display()} Q{self.order}"
        return f"Round {self.round_number} (unlinked) — {self.get_category_display()} Q{self.order}"
    
    def get_correct_option(self):
        """Return the correct option text"""
        options = {
            'A': self.option_a,
            'B': self.option_b,
            'C': self.option_c,
            'D': self.option_d,
        }
        return options.get(self.correct_answer, '')


class Submission(models.Model):
    """Track user submissions for each question"""
    
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name='submissions')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='submissions')
    round_number = models.IntegerField(default=1)
    round = models.ForeignKey(
        Round,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submissions",
    )
    
    # Answer
    selected_answer = models.CharField(max_length=1, choices=[
        ('A', 'Option A'),
        ('B', 'Option B'),
        ('C', 'Option C'),
        ('D', 'Option D'),
    ])
    
    is_correct = models.BooleanField(default=False)
    points_earned = models.IntegerField(default=0)
    score = models.IntegerField(default=0)
    
    # Timing
    time_taken = models.IntegerField(default=0, help_text="Time in seconds to answer this question")
    submitted_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-submitted_at']
        unique_together = ['participant', 'question']
        verbose_name = "Submission"
        verbose_name_plural = "Submissions"
    
    def __str__(self):
        return f"{self.participant.full_name} - {self.question} - {'✓' if self.is_correct else '✗'}"
    
    def save(self, *args, **kwargs):
        # Auto-check if answer is correct
        if self.selected_answer == self.question.correct_answer:
            self.is_correct = True
            self.points_earned = self.question.points
        else:
            self.is_correct = False
            self.points_earned = 0
        self.score = self.points_earned
        if not self.round_id and self.question.round_id:
            self.round = self.question.round
        
        super().save(*args, **kwargs)
        
        # Update participant's total score
        self.update_participant_score()
    
    def update_participant_score(self):
        """Recalculate participant's total score"""
        participant = self.participant
        total_score = Submission.objects.filter(
            participant=participant,
            is_correct=True
        ).aggregate(total=models.Sum('points_earned'))['total'] or 0
        
        participant.total_score = total_score
        participant.save()


class QuizAttempt(models.Model):
    """Track quiz attempts to prevent re-attempts"""
    
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name='attempts')
    round_number = models.IntegerField(default=1)
    schedule_round = models.ForeignKey(
        Round,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attempts",
        help_text="Which schedule round (week + order) this attempt belongs to",
    )

    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    time_taken = models.IntegerField(default=0, help_text="Total time in seconds")
    total_score = models.IntegerField(default=0)
    
    is_completed = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-started_at']
        verbose_name = "Quiz Attempt"
        verbose_name_plural = "Quiz Attempts"
        constraints = [
            models.UniqueConstraint(
                fields=["participant", "schedule_round"],
                condition=Q(schedule_round__isnull=False),
                name="unique_participant_schedule_round_attempt",
            ),
        ]
    
    def __str__(self):
        status = "Completed" if self.is_completed else "In Progress"
        return f"{self.participant.full_name} - Round {self.round_number} - {status}"



# Signal to create Participant profile automatically
@receiver(post_save, sender=User)
def create_participant_profile(sender, instance, created, **kwargs):
    if created:
        # Participant requires full_name + unique email; RegistrationForm overwrites both right after.
        email = (instance.email or "").strip().lower()
        if not email:
            email = f"user-{instance.pk}@noreply.local"
        Participant.objects.create(
            user=instance,
            full_name=(instance.get_full_name() or instance.username or "Participant"),
            email=email,
        )

@receiver(post_save, sender=User)
def save_participant_profile(sender, instance, **kwargs):
    if hasattr(instance, 'participant'):
        instance.participant.save()

