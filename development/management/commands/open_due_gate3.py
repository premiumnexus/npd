from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help='Retired: Gate 3 is entered manually without an elapsed-day restriction.'
    def handle(self,*args,**options):
        self.stdout.write('Automatic Gate 3 opening is disabled. Move from Launch GO to Gate 3 in the workflow at any time.')
