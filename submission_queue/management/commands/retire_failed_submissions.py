import logging

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import models

from submission_queue.consumer import post_failure_to_lms
from submission_queue.models import Submission

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = """
           Retire submissions that have more than settings.MAX_NUMBER_OF_FAILURES failures.\
           Notify the LMS/student that the queue will no longer attempt to process the submission.\
           Optional <queue_name> - no queue name provided means all queues will be processed.
           """

    def add_arguments(self, parser):
        parser.add_argument('queue_name', nargs='*')
        parser.add_argument(
            '-f', '--force',
            action='store_true',
            dest='force',
            default=False,
            help='Force retire submissions',
        )

    def handle(self, *args, **options):
        log.info(' [*] Scanning Submission database to retire failed submissions...')

        force = options['force']
        if force:
            log.info(" [ ] Force retiring all failed submissions...")

        queue_names = options['queue_name']
        if len(queue_names) == 0:
            failed_submissions = Submission.objects.filter(retired=models.Value(0))
            failed_submissions = failed_submissions.exclude(num_failures=0)
            self.retire_submissions(failed_submissions, force)
        else:
            for queue_name in queue_names:
                failed_submissions = Submission.objects.filter(queue_name=queue_name, retired=models.Value(0))
                failed_submissions = failed_submissions.exclude(num_failures=0)
                self.retire_submissions(failed_submissions, force)

    def retire_submissions(self, failed_submissions, force):
        for failed_submission in failed_submissions:
            if failed_submission.num_failures >= settings.MAX_NUMBER_OF_FAILURES:
                log.info(" [ ] Retiring submission id=%d from queue '%s' with num_failures=%d" %
                         (failed_submission.id, failed_submission.queue_name, failed_submission.num_failures))
                if force:
                    failed_submission.retired = True  # Mark as done without contacting LMS
                else:
                    failed_submission.lms_ack = post_failure_to_lms(failed_submission.xqueue_header)
                    failed_submission.retired = failed_submission.lms_ack
                    if not failed_submission.lms_ack:
                        log.error(' [ ] Could not contact LMS to retire submission id=%d' % failed_submission.id)
                failed_submission.save()
