from django.core.management.base import BaseCommand
from development.launch import open_due_reviews

class Command(BaseCommand):
    help='Open Gate 3 for projects that have reached Day 45 after Launch GO.'
    def handle(self,*args,**options):
        count=open_due_reviews()
        self.stdout.write('Opened %s Gate 3 reviews.'%count)
