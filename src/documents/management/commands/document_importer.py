import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command

from documents.models import Document
from paperless.db import GnuPG

from ...mixins import Renderable


class Command(Renderable, BaseCommand):

    help = """
        Using a manifest.json file, load the data from there, and import the
        documents it refers to.
    """.replace("    ", "")

    def add_arguments(self, parser):
        parser.add_argument("source")

    def __init__(self, *args, **kwargs):
        BaseCommand.__init__(self, *args, **kwargs)
        self.source = None
        self.manifest = None

    def handle(self, *args, **options):

        self.source = options["source"]

        if not os.path.exists(self.source):
            raise CommandError("That path doesn't exist")

        if not os.access(self.source, os.R_OK):
            raise CommandError("That path doesn't appear to be readable")

        manifest_path = os.path.join(self.source, "manifest.json")
        self._check_manifest_exists(manifest_path)

        with open(manifest_path) as f:
            self.manifest = json.load(f)

        self._check_manifest()

        if not settings.PASSPHRASE:
            raise CommandError(
                "You need to define a passphrase before continuing.  Please "
                "consult the documentation for setting up Paperless."
            )

        # Fill up the database with whatever is in the manifest
        call_command("loaddata", manifest_path)

        self._import_files_from_manifest()

    @staticmethod
    def _check_manifest_exists(path):
        if not os.path.exists(path):
            raise CommandError(
                "That directory doesn't appear to contain a manifest.json "
                "file."
            )

    def _check_manifest(self):

        for record in self.manifest:

            if not record["model"] == "documents.document":
                continue

            if "__exported_file_name__" not in record:
                raise CommandError(
                    'The manifest file contains a record which does not '
                    'refer to an actual document file.'
                )

            doc_file = record["__exported_file_name__"]
            if not os.path.exists(os.path.join(self.source, doc_file)):
                raise CommandError(
                    'The manifest file refers to "{}" which does not '
                    'appear to be in the source directory.'.format(doc_file)
                )

    def _import_files_from_manifest(self):

        for record in self.manifest:

            if not record["model"] == "documents.document":
                continue

            doc_file = record["__exported_file_name__"]
            document = Document.objects.get(pk=record["pk"])
            with open(doc_file, "rb") as unencrypted:
                with open(document.source_path, "wb") as encrypted:
                    print("Encrypting {} and saving it to {}".format(
                        doc_file, document.source_path))
                    encrypted.write(GnuPG.encrypted(unencrypted))
