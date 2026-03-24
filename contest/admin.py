from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils import timezone
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.contrib import messages
from django.db.models import Sum
import csv
from .models import Participant, Question, Submission, QuizAttempt, Week, Round
from .promotion import promote_participants_to_next_round
from .question_csv_import import (
    TEMPLATE_HEADERS,
    csv_template_content,
    import_questions_from_csv_text,
    import_questions_from_xlsx_bytes,
    xlsx_template_bytes,
)


class RoundInline(admin.TabularInline):
    """Nested under each Week: Round 1, Round 2, Round 3, …"""

    model = Round
    fk_name = "week"
    extra = 1
    min_num = 0
    can_delete = True
    show_change_link = True
    ordering = ("order_number", "id")
    fields = (
        "order_number",
        "round_name",
        "duration_seconds",
        "total_questions",
        "promotion_cutoff_score",
        "is_active",
    )


@admin.register(Week)
class WeekAdmin(admin.ModelAdmin):
    list_display = ["title", "start_date", "end_date", "is_active", "rounds_tree"]
    list_editable = ["is_active"]
    readonly_fields = ["rounds_tree_readonly"]
    fieldsets = (
        (
            None,
            {
                "fields": ("title", "start_date", "end_date", "is_active"),
                "description": "Only one week can be active at a time. Add rounds in the table below.",
            },
        ),
        (
            "Rounds preview",
            {
                "fields": ("rounds_tree_readonly",),
                "classes": ("collapse",),
            },
        ),
    )
    inlines = [RoundInline]
    save_on_top = True
    search_fields = ["title"]
    ordering = ("-start_date", "-id")
    actions = ["activate_selected_week"]

    @admin.display(description="Rounds (tree)")
    def rounds_tree(self, obj):
        if obj.pk is None:
            return "—"
        qs = obj.rounds.order_by("order_number", "id")
        if not qs.exists():
            return mark_safe(
                '<span style="color:#666">No rounds — open this week and add rows below.</span>'
            )
        lines = []
        for r in qs:
            # Static HTML: use mark_safe (format_html requires at least one format arg in Django 6+)
            star = (
                mark_safe(' <span style="color:#15803d;font-weight:600">★ active</span>')
                if r.is_active
                else ""
            )
            lines.append(
                format_html(
                    "├─ <strong>{}</strong>. {}{}",
                    r.order_number,
                    r.round_name,
                    star,
                )
            )
        return mark_safe("<br/>".join(str(line) for line in lines))

    @admin.display(description="Rounds in this week")
    def rounds_tree_readonly(self, obj):
        if obj.pk is None:
            return "Save the week first, then add rounds in the inline table."
        return self.rounds_tree(obj)

    def activate_selected_week(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Select exactly one week to activate.", messages.ERROR)
            return
        selected = queryset.first()
        Week.objects.update(is_active=False)
        selected.is_active = True
        selected.save()
        self.message_user(request, f"{selected.title} is now active.", messages.SUCCESS)
    activate_selected_week.short_description = "Activate selected week (deactivate others)"


@admin.register(Round)
class RoundAdmin(admin.ModelAdmin):
    change_form_template = "admin/contest/round/change_form.html"

    list_display = [
        "round_name",
        "week",
        "order_number",
        "duration_seconds",
        "total_questions",
        "promotion_cutoff_score",
        "is_active",
    ]
    search_fields = ["round_name", "week__title"]
    list_filter = ["week", "is_active"]
    list_editable = ["order_number", "is_active"]
    actions = [
        "activate_round_in_week",
        "promote_by_cutoff_to_next_round",
    ]

    def get_urls(self):
        urls = super().get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name
        custom = [
            path(
                "<path:object_id>/promote-by-cutoff/",
                self.admin_site.admin_view(self._promote_by_cutoff_button),
                name="%s_%s_promote_by_cutoff" % info,
            ),
        ]
        return custom + urls

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        if object_id:
            obj = self.get_object(request, object_id)
            if obj is not None:
                oid = str(obj.pk)
                if obj.promotion_cutoff_score is not None:
                    extra_context["promote_cutoff_url"] = reverse(
                        "admin:%s_%s_promote_by_cutoff" % (self.model._meta.app_label, self.model._meta.model_name),
                        args=[oid],
                    )
        return super().changeform_view(
            request, object_id, form_url, extra_context=extra_context
        )

    def _promote_by_cutoff_button(self, request, object_id):
        if request.method != "POST":
            self.message_user(request, "Use the button on the round change page (POST).", messages.WARNING)
            return redirect("admin:contest_round_changelist")
        r = get_object_or_404(Round, pk=object_id)
        if r.promotion_cutoff_score is None:
            self.message_user(
                request,
                "Set Promotion cutoff score on this round first.",
                messages.ERROR,
            )
            return redirect("admin:contest_round_change", object_id)
        ranked = (
            Submission.objects.filter(round=r)
            .values("participant_id")
            .annotate(total=Sum("score"))
            .filter(total__gte=r.promotion_cutoff_score)
        )
        ids = [row["participant_id"] for row in ranked]
        count, err = promote_participants_to_next_round(ids, r)
        if err:
            self.message_user(request, err, messages.ERROR)
        else:
            self.message_user(
                request,
                f"Promoted {count} participant(s) (score ≥ {r.promotion_cutoff_score}) to the next round.",
                messages.SUCCESS,
            )
        return redirect("admin:contest_round_change", object_id)

    def activate_round_in_week(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Select exactly one round to activate.", messages.ERROR)
            return
        selected = queryset.first()
        Round.objects.filter(week=selected.week).update(is_active=False)
        selected.is_active = True
        selected.save()
        self.message_user(request, f"{selected.round_name} is active in {selected.week.title}.", messages.SUCCESS)
    activate_round_in_week.short_description = "Activate selected round in its week"

    @admin.action(
        description="Promote to next round: everyone ≥ promotion cutoff score on this round"
    )
    def promote_by_cutoff_to_next_round(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Select exactly one source round.", messages.ERROR)
            return
        source_round = queryset.first()
        if source_round.promotion_cutoff_score is None:
            self.message_user(
                request,
                "Set Promotion cutoff score on this round before using this action.",
                messages.ERROR,
            )
            return
        cutoff = source_round.promotion_cutoff_score
        ranked = (
            Submission.objects.filter(round=source_round)
            .values("participant_id")
            .annotate(total=Sum("score"))
            .filter(total__gte=cutoff)
        )
        ids = [row["participant_id"] for row in ranked]
        count, err = promote_participants_to_next_round(ids, source_round)
        if err:
            self.message_user(request, err, messages.ERROR)
        else:
            self.message_user(
                request,
                f"Promoted {count} participant(s) with score ≥ {cutoff} to the next round.",
                messages.SUCCESS,
            )

@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = [
        "full_name",
        "user",
        "email",
        "total_score",
        "rank_display",
        "schedule_rounds_done",
        "current_round",
        "registered_at",
    ]
    list_filter = [
        "current_round",
    ]
    search_fields = ['full_name', 'user__username', 'email']
    readonly_fields = ['registered_at', 'updated_at']

    actions = [
        "unlock_active_round_for_selected",
        "reset_contest_progress",
        "export_participants_csv",
    ]

    def get_actions(self, request):
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            func, name, _desc = actions["delete_selected"]
            actions["delete_selected"] = (
                func,
                name,
                "Delete selected participant profiles (User accounts are kept)",
            )
        return actions
    
    fieldsets = (
        ("User Information", {"fields": ("user", "full_name", "email", "phone")}),
        (
            "Contest (weekly schedule)",
            {
                "description": (
                    "Truth for who finished which round is in "
                    "<strong>Quiz attempts</strong> (per schedule Round). "
                    "Total score sums all correct submissions."
                ),
                "fields": ("total_score", "current_round"),
            },
        ),
        (
            "Legacy — old fixed Round 1 / Round 2 only",
            {
                "classes": ("collapse",),
                "description": (
                    "These flags are only maintained for rounds with order 1 and 2. "
                    "Ignore for 3+ rounds; use Quiz attempts instead."
                ),
                "fields": (
                    "round1_completed",
                    "round2_completed",
                    "can_access_round2",
                ),
            },
        ),
        (
            "Timing",
            {
                "fields": (
                    "round1_time_taken",
                    "round2_time_taken",
                    "total_time_taken",
                )
            },
        ),
        (
            "Metadata",
            {"fields": ("registered_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    @admin.display(description="Schedule rounds done")
    def schedule_rounds_done(self, obj):
        n = QuizAttempt.objects.filter(participant=obj, is_completed=True).count()
        return n

    def rank_display(self, obj):
        rank = obj.rank
        if rank:
            if rank == 1:
                return format_html('🏆 {}', rank)
            elif rank == 2:
                return format_html('🥈 {}', rank)
            elif rank == 3:
                return format_html('🥉 {}', rank)
            else:
                return rank
        return '-'
    rank_display.short_description = 'Rank'

    @admin.action(description="Unlock active round for selected (mark earlier rounds in this week complete)")
    def unlock_active_round_for_selected(self, request, queryset):
        """
        Lets selected users play the currently active round without redoing prior rounds:
        creates/completes QuizAttempts for all earlier rounds in the active week.
        """
        active_week = Week.objects.filter(is_active=True).first()
        if not active_week:
            self.message_user(request, "No active week — activate one under Weeks (schedule).", messages.ERROR)
            return
        active_round = (
            active_week.rounds.filter(is_active=True).order_by("order_number").first()
        )
        if not active_round:
            self.message_user(request, "No active round in that week.", messages.ERROR)
            return
        prev_rounds = active_week.rounds.filter(
            order_number__lt=active_round.order_number
        ).order_by("order_number")
        if not prev_rounds.exists():
            self.message_user(
                request,
                f"{active_round.round_name} is the first round — nothing to unlock.",
                messages.INFO,
            )
            return

        updated = 0
        for participant in queryset:
            for pr in prev_rounds:
                att, created = QuizAttempt.objects.get_or_create(
                    participant=participant,
                    schedule_round=pr,
                    defaults={
                        "round_number": pr.order_number,
                        "is_completed": True,
                        "completed_at": timezone.now(),
                        "time_taken": 0,
                        "total_score": 0,
                    },
                )
                if not created and not att.is_completed:
                    att.is_completed = True
                    att.completed_at = timezone.now()
                    att.save()
                if pr.order_number == 1:
                    participant.round1_completed = True
                elif pr.order_number == 2:
                    participant.round2_completed = True
            participant.current_round = active_round.order_number
            if active_round.order_number >= 2:
                participant.can_access_round2 = True
            participant.save()
            updated += 1

        self.message_user(
            request,
            f"{updated} participant(s) can now start {active_round.round_name} in {active_week.title}.",
            messages.SUCCESS,
        )

    @admin.action(description="Reset contest progress for selected (scores, submissions, attempts)")
    def reset_contest_progress(self, request, queryset):
        for participant in queryset:
            participant.total_score = 0
            participant.current_round = 1
            participant.round1_completed = False
            participant.round2_completed = False
            participant.can_access_round2 = False
            participant.round1_time_taken = 0
            participant.round2_time_taken = 0
            participant.total_time_taken = 0
            participant.save()
            Submission.objects.filter(participant=participant).delete()
            QuizAttempt.objects.filter(participant=participant).delete()

        self.message_user(
            request,
            f"{queryset.count()} participant(s) fully reset for a new weekly run.",
            messages.SUCCESS,
        )

    @admin.action(description="Export selected participants to CSV")
    def export_participants_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="participants_export.csv"'

        writer = csv.writer(response)
        writer.writerow(
            [
                "Rank",
                "Full name",
                "Username",
                "Email",
                "Total score",
                "Display round (legacy)",
                "Round 1 done (legacy)",
                "Round 2 done (legacy)",
                "Unlock R2 flag (legacy)",
                "Total time (s)",
                "Registered",
            ]
        )

        for obj in queryset.order_by("-total_score", "total_time_taken"):
            writer.writerow(
                [
                    obj.rank,
                    obj.full_name,
                    obj.user.username,
                    obj.email,
                    obj.total_score,
                    obj.current_round,
                    obj.round1_completed,
                    obj.round2_completed,
                    obj.can_access_round2,
                    obj.total_time_taken,
                    obj.registered_at.isoformat() if obj.registered_at else "",
                ]
            )

        return response


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    change_list_template = "admin/contest/question/change_list.html"

    list_display = [
        'question_preview',
        'week_and_round',
        'round_number',
        'category',
        'difficulty',
        'points',
        'correct_answer',
        'order',
        'is_active',
    ]
    list_display_links = ['question_preview']
    list_filter = ['round__week', 'round', 'round_number', 'category', 'difficulty', 'is_active']
    search_fields = ['question_text', 'option_a', 'option_b', 'option_c', 'option_d']
    list_editable = ['is_active', 'order']
    ordering = ['round__week', 'round__order_number', 'order', 'category']

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Plain dropdown for Round (avoid autocomplete search box)."""
        if db_field.name == "round":
            kwargs["queryset"] = Round.objects.select_related("week").order_by(
                "week__start_date", "week__title", "order_number", "id"
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description="Week → Round")
    def week_and_round(self, obj):
        if obj.round_id:
            return format_html(
                "<strong>{}</strong><br/><span style='color:#555'>{}</span>",
                obj.round.week.title,
                obj.round.round_name,
            )
        return mark_safe(
            '<span style="color:#b45309">Set “Round” FK (legacy round # only)</span>'
        )

    fieldsets = (
        (
            "Schedule (week comes from round)",
            {
                "description": "Link each question to a <strong>Round</strong>; the week is that round’s week.",
                "fields": ("round", "round_number"),
            },
        ),
        ('Question Details', {
            'fields': ('category', 'question_text', 'order')
        }),
        ('Options', {
            'fields': ('option_a', 'option_b', 'option_c', 'option_d')
        }),
        ('Answer & Points', {
            'fields': ('correct_answer', 'points')
        }),
        ('Metadata', {
            'fields': ('difficulty', 'is_active')
        }),
    )
    
    actions = ['activate_questions', 'deactivate_questions', 'duplicate_questions', 'export_questions']

    def get_urls(self):
        urls = super().get_urls()
        opts = self.model._meta
        custom = [
            path(
                "import-csv/",
                self.admin_site.admin_view(self.import_csv_view),
                name="%s_%s_import_csv" % (opts.app_label, opts.model_name),
            ),
        ]
        return custom + urls

    def import_csv_view(self, request):
        if not self.has_add_permission(request):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied
        opts = self.model._meta

        if request.GET.get("template") == "1":
            fmt = (request.GET.get("format") or "csv").lower()
            if fmt == "xlsx":
                try:
                    body = xlsx_template_bytes()
                except ImportError:
                    self.message_user(
                        request,
                        "Excel template needs openpyxl: pip install openpyxl",
                        messages.ERROR,
                    )
                    return redirect("admin:%s_%s_import_csv" % (opts.app_label, opts.model_name))
                resp = HttpResponse(
                    body,
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                resp["Content-Disposition"] = (
                    'attachment; filename="questions_import_template.xlsx"'
                )
                return resp
            resp = HttpResponse(csv_template_content(), content_type="text/csv; charset=utf-8")
            resp["Content-Disposition"] = (
                'attachment; filename="questions_import_template.csv"'
            )
            return resp

        if request.method == "POST":
            upload = request.FILES.get("csv_file")
            round_id = (request.POST.get("schedule_round") or "").strip()
            target_round = None
            if round_id:
                try:
                    target_round = Round.objects.select_related("week").get(pk=int(round_id))
                except (ValueError, Round.DoesNotExist):
                    self.message_user(
                        request,
                        "Invalid or unknown round selected.",
                        messages.ERROR,
                    )
            else:
                self.message_user(
                    request,
                    "Select the target round before uploading.",
                    messages.ERROR,
                )

            if not upload:
                self.message_user(
                    request,
                    "Choose a CSV or Excel (.xlsx) file to upload.",
                    messages.ERROR,
                )

            if upload and target_round:
                raw = upload.read()
                name = (upload.name or "").lower()
                if name.endswith(".xlsx"):
                    created, errs, warns = import_questions_from_xlsx_bytes(raw, target_round)
                else:
                    try:
                        text = raw.decode("utf-8-sig")
                    except UnicodeDecodeError:
                        text = raw.decode("latin-1", errors="replace")
                    created, errs, warns = import_questions_from_csv_text(text, target_round)
                for w in warns[:25]:
                    self.message_user(request, w, messages.WARNING)
                for e in errs[:40]:
                    self.message_user(request, e, messages.ERROR)
                if created:
                    self.message_user(
                        request,
                        f"Successfully imported {created} question(s) into "
                        f"{target_round.week.title} — {target_round.round_name}.",
                        messages.SUCCESS,
                    )
                elif not errs:
                    self.message_user(
                        request,
                        "No rows were imported (empty or skipped).",
                        messages.WARNING,
                    )
                return redirect("admin:%s_%s_changelist" % (opts.app_label, opts.model_name))

        rounds = Round.objects.select_related("week").order_by(
            "-week__start_date",
            "week__title",
            "order_number",
            "id",
        )
        preselect = None
        if request.method == "POST":
            pr = (request.POST.get("schedule_round") or "").strip()
            if pr:
                try:
                    if rounds.filter(pk=int(pr)).exists():
                        preselect = int(pr)
                except ValueError:
                    pass
        else:
            rid = (request.GET.get("round") or "").strip()
            if rid:
                try:
                    if rounds.filter(pk=int(rid)).exists():
                        preselect = int(rid)
                except ValueError:
                    pass

        context = {
            **self.admin_site.each_context(request),
            "opts": opts,
            "title": "Import questions from CSV / Excel",
            "template_headers": TEMPLATE_HEADERS,
            "rounds": rounds,
            "preselect_round_id": preselect,
        }
        return TemplateResponse(
            request,
            "admin/contest/question/import_csv.html",
            context,
        )

    def question_preview(self, obj):
        preview = obj.question_text[:60] + '...' if len(obj.question_text) > 60 else obj.question_text
        return preview
    question_preview.short_description = 'Question'
    
    def activate_questions(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f'{count} question(s) activated', messages.SUCCESS)
    activate_questions.short_description = 'Activate selected questions'
    
    def deactivate_questions(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f'{count} question(s) deactivated', messages.WARNING)
    deactivate_questions.short_description = 'Deactivate selected questions'
    
    def duplicate_questions(self, request, queryset):
        for question in queryset:
            question.pk = None
            question.order = Question.objects.filter(round_number=question.round_number).count() + 1
            question.save()
        self.message_user(request, f'{queryset.count()} question(s) duplicated', messages.SUCCESS)
    duplicate_questions.short_description = 'Duplicate selected questions'
    
    def export_questions(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="questions.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'category',
            'question_text',
            'option_a',
            'option_b',
            'option_c',
            'option_d',
            'correct_answer',
            'difficulty',
            'points',
            'order',
            'is_active',
        ])
        
        for q in queryset:
            writer.writerow([
                q.category,
                q.question_text,
                q.option_a,
                q.option_b,
                q.option_c,
                q.option_d,
                q.correct_answer,
                q.difficulty,
                q.points,
                q.order,
                'true' if q.is_active else 'false',
            ])
        
        return response
    export_questions.short_description = 'Export to CSV'


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = [
        'participant',
        'question',
        'round_number',
        'selected_answer',
        'is_correct',
        'points_earned',
        'time_taken',
        'submitted_at'
    ]
    list_filter = ['round_number', 'is_correct', 'question__category']
    search_fields = ['participant__full_name', 'participant__user__username']
    readonly_fields = ['is_correct', 'points_earned', 'submitted_at']
    date_hierarchy = 'submitted_at'
    
    def has_add_permission(self, request):
        return False


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = [
        'participant',
        'schedule_round',
        'round_number',
        'started_at',
        'is_completed',
        'total_score',
        'time_taken',
        'completed_at'
    ]
    list_filter = ['round_number', 'is_completed', 'schedule_round__week']
    search_fields = ['participant__full_name', 'participant__user__username']
    readonly_fields = ['started_at', 'completed_at']
    date_hierarchy = 'started_at'


# Customize Admin Site
admin.site.site_header = '🧠 Aptitude Contest Admin'
admin.site.site_title = 'Contest Admin'
admin.site.index_title = 'Contest Management Dashboard'