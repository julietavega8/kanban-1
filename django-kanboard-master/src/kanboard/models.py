import datetime

from django.db import models

from kanboard import signals

class Card(models.Model):
    title = models.CharField(max_length=80)
    board = models.ForeignKey("Board", related_name="cards")
    phase = models.ForeignKey("Phase", related_name="cards")
    order = models.SmallIntegerField()
    created_by = models.ForeignKey('auth.User')
    backlogged_at = models.DateTimeField(default=datetime.datetime.now)

    started_at = models.DateTimeField(blank=True, null=True)
    done_at = models.DateTimeField(blank=True, null=True)
    description = models.TextField(blank=True)
    size = models.CharField(max_length=80, blank=True)
    color = models.CharField(max_length=7, blank=True)
    ready = models.BooleanField()
    blocked = models.BooleanField()
    blocked_because = models.TextField(blank=True)

    class Meta:
        ordering = ['order', ]

    def __unicode__(self):
        return "%s - %s (%s) -- %s" % (self.id, self.title, self.order, self.phase.title)

    def change_phase(self, new_phase, change_at=None):
        if not change_at:
            change_at = datetime.datetime.now()

        if self.phase.status == Phase.UPCOMING:
            if new_phase.status in (Phase.PROGRESS, Phase.FINISHED):
                self.started_at = change_at
            elif new_phase.status == Phase.UPCOMING and self.started_at:
                self.started_at == None
        elif new_phase.status == Phase.FINISHED:
            if not self.done_at:
                self.done_at = change_at
        elif new_phase.status == Phase.PROGRESS:
            if self.done_at:
                self.done_at == None

        from_phase = self.phase
        self.phase = new_phase
        self.save()

        signals.phase_change.send(sender=self, from_phase=from_phase,
                                  to_phase=new_phase, changed_at=change_at)

signals.phase_change.connect(signals.update_phase_log)
models.signals.pre_save.connect(signals.card_order, sender=Card)


class Board(models.Model):
    title = models.CharField(max_length=80)
    slug = models.SlugField()

    #Optional fields
    description = models.TextField(blank=True)

    def __unicode__(self):
        return self.title
    
    @models.permalink
    def get_absolute_url(self):
        return 'kanboard', [self.slug]

models.signals.post_save.connect(signals.create_default_phases, sender=Board)


class Phase(models.Model):
    UPCOMING = 'upcoming'
    PROGRESS = 'progress'
    FINISHED = 'finished'
    STATUSES = (
        (UPCOMING, 'Upcoming'),
        (PROGRESS, 'In progress'),
        (FINISHED, 'Finished'),
    )

    title = models.CharField(max_length=80)
    board = models.ForeignKey("Board", related_name="phases")
    order = models.SmallIntegerField()
    status = models.CharField(max_length=25, choices=STATUSES,default=PROGRESS)

    description = models.TextField(blank=True)
    limit = models.SmallIntegerField(blank=True, null=True)

    class Meta:
        ordering = ['order']

    def __unicode__(self):
        return u"%s - %s (%s)" % (self.board.title, self.title, self.order)

    def update_log(self, count, changed_at):
        log, created = PhaseLog.objects.get_or_create(phase=self,date=changed_at)
        log.count = count
        log.save()

models.signals.post_save.connect(signals.update_phase_order, sender=Phase)
models.signals.post_save.connect(signals.create_phase_log, sender=Phase)

class PhaseLog(models.Model):
    phase = models.ForeignKey(Phase, related_name='logs')
    count = models.SmallIntegerField(default=0)
    date = models.DateField()

    class Meta:
        unique_together = ('phase', 'date')

    def __unicode__(self):
        return u"%s log on %s - %s" % (self.phase.title, self.date, self.count)

#TODO: Implement goal object


class KanboardStats(object):
    def __init__(self, board):
        self.board = board

    def delta_from_done(self, attr_name, start=None, finish=None):
        now = datetime.datetime.now()
        if not finish: finish = now

        cards = Card.objects.filter(board=self.board, done_at__lte=finish)
        if start:
            cards = cards.filter(done_at__gte=start)

        if not cards:
            return datetime.timedelta()

        deltas = [ card.done_at - getattr(card, attr_name) for card in cards ]
        the_sum = sum(deltas, datetime.timedelta())
        return the_sum / cards.count()

    def cycle_time(self, start=None, finish=None):
        return self.delta_from_done('started_at', start, finish)

    def lead_time(self, start=None, finish=None)
        return self.delta_from_done('backlogged_at', start, finish)

    def cumulative_flow(self, date=None):

        if date is None: date = datetime.date.today()

        result = {}
        for phase in self.board.phases.all():
            try:
                log = PhaseLog.objects.filter(phase=phase, date__lte=date).order_by('-date')[0]
                result[phase.title] = log.count
            except IndexError:
                result[phase.title] = 0

        backlog, archive = self.board.get_backlog(), self.board.get_archive()
        archive_count = result[archive.title]
        result[backlog.title] += archive_count
        del result[archive.title]

        return result

