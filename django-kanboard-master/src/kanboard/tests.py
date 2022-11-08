import datetime
import random

from django.test import TestCase

from kanboard.models import Board, Card, Phase, KanboardStats

class KanboardTestCase(TestCase):
    def setUp(self):
        self.board = self.create_board()

        self.backlog = self.board.get_backlog()
        self.ideation = self.create_phase(save=True, title="Ideation", order=1, board=self.board)
        self.design = self.create_phase(save=True, title="Design", order=2, board=self.board)
        self.dev = self.create_phase(save=True, title="Development", order=3, board=self.board)
        self.test = self.create_phase(save=True, title="Testing", order=4, board=self.board)
        self.deploy = self.create_phase(save=True, title="Deployment", order=5, board=self.board)
        self.done = self.board.get_done()
        self.archive = self.board.get_archive()
        
        super(KanboardTestCase, self).setUp()

    def random_int(self):
        return random.randint(1, 1000)

    def create_board(self, save=True, **kwargs):
        index = self.random_int()
        defaults = {
            'title': 'Test Board %s' % index,
            'slug': 'test-board-%s' % index,
        }
        defaults.update(kwargs)
        b = self.create_object(Board, save, defaults)
        if save:
            self.assert_(b.title)
            self.assert_(b.slug)
        return b

    def create_card(self, save=True, **kwargs):
        index = self.random_int()
        phase = self.create_phase()
        defaults = {
            'title': 'Card %s' % index,
            'phase': phase,
            'order': 0,
            'board': phase.board
        }
        defaults.update(kwargs)
        c = self.create_object(Card, save, defaults)
        if save:
            self.assert_(c.title)
            self.assert_(c.phase)
            self.assertNotEqual(None, c.order) #Because order can be 0
        return c

    def create_phase(self, save=True, **kwargs):
        index = self.random_int()
        board = self.create_board()
        defaults = {
            'title': 'Phase %s' % index,
            'board': board,
            'order': 0,
        }
        defaults.update(kwargs)

        p = self.create_object(Phase, save, defaults)
        if save:
            self.assert_(p.title)
            self.assert_(p.board)
            self.assertNotEqual(None, p.order)
        return p

    def create_object(self, klass, save=True, kwargs={}):
        o = klass(**kwargs) 
        if save:
            o.save()
            self.assert_(o.id, "Unable to save %s" % o)
        return o


class KanboardTests(KanboardTestCase):
    def test_create(self):
        b = self.create_board()
        self.assert_(b.id)

        c = self.create_card()
        self.assert_(c.id)

        p = self.create_phase()
        self.assert_(p.id)

    def test_board_auto_phases(self):
        b = self.create_board()
        self.assertEqual(3, len(b.phases.all()))

        self.assert_(b.get_backlog())
        self.assert_(b.get_done())
        self.assert_(b.get_archive())

    def test_phase_ordering(self):
        expected = [self.board.get_backlog(), self.ideation, self.design, self.dev, self.test, self.deploy, self.board.get_done(), self.board.get_archive()]
        actual = list(self.board.phases.all())
       
        from pprint import pformat
        msg = "%s\n%s" % (pformat(expected), pformat(actual))
        self.assertEqual(expected, actual, msg)

    def test_cards_ordering(self):
        backlog = self.board.get_backlog()

        common_args = dict(save=True, phase=backlog)
        card2 = self.create_card(order=2, **common_args)
        card1 = self.create_card(order=1, **common_args)
        card0 = self.create_card(order=0, **common_args)

        expected = [card0, card1, card2]
        actual = list(backlog.cards.all())

        self.assertEqual(expected, actual)
    
    def test_card_changing_phase(self):
        card = self.create_card(phase=self.backlog)
        self.assert_(card.backlogged_at)

        card.change_phase(self.ideation)
        self.assert_(card.started_at)

        card.change_phase(self.design)
        card.change_phase(self.done)
        self.assert_(card.done_at)
        done_at = card.done_at

        card.change_phase(self.archive)
        self.assertEqual(done_at, card.done_at)

    def test_phase_change_with_datetime(self):
        now = datetime.datetime.now()
        later = datetime.datetime.now() + datetime.timedelta(days=2)
        way_later = later + datetime.timedelta(days=7)

        card = self.create_card(phase=self.backlog, backlogged_at=now)
        self.assertEqual(card.backlogged_at, now)

        card.change_phase(self.design, change_at=later)
        self.assertEqual(card.started_at, later)

        card.change_phase(self.archive, change_at=way_later)
        self.assertEqual(card.done_at, way_later)

class StatsTests(KanboardTestCase):
    def setUp(self):
        super(StatsTests, self).setUp()
        self.stats = KanboardStats(board=self.board)

    def set_up_board(self, expected_counts, board=None, date=None):
        if board is None:
            board = self.board

        if date is None:
            date = datetime.date.today()

        for phase_name, count in expected_counts.items():
            phase = Phase.objects.get(title=phase_name, board=self.board)
            for i in xrange(0, count):
                card = self.create_card(phase=self.backlog, backlogged_at=date, board=board)
                card.change_phase(phase, change_at=date) 

    def test_cycle_time(self):
        board = {
            u'Backlog': 4,
        } 
        board_start = datetime.datetime.now() - datetime.timedelta(days=10)
        self.set_up_board(board, date=board_start)

        self.assertEqual(0, self.stats.cycle_time().days)

        nine_days_ago = datetime.datetime.now() - datetime.timedelta(days=9)
        card = self.backlog.cards.all()[0]
        card.change_phase(self.design, change_at=nine_days_ago)
        card.change_phase(self.done)
        self.assertEqual(9, self.stats.cycle_time().days)

        five_days_ago = datetime.datetime.now() - datetime.timedelta(days=5)
        card = self.backlog.cards.all()[0]
        card.change_phase(self.dev, change_at=five_days_ago)
        card.change_phase(self.archive)
        self.assertEqual(7, self.stats.cycle_time().days)

    def test_lead_time(self):
        board = {
            u'Backlog': 4,
        } 
        board_start = datetime.datetime.now() - datetime.timedelta(days=3)
        self.set_up_board(board, date=board_start)

        self.assertEqual(0, self.stats.lead_time().days )

        card = self.backlog.cards.all()[0]
        one_day_ago = datetime.datetime.now() - datetime.timedelta(days=1)
        card.change_phase(self.done, change_at=one_day_ago) 
        self.assertEqual(2, self.stats.lead_time().days)
        self.assertEqual(0, self.stats.lead_time().seconds)

        card = self.backlog.cards.all()[1]
        card.change_phase(self.done)
        self.assertEqual(2, self.stats.lead_time().days) 
        self.assertEqual(12 * 60 * 60, self.stats.lead_time().seconds) 

        lead_time = self.stats.lead_time(start=one_day_ago, finish=one_day_ago)
        self.assertEqual(2, lead_time.days)
        self.assertEqual(0, lead_time.seconds)

        today = datetime.date.today()
        lead_time = self.stats.lead_time(start=today)
        self.assertEqual(3, lead_time.days)

    def test_cumulative_flow(self):
        expected = {
            u'Backlog': 5,
            u'Ideation': 2,
            u'Design': 7,
            u'Development': 3,
            u'Testing': 6,
            u'Deployment': 1,
            u'Done': 3,
        }
        self.set_up_board(expected)

        self.assertEqual(expected, self.stats.cumulative_flow())

        card = self.test.cards.all()[0]
        card.change_phase(self.deploy)
    
        expected[u'Testing'] = 5
        expected[u'Deployment'] = 2
        result = self.stats.cumulative_flow()
        self.assertEqual(expected[u'Testing'], result[u'Testing'])
        self.assertEqual(expected[u'Deployment'], result[u'Deployment'])

        card = self.dev.cards.all()[0]
        card.change_phase(self.design)

        expected[u'Development'] = 2
        expected[u'Design'] = 8
        self.assertEqual(expected, self.stats.cumulative_flow())

    def test_cumulative_flow_dates(self):
        four_days_ago = datetime.date.today() - datetime.timedelta(days=4)
        three_days_ago = datetime.date.today() - datetime.timedelta(days=3)
        two_days_ago = datetime.date.today() - datetime.timedelta(days=2)
        one_day_ago = datetime.date.today() - datetime.timedelta(days=1)

        three_ago_expected = {
            u'Backlog': 5,
            u'Ideation': 2,
            u'Design': 5,
            u'Development': 4,
            u'Testing': 6,
            u'Deployment': 2,
            u'Done': 0,
        }
        self.set_up_board(three_ago_expected, date=three_days_ago)
        self.assertEqual(three_ago_expected,
                         self.stats.cumulative_flow(three_days_ago))

        self.deploy.cards.all()[0].change_phase(self.done, change_at=one_day_ago) 
        one_ago_expected = {
            u'Backlog': 5,
            u'Ideation': 2,
            u'Design': 5,
            u'Development': 4,
            u'Testing': 6,
            u'Deployment': 1,
            u'Done': 1,
        }
        self.assertEqual(one_ago_expected,
                         self.stats.cumulative_flow(one_day_ago))

        self.assertEqual(three_ago_expected,
                         self.stats.cumulative_flow(two_days_ago)) 


        four_ago_expected = {
            u'Backlog': 0,
            u'Ideation': 0,
            u'Design': 0,
            u'Development': 0,
            u'Testing': 0,
            u'Deployment': 0,
            u'Done': 0,
        }
        self.assertEqual(four_ago_expected,self.stats.cumulative_flow(four_days_ago))


